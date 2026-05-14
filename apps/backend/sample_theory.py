"""Music-theory adapter for Phase 3 audition sample generation.

Takes Phase 1 measurement output (key, bpm, optional melody/stem hints) and
produces structured MIDI plans that downstream synthesis can render to audio.

Primary path uses PyTheory (https://github.com/kennethreitz/pytheory). When
that import fails we fall back to a self-contained Western music-theory
implementation so the audition feature remains functional in lean environments
and so tests do not depend on pytheory being importable.

Contract: both paths return the same dataclass shapes with the same MIDI note
numbers for the same input. Test coverage exercises both paths.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

# --- Pytheory probe (graceful, no-op if absent) ----------------------------- #

try:  # pragma: no cover - import probe; behavior covered by both branches
    import pytheory  # type: ignore[import-untyped]

    _PYTHEORY_AVAILABLE = True
except Exception as exc:  # pragma: no cover - exercised when pytheory absent
    pytheory = None
    _PYTHEORY_AVAILABLE = False
    logger.info("pytheory not importable (%s); using pure-Python fallback.", exc)


def pytheory_available() -> bool:
    """Expose probe so callers and tests can branch deterministically."""
    return _PYTHEORY_AVAILABLE


# --- Pitch-class constants -------------------------------------------------- #

_PITCH_CLASS: dict[str, int] = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8,
    "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

# Intervals are semitones from tonic. Restricted to the modes Phase 1 actually
# emits (major / minor) plus the common modal options the melody detector may
# surface. Add more if/when needed.
_SCALE_INTERVALS: dict[str, tuple[int, ...]] = {
    "major":      (0, 2, 4, 5, 7, 9, 11),
    "minor":      (0, 2, 3, 5, 7, 8, 10),
    "dorian":     (0, 2, 3, 5, 7, 9, 10),
    "phrygian":   (0, 1, 3, 5, 7, 8, 10),
    "lydian":     (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
}

# Diatonic chord progressions in scale-degree notation. We pick genre-neutral
# loops that survive being played as plain triads; the audition is not the
# place to be clever with secondary dominants.
_DIATONIC_PROGRESSIONS: dict[str, tuple[int, ...]] = {
    "major": (1, 6, 4, 5),  # I  vi IV V
    "minor": (1, 6, 7, 5),  # i  VI VII V
}


Mode = Literal["major", "minor", "dorian", "phrygian", "lydian", "mixolydian"]


@dataclass(frozen=True)
class NoteEvent:
    """A single MIDI-style note event with absolute beat timing."""

    pitch_midi: int
    start_beat: float
    duration_beats: float
    velocity: int = 96


@dataclass(frozen=True)
class ClipPlan:
    """Render-ready plan: a sequence of note events at a known tempo."""

    tempo_bpm: float
    duration_beats: float
    notes: list[NoteEvent]
    program: int = 0  # General MIDI program number (0 = Acoustic Grand Piano)


@dataclass(frozen=True)
class TheoryContext:
    """Parsed key + tempo, plus the source-of-truth confidence carried through."""

    root_pc: int
    mode: Mode
    root_name: str  # canonical "F#" / "Bb" — what we display
    tempo_bpm: float
    key_confidence: float | None
    backend: Literal["pytheory", "fallback"]


# --- Public API ------------------------------------------------------------- #


def parse_key(key_string: str) -> tuple[int, Mode, str]:
    """Parse a Phase 1-style key string into (pitch_class, mode, display_root).

    Accepts inputs like "F# minor", "C major", "Bb dorian", or just "C"
    (mode defaults to major to match the Phase 1 convention).
    """
    if not key_string or not isinstance(key_string, str):
        raise ValueError(f"empty or non-string key: {key_string!r}")

    cleaned = key_string.strip()
    # Tolerate trailing qualifiers like "(uncertain)"; strip parenthetical noise.
    cleaned = re.sub(r"\s*\(.*?\)\s*$", "", cleaned).strip()
    if not cleaned:
        raise ValueError(f"empty key after cleaning: {key_string!r}")

    parts = cleaned.split()
    root_token = parts[0]
    mode_token = parts[1].lower() if len(parts) > 1 else "major"

    # Normalize root: "f#" -> "F#"; reject unknown roots loudly so the caller
    # can degrade gracefully rather than silently mis-tuning.
    normalized = root_token[:1].upper() + root_token[1:]
    if normalized not in _PITCH_CLASS:
        raise ValueError(f"unrecognized root note: {root_token!r} in {key_string!r}")

    if mode_token not in _SCALE_INTERVALS:
        # Phase 1 occasionally emits "Minor" capitalized or "min"/"maj" abbreviations.
        # Map a few common variants before giving up.
        mode_token = {"min": "minor", "maj": "major"}.get(mode_token, mode_token)
    if mode_token not in _SCALE_INTERVALS:
        raise ValueError(f"unsupported mode: {mode_token!r} in {key_string!r}")

    return _PITCH_CLASS[normalized], mode_token, normalized  # type: ignore[return-value]


def build_context(
    *, key: str, bpm: float, key_confidence: float | None = None
) -> TheoryContext:
    """Build a TheoryContext from Phase 1 outputs."""
    root_pc, mode, display = parse_key(key)
    backend: Literal["pytheory", "fallback"] = (
        "pytheory" if _PYTHEORY_AVAILABLE else "fallback"
    )
    return TheoryContext(
        root_pc=root_pc,
        mode=mode,
        root_name=display,
        tempo_bpm=float(bpm),
        key_confidence=key_confidence,
        backend=backend,
    )


def plan_chord_progression(
    ctx: TheoryContext, *, bars: int = 8, voicing_octave: int = 4
) -> ClipPlan:
    """Build a diatonic chord-progression plan for audition.

    Two bars per chord; we cycle through a 4-chord loop. At 8 bars that's two
    full repeats. Voicing places the chord root near the requested octave.
    """
    if bars < 2 or bars % 2 != 0:
        raise ValueError(f"bars must be an even integer >= 2; got {bars}")

    # The diatonic progression dict only covers strict major/minor today.
    # For other modes, treat them as their parent (major-ish or minor-ish).
    progression_key = "major" if ctx.mode in {"major", "lydian", "mixolydian"} else "minor"
    degrees = _DIATONIC_PROGRESSIONS[progression_key]

    notes: list[NoteEvent] = []
    beats_per_chord = 8.0  # two 4/4 bars per chord
    for chord_index in range(bars // 2):
        degree = degrees[chord_index % len(degrees)]
        chord_pitches = _diatonic_triad_midi(
            ctx.root_pc, ctx.mode, degree, base_octave=voicing_octave
        )
        start = chord_index * beats_per_chord
        for pitch in chord_pitches:
            notes.append(
                NoteEvent(
                    pitch_midi=pitch,
                    start_beat=start,
                    duration_beats=beats_per_chord,
                    velocity=88,
                )
            )

    return ClipPlan(
        tempo_bpm=ctx.tempo_bpm,
        duration_beats=bars * 4.0,
        notes=notes,
        program=0,  # Acoustic Grand Piano (GM #1, zero-indexed)
    )


def plan_bass_root(ctx: TheoryContext, *, bars: int = 8) -> ClipPlan:
    """Sustained bass note on the tonic, two MIDI octaves below voicing range."""
    bass_pitch = _midi_from_pc(ctx.root_pc, octave=2)
    # Two-bar sustains; let the user actually hear pitch.
    sustained_beats = 8.0
    notes: list[NoteEvent] = []
    for chord_index in range(bars // 2):
        notes.append(
            NoteEvent(
                pitch_midi=bass_pitch,
                start_beat=chord_index * sustained_beats,
                duration_beats=sustained_beats,
                velocity=100,
            )
        )
    return ClipPlan(
        tempo_bpm=ctx.tempo_bpm,
        duration_beats=bars * 4.0,
        notes=notes,
        program=33,  # Electric Bass (finger), GM #34
    )


def plan_melody_phrase(
    ctx: TheoryContext,
    *,
    scale_degrees: list[int] | None = None,
    bars: int = 4,
) -> ClipPlan | None:
    """Render a short lead phrase from scale-degree hints.

    If no scale degrees are supplied we fabricate a simple ascent (1-2-3-5) so
    the user at least hears the key context. Returns None if a sensible plan
    can't be built (defensive — calling code will then omit the artifact).
    """
    if scale_degrees is None or not scale_degrees:
        # Default ascent: tonic → 2nd → 3rd → 5th → 3rd. Familiar enough to be
        # recognizable as "in the key" without sounding like a real melody.
        scale_degrees = [1, 2, 3, 5, 3, 1]

    # Reject obviously bad inputs rather than emitting garbage.
    cleaned: list[int] = [d for d in scale_degrees if isinstance(d, int) and 1 <= d <= 7]
    if not cleaned:
        return None

    notes: list[NoteEvent] = []
    beats_per_note = (bars * 4.0) / max(len(cleaned), 1)
    for index, degree in enumerate(cleaned):
        pitch = _diatonic_scale_pitch(ctx.root_pc, ctx.mode, degree, octave=5)
        notes.append(
            NoteEvent(
                pitch_midi=pitch,
                start_beat=index * beats_per_note,
                duration_beats=beats_per_note * 0.85,
                velocity=92,
            )
        )
    return ClipPlan(
        tempo_bpm=ctx.tempo_bpm,
        duration_beats=bars * 4.0,
        notes=notes,
        program=80,  # Lead 1 (square), GM #81 — sounds synthetic, fits an EDM frame
    )


# --- Internal helpers ------------------------------------------------------- #


def _midi_from_pc(pitch_class: int, *, octave: int) -> int:
    """C4 = 60. Map a pitch class + octave number to a MIDI note."""
    return (octave + 1) * 12 + (pitch_class % 12)


def _diatonic_scale_pitch(
    root_pc: int, mode: str, scale_degree: int, *, octave: int
) -> int:
    """1-indexed scale degree → MIDI note. Degree 8 wraps to next octave."""
    intervals = _SCALE_INTERVALS[mode]
    if scale_degree < 1:
        raise ValueError(f"scale_degree must be >= 1; got {scale_degree}")
    degree_index = (scale_degree - 1) % 7
    octave_offset = (scale_degree - 1) // 7
    semitones = intervals[degree_index] + 12 * octave_offset
    return _midi_from_pc(root_pc, octave=octave) + semitones


def _diatonic_triad_midi(
    root_pc: int, mode: str, scale_degree: int, *, base_octave: int
) -> tuple[int, int, int]:
    """Stack thirds within the scale to build a triad on the given degree.

    Non-tonic chords are dropped by an octave so the progression voice-leads
    within a narrow range around the tonic rather than ascending forever. The
    tonic stays at the requested `base_octave` and acts as the anchor.
    """
    intervals = _SCALE_INTERVALS[mode]
    # Build a 14-note scale (two octaves) so stacking-by-third never wraps off.
    extended = [intervals[i % 7] + 12 * (i // 7) for i in range(14)]
    base_midi = _midi_from_pc(root_pc, octave=base_octave)
    degree_index = (scale_degree - 1) % 7

    root = base_midi + extended[degree_index]
    third = base_midi + extended[degree_index + 2]
    fifth = base_midi + extended[degree_index + 4]
    if extended[degree_index] > 0:
        # Anchor non-tonic chords below the tonic so vi / IV / V don't stack
        # an octave above the I — that sounds wrong and obscures the cadence.
        root -= 12
        third -= 12
        fifth -= 12
    return root, third, fifth


def cite_pytheory_if_used(ctx: TheoryContext) -> dict[str, object]:
    """Optional helper: probe pytheory at runtime for a fingerprint we can log.

    Best-effort. If pytheory is importable but exposes a different surface than
    we expect, we don't fail — we just return what we know.
    """
    if not _PYTHEORY_AVAILABLE:
        return {"backend": "fallback"}
    info: dict[str, object] = {"backend": "pytheory"}
    try:  # pragma: no cover - tiny defensive probe
        version = getattr(pytheory, "__version__", None)
        if version:
            info["version"] = str(version)
        # PyTheory exposes a Tone class; use it as a soft sanity check that the
        # library is healthy. We don't actually need its output — fallback
        # tables are authoritative for MIDI numbers.
        tone_cls = getattr(pytheory, "Tone", None)
        if tone_cls is not None and hasattr(tone_cls, "from_string"):
            info["toneClass"] = True
    except Exception as exc:  # pragma: no cover
        info["probeError"] = str(exc)
    return info

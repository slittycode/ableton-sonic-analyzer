#!/usr/bin/env python3
"""Build the generated-on-demand fundamentals synthetic audio corpus.

Audio is intentionally not committed. This script emits deterministic WAV files
under tests/fixtures/fundamentals_tracks plus a JSON manifest that activates the
fundamentals evaluation harness without relying on owner-provided audio.

Fixture design notes (empirically validated against the shipping detectors):

- Two drum-clip roles with conflicting needs are kept separate:
  * GRID clips (tempo / beatGrid / downbeats / meter checks) use a musically
    natural pattern — kick on every beat with an accented downbeat, hats on
    every 8th-note "and", snare with the kick mid-bar — because the beat
    tracker needs plausible rhythm. Percussion counts are NOT checked here
    (coincident kick+snare onsets merge into one band transient).
  * COUNT clips (kick/snare/hihat count checks) use band-disjoint engineered
    one-shots placed so no two instruments ever share an instant.
- One-shots are engineered in this script rather than reusing sample_drums:
  the product kick's pitch-sweep onset and broadband click land inside the
  snare detector's 120-2000 Hz band and get counted as snares. A 50 Hz sine
  with a 20 ms fade-in has zero snare-band presence (verified: kick-only
  renders produce zero snare-band onsets), and band-passed noise bursts keep
  snare (300-1500 Hz) and hat (4-10 kHz) inside their own detector bands.
- Chord truth labels are computed from the triad's pitch classes and spelled
  flat to match the Viterbi chord vocab (analyze_segments._state_label_short).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy.signal import butter, filtfilt

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sample_synthesis import SAMPLE_RATE, render_clip, write_wav  # noqa: E402
from sample_theory import (  # noqa: E402
    ClipPlan,
    NoteEvent,
    build_context,
    plan_bass_root,
    _SCALE_INTERVALS,
    _diatonic_triad_midi,
)

SCHEMA_VERSION = "fundamentals-eval.v1"
TARGET_PROFILE = "electronic_ableton_v1"

# Flat spellings match the Viterbi chord vocab (_PITCH_CLASS_NAMES_FLAT).
_PC_NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


@dataclass(frozen=True)
class RenderedClip:
    samples: np.ndarray
    truth: dict[str, Any]


# --- Engineered one-shots ---------------------------------------------------- #


def _eng_kick(*, fundamental_hz: float = 50.0, decay_s: float = 0.06) -> np.ndarray:
    """Pure decaying sine. Two properties are load-bearing:

    - The 20 ms fade-in: a sharper attack splatters energy above 120 Hz and
      the snare-band detector counts kicks as snares.
    - The 0.20 s total length: it must end before the next 8th-note instant
      (0.234 s at 128 BPM), because even a -64 dB snare residual riding the
      kick's low-band decay tail forms a countable local maximum above the
      kick detector's absolute 0.01 envelope floor.
    """
    t = np.arange(int(SAMPLE_RATE * 0.20)) / SAMPLE_RATE
    body = np.sin(2.0 * np.pi * fundamental_hz * t) * np.exp(-t / decay_s)
    fade = int(0.020 * SAMPLE_RATE)
    body[:fade] *= np.linspace(0.0, 1.0, fade)
    return (body * 0.95).astype(np.float32)


def _eng_burst(
    *, lo_hz: float, hi_hz: float, decay_s: float, duration_s: float, seed: int
) -> np.ndarray:
    """Band-passed noise burst with exponential decay; deterministic per seed.

    The extra high-pass pass at lo_hz is load-bearing: a 4th-order band-pass
    alone leaves enough sub-band residual that the kick detector's absolute
    0.01 envelope floor counts snare bursts as kicks (verified: without it,
    snare-only renders register 16 kick-band onsets; with it, zero).
    """
    rng = np.random.default_rng(seed)
    t = np.arange(int(SAMPLE_RATE * duration_s)) / SAMPLE_RATE
    noise = rng.standard_normal(t.size)
    b, a = butter(4, [lo_hz / (SAMPLE_RATE / 2), hi_hz / (SAMPLE_RATE / 2)], "band")
    noise = filtfilt(b, a, noise)
    b_hp, a_hp = butter(4, lo_hz / (SAMPLE_RATE / 2), "high")
    noise = filtfilt(b_hp, a_hp, noise) * np.exp(-t / decay_s)
    peak = float(np.max(np.abs(noise)))
    if peak > 1e-9:
        noise = noise / peak * 0.9
    return noise.astype(np.float32)


def _eng_snare(seed: int = 7) -> np.ndarray:
    return _eng_burst(lo_hz=300.0, hi_hz=1500.0, decay_s=0.08, duration_s=0.25, seed=seed)


def _eng_hat(seed: int = 11) -> np.ndarray:
    return _eng_burst(lo_hz=4000.0, hi_hz=10000.0, decay_s=0.04, duration_s=0.12, seed=seed)


# --- Pattern renderers -------------------------------------------------------- #


def _meter_beats_per_bar(meter: str) -> int:
    numerator, _slash, denominator = meter.partition("/")
    if denominator == "8" and numerator == "6":
        return 6
    return int(numerator or 4)


def _new_buffer(bpm: float, total_beats: int, tail_s: float = 0.7) -> np.ndarray:
    duration = total_beats * 60.0 / bpm + tail_s
    return np.zeros(int(round(duration * SAMPLE_RATE)), dtype=np.float32)


def _overlay(target: np.ndarray, source: np.ndarray, start_sec: float, gain: float) -> None:
    start = int(round(start_sec * SAMPLE_RATE))
    end = min(target.size, start + source.size)
    if start < target.size and end > start:
        target[start:end] += source[: end - start] * gain


def _peak_guard(samples: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak > 0.98:
        samples *= 0.98 / peak
    return samples


def render_grid_pattern(
    *,
    bpm: float,
    meter: str,
    bars: int,
    with_hats: bool = False,
    swing_percent: float = 50.0,
) -> RenderedClip:
    """Accented kick pulse for tempo/beat/downbeat/meter checks.

    Kick on every beat with the downbeat accented; nothing else unless
    with_hats. Off-beat onsets bin ambiguously in analyze_time_signature's
    ±half-beat onset counting and corrupt the bar-length autocorrelation
    (verified: hats on every "and" flip a straight 4/4 read to 6/8 or 3/4),
    so meter-checked clips carry the bare pulse. with_hats adds a realistic
    swung 8th-note hat pattern — a straight on-beat hat plus the delayed
    off-beat "and" hat — for the swing-truth clips, whose manifest checks BPM
    and swingPercent (the long/short 8th-interval ratio the swing measurement
    reads). Both hats are present because the measurement keys off the
    alternation of long and short intervals, not a single offbeat position.
    """
    beats_per_bar = _meter_beats_per_bar(meter)
    total_beats = bars * beats_per_bar
    beat_s = 60.0 / bpm
    buf = _new_buffer(bpm, total_beats)
    kick, hat = _eng_kick(), _eng_hat()

    hat_times: list[float] = []
    for beat in range(total_beats):
        accent = beat % beats_per_bar == 0
        _overlay(buf, kick, beat * beat_s, 1.0 if accent else 0.8)
        if with_hats:
            _overlay(buf, hat, beat * beat_s, 0.6)  # straight on-beat 8th
            and_sec = (beat + swing_percent / 100.0) * beat_s
            hat_times.append(round(and_sec, 6))
            _overlay(buf, hat, and_sec, 0.6)  # swung off-beat 8th

    truth = {
        "bpm": bpm,
        "bpmOctave": bpm,
        "timeSignature": meter,
        "beatGrid": [round(b * beat_s, 6) for b in range(total_beats)],
        "downbeats": [round(i * beats_per_bar * beat_s, 6) for i in range(bars)],
    }
    if with_hats:
        truth["swingPercent"] = swing_percent
        truth["hitTimes"] = {"hihat": hat_times}
    return RenderedClip(_peak_guard(buf), truth)


def render_broken_grid(
    *,
    bpm: float,
    bars: int,
    kick_offsets: tuple[float, ...],
    snare_offsets: tuple[float, ...],
) -> RenderedClip:
    """Broken-kick 4/4 pattern for the genre-generalization rhythm clips.

    kick_offsets/snare_offsets are 0-indexed beat positions within a 4/4 bar
    (e.g. 2-step: kick (0, 1.5), snare (1, 3)). Straight 8th-note hats ride on
    top so the beat tracker has pulse evidence at the notated tempo — that is
    what makes the halftime clip an honest tempo-octave trap rather than an
    ambiguous one (a real halftime arrangement carries its notated tempo in
    the hat grid). Truth checks are the same as grid clips: bpm, 4/4,
    beatGrid, downbeats.
    """
    beats_per_bar = 4
    total_beats = bars * beats_per_bar
    beat_s = 60.0 / bpm
    buf = _new_buffer(bpm, total_beats)
    kick, snare, hat = _eng_kick(), _eng_snare(), _eng_hat()

    for bar in range(bars):
        bar_start = bar * beats_per_bar
        for offset in kick_offsets:
            _overlay(buf, kick, (bar_start + offset) * beat_s, 1.0 if offset == 0.0 else 0.85)
        for offset in snare_offsets:
            _overlay(buf, snare, (bar_start + offset) * beat_s, 0.85)
    for eighth in range(total_beats * 2):
        _overlay(buf, hat, eighth * 0.5 * beat_s, 0.45)

    truth = {
        "bpm": bpm,
        "bpmOctave": bpm,
        "timeSignature": "4/4",
        "beatGrid": [round(b * beat_s, 6) for b in range(total_beats)],
        "downbeats": [round(i * beats_per_bar * beat_s, 6) for i in range(bars)],
        "hitTimes": {
            "kick": [round((bar * beats_per_bar + o) * beat_s, 6) for bar in range(bars) for o in kick_offsets],
            "snare": [round((bar * beats_per_bar + o) * beat_s, 6) for bar in range(bars) for o in snare_offsets],
        },
    }
    return RenderedClip(_peak_guard(buf), truth)


def render_shuffle16_pattern(*, bpm: float, bars: int, swing_percent: float) -> RenderedClip:
    """Four-on-the-floor kicks + 16th-note shuffled hats (UKG/2-step shuffle).

    The same long/short alternation as the 8th-grid swing clips, one metrical
    level down: each 8th-note span [x, x+0.5] carries its inner 16th delayed
    to x + (swing/100)*0.5 beats. The truth swingPercent is the 16th-grid
    ratio — what the swing measurement SHOULD report once it detects the
    dominant grid instead of hardwiring 8ths (accuracy program PR-G5).
    """
    total_beats = bars * 4
    beat_s = 60.0 / bpm
    buf = _new_buffer(bpm, total_beats)
    kick, hat = _eng_kick(), _eng_hat()

    hat_times: list[float] = []
    for beat in range(total_beats):
        _overlay(buf, kick, beat * beat_s, 1.0 if beat % 4 == 0 else 0.8)
        for eighth_offset in (0.0, 0.5):
            base = beat + eighth_offset
            _overlay(buf, hat, base * beat_s, 0.6)
            swung = base + swing_percent / 100.0 * 0.5
            hat_times.append(round(swung * beat_s, 6))
            _overlay(buf, hat, swung * beat_s, 0.6)

    truth = {
        "bpm": bpm,
        "swingPercent": swing_percent,
        "gridResolution": "16th",
        "hitTimes": {"hihat": hat_times},
    }
    return RenderedClip(_peak_guard(buf), truth)


def render_ambient_pad(key_root: str, mode: str, bpm: float) -> RenderedClip:
    """Sparse beatless pad — the abstention clip.

    Two slow triads, no percussion. Active checks assert the key is still
    right AND that the rhythm stack abstains: low tempo confidence, no
    swingDetail, meter on the assumed-4/4 fallback. The honesty block is
    check configuration (it rides in `expected`), not signal truth.
    """
    chords = render_chord_progression(key_root, mode, [1, 6], bpm, 16.0)
    truth = {
        "key": chords.truth["key"],
        "honesty": {
            "maxBpmConfidence": 0.4,
            "swingDetailAbsent": True,
            "meterSources": ["assumed_four_four"],
        },
        "chordTimeline": chords.truth["chordTimeline"],
    }
    return RenderedClip(chords.samples, truth)


def render_count_pattern(*, bpm: float, bars: int) -> RenderedClip:
    """Band-disjoint, never-coincident placement for percussion-count checks.

    Kicks on every beat, snares on odd beats' "and", hats on even beats' "and"
    — every onset is alone in both time and frequency, so each band detector
    counts exactly its own instrument (verified 32/16/16 at 8 bars, 128 BPM).
    """
    total_beats = bars * 4
    beat_s = 60.0 / bpm
    buf = _new_buffer(bpm, total_beats)
    kick, snare, hat = _eng_kick(), _eng_snare(), _eng_hat()

    snare_beats = [b + 0.5 for b in range(total_beats) if b % 2 == 1]
    hat_beats = [b + 0.5 for b in range(total_beats) if b % 2 == 0]
    for beat in range(total_beats):
        _overlay(buf, kick, beat * beat_s, 1.0 if beat % 4 == 0 else 0.8)
    for pos in snare_beats:
        _overlay(buf, snare, pos * beat_s, 0.8)
    for pos in hat_beats:
        _overlay(buf, hat, pos * beat_s, 0.8)

    truth = {
        "bpm": bpm,
        "timeSignature": "4/4",
        "percussion": {
            "kickCount": total_beats,
            "snareCount": len(snare_beats),
            "hihatCount": len(hat_beats),
        },
        "hitTimes": {
            "kick": [round(b * beat_s, 6) for b in range(total_beats)],
            "snare": [round(p * beat_s, 6) for p in snare_beats],
            "hihat": [round(p * beat_s, 6) for p in hat_beats],
        },
    }
    return RenderedClip(_peak_guard(buf), truth)


def _label_for_degree(root_pc: int, mode: str, degree: int) -> str:
    """Flat-spelled triad label computed from pitch classes (Viterbi vocab)."""
    root, third, _fifth = _diatonic_triad_midi(root_pc, mode, degree, base_octave=4)
    quality_minor = (third - root) % 12 == 3
    return _PC_NAMES_FLAT[root % 12] + ("m" if quality_minor else "")


def render_chord_progression(
    key_root: str,
    mode: str,
    degrees: list[int],
    bpm: float,
    beats_per_chord: float,
) -> RenderedClip:
    ctx = build_context(key=f"{key_root} {mode}", bpm=bpm)
    if mode not in _SCALE_INTERVALS:
        raise ValueError(f"unsupported mode: {mode}")
    notes: list[NoteEvent] = []
    for index, degree in enumerate(degrees):
        for pitch in _diatonic_triad_midi(ctx.root_pc, ctx.mode, degree, base_octave=4):
            notes.append(
                NoteEvent(
                    pitch_midi=pitch,
                    start_beat=index * beats_per_chord,
                    duration_beats=beats_per_chord,
                    velocity=88,
                )
            )
    plan = ClipPlan(
        tempo_bpm=bpm,
        duration_beats=len(degrees) * beats_per_chord,
        notes=notes,
        program=0,
    )
    rendered = render_clip(plan, allow_soundfont_backends=False)
    beat_s = 60.0 / bpm
    timeline = [
        {
            "startSec": round(index * beats_per_chord * beat_s, 6),
            "endSec": round((index + 1) * beats_per_chord * beat_s, 6),
            "label": _label_for_degree(ctx.root_pc, ctx.mode, degree),
        }
        for index, degree in enumerate(degrees)
    ]
    return RenderedClip(
        rendered.samples,
        {"bpm": bpm, "key": f"{key_root} {mode}", "chordTimeline": timeline},
    )


def render_bass_line(bpm: float) -> RenderedClip:
    notes = [
        NoteEvent(48, 0.0, 1.0),
        NoteEvent(51, 1.0, 1.0),
        NoteEvent(55, 2.0, 1.0),
    ]
    plan = ClipPlan(tempo_bpm=bpm, duration_beats=3.0, notes=notes, program=38)
    rendered = render_clip(plan, allow_soundfont_backends=False)
    beat_s = 60.0 / bpm
    return RenderedClip(
        rendered.samples,
        {
            "transcriptionNotes": [
                {"pitchMidi": n.pitch_midi, "onsetSeconds": round(n.start_beat * beat_s, 6), "durationSeconds": round(n.duration_beats * beat_s, 6)}
                for n in notes
            ]
        },
    )


def render_multi_layer(key_root: str, mode: str, bpm: float) -> RenderedClip:
    degrees = [1, 6, 4 if mode == "major" else 7, 5]
    chords = render_chord_progression(key_root, mode, degrees, bpm, 4.0)
    ctx = build_context(key=f"{key_root} {mode}", bpm=bpm)
    bass = render_clip(plan_bass_root(ctx, bars=4), allow_soundfont_backends=False).samples
    drums = render_grid_pattern(bpm=bpm, meter="4/4", bars=4)
    n = max(chords.samples.size, bass.size, drums.samples.size)
    mix = np.zeros(n, dtype=np.float32)
    mix[: chords.samples.size] += chords.samples * 0.55
    mix[: bass.size] += bass * 0.28
    mix[: drums.samples.size] += drums.samples * 0.45
    truth = {**chords.truth, "timeSignature": "4/4"}
    return RenderedClip(_peak_guard(mix), truth)


# --- Corpus specs -------------------------------------------------------------- #


def _default_specs() -> list[dict[str, Any]]:
    """The 4 clips backing the committed default manifest (asa verify path)."""
    return [
        {"id": "four_on_floor_clear_128", "kind": "grid", "bpm": 128, "meter": "4/4", "bars": 8},
        {"id": "tonal_minor_static_chords", "kind": "chords", "root": "A", "mode": "minor", "bpm": 120, "degrees": [1, 6], "beats_per_chord": 8},
        {"id": "drum_stem_known_counts", "kind": "counts", "bpm": 128, "bars": 8},
        {"id": "mono_bass_transcription", "kind": "bass", "bpm": 120},
    ]


# Broken-kick bar patterns (0-indexed beat offsets in a 4/4 bar). Sources:
# classic 2-step (kick 1 + "and" of 2, backbeat snares), halftime (kick 1 /
# snare 3 — the tempo-octave trap), and a breakbeat-style syncopation with
# an anticipated second kick and the "and" of 3.
_BROKEN_PATTERNS: dict[str, dict[str, tuple[float, ...]]] = {
    "twostep": {"kick": (0.0, 1.5), "snare": (1.0, 3.0)},
    "halftime": {"kick": (0.0,), "snare": (2.0,)},
    "breakbeat": {"kick": (0.0, 1.75, 2.5), "snare": (1.0, 3.0)},
}


def _synthetic_specs() -> list[dict[str, Any]]:
    specs = list(_default_specs())
    for bpm, meter in [(70, "4/4"), (85, "4/4"), (90, "3/4"), (110, "6/8"), (128, "4/4"), (140, "7/8"), (150, "4/4"), (174, "4/4"), (190, "4/4")]:
        specs.append({"id": f"grid_{meter.replace('/', '_')}_{bpm}", "kind": "grid", "bpm": bpm, "meter": meter, "bars": 8})
    roots = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    for i, root in enumerate(roots):
        mode = "major" if i % 2 == 0 else "minor"
        degrees = [1, 6, 4, 5] if mode == "major" else [1, 6, 7, 5]
        specs.append({"id": f"chords_{root.replace('#', 'sharp').replace('b', 'flat')}_{mode}", "kind": "chords", "root": root, "mode": mode, "bpm": 96 + i * 4, "degrees": degrees, "beats_per_chord": 4})
    for swing in [50, 54, 58, 62, 66]:
        specs.append({"id": f"swing_hats_{swing}", "kind": "swing", "bpm": 124, "bars": 8, "swing": swing})
    for root, mode, bpm in [("A", "minor", 128), ("F", "major", 122)]:
        specs.append({"id": f"multi_{root}_{mode}", "kind": "multi", "root": root, "mode": mode, "bpm": bpm})
    specs.append({"id": "twostep_132", "kind": "twostep", "bpm": 132, "bars": 8})
    for bpm in (140, 174):
        specs.append({"id": f"halftime_{bpm}", "kind": "halftime", "bpm": bpm, "bars": 8})
    specs.append({"id": "breakbeat_136", "kind": "breakbeat", "bpm": 136, "bars": 8})
    specs.append({"id": "shuffle16_130_62", "kind": "shuffle16", "bpm": 130, "bars": 8, "swing": 62})
    specs.append({"id": "ambient_beatless_70", "kind": "ambient", "root": "A", "mode": "minor", "bpm": 70})
    return specs


def _render_spec(spec: dict[str, Any]) -> RenderedClip:
    kind = spec["kind"]
    if kind == "grid":
        return render_grid_pattern(bpm=float(spec["bpm"]), meter=spec.get("meter", "4/4"), bars=int(spec.get("bars", 8)))
    if kind == "counts":
        return render_count_pattern(bpm=float(spec["bpm"]), bars=int(spec.get("bars", 8)))
    if kind == "swing":
        return render_grid_pattern(bpm=float(spec["bpm"]), meter="4/4", bars=int(spec.get("bars", 8)), with_hats=True, swing_percent=float(spec["swing"]))
    if kind in _BROKEN_PATTERNS:
        pattern = _BROKEN_PATTERNS[kind]
        return render_broken_grid(
            bpm=float(spec["bpm"]),
            bars=int(spec.get("bars", 8)),
            kick_offsets=pattern["kick"],
            snare_offsets=pattern["snare"],
        )
    if kind == "shuffle16":
        return render_shuffle16_pattern(bpm=float(spec["bpm"]), bars=int(spec.get("bars", 8)), swing_percent=float(spec["swing"]))
    if kind == "ambient":
        return render_ambient_pad(spec["root"], spec["mode"], float(spec["bpm"]))
    if kind == "chords":
        return render_chord_progression(spec["root"], spec["mode"], list(spec["degrees"]), float(spec["bpm"]), float(spec["beats_per_chord"]))
    if kind == "multi":
        return render_multi_layer(spec["root"], spec["mode"], float(spec["bpm"]))
    if kind == "bass":
        return render_bass_line(float(spec["bpm"]))
    raise ValueError(f"unknown spec kind: {kind}")


# --- Manifest emission --------------------------------------------------------- #

# Checks a clip kind activates. Everything else in the rendered truth is stored
# under the manifest entry's "truth" key (inert for the harness) so later PRs —
# e.g. the swing measurement — can promote it to an active check deliberately.
_EXPECTED_KEYS_BY_KIND: dict[str, tuple[str, ...]] = {
    "grid": ("bpm", "bpmOctave", "timeSignature", "beatGrid", "downbeats"),
    "counts": ("bpm", "percussion"),
    # Swing clips: their swung "and" hats corrupt the meter autocorrelation,
    # so meter/beat checks stay off; BPM and swingPercent are the active checks.
    "swing": ("bpm", "swingPercent"),
    "chords": ("key", "chordTimeline"),
    "multi": ("key", "chordTimeline", "timeSignature"),
    "bass": ("transcriptionNotes",),
    # Genre-generalization clips (accuracy program PR-G2): broken-kick
    # patterns share the grid checks; shuffle16 shares the swing checks
    # (its swung 16ths corrupt the meter autocorrelation the same way);
    # ambient is key + abstention-honesty only. bpmOctave (PR-G3) gates the
    # surfacing-only bpmOctaveEvidence field on every rhythm-kind clip.
    "twostep": ("bpm", "bpmOctave", "timeSignature", "beatGrid", "downbeats"),
    "halftime": ("bpm", "bpmOctave", "timeSignature", "beatGrid", "downbeats"),
    "breakbeat": ("bpm", "bpmOctave", "timeSignature", "beatGrid", "downbeats"),
    "shuffle16": ("bpm", "swingPercent"),
    "ambient": ("key", "honesty"),
}

_THRESHOLDS_BY_KIND: dict[str, dict[str, Any]] = {
    "grid": {"bpmTolerance": 1.0, "beatF1": 0.9, "downbeatF1": 0.75, "octaveTolerance": 2.0},
    "counts": {"bpmTolerance": 1.0, "percussionCountTolerance": 1},
    "swing": {"bpmTolerance": 1.0, "swingTolerance": 3.0},
    "chords": {"chordSegmentAccuracy": 0.65},
    "multi": {"chordSegmentAccuracy": 0.45, "allowRelativeMajorMinor": True},
    "bass": {"transcriptionNoteF1": 0.75},
    "twostep": {"bpmTolerance": 1.0, "beatF1": 0.9, "downbeatF1": 0.75, "octaveTolerance": 2.0},
    "halftime": {"bpmTolerance": 1.0, "beatF1": 0.9, "downbeatF1": 0.75, "octaveTolerance": 2.0},
    "breakbeat": {"bpmTolerance": 1.0, "beatF1": 0.9, "downbeatF1": 0.75, "octaveTolerance": 2.0},
    "shuffle16": {"bpmTolerance": 1.0, "swingTolerance": 3.0},
    "ambient": {},
}

# Measured baseline weaknesses (calibrated 2026-07-03 by running the full
# eval): these checks still run and report scores but do not gate the summary.
# They are the accuracy program's improvement targets — remove entries as
# upgrades land. Only checks that actually fail at baseline belong here; the
# rest of each clip's checks gate normally.
_KNOWN_GAPS_BY_ID: dict[str, list[str]] = {
    # analyze_time_signature's 20%-margin conservatism reads every odd meter
    # as 4/4, and the bar-1 phase depends on the meter, so downbeats follow.
    "grid_3_4_90": ["meter:timeSignature", "downbeats:f1"],
    "grid_6_8_110": ["meter:timeSignature", "downbeats:f1"],
    # 7/8 additionally confuses the tempo estimate (142.6 vs 140). The
    # octave-evidence check also stays informational here: the shipped bpm
    # is smeared (a meter artifact, PR-G4's problem), not octave-wrong, so
    # no simple ratio of 142.6 can land on 140.
    "grid_7_8_140": ["meter:timeSignature", "downbeats:f1", "tempo:bpm", "tempoOctave:preferredBpm"],
    # RhythmExtractor halves 174 BPM to 86.9 (octave preference); the beat
    # grid and downbeats still score >= 0.87 against truth.
    "grid_4_4_174": ["tempo:bpm"],
    # Genre-generalization baseline (calibrated 2026-07-13; PR-G3/PR-G5 own
    # these). At 190 the octave halving worsens: unlike 174 (where the beat
    # grid survived), the halved grid drags beatGrid to 0.625 and downbeats
    # to 0.667.
    "grid_4_4_190": ["tempo:bpm", "beatGrid:f1", "downbeats:f1"],
    # Halftime at 174 (kick 1 / snare 3, 8th hats) reads 117.0 — a 2:3
    # ratio error, not a clean octave — and the grid follows it down
    # (beatGrid 0.370, downbeats 0.308). The same arrangement at 140 passes
    # every check, so the trap is specifically tempo-extreme halftime.
    "halftime_174": ["tempo:bpm", "beatGrid:f1", "downbeats:f1"],
    # 16th-grid shuffle is invisible to the swing measurement (swingDetail
    # None): compute_swing_detail keeps only 8th-scale IOIs (0.30-0.70
    # beats) and hardwires gridResolution "8th". PR-G5 target.
    "shuffle16_130_62": ["swing:swingPercent"],
}


def _manifest_track(spec: dict[str, Any], rendered: RenderedClip, *, synthetic_subdir: bool) -> dict[str, Any]:
    kind = spec["kind"]
    audio_name = f"{spec['id']}.wav"
    active_keys = _EXPECTED_KEYS_BY_KIND[kind]
    expected = {key: rendered.truth[key] for key in active_keys if key in rendered.truth}
    truth_extras = {key: value for key, value in rendered.truth.items() if key not in expected}
    track: dict[str, Any] = {
        "id": spec["id"],
        "audioPath": f"synthetic/{audio_name}" if synthetic_subdir else audio_name,
        "category": kind,
        "description": "Deterministic NumPy-rendered synthetic fundamentals fixture.",
        "expected": expected,
        "thresholds": dict(_THRESHOLDS_BY_KIND[kind]),
    }
    if truth_extras:
        track["truth"] = truth_extras
    if kind == "multi":
        track["analyzeFlags"] = ["--separate"]
    if kind == "bass":
        track["analyzeFlags"] = ["--transcribe"]
    known_gaps = _KNOWN_GAPS_BY_ID.get(spec["id"])
    if known_gaps:
        track["knownGaps"] = list(known_gaps)
    return track


def emit_manifest(manifest_path: Path, tracks: list[dict[str, Any]]) -> None:
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "targetProfile": TARGET_PROFILE,
        "gates": {"clearTempoWithinBpm": 1.0, "beatF1": 0.9, "downbeatF1": 0.75, "chordSegmentAccuracy": 0.65},
        "tracks": tracks,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def build_corpus(
    out_dir: Path,
    manifest_path: Path,
    *,
    check: bool = False,
    write_manifest: bool = True,
) -> dict[str, Any]:
    synthetic_manifest = manifest_path.name.endswith(".synthetic.json")
    specs = _synthetic_specs() if synthetic_manifest else _default_specs()
    audio_root = out_dir / "synthetic" if synthetic_manifest else out_dir
    tracks: list[dict[str, Any]] = []
    fingerprints: dict[str, bytes] = {}
    for spec in specs:
        rendered = _render_spec(spec)
        path = audio_root / f"{spec['id']}.wav"
        write_wav(rendered.samples, path=path, sample_rate=SAMPLE_RATE)
        fingerprints[spec["id"]] = rendered.samples.tobytes()
        tracks.append(_manifest_track(spec, rendered, synthetic_subdir=synthetic_manifest))
    if write_manifest:
        emit_manifest(manifest_path, tracks)
    if check:
        for spec in specs:
            second = _render_spec(spec)
            if second.samples.tobytes() != fingerprints[spec["id"]]:
                raise SystemExit(f"non-deterministic render for {spec['id']}")
    return {
        "tracks": len(tracks),
        "manifest": str(manifest_path) if write_manifest else None,
        "outDir": str(out_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ASA's deterministic synthetic fundamentals corpus.")
    parser.add_argument("--out-dir", type=Path, default=BACKEND_DIR / "tests" / "fixtures" / "fundamentals_tracks")
    parser.add_argument("--manifest", type=Path, default=BACKEND_DIR / "tests" / "fixtures" / "fundamentals_eval_manifest.synthetic.json")
    parser.add_argument("--check", action="store_true", help="Double-render every clip and fail if bytes differ.")
    parser.add_argument(
        "--audio-only",
        action="store_true",
        help="Render WAV files without rewriting the committed manifest.",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            build_corpus(
                args.out_dir,
                args.manifest,
                check=args.check,
                write_manifest=not args.audio_only,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

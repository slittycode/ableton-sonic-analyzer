"""MIDI plan → WAV rendering for audition samples.

Three render backends, picked in this order under the default ``auto`` policy:

1. **symusic Synthesizer** (Prestosynth + SF2/SF3 soundfont) — fastest of the
   soundfont options; the same MIDI library used everywhere else on the
   backend.
2. **FluidSynth** (``pyfluidsynth`` + soundfont) — kept as a fallback because
   it's the historically-shipped path and remains the reference rendering for
   users with a tuned `SONIC_ANALYZER_SOUNDFONT`.
3. **Sine-additive fallback** — pure NumPy. Always available; in-tune; raw.

All three produce the same float32 mono 44.1 kHz numpy array, so callers
don't need to branch on which backend ran. The selected backend is recorded
on ``RenderResult.backend`` so it can flow into the citation manifest
(samples cite which synth rendered them, preserving chain-of-custody on the
audition surface).

The ``ASA_SAMPLE_SYNTH_BACKEND`` env var (values: ``auto``, ``symusic``,
``fluidsynth``, ``sine``) overrides the default precedence. ``auto`` is the
shipping default. Pinning an explicit backend is the escape hatch if a
regression surfaces in the wild — flip back to ``fluidsynth`` without a code
change.

MIDI artifacts are emitted via ``symusic`` (fast C++ core), so the user can
drop a ``.mid`` into Ableton even if the audio render is rough. The MIDI file
is a spec-conformant artifact that DAWs read as a fixed format — switching
writers is a non-audible change, but the test in
``tests/test_sample_synthesis.WriteMidiTests`` round-trips via ``pretty_midi``
to keep the parity contract honest.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf
from symusic import Note, Score, Synthesizer, Tempo, Track

from sample_theory import ClipPlan

logger = logging.getLogger(__name__)

SAMPLE_RATE = 44_100

# --- FluidSynth probe ------------------------------------------------------- #

try:  # pragma: no cover - import probe
    import fluidsynth  # type: ignore[import-untyped]

    _FLUIDSYNTH_IMPORTABLE = True
except Exception as exc:  # pragma: no cover - exercised when pyfluidsynth absent
    fluidsynth = None
    _FLUIDSYNTH_IMPORTABLE = False
    logger.info("pyfluidsynth not importable (%s); skipping FluidSynth path.", exc)


_DEFAULT_SOUNDFONT_CANDIDATES: tuple[Path, ...] = (
    Path(__file__).parent / "assets" / "soundfonts" / "default.sf2",
    Path("/usr/share/sounds/sf2/FluidR3_GM.sf2"),
    Path("/usr/share/sounds/sf2/default-GM.sf2"),
    Path("/usr/share/sounds/sf3/default-GM.sf3"),
    Path("/opt/homebrew/share/fluid-synth/sf2/FluidR3_GM.sf2"),
)


Backend = Literal["symusic", "fluidsynth", "sine_fallback"]

_BACKEND_ENV_VAR = "ASA_SAMPLE_SYNTH_BACKEND"
_VALID_BACKEND_OVERRIDES = {"auto", "symusic", "fluidsynth", "sine"}


@dataclass(frozen=True)
class RenderResult:
    samples: np.ndarray  # float32 mono, range ~[-1, 1]
    sample_rate: int
    backend: Backend
    soundfont_path: str | None
    duration_seconds: float


def locate_soundfont(explicit: Path | str | None = None) -> Path | None:
    """Resolve a soundfont path from explicit input → env var → known locations."""
    if explicit is not None:
        path = Path(explicit)
        return path if path.is_file() else None
    env_path = os.environ.get("SONIC_ANALYZER_SOUNDFONT")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    for candidate in _DEFAULT_SOUNDFONT_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def _read_backend_override() -> str:
    raw = os.environ.get(_BACKEND_ENV_VAR, "auto").strip().lower()
    if raw not in _VALID_BACKEND_OVERRIDES:
        logger.warning(
            "Ignoring unknown %s=%r; valid values: %s.",
            _BACKEND_ENV_VAR,
            raw,
            sorted(_VALID_BACKEND_OVERRIDES),
        )
        return "auto"
    return raw


def _resolve_backend(
    *,
    soundfont_path: Path | None,
    allow_soundfont_backends: bool,
) -> Backend:
    """Pick the backend the next render should use.

    ``allow_soundfont_backends=False`` is the test escape hatch — same role
    that ``prefer_fluidsynth=False`` played pre-PR-F: force the deterministic
    sine path regardless of what's installed. The env var still wins when
    set, so an operator can explicitly pin a backend.
    """
    override = _read_backend_override()
    if override == "sine" or not allow_soundfont_backends:
        return "sine_fallback"

    if override == "symusic":
        return "symusic" if soundfont_path is not None else "sine_fallback"
    if override == "fluidsynth":
        if _FLUIDSYNTH_IMPORTABLE and soundfont_path is not None:
            return "fluidsynth"
        return "sine_fallback"

    # ``auto`` — symusic > fluidsynth > sine, gated on a soundfont being
    # locatable. Symusic outranks FluidSynth because it's the same MIDI
    # library used elsewhere on the backend; FluidSynth stays available as
    # the documented fallback for operators who tuned their setup against it.
    if soundfont_path is None:
        return "sine_fallback"
    return "symusic"


def render_clip(
    plan: ClipPlan,
    *,
    soundfont: Path | str | None = None,
    prefer_fluidsynth: bool = True,
) -> RenderResult:
    """Render a ClipPlan to an in-memory float32 audio buffer.

    Picks the best available backend using :func:`_resolve_backend`. The
    ``prefer_fluidsynth`` kwarg is historical — its actual semantics are
    "allow soundfont-based backends." Pass ``False`` to force the sine path
    (tests do this to keep coverage deterministic).
    """
    sf_path = locate_soundfont(soundfont)
    backend = _resolve_backend(
        soundfont_path=sf_path,
        allow_soundfont_backends=prefer_fluidsynth,
    )

    if backend == "symusic" and sf_path is not None:
        try:
            return _render_with_symusic_synth(plan, sf_path)
        except Exception as exc:  # pragma: no cover - hard to trigger in CI
            logger.warning(
                "symusic render failed (%s); falling back to FluidSynth or sine.",
                exc,
            )
            if _FLUIDSYNTH_IMPORTABLE:
                try:
                    return _render_with_fluidsynth(plan, sf_path)
                except Exception as inner_exc:  # pragma: no cover
                    logger.warning(
                        "FluidSynth fallback also failed (%s); using sine.",
                        inner_exc,
                    )

    if backend == "fluidsynth" and sf_path is not None and _FLUIDSYNTH_IMPORTABLE:
        try:
            return _render_with_fluidsynth(plan, sf_path)
        except Exception as exc:  # pragma: no cover - hard to trigger in CI
            logger.warning(
                "FluidSynth render failed (%s); falling back to sine synth.", exc
            )

    return _render_with_sine_fallback(plan)


def write_wav(samples: np.ndarray, *, path: Path, sample_rate: int = SAMPLE_RATE) -> None:
    """Write float32 samples to a 16-bit PCM WAV at the conventional bit depth."""
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0).astype(np.float32)
    sf.write(str(path), clipped, sample_rate, subtype="PCM_16")


def write_midi(plan: ClipPlan, *, path: Path) -> None:
    """Emit a MIDI file from a ClipPlan so users can audition in Ableton.

    Uses ``symusic`` (C++ core) so the backend has a single canonical MIDI
    library; the output is a spec-conformant Standard MIDI file that any DAW
    parses identically. Tempo is emitted at ``t=0`` to match the static plan,
    and the GM program is set on the track header so Ableton picks the right
    default sound.
    """
    score = Score(480, ttype="Second")
    score.tempos.append(Tempo(time=0.0, qpm=float(plan.tempo_bpm), ttype="Second"))
    track = Track(
        name="audition", program=int(plan.program), is_drum=False, ttype="Second"
    )
    beats_per_second = plan.tempo_bpm / 60.0
    for note in plan.notes:
        start_seconds = note.start_beat / beats_per_second
        duration_seconds = max(0.0, note.duration_beats / beats_per_second)
        track.notes.append(
            Note(
                time=float(start_seconds),
                duration=float(duration_seconds),
                pitch=int(np.clip(note.pitch_midi, 0, 127)),
                velocity=int(np.clip(note.velocity, 1, 127)),
                ttype="Second",
            )
        )
    score.tracks.append(track)
    path.parent.mkdir(parents=True, exist_ok=True)
    score.dump_midi(str(path))


# --- symusic Synthesizer path ---------------------------------------------- #


def _build_score_from_plan(plan: ClipPlan) -> Score:
    """Build a Second-unit Score from a ClipPlan.

    Shared by the symusic synth and ``write_midi`` to keep the plan-to-Score
    translation in one place; future plan extensions only need updating here.
    """
    score = Score(480, ttype="Second")
    score.tempos.append(Tempo(time=0.0, qpm=float(plan.tempo_bpm), ttype="Second"))
    track = Track(
        name="audition", program=int(plan.program), is_drum=False, ttype="Second"
    )
    beats_per_second = plan.tempo_bpm / 60.0
    for note in plan.notes:
        start_seconds = note.start_beat / beats_per_second
        duration_seconds = max(0.0, note.duration_beats / beats_per_second)
        track.notes.append(
            Note(
                time=float(start_seconds),
                duration=float(duration_seconds),
                pitch=int(np.clip(note.pitch_midi, 0, 127)),
                velocity=int(np.clip(note.velocity, 1, 127)),
                ttype="Second",
            )
        )
    score.tracks.append(track)
    return score


def _render_with_symusic_synth(
    plan: ClipPlan, soundfont_path: Path
) -> RenderResult:  # pragma: no cover - exercised only when a real SF2/SF3 is available locally
    """Render a ClipPlan via symusic.Synthesizer (Prestosynth backend).

    Returns the same float32 mono 44.1 kHz buffer shape as the other paths so
    the caller doesn't have to branch.
    """
    score = _build_score_from_plan(plan)
    synth = Synthesizer(str(soundfont_path), sample_rate=SAMPLE_RATE, quality=0)
    audio = synth.render(score, stereo=False)
    samples = np.asarray(audio, dtype=np.float32)

    # Symusic returns 1D mono when stereo=False, but be defensive in case a
    # future version changes the shape — we always reduce to a 1D float32.
    if samples.ndim == 2:
        # Average across the non-time axis. With 2 channels in either layout,
        # the shorter axis is the channel axis.
        channel_axis = 0 if samples.shape[0] <= samples.shape[1] else 1
        samples = samples.mean(axis=channel_axis).astype(np.float32)
    elif samples.ndim != 1:
        raise RuntimeError(
            f"symusic.Synthesizer.render returned unexpected shape {samples.shape}"
        )

    seconds_total = (plan.duration_beats / plan.tempo_bpm) * 60.0
    return RenderResult(
        samples=samples,
        sample_rate=SAMPLE_RATE,
        backend="symusic",
        soundfont_path=str(soundfont_path),
        duration_seconds=seconds_total,
    )


# --- FluidSynth path -------------------------------------------------------- #


def _render_with_fluidsynth(plan: ClipPlan, soundfont_path: Path) -> RenderResult:  # pragma: no cover - exercised only when FluidSynth + a soundfont are available locally
    """Offline-render a ClipPlan via pyfluidsynth.

    We bypass an audio driver entirely (`driver=None`) and use `get_samples()`
    to pull rendered audio out in fixed-size blocks. That keeps the call site
    headless-server-safe.
    """
    if fluidsynth is None:
        raise RuntimeError("pyfluidsynth missing despite probe passing")

    seconds_total = (plan.duration_beats / plan.tempo_bpm) * 60.0
    total_samples = int(round(SAMPLE_RATE * seconds_total))

    synth = fluidsynth.Synth(samplerate=float(SAMPLE_RATE))
    sfid = synth.sfload(str(soundfont_path))
    # Channel 0, bank 0, preset = clip's GM program.
    synth.program_select(0, sfid, 0, plan.program)

    # Build an event timeline: each note becomes a noteon and a noteoff at the
    # right sample index. Sorted so we can iterate forward.
    beats_per_second = plan.tempo_bpm / 60.0
    events: list[tuple[int, str, int, int]] = []
    for note in plan.notes:
        on_sample = int(round(note.start_beat / beats_per_second * SAMPLE_RATE))
        off_sample = int(
            round(
                (note.start_beat + note.duration_beats) / beats_per_second * SAMPLE_RATE
            )
        )
        events.append((on_sample, "on", note.pitch_midi, int(note.velocity)))
        events.append((off_sample, "off", note.pitch_midi, 0))
    events.sort(key=lambda e: (e[0], 0 if e[1] == "off" else 1))

    block = 1024
    buffer = np.zeros(total_samples, dtype=np.float32)
    event_idx = 0
    cursor = 0
    while cursor < total_samples:
        while event_idx < len(events) and events[event_idx][0] <= cursor:
            _, kind, pitch, velocity = events[event_idx]
            if kind == "on":
                synth.noteon(0, pitch, velocity)
            else:
                synth.noteoff(0, pitch)
            event_idx += 1
        chunk_size = min(block, total_samples - cursor)
        # get_samples returns interleaved stereo int16. Mix to mono float32.
        raw = synth.get_samples(chunk_size)
        stereo = np.asarray(raw, dtype=np.int16).reshape(-1, 2)
        mono = stereo.mean(axis=1).astype(np.float32) / 32768.0
        buffer[cursor : cursor + chunk_size] = mono[:chunk_size]
        cursor += chunk_size

    synth.delete()
    return RenderResult(
        samples=buffer,
        sample_rate=SAMPLE_RATE,
        backend="fluidsynth",
        soundfont_path=str(soundfont_path),
        duration_seconds=seconds_total,
    )


# --- Sine fallback ---------------------------------------------------------- #


def _render_with_sine_fallback(plan: ClipPlan) -> RenderResult:
    """Sine-additive synth with a simple ADSR envelope.

    Three harmonics (1f, 2f, 3f) with decreasing amplitude give a slightly
    less plain sound than a pure sine, without straying into territory we'd
    have to defend musically.
    """
    seconds_total = (plan.duration_beats / plan.tempo_bpm) * 60.0
    total_samples = int(round(SAMPLE_RATE * seconds_total))
    buffer = np.zeros(total_samples, dtype=np.float64)

    beats_per_second = plan.tempo_bpm / 60.0
    for note in plan.notes:
        start_sample = int(round(note.start_beat / beats_per_second * SAMPLE_RATE))
        note_samples = int(
            round(note.duration_beats / beats_per_second * SAMPLE_RATE)
        )
        if note_samples <= 0:
            continue
        end_sample = min(start_sample + note_samples, total_samples)
        if start_sample >= total_samples:
            continue

        actual_samples = end_sample - start_sample
        t = np.arange(actual_samples, dtype=np.float64) / SAMPLE_RATE
        freq = 440.0 * (2.0 ** ((note.pitch_midi - 69) / 12.0))

        voice = (
            np.sin(2.0 * np.pi * freq * t) * 0.6
            + np.sin(2.0 * np.pi * (2.0 * freq) * t) * 0.25
            + np.sin(2.0 * np.pi * (3.0 * freq) * t) * 0.12
        )
        envelope = _adsr_envelope(actual_samples, sample_rate=SAMPLE_RATE)
        velocity_scale = note.velocity / 127.0
        buffer[start_sample:end_sample] += voice * envelope * velocity_scale

    # Soft normalization to leave headroom.
    peak = float(np.max(np.abs(buffer))) if buffer.size else 0.0
    if peak > 1e-9:
        buffer *= 0.8 / peak

    return RenderResult(
        samples=buffer.astype(np.float32),
        sample_rate=SAMPLE_RATE,
        backend="sine_fallback",
        soundfont_path=None,
        duration_seconds=seconds_total,
    )


def _adsr_envelope(
    num_samples: int,
    *,
    sample_rate: int,
    attack_s: float = 0.01,
    decay_s: float = 0.04,
    sustain_level: float = 0.7,
    release_s: float = 0.12,
) -> np.ndarray:
    """Standard 4-stage envelope. Length matches the note; trims if too short."""
    env = np.ones(num_samples, dtype=np.float64) * sustain_level

    attack_samples = min(int(attack_s * sample_rate), num_samples)
    if attack_samples > 0:
        env[:attack_samples] = np.linspace(0.0, 1.0, attack_samples, dtype=np.float64)

    decay_start = attack_samples
    decay_samples = min(int(decay_s * sample_rate), num_samples - decay_start)
    if decay_samples > 0:
        env[decay_start : decay_start + decay_samples] = np.linspace(
            1.0, sustain_level, decay_samples, dtype=np.float64
        )

    release_samples = min(int(release_s * sample_rate), num_samples)
    if release_samples > 0:
        env[-release_samples:] *= np.linspace(
            1.0, 0.0, release_samples, dtype=np.float64
        )
    return env


def fluidsynth_available() -> bool:
    """True iff both the python binding and a soundfont file are reachable."""
    if not _FLUIDSYNTH_IMPORTABLE:
        return False
    return locate_soundfont() is not None


def symusic_synth_available() -> bool:
    """True iff a soundfont file is reachable (symusic itself is a hard dep)."""
    return locate_soundfont() is not None

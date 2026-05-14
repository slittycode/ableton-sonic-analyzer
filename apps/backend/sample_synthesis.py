"""MIDI plan → WAV rendering for audition samples.

Two render paths:

1. **FluidSynth** (`pyfluidsynth` + a General MIDI soundfont) — high-quality.
   Used when both the Python binding and a soundfont file are available.
2. **Sine-additive fallback** — pure NumPy. Always available; in-tune; raw.

Both paths produce the same float32 mono 44.1 kHz numpy array, so callers
don't need to branch on which backend was selected. The selected backend is
recorded on `RenderResult.backend` so it can flow into the manifest.

MIDI artifacts are emitted via `pretty_midi`, which is already a hard dep, so
the user can drop a `.mid` into Ableton even if the audio render is rough.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pretty_midi  # type: ignore[import-untyped]
import soundfile as sf

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
    logger.info("pyfluidsynth not importable (%s); using sine fallback.", exc)


_DEFAULT_SOUNDFONT_CANDIDATES: tuple[Path, ...] = (
    Path(__file__).parent / "assets" / "soundfonts" / "default.sf2",
    Path("/usr/share/sounds/sf2/FluidR3_GM.sf2"),
    Path("/usr/share/sounds/sf2/default-GM.sf2"),
    Path("/usr/share/sounds/sf3/default-GM.sf3"),
    Path("/opt/homebrew/share/fluid-synth/sf2/FluidR3_GM.sf2"),
)


Backend = Literal["fluidsynth", "sine_fallback"]


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


def render_clip(
    plan: ClipPlan,
    *,
    soundfont: Path | str | None = None,
    prefer_fluidsynth: bool = True,
) -> RenderResult:
    """Render a ClipPlan to an in-memory float32 audio buffer.

    Picks the best available backend. Caller can force the fallback by passing
    `prefer_fluidsynth=False`; tests use that to exercise the fallback path
    even when FluidSynth happens to be installed.
    """
    if prefer_fluidsynth and _FLUIDSYNTH_IMPORTABLE:
        sf_path = locate_soundfont(soundfont)
        if sf_path is not None:
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
    """Emit a MIDI file from a ClipPlan so users can audition in Ableton."""
    pm = pretty_midi.PrettyMIDI(initial_tempo=plan.tempo_bpm)
    inst = pretty_midi.Instrument(program=plan.program)
    beats_per_second = plan.tempo_bpm / 60.0
    for note in plan.notes:
        start_seconds = note.start_beat / beats_per_second
        end_seconds = (note.start_beat + note.duration_beats) / beats_per_second
        inst.notes.append(
            pretty_midi.Note(
                velocity=int(np.clip(note.velocity, 1, 127)),
                pitch=int(np.clip(note.pitch_midi, 0, 127)),
                start=float(start_seconds),
                end=float(end_seconds),
            )
        )
    pm.instruments.append(inst)
    path.parent.mkdir(parents=True, exist_ok=True)
    pm.write(str(path))


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

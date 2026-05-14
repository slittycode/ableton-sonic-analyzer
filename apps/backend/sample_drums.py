"""NumPy-based drum one-shot synthesis for audition samples.

Phase 1 measures the kick's fundamental and decay (`kickDetail.fundamentalHz`,
`kickDetail.decayTimeMs`). We turn those into a sub-sine + transient click.
Snare and hi-hat are not directly measured — we render plausible defaults and
the manifest is explicit that those are heuristic, not measurement-grounded.

PyTheory is not involved here; drums are not harmonic. Synthesis lives outside
the music-theory layer.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


SAMPLE_RATE = 44_100
_RNG = np.random.default_rng(seed=42)  # deterministic noise so tests are stable


@dataclass(frozen=True)
class DrumOneShot:
    samples: np.ndarray  # float32, mono, range [-1, 1]
    sample_rate: int
    duration_seconds: float
    label: str


def synth_kick(
    *,
    fundamental_hz: float = 55.0,
    decay_time_ms: float = 250.0,
    click_amount: float = 0.35,
    duration_seconds: float = 0.6,
) -> DrumOneShot:
    """Synthesize a kick: pitch-modulated sub-sine plus transient click.

    The pitch starts an octave above `fundamental_hz` and exponentially decays
    to the fundamental over the first 30 ms. This mimics the body-and-thump
    shape of an electronic kick well enough for an audition.

    `decay_time_ms` controls how long the body sustains. Phase 1 typically
    measures values in the 150–400 ms range for electronic kicks.
    """
    if fundamental_hz <= 0:
        raise ValueError(f"fundamental_hz must be positive; got {fundamental_hz}")
    if duration_seconds <= 0:
        raise ValueError(f"duration_seconds must be positive; got {duration_seconds}")

    num_samples = int(round(SAMPLE_RATE * duration_seconds))
    t = np.arange(num_samples, dtype=np.float64) / SAMPLE_RATE

    # Pitch envelope: octave drop over the first 30 ms.
    pitch_decay_s = 0.030
    pitch_env = np.exp(-t / pitch_decay_s) * fundamental_hz + fundamental_hz
    phase = 2.0 * np.pi * np.cumsum(pitch_env) / SAMPLE_RATE
    body = np.sin(phase)

    # Amplitude envelope: exponential decay with measured time constant.
    decay_s = max(decay_time_ms, 50.0) / 1000.0
    amp_env = np.exp(-t / (decay_s * 0.4))  # slightly tighter than reported decay
    body *= amp_env

    # Click: short high-frequency burst with its own fast envelope.
    click_env = np.exp(-t / 0.004)  # 4 ms decay
    click_noise = _RNG.standard_normal(num_samples).astype(np.float64)
    click = click_noise * click_env * click_amount

    samples = body * 0.85 + click
    samples = _normalize(samples)

    return DrumOneShot(
        samples=samples.astype(np.float32),
        sample_rate=SAMPLE_RATE,
        duration_seconds=duration_seconds,
        label=f"Kick at {fundamental_hz:.0f} Hz",
    )


def synth_snare(
    *,
    body_hz: float = 200.0,
    duration_seconds: float = 0.4,
) -> DrumOneShot:
    """Snare: tone body + noise crack. Heuristic only — no Phase 1 ground truth."""
    num_samples = int(round(SAMPLE_RATE * duration_seconds))
    t = np.arange(num_samples, dtype=np.float64) / SAMPLE_RATE

    body_env = np.exp(-t / 0.08)
    body = np.sin(2.0 * np.pi * body_hz * t) * body_env

    noise_env = np.exp(-t / 0.12)
    noise = _RNG.standard_normal(num_samples) * noise_env

    # Simple high-shelf: take the running difference to emphasize highs.
    noise_hp = np.empty_like(noise)
    noise_hp[0] = noise[0]
    noise_hp[1:] = noise[1:] - 0.97 * noise[:-1]

    samples = body * 0.4 + noise_hp * 0.85
    samples = _normalize(samples)
    return DrumOneShot(
        samples=samples.astype(np.float32),
        sample_rate=SAMPLE_RATE,
        duration_seconds=duration_seconds,
        label="Snare (heuristic)",
    )


def synth_hat(*, duration_seconds: float = 0.18) -> DrumOneShot:
    """Closed hi-hat: short filtered noise. Heuristic — no Phase 1 ground truth."""
    num_samples = int(round(SAMPLE_RATE * duration_seconds))
    t = np.arange(num_samples, dtype=np.float64) / SAMPLE_RATE

    env = np.exp(-t / 0.035)
    noise = _RNG.standard_normal(num_samples)

    # Two-tap high-pass (same idea as snare): emphasize >5 kHz content.
    hp = np.empty_like(noise)
    hp[0] = noise[0]
    hp[1] = noise[1] - 0.98 * noise[0]
    for i in range(2, num_samples):
        hp[i] = noise[i] - 1.96 * noise[i - 1] + 0.97 * noise[i - 2]

    samples = hp * env
    samples = _normalize(samples) * 0.7
    return DrumOneShot(
        samples=samples.astype(np.float32),
        sample_rate=SAMPLE_RATE,
        duration_seconds=duration_seconds,
        label="Closed hat (heuristic)",
    )


def _normalize(samples: np.ndarray, *, headroom_db: float = 1.5) -> np.ndarray:
    """Peak-normalize to leave a small headroom margin."""
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak <= 1e-9:
        return samples
    target = 10 ** (-headroom_db / 20.0)
    return samples * (target / peak)

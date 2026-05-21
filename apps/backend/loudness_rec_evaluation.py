"""Offline reachability evaluation for prescriptive loudness/dynamics advice.

EVAL / TEST ONLY. This module renders and re-measures audio to verify that the
*deterministic subset* of a loudness recommendation — gain-to-target-LUFS and a
true-peak ceiling — is physically reachable. It MUST NOT be imported by
``analyze.py`` or ``server.py``: ASA recommends Ableton devices, it does not
process audio on the product path. The gain/limiter helpers below exist purely
so the evaluation can use ASA's own Essentia measurements as the oracle.

Unit note: Phase 1 ``truePeak`` is a LINEAR amplitude proxy (see
``JSON_SCHEMA.md`` — "linear amplitude proxy (rounded)"), NOT dBTP. ``1.0`` is
0 dBFS full scale; ``> 1.0`` is an inter-sample over. The constant below mirrors
``apps/ui/src/services/loudnessGuardrails.ts`` (``TRUE_PEAK_OVER_LINEAR``) — keep
the two in sync.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

# Linear amplitude above which truePeak is an inter-sample over (0 dBFS).
# Mirror of TRUE_PEAK_OVER_LINEAR in apps/ui/src/services/loudnessGuardrails.ts.
TRUE_PEAK_OVER_LINEAR = 1.0


def db_to_linear(db: float) -> float:
    return float(10.0 ** (float(db) / 20.0))


def linear_to_db(linear: float) -> float:
    if linear <= 0:
        return float("-inf")
    return float(20.0 * math.log10(float(linear)))


def gain_db_to_target(current_lufs: float, target_lufs: float) -> float:
    """Gain (dB) to move integrated loudness from current to target.

    LUFS is gain-linear: applying ``G`` dB of broadband gain raises integrated
    loudness by ~``G`` dB for the same content, so the required gain is simply
    ``target - current``.
    """
    return float(target_lufs) - float(current_lufs)


def apply_gain(stereo: np.ndarray, gain_db: float) -> np.ndarray:
    return (stereo.astype(np.float64) * db_to_linear(gain_db)).astype(np.float32)


def projected_true_peak_linear(current_peak_linear: float, gain_db: float) -> float:
    return float(current_peak_linear) * db_to_linear(gain_db)


def scale_to_true_peak_ceiling(
    stereo: np.ndarray, measured_true_peak: float, ceiling_linear: float
) -> np.ndarray:
    """Linearly scale a buffer down so its true peak sits at the ceiling.

    A deliberately minimal "limiter": linear scaling removes overs without
    introducing the clipping harmonics a hard clip would, so the re-measured true
    peak lands exactly at the ceiling. It also reduces overall loudness — which is
    precisely the target-vs-ceiling tension that :func:`analytic_reachability`
    quantifies (a real peak limiter would recover most of that loudness).
    """
    if measured_true_peak <= ceiling_linear or measured_true_peak <= 0:
        return stereo.astype(np.float32)
    return (
        stereo.astype(np.float64) * (float(ceiling_linear) / float(measured_true_peak))
    ).astype(np.float32)


@dataclass
class ReachabilityResult:
    target_lufs: float
    ceiling_linear: float
    gain_db: float
    projected_peak_linear: float
    pure_gain_reaches_target: bool
    limiting_required_db: float
    final_lufs_estimate: float
    contradictory: bool
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


def analytic_reachability(
    current_lufs: float,
    current_peak_linear: float,
    target_lufs: float,
    ceiling_linear: float,
) -> ReachabilityResult:
    """Without rendering: can gain + ceiling jointly hit target and kill overs?

    - ``g = target - current``
    - ``projected_peak = current_peak * 10^(g/20)``
    - if ``projected_peak <= ceiling``: pure gain reaches the target exactly, no
      limiting needed.
    - else: holding the ceiling by linear scaling costs ``limiting_required_db``
      of loudness, so pure gain+scale lands at ``target - limiting_required_db``;
      a real peak limiter would recover most of it. This is *not* contradictory —
      it just means a limiter (not bare gain) is required.

    A recommendation is flagged ``contradictory`` only when it is physically
    nonsensical: a ceiling above full scale (which would permit overs), a
    non-positive ceiling, or a non-finite target.
    """
    g = gain_db_to_target(current_lufs, target_lufs)
    projected = projected_true_peak_linear(current_peak_linear, g)
    pure_ok = projected <= ceiling_linear + 1e-9
    if pure_ok:
        limiting_db = 0.0
        final = float(target_lufs)
        note = "pure gain reaches target with headroom under ceiling"
    else:
        limiting_db = linear_to_db(projected / ceiling_linear)
        final = float(target_lufs) - limiting_db
        note = "needs a peak limiter to hold target while killing overs"
    contradictory = (
        not math.isfinite(float(target_lufs))
        or ceiling_linear > TRUE_PEAK_OVER_LINEAR + 1e-9
        or ceiling_linear <= 0
    )
    return ReachabilityResult(
        target_lufs=float(target_lufs),
        ceiling_linear=float(ceiling_linear),
        gain_db=g,
        projected_peak_linear=projected,
        pure_gain_reaches_target=pure_ok,
        limiting_required_db=limiting_db,
        final_lufs_estimate=final,
        contradictory=contradictory,
        note=note,
    )


def evaluate_recommendation_reachability(
    measured_lufs: float,
    measured_true_peak_linear: float,
    target_lufs: float,
    ceiling_dbfs: float,
) -> ReachabilityResult:
    """Convenience wrapper: recommendations express the ceiling in dBFS."""
    return analytic_reachability(
        current_lufs=measured_lufs,
        current_peak_linear=measured_true_peak_linear,
        target_lufs=target_lufs,
        ceiling_linear=db_to_linear(ceiling_dbfs),
    )


# ---- Synthetic signal helpers (numpy only) -----------------------------------


def synth_stereo_sine(
    peak_linear: float,
    duration_s: float = 4.0,
    sample_rate: int = 44_100,
    freq_hz: float = 1_000.0,
) -> np.ndarray:
    """Dual-mono sine at a given linear peak amplitude. Shape ``(N, 2)`` float32.

    Matches the shape ``analyze_loudness`` / ``analyze_true_peak`` expect (see
    ``tests/test_loudness_r128.py``).
    """
    n_samples = int(round(duration_s * sample_rate))
    t = np.arange(n_samples, dtype=np.float64) / float(sample_rate)
    mono = float(peak_linear) * np.sin(2.0 * math.pi * freq_hz * t)
    return np.stack([mono, mono], axis=-1).astype(np.float32)


# ---- Essentia oracle (lazy import; eval-only) --------------------------------


def measure_loudness_true_peak(
    stereo: np.ndarray, sample_rate: int = 44_100
) -> tuple[float | None, float | None]:
    """Re-measure ``(lufs_integrated, true_peak_linear)`` with ASA's analyzers.

    ``analyze_core`` is imported lazily so the pure-math helpers above stay usable
    in environments without Essentia. Raises ``ImportError`` if Essentia is
    unavailable — callers (driver / tests) guard for that.
    """
    import analyze_core  # eval-only lazy import; never import at module top

    loudness = analyze_core.analyze_loudness(stereo, sample_rate=sample_rate)
    true_peak = analyze_core.analyze_true_peak(stereo)
    return loudness.get("lufsIntegrated"), true_peak.get("truePeak")

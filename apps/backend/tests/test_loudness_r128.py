"""EBU R128 verification spike for ASA's loudness path.

Track 1 of the external-repo incorporation plan (docs/external-repo-review-2026-05-13.md)
asked: is ASA's integrated-LUFS implementation correct, or does it lag the BS.1770-5
revision? This module answers that with the EBU Tech 3341 compliance signals — the
canonical loudness conformance test set.

What we test:

1. Tech 3341 Case 1 — stereo 1 kHz sine at -23.0 dB FS for 20 s.
   Expected integrated loudness: -23.0 ±0.1 LUFS.

2. Tech 3341 Case 2 — stereo 1 kHz sine at -33.0 dB FS for 20 s.
   Expected integrated loudness: -33.0 ±0.1 LUFS.

The ±0.1 LU tolerance is the EBU R128 compliance gate for "EBU Mode" loudness
meters. If both cases pass on ASA's actual call path (`analyze_loudness` →
Essentia's `LoudnessEBUR128`), the review's premise check is positive: no
algorithm rewrite needed.

Both tests run at 44.1 kHz because that is the sample rate ASA's full pipeline
uses for the LUFS call (`analyze_core.py:197` calls `LoudnessEBUR128()` with no
explicit `sampleRate`, defaulting to 44100). A third test calls Essentia
directly at 48 kHz with the sample rate threaded through, demonstrating that
the algorithm itself is correct at non-44.1 rates when given the right input —
which is the case `analyze_fast.py:100` already handles. The gap between
`analyze_core` and `analyze_fast` on sample-rate threading is logged as a
follow-up finding from this spike (not fixed here — out of scope for a
verification-only spike).

All synthetic signals are generated procedurally; no test fixtures are
downloaded or committed.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


try:
    import essentia.standard as es  # noqa: F401
    from analyze_core import analyze_loudness
    ESSENTIA_AVAILABLE = True
except Exception:  # pragma: no cover - guarded by skip
    ESSENTIA_AVAILABLE = False
    es = None  # type: ignore[assignment]
    analyze_loudness = None  # type: ignore[assignment]


# EBU R128 compliance tolerance for integrated loudness, "EBU Mode" meters.
LUFS_TOLERANCE = 0.1


def _make_stereo_sine(
    peak_dbfs: float,
    duration_s: float,
    sample_rate: int,
    freq_hz: float = 1000.0,
) -> np.ndarray:
    """Generate a stereo sine tone at a given peak dB FS.

    Returns shape ``(N, 2)`` float32 to match what Essentia's ``AudioLoader``
    returns (i.e. what ``analyze_loudness`` expects). The two channels carry
    the same signal — the EBU Tech 3341 cases 1 and 2 are defined as
    identical L/R, which sums to +3 dB stereo per BS.1770 channel weighting
    (mono mono per channel, summed before K-weighting integration).
    """
    n_samples = int(round(duration_s * sample_rate))
    t = np.arange(n_samples, dtype=np.float64) / float(sample_rate)
    peak_amplitude = 10.0 ** (peak_dbfs / 20.0)
    mono = peak_amplitude * np.sin(2.0 * math.pi * freq_hz * t)
    stereo = np.stack([mono, mono], axis=-1).astype(np.float32)
    return stereo


@unittest.skipUnless(ESSENTIA_AVAILABLE, "Essentia not available in test env")
class TestLoudnessR128Tech3341(unittest.TestCase):
    """EBU R128 Tech 3341 compliance probes at ASA's operating sample rate."""

    SAMPLE_RATE_HZ = 44_100
    DURATION_S = 20.0

    def test_case1_minus23_dbfs_sine_yields_minus23_lufs(self) -> None:
        """Case 1: -23.0 dB FS stereo 1 kHz sine → -23.0 ±0.1 LUFS integrated."""
        stereo = _make_stereo_sine(
            peak_dbfs=-23.0,
            duration_s=self.DURATION_S,
            sample_rate=self.SAMPLE_RATE_HZ,
        )

        result = analyze_loudness(stereo)
        integrated = result.get("lufsIntegrated")

        self.assertIsNotNone(
            integrated,
            "analyze_loudness returned None for lufsIntegrated on a clean sine",
        )
        self.assertAlmostEqual(
            integrated,
            -23.0,
            delta=LUFS_TOLERANCE,
            msg=(
                f"EBU Tech 3341 case 1: expected -23.0 ±{LUFS_TOLERANCE} LUFS, "
                f"got {integrated} LUFS. Either ASA's loudness path drifted, "
                f"the K-weighting filter is mis-tuned, or Essentia's "
                f"LoudnessEBUR128 default at 44.1 kHz disagrees with R128."
            ),
        )

    def test_case2_minus33_dbfs_sine_yields_minus33_lufs(self) -> None:
        """Case 2: -33.0 dB FS stereo 1 kHz sine → -33.0 ±0.1 LUFS integrated."""
        stereo = _make_stereo_sine(
            peak_dbfs=-33.0,
            duration_s=self.DURATION_S,
            sample_rate=self.SAMPLE_RATE_HZ,
        )

        result = analyze_loudness(stereo)
        integrated = result.get("lufsIntegrated")

        self.assertIsNotNone(integrated)
        self.assertAlmostEqual(
            integrated,
            -33.0,
            delta=LUFS_TOLERANCE,
            msg=(
                f"EBU Tech 3341 case 2: expected -33.0 ±{LUFS_TOLERANCE} LUFS, "
                f"got {integrated} LUFS. A pass on case 1 but a fail here would "
                f"point at a non-linearity in the integration path."
            ),
        )


@unittest.skipUnless(ESSENTIA_AVAILABLE, "Essentia not available in test env")
class TestLoudnessR128AtNon441kHz(unittest.TestCase):
    """Verifies the BS.1770 algorithm itself is correct at 48 kHz.

    This test bypasses ``analyze_loudness`` and calls Essentia's
    ``LoudnessEBUR128(sampleRate=48000)`` directly. Its purpose is to
    establish that Essentia is sample-rate aware — so any LUFS error
    observed on 48 kHz sources via ``analyze_loudness`` is a *call-site
    bug* (sample rate not threaded), not an algorithm bug.

    This is the open finding from the spike documented in
    docs/external-repo-review-2026-05-13.md (Track 1 follow-up): the
    full pipeline calls ``analyze_loudness(stereo)`` after
    ``load_stereo`` returns audio at the source's native rate, so any
    48 kHz source today gets measured against 44.1 kHz K-weighting.
    """

    SAMPLE_RATE_HZ = 48_000
    DURATION_S = 20.0

    def test_case1_at_48khz_with_explicit_sample_rate(self) -> None:
        """At 48 kHz, Essentia must produce -23.0 ±0.1 LUFS for case 1
        when given the correct sample rate.
        """
        stereo = _make_stereo_sine(
            peak_dbfs=-23.0,
            duration_s=self.DURATION_S,
            sample_rate=self.SAMPLE_RATE_HZ,
        )

        loudness = es.LoudnessEBUR128(sampleRate=self.SAMPLE_RATE_HZ)
        _momentary, _short_term, integrated, _lra = loudness(stereo)

        self.assertAlmostEqual(
            float(integrated),
            -23.0,
            delta=LUFS_TOLERANCE,
            msg=(
                f"Essentia LoudnessEBUR128 at 48 kHz with explicit sampleRate "
                f"must match -23.0 ±{LUFS_TOLERANCE} LUFS. Got {integrated}. "
                f"If this fails, the algorithm itself is suspect at non-44.1 "
                f"rates and the call-site fix would not help."
            ),
        )


if __name__ == "__main__":
    unittest.main()

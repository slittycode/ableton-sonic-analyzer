"""EBU R128 verification + regression gate for ASA's loudness path.

Track 1 of the external-repo incorporation plan (docs/history/external-repo-review-2026-05-13.md)
asked: is ASA's integrated-LUFS implementation correct, or does it lag the BS.1770-5
revision? This module answers that with the EBU Tech 3341 compliance signals — the
canonical loudness conformance test set — and now also gates the sample-rate
threading fix that closed the spike's open finding.

What we test:

1. Tech 3341 Case 1 — stereo 1 kHz sine at -23.0 dB FS for 20 s @ 44.1 kHz.
   Expected integrated loudness: -23.0 ±0.1 LUFS via ``analyze_loudness``.

2. Tech 3341 Case 2 — stereo 1 kHz sine at -33.0 dB FS for 20 s @ 44.1 kHz.
   Expected integrated loudness: -33.0 ±0.1 LUFS via ``analyze_loudness``.

3. Case 1 at 48 kHz against Essentia directly — proves the BS.1770 algorithm
   is correct at non-44.1 rates when the sample rate is threaded through.

4. Case 1 at 48 kHz via ``analyze_loudness(stereo, sample_rate=48000)`` —
   end-to-end regression gate for the fix that closed the open finding from
   the original spike (``analyze_core.analyze_loudness`` now takes
   ``sample_rate`` and threads it to ``LoudnessEBUR128(sampleRate=…)``).

5. Parameter-wiring tests (``TestAnalyzeLoudnessThreadsSampleRateToEssentia``)
   that patch ``analyze_core.es.LoudnessEBUR128`` and assert
   ``sampleRate=<the value passed>`` reaches Essentia. These cover the gap
   the 1 kHz tolerance tests cannot: at 1 kHz the K-weighting bias between
   44.1 kHz and 48 kHz coefficient sets is under 0.05 LU and the function
   rounds to one decimal, so a silently-swallowed parameter would still
   pass a tolerance assertion. The mock-based assertions catch that.

The ±0.1 LU tolerance is the EBU R128 compliance gate for "EBU Mode" loudness
meters.

All synthetic signals are generated procedurally; no test fixtures are
downloaded or committed.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


try:
    import essentia.standard as es  # noqa: F401
    import analyze_core
    from analyze_core import analyze_loudness, analyze_plr, analyze_true_peak
    ESSENTIA_AVAILABLE = True
except Exception:  # pragma: no cover - guarded by skip
    ESSENTIA_AVAILABLE = False
    es = None  # type: ignore[assignment]
    analyze_core = None  # type: ignore[assignment]
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

    Originally the open finding from the verification spike documented
    in docs/history/external-repo-review-2026-05-13.md (Track 1 follow-up). The
    follow-up fix lives in this branch's companion edits to
    ``analyze_core.analyze_loudness`` (now takes ``sample_rate``) and
    its call sites in ``analyze.py``; the regression test below
    (``TestLoudnessR128ThroughAnalyzeLoudnessAt48kHz``) is the
    end-to-end gate for that fix.
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


@unittest.skipUnless(ESSENTIA_AVAILABLE, "Essentia not available in test env")
class TestLoudnessR128ThroughAnalyzeLoudnessAt48kHz(unittest.TestCase):
    """End-to-end gate for the sample-rate threading fix.

    Before the fix, ``analyze_loudness(stereo)`` instantiated
    ``LoudnessEBUR128()`` with no ``sampleRate`` argument (defaulting
    to 44100), so a 48 kHz stereo array got measured against K-weighting
    coefficients tuned for 44.1 kHz. The bias is small at 1 kHz but
    non-zero, and grows with frequency.

    After the fix, ``analyze_loudness(stereo, sample_rate=48000)`` must
    produce the same -23.0 ±0.1 LUFS that the direct-Essentia probe
    above produces. A failure here is a regression on the fix.
    """

    SAMPLE_RATE_HZ = 48_000
    DURATION_S = 20.0

    def test_case1_through_analyze_loudness_at_48khz(self) -> None:
        """At 48 kHz, analyze_loudness must produce -23.0 ±0.1 LUFS
        when the caller threads the sample rate through.
        """
        stereo = _make_stereo_sine(
            peak_dbfs=-23.0,
            duration_s=self.DURATION_S,
            sample_rate=self.SAMPLE_RATE_HZ,
        )

        result = analyze_loudness(stereo, sample_rate=self.SAMPLE_RATE_HZ)
        integrated = result.get("lufsIntegrated")

        self.assertIsNotNone(integrated)
        self.assertAlmostEqual(
            integrated,
            -23.0,
            delta=LUFS_TOLERANCE,
            msg=(
                f"analyze_loudness at 48 kHz: expected -23.0 ±{LUFS_TOLERANCE} "
                f"LUFS, got {integrated}. If this fails, either the "
                f"sample_rate parameter is not being threaded to Essentia "
                f"or the K-weighting filter is mis-tuned."
            ),
        )


@unittest.skipUnless(ESSENTIA_AVAILABLE, "Essentia not available in test env")
class TestAnalyzeLoudnessThreadsSampleRateToEssentia(unittest.TestCase):
    """White-box: ``analyze_loudness`` must construct ``LoudnessEBUR128``
    with ``sampleRate=<the value the caller passed>``.

    The tolerance-based tests above (1 kHz Tech 3341 cases) cannot prove
    this on their own. At 1 kHz the K-weighting bias between 44.1 kHz and
    48 kHz coefficient sets is well under 0.05 LU, and ``analyze_loudness``
    rounds the integrated value to one decimal — so a silently-swallowed
    ``sample_rate`` parameter would still pass the 1 kHz compliance tests.

    These tests assert the parameter wiring directly by patching
    ``analyze_core.es.LoudnessEBUR128`` and inspecting the kwargs passed
    to it. Mock-based and white-box, by design.
    """

    @staticmethod
    def _make_fake_loudness_class() -> mock.MagicMock:
        """Build a stand-in for ``es.LoudnessEBUR128``.

        Calling ``LoudnessEBUR128(sampleRate=X)`` returns an *instance*;
        the instance is then called with the stereo array and returns
        ``(momentary_array, short_term_array, integrated_scalar,
        loudness_range_scalar)``. The mock matches that shape so
        ``analyze_loudness`` can complete without raising.
        """
        fake_class = mock.MagicMock(name="LoudnessEBUR128_class")
        fake_instance = mock.MagicMock(name="LoudnessEBUR128_instance")
        fake_instance.return_value = (
            np.zeros(10, dtype=np.float64),
            np.zeros(10, dtype=np.float64),
            -23.0,
            5.0,
        )
        fake_class.return_value = fake_instance
        return fake_class

    def test_explicit_sample_rate_is_passed_to_LoudnessEBUR128(self) -> None:
        stereo = _make_stereo_sine(
            peak_dbfs=-23.0, duration_s=1.0, sample_rate=48_000
        )

        fake_class = self._make_fake_loudness_class()
        with mock.patch.object(
            analyze_core.es, "LoudnessEBUR128", new=fake_class
        ):
            analyze_loudness(stereo, sample_rate=48_000)

        fake_class.assert_called_once_with(sampleRate=48_000)

    def test_default_sample_rate_is_44100(self) -> None:
        stereo = _make_stereo_sine(
            peak_dbfs=-23.0, duration_s=1.0, sample_rate=44_100
        )

        fake_class = self._make_fake_loudness_class()
        with mock.patch.object(
            analyze_core.es, "LoudnessEBUR128", new=fake_class
        ):
            analyze_loudness(stereo)  # no sample_rate kwarg

        fake_class.assert_called_once_with(sampleRate=44_100)

    def test_unusual_sample_rate_is_passed_verbatim(self) -> None:
        """Guards against a future change that might clamp or normalize the
        sample_rate argument. Whatever the caller passes must reach Essentia.
        """
        stereo = _make_stereo_sine(
            peak_dbfs=-23.0, duration_s=1.0, sample_rate=96_000
        )

        fake_class = self._make_fake_loudness_class()
        with mock.patch.object(
            analyze_core.es, "LoudnessEBUR128", new=fake_class
        ):
            analyze_loudness(stereo, sample_rate=96_000)

        fake_class.assert_called_once_with(sampleRate=96_000)


@unittest.skipUnless(ESSENTIA_AVAILABLE, "Essentia not available in test env")
class TestAnalyzePlrIsDbtpMinusLufs(unittest.TestCase):
    """``analyze_plr`` is a direct dB-domain subtraction: truePeak(dBTP) - LUFS.

    Phase 1 schema v2 emits ``truePeak`` in dBTP, so PLR needs no log conversion.
    Regression gate for the prior unit-mismatch bug where PLR mixed a linear
    amplitude with a dB value. The golden fixture only covers one signal, so
    these pure-function cases lock the contract (including negative dBTP, which
    real masters always have).
    """

    def test_full_scale_peak_plr_equals_negative_lufs(self) -> None:
        # 0.0 dBTP (full scale) → PLR == -lufsIntegrated.
        self.assertAlmostEqual(analyze_plr(-8.9, 0.0)["plr"], 8.9, places=2)

    def test_negative_dbtp_peak(self) -> None:
        # A mastered track at -1.2 dBTP, -9.0 LUFS → PLR 7.8 LU. (A positivity
        # guard would have wrongly nulled this — most masters are negative dBTP.)
        self.assertAlmostEqual(analyze_plr(-9.0, -1.2)["plr"], 7.8, places=2)

    def test_inter_sample_over_positive_dbtp(self) -> None:
        # +0.6 dBTP over, -7.0 LUFS → PLR 7.6 LU.
        self.assertAlmostEqual(analyze_plr(-7.0, 0.6)["plr"], 7.6, places=2)

    def test_missing_or_non_finite_inputs_return_none(self) -> None:
        self.assertIsNone(analyze_plr(None, 0.0)["plr"])
        self.assertIsNone(analyze_plr(-8.0, None)["plr"])
        self.assertIsNone(analyze_plr(float("nan"), 0.0)["plr"])
        self.assertIsNone(analyze_plr(-8.0, float("inf"))["plr"])


@unittest.skipUnless(ESSENTIA_AVAILABLE, "Essentia not available in test env")
class TestAnalyzeTruePeakEmitsDbtp(unittest.TestCase):
    """``analyze_true_peak`` emits dBTP (Phase 1 schema v2). A linear peak above
    1.0 must surface as a *positive* dBTP (an inter-sample over), full scale as
    0.0 dBTP, and silence as None.

    White-box: patches ``TruePeakDetector`` to return a known linear peak so the
    dBTP conversion is asserted independent of Essentia's oversampler.
    """

    def _true_peak_dbtp_for_linear(self, linear: float) -> float | None:
        stereo = _make_stereo_sine(
            peak_dbfs=0.0, duration_s=0.1, sample_rate=44_100
        )
        fake_class = mock.MagicMock(name="TruePeakDetector_class")
        fake_instance = mock.MagicMock(name="TruePeakDetector_instance")
        fake_instance.return_value = (
            np.zeros(8, dtype=np.float32),
            np.array([linear], dtype=np.float32),
        )
        fake_class.return_value = fake_instance
        with mock.patch.object(
            analyze_core.es, "TruePeakDetector", new=fake_class
        ):
            return analyze_true_peak(stereo)["truePeak"]

    def test_inter_sample_over_is_positive_dbtp(self) -> None:
        # linear 1.032 → 20*log10(1.032) == +0.27 dBTP (an over).
        result = self._true_peak_dbtp_for_linear(1.032)
        self.assertAlmostEqual(result, 0.3, places=1)
        self.assertGreater(result, 0.0, "an inter-sample over must read > 0 dBTP")

    def test_full_scale_is_zero_dbtp(self) -> None:
        self.assertAlmostEqual(self._true_peak_dbtp_for_linear(1.0), 0.0, places=1)

    def test_minus_one_dbtp(self) -> None:
        # linear 0.8913 → -1.0 dBTP (the conventional master ceiling).
        self.assertAlmostEqual(self._true_peak_dbtp_for_linear(0.8913), -1.0, places=1)

    def test_silence_returns_none(self) -> None:
        self.assertIsNone(self._true_peak_dbtp_for_linear(0.0))


if __name__ == "__main__":
    unittest.main()

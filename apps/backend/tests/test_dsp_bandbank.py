"""Frequency-response tests for ``BatchedBandpass``.

``BatchedBandpassTests`` in ``test_dsp_utils.py`` locks bit-identicality with
the pre-refactor inline scipy code (so a refactor cannot drift). This file
locks the **behavioral** contract: a sine inside the band passes through near
unity, a sine outside the band is attenuated. If scipy ever changed the
Butterworth filter implementation in a way that broke the actual frequency
response, the bit-identicality test would still pass (since it compares
against the same scipy code) — these tests would catch it.

This is complementary, not duplicative, with ``test_dsp_utils.py``.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


_BANDBANK_PATH = _BACKEND_ROOT / "dsp_bandbank.py"
_BANDBANK_SPEC = importlib.util.spec_from_file_location("dsp_bandbank_resp", _BANDBANK_PATH)
if _BANDBANK_SPEC is None or _BANDBANK_SPEC.loader is None:
    raise AssertionError("Could not load dsp_bandbank.py")
dsp_bandbank = importlib.util.module_from_spec(_BANDBANK_SPEC)
_BANDBANK_SPEC.loader.exec_module(dsp_bandbank)


def _sine(freq_hz: float, sample_rate: int, duration_s: float, amplitude: float = 1.0) -> np.ndarray:
    """Pure tone — used to probe the filter's frequency response."""
    t = np.arange(int(sample_rate * duration_s), dtype=np.float64) / sample_rate
    return amplitude * np.sin(2 * np.pi * freq_hz * t)


def _rms(signal: np.ndarray) -> float:
    return float(np.sqrt(np.mean(signal.astype(np.float64) ** 2)))


def _db(ratio: float) -> float:
    """Power-ratio → dB, with a floor to keep ``-inf`` out of the log."""
    return 20.0 * np.log10(max(ratio, 1e-12))


class PassBandTests(unittest.TestCase):
    """A sine at the band center must pass through near unity gain.

    Tolerance is 1 dB — the 4th-order Butterworth has a flat response in the
    passband but the filtfilt double-pass narrows the effective bandwidth
    slightly; ±1 dB is comfortable for a center-of-band tone.
    """

    @classmethod
    def setUpClass(cls):
        cls.sr = 44100
        cls.duration_s = 2.0

    def _assert_passes(self, band_lo: float, band_hi: float, probe_hz: float):
        """Filter a sine inside the band; expect output RMS ≈ input RMS."""
        bb = dsp_bandbank.BatchedBandpass(self.sr)
        sine = _sine(probe_hz, self.sr, self.duration_s)
        filtered = bb.filter_one(sine, band_lo, band_hi, dtype=np.float64)
        self.assertIsNotNone(filtered)
        # Trim edges to avoid filtfilt edge transients tainting the RMS.
        edge = self.sr // 10
        gain_db = _db(_rms(filtered[edge:-edge]) / _rms(sine[edge:-edge]))
        self.assertGreater(
            gain_db, -1.0,
            f"Pass-band gain {gain_db:.2f} dB at {probe_hz} Hz in [{band_lo}, {band_hi}] Hz",
        )
        self.assertLess(gain_db, 1.0)

    def test_low_band_passes_60_hz(self):
        self._assert_passes(band_lo=20.0, band_hi=250.0, probe_hz=60.0)

    def test_low_mids_band_passes_500_hz(self):
        self._assert_passes(band_lo=250.0, band_hi=2000.0, probe_hz=500.0)

    def test_high_mids_band_passes_4khz(self):
        self._assert_passes(band_lo=2000.0, band_hi=8000.0, probe_hz=4000.0)

    def test_highs_band_passes_10khz(self):
        self._assert_passes(band_lo=8000.0, band_hi=16000.0, probe_hz=10000.0)


class StopBandTests(unittest.TestCase):
    """A sine well outside the band must be attenuated by ≥40 dB.

    The 4th-order Butterworth rolls off at 24 dB/oct per pass; filtfilt's
    double-pass doubles the effective order to 8th, ≈48 dB/oct. A probe one
    octave outside the band edge should clear 40 dB easily.
    """

    @classmethod
    def setUpClass(cls):
        cls.sr = 44100
        cls.duration_s = 2.0

    def _assert_rejects(
        self, band_lo: float, band_hi: float, probe_hz: float, min_attenuation_db: float = 40.0,
    ):
        bb = dsp_bandbank.BatchedBandpass(self.sr)
        sine = _sine(probe_hz, self.sr, self.duration_s)
        filtered = bb.filter_one(sine, band_lo, band_hi, dtype=np.float64)
        self.assertIsNotNone(filtered)
        edge = self.sr // 10
        gain_db = _db(_rms(filtered[edge:-edge]) / _rms(sine[edge:-edge]))
        self.assertLess(
            gain_db, -min_attenuation_db,
            f"Stop-band gain {gain_db:.2f} dB at {probe_hz} Hz in [{band_lo}, {band_hi}] Hz "
            f"(expected < {-min_attenuation_db} dB)",
        )

    def test_sub_bass_signal_rejected_by_mids_band(self):
        self._assert_rejects(band_lo=2000.0, band_hi=8000.0, probe_hz=60.0)

    def test_high_signal_rejected_by_low_band(self):
        self._assert_rejects(band_lo=20.0, band_hi=200.0, probe_hz=4000.0)

    def test_high_above_band_rejected(self):
        self._assert_rejects(band_lo=250.0, band_hi=2000.0, probe_hz=10000.0)


class NyquistClampTests(unittest.TestCase):
    """Bands that crowd the Nyquist boundary must be clamped, not crash.

    ``_design`` clamps ``hi`` to ``sample_rate * 0.49`` before normalising.
    A band that would exceed Nyquist outright (``hi > nyquist``) is still
    designed (clamped); a band where ``lo`` itself is above Nyquist returns
    ``None``.
    """

    def test_band_above_nyquist_returns_none(self):
        sr = 44100
        bb = dsp_bandbank.BatchedBandpass(sr)
        # lo (30 kHz) > Nyquist (22.05 kHz) → must reject, not crash.
        sine = _sine(440.0, sr, 1.0)
        self.assertIsNone(bb.filter_one(sine, 30000.0, 40000.0))

    def test_band_hi_above_nyquist_is_clamped_and_filters(self):
        """Requesting hi=25 kHz at sr=44.1 kHz clamps hi to ~21.6 kHz."""
        sr = 44100
        bb = dsp_bandbank.BatchedBandpass(sr)
        sine = _sine(8000.0, sr, 1.0)
        # Mid-band probe at 8 kHz should still pass through.
        filtered = bb.filter_one(sine, 4000.0, 25000.0, dtype=np.float64)
        self.assertIsNotNone(filtered)

    def test_lo_clamped_to_minimum_one_hz(self):
        """``lo_hz=0`` is clamped to ``max(1.0, lo_hz)`` → design still succeeds."""
        sr = 44100
        bb = dsp_bandbank.BatchedBandpass(sr)
        sine = _sine(100.0, sr, 1.0)
        filtered = bb.filter_one(sine, 0.0, 500.0, dtype=np.float64)
        self.assertIsNotNone(filtered)


class SampleRateThreadingTests(unittest.TestCase):
    """The sample rate baked into the instance affects the SOS coefficients —
    a band designed at 44.1 kHz is not the same as one designed at 48 kHz."""

    def test_same_band_at_different_sample_rates_produces_different_sos(self):
        sine = np.random.default_rng(7).standard_normal(2 * 48000)
        bb_44 = dsp_bandbank.BatchedBandpass(44100)
        bb_48 = dsp_bandbank.BatchedBandpass(48000)
        out_44 = bb_44.filter_one(sine[:44100], 250.0, 2000.0, dtype=np.float64)
        out_48 = bb_48.filter_one(sine[:48000], 250.0, 2000.0, dtype=np.float64)
        # Just assert the SOS coefficient caches are distinct; the output
        # arrays have different lengths so we can't compare them directly.
        self.assertIsNotNone(out_44)
        self.assertIsNotNone(out_48)
        sos_44 = bb_44._sos_cache[(250.0, 2000.0)]
        sos_48 = bb_48._sos_cache[(250.0, 2000.0)]
        self.assertFalse(np.array_equal(sos_44, sos_48))


if __name__ == "__main__":
    unittest.main()

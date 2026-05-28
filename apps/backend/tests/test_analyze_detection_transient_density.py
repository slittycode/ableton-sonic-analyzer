"""Unit tests for ``analyze_per_band_transient_density``.

The detector computes onset density per spectral-balance band (sub-bass →
brilliance) via librosa. Phase 2 cites these per-band rates to anchor hi-hat
bus recommendations and percussion suggestions, so the shape and the
band-specificity of the output are part of the cross-boundary contract.

Tests synthesize signals with known transient density in known bands and
assert the detector concentrates events in the right band.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


_AD_PATH = _BACKEND_ROOT / "analyze_detection.py"
_AD_SPEC = importlib.util.spec_from_file_location("analyze_detection_td_test", _AD_PATH)
if _AD_SPEC is None or _AD_SPEC.loader is None:
    raise AssertionError("Could not load analyze_detection.py")
analyze_detection = importlib.util.module_from_spec(_AD_SPEC)
_AD_SPEC.loader.exec_module(analyze_detection)


_LIBROSA_AVAILABLE = analyze_detection.librosa is not None


def _click_train(
    sample_rate: int, duration_s: float, bpm: float, freq_hz: float,
    amplitude: float = 0.6, decay_s: float = 0.02,
) -> np.ndarray:
    """A click train at ``bpm`` whose clicks are tuned to ``freq_hz``.

    Each click is a short decaying sine that concentrates energy in a
    specific band — useful for testing that band-specific onset density
    rises in the expected band.
    """
    n = int(sample_rate * duration_s)
    signal = np.zeros(n, dtype=np.float64)
    period_s = 60.0 / bpm
    decay_samples = max(1, int(sample_rate * decay_s))
    t_decay = np.arange(decay_samples) / sample_rate
    click = amplitude * np.exp(-t_decay / (decay_s / 3.0)) * np.sin(2 * np.pi * freq_hz * t_decay)
    onset = 0.0
    while onset < duration_s:
        idx = int(onset * sample_rate)
        end = min(idx + decay_samples, n)
        signal[idx:end] += click[: end - idx]
        onset += period_s
    return signal


class NullInputTests(unittest.TestCase):
    """Graceful-degradation contract — downstream Phase 1 emits
    ``transientDensityDetail: None`` rather than crashing on bad input.

    These paths short-circuit *before* any librosa call (the early-return
    guards in ``analyze_per_band_transient_density`` cover ``mono is None``,
    ``size == 0``, ``sample_rate <= 0``, and ``librosa is None`` itself).
    They must hold even when librosa is absent — that's the entire point of
    the graceful-degradation contract — so this class is NOT gated on
    librosa availability.
    """

    def test_empty_array_returns_null_detail(self):
        result = analyze_detection.analyze_per_band_transient_density(
            np.array([], dtype=np.float32),
        )
        self.assertEqual(result, {"transientDensityDetail": None})

    def test_none_input_returns_null_detail(self):
        result = analyze_detection.analyze_per_band_transient_density(None)  # type: ignore[arg-type]
        self.assertEqual(result, {"transientDensityDetail": None})

    def test_zero_sample_rate_returns_null_detail(self):
        result = analyze_detection.analyze_per_band_transient_density(
            np.zeros(44100, dtype=np.float32), sample_rate=0,
        )
        self.assertEqual(result, {"transientDensityDetail": None})


@unittest.skipUnless(_LIBROSA_AVAILABLE, "librosa not installed")
class OutputShapeTests(unittest.TestCase):
    """The detector emits one entry per spectral-balance band; each entry
    has four required fields — the cross-boundary contract for citation."""

    @classmethod
    def setUpClass(cls):
        cls.sr = 22050  # lower SR keeps test fast; librosa is OK with it
        # 4 s of silence + a couple of clicks so onset_strength has something to chew on.
        cls.signal = _click_train(cls.sr, duration_s=4.0, bpm=120.0, freq_hz=200.0)

    def test_all_bands_present_in_output(self):
        result = analyze_detection.analyze_per_band_transient_density(
            self.signal, sample_rate=self.sr,
        )
        detail = result["transientDensityDetail"]
        self.assertIsNotNone(detail)
        # The spectralBalance bands are the same set used everywhere in ASA.
        expected_bands = set(analyze_detection._spectral_balance_bands().keys())
        self.assertEqual(set(detail.keys()), expected_bands)

    def test_each_band_has_required_fields(self):
        result = analyze_detection.analyze_per_band_transient_density(
            self.signal, sample_rate=self.sr,
        )
        for band_name, band_data in result["transientDensityDetail"].items():
            with self.subTest(band=band_name):
                self.assertIn("onsetRatePerSecond", band_data)
                self.assertIn("meanOnsetStrength", band_data)
                self.assertIn("peakOnsetStrength", band_data)
                self.assertIn("eventCount", band_data)
                self.assertIsInstance(band_data["eventCount"], int)
                self.assertGreaterEqual(band_data["onsetRatePerSecond"], 0.0)
                self.assertGreaterEqual(band_data["eventCount"], 0)


@unittest.skipUnless(_LIBROSA_AVAILABLE, "librosa not installed")
class BandSpecificityTests(unittest.TestCase):
    """A click train tuned to a specific frequency must produce more events
    in the band that contains that frequency than in unrelated bands."""

    def test_low_frequency_clicks_register_in_low_bands(self):
        """A 60 Hz click train must produce non-zero events in at least one
        of the sub-bass / low-bass bands.

        Note: a click's broadband attack transient leaks into higher bands
        too, so we don't assert exclusivity — only that the low-band signal
        is actually present (not dropped to zero).
        """
        sr = 22050
        sig = _click_train(sr, duration_s=6.0, bpm=120.0, freq_hz=60.0)
        result = analyze_detection.analyze_per_band_transient_density(sig, sample_rate=sr)
        detail = result["transientDensityDetail"]

        low_events = sum(
            detail[b]["eventCount"] for b in detail if b in ("subBass", "lowBass")
        )
        self.assertGreater(
            low_events, 0,
            f"Expected ≥1 onset in low bands for a 60 Hz click train; got {low_events}",
        )

    def test_silence_yields_zero_events_across_all_bands(self):
        sr = 22050
        silent = np.zeros(sr * 3, dtype=np.float32)
        result = analyze_detection.analyze_per_band_transient_density(
            silent, sample_rate=sr,
        )
        for band_name, band_data in result["transientDensityDetail"].items():
            with self.subTest(band=band_name):
                self.assertEqual(band_data["eventCount"], 0)
                self.assertEqual(band_data["onsetRatePerSecond"], 0.0)


@unittest.skipUnless(_LIBROSA_AVAILABLE, "librosa not installed")
class RateMatchesBpmTests(unittest.TestCase):
    """A click train at 120 BPM → 2 events/sec. Even with bandpass leakage
    and the conservative librosa onset detector, the matching-band rate
    should be in the right ballpark."""

    def test_120_bpm_low_clicks_produce_roughly_two_per_second(self):
        sr = 22050
        sig = _click_train(sr, duration_s=6.0, bpm=120.0, freq_hz=80.0)
        result = analyze_detection.analyze_per_band_transient_density(sig, sample_rate=sr)
        detail = result["transientDensityDetail"]
        # Pick whichever low band saw the most action.
        best = max(("subBass", "lowBass"), key=lambda b: detail[b]["eventCount"])
        rate = detail[best]["onsetRatePerSecond"]
        # Loose bounds — librosa can merge consecutive clicks or miss some.
        # We just want to confirm it's in the right order of magnitude (1–5/s).
        self.assertGreater(rate, 1.0, f"Best band {best} rate {rate} below 1/s")
        self.assertLess(rate, 5.0, f"Best band {best} rate {rate} above 5/s")


if __name__ == "__main__":
    unittest.main()

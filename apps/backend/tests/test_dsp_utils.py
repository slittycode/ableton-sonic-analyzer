"""Unit tests for shared DSP utilities in `dsp_utils.py`.

A numerical bug in any of these helpers — `_pearson_corr` in particular —
propagates into the sidechain dip-correlation loop, the stereo band-correlation
curve, and the segment-by-segment downsamplers consumed by the UI. These tests
exercise each one against synthetic inputs with closed-form expected values.
"""

import importlib.util
import math
import sys
import unittest
from pathlib import Path

import numpy as np


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

_DSP_PATH = _BACKEND_ROOT / "dsp_utils.py"
_DSP_SPEC = importlib.util.spec_from_file_location("dsp_utils_test", _DSP_PATH)
if _DSP_SPEC is None or _DSP_SPEC.loader is None:
    raise AssertionError("Could not load dsp_utils.py for direct helper tests.")
dsp_utils = importlib.util.module_from_spec(_DSP_SPEC)
_DSP_SPEC.loader.exec_module(dsp_utils)


class PearsonCorrTests(unittest.TestCase):
    """Sanity-check the in-house Pearson correlation used across the analyzers."""

    def test_perfect_positive_correlation_is_one(self):
        a = np.linspace(-1.0, 1.0, 200, dtype=np.float64)
        b = 2.0 * a + 0.5
        self.assertAlmostEqual(dsp_utils._pearson_corr(a, b), 1.0, places=6)

    def test_perfect_negative_correlation_is_negative_one(self):
        a = np.linspace(-1.0, 1.0, 200, dtype=np.float64)
        b = -3.0 * a + 1.0
        self.assertAlmostEqual(dsp_utils._pearson_corr(a, b), -1.0, places=6)

    def test_orthogonal_signals_correlate_near_zero(self):
        n = 4096
        t = np.linspace(0, 1.0, n, endpoint=False, dtype=np.float64)
        a = np.sin(2 * np.pi * 4 * t)
        b = np.cos(2 * np.pi * 4 * t)
        corr = dsp_utils._pearson_corr(a, b)
        self.assertLess(abs(corr), 1e-6)

    def test_constant_input_returns_nan(self):
        """Zero-variance input must return NaN (caller treats NaN as 'no correlation')."""
        a = np.full(128, 0.5, dtype=np.float64)
        b = np.linspace(0, 1, 128, dtype=np.float64)
        self.assertTrue(math.isnan(dsp_utils._pearson_corr(a, b)))
        self.assertTrue(math.isnan(dsp_utils._pearson_corr(b, a)))

    def test_empty_input_returns_nan(self):
        a = np.array([], dtype=np.float64)
        b = np.array([], dtype=np.float64)
        self.assertTrue(math.isnan(dsp_utils._pearson_corr(a, b)))

    def test_unequal_lengths_truncates_to_shorter(self):
        a = np.linspace(-1.0, 1.0, 50, dtype=np.float64)
        b = np.concatenate([2.0 * a + 0.5, np.full(20, 999.0)])
        self.assertAlmostEqual(dsp_utils._pearson_corr(a, b), 1.0, places=6)


class DownsampleLufsArrayTests(unittest.TestCase):
    """Verify the LUFS array downsampler used by the UI loudness curve."""

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(dsp_utils._downsample_lufs_array(np.array([], dtype=np.float64)), [])

    def test_all_nan_input_returns_empty_list(self):
        values = np.full(50, np.nan, dtype=np.float64)
        self.assertEqual(dsp_utils._downsample_lufs_array(values), [])

    def test_constant_value_preserved_through_downsample(self):
        values = np.full(1000, -14.2, dtype=np.float64)
        points = dsp_utils._downsample_lufs_array(values, target_points=50)
        self.assertGreater(len(points), 0)
        self.assertLessEqual(len(points), 50)
        for point in points:
            self.assertAlmostEqual(point["lufs"], -14.2, places=1)
            self.assertIn("t", point)

    def test_target_points_caps_output(self):
        """At target_points=10 over a 1000-frame array, we get ≤ 10 rows."""
        values = np.linspace(-30.0, -10.0, 1000, dtype=np.float64)
        points = dsp_utils._downsample_lufs_array(values, target_points=10)
        self.assertGreater(len(points), 0)
        self.assertLessEqual(len(points), 10)

    def test_finite_filter_drops_nan_bins(self):
        """Bins that are entirely NaN must be skipped (not emitted as NaN/zero)."""
        values = np.full(100, np.nan, dtype=np.float64)
        values[10:20] = -12.0  # only one bin worth of finite samples
        points = dsp_utils._downsample_lufs_array(values, target_points=10)
        for point in points:
            self.assertTrue(np.isfinite(point["lufs"]))

    def test_timestamps_are_increasing(self):
        values = np.linspace(-30.0, -10.0, 200, dtype=np.float64)
        points = dsp_utils._downsample_lufs_array(values, target_points=20)
        timestamps = [p["t"] for p in points]
        for prev, curr in zip(timestamps, timestamps[1:]):
            self.assertLess(prev, curr)


class DownsampleBandEnergiesCurveTests(unittest.TestCase):
    """Verify the time-series spectralBalance downsampler."""

    def test_empty_input_returns_empty(self):
        self.assertEqual(
            dsp_utils._downsample_band_energies_curve(
                {}, [], frame_hop_seconds=0.1, target_points=100,
            ),
            [],
        )

    def test_zero_band_names_returns_empty(self):
        energies = {"subBass": [0.1, 0.2], "lowBass": [0.1, 0.2]}
        self.assertEqual(
            dsp_utils._downsample_band_energies_curve(energies, [], 0.1), [],
        )

    def test_zero_or_negative_energy_collapses_to_minus_100_db(self):
        energies = {"subBass": [0.0, 0.0, 0.0, 0.0]}
        result = dsp_utils._downsample_band_energies_curve(
            energies, ["subBass"], frame_hop_seconds=0.1, target_points=4,
        )
        self.assertGreater(len(result), 0)
        for point in result:
            self.assertEqual(point["subBass"], -100.0)

    def test_positive_energy_yields_finite_db_values(self):
        energies = {"subBass": [1.0] * 10, "lowBass": [0.5] * 10}
        result = dsp_utils._downsample_band_energies_curve(
            energies, ["subBass", "lowBass"], frame_hop_seconds=0.05, target_points=5,
        )
        self.assertGreater(len(result), 0)
        for point in result:
            self.assertIn("t", point)
            self.assertIn("subBass", point)
            self.assertIn("lowBass", point)
            self.assertTrue(np.isfinite(point["subBass"]))
            self.assertTrue(np.isfinite(point["lowBass"]))
            # subBass (1.0) is 3 dB above lowBass (0.5) in power → ≥ lowBass.
            self.assertGreater(point["subBass"], point["lowBass"])

    def test_target_points_caps_output_length(self):
        energies = {"subBass": list(np.linspace(0.01, 1.0, 1000))}
        result = dsp_utils._downsample_band_energies_curve(
            energies, ["subBass"], frame_hop_seconds=0.01, target_points=20,
        )
        self.assertLessEqual(len(result), 20)
        self.assertGreater(len(result), 0)


class ComputeTempoCurveTests(unittest.TestCase):
    """Verify the tick → instantaneous-BPM curve helper."""

    def test_empty_ticks_returns_empty(self):
        self.assertEqual(dsp_utils._compute_tempo_curve_from_ticks(np.array([])), [])

    def test_single_tick_returns_empty(self):
        """Need at least two ticks to compute an interval."""
        self.assertEqual(
            dsp_utils._compute_tempo_curve_from_ticks(np.array([1.0])), [],
        )

    def test_steady_120_bpm_resolves_to_120(self):
        # Beat every 0.5 s = 120 BPM
        ticks = np.arange(0.0, 10.0, 0.5, dtype=np.float64)
        curve = dsp_utils._compute_tempo_curve_from_ticks(ticks, target_points=50)
        self.assertGreater(len(curve), 0)
        for point in curve:
            self.assertAlmostEqual(point["bpm"], 120.0, delta=0.5)

    def test_zero_intervals_are_treated_as_invalid(self):
        """Duplicate ticks (zero interval) must not produce inf BPM rows."""
        ticks = np.array([0.0, 0.0, 0.5, 1.0, 1.5, 2.0], dtype=np.float64)
        curve = dsp_utils._compute_tempo_curve_from_ticks(ticks, target_points=10)
        for point in curve:
            self.assertTrue(np.isfinite(point["bpm"]))

    def test_negative_intervals_are_treated_as_invalid(self):
        """Out-of-order ticks must not crash; the rejected intervals are dropped."""
        ticks = np.array([0.0, 0.5, 0.4, 1.0, 1.5, 2.0], dtype=np.float64)
        curve = dsp_utils._compute_tempo_curve_from_ticks(ticks, target_points=10)
        for point in curve:
            self.assertTrue(np.isfinite(point["bpm"]))
            self.assertGreater(point["bpm"], 0.0)

    def test_tempo_change_detected_in_curve(self):
        """A first-half/second-half tempo change must be reflected in the curve range."""
        first_half = np.arange(0.0, 5.0, 0.5)   # 120 BPM
        # Start the second half just after the first half ends so the diff between
        # the last 120-BPM tick and the first 90-BPM tick stays positive.
        second_half = np.arange(5.0 + 2.0 / 3.0, 10.0, 2.0 / 3.0)  # 90 BPM
        ticks = np.concatenate([first_half, second_half]).astype(np.float64)
        curve = dsp_utils._compute_tempo_curve_from_ticks(ticks, target_points=50)
        bpm_values = [point["bpm"] for point in curve]
        self.assertGreater(max(bpm_values), 110.0)
        self.assertLess(min(bpm_values), 100.0)


class ComputeStereoCorrelationCurveTests(unittest.TestCase):
    """Verify the 1-second windowed L/R correlation helper."""

    def test_short_input_returns_empty(self):
        sr = 44_100
        left = np.zeros(sr // 2, dtype=np.float64)  # 0.5 s < window
        right = np.zeros(sr // 2, dtype=np.float64)
        sub_l = np.zeros(sr // 2, dtype=np.float64)
        sub_r = np.zeros(sr // 2, dtype=np.float64)
        result = dsp_utils._compute_stereo_correlation_curve(
            left, right, sub_l, sub_r, sr, window_seconds=1.0,
        )
        self.assertEqual(result, [])

    def test_invalid_sample_rate_returns_empty(self):
        left = right = np.zeros(1000, dtype=np.float64)
        sub_l = sub_r = np.zeros(1000, dtype=np.float64)
        self.assertEqual(
            dsp_utils._compute_stereo_correlation_curve(left, right, sub_l, sub_r, 0),
            [],
        )
        self.assertEqual(
            dsp_utils._compute_stereo_correlation_curve(left, right, sub_l, sub_r, 44_100, window_seconds=0.0),
            [],
        )

    def test_identical_l_r_gives_full_correlation_one(self):
        sr = 44_100
        duration = 3.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float64)
        signal = np.sin(2 * np.pi * 220 * t)
        sub_signal = np.sin(2 * np.pi * 40 * t)
        result = dsp_utils._compute_stereo_correlation_curve(
            signal, signal, sub_signal, sub_signal, sr, window_seconds=1.0,
        )
        self.assertGreater(len(result), 0)
        for point in result:
            self.assertIsNotNone(point["full"])
            self.assertAlmostEqual(point["full"], 1.0, places=2)

    def test_inverted_l_r_gives_full_correlation_negative_one(self):
        sr = 44_100
        duration = 3.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float64)
        signal = np.sin(2 * np.pi * 220 * t)
        sub_signal = np.sin(2 * np.pi * 40 * t)
        result = dsp_utils._compute_stereo_correlation_curve(
            signal, -signal, sub_signal, -sub_signal, sr, window_seconds=1.0,
        )
        for point in result:
            self.assertIsNotNone(point["full"])
            self.assertAlmostEqual(point["full"], -1.0, places=2)

    def test_silent_sub_band_produces_none_sub(self):
        """Sub-correlation must be None when the sub band is silent (not 0 or NaN)."""
        sr = 44_100
        duration = 3.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float64)
        signal = np.sin(2 * np.pi * 220 * t)
        sub_silent = np.zeros_like(signal)
        result = dsp_utils._compute_stereo_correlation_curve(
            signal, signal, sub_silent, sub_silent, sr, window_seconds=1.0,
        )
        self.assertGreater(len(result), 0)
        for point in result:
            self.assertIsNone(point["sub"])


if __name__ == "__main__":
    unittest.main()

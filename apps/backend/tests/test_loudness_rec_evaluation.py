"""Unit tests for the loudness recommendation evaluation harness.

The pure-math reachability checks run without Essentia. The render + re-measure
round-trip is gated behind ``ESSENTIA_AVAILABLE``. A firewall test asserts the
eval module never leaks onto the product path (analyze.py / server.py).
"""

from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path

import numpy as np

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from loudness_rec_evaluation import (
    TRUE_PEAK_OVER_LINEAR,
    analytic_reachability,
    apply_gain,
    db_to_linear,
    evaluate_recommendation_reachability,
    gain_db_to_target,
    linear_to_db,
    projected_true_peak_linear,
    scale_to_true_peak_ceiling,
    synth_stereo_sine,
)

ESSENTIA_AVAILABLE = importlib.util.find_spec("essentia") is not None


class PureMathTests(unittest.TestCase):
    def test_db_linear_round_trip(self) -> None:
        self.assertAlmostEqual(linear_to_db(db_to_linear(6.0)), 6.0, places=6)
        self.assertAlmostEqual(db_to_linear(0.0), 1.0, places=9)
        self.assertEqual(linear_to_db(0.0), float("-inf"))

    def test_gain_db_to_target(self) -> None:
        self.assertAlmostEqual(gain_db_to_target(-14.0, -9.0), 5.0, places=9)
        self.assertAlmostEqual(gain_db_to_target(-6.0, -9.0), -3.0, places=9)

    def test_projected_true_peak_linear(self) -> None:
        self.assertAlmostEqual(projected_true_peak_linear(0.5, 6.0), 0.5 * db_to_linear(6.0), places=9)

    def test_apply_gain_scales_linearly(self) -> None:
        buf = np.full((100, 2), 0.25, dtype=np.float32)
        out = apply_gain(buf, 6.0)
        self.assertAlmostEqual(float(np.max(np.abs(out))), 0.25 * db_to_linear(6.0), places=4)


class AnalyticReachabilityTests(unittest.TestCase):
    def test_pure_gain_reaches_target_with_headroom(self) -> None:
        r = analytic_reachability(current_lufs=-14.0, current_peak_linear=0.5, target_lufs=-9.0, ceiling_linear=db_to_linear(-0.3))
        self.assertTrue(r.pure_gain_reaches_target)
        self.assertFalse(r.contradictory)
        self.assertAlmostEqual(r.limiting_required_db, 0.0, places=9)
        self.assertAlmostEqual(r.final_lufs_estimate, -9.0, places=6)

    def test_over_requires_limiter_but_is_not_contradictory(self) -> None:
        r = analytic_reachability(current_lufs=-6.0, current_peak_linear=0.99, target_lufs=-3.0, ceiling_linear=db_to_linear(-0.3))
        self.assertFalse(r.pure_gain_reaches_target)
        self.assertFalse(r.contradictory)
        self.assertGreater(r.limiting_required_db, 0.0)
        # final estimate sits below target by the limiting amount.
        self.assertAlmostEqual(r.final_lufs_estimate, r.target_lufs - r.limiting_required_db, places=6)

    def test_ceiling_above_full_scale_is_contradictory(self) -> None:
        r = analytic_reachability(current_lufs=-9.0, current_peak_linear=0.9, target_lufs=-9.0, ceiling_linear=db_to_linear(1.0))
        self.assertTrue(r.contradictory)

    def test_non_finite_target_is_contradictory(self) -> None:
        r = analytic_reachability(current_lufs=-9.0, current_peak_linear=0.9, target_lufs=float("nan"), ceiling_linear=db_to_linear(-0.3))
        self.assertTrue(r.contradictory)

    def test_evaluate_recommendation_wrapper_converts_ceiling_dbfs(self) -> None:
        r = evaluate_recommendation_reachability(measured_lufs=-14.0, measured_true_peak_linear=0.5, target_lufs=-9.0, ceiling_dbfs=-0.3)
        self.assertAlmostEqual(r.ceiling_linear, db_to_linear(-0.3), places=9)


class ScaleToCeilingTests(unittest.TestCase):
    def test_over_signal_is_scaled_to_ceiling(self) -> None:
        buf = np.full((100, 2), 1.5, dtype=np.float32)
        out = scale_to_true_peak_ceiling(buf, measured_true_peak=1.5, ceiling_linear=0.7)
        self.assertLessEqual(float(np.max(np.abs(out))), 0.7 + 1e-6)

    def test_signal_below_ceiling_is_unchanged(self) -> None:
        buf = np.full((100, 2), 0.5, dtype=np.float32)
        out = scale_to_true_peak_ceiling(buf, measured_true_peak=0.5, ceiling_linear=0.966)
        self.assertTrue(np.allclose(out, buf))


class ProductPathFirewallTests(unittest.TestCase):
    """The eval module renders/limits audio; it must never reach the request path."""

    def test_eval_module_not_imported_by_product_entry_points(self) -> None:
        for name in ("analyze.py", "server.py"):
            source = (_BACKEND_ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn(
                "loudness_rec_evaluation",
                source,
                f"{name} must not import loudness_rec_evaluation — it renders/limits "
                "audio and is eval-only.",
            )


@unittest.skipUnless(ESSENTIA_AVAILABLE, "Essentia not installed")
class RenderRoundTripTests(unittest.TestCase):
    def test_gain_to_target_lands_within_half_lu(self) -> None:
        from loudness_rec_evaluation import measure_loudness_true_peak

        sr = 44_100
        tone = synth_stereo_sine(peak_linear=0.25, duration_s=10.0, sample_rate=sr)
        cur_lufs, _ = measure_loudness_true_peak(tone, sr)
        self.assertIsNotNone(cur_lufs)
        target = round(cur_lufs + 6.0, 1)
        processed = apply_gain(tone, gain_db_to_target(cur_lufs, target))
        out_lufs, out_tp = measure_loudness_true_peak(processed, sr)
        self.assertIsNotNone(out_lufs)
        self.assertLessEqual(abs(out_lufs - target), 0.5)
        self.assertLessEqual(out_tp, TRUE_PEAK_OVER_LINEAR + 1e-9)

    def test_true_peak_ceiling_removes_overs(self) -> None:
        from loudness_rec_evaluation import measure_loudness_true_peak

        sr = 44_100
        over = synth_stereo_sine(peak_linear=1.5, duration_s=2.0, sample_rate=sr)
        _, over_tp = measure_loudness_true_peak(over, sr)
        self.assertIsNotNone(over_tp)
        self.assertGreater(over_tp, TRUE_PEAK_OVER_LINEAR)
        limited = scale_to_true_peak_ceiling(over, over_tp, 0.7)
        _, lim_tp = measure_loudness_true_peak(limited, sr)
        self.assertLessEqual(lim_tp, 0.7 + 0.05)
        self.assertLess(lim_tp, over_tp)


if __name__ == "__main__":
    unittest.main()

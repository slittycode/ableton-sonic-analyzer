import unittest

import numpy as np

from analyze_core import (
    _is_harmonic_of_shorter_bar,
    _loudness_meter_dominance,
    analyze_time_signature,
)


def _accented(bar: list[float], bars: int) -> np.ndarray:
    return np.asarray(bar * bars, dtype=np.float64)


class LoudnessMeterDominanceTests(unittest.TestCase):
    def test_accented_downbeat_dominates_at_true_bar_length(self) -> None:
        low = _accented([1.0, 0.8, 0.8], 8)  # 3/4, kick every beat, louder downbeat
        self.assertAlmostEqual(_loudness_meter_dominance(low, 3), 1.25, places=3)
        # Folded at 4 the accent smears across positions.
        self.assertLess(_loudness_meter_dominance(low, 4), 1.15)

    def test_flat_signal_is_neutral(self) -> None:
        low = np.full(32, 0.9)
        for bar_length in (3, 4, 5, 6, 7):
            self.assertAlmostEqual(_loudness_meter_dominance(low, bar_length), 1.0, places=3)

    def test_too_few_bars_is_neutral(self) -> None:
        low = _accented([1.0, 0.8, 0.8, 0.8, 0.8, 0.8], 3)  # 3 bars < min 4
        self.assertEqual(_loudness_meter_dominance(low, 6), 1.0)

    def test_missing_signal_is_neutral(self) -> None:
        self.assertEqual(_loudness_meter_dominance(None, 4), 1.0)

    def test_near_silent_offbeats_are_capped(self) -> None:
        low = _accented([1.0, 0.0, 0.0, 0.0], 8)  # broken-kick: one hit per bar
        self.assertEqual(_loudness_meter_dominance(low, 4), 10.0)


class HarmonicCollapseTests(unittest.TestCase):
    def test_three_periodic_accent_collapses_the_six_fold(self) -> None:
        low = _accented([1.0, 0.8, 0.8], 8)  # true 3/4: fold at 6 shows two peaks
        self.assertTrue(_is_harmonic_of_shorter_bar(low, 6, 3))

    def test_genuine_six_bar_accent_does_not_collapse(self) -> None:
        low = _accented([1.0, 0.8, 0.8, 0.8, 0.8, 0.8], 8)  # true 6/8: one peak
        self.assertFalse(_is_harmonic_of_shorter_bar(low, 6, 3))


class AnalyzeTimeSignatureBeatDataTests(unittest.TestCase):
    def test_without_beat_data_behavior_is_count_only(self) -> None:
        # Legacy/--fast callers pass no beat_data: the loudness stream must
        # be absent from the decision (all-neutral) and the 20% count-only
        # margin applies. rhythm_data=None hits the earliest fallback.
        result = analyze_time_signature(None)
        self.assertIsNone(result["timeSignature"])
        self.assertEqual(result["timeSignatureCandidates"], [])


if __name__ == "__main__":
    unittest.main()

import unittest

import numpy as np

from analyze_rhythm import compute_swing_detail


def _swung_onsets(bpm: float, bars: int, swing: float) -> tuple[np.ndarray, np.ndarray]:
    """Build ticks (quarter grid) and onsets (on-beat + swung off-beat 8ths)."""
    beat_s = 60.0 / bpm
    beats = bars * 4
    ticks = np.array([b * beat_s for b in range(beats + 1)], dtype=np.float64)
    onsets = []
    for b in range(beats):
        onsets.append(b * beat_s)                              # on-beat 8th
        onsets.append((b + swing / 100.0) * beat_s)            # off-beat 8th
    return np.asarray(onsets, dtype=np.float64), ticks


class SwingDetailTests(unittest.TestCase):
    def test_straight_reads_fifty(self) -> None:
        onsets, ticks = _swung_onsets(124, 8, 50.0)
        result = compute_swing_detail(onsets, ticks)
        self.assertIsNotNone(result)
        self.assertEqual(result["swingPercent"], 50.0)
        self.assertEqual(result["direction"], "straight")

    def test_swung_ratios_recovered_within_tolerance(self) -> None:
        for swing in (54.0, 58.0, 62.0, 66.0):
            onsets, ticks = _swung_onsets(124, 8, swing)
            result = compute_swing_detail(onsets, ticks)
            self.assertIsNotNone(result, f"swing {swing}")
            self.assertEqual(result["direction"], "swung")
            self.assertLessEqual(
                abs(result["swingPercent"] - swing), 3.0,
                f"swing {swing} -> {result['swingPercent']}",
            )
            self.assertEqual(result["gridResolution"], "8th")
            self.assertGreater(result["offbeatOnsetCount"], 0)

    def test_phase_flip_invariance(self) -> None:
        # Shifting every onset by a constant (as an offbeat-anchored beat
        # tracker effectively would) must not change the swing reading — the
        # whole point of the interval-ratio approach.
        onsets, ticks = _swung_onsets(124, 8, 62.0)
        shifted = compute_swing_detail(onsets + 0.113, ticks + 0.113)
        base = compute_swing_detail(onsets, ticks)
        self.assertEqual(base["swingPercent"], shifted["swingPercent"])

    def test_insufficient_onsets_returns_none(self) -> None:
        self.assertIsNone(compute_swing_detail(np.array([0.0, 0.5]), np.array([0.0, 0.5, 1.0])))
        self.assertIsNone(compute_swing_detail(np.array([]), np.array([])))


def _shuffled_16th_onsets(bpm: float, bars: int, swing: float) -> tuple[np.ndarray, np.ndarray]:
    """Straight 8ths plus swung inner 16ths (UKG shuffle), PR-G5."""
    beat_s = 60.0 / bpm
    beats = bars * 4
    ticks = np.array([b * beat_s for b in range(beats + 1)], dtype=np.float64)
    onsets = []
    for b in range(beats):
        for eighth in (0.0, 0.5):
            base = b + eighth
            onsets.append(base * beat_s)
            onsets.append((base + swing / 100.0 * 0.5) * beat_s)
    return np.asarray(onsets, dtype=np.float64), ticks


class SixteenthShuffleTests(unittest.TestCase):
    def test_shuffled_16ths_recovered_on_the_16th_grid(self) -> None:
        for swing in (58.0, 62.0, 66.0):
            onsets, ticks = _shuffled_16th_onsets(130, 8, swing)
            result = compute_swing_detail(onsets, ticks)
            self.assertIsNotNone(result, f"shuffle {swing}")
            self.assertEqual(result["gridResolution"], "16th")
            self.assertEqual(result["direction"], "swung")
            self.assertLessEqual(
                abs(result["swingPercent"] - swing), 3.0,
                f"shuffle {swing} -> {result['swingPercent']}",
            )

    def test_swung_8ths_still_win_over_the_16th_probe(self) -> None:
        # The 8th grid keeps priority: a swung-8th stream must report the
        # 8th grid exactly as before PR-G5.
        onsets, ticks = _swung_onsets(124, 8, 58.0)
        result = compute_swing_detail(onsets, ticks)
        self.assertEqual(result["gridResolution"], "8th")
        self.assertEqual(result["direction"], "swung")

    def test_straight_16ths_do_not_fabricate_a_shuffle(self) -> None:
        # Straight 16th activity (all IOIs at 0.25 beats) has no long/short
        # split — nothing on the 16th grid may ship, preserving the original
        # output (None here: no 8th-scale IOIs at all).
        beat_s = 60.0 / 130
        beats = 8 * 4
        ticks = np.array([b * beat_s for b in range(beats + 1)], dtype=np.float64)
        onsets = np.arange(0, beats, 0.25) * beat_s
        self.assertIsNone(compute_swing_detail(onsets, ticks))


if __name__ == "__main__":
    unittest.main()

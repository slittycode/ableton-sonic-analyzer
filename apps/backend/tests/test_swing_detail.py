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


if __name__ == "__main__":
    unittest.main()

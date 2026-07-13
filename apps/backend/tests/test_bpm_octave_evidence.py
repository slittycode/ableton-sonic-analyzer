import unittest

import numpy as np

from analyze_rhythm import _score_octave_candidates


def _iois(true_bpm: float, beats_per_hit: float, count: int) -> np.ndarray:
    """IOIs of a stream that fires every `beats_per_hit` beats of the true tempo."""
    interval = 60.0 / true_bpm * beats_per_hit
    return np.full(count, interval, dtype=np.float64)


_EMPTY = np.asarray([], dtype=np.float64)


class ScoreOctaveCandidatesTests(unittest.TestCase):
    def test_halved_shipped_bpm_prefers_the_doubled_candidate(self) -> None:
        # grid_4_4_190 baseline: kick on every 190-beat, shipped bpm 95.
        # At 95 every kick IOI is half a beat (no allowed low-band fit); at
        # 190 it fits at multiple 1 — the 2:1 candidate must win.
        low = _iois(190.0, 1.0, 30)
        full = _iois(190.0, 0.5, 60)  # 8th hats
        candidates = _score_octave_candidates(low, full, 95.0)
        self.assertIsNotNone(candidates)
        self.assertEqual(candidates[0]["ratio"], "2:1")
        self.assertAlmostEqual(candidates[0]["bpm"], 190.0, delta=0.1)

    def test_true_half_tempo_keeps_the_shipped_reading(self) -> None:
        # A genuine 87 BPM kick-on-every-beat groove shipped at 87: the 2:1
        # candidate (174) also explains every IOI but only as multiples of 2
        # on the low band, so economy must keep 1:1 on top.
        low = _iois(87.0, 1.0, 30)
        full = _iois(87.0, 0.5, 60)
        candidates = _score_octave_candidates(low, full, 87.0)
        self.assertEqual(candidates[0]["ratio"], "1:1")
        doubled = next(c for c in candidates if c["ratio"] == "2:1")
        self.assertGreater(candidates[0]["score"], doubled["score"])

    def test_two_thirds_error_recovers_the_notated_tempo(self) -> None:
        # halftime_174 baseline: kick once per bar (every 4 beats of 174),
        # 8th hats on the notated grid, shipped bpm 116 (the measured 2:3
        # error). The hats fit nothing at 116 but fit the 3:2 candidate's
        # 0.5 multiple exactly.
        low = _iois(174.0, 4.0, 12)
        full = _iois(174.0, 0.5, 100)
        candidates = _score_octave_candidates(low, full, 116.0)
        self.assertEqual(candidates[0]["ratio"], "3:2")
        self.assertAlmostEqual(candidates[0]["bpm"], 174.0, delta=0.1)

    def test_correct_halftime_shipping_is_not_contradicted(self) -> None:
        # halftime at 140 shipped CORRECTLY at 140: the kick alone (one hit
        # per bar = a clean 70 BPM pulse at multiple 2) would prefer 1:2 —
        # the full-band 8th-hat stream must rescue the shipped reading.
        # This is the false-alarm case that motivated two-stream scoring.
        low = _iois(140.0, 4.0, 12)
        full = _iois(140.0, 0.5, 100)
        candidates = _score_octave_candidates(low, full, 140.0)
        self.assertEqual(candidates[0]["ratio"], "1:1")
        halved = next(c for c in candidates if c["ratio"] == "1:2")
        self.assertGreater(candidates[0]["score"], halved["score"])

    def test_lowband_only_still_ranks_articulated_pulse_first(self) -> None:
        # No usable full-band stream: pure kick evidence must still prefer
        # the articulated pulse over its aggregations.
        candidates = _score_octave_candidates(_iois(190.0, 1.0, 30), _EMPTY, 95.0)
        self.assertEqual(candidates[0]["ratio"], "2:1")
        self.assertEqual(candidates[0]["fullbandScore"], 0.0)

    def test_ties_break_toward_the_shipped_tempo(self) -> None:
        # IOIs that fit nothing leave every candidate at score 0.0 —
        # the shipped 1:1 reading must sort first rather than a random ratio.
        iois = np.full(10, 0.777, dtype=np.float64) * np.pi
        candidates = _score_octave_candidates(iois, _EMPTY, 130.0)
        if {c["score"] for c in candidates} == {0.0}:
            self.assertEqual(candidates[0]["ratio"], "1:1")

    def test_candidates_outside_plausible_range_are_dropped(self) -> None:
        candidates = _score_octave_candidates(_iois(190.0, 1.0, 30), _EMPTY, 190.0)
        ratios = {c["ratio"] for c in candidates}
        self.assertNotIn("2:1", ratios)  # 380 BPM is outside [40, 220]
        self.assertIn("1:2", ratios)

    def test_too_few_iois_abstains(self) -> None:
        self.assertIsNone(
            _score_octave_candidates(_iois(120.0, 1.0, 3), _iois(120.0, 1.0, 2), 120.0)
        )

    def test_missing_shipped_bpm_abstains(self) -> None:
        self.assertIsNone(
            _score_octave_candidates(_iois(120.0, 1.0, 30), _EMPTY, 0.0)
        )


if __name__ == "__main__":
    unittest.main()

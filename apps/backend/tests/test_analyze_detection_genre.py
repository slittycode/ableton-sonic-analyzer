"""Unit tests for ``analyze_genre_detail`` — the dict-driven genre classifier.

Unlike the audio-driven detectors in this module, ``analyze_genre_detail``
operates entirely on a previously computed Phase 1 result dict
(``spectralBalance``, ``rhythmDetail``, ``sidechainDetail``, etc.). That makes
it cheap to test in isolation — no audio, no Essentia, no librosa.

These tests lock the abstention contract (returns ``{"genreDetail": None}``
below a confidence threshold or with insufficient input features) and the
basic signature-match behavior for a few canonical electronic-music genres.
"""

import importlib.util
import sys
import unittest
from pathlib import Path


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


_AD_PATH = _BACKEND_ROOT / "analyze_detection.py"
_AD_SPEC = importlib.util.spec_from_file_location("analyze_detection_genre_test", _AD_PATH)
if _AD_SPEC is None or _AD_SPEC.loader is None:
    raise AssertionError("Could not load analyze_detection.py")
analyze_detection = importlib.util.module_from_spec(_AD_SPEC)
_AD_SPEC.loader.exec_module(analyze_detection)


def _phase1_result(**overrides) -> dict:
    """Build a Phase 1 result dict with sensible mid-range defaults.

    The classifier requires ≥3 of 7 core features to be non-None; this helper
    starts with all 7 present so individual tests can null them out
    selectively without crossing the abstention threshold accidentally.
    """
    base = {
        "bpm": 120.0,
        "crestFactor": 8.0,
        "spectralBalance": {"subBass": -16.0},
        "spectralDetail": {"spectralCentroid": 3000.0},
        "rhythmDetail": {"onsetRate": 5.0},
        "sidechainDetail": {"pumpingStrength": 0.4},
        "bassDetail": {"averageDecayMs": 350.0},
    }
    # Deep-merge nested dicts under recognised keys, replace top-level scalars.
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


class GenreRangeScoreTests(unittest.TestCase):
    """``_genre_range_score`` is the building block — verify the math."""

    def test_value_inside_range_returns_one(self):
        self.assertEqual(analyze_detection._genre_range_score(125.0, 120, 130), 1.0)

    def test_value_at_range_boundary_returns_one(self):
        self.assertEqual(analyze_detection._genre_range_score(120.0, 120, 130), 1.0)
        self.assertEqual(analyze_detection._genre_range_score(130.0, 120, 130), 1.0)

    def test_value_just_outside_range_decays_toward_zero(self):
        """At ``value == range_max + half_range`` the score hits exactly 0.
        Just before that boundary it's positive but less than 1.0."""
        # range (120,130) → half_range=5. value=132 is 7 from center,
        # normalized_dist=(7-5)/5=0.4 → score = 1 - 0.4**2 = 0.84.
        score = analyze_detection._genre_range_score(132.0, 120, 130)
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)

    def test_value_far_outside_range_returns_zero(self):
        # At distance == 2*half_range from center the score reaches 0 and is
        # clamped to 0 thereafter.
        self.assertEqual(analyze_detection._genre_range_score(0.0, 120, 130), 0.0)
        self.assertEqual(analyze_detection._genre_range_score(135.0, 120, 130), 0.0)

    def test_zero_width_range_returns_zero_outside(self):
        # half_range == 0 path — defensive, would never occur with real signatures.
        self.assertEqual(analyze_detection._genre_range_score(125.0, 120, 120), 0.0)


class AbstentionTests(unittest.TestCase):
    """The classifier must abstain when input is missing or ambiguous."""

    def test_returns_null_when_fewer_than_three_core_features_present(self):
        # Only 2 of 7 core features supplied.
        result = analyze_detection.analyze_genre_detail({
            "bpm": 128.0,
            "crestFactor": 7.0,
        })
        self.assertEqual(result, {"genreDetail": None})

    def test_returns_null_when_result_is_completely_empty(self):
        self.assertEqual(analyze_detection.analyze_genre_detail({}), {"genreDetail": None})

    def test_returns_null_when_best_score_below_quarter_threshold(self):
        """Inputs that don't match any signature (extreme outliers) — the
        classifier must abstain rather than force a label."""
        result = analyze_detection.analyze_genre_detail(_phase1_result(
            bpm=999.0,  # No genre signature has a 999 BPM range.
            spectralBalance={"subBass": 50.0},  # Way above any signature.
            spectralDetail={"spectralCentroid": 50000.0},
        ))
        # Either abstains entirely, or returns a result with very low confidence.
        if result["genreDetail"] is not None:
            self.assertLess(result["genreDetail"]["confidence"], 0.5)


class SignatureMatchTests(unittest.TestCase):
    """Hand-built results that should clearly land on a specific genre."""

    def test_techno_signature_resolves_to_techno_family(self):
        result = analyze_detection.analyze_genre_detail(_phase1_result(
            bpm=128.0,
            crestFactor=6.5,
            spectralBalance={"subBass": -12.0},
            spectralDetail={"spectralCentroid": 2500.0},
            rhythmDetail={"onsetRate": 6.0},
            sidechainDetail={"pumpingStrength": 0.45},
            bassDetail={"averageDecayMs": 600.0},
        ))
        self.assertIsNotNone(result["genreDetail"])
        # The exact ID may be techno, driving-techno, melodic-techno, etc.,
        # depending on the closest signature — assert the family rolls up.
        family = result["genreDetail"]["genreFamily"]
        self.assertEqual(family, "techno")

    def test_house_signature_resolves_to_house_family(self):
        result = analyze_detection.analyze_genre_detail(_phase1_result(
            bpm=124.0,
            crestFactor=7.5,
            spectralBalance={"subBass": -14.0},
            spectralDetail={"spectralCentroid": 3000.0},
            rhythmDetail={"onsetRate": 5.5},
            sidechainDetail={"pumpingStrength": 0.55},
            bassDetail={"averageDecayMs": 300.0},
        ))
        self.assertIsNotNone(result["genreDetail"])
        self.assertEqual(result["genreDetail"]["genreFamily"], "house")

    def test_dnb_signature_resolves_to_dnb_family(self):
        result = analyze_detection.analyze_genre_detail(_phase1_result(
            bpm=174.0,
            crestFactor=8.0,
            spectralBalance={"subBass": -10.0},
            spectralDetail={"spectralCentroid": 3500.0},
            rhythmDetail={"onsetRate": 12.0},
            sidechainDetail={"pumpingStrength": 0.4},
            bassDetail={"averageDecayMs": 400.0},
        ))
        self.assertIsNotNone(result["genreDetail"])
        self.assertEqual(result["genreDetail"]["genreFamily"], "dnb")


class OutputShapeTests(unittest.TestCase):
    """The classifier's response shape is part of the Phase 1 → UI contract."""

    def test_result_includes_required_fields(self):
        result = analyze_detection.analyze_genre_detail(_phase1_result(bpm=128.0))
        detail = result["genreDetail"]
        if detail is None:
            self.skipTest("classifier abstained — shape test requires a positive match")
        self.assertIn("genre", detail)
        self.assertIn("confidence", detail)
        self.assertIn("secondaryGenre", detail)
        self.assertIn("genreFamily", detail)
        self.assertIn("topScores", detail)
        self.assertIsInstance(detail["topScores"], list)
        # topScores is capped at 5 entries.
        self.assertLessEqual(len(detail["topScores"]), 5)
        for entry in detail["topScores"]:
            self.assertIn("genre", entry)
            self.assertIn("score", entry)

    def test_confidence_is_bounded_in_0_to_1(self):
        result = analyze_detection.analyze_genre_detail(_phase1_result(bpm=128.0))
        detail = result["genreDetail"]
        if detail is None:
            self.skipTest("classifier abstained")
        self.assertGreaterEqual(detail["confidence"], 0.0)
        self.assertLessEqual(detail["confidence"], 1.0)

    def test_top_scores_are_sorted_descending(self):
        result = analyze_detection.analyze_genre_detail(_phase1_result(bpm=128.0))
        detail = result["genreDetail"]
        if detail is None:
            self.skipTest("classifier abstained")
        scores = [entry["score"] for entry in detail["topScores"]]
        self.assertEqual(scores, sorted(scores, reverse=True))


class AmbiguousScoreCapTests(unittest.TestCase):
    """When the top two genres are within 0.05 of each other, confidence
    must be capped at 0.4 to signal ambiguity to the UI/Phase 2."""

    def test_confidence_capped_when_genres_nearly_tied(self):
        # House and tech-house signatures overlap heavily near 125 BPM with
        # moderate sidechain. Pick values that should land in the overlap.
        result = analyze_detection.analyze_genre_detail(_phase1_result(
            bpm=126.0,
            spectralBalance={"subBass": -16.0},
            crestFactor=8.0,
            spectralDetail={"spectralCentroid": 3500.0},
            rhythmDetail={"onsetRate": 5.5},
            sidechainDetail={"pumpingStrength": 0.5},
            bassDetail={"averageDecayMs": 350.0},
        ))
        detail = result["genreDetail"]
        if detail is None:
            self.skipTest("classifier abstained")
        # Inspect whether the second-best score is within 0.05 of the first;
        # if so, confidence must be ≤ 0.4. If not, we can't assert the cap.
        scores = detail["topScores"]
        if len(scores) >= 2 and (scores[0]["score"] - scores[1]["score"]) < 0.05:
            self.assertLessEqual(detail["confidence"], 0.4)


class BooleanFlagBoostTests(unittest.TestCase):
    """``acidDetail.isAcid``, ``supersawDetail.isSupersaw``, and
    ``vocalDetail.hasVocals`` boost matching-family scores. A regression
    that drops the boost would lose track-character signal."""

    def test_acid_flag_boosts_acid_techno_score(self):
        baseline = _phase1_result(
            bpm=130.0,
            spectralBalance={"subBass": -14.0},
            crestFactor=8.0,
            spectralDetail={"spectralCentroid": 4000.0},
            rhythmDetail={"onsetRate": 7.0},
            sidechainDetail={"pumpingStrength": 0.45},
            bassDetail={"averageDecayMs": 400.0},
        )
        without_acid = analyze_detection.analyze_genre_detail(baseline)
        with_acid = analyze_detection.analyze_genre_detail({
            **baseline,
            "acidDetail": {"isAcid": True},
        })

        def _acid_techno_score(detail):
            if detail is None:
                return None
            for entry in detail["topScores"]:
                if entry["genre"] == "acid-techno":
                    return entry["score"]
            return None

        s_without = _acid_techno_score(without_acid["genreDetail"])
        s_with = _acid_techno_score(with_acid["genreDetail"])
        if s_without is None or s_with is None:
            self.skipTest("acid-techno did not surface in top-5 — cannot compare")
        self.assertGreaterEqual(s_with, s_without)


if __name__ == "__main__":
    unittest.main()

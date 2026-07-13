import unittest

from fundamentals_quality import build_fundamentals_quality


class FundamentalsQualityTests(unittest.TestCase):
    def test_marks_strong_local_measurements_as_authoritative(self) -> None:
        payload = {
            "bpm": 128.0,
            "bpmConfidence": 0.92,
            "bpmPercival": 128.1,
            "bpmAgreement": True,
            "bpmDoubletime": False,
            "bpmSource": "rhythm_extractor_confirmed",
            "key": "A Minor",
            "keyConfidence": 0.82,
            "keyProfile": "edma",
            "timeSignature": "4/4",
            "timeSignatureSource": "onset_autocorrelation",
            "timeSignatureConfidence": 0.71,
            "rhythmDetail": {
                "beatGrid": [0.0, 0.46875, 0.9375, 1.40625],
                "downbeats": [0.0],
                "downbeatConfidence": 0.7,
                "downbeatSource": "kick_accent",
            },
            "chordDetail": {
                "chordStrength": 0.78,
                "chordTimelineAgreement": True,
                "chordTimelineSource": "librosa_viterbi",
                "chordChangeCount": 2,
            },
            "kickDetail": {"kickCount": 16, "fundamentalHz": 55.0},
            "snareDetail": {"hitCount": 8},
            "hihatDetail": {"hitCount": 32},
            "transcriptionDetail": {
                "averageConfidence": 0.81,
                "fullMixFallback": False,
                "noteCount": 12,
                "transcriptionMethod": "torchcrepe-viterbi",
            },
        }

        quality = build_fundamentals_quality(payload, analysis_mode="full")

        self.assertTrue(quality["localOnly"])
        self.assertTrue(quality["llmExcluded"])
        self.assertEqual(quality["domains"]["tempo"]["status"], "authoritative")
        self.assertEqual(quality["domains"]["key"]["status"], "authoritative")
        self.assertEqual(quality["domains"]["meter"]["status"], "authoritative")
        self.assertEqual(quality["domains"]["chords"]["status"], "authoritative")
        self.assertEqual(quality["domains"]["percussion"]["status"], "authoritative")
        self.assertEqual(quality["domains"]["transcription"]["status"], "authoritative")

    def test_meter_evidence_summarizes_candidates(self) -> None:
        payload = {
            "bpm": 128.0,
            "bpmConfidence": 0.9,
            "timeSignature": "4/4",
            "timeSignatureSource": "onset_autocorrelation",
            "timeSignatureConfidence": 0.6,
            "timeSignatureCandidates": [
                {"timeSignature": "4/4", "dominance": 1.5, "positionMeans": [2.0, 1.2, 1.4, 1.3]},
                {"timeSignature": "3/4", "dominance": 1.2, "positionMeans": [1.8, 1.5, 1.5]},
            ],
        }
        quality = build_fundamentals_quality(payload, analysis_mode="full")
        evidence = quality["domains"]["meter"]["evidence"]
        self.assertEqual(evidence["bestCandidate"], "4/4")
        self.assertEqual(evidence["candidateCount"], 2)
        self.assertAlmostEqual(evidence["margin"], 0.25, places=3)

        # No candidates (fast mode / fallback) — evidence stays minimal.
        quality = build_fundamentals_quality(
            {"bpm": 128.0, "timeSignature": "4/4", "timeSignatureSource": "assumed_four_four"},
            analysis_mode="fast",
        )
        self.assertNotIn("bestCandidate", quality["domains"]["meter"]["evidence"])

    def test_tempo_cross_check_agreement_settles_mid_confidence(self) -> None:
        # Two independent estimators agreeing IS the settling evidence — a
        # mid-range extractor confidence must not demote a cross-confirmed BPM.
        payload = {
            "bpm": 128.0,
            "bpmConfidence": 0.6,
            "bpmPercival": 128.4,
            "bpmAgreement": True,
            "bpmDoubletime": False,
            "bpmSource": "rhythm_extractor_confirmed",
        }
        quality = build_fundamentals_quality(payload, analysis_mode="full")
        self.assertEqual(quality["domains"]["tempo"]["status"], "authoritative")

        # Without agreement the mid-confidence demotion stands.
        payload["bpmAgreement"] = None
        quality = build_fundamentals_quality(payload, analysis_mode="full")
        self.assertEqual(quality["domains"]["tempo"]["status"], "ambiguous")

        # And agreement does not rescue genuinely low confidence.
        payload["bpmAgreement"] = True
        payload["bpmConfidence"] = 0.3
        quality = build_fundamentals_quality(payload, analysis_mode="full")
        self.assertEqual(quality["domains"]["tempo"]["status"], "ambiguous")

    def test_marks_assumed_meter_and_chord_disagreement_as_ambiguous(self) -> None:
        payload = {
            "bpm": 126.0,
            "bpmConfidence": 0.86,
            "bpmAgreement": True,
            "key": "C Minor",
            "keyConfidence": 0.3,
            "timeSignature": "4/4",
            "timeSignatureSource": "assumed_four_four",
            "timeSignatureConfidence": 0.0,
            "chordDetail": {
                "chordStrength": 0.8,
                "chordTimelineAgreement": False,
            },
            "transcriptionDetail": {
                "averageConfidence": 0.9,
                "fullMixFallback": True,
                "noteCount": 8,
            },
        }

        quality = build_fundamentals_quality(payload)

        self.assertEqual(quality["overallStatus"], "ambiguous")
        self.assertEqual(quality["domains"]["meter"]["status"], "ambiguous")
        self.assertEqual(quality["domains"]["key"]["status"], "ambiguous")
        self.assertEqual(quality["domains"]["chords"]["status"], "ambiguous")
        self.assertEqual(quality["domains"]["transcription"]["status"], "ambiguous")
        self.assertIn("working assumption", quality["domains"]["meter"]["plainEnglish"])
        self.assertIn("detector disagreement", quality["domains"]["chords"]["plainEnglish"])

    def test_beat_grid_is_authoritative_at_mid_tempo_confidence(self) -> None:
        # A well-tracked grid on a track whose tempo cross-check is only middling
        # (0.5) must not be marked "ambiguous" — that wrongly forced every
        # beat-grid-citing recommendation to be hedged. Below the detector's own
        # ambiguity floor (0.4), the grid is genuinely uncertain.
        base = {
            "bpm": 128.0,
            "timeSignature": "4/4",
            "rhythmDetail": {"beatGrid": [0.0, 0.47, 0.94, 1.41]},
        }

        mid = build_fundamentals_quality({**base, "bpmConfidence": 0.5})
        self.assertEqual(mid["domains"]["beatGrid"]["status"], "authoritative")

        low = build_fundamentals_quality({**base, "bpmConfidence": 0.3})
        self.assertEqual(low["domains"]["beatGrid"]["status"], "ambiguous")

    def test_overall_status_ignores_not_run_domains(self) -> None:
        # A clean standard run never runs transcription, so that domain is
        # not_run. A single not_run domain must not drag the overall status
        # down to "ambiguous" when everything actually measured is solid.
        payload = {
            "bpm": 128.0,
            "bpmConfidence": 0.92,
            "bpmAgreement": True,
            "key": "A Minor",
            "keyConfidence": 0.82,
            "timeSignature": "4/4",
            "timeSignatureSource": "onset_autocorrelation",
            "timeSignatureConfidence": 0.71,
            "rhythmDetail": {
                "beatGrid": [0.0, 0.47, 0.94, 1.41],
                "downbeats": [0.0, 1.88],
                "downbeatConfidence": 0.7,
            },
            "chordDetail": {"chordStrength": 0.78, "chordTimelineAgreement": True},
            "kickDetail": {"kickCount": 16, "fundamentalHz": 55.0},
            "snareDetail": {"hitCount": 8},
            "hihatDetail": {"hitCount": 32},
        }

        quality = build_fundamentals_quality(payload)

        self.assertEqual(quality["domains"]["transcription"]["status"], "not_run")
        self.assertEqual(quality["overallStatus"], "authoritative")

    def test_marks_missing_mandatory_fundamentals_as_failed(self) -> None:
        quality = build_fundamentals_quality({})

        self.assertEqual(quality["overallStatus"], "failed")
        self.assertEqual(quality["domains"]["tempo"]["status"], "failed")
        self.assertEqual(quality["domains"]["key"]["status"], "failed")
        self.assertEqual(quality["domains"]["meter"]["status"], "failed")
        self.assertEqual(quality["domains"]["beatGrid"]["status"], "not_run")


if __name__ == "__main__":
    unittest.main()

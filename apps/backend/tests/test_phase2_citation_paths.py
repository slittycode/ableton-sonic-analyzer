"""Backend citation-path verification (M4).

Defense-in-depth mirror of the frontend's citation-existence check
(`validatePhase1FieldCitations` in apps/ui/src/services/phase2Validator.ts).
The backend flags Phase 2 recommendations whose `phase1Fields` cite a dotted
path that does not resolve against the authoritative measurement payload, so a
non-browser API consumer cannot silently accept invented citations. WARNING
only — Phase 1 authority means a flagged citation is never a rejection.
"""
import unittest

from server_phase2 import (
    _collect_measurement_field_paths,
    _validate_phase2_citation_paths,
)


class CollectMeasurementFieldPathsTests(unittest.TestCase):
    """Faithful port of walkForPaths()/collectPhase1FieldPaths()."""

    def test_nested_object_paths_resolve(self):
        paths = _collect_measurement_field_paths(
            {"spectralBalance": {"subBass": 0.4, "highs": 0.1}}
        )
        self.assertIn("spectralBalance", paths)
        self.assertIn("spectralBalance.subBass", paths)
        self.assertIn("spectralBalance.highs", paths)

    def test_array_path_itself_registers(self):
        paths = _collect_measurement_field_paths(
            {"lufsCurve": {"shortTerm": [-14.0, -13.5, -13.2]}}
        )
        # The array path is registered even though its items are scalars.
        self.assertIn("lufsCurve.shortTerm", paths)

    def test_array_of_objects_registers_item_field_paths(self):
        paths = _collect_measurement_field_paths(
            {"arrangementDetail": {"noveltyPeaks": [{"time": 1.0, "strength": 0.9}]}}
        )
        self.assertIn("arrangementDetail.noveltyPeaks", paths)
        self.assertIn("arrangementDetail.noveltyPeaks.time", paths)
        self.assertIn("arrangementDetail.noveltyPeaks.strength", paths)

    def test_concrete_stem_paths_register(self):
        paths = _collect_measurement_field_paths(
            {
                "stemAnalysis": {
                    "bass": {"reverbDetail": {"preDelayMs": 42.0}},
                }
            }
        )
        self.assertIn("stemAnalysis.bass.reverbDetail", paths)
        self.assertIn("stemAnalysis.bass.reverbDetail.preDelayMs", paths)
        # No literal wildcard is ever registered — the prompt cites concrete stems.
        self.assertNotIn("stemAnalysis.*.reverbDetail", paths)

    def test_null_and_empty_yield_no_paths(self):
        self.assertEqual(_collect_measurement_field_paths({}), set())


class ValidatePhase2CitationPathsTests(unittest.TestCase):
    MEASUREMENT = {
        "bpm": 128.0,
        "spectralBalance": {"subBass": 0.4},
        "kickDetail": {"fundamentalHz": 55.0},
        "stemAnalysis": {"bass": {"reverbDetail": {"preDelayMs": 42.0}}},
    }

    def test_valid_concrete_citation_yields_no_warning(self):
        phase2 = {
            "abletonRecommendations": [
                {"device": "EQ Eight", "phase1Fields": ["spectralBalance.subBass"]}
            ]
        }
        warnings = _validate_phase2_citation_paths(phase2, self.MEASUREMENT)
        self.assertEqual(warnings, [])

    def test_valid_concrete_stem_citation_is_not_a_false_positive(self):
        phase2 = {
            "mixAndMasterChain": [
                {"device": "Reverb", "phase1Fields": ["stemAnalysis.bass.reverbDetail"]}
            ]
        }
        warnings = _validate_phase2_citation_paths(phase2, self.MEASUREMENT)
        self.assertEqual(warnings, [])

    def test_invented_path_yields_exactly_one_warning(self):
        phase2 = {
            "abletonRecommendations": [
                {"device": "EQ Eight", "phase1Fields": ["kickDetail.madeUpField"]}
            ]
        }
        warnings = _validate_phase2_citation_paths(phase2, self.MEASUREMENT)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["code"], "UNRESOLVED_CITATION_PATH")
        self.assertEqual(warnings[0]["path"], "abletonRecommendations[0].phase1Fields")
        self.assertEqual(warnings[0]["originalValue"], "kickDetail.madeUpField")

    def test_wildcard_citation_is_flagged_because_payload_is_concrete(self):
        # The frontend rejects a literal '*' citation too — the payload holds
        # concrete stem names, so a wildcard never resolves. Parity check.
        phase2 = {
            "abletonRecommendations": [
                {"device": "Reverb", "phase1Fields": ["stemAnalysis.*.reverbDetail"]}
            ]
        }
        warnings = _validate_phase2_citation_paths(phase2, self.MEASUREMENT)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["code"], "UNRESOLVED_CITATION_PATH")

    def test_secret_sauce_bucket_is_checked(self):
        phase2 = {
            "secretSauce": {
                "workflowSteps": [
                    {"instruction": "x", "phase1Fields": ["nope.not.real"]}
                ]
            }
        }
        warnings = _validate_phase2_citation_paths(phase2, self.MEASUREMENT)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(
            warnings[0]["path"], "secretSauce.workflowSteps[0].phase1Fields"
        )

    def test_track_layout_grounding_bucket_is_checked(self):
        phase2 = {
            "trackLayout": [
                {
                    "order": 1,
                    "name": "Bass",
                    "grounding": {"phase1Fields": ["kickDetail.madeUpField"]},
                }
            ]
        }
        warnings = _validate_phase2_citation_paths(phase2, self.MEASUREMENT)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["code"], "UNRESOLVED_CITATION_PATH")
        self.assertEqual(
            warnings[0]["path"], "trackLayout[0].grounding.phase1Fields"
        )

    def test_missing_or_nonstring_entries_are_skipped(self):
        phase2 = {
            "abletonRecommendations": [
                {"device": "EQ Eight"},  # no phase1Fields → frontend owns this error
                {"device": "EQ Eight", "phase1Fields": []},  # empty → skipped here
                {"device": "EQ Eight", "phase1Fields": [123, "  "]},  # non-str / blank
            ]
        }
        warnings = _validate_phase2_citation_paths(phase2, self.MEASUREMENT)
        self.assertEqual(warnings, [])

    def test_multiple_invented_paths_each_warn(self):
        phase2 = {
            "abletonRecommendations": [
                {
                    "device": "EQ Eight",
                    "phase1Fields": ["spectralBalance.subBass", "bogus.one", "bogus.two"],
                }
            ]
        }
        warnings = _validate_phase2_citation_paths(phase2, self.MEASUREMENT)
        self.assertEqual(len(warnings), 2)
        self.assertEqual(
            {w["originalValue"] for w in warnings}, {"bogus.one", "bogus.two"}
        )


class SpectralRenameNormalizationTests(unittest.TestCase):
    """Regression: the validator must collect allowed paths from the *normalized*
    payload (the shape Gemini is prompted with), not the raw analyzer output.

    ``_normalize_measurement_result_for_gemini`` renames spectral fields with a
    ``Mean`` suffix (``spectralCentroid`` -> ``spectralCentroidMean``), top-level
    and per-stem. Gemini cites the renamed names; walking the raw payload would
    flag every such valid citation as ``UNRESOLVED_CITATION_PATH``.
    """

    # Raw analyzer output: spectralDetail still uses the pre-rename field names.
    MEASUREMENT_RAW = {
        "spectralDetail": {"spectralCentroid": 1800.0, "spectralRolloff": 8000.0},
        "stemAnalysis": {"bass": {"spectralDetail": {"spectralCentroid": 400.0}}},
    }

    def test_renamed_top_level_spectral_citation_is_not_flagged(self):
        phase2 = {
            "abletonRecommendations": [
                {"device": "EQ Eight", "phase1Fields": ["spectralDetail.spectralCentroidMean"]}
            ]
        }
        warnings = _validate_phase2_citation_paths(phase2, self.MEASUREMENT_RAW)
        self.assertEqual(warnings, [])

    def test_renamed_per_stem_spectral_citation_is_not_flagged(self):
        phase2 = {
            "mixAndMasterChain": [
                {
                    "device": "EQ Eight",
                    "phase1Fields": ["stemAnalysis.bass.spectralDetail.spectralCentroidMean"],
                }
            ]
        }
        warnings = _validate_phase2_citation_paths(phase2, self.MEASUREMENT_RAW)
        self.assertEqual(warnings, [])

    def test_invented_spectral_path_still_flagged_after_normalization(self):
        # Normalization fixes false positives without masking genuinely bad paths.
        phase2 = {
            "abletonRecommendations": [
                {"device": "EQ Eight", "phase1Fields": ["spectralDetail.spectralFakeMean"]}
            ]
        }
        warnings = _validate_phase2_citation_paths(phase2, self.MEASUREMENT_RAW)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["code"], "UNRESOLVED_CITATION_PATH")


if __name__ == "__main__":
    unittest.main()

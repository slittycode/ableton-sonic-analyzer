"""Recommendations contract v1 — schema, projection, and round-trip gate.

This is the CI gate for ADR 0003. It proves three things the goal's DoD names:

  1. the committed schema (schemas/recommendations.v1.schema.json) is a valid
     JSON Schema and is the artifact actually validated against — not a
     hand-rolled mirror that could drift from it;
  2. every projected Phase 2 result validates against that schema (the
     "validate all Phase-2 output against it" requirement); and
  3. a projected envelope survives a JSON round-trip unchanged.

It also pins the contract's invariants: citation-gating (uncited cards are
excluded), value/unit normalization, best-effort range, and the schema's
freeze (additionalProperties:false, cited_measurements minItems:1, version const).
"""

import json
import unittest

import jsonschema

import recommendations_contract as rc


# A realistic Phase 2 result covering all three recommendation sources plus the
# prose fields the projection must ignore. Every device card here is cited.
PHASE2_FIXTURE = {
    "trackCharacter": "Driving, sidechained techno with a saturated low end.",
    "sonicElements": {
        "kick": "Punchy analog kick, fundamental ~55 Hz.",
        "bass": "Rolling reese bass, sidechained to the kick.",
        "melodicArp": "Sparse detuned stab.",
        "grooveAndTiming": "Straight 4/4, tight quantize.",
        "effectsAndTexture": "Plate reverb on the stab return.",
    },
    "abletonRecommendations": [
        {
            "device": "Glue Compressor",
            "category": "DYNAMICS",
            "trackContext": "Kick bus",
            "parameter": "Attack",
            "value": "10 ms",
            "reason": "Preserve the kick transient given crest factor 8.2 dB.",
            "phase1Fields": ["dynamicsDetail.crestFactor"],
        },
        {
            "device": "EQ Eight",
            "category": "EQ",
            "trackContext": "Bass",
            "parameter": "Band 1 Frequency",
            "value": "4 kHz",
            "reason": "Carve presence to seat the bass under the kick.",
            "phase1Fields": ["spectralBalance.lowBass", "spectralBalance.mids"],
        },
        {
            "device": "Operator",
            "category": "SYNTHESIS",
            "trackContext": "Bass",
            "parameter": "Oscillator Waveform",
            "value": "Sine",
            "reason": "Sub energy concentrated at the fundamental.",
            "phase1Fields": ["kickDetail.fundamentalHz"],
        },
    ],
    "mixAndMasterChain": [
        {
            "order": 1,
            "device": "Glue Compressor",
            "trackContext": "Master",
            "parameter": "Ratio",
            "value": "3:1",
            "reason": "Gentle master glue; dynamics are already controlled.",
            "phase1Fields": ["dynamicsDetail.crestFactor"],
        },
        {
            "order": 2,
            "device": "Limiter",
            "trackContext": "Master",
            "parameter": "Ceiling",
            "value": "-1 dB",
            "reason": "True-peak headroom for streaming.",
            "phase1Fields": ["truePeak"],
        },
    ],
    "secretSauce": {
        "title": "The pump",
        "explanation": "Sidechain everything to the kick.",
        "implementationSteps": ["Route kick to a send", "Trigger the compressor"],
        "workflowSteps": [
            {
                "step": 1,
                "trackContext": "Bass",
                "device": "Compressor",
                "parameter": "Threshold",
                "value": "-24 dB",
                "instruction": "Sidechain the bass to the kick.",
                "measurementJustification": "Sidechain depth measured at -6 dB.",
                "phase1Fields": ["sidechainDetail.depthDb"],
            }
        ],
    },
}


class SchemaIsValidTests(unittest.TestCase):
    def test_committed_schema_is_a_valid_json_schema(self):
        schema = rc.load_schema()
        # Raises SchemaError if the committed file is not a valid Draft 2020-12
        # schema. This is what makes "validate against the file" trustworthy.
        validator_cls = jsonschema.validators.validator_for(schema)
        validator_cls.check_schema(schema)

    def test_schema_version_const_matches_module_constant(self):
        # Drift guard: the version in the schema file and the module must agree.
        schema = rc.load_schema()
        self.assertEqual(
            schema["properties"]["version"]["const"], rc.CONTRACT_VERSION
        )

    def test_validator_actually_rejects_bad_input(self):
        # Guards against a no-op validator: a missing required field must fail.
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            rc.validate_envelope({"version": rc.CONTRACT_VERSION})


class ProjectionValidatesTests(unittest.TestCase):
    def test_projected_fixture_validates_against_committed_schema(self):
        envelope = rc.project_recommendations(PHASE2_FIXTURE)
        # Must not raise.
        rc.validate_envelope(envelope)
        self.assertEqual(envelope["version"], "recommendations.v1")
        # 3 abletonRecommendations + 2 mixAndMasterChain + 1 workflowStep.
        self.assertEqual(len(envelope["recommendations"]), 6)

    def test_empty_phase2_yields_valid_empty_envelope(self):
        envelope = rc.project_recommendations({})
        rc.validate_envelope(envelope)
        self.assertEqual(envelope["recommendations"], [])

    def test_non_dict_input_is_safe(self):
        for junk in (None, [], "x", 7):
            envelope = rc.project_recommendations(junk)
            rc.validate_envelope(envelope)
            self.assertEqual(envelope["recommendations"], [])

    def test_projection_is_deterministic(self):
        a = rc.project_recommendations(PHASE2_FIXTURE)
        b = rc.project_recommendations(PHASE2_FIXTURE)
        self.assertEqual(a, b)


class RoundTripTests(unittest.TestCase):
    def test_envelope_survives_json_round_trip_unchanged(self):
        envelope = rc.project_recommendations(PHASE2_FIXTURE)
        rc.validate_envelope(envelope)

        serialized = json.dumps(envelope, sort_keys=True)
        reloaded = json.loads(serialized)

        # Still valid after a full serialize -> parse cycle ...
        rc.validate_envelope(reloaded)
        # ... structurally identical ...
        self.assertEqual(reloaded, envelope)
        # ... and serialization is stable (re-dump matches).
        self.assertEqual(json.dumps(reloaded, sort_keys=True), serialized)


class CitationGatingTests(unittest.TestCase):
    def test_uncited_cards_are_excluded(self):
        phase2 = {
            "abletonRecommendations": [
                {"device": "EQ Eight", "parameter": "Gain", "value": "+3 dB"},
                {
                    "device": "EQ Eight",
                    "parameter": "Gain",
                    "value": "+3 dB",
                    "phase1Fields": [],
                },
                {
                    "device": "EQ Eight",
                    "parameter": "Gain",
                    "value": "+3 dB",
                    "phase1Fields": ["spectralBalance.highs"],
                },
            ]
        }
        envelope = rc.project_recommendations(phase2)
        rc.validate_envelope(envelope)
        # Only the third (cited) card survives.
        self.assertEqual(len(envelope["recommendations"]), 1)
        self.assertEqual(
            envelope["recommendations"][0]["cited_measurements"],
            ["spectralBalance.highs"],
        )

    def test_card_missing_device_or_parameter_is_excluded(self):
        phase2 = {
            "abletonRecommendations": [
                {"parameter": "Gain", "value": "1", "phase1Fields": ["bpm"]},
                {"device": "EQ Eight", "value": "1", "phase1Fields": ["bpm"]},
            ]
        }
        envelope = rc.project_recommendations(phase2)
        self.assertEqual(envelope["recommendations"], [])

    def test_blank_citation_strings_are_dropped(self):
        phase2 = {
            "abletonRecommendations": [
                {
                    "device": "EQ Eight",
                    "parameter": "Gain",
                    "value": "1",
                    "phase1Fields": ["  ", "", "spectralBalance.highs", "  "],
                }
            ]
        }
        envelope = rc.project_recommendations(phase2)
        self.assertEqual(
            envelope["recommendations"][0]["cited_measurements"],
            ["spectralBalance.highs"],
        )


class ValueUnitRangeTests(unittest.TestCase):
    def _project_one(self, value):
        phase2 = {
            "abletonRecommendations": [
                {
                    "device": "D",
                    "parameter": "P",
                    "value": value,
                    "phase1Fields": ["bpm"],
                }
            ]
        }
        return rc.project_recommendations(phase2)["recommendations"][0]

    def test_milliseconds(self):
        entry = self._project_one("10 ms")
        self.assertEqual(entry["value"], 10.0)
        self.assertEqual(entry["unit"], "ms")
        self.assertEqual(entry["range"], [7.0, 13.0])

    def test_decibels(self):
        entry = self._project_one("-18 dB")
        self.assertEqual(entry["value"], -18.0)
        self.assertEqual(entry["unit"], "dB")
        self.assertEqual(entry["range"], [-21.0, -15.0])

    def test_kilohertz_normalizes_to_hz(self):
        entry = self._project_one("4 kHz")
        self.assertEqual(entry["value"], 4000.0)
        self.assertEqual(entry["unit"], "Hz")
        self.assertEqual(entry["range"], [3200.0, 4800.0])

    def test_ratio(self):
        entry = self._project_one("3:1")
        self.assertEqual(entry["value"], 3.0)
        self.assertEqual(entry["unit"], "ratio")
        self.assertEqual(entry["range"], [2.0, 4.0])

    def test_percent(self):
        entry = self._project_one("30%")
        self.assertEqual(entry["value"], 30.0)
        self.assertEqual(entry["unit"], "%")
        self.assertEqual(entry["range"], [15.0, 45.0])

    def test_semitones(self):
        entry = self._project_one("+12 st")
        self.assertEqual(entry["value"], 12.0)
        self.assertEqual(entry["unit"], "st")
        self.assertEqual(entry["range"], [11.0, 13.0])

    def test_non_numeric_value_has_null_unit_and_range(self):
        entry = self._project_one("Sine")
        self.assertEqual(entry["value"], "Sine")
        self.assertIsNone(entry["unit"])
        self.assertIsNone(entry["range"])

    def test_unitless_number_has_null_unit_and_range(self):
        entry = self._project_one("0.6")
        self.assertEqual(entry["value"], 0.6)
        self.assertIsNone(entry["unit"])
        self.assertIsNone(entry["range"])


class SchemaFreezeTests(unittest.TestCase):
    """The schema must reject anything outside the frozen v1 shape."""

    def _valid_entry(self):
        return {
            "device": "EQ Eight",
            "parameter": "Gain",
            "value": 3.0,
            "unit": "dB",
            "range": [0.0, 6.0],
            "cited_measurements": ["spectralBalance.highs"],
        }

    def _envelope(self, entry):
        return {"version": rc.CONTRACT_VERSION, "recommendations": [entry]}

    def test_valid_entry_passes(self):
        rc.validate_envelope(self._envelope(self._valid_entry()))

    def test_empty_citation_array_is_rejected(self):
        entry = self._valid_entry()
        entry["cited_measurements"] = []
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            rc.validate_envelope(self._envelope(entry))

    def test_additional_property_is_rejected(self):
        entry = self._valid_entry()
        entry["reason"] = "not part of the frozen contract"
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            rc.validate_envelope(self._envelope(entry))

    def test_missing_required_field_is_rejected(self):
        entry = self._valid_entry()
        del entry["range"]  # range is required (may be null, but must be present)
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            rc.validate_envelope(self._envelope(entry))

    def test_unknown_unit_token_is_rejected(self):
        entry = self._valid_entry()
        entry["unit"] = "decibels"  # not in the unit enum
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            rc.validate_envelope(self._envelope(entry))

    def test_wrong_version_string_is_rejected(self):
        envelope = self._envelope(self._valid_entry())
        envelope["version"] = "recommendations.v2"
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            rc.validate_envelope(envelope)

    def test_range_must_be_two_numbers(self):
        entry = self._valid_entry()
        entry["range"] = [1.0, 2.0, 3.0]
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            rc.validate_envelope(self._envelope(entry))

    def test_null_unit_and_range_are_accepted(self):
        entry = self._valid_entry()
        entry["value"] = "Sine"
        entry["unit"] = None
        entry["range"] = None
        rc.validate_envelope(self._envelope(entry))


class BuildValidatedHelperTests(unittest.TestCase):
    def test_build_validated_returns_envelope(self):
        envelope = rc.build_validated_recommendations(PHASE2_FIXTURE)
        self.assertIsNotNone(envelope)
        self.assertEqual(envelope["version"], "recommendations.v1")

    def test_iter_validation_errors_empty_when_valid(self):
        envelope = rc.project_recommendations(PHASE2_FIXTURE)
        self.assertEqual(rc.iter_validation_errors(envelope), [])

    def test_iter_validation_errors_reports_problems(self):
        bad = {"version": "wrong", "recommendations": [{"device": "X"}]}
        errors = rc.iter_validation_errors(bad)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()

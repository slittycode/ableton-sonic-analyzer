"""Tests for phase2_export.py — the phase2-export.v1 handoff envelope.

Pure-builder tests only; the HTTP shell (status codes, ownership, headers)
is covered by Phase2ExportRouteTests in tests/test_server.py.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import phase2_export  # noqa: E402
import recommendations_contract  # noqa: E402


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "phase2_export"
    / "asa_ableton_gate_alpha.phase2-export.json"
)
EXPORT_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "phase2-export.v1.schema.json"
)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _validate_asa_ableton_handoff(envelope: dict) -> None:
    schema = _load_json(EXPORT_SCHEMA_PATH)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(envelope)
    recommendations_contract.validate_envelope(
        envelope["phase2"]["recommendations"]
    )


def _snapshot(
    *,
    interpretation_status: str = "completed",
    result: dict | None = None,
    diagnostics: dict | None = None,
    provenance: dict | None = None,
    profile_id: str = "producer_summary",
    measurement_result: dict | None = None,
) -> dict:
    """A minimal run snapshot shaped like AnalysisRuntime.get_run output."""
    return {
        "runId": "run-123",
        "stages": {
            "measurement": {
                "status": "completed",
                "result": measurement_result,
            },
            "interpretation": {
                "status": interpretation_status,
                "result": result,
                "profiles": {
                    profile_id: {
                        "attemptId": "attempt-1",
                        "status": interpretation_status,
                        "result": result,
                        "provenance": provenance,
                        "diagnostics": diagnostics,
                        "error": None,
                    }
                },
            },
        },
    }


PHASE2_RESULT = {
    "trackCharacter": "Driving techno",
    "abletonRecommendations": [
        {
            "device": "Glue Compressor",
            "parameter": "Threshold",
            "value": "-12 dB",
            "phase1Fields": ["lufsIntegrated"],
        }
    ],
    "recommendations": {
        "version": "recommendations.v1",
        "recommendations": [
            {
                "device": "Glue Compressor",
                "parameter": "Threshold",
                "value": -12.0,
                "unit": "dB",
                "range": [-15.0, -9.0],
                "cited_measurements": ["lufsIntegrated"],
            }
        ],
    },
}

MEASUREMENT_RESULT = {"bpm": 130.0, "lufsIntegrated": -9.2}

PROVENANCE = {
    "schemaVersion": "interpretation.v2",
    "profileId": "producer_summary",
    "modelName": "gemini-2.5-flash",
    "groundedMeasurementRunId": "run-123",
}

DIAGNOSTICS = {
    "requestId": "req-1",
    "validationWarnings": [
        {
            "code": "RECOMMENDATION_UNVERIFIED",
            "path": "abletonRecommendations[0]",
            "message": "parameter_unknown",
        }
    ],
}


class BuildPhase2ExportTests(unittest.TestCase):
    def test_complete_run_exports_full_envelope(self) -> None:
        envelope = phase2_export.build_phase2_export(
            _snapshot(
                result=PHASE2_RESULT,
                diagnostics=DIAGNOSTICS,
                provenance=PROVENANCE,
                measurement_result=MEASUREMENT_RESULT,
            ),
            exported_at="2026-06-10T00:00:00+00:00",
        )
        self.assertIsNotNone(envelope)
        self.assertEqual(envelope["schemaVersion"], "phase2-export.v1")
        self.assertEqual(envelope["runId"], "run-123")
        self.assertEqual(envelope["exportedAt"], "2026-06-10T00:00:00+00:00")
        # phase2 is the stored interpretation result verbatim — including the
        # frozen recommendations.v1 envelope the validator tail attached.
        self.assertEqual(envelope["phase2"], PHASE2_RESULT)
        self.assertEqual(
            envelope["phase2"]["recommendations"]["version"], "recommendations.v1"
        )
        # phase1 is the authoritative measurement payload, so a consumer can
        # resolve cited phase1Fields paths without a second request.
        self.assertEqual(envelope["phase1"], MEASUREMENT_RESULT)
        self.assertEqual(envelope["provenance"], PROVENANCE)
        self.assertEqual(
            envelope["validationWarnings"],
            DIAGNOSTICS["validationWarnings"],
        )

    def test_envelope_key_set_is_frozen(self) -> None:
        """The v1 key set is a published contract — additions need a version bump."""
        envelope = phase2_export.build_phase2_export(
            _snapshot(result=PHASE2_RESULT, measurement_result=MEASUREMENT_RESULT)
        )
        self.assertEqual(
            set(envelope.keys()),
            {
                "schemaVersion",
                "runId",
                "exportedAt",
                "provenance",
                "validationWarnings",
                "phase1",
                "phase2",
            },
        )

    def test_exported_at_defaults_to_now(self) -> None:
        envelope = phase2_export.build_phase2_export(
            _snapshot(result=PHASE2_RESULT)
        )
        self.assertIsInstance(envelope["exportedAt"], str)
        self.assertIn("T", envelope["exportedAt"])

    def test_missing_diagnostics_yields_empty_warning_list(self) -> None:
        envelope = phase2_export.build_phase2_export(
            _snapshot(result=PHASE2_RESULT, diagnostics=None)
        )
        self.assertEqual(envelope["validationWarnings"], [])

    def test_non_dict_warning_entries_are_dropped(self) -> None:
        envelope = phase2_export.build_phase2_export(
            _snapshot(
                result=PHASE2_RESULT,
                diagnostics={"validationWarnings": ["stray-string", {"code": "X"}]},
            )
        )
        self.assertEqual(envelope["validationWarnings"], [{"code": "X"}])

    def test_no_interpretation_stage_returns_none(self) -> None:
        snapshot = {"runId": "run-123", "stages": {"measurement": {"result": {}}}}
        self.assertIsNone(phase2_export.build_phase2_export(snapshot))

    def test_incomplete_interpretation_returns_none(self) -> None:
        self.assertIsNone(
            phase2_export.build_phase2_export(
                _snapshot(interpretation_status="running", result=None)
            )
        )

    def test_completed_with_null_result_returns_none(self) -> None:
        """The skip path completes an attempt with a null result — not exportable."""
        self.assertIsNone(
            phase2_export.build_phase2_export(_snapshot(result=None))
        )

    def test_stem_summary_only_run_returns_none(self) -> None:
        """Only producer_summary carries device cards; stem_summary is not a handoff."""
        self.assertIsNone(
            phase2_export.build_phase2_export(
                _snapshot(result={"stems": []}, profile_id="stem_summary")
            )
        )

    def test_missing_measurement_result_degrades_to_null_phase1(self) -> None:
        envelope = phase2_export.build_phase2_export(
            _snapshot(result=PHASE2_RESULT, measurement_result=None)
        )
        self.assertIsNotNone(envelope)
        self.assertIsNone(envelope["phase1"])


class AsaAbletonHandoffContractTests(unittest.TestCase):
    def test_committed_gate_alpha_fixture_exists(self) -> None:
        self.assertTrue(
            FIXTURE_PATH.is_file(),
            f"missing committed asa-ableton handoff fixture: {FIXTURE_PATH}",
        )

    def test_fixture_matches_the_export_builder_field_for_field(self) -> None:
        fixture = _load_json(FIXTURE_PATH)
        snapshot = _snapshot(
            result=fixture["phase2"],
            diagnostics={"validationWarnings": fixture["validationWarnings"]},
            provenance=fixture["provenance"],
            measurement_result=fixture["phase1"],
        )
        snapshot["runId"] = fixture["runId"]

        exported = phase2_export.build_phase2_export(
            snapshot,
            exported_at=fixture["exportedAt"],
        )

        self.assertEqual(exported, fixture)

    def test_fixture_satisfies_both_handoff_contracts(self) -> None:
        _validate_asa_ableton_handoff(_load_json(FIXTURE_PATH))

    def test_envelope_shape_drift_is_rejected(self) -> None:
        fixture = _load_json(FIXTURE_PATH)
        for mutation, field in (("remove", "phase1"), ("add", "unexpected")):
            with self.subTest(mutation=mutation, field=field):
                drifted = copy.deepcopy(fixture)
                if mutation == "remove":
                    drifted.pop(field)
                else:
                    drifted[field] = True
                with self.assertRaises(jsonschema.ValidationError):
                    _validate_asa_ableton_handoff(drifted)

    def test_gate_alpha_raw_card_field_drift_is_rejected(self) -> None:
        fixture = _load_json(FIXTURE_PATH)
        for field in ("device", "parameter", "value", "trackContext", "phase1Fields"):
            with self.subTest(field=field):
                drifted = copy.deepcopy(fixture)
                drifted["phase2"]["abletonRecommendations"][0].pop(field)
                with self.assertRaises(jsonschema.ValidationError):
                    _validate_asa_ableton_handoff(drifted)

    def test_normalized_dedupe_and_citation_field_drift_is_rejected(self) -> None:
        fixture = _load_json(FIXTURE_PATH)
        for field in ("device", "parameter", "value", "cited_measurements"):
            with self.subTest(field=field):
                drifted = copy.deepcopy(fixture)
                drifted["phase2"]["recommendations"]["recommendations"][0].pop(field)
                with self.assertRaises(jsonschema.ValidationError):
                    _validate_asa_ableton_handoff(drifted)

    def test_duplicate_cards_and_their_citations_survive_the_handoff(self) -> None:
        fixture = _load_json(FIXTURE_PATH)
        phase2 = fixture["phase2"]
        raw_cards = [
            *phase2["mixAndMasterChain"],
            *phase2["abletonRecommendations"],
            *phase2["secretSauce"]["workflowSteps"],
        ]
        duplicate = [
            card
            for card in raw_cards
            if (card["device"], card["parameter"], card["value"])
            == ("EQ Eight", "Low Shelf Gain", "-1.5 dB")
        ]

        self.assertEqual(len(duplicate), 2)
        self.assertEqual(
            [card["phase1Fields"] for card in duplicate],
            [["spectralBalance.subBass"], ["spectralBalance.subBass"]],
        )

    def test_warning_and_provenance_payloads_are_not_reconstructed(self) -> None:
        fixture = _load_json(FIXTURE_PATH)
        snapshot = _snapshot(
            result=fixture["phase2"],
            diagnostics={"validationWarnings": fixture["validationWarnings"]},
            provenance=fixture["provenance"],
            measurement_result=fixture["phase1"],
        )
        snapshot["runId"] = fixture["runId"]

        exported = phase2_export.build_phase2_export(
            snapshot,
            exported_at=fixture["exportedAt"],
        )

        attempt = snapshot["stages"]["interpretation"]["profiles"][
            "producer_summary"
        ]
        self.assertIs(exported["provenance"], attempt["provenance"])
        self.assertEqual(
            exported["validationWarnings"],
            attempt["diagnostics"]["validationWarnings"],
        )


if __name__ == "__main__":
    unittest.main()

"""Tests for phase2_export.py — the phase2-export.v1 handoff envelope.

Pure-builder tests only; the HTTP shell (status codes, ownership, headers)
is covered by Phase2ExportRouteTests in tests/test_server.py.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import phase2_export  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()

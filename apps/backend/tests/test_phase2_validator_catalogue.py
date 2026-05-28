"""Integration tests for the Live 12 catalogue gates in
`server_phase2.apply_live12_catalogue_gates`.

The synthetic Phase 2 result here intentionally bundles one recommendation in
each of the four categories the goal calls out:

  1. Valid recommendation — accepted, no event.
  2. Hallucinated device — rejected, RECOMMENDATION_REJECTED with
     reason=device_unknown.
  3. Fixable parameter typo — rewritten, PARAMETER_REWRITTEN with original +
     resolved + requestId.
  4. Out-of-range value (on a parameter that DOES carry a spec.min/max in the
     fixture) — rejected, RECOMMENDATION_REJECTED with
     reason=value_out_of_range.

A fifth case covers the citation gate (missing/empty phase1Fields →
RECOMMENDATION_REJECTED with reason=citation_missing).
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from live12_catalogue import Live12Catalogue
from phase2_catalogue_gates import apply_live12_catalogue_gates


_THREE_DEVICE_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "live12_catalogue"
    / "three_device_catalogue.json"
)


def _make_recommendation(
    *,
    device: str,
    parameter: str,
    value: str,
    phase1_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Build the minimum-viable Phase 2 `abletonRecommendations` item."""
    return {
        "device": device,
        "deviceFamily": "NATIVE",
        "trackContext": "Drums",
        "workflowStage": "MIX",
        "category": "DYNAMICS",
        "parameter": parameter,
        "value": value,
        "reason": "test reason",
        "advancedTip": "test advanced tip",
        "phase1Fields": phase1_fields if phase1_fields is not None else ["bpm"],
    }


class CatalogueGatesIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalogue = Live12Catalogue.from_path(_THREE_DEVICE_FIXTURE)

    def _apply(self, phase2_result: dict[str, Any], *, request_id: str = "req-test-42"):
        events = apply_live12_catalogue_gates(
            phase2_result,
            request_id=request_id,
            catalogue=self.catalogue,
        )
        return events

    # ----- Valid recommendation -----

    def test_valid_recommendation_passes_unchanged(self):
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(
                    device="Saturator",
                    parameter="Drive",
                    value="6.0",
                    phase1_fields=["bpm"],
                ),
            ],
        }
        events = self._apply(phase2)
        self.assertEqual(events, [])
        self.assertEqual(len(phase2["abletonRecommendations"]), 1)
        self.assertEqual(phase2["abletonRecommendations"][0]["parameter"], "Drive")

    def test_display_name_device_passes_unchanged(self):
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(
                    device="EQ Eight",
                    parameter="1 Frequency A",
                    value="120",
                    phase1_fields=["bpm"],
                ),
            ],
        }
        events = self._apply(phase2)
        self.assertEqual(events, [])
        self.assertEqual(len(phase2["abletonRecommendations"]), 1)

    # ----- Hallucinated device -----

    def test_hallucinated_device_is_rejected(self):
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(
                    device="Saturation Color",
                    parameter="Drive",
                    value="6.0",
                ),
            ],
        }
        events = self._apply(phase2)
        self.assertEqual(phase2["abletonRecommendations"], [])
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["code"], "RECOMMENDATION_REJECTED")
        self.assertEqual(event["reason"], "device_unknown")
        self.assertEqual(event["device"], "Saturation Color")
        self.assertEqual(event["requestId"], "req-test-42")
        self.assertEqual(event["path"], "abletonRecommendations[0]")

    # ----- Fixable parameter typo -----

    def test_fixable_parameter_typo_is_rewritten_with_event(self):
        # Saturator catalogue has "Drive" (close to "Drives" typo).
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(
                    device="Saturator",
                    parameter="Drives",
                    value="6.0",
                ),
            ],
        }
        events = self._apply(phase2)
        # Recommendation survives — fuzzy resolution accepted.
        self.assertEqual(len(phase2["abletonRecommendations"]), 1)
        self.assertEqual(phase2["abletonRecommendations"][0]["parameter"], "Drive")
        # A single PARAMETER_REWRITTEN event was emitted, original + resolved
        # + requestId all present.
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["code"], "PARAMETER_REWRITTEN")
        self.assertEqual(event["device"], "Saturator")
        self.assertEqual(event["originalParameter"], "Drives")
        self.assertEqual(event["resolvedParameter"], "Drive")
        self.assertEqual(event["requestId"], "req-test-42")
        self.assertEqual(event["path"], "abletonRecommendations[0].parameter")

    def test_parameter_unresolvable_typo_is_rejected(self):
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(
                    device="Saturator",
                    parameter="TotalGarbage",
                    value="6.0",
                ),
            ],
        }
        events = self._apply(phase2)
        self.assertEqual(phase2["abletonRecommendations"], [])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["code"], "RECOMMENDATION_REJECTED")
        self.assertEqual(events[0]["reason"], "parameter_unknown")
        self.assertEqual(events[0]["device"], "Saturator")
        self.assertEqual(events[0]["parameter"], "TotalGarbage")

    # ----- Out-of-range value -----

    def test_out_of_range_value_is_rejected(self):
        # Operator/Volume in the fixture: type=float, min=-36.0, max=6.0.
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(
                    device="Operator",
                    parameter="Volume",
                    value="42 dB",
                ),
            ],
        }
        events = self._apply(phase2)
        self.assertEqual(phase2["abletonRecommendations"], [])
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["code"], "RECOMMENDATION_REJECTED")
        self.assertEqual(event["reason"], "value_out_of_range")
        self.assertEqual(event["device"], "Operator")
        self.assertEqual(event["parameter"], "Volume")
        self.assertEqual(event["value"], "42 dB")

    def test_in_range_value_passes(self):
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(
                    device="Operator",
                    parameter="Volume",
                    value="-12.0 dB",
                ),
            ],
        }
        events = self._apply(phase2)
        self.assertEqual(events, [])
        self.assertEqual(len(phase2["abletonRecommendations"]), 1)

    def test_range_gate_is_inert_when_spec_lacks_bounds(self):
        # Saturator/Drive in the fixture: name only, no min/max -- range gate
        # must NOT fire, even on absurd values.
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(
                    device="Saturator",
                    parameter="Drive",
                    value="9999.0",
                ),
            ],
        }
        events = self._apply(phase2)
        self.assertEqual(events, [])
        self.assertEqual(len(phase2["abletonRecommendations"]), 1)

    def test_unparseable_value_passes_range_gate(self):
        # "auto" cannot be coerced to a number — the gate stays silent rather
        # than producing a false-positive rejection.
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(
                    device="Operator",
                    parameter="Volume",
                    value="auto",
                ),
            ],
        }
        events = self._apply(phase2)
        self.assertEqual(events, [])
        self.assertEqual(len(phase2["abletonRecommendations"]), 1)

    # ----- Citation gate -----

    def test_missing_phase1_fields_is_rejected(self):
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(
                    device="Saturator",
                    parameter="Drive",
                    value="6.0",
                    phase1_fields=[],
                ),
            ],
        }
        events = self._apply(phase2)
        self.assertEqual(phase2["abletonRecommendations"], [])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["code"], "RECOMMENDATION_REJECTED")
        self.assertEqual(events[0]["reason"], "citation_missing")
        self.assertEqual(events[0]["path"], "abletonRecommendations[0].phase1Fields")

    def test_whitespace_only_phase1_fields_is_rejected(self):
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(
                    device="Saturator",
                    parameter="Drive",
                    value="6.0",
                    phase1_fields=["", "   "],
                ),
            ],
        }
        events = self._apply(phase2)
        self.assertEqual(phase2["abletonRecommendations"], [])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["reason"], "citation_missing")

    # ----- Mixed: all four cases at once -----

    def test_mixed_recommendations_drop_only_failures(self):
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(
                    device="Saturator", parameter="Drive", value="3.0",
                ),
                _make_recommendation(
                    device="Saturation Color", parameter="Drive", value="3.0",
                ),
                _make_recommendation(
                    device="Saturator", parameter="Drives", value="3.0",
                ),
                _make_recommendation(
                    device="Operator", parameter="Volume", value="42 dB",
                ),
            ],
        }
        events = self._apply(phase2)
        # Survivors: index 0 (valid) and index 2 (rewritten "Drives" -> "Drive").
        self.assertEqual(len(phase2["abletonRecommendations"]), 2)
        self.assertEqual(phase2["abletonRecommendations"][0]["parameter"], "Drive")
        self.assertEqual(phase2["abletonRecommendations"][1]["parameter"], "Drive")

        codes = sorted(e["code"] for e in events)
        reasons = sorted(
            e.get("reason", "") for e in events if e["code"] == "RECOMMENDATION_REJECTED"
        )
        self.assertEqual(
            codes,
            ["PARAMETER_REWRITTEN", "RECOMMENDATION_REJECTED", "RECOMMENDATION_REJECTED"],
        )
        self.assertEqual(reasons, ["device_unknown", "value_out_of_range"])
        # Base paths still reference the ORIGINAL indices in Gemini's response
        # so the operator log can correlate which slot was dropped.
        rejection_paths = sorted(
            e["path"] for e in events if e["code"] == "RECOMMENDATION_REJECTED"
        )
        self.assertEqual(
            rejection_paths,
            ["abletonRecommendations[1]", "abletonRecommendations[3]"],
        )

    # ----- mixAndMasterChain receives the same gates -----

    def test_mix_and_master_chain_is_gated(self):
        phase2 = {
            "mixAndMasterChain": [
                {
                    "order": 1,
                    "device": "Saturator",
                    "deviceFamily": "NATIVE",
                    "trackContext": "Master",
                    "workflowStage": "MASTER",
                    "parameter": "Drives",  # fuzzy rewrite to "Drive"
                    "value": "3.0",
                    "reason": "test",
                    "phase1Fields": ["bpm"],
                },
                {
                    "order": 2,
                    "device": "Saturation Color",  # hallucination
                    "deviceFamily": "NATIVE",
                    "trackContext": "Master",
                    "workflowStage": "MASTER",
                    "parameter": "Drive",
                    "value": "3.0",
                    "reason": "test",
                    "phase1Fields": ["bpm"],
                },
            ],
        }
        events = self._apply(phase2)
        self.assertEqual(len(phase2["mixAndMasterChain"]), 1)
        self.assertEqual(phase2["mixAndMasterChain"][0]["parameter"], "Drive")
        rewrite_paths = sorted(
            e["path"] for e in events if e["code"] == "PARAMETER_REWRITTEN"
        )
        self.assertEqual(rewrite_paths, ["mixAndMasterChain[0].parameter"])
        rejection_paths = sorted(
            e["path"] for e in events if e["code"] == "RECOMMENDATION_REJECTED"
        )
        self.assertEqual(rejection_paths, ["mixAndMasterChain[1]"])

    # ----- secretSauce.workflowSteps -----

    def test_workflow_steps_are_gated(self):
        phase2 = {
            "secretSauce": {
                "title": "Test",
                "explanation": "Test",
                "implementationSteps": ["Step 1"],
                "workflowSteps": [
                    {
                        "step": 1,
                        "trackContext": "Drums",
                        "device": "Saturator",
                        "parameter": "Drives",  # fuzzy rewrite
                        "value": "3.0",
                        "instruction": "Test",
                        "measurementJustification": "Test",
                        "phase1Fields": ["bpm"],
                    },
                    {
                        "step": 2,
                        "trackContext": "Drums",
                        "device": "Saturator",
                        "parameter": "Drive",
                        "value": "3.0",
                        "instruction": "Test",
                        "measurementJustification": "Test",
                        "phase1Fields": [],  # missing citation
                    },
                ],
            },
        }
        events = self._apply(phase2)
        steps = phase2["secretSauce"]["workflowSteps"]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["parameter"], "Drive")
        codes = sorted(e["code"] for e in events)
        self.assertEqual(codes, ["PARAMETER_REWRITTEN", "RECOMMENDATION_REJECTED"])
        rewrite = next(e for e in events if e["code"] == "PARAMETER_REWRITTEN")
        rejection = next(e for e in events if e["code"] == "RECOMMENDATION_REJECTED")
        self.assertEqual(rewrite["path"], "secretSauce.workflowSteps[0].parameter")
        self.assertEqual(rejection["path"], "secretSauce.workflowSteps[1].phase1Fields")
        self.assertEqual(rejection["reason"], "citation_missing")

    # ----- request_id is always present on events -----

    def test_every_event_carries_request_id(self):
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(device="Nope", parameter="Drive", value="1"),
                _make_recommendation(device="Saturator", parameter="Drives", value="1"),
            ],
        }
        events = self._apply(phase2, request_id="custom-req-id-001")
        self.assertGreater(len(events), 0)
        for event in events:
            self.assertEqual(event["requestId"], "custom-req-id-001")

    # ----- Idempotency / empty / opaque input -----

    def test_empty_phase2_result_produces_no_events(self):
        phase2: dict[str, Any] = {}
        events = self._apply(phase2)
        self.assertEqual(events, [])

    def test_non_dict_input_is_safe(self):
        events = apply_live12_catalogue_gates(
            "not a dict",  # type: ignore[arg-type]
            request_id="req-test-42",
            catalogue=self.catalogue,
        )
        self.assertEqual(events, [])

    def test_loads_default_catalogue_when_not_injected(self):
        """Smoke test: production code path loads `data/live12_catalogue.json`
        via `Live12Catalogue.load_default()` when no catalogue is injected.
        This ensures the on-disk catalogue meets the validator's expectations
        end-to-end."""
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(
                    device="Saturator",
                    parameter="Drive",
                    value="6.0",
                    phase1_fields=["bpm"],
                ),
            ],
        }
        # No `catalogue=` kwarg — falls back to load_default().
        events = apply_live12_catalogue_gates(phase2, request_id="req-default-load")
        self.assertEqual(events, [])
        self.assertEqual(len(phase2["abletonRecommendations"]), 1)


if __name__ == "__main__":
    unittest.main()

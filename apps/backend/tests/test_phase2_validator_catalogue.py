"""Integration tests for the Live 12 catalogue checks in
`phase2_catalogue_gates.apply_live12_catalogue_gates`.

WARN-AND-KEEP CONTRACT: the checks NEVER drop a recommendation and NEVER
rewrite a parameter. Each check emits an advisory `RECOMMENDATION_UNVERIFIED`
warning (discriminated by `reason`) and leaves the recommendation untouched in
the payload. These tests assert exactly that — every record survives, every
`parameter` is byte-for-byte what Gemini wrote, and the legacy
`RECOMMENDATION_REJECTED` / `PARAMETER_REWRITTEN` codes are never emitted.

The synthetic Phase 2 result here bundles one recommendation in each of the
four check categories:

  1. Valid recommendation — no event.
  2. Unknown device — RECOMMENDATION_UNVERIFIED, reason=device_unknown (kept).
  3a. Near-miss parameter that fuzzy-resolves — kept SILENTLY, no event (fuzzy
      suppresses the warning but never rewrites the parameter).
  3b. Parameter with no close match — RECOMMENDATION_UNVERIFIED,
      reason=parameter_unknown (kept).
  4. Out-of-range value (on a parameter that DOES carry spec.min/max in the
     fixture) — RECOMMENDATION_UNVERIFIED, reason=value_out_of_range (kept).

A fifth case covers the citation check (missing/empty phase1Fields →
RECOMMENDATION_UNVERIFIED, reason=citation_missing, kept).
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

_LEGACY_MUTATING_CODES = ("RECOMMENDATION_REJECTED", "PARAMETER_REWRITTEN")


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


class CatalogueChecksIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalogue = Live12Catalogue.from_path(_THREE_DEVICE_FIXTURE)

    def _apply(self, phase2_result: dict[str, Any], *, request_id: str = "req-test-42"):
        return apply_live12_catalogue_gates(
            phase2_result,
            request_id=request_id,
            catalogue=self.catalogue,
        )

    def _assert_no_legacy_codes(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            self.assertNotIn(event["code"], _LEGACY_MUTATING_CODES)

    # ----- Valid recommendation -----

    def test_valid_recommendation_passes_with_no_event(self):
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

    def test_display_name_device_passes_with_no_event(self):
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

    # ----- Unknown device -----

    def test_unknown_device_is_flagged_and_kept(self):
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
        # Kept — warn-and-keep never drops.
        self.assertEqual(len(phase2["abletonRecommendations"]), 1)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["code"], "RECOMMENDATION_UNVERIFIED")
        self.assertEqual(event["reason"], "device_unknown")
        self.assertEqual(event["device"], "Saturation Color")
        self.assertEqual(event["requestId"], "req-test-42")
        self.assertEqual(event["path"], "abletonRecommendations[0]")

    # ----- Near-miss parameter (fuzzy-resolvable) -----

    def test_fuzzy_resolvable_parameter_is_kept_silently_and_not_rewritten(self):
        # Saturator catalogue has "Drive"; "Drives" fuzzy-resolves to it.
        # Under warn-and-keep that suppresses the warning but MUST NOT rewrite
        # the parameter — the record keeps "Drives" exactly as written.
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
        self.assertEqual(events, [])
        self.assertEqual(len(phase2["abletonRecommendations"]), 1)
        # Critical: parameter is NOT rewritten.
        self.assertEqual(phase2["abletonRecommendations"][0]["parameter"], "Drives")

    def test_parameter_with_no_close_match_is_flagged_and_kept(self):
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
        self.assertEqual(len(phase2["abletonRecommendations"]), 1)
        self.assertEqual(
            phase2["abletonRecommendations"][0]["parameter"], "TotalGarbage"
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["code"], "RECOMMENDATION_UNVERIFIED")
        self.assertEqual(events[0]["reason"], "parameter_unknown")
        self.assertEqual(events[0]["device"], "Saturator")
        self.assertEqual(events[0]["parameter"], "TotalGarbage")

    # ----- Out-of-range value -----

    def test_out_of_range_value_is_flagged_and_kept(self):
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
        self.assertEqual(len(phase2["abletonRecommendations"]), 1)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["code"], "RECOMMENDATION_UNVERIFIED")
        self.assertEqual(event["reason"], "value_out_of_range")
        self.assertEqual(event["device"], "Operator")
        self.assertEqual(event["parameter"], "Volume")
        self.assertEqual(event["value"], "42 dB")

    def test_in_range_value_produces_no_event(self):
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

    def test_range_check_is_inert_when_spec_lacks_bounds(self):
        # Saturator/Drive in the fixture: name only, no min/max -- range check
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

    def test_unparseable_value_produces_no_range_event(self):
        # "auto" cannot be coerced to a number — the check stays silent rather
        # than producing a false-positive warning.
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

    # ----- Citation check -----

    def test_missing_phase1_fields_is_flagged_and_kept(self):
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
        self.assertEqual(len(phase2["abletonRecommendations"]), 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["code"], "RECOMMENDATION_UNVERIFIED")
        self.assertEqual(events[0]["reason"], "citation_missing")
        self.assertEqual(events[0]["path"], "abletonRecommendations[0].phase1Fields")

    def test_whitespace_only_phase1_fields_is_flagged_and_kept(self):
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
        self.assertEqual(len(phase2["abletonRecommendations"]), 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["reason"], "citation_missing")

    # ----- Mixed: all cases at once, everything kept -----

    def test_mixed_recommendations_are_all_kept_with_warnings(self):
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
        # Nothing is dropped — all four survive in their original order.
        self.assertEqual(len(phase2["abletonRecommendations"]), 4)
        # Parameters are never rewritten — index 2 keeps "Drives".
        self.assertEqual(
            [r["parameter"] for r in phase2["abletonRecommendations"]],
            ["Drive", "Drive", "Drives", "Volume"],
        )
        self._assert_no_legacy_codes(events)
        # Only the unknown-device (idx 1) and out-of-range (idx 3) warn; the
        # fuzzy-resolvable "Drives" (idx 2) is kept silently.
        self.assertTrue(all(e["code"] == "RECOMMENDATION_UNVERIFIED" for e in events))
        reasons = sorted(e["reason"] for e in events)
        self.assertEqual(reasons, ["device_unknown", "value_out_of_range"])
        # Paths reference the ORIGINAL indices so the operator log can correlate.
        paths = sorted(e["path"] for e in events)
        self.assertEqual(
            paths,
            ["abletonRecommendations[1]", "abletonRecommendations[3]"],
        )

    # ----- mixAndMasterChain receives the same checks -----

    def test_mix_and_master_chain_is_checked(self):
        phase2 = {
            "mixAndMasterChain": [
                {
                    "order": 1,
                    "device": "Saturator",
                    "deviceFamily": "NATIVE",
                    "trackContext": "Master",
                    "workflowStage": "MASTER",
                    "parameter": "Drives",  # fuzzy-resolvable -> kept silently
                    "value": "3.0",
                    "reason": "test",
                    "phase1Fields": ["bpm"],
                },
                {
                    "order": 2,
                    "device": "Saturation Color",  # unknown device
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
        # Both kept; "Drives" not rewritten.
        self.assertEqual(len(phase2["mixAndMasterChain"]), 2)
        self.assertEqual(phase2["mixAndMasterChain"][0]["parameter"], "Drives")
        self._assert_no_legacy_codes(events)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["code"], "RECOMMENDATION_UNVERIFIED")
        self.assertEqual(events[0]["reason"], "device_unknown")
        self.assertEqual(events[0]["path"], "mixAndMasterChain[1]")

    # ----- secretSauce.workflowSteps -----

    def test_workflow_steps_are_checked(self):
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
                        "parameter": "Drives",  # fuzzy-resolvable -> kept silently
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
        # Both kept; "Drives" not rewritten.
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["parameter"], "Drives")
        self._assert_no_legacy_codes(events)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["code"], "RECOMMENDATION_UNVERIFIED")
        self.assertEqual(events[0]["reason"], "citation_missing")
        self.assertEqual(events[0]["path"], "secretSauce.workflowSteps[1].phase1Fields")

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

    # ----- Regression: EQ-band parameters must never be rewritten -----

    def test_eq_band_parameter_is_never_rewritten_against_real_catalogue(self):
        """Regression for the wrong-band rewrite. Against the real shipped
        catalogue, EQ Eight stores band params as '1 Frequency A' ...
        '8 Frequency B'. A producer's natural phrasing ('Band 1 Frequency')
        lexically fuzzy-matches the WRONG instance ('1 Frequency B' / even
        '8 Frequency B'). Warn-and-keep must leave the parameter byte-for-byte
        as written and never drop the recommendation."""
        catalogue = Live12Catalogue.load_default()
        for phrasing in (
            "Band 1 Frequency",
            "Frequency 1",
            "Frequency",
            "Band 1 Gain",
            "Resonance",
        ):
            with self.subTest(phrasing=phrasing):
                phase2 = {
                    "abletonRecommendations": [
                        _make_recommendation(
                            device="EQ Eight",
                            parameter=phrasing,
                            value="-1.5 dB @ 35 Hz",
                            phase1_fields=["spectralBalance.subBass"],
                        ),
                    ],
                }
                events = apply_live12_catalogue_gates(
                    phase2, request_id="req-eq", catalogue=catalogue
                )
                rec = phase2["abletonRecommendations"][0]
                # Never dropped.
                self.assertEqual(len(phase2["abletonRecommendations"]), 1)
                # Never rewritten — exactly what Gemini wrote.
                self.assertEqual(rec["parameter"], phrasing)
                # Never via a legacy mutating code.
                self._assert_no_legacy_codes(events)

    def test_record_failing_every_check_is_still_kept(self):
        # Unknown device AND missing citation — the worst case. Still kept,
        # with both warnings surfaced.
        phase2 = {
            "abletonRecommendations": [
                _make_recommendation(
                    device="Totally Fake Device",
                    parameter="Whatever",
                    value="1",
                    phase1_fields=[],
                ),
            ],
        }
        events = self._apply(phase2)
        self.assertEqual(len(phase2["abletonRecommendations"]), 1)
        self._assert_no_legacy_codes(events)
        reasons = sorted(e["reason"] for e in events)
        self.assertEqual(reasons, ["citation_missing", "device_unknown"])

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

    def test_opaque_list_entries_are_left_untouched(self):
        phase2 = {
            "abletonRecommendations": [
                "not a record",
                _make_recommendation(device="Saturator", parameter="Drive", value="1"),
            ],
        }
        events = self._apply(phase2)
        # Opaque entry survives untouched; the real record is checked (and OK).
        self.assertEqual(len(phase2["abletonRecommendations"]), 2)
        self.assertEqual(phase2["abletonRecommendations"][0], "not a record")
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

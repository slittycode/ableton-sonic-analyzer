import asyncio
import io
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.responses import JSONResponse
from fastapi import UploadFile

import server


def _make_timeout_expired() -> subprocess.TimeoutExpired:
    error = subprocess.TimeoutExpired(
        cmd=["./venv/bin/python", "analyze.py", "track.mp3", "--yes"],
        timeout=53,
    )
    error.stdout = b"partial stdout"
    error.stderr = b"partial stderr"
    return error


def _timing_points(
    *,
    request_start_ms: int = 0,
    analysis_start_ms: int = 10,
    analysis_end_ms: int = 210,
    response_ready_ms: int = 260,
) -> list[datetime]:
    base = datetime(2026, 3, 8, 12, 0, 0)
    return [
        base + timedelta(milliseconds=request_start_ms),
        base + timedelta(milliseconds=analysis_start_ms),
        base + timedelta(milliseconds=analysis_end_ms),
        base + timedelta(milliseconds=response_ready_ms),
    ]


def _valid_phase2_result() -> dict:
    return {
        "trackCharacter": "Driving techno groove at 128 BPM.",
        "projectSetup": {
            "tempoBpm": 128,
            "timeSignature": "4/4",
            "sampleRate": 48000,
            "bitDepth": 24,
            "headroomTarget": "-6 dB",
            "sessionGoal": "Rebuild a tight, club-focused groove from measured loudness and synthesis cues.",
        },
        "trackLayout": [
            {
                "order": 1,
                "name": "Drum Group",
                "type": "GROUP",
                "purpose": "Anchor the kick and percussion bus.",
                "grounding": {
                    "phase1Fields": ["grooveDetail.kickSwing", "crestFactor"],
                    "segmentIndexes": [1],
                },
            }
        ],
        "routingBlueprint": {
            "sidechainSource": "Kick",
            "sidechainTargets": ["Bass", "Pads"],
            "returns": [
                {
                    "name": "Return A",
                    "purpose": "Short space for upper percussion.",
                    "sendSources": ["Drum Group"],
                    "deviceFocus": "Hybrid Reverb",
                    "levelGuidance": "-18 dB send baseline",
                }
            ],
            "notes": ["Keep sub content dry and centered."],
        },
        "warpGuide": {
            "fullTrack": {
                "warpMode": "Complex Pro",
                "settings": "Formants 100, Envelope 128",
                "reason": "Full mix preservation while checking the measured arrangement.",
            },
            "drums": {
                "warpMode": "Beats",
                "settings": "Preserve Transients",
                "reason": "Transient integrity suits the punchy kick profile.",
            },
            "bass": {
                "warpMode": "Tones",
                "settings": "Grain Size 65",
                "reason": "Keeps sustained bass notes stable.",
            },
            "melodic": {
                "warpMode": "Complex",
                "settings": "Default envelope",
                "reason": "Maintains harmonic material in melodic layers.",
            },
            "rationale": "Use source-appropriate warp modes when rebuilding clips from the measured arrangement.",
        },
        "detectedCharacteristics": [
            {
                "name": "Pumping groove",
                "confidence": "HIGH",
                "explanation": "Kick and bass are tightly coupled.",
            }
        ],
        "arrangementOverview": {
            "summary": "Steady arrangement with a single lift.",
            "segments": [
                {
                    "index": 0,
                    "startTime": 0,
                    "endTime": 16,
                    "lufs": -8.2,
                    "description": "Intro groove.",
                    "spectralNote": "Tight low end.",
                    "sceneName": "INTRO",
                    "abletonAction": "Build the first scene with kick, hat, and filtered bass.",
                    "automationFocus": "Open the filter over the last 4 bars.",
                }
            ],
            "noveltyNotes": "Minimal transitions.",
        },
        "sonicElements": {
            "kick": "Short and punchy.",
            "bass": "Sidechained mono bass.",
            "melodicArp": "Sparse arp layer.",
            "grooveAndTiming": "Rigid 16th-note pulse.",
            "effectsAndTexture": "Light delays and filtered noise.",
            "widthAndStereo": "Mostly centered.",
            "harmonicContent": "Minor-key tension.",
        },
        "mixAndMasterChain": [
            {
                "order": 1,
                "device": "EQ Eight",
                "deviceFamily": "NATIVE",
                "trackContext": "Master",
                "workflowStage": "MIX",
                "parameter": "Band 1 Frequency",
                "value": "-1.5 dB @ 35 Hz",
                "reason": "Tighten sub energy.",
            }
        ],
        "secretSauce": {
            "title": "Breathing low end",
            "icon": "wave",
            "explanation": "Use ducking to exaggerate motion.",
            "implementationSteps": [
                "Insert compressor on bass.",
                "Sidechain from kick.",
            ],
            "workflowSteps": [
                {
                    "step": 1,
                    "trackContext": "Drum Group",
                    "device": "Glue Compressor",
                    "parameter": "Attack",
                    "value": "3 ms",
                    "instruction": "Set up light bus glue before the build opens up.",
                    "measurementJustification": "The measured crest profile supports a controlled transient shape.",
                }
            ],
        },
        "confidenceNotes": [
            {
                "field": "kick",
                "value": "HIGH",
                "reason": "Clear transient profile.",
            }
        ],
        "abletonRecommendations": [
            {
                "device": "Glue Compressor",
                "deviceFamily": "NATIVE",
                "trackContext": "Master",
                "workflowStage": "MIX",
                "category": "DYNAMICS",
                "parameter": "Attack",
                "value": "3 ms",
                "reason": "Keep transients intact.",
                "advancedTip": "Drive lightly.",
            }
        ],
    }


def _valid_audio_observations() -> dict:
    return {
        "soundDesignFingerprint": (
            "The bass reads like an FM-weighted patch with a short envelope and clipped transient edge, "
            "while the tops feel filtered rather than naturally bright."
        ),
        "elementCharacter": [
            {
                "element": "Kick",
                "description": "The transient has a short click up front and a controlled sub tail without a long ring.",
            },
            {
                "element": "Bass",
                "description": "The body feels compact and synthetic, with a rounded sustain that still ducks clearly to the kick.",
            },
        ],
        "productionSignatures": [
            "Pitched delay throws used as a transition accent.",
            "Short gated reverb feel on the upper percussion.",
        ],
        "mixContext": (
            "By ear the mix feels intentionally club-focused rather than lo-fi, with the sub pushed forward and the upper effects kept tidy."
        ),
    }


def _valid_single_stem_summary_result(summary: str = "Bass pulses anchor the section while the upper stem stays approximate.") -> dict:
    return {
        "summary": summary,
        "bars": [
            {
                "barStart": 1,
                "barEnd": 2,
                "startTime": 0.0,
                "endTime": 3.75,
                "noteHypotheses": ["C3 pedal"],
                "scaleDegreeHypotheses": ["1"],
                "rhythmicPattern": "Short off-beat bass pulses.",
                "uncertaintyLevel": "LOW",
                "uncertaintyReason": "Pitch/note translation and measured downbeats agree.",
            }
        ],
        "globalPatterns": {
            "bassRole": "Anchors the groove in the low register.",
            "melodicRole": "Sparse upper-register punctuation.",
            "pumpingOrModulation": "Measured pumping suggests compressor-led movement.",
        },
        "uncertaintyFlags": ["Upper melodic detail is approximate."],
    }


class ServerContractTests(unittest.TestCase):
    def _upload_file(self) -> UploadFile:
        return UploadFile(filename="track.mp3", file=io.BytesIO(b"fake-audio"))

    def _decode_json_response(self, response) -> dict:
        return json.loads(response.body.decode("utf-8"))

    def _request_body_properties(self, path: str) -> dict:
        openapi = server.app.openapi()
        schema_ref = openapi["paths"][path]["post"]["requestBody"]["content"][
            "multipart/form-data"
        ]["schema"]["$ref"]
        schema_name = schema_ref.split("/")[-1]
        return openapi["components"]["schemas"][schema_name]["properties"]

    def test_phase2_prompt_template_loaded(self) -> None:
        self.assertIsInstance(server.PHASE2_PROMPT_TEMPLATE, str)
        self.assertGreater(len(server.PHASE2_PROMPT_TEMPLATE), 100)

    def test_live12_device_catalog_is_loaded(self) -> None:
        self.assertIsInstance(server.LIVE12_DEVICE_CATALOG, dict)
        self.assertGreaterEqual(len(server.LIVE12_DEVICE_CATALOG.get("devices", [])), 16)

    def test_load_live12_device_catalog_raises_when_missing(self) -> None:
        missing_path = Path("/tmp/asa-missing-live12-catalog.json")
        with self.assertRaisesRegex(RuntimeError, "not found"):
            server._load_live12_device_catalog(missing_path)

    def test_load_live12_device_catalog_raises_on_empty_devices(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_live12_catalog_") as temp_dir:
            catalog_path = Path(temp_dir) / "catalog.json"
            catalog_path.write_text(json.dumps({"devices": []}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "devices"):
                server._load_live12_device_catalog(catalog_path)

    def test_build_phase2_prompt_includes_live12_catalog_json(self) -> None:
        prompt = server._build_phase2_prompt(
            measurement_result={"bpm": 128},
            pitch_note_result=None,
            grounding_metadata={"profileId": "producer_summary"},
            descriptor_hooks=None,
        )

        self.assertIn("LIVE_12_DEVICE_CATALOG_JSON", prompt)
        self.assertIn('"devices"', prompt)

    def test_build_phase2_prompt_includes_audio_observations_instructions(self) -> None:
        prompt = server._build_phase2_prompt(
            measurement_result={"bpm": 128, "durationSeconds": 180},
            pitch_note_result=None,
            grounding_metadata={"profileId": "producer_summary"},
            descriptor_hooks=None,
        )

        self.assertIn("audioObservations", prompt)
        self.assertIn("sound design fingerprinting", prompt)
        self.assertIn("production technique signatures", prompt)
        self.assertIn("must not repeat or restate content already covered", prompt)
        self.assertIn("Do not omit any required top-level keys", prompt)
        self.assertIn("Only audioObservations may be omitted", prompt)
        self.assertIn("category must be exactly one of", prompt)
        self.assertIn("workflowStage = the project phase", prompt)
        self.assertIn('"workflowStage":"SOUND_DESIGN","category":"SYNTHESIS"', prompt)
        self.assertIn("Return:<name> with no space after the colon", prompt)

    def test_parse_phase2_result_keeps_valid_audio_observations(self) -> None:
        payload = _valid_phase2_result()
        payload["audioObservations"] = _valid_audio_observations()

        parsed, skip_message = server._parse_phase2_result(json.dumps(payload))

        self.assertIsNone(skip_message)
        self.assertIsNotNone(parsed)
        self.assertEqual(
            parsed["audioObservations"]["soundDesignFingerprint"],
            payload["audioObservations"]["soundDesignFingerprint"],
        )
        self.assertEqual(
            parsed["audioObservations"]["elementCharacter"][0]["element"],
            "Kick",
        )

    def test_parse_phase2_result_allows_missing_audio_observations(self) -> None:
        parsed, skip_message = server._parse_phase2_result(json.dumps(_valid_phase2_result()))

        self.assertIsNone(skip_message)
        self.assertIsNotNone(parsed)
        self.assertNotIn("audioObservations", parsed)

    def test_parse_phase2_result_drops_malformed_audio_observations_only(self) -> None:
        payload = _valid_phase2_result()
        payload["audioObservations"] = {
            "soundDesignFingerprint": "Compact FM-like bass contour.",
            "elementCharacter": "not-an-array",
            "productionSignatures": ["Short reverb tails."],
            "mixContext": "Club-focused low end.",
        }

        parsed, skip_message = server._parse_phase2_result(json.dumps(payload))

        self.assertIsNone(skip_message)
        self.assertIsNotNone(parsed)
        self.assertNotIn("audioObservations", parsed)
        self.assertEqual(parsed["projectSetup"]["sampleRate"], 48000)

    def test_parse_phase2_result_debug_coerces_synthesis_workflow_stage(self) -> None:
        payload = _valid_phase2_result()
        payload["abletonRecommendations"][0]["workflowStage"] = "SYNTHESIS"

        debug = server._parse_phase2_result_debug(json.dumps(payload))

        self.assertIsNone(debug["skipReason"])
        self.assertIsNotNone(debug["result"])
        self.assertEqual(
            debug["result"]["abletonRecommendations"][0]["workflowStage"],
            "SOUND_DESIGN",
        )
        self.assertEqual(
            debug["validationWarnings"],
            [
                {
                    "code": "COERCED_ENUM_VALUE",
                    "path": "abletonRecommendations[0].workflowStage",
                    "message": (
                        "Coerced workflowStage 'SYNTHESIS' to 'SOUND_DESIGN' for "
                        "abletonRecommendations."
                    ),
                    "originalValue": "SYNTHESIS",
                    "coercedValue": "SOUND_DESIGN",
                }
            ],
        )

    def test_parse_phase2_result_debug_coerces_return_track_context_spacing(self) -> None:
        payload = _valid_phase2_result()
        payload["routingBlueprint"]["returns"][0]["name"] = "Long Reverb"
        payload["mixAndMasterChain"][0]["trackContext"] = "Return: Long Reverb"
        payload["abletonRecommendations"][0]["trackContext"] = "Return: Long Reverb"
        payload["secretSauce"]["workflowSteps"][0]["trackContext"] = "Return: Long Reverb"

        debug = server._parse_phase2_result_debug(json.dumps(payload))

        self.assertIsNone(debug["skipReason"])
        self.assertIsNotNone(debug["result"])
        self.assertEqual(debug["result"]["mixAndMasterChain"][0]["trackContext"], "Return:Long Reverb")
        self.assertEqual(
            debug["result"]["abletonRecommendations"][0]["trackContext"],
            "Return:Long Reverb",
        )
        self.assertEqual(
            debug["result"]["secretSauce"]["workflowSteps"][0]["trackContext"],
            "Return:Long Reverb",
        )
        warning_paths = {warning["path"] for warning in debug["validationWarnings"]}
        self.assertIn("mixAndMasterChain[0].trackContext", warning_paths)
        self.assertIn("abletonRecommendations[0].trackContext", warning_paths)
        self.assertIn("secretSauce.workflowSteps[0].trackContext", warning_paths)

    def test_parse_phase2_result_debug_repairs_abbreviated_return_name(self) -> None:
        payload = _valid_phase2_result()
        payload["routingBlueprint"]["returns"][0]["name"] = "Long Reverb"
        payload["mixAndMasterChain"][0]["trackContext"] = "Return:Reverb"
        payload["abletonRecommendations"][0]["trackContext"] = "Return:Reverb"
        payload["secretSauce"]["workflowSteps"][0]["trackContext"] = "Return:Reverb"

        debug = server._parse_phase2_result_debug(json.dumps(payload))

        self.assertIsNone(debug["skipReason"])
        self.assertEqual(debug["result"]["mixAndMasterChain"][0]["trackContext"], "Return:Long Reverb")
        self.assertEqual(debug["result"]["abletonRecommendations"][0]["trackContext"], "Return:Long Reverb")
        self.assertEqual(
            debug["result"]["secretSauce"]["workflowSteps"][0]["trackContext"],
            "Return:Long Reverb",
        )
        coerced = [w for w in debug["validationWarnings"] if w["code"] == "COERCED_TRACK_CONTEXT"]
        self.assertEqual(len(coerced), 3)

    def test_parse_phase2_result_debug_repairs_case_insensitive_return_name(self) -> None:
        payload = _valid_phase2_result()
        payload["routingBlueprint"]["returns"][0]["name"] = "Long Reverb"
        payload["mixAndMasterChain"][0]["trackContext"] = "Return:long reverb"

        debug = server._parse_phase2_result_debug(json.dumps(payload))

        self.assertIsNone(debug["skipReason"])
        self.assertEqual(debug["result"]["mixAndMasterChain"][0]["trackContext"], "Return:Long Reverb")
        coerced = [w for w in debug["validationWarnings"] if w["code"] == "COERCED_TRACK_CONTEXT"]
        self.assertTrue(len(coerced) >= 1)

    def test_parse_phase2_result_debug_no_repair_when_ambiguous_substring(self) -> None:
        payload = _valid_phase2_result()
        payload["routingBlueprint"]["returns"] = [
            {
                "name": "Long Reverb",
                "purpose": "Spatial depth.",
                "sendSources": ["Drum Group"],
                "deviceFocus": "Hybrid Reverb",
                "levelGuidance": "-18 dB send baseline",
            },
            {
                "name": "Short Reverb",
                "purpose": "Tight space.",
                "sendSources": ["Drum Group"],
                "deviceFocus": "Reverb",
                "levelGuidance": "-12 dB send baseline",
            },
        ]
        payload["mixAndMasterChain"][0]["trackContext"] = "Return:Reverb"

        debug = server._parse_phase2_result_debug(json.dumps(payload))

        self.assertIsNone(debug["skipReason"])
        # No repair — ambiguous match, value stays as-is
        self.assertEqual(debug["result"]["mixAndMasterChain"][0]["trackContext"], "Return:Reverb")
        coerced = [w for w in debug["validationWarnings"] if w["code"] == "COERCED_TRACK_CONTEXT"]
        # No coercion warning from the repair pass for this field
        coerced_mix = [w for w in coerced if "mixAndMasterChain" in w["path"]]
        self.assertEqual(len(coerced_mix), 0)

    def test_parse_phase2_result_debug_no_repair_when_exact_match_exists(self) -> None:
        payload = _valid_phase2_result()
        payload["routingBlueprint"]["returns"][0]["name"] = "Reverb"
        payload["mixAndMasterChain"][0]["trackContext"] = "Return:Reverb"

        debug = server._parse_phase2_result_debug(json.dumps(payload))

        self.assertIsNone(debug["skipReason"])
        self.assertEqual(debug["result"]["mixAndMasterChain"][0]["trackContext"], "Return:Reverb")
        coerced = [w for w in debug["validationWarnings"] if w["code"] == "COERCED_TRACK_CONTEXT"]
        coerced_mix = [w for w in coerced if "mixAndMasterChain" in w["path"]]
        self.assertEqual(len(coerced_mix), 0)

    def test_parse_phase2_result_debug_repairs_after_spacing_normalization(self) -> None:
        payload = _valid_phase2_result()
        payload["routingBlueprint"]["returns"][0]["name"] = "Long Reverb"
        # Space after colon AND abbreviated — both normalizers should chain
        payload["mixAndMasterChain"][0]["trackContext"] = "Return: Reverb"

        debug = server._parse_phase2_result_debug(json.dumps(payload))

        self.assertIsNone(debug["skipReason"])
        self.assertEqual(debug["result"]["mixAndMasterChain"][0]["trackContext"], "Return:Long Reverb")
        coerced = [w for w in debug["validationWarnings"] if w["code"] == "COERCED_TRACK_CONTEXT"]
        coerced_mix = [w for w in coerced if "mixAndMasterChain" in w["path"]]
        # Two coercion warnings: spacing fix + fuzzy repair
        self.assertEqual(len(coerced_mix), 2)

    def test_parse_phase2_result_drops_single_invalid_ableton_recommendation_item(self) -> None:
        payload = _valid_phase2_result()
        payload["abletonRecommendations"].append(
            {
                "device": "Glue Compressor",
                "deviceFamily": "NATIVE",
                "trackContext": "Master",
                "workflowStage": "PATCHING",
                "category": "DYNAMICS",
                "parameter": "Attack",
                "value": "3 ms",
                "reason": "Bad enum should drop this one item.",
                "advancedTip": "Ignore this card.",
            }
        )

        debug = server._parse_phase2_result_debug(json.dumps(payload))

        self.assertIsNone(debug["skipReason"])
        self.assertIsNotNone(debug["result"])
        self.assertEqual(len(debug["result"]["abletonRecommendations"]), 1)
        warning = next(
            warning
            for warning in debug["validationWarnings"]
            if warning["code"] == "DROPPED_INVALID_ARRAY_ITEM"
        )
        self.assertEqual(warning["path"], "abletonRecommendations[1]")
        self.assertIn("workflowStage", warning["dropReason"])
        self.assertIn('"workflowStage": "PATCHING"', warning["originalValue"])

    def test_parse_phase2_result_drops_single_invalid_mix_chain_item(self) -> None:
        payload = _valid_phase2_result()
        payload["mixAndMasterChain"].append(
            {
                "order": 2,
                "device": "EQ Eight",
                "deviceFamily": "NATIVE",
                "trackContext": "Master",
                "workflowStage": "PATCHING",
                "parameter": "Band 1 Frequency",
                "value": "-1 dB @ 45 Hz",
                "reason": "Bad stage should drop this one item.",
            }
        )

        debug = server._parse_phase2_result_debug(json.dumps(payload))

        self.assertIsNone(debug["skipReason"])
        self.assertIsNotNone(debug["result"])
        self.assertEqual(len(debug["result"]["mixAndMasterChain"]), 1)
        warning = next(
            warning
            for warning in debug["validationWarnings"]
            if warning["code"] == "DROPPED_INVALID_ARRAY_ITEM"
            and warning["path"] == "mixAndMasterChain[1]"
        )
        self.assertIn("workflowStage", warning["dropReason"])
        self.assertIn('"workflowStage": "PATCHING"', warning["originalValue"])

    def test_parse_phase2_result_skips_when_required_recommendation_array_is_emptied(self) -> None:
        payload = _valid_phase2_result()
        payload["abletonRecommendations"] = [
            {
                "device": "Glue Compressor",
                "deviceFamily": "NATIVE",
                "trackContext": "Master",
                "workflowStage": "PATCHING",
                "category": "DYNAMICS",
                "parameter": "Attack",
                "value": "3 ms",
                "reason": "This only card should be dropped.",
                "advancedTip": "Ignore this card.",
            }
        ]

        debug = server._parse_phase2_result_debug(json.dumps(payload))

        self.assertEqual(debug["skipReason"], "invalid_shape")
        self.assertIsNone(debug["result"])
        paths = {issue["path"] for issue in debug["shapeIssues"]}
        self.assertIn("abletonRecommendations", paths)
        warning = next(
            warning
            for warning in debug["validationWarnings"]
            if warning["code"] == "DROPPED_INVALID_ARRAY_ITEM"
        )
        self.assertEqual(warning["path"], "abletonRecommendations[0]")
        self.assertIn("workflowStage", warning["dropReason"])

    def test_parse_phase2_result_debug_reports_invalid_shape_paths(self) -> None:
        payload = _valid_phase2_result()
        payload["projectSetup"] = "wrong-type"
        payload["warpGuide"]["drums"]["warpMode"] = "Warped"
        payload["arrangementOverview"]["segments"][0].pop("sceneName")

        debug = server._parse_phase2_result_debug(json.dumps(payload))

        self.assertEqual(debug["skipReason"], "invalid_shape")
        self.assertIsNone(debug["result"])
        self.assertGreaterEqual(len(debug["shapeIssues"]), 3)
        paths = {issue["path"] for issue in debug["shapeIssues"]}
        self.assertIn("projectSetup", paths)
        self.assertIn("warpGuide.drums.warpMode", paths)
        self.assertIn("arrangementOverview.segments[0].sceneName", paths)

    def test_run_interpretation_request_with_profile_config_surfaces_salvage_warnings_in_normal_diagnostics(
        self,
    ) -> None:
        payload = _valid_phase2_result()
        payload["abletonRecommendations"][0]["workflowStage"] = "SYNTHESIS"
        mock_response = unittest.mock.MagicMock()
        mock_response.text = json.dumps(payload)
        mock_model = unittest.mock.MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_client = unittest.mock.MagicMock()
        mock_client.models = mock_model
        with tempfile.TemporaryDirectory(prefix="asa_phase2_salvage_") as temp_dir:
            audio_path = Path(temp_dir) / "track.wav"
            audio_path.write_bytes(b"fake-audio")
            profile_config = server._resolve_interpretation_profile_config("producer_summary")
            with (
                patch.object(server, "_GENAI_AVAILABLE", True),
                patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
                patch.object(server, "_genai") as mock_genai,
                patch.object(server, "_genai_types") as mock_genai_types,
            ):
                mock_genai.Client.return_value = mock_client
                mock_genai_types.GenerateContentConfig.return_value = unittest.mock.MagicMock()
                execution = server._run_interpretation_request_with_profile_config(
                    source_path=str(audio_path),
                    filename=audio_path.name,
                    file_size_bytes=audio_path.stat().st_size,
                    profile_id="producer_summary",
                    profile_config=profile_config,
                    measurement_result={"bpm": 128},
                    pitch_note_result=None,
                    grounding_metadata={"profileId": "producer_summary"},
                    model_name="gemini-3.1-pro-preview",
                    request_id="normal-salvage-test",
                )

        self.assertTrue(execution["ok"])
        self.assertIsNotNone(execution["interpretationResult"])
        self.assertEqual(
            execution["interpretationResult"]["abletonRecommendations"][0]["workflowStage"],
            "SOUND_DESIGN",
        )
        warnings = execution["diagnostics"]["validationWarnings"]
        self.assertEqual(warnings[0]["code"], "COERCED_ENUM_VALUE")
        self.assertEqual(warnings[0]["originalValue"], "SYNTHESIS")
        self.assertEqual(warnings[0]["coercedValue"], "SOUND_DESIGN")

    def test_resolve_server_port_defaults_to_8100(self) -> None:
        with patch.dict(server.os.environ, {}, clear=True):
            self.assertEqual(server.resolve_server_port(), 8100)

    def test_resolve_server_port_uses_env_override(self) -> None:
        with patch.dict(server.os.environ, {"SONIC_ANALYZER_PORT": "8456"}, clear=True):
            self.assertEqual(server.resolve_server_port(), 8456)

    def test_analyze_endpoint_openapi_contract_exposes_separate_form_field(
        self,
    ) -> None:
        properties = self._request_body_properties("/api/analyze")

        self.assertIn("track", properties)
        self.assertIn("transcribe", properties)
        self.assertIn("separate", properties)

    def test_estimate_endpoint_openapi_contract_exposes_separate_form_field(
        self,
    ) -> None:
        properties = self._request_body_properties("/api/analyze/estimate")

        self.assertIn("track", properties)
        self.assertIn("analysis_mode", properties)
        self.assertIn("transcribe", properties)
        self.assertIn("separate", properties)

    def test_analysis_runs_endpoint_openapi_contract_exposes_stage_request_fields(
        self,
    ) -> None:
        properties = self._request_body_properties("/api/analysis-runs")

        self.assertIn("track", properties)
        self.assertIn("analysis_mode", properties)
        self.assertIn("pitch_note_mode", properties)
        self.assertIn("pitch_note_backend", properties)
        self.assertIn("interpretation_mode", properties)
        self.assertIn("interpretation_profile", properties)
        self.assertIn("interpretation_model", properties)

    def test_analysis_runs_estimate_endpoint_openapi_contract_exposes_stage_request_fields(
        self,
    ) -> None:
        properties = self._request_body_properties("/api/analysis-runs/estimate")

        self.assertIn("track", properties)
        self.assertIn("analysis_mode", properties)
        self.assertIn("pitch_note_mode", properties)
        self.assertIn("pitch_note_backend", properties)
        self.assertIn("interpretation_mode", properties)
        self.assertIn("interpretation_profile", properties)
        self.assertIn("interpretation_model", properties)

    def test_analysis_runs_endpoint_returns_canonical_stage_snapshot(self) -> None:
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_server_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            with patch.object(server, "get_analysis_runtime", return_value=runtime):
                response = asyncio.run(
                    server.create_analysis_run(
                        track=self._upload_file(),
                        analysis_mode="standard",
                        pitch_note_mode="stem_notes",
                        pitch_note_backend="auto",
                        interpretation_mode="async",
                        interpretation_profile="producer_summary",
                        interpretation_model="gemini-2.5-flash",
                    )
                )

        payload = self._decode_json_response(response)
        self.assertEqual(response.status_code, 200)
        self.assertIn("runId", payload)
        self.assertEqual(payload["requestedStages"]["analysisMode"], "standard")
        self.assertEqual(payload["stages"]["measurement"]["status"], "queued")
        self.assertEqual(payload["stages"]["pitchNoteTranslation"]["status"], "blocked")
        self.assertEqual(payload["stages"]["interpretation"]["status"], "blocked")

    @patch.object(server, "get_audio_duration_seconds", return_value=214.6, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 214.6,
            "totalSeconds": {"min": 107, "max": 203},
            "stages": [
                {
                    "key": "dsp",
                    "label": "DSP analysis",
                    "seconds": {"min": 22, "max": 38},
                },
                {
                    "key": "separation",
                    "label": "Demucs separation",
                    "seconds": {"min": 45, "max": 90},
                },
                {
                    "key": "transcription_stems",
                    "label": "Torchcrepe on bass + other stems",
                    "seconds": {"min": 40, "max": 75},
                },
            ],
        },
        create=True,
    )
    def test_analysis_runs_estimate_endpoint_uses_staged_request_fields(
        self, build_estimate_mock, *_mocks
    ) -> None:
        response = asyncio.run(
            server.estimate_analysis_run(
                track=self._upload_file(),
                analysis_mode="standard",
                pitch_note_mode="stem_notes",
                pitch_note_backend="auto",
                interpretation_mode="async",
                interpretation_profile="producer_summary",
                interpretation_model="gemini-2.5-flash",
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = self._decode_json_response(response)
        self.assertEqual(payload["estimate"]["totalLowMs"], 107000)
        self.assertEqual(
            [stage["key"] for stage in payload["estimate"]["stages"]],
            ["local_dsp", "demucs_separation", "transcription_stems"],
        )
        build_estimate_mock.assert_called_once_with(214.6, True, True, run_standard=True)

    def test_analysis_runs_estimate_rejects_unknown_pitch_note_mode(self) -> None:
        response = asyncio.run(
            server.estimate_analysis_run(
                track=self._upload_file(),
                pitch_note_mode="invalid_mode",
                pitch_note_backend="auto",
                interpretation_mode="off",
                interpretation_profile="producer_summary",
                interpretation_model=None,
            )
        )

        self.assertEqual(response.status_code, 400)
        payload = self._decode_json_response(response)
        self.assertEqual(payload["error"]["code"], "PITCH_NOTE_MODE_UNSUPPORTED")
        self.assertIn("invalid_mode", payload["error"]["message"])

    def test_analysis_runs_estimate_rejects_unknown_pitch_note_backend(self) -> None:
        response = asyncio.run(
            server.estimate_analysis_run(
                track=self._upload_file(),
                pitch_note_mode="stem_notes",
                pitch_note_backend="mystery-backend",
                interpretation_mode="off",
                interpretation_profile="producer_summary",
                interpretation_model=None,
            )
        )

        self.assertEqual(response.status_code, 400)
        payload = self._decode_json_response(response)
        self.assertEqual(payload["error"]["code"], "PITCH_NOTE_BACKEND_UNSUPPORTED")
        self.assertIn("mystery-backend", payload["error"]["message"])

    def test_analysis_runs_endpoint_rejects_unknown_pitch_note_backend(self) -> None:
        response = asyncio.run(
            server.create_analysis_run(
                track=self._upload_file(),
                pitch_note_mode="stem_notes",
                pitch_note_backend="mystery-backend",
                interpretation_mode="off",
                interpretation_profile="producer_summary",
                interpretation_model=None,
            )
        )

        self.assertEqual(response.status_code, 400)
        payload = self._decode_json_response(response)
        self.assertEqual(payload["error"]["code"], "PITCH_NOTE_BACKEND_UNSUPPORTED")
        self.assertIn("mystery-backend", payload["error"]["message"])

    def test_analysis_runs_estimate_rejects_unknown_interpretation_profile(self) -> None:
        response = asyncio.run(
            server.estimate_analysis_run(
                track=self._upload_file(),
                pitch_note_mode="off",
                pitch_note_backend="auto",
                interpretation_mode="async",
                interpretation_profile="nonexistent_profile",
                interpretation_model=None,
            )
        )

        self.assertEqual(response.status_code, 400)
        payload = self._decode_json_response(response)
        self.assertEqual(payload["error"]["code"], "INTERPRETATION_PROFILE_UNSUPPORTED")
        self.assertIn("nonexistent_profile", payload["error"]["message"])

    def test_analysis_runs_endpoint_accepts_stem_summary_profile(self) -> None:
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_server_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            with patch.object(server, "get_analysis_runtime", return_value=runtime):
                response = asyncio.run(
                    server.create_analysis_run(
                        track=self._upload_file(),
                        pitch_note_mode="off",
                        pitch_note_backend="auto",
                        interpretation_mode="async",
                        interpretation_profile="stem_summary",
                        interpretation_model="gemini-2.5-flash",
                    )
                )

        payload = self._decode_json_response(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["requestedStages"]["interpretationProfile"], "stem_summary")

    def test_get_analysis_run_returns_persisted_stage_snapshot(self) -> None:
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_server_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            created = runtime.create_run(
                filename="track.mp3",
                content=b"fake-audio",
                mime_type="audio/mpeg",
                pitch_note_mode="off",
                pitch_note_backend="auto",
                interpretation_mode="off",
                interpretation_profile="producer_summary",
                interpretation_model=None,
            )
            with patch.object(server, "get_analysis_runtime", return_value=runtime):
                response = asyncio.run(server.get_analysis_run(created["runId"]))

        payload = self._decode_json_response(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["runId"], created["runId"])
        self.assertIn("artifacts", payload)

    def test_interrupt_analysis_run_marks_stages_interrupted_and_reports_terminated_children(self) -> None:
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_server_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            created = runtime.create_run(
                filename="track.mp3",
                content=b"fake-audio",
                mime_type="audio/mpeg",
                analysis_mode="full",
                pitch_note_mode="stem_notes",
                pitch_note_backend="auto",
                interpretation_mode="async",
                interpretation_profile="producer_summary",
                interpretation_model="gemini-2.5-flash",
            )
            with patch.object(server, "get_analysis_runtime", return_value=runtime), patch.object(
                server,
                "_interrupt_active_child_processes",
                return_value=["measurement", "pitchNoteTranslation"],
            ):
                response = asyncio.run(server.interrupt_analysis_run(created["runId"]))

        payload = self._decode_json_response(response)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["stages"]["measurement"]["status"], "interrupted")
        self.assertEqual(payload["stages"]["pitchNoteTranslation"]["status"], "interrupted")
        self.assertEqual(payload["stages"]["interpretation"]["status"], "interrupted")
        self.assertEqual(
            payload["interrupt"]["stagesTerminated"],
            ["measurement", "pitchNoteTranslation"],
        )

    @patch.object(server, "get_audio_duration_seconds", return_value=214.6, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 214.6,
            "totalSeconds": {"min": 107, "max": 203},
            "stages": [
                {
                    "key": "dsp",
                    "label": "DSP analysis",
                    "seconds": {"min": 22, "max": 38},
                },
                {
                    "key": "separation",
                    "label": "Demucs separation",
                    "seconds": {"min": 45, "max": 90},
                },
                {
                    "key": "transcription_stems",
                    "label": "Torchcrepe on bass + other stems",
                    "seconds": {"min": 40, "max": 75},
                },
            ],
        },
        create=True,
    )
    def test_estimate_endpoint_combines_separate_and_transcribe_flags(
        self, build_estimate_mock, *_mocks
    ) -> None:
        response = asyncio.run(
            server.estimate_analysis(
                track=self._upload_file(),
                dsp_json_override=None,
                transcribe=True,
                separate=True,
                separate_query=False,
                separate_flag=False,
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = self._decode_json_response(response)
        self.assertEqual(payload["estimate"]["totalLowMs"], 107000)
        self.assertEqual(
            [stage["key"] for stage in payload["estimate"]["stages"]],
            ["local_dsp", "demucs_separation", "transcription_stems"],
        )
        build_estimate_mock.assert_called_once_with(214.6, True, True)

    @patch.object(server, "get_audio_duration_seconds", return_value=214.6, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 214.6,
            "totalSeconds": {"min": 107, "max": 203},
            "stages": [
                {
                    "key": "dsp",
                    "label": "DSP analysis",
                    "seconds": {"min": 22, "max": 38},
                },
                {
                    "key": "separation",
                    "label": "Demucs separation",
                    "seconds": {"min": 45, "max": 90},
                },
                {
                    "key": "transcription_stems",
                    "label": "Torchcrepe on bass + other stems",
                    "seconds": {"min": 40, "max": 75},
                },
            ],
        },
        create=True,
    )
    @patch.object(
        server.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            args=[
                "./venv/bin/python",
                "analyze.py",
                "track.mp3",
                "--yes",
                "--separate",
                "--transcribe",
            ],
            returncode=0,
            stdout=json.dumps(
                {
                    "bpm": 128,
                    "bpmConfidence": 0.92,
                    "key": "A minor",
                    "keyConfidence": 0.88,
                    "timeSignature": "4/4",
                    "durationSeconds": 214.6,
                    "lufsIntegrated": -8.2,
                    "truePeak": -0.1,
                    "stereoDetail": {
                        "stereoWidth": 0.74,
                        "stereoCorrelation": 0.82,
                    },
                    "spectralBalance": {
                        "subBass": -0.6,
                        "lowBass": 1.0,
                        "lowMids": 0.0,
                        "mids": -0.2,
                        "upperMids": 0.3,
                        "highs": 0.9,
                        "brilliance": 0.7,
                    },
                    "melodyDetail": None,
                    "transcriptionDetail": None,
                }
            ),
            stderr="",
        ),
    )
    def test_analyze_endpoint_combines_separate_and_transcribe_in_subprocess(
        self, run_mock, build_estimate_mock, *_mocks
    ) -> None:
        with (
            patch.object(
                server,
                "_current_time",
                side_effect=_timing_points(response_ready_ms=245),
                create=True,
            ),
            patch("builtins.print") as print_mock,
        ):
            response = asyncio.run(
                server.analyze_audio(
                    track=self._upload_file(),
                    dsp_json_override=None,
                    transcribe=True,
                    separate=True,
                    separate_query=False,
                    separate_flag=False,
                    fast=False,
                    fast_query=False,
                )
            )

        self.assertEqual(response.status_code, 200)
        command = run_mock.call_args.args[0]
        self.assertEqual(
            command,
            [
                "./venv/bin/python",
                "analyze.py",
                unittest.mock.ANY,
                "--yes",
                "--separate",
            ],
        )
        self.assertEqual(run_mock.call_args.kwargs["timeout"], 526)
        build_estimate_mock.assert_called_once_with(214.6, True, False)
        payload = self._decode_json_response(response)
        self.assertEqual(payload["diagnostics"]["backendDurationMs"], 200.0)
        self.assertEqual(
            payload["diagnostics"]["timings"],
            {
                "totalMs": 245.0,
                "analysisMs": 200.0,
                "serverOverheadMs": 45.0,
                "flagsUsed": ["--separate"],
                "fileSizeBytes": 10,
                "fileDurationSeconds": 214.6,
                "msPerSecondOfAudio": 0.93,
            },
        )
        timing_calls = [
            c
            for c in print_mock.call_args_list
            if c.args and "[TIMING]" in str(c.args[0])
        ]
        self.assertEqual(len(timing_calls), 1)
        timing_call = timing_calls[0]
        self.assertIs(timing_call.kwargs["file"], server.sys.stderr)
        self.assertIn(
            "[TIMING] total=245.0ms analysis=200.0ms overhead=45.0ms",
            timing_call.args[0],
        )
        self.assertIn("flags=[--separate]", timing_call.args[0])
        self.assertIn(
            "fileSize=0.0MB duration=214.6s ms/s=0.93", timing_call.args[0]
        )

    def test_analyze_endpoint_openapi_exposes_fast_form_field(self) -> None:
        properties = self._request_body_properties("/api/analyze")
        self.assertIn("fast", properties)

    @patch.object(server, "get_audio_duration_seconds", return_value=60.0, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 60.0,
            "totalSeconds": {"min": 10, "max": 20},
            "stages": [{"key": "dsp", "label": "DSP analysis", "seconds": {"min": 10, "max": 20}}],
        },
        create=True,
    )
    @patch.object(
        server.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            args=["./venv/bin/python", "analyze.py", "track.mp3", "--yes", "--fast"],
            returncode=0,
            stdout=json.dumps({
                "bpm": 128, "bpmConfidence": 0.9, "key": "C major", "keyConfidence": 0.8,
                "timeSignature": "4/4", "durationSeconds": 60.0,
                "lufsIntegrated": -8.0, "truePeak": -0.5,
                "stereoDetail": {"stereoWidth": 0.5, "stereoCorrelation": 0.9},
                "spectralBalance": {"subBass": 0.0, "lowBass": 0.0, "lowMids": 0.0, "mids": 0.0, "upperMids": 0.0, "highs": 0.0, "brilliance": 0.0},
                "melodyDetail": None, "transcriptionDetail": None,
            }),
            stderr="",
        ),
    )
    def test_analyze_endpoint_passes_fast_flag_to_subprocess(
        self, run_mock, *_mocks
    ) -> None:
        with (
            patch.object(server, "_current_time", side_effect=_timing_points(), create=True),
            patch("builtins.print"),
        ):
            response = asyncio.run(
                server.analyze_audio(
                    track=self._upload_file(),
                    dsp_json_override=None,
                    transcribe=False,
                    separate=False,
                    separate_query=False,
                    separate_flag=False,
                    fast=True,
                    fast_query=False,
                )
            )

        self.assertEqual(response.status_code, 200)
        command = run_mock.call_args.args[0]
        self.assertIn("--fast", command)
        payload = self._decode_json_response(response)
        self.assertIn("--fast", payload["diagnostics"]["timings"]["flagsUsed"])

    @patch.object(server, "get_audio_duration_seconds", return_value=60.0, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 60.0,
            "totalSeconds": {"min": 10, "max": 20},
            "stages": [{"key": "dsp", "label": "DSP analysis", "seconds": {"min": 10, "max": 20}}],
        },
        create=True,
    )
    @patch.object(
        server.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            args=["./venv/bin/python", "analyze.py", "track.mp3", "--yes"],
            returncode=0,
            stdout=json.dumps({
                "bpm": 128, "bpmConfidence": 0.9, "key": "C major", "keyConfidence": 0.8,
                "timeSignature": "4/4", "durationSeconds": 60.0,
                "lufsIntegrated": -8.0, "truePeak": -0.5,
                "stereoDetail": {"stereoWidth": 0.5, "stereoCorrelation": 0.9},
                "spectralBalance": {"subBass": 0.0, "lowBass": 0.0, "lowMids": 0.0, "mids": 0.0, "upperMids": 0.0, "highs": 0.0, "brilliance": 0.0},
                "melodyDetail": None, "transcriptionDetail": None,
            }),
            stderr="",
        ),
    )
    def test_analyze_endpoint_does_not_pass_fast_when_false(
        self, run_mock, *_mocks
    ) -> None:
        with (
            patch.object(server, "_current_time", side_effect=_timing_points(), create=True),
            patch("builtins.print"),
        ):
            response = asyncio.run(
                server.analyze_audio(
                    track=self._upload_file(),
                    dsp_json_override=None,
                    transcribe=False,
                    separate=False,
                    separate_query=False,
                    separate_flag=False,
                    fast=False,
                    fast_query=False,
                )
            )

        self.assertEqual(response.status_code, 200)
        command = run_mock.call_args.args[0]
        self.assertNotIn("--fast", command)
        payload = self._decode_json_response(response)
        self.assertNotIn("--fast", payload["diagnostics"]["timings"]["flagsUsed"])

    @patch.object(server, "get_audio_duration_seconds", return_value=60.0, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 60.0,
            "totalSeconds": {"min": 10, "max": 20},
            "stages": [{"key": "dsp", "label": "DSP analysis", "seconds": {"min": 10, "max": 20}}],
        },
        create=True,
    )
    @patch.object(
        server.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            args=["./venv/bin/python", "analyze.py", "track.mp3", "--yes"],
            returncode=0,
            stdout=json.dumps(
                {
                    "bpm": 128,
                    "bpmConfidence": 0.9,
                    "key": "C major",
                    "keyConfidence": 0.8,
                    "timeSignature": "4/4",
                    "timeSignatureSource": "assumed_four_four",
                    "timeSignatureConfidence": 0.0,
                    "durationSeconds": 60.0,
                    "lufsIntegrated": -8.0,
                    "truePeak": -0.5,
                    "stereoDetail": {"stereoWidth": 0.5, "stereoCorrelation": 0.9},
                    "spectralBalance": {
                        "subBass": 0.0,
                        "lowBass": 0.0,
                        "lowMids": 0.0,
                        "mids": 0.0,
                        "upperMids": 0.0,
                        "highs": 0.0,
                        "brilliance": 0.0,
                    },
                    "melodyDetail": None,
                    "transcriptionDetail": None,
                }
            ),
            stderr="",
        ),
    )
    def test_analyze_endpoint_forwards_time_signature_source_and_confidence(
        self, *_mocks
    ) -> None:
        with (
            patch.object(server, "_current_time", side_effect=_timing_points(), create=True),
            patch("builtins.print"),
        ):
            response = asyncio.run(
                server.analyze_audio(
                    track=self._upload_file(),
                    dsp_json_override=None,
                    transcribe=False,
                    separate=False,
                    separate_query=False,
                    separate_flag=False,
                    fast=False,
                    fast_query=False,
                )
            )

        self.assertEqual(response.status_code, 200)
        payload = self._decode_json_response(response)
        self.assertEqual(payload["phase1"]["timeSignatureSource"], "assumed_four_four")
        self.assertEqual(payload["phase1"]["timeSignatureConfidence"], 0.0)

    @patch.object(server, "get_audio_duration_seconds", return_value=214.6, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 214.6,
            "totalSeconds": {"min": 22, "max": 38},
            "stages": [
                {
                    "key": "dsp",
                    "label": "DSP analysis",
                    "seconds": {"min": 22, "max": 38},
                }
            ],
        },
        create=True,
    )
    def test_estimate_endpoint_returns_preflight_contract(self, *_mocks) -> None:
        response = asyncio.run(
            server.estimate_analysis(
                track=self._upload_file(),
                dsp_json_override=None,
                transcribe=False,
                separate=False,
                separate_query=False,
                separate_flag=False,
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = self._decode_json_response(response)
        self.assertIn("requestId", payload)
        self.assertEqual(payload["estimate"]["durationSeconds"], 214.6)
        self.assertEqual(payload["estimate"]["totalLowMs"], 22000)
        self.assertEqual(payload["estimate"]["totalHighMs"], 38000)
        self.assertEqual(payload["estimate"]["stages"][0]["key"], "local_dsp")

    @patch.object(
        server,
        "_estimate_analysis_run",
        new_callable=AsyncMock,
        create=True,
    )
    def test_legacy_estimate_endpoint_delegates_to_canonical_estimate_helper(
        self,
        estimate_mock: AsyncMock,
    ) -> None:
        estimate_mock.return_value = JSONResponse(
            content={
                "requestId": "req_estimate_legacy",
                "estimate": {
                    "durationSeconds": 60.0,
                    "totalLowMs": 10000,
                    "totalHighMs": 20000,
                    "stages": [
                        {
                            "key": "local_dsp",
                            "label": "Local DSP analysis",
                            "lowMs": 10000,
                            "highMs": 20000,
                        }
                    ],
                },
            }
        )

        response = asyncio.run(
            server.estimate_analysis(
                track=self._upload_file(),
                dsp_json_override=None,
                transcribe=True,
                separate=False,
                separate_query=False,
                separate_flag=False,
            )
        )

        self.assertEqual(response.status_code, 200)
        estimate_mock.assert_awaited_once()

    @patch.object(server, "get_audio_duration_seconds", return_value=214.6, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 214.6,
            "totalSeconds": {"min": 22, "max": 38},
            "stages": [
                {
                    "key": "dsp",
                    "label": "DSP analysis",
                    "seconds": {"min": 22, "max": 38},
                }
            ],
        },
        create=True,
    )
    @patch.object(
        server.subprocess,
        "run",
        side_effect=_make_timeout_expired(),
    )
    def test_timeout_response_uses_structured_json_contract(self, *_mocks) -> None:
        with (
            patch.object(
                server,
                "_current_time",
                side_effect=_timing_points(response_ready_ms=255),
                create=True,
            ),
            patch("builtins.print") as print_mock,
        ):
            response = asyncio.run(
                server.analyze_audio(
                    track=self._upload_file(),
                    dsp_json_override=None,
                    transcribe=True,
                    separate=True,
                    separate_query=False,
                    separate_flag=False,
                    fast=False,
                    fast_query=False,
                )
            )

        self.assertEqual(response.status_code, 504)
        payload = self._decode_json_response(response)
        self.assertEqual(payload["error"]["code"], "ANALYZER_TIMEOUT")
        self.assertEqual(payload["error"]["phase"], "phase1_local_dsp")
        self.assertTrue(payload["error"]["retryable"])
        self.assertEqual(payload["diagnostics"]["estimatedLowMs"], 22000)
        self.assertEqual(payload["diagnostics"]["estimatedHighMs"], 38000)
        self.assertEqual(payload["diagnostics"]["stdoutSnippet"], "partial stdout")
        self.assertEqual(payload["diagnostics"]["stderrSnippet"], "partial stderr")
        self.assertEqual(
            payload["diagnostics"]["timings"],
            {
                "totalMs": 255.0,
                "analysisMs": 200.0,
                "serverOverheadMs": 55.0,
                "flagsUsed": ["--separate"],
                "fileSizeBytes": 10,
                "fileDurationSeconds": None,
                "msPerSecondOfAudio": None,
            },
        )
        print_mock.assert_called_once()
        self.assertIn("flags=[--separate]", print_mock.call_args.args[0])
        self.assertIn("duration=n/a ms/s=n/a", print_mock.call_args.args[0])

    @patch.object(server, "get_audio_duration_seconds", return_value=214.6, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 214.6,
            "totalSeconds": {"min": 22, "max": 38},
            "stages": [
                {
                    "key": "dsp",
                    "label": "DSP analysis",
                    "seconds": {"min": 22, "max": 38},
                }
            ],
        },
        create=True,
    )
    @patch.object(
        server.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            args=["./venv/bin/python", "analyze.py", "track.mp3", "--yes"],
            returncode=0,
            stdout="{not-json",
            stderr="broken payload",
        ),
    )
    def test_invalid_json_response_includes_timing_breakdown(self, *_mocks) -> None:
        with (
            patch.object(
                server,
                "_current_time",
                side_effect=_timing_points(response_ready_ms=235),
                create=True,
            ),
            patch("builtins.print") as print_mock,
        ):
            response = asyncio.run(
                server.analyze_audio(
                    track=self._upload_file(),
                    dsp_json_override=None,
                    transcribe=False,
                    separate=False,
                    separate_query=False,
                    separate_flag=False,
                    fast=False,
                    fast_query=False,
                )
            )

        self.assertEqual(response.status_code, 502)
        payload = self._decode_json_response(response)
        self.assertEqual(payload["error"]["code"], "ANALYZER_INVALID_JSON")
        self.assertEqual(payload["diagnostics"]["backendDurationMs"], 200.0)
        self.assertEqual(
            payload["diagnostics"]["timings"],
            {
                "totalMs": 235.0,
                "analysisMs": 200.0,
                "serverOverheadMs": 35.0,
                "flagsUsed": [],
                "fileSizeBytes": 10,
                "fileDurationSeconds": None,
                "msPerSecondOfAudio": None,
            },
        )
        print_mock.assert_called_once()
        self.assertIn("flags=[]", print_mock.call_args.args[0])
        self.assertIn("duration=n/a ms/s=n/a", print_mock.call_args.args[0])

    @patch.object(server, "get_audio_duration_seconds", return_value=214.6, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 214.6,
            "totalSeconds": {"min": 22, "max": 38},
            "stages": [
                {
                    "key": "dsp",
                    "label": "DSP analysis",
                    "seconds": {"min": 22, "max": 38},
                }
            ],
        },
        create=True,
    )
    @patch.object(
        server.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            args=["./venv/bin/python", "analyze.py", "track.mp3", "--yes"],
            returncode=0,
            stdout=json.dumps(
                {
                    "bpm": 128,
                    "bpmConfidence": 0.92,
                    "key": "A minor",
                    "keyConfidence": 0.88,
                    "timeSignature": "4/4",
                    "durationSeconds": 214.6,
                    "lufsIntegrated": -8.2,
                    "truePeak": -0.1,
                    "stereoDetail": {
                        "stereoWidth": 0.74,
                        "stereoCorrelation": 0.82,
                    },
                    "spectralBalance": {
                        "subBass": -0.6,
                        "lowBass": 1.0,
                        "lowMids": 0.0,
                        "mids": -0.2,
                        "upperMids": 0.3,
                        "highs": 0.9,
                        "brilliance": 0.7,
                    },
                    "melodyDetail": None,
                    "transcriptionDetail": None,
                }
            ),
            stderr="",
        ),
    )
    def test_success_response_includes_estimate_diagnostics(self, *_mocks) -> None:
        with patch("builtins.print"):
            response = asyncio.run(
                server.analyze_audio(
                    track=self._upload_file(),
                    dsp_json_override=None,
                    transcribe=False,
                    separate=False,
                    separate_query=False,
                    separate_flag=False,
                    fast=False,
                    fast_query=False,
                )
            )

        self.assertEqual(response.status_code, 200)
        payload = self._decode_json_response(response)
        self.assertEqual(payload["phase1"]["bpm"], 128)
        self.assertEqual(payload["diagnostics"]["estimatedLowMs"], 22000)
        self.assertEqual(payload["diagnostics"]["estimatedHighMs"], 38000)
        self.assertGreaterEqual(payload["diagnostics"]["timeoutSeconds"], 38)

    @patch.object(server, "get_audio_duration_seconds", return_value=214.6, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 214.6,
            "totalSeconds": {"min": 22, "max": 38},
            "stages": [
                {
                    "key": "dsp",
                    "label": "DSP analysis",
                    "seconds": {"min": 22, "max": 38},
                }
            ],
        },
        create=True,
    )
    @patch.object(
        server.subprocess,
        "run",
        side_effect=RuntimeError("disk full"),
    )
    def test_internal_error_returns_500_with_structured_envelope(self, *_mocks) -> None:
        with (
            patch.object(
                server,
                "_current_time",
                side_effect=_timing_points(response_ready_ms=230),
                create=True,
            ),
            patch("builtins.print"),
        ):
            response = asyncio.run(
                server.analyze_audio(
                    track=self._upload_file(),
                    dsp_json_override=None,
                    transcribe=False,
                    separate=False,
                    separate_query=False,
                    separate_flag=False,
                    fast=False,
                    fast_query=False,
                )
            )

        self.assertEqual(response.status_code, 500)
        payload = self._decode_json_response(response)
        self.assertIn("requestId", payload)
        self.assertEqual(payload["error"]["code"], "BACKEND_INTERNAL_ERROR")
        self.assertEqual(payload["error"]["phase"], "phase1_local_dsp")
        self.assertFalse(payload["error"]["retryable"])
        self.assertIn("stderrSnippet", payload["diagnostics"])
        self.assertIn("timings", payload["diagnostics"])

    @patch.object(server, "get_audio_duration_seconds", return_value=214.6, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 214.6,
            "totalSeconds": {"min": 22, "max": 38},
            "stages": [
                {
                    "key": "dsp",
                    "label": "DSP analysis",
                    "seconds": {"min": 22, "max": 38},
                }
            ],
        },
        create=True,
    )
    @patch.object(
        server.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            args=["./venv/bin/python", "analyze.py", "track.mp3", "--yes"],
            returncode=1,
            stdout="partial output",
            stderr="segfault in essentia",
        ),
    )
    def test_nonzero_exit_returns_502_analyzer_failed(self, *_mocks) -> None:
        with (
            patch.object(
                server,
                "_current_time",
                side_effect=_timing_points(response_ready_ms=250),
                create=True,
            ),
            patch("builtins.print"),
        ):
            response = asyncio.run(
                server.analyze_audio(
                    track=self._upload_file(),
                    dsp_json_override=None,
                    transcribe=False,
                    separate=False,
                    separate_query=False,
                    separate_flag=False,
                    fast=False,
                    fast_query=False,
                )
            )

        self.assertEqual(response.status_code, 502)
        payload = self._decode_json_response(response)
        self.assertIn("requestId", payload)
        self.assertEqual(payload["error"]["code"], "ANALYZER_FAILED")
        self.assertEqual(payload["error"]["phase"], "phase1_local_dsp")
        self.assertTrue(payload["error"]["retryable"])
        self.assertEqual(payload["diagnostics"]["stdoutSnippet"], "partial output")
        self.assertEqual(
            payload["diagnostics"]["stderrSnippet"], "segfault in essentia"
        )

    @patch.object(server, "get_audio_duration_seconds", return_value=214.6, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 214.6,
            "totalSeconds": {"min": 22, "max": 38},
            "stages": [
                {
                    "key": "dsp",
                    "label": "DSP analysis",
                    "seconds": {"min": 22, "max": 38},
                }
            ],
        },
        create=True,
    )
    @patch.object(
        server.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            args=["./venv/bin/python", "analyze.py", "track.mp3", "--yes"],
            returncode=0,
            stdout="",
            stderr="analyze finished with no output",
        ),
    )
    def test_empty_stdout_returns_502_analyzer_empty_output(self, *_mocks) -> None:
        with (
            patch.object(
                server,
                "_current_time",
                side_effect=_timing_points(response_ready_ms=240),
                create=True,
            ),
            patch("builtins.print"),
        ):
            response = asyncio.run(
                server.analyze_audio(
                    track=self._upload_file(),
                    dsp_json_override=None,
                    transcribe=False,
                    separate=False,
                    separate_query=False,
                    separate_flag=False,
                    fast=False,
                    fast_query=False,
                )
            )

        self.assertEqual(response.status_code, 502)
        payload = self._decode_json_response(response)
        self.assertIn("requestId", payload)
        self.assertEqual(payload["error"]["code"], "ANALYZER_EMPTY_OUTPUT")
        self.assertEqual(payload["error"]["phase"], "phase1_local_dsp")
        self.assertFalse(payload["error"]["retryable"])
        self.assertEqual(
            payload["diagnostics"]["stderrSnippet"], "analyze finished with no output"
        )

    @patch.object(server, "get_audio_duration_seconds", return_value=214.6, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 214.6,
            "totalSeconds": {"min": 22, "max": 38},
            "stages": [
                {
                    "key": "dsp",
                    "label": "DSP analysis",
                    "seconds": {"min": 22, "max": 38},
                }
            ],
        },
        create=True,
    )
    @patch.object(
        server.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            args=["./venv/bin/python", "analyze.py", "track.mp3", "--yes"],
            returncode=0,
            stdout="[1, 2, 3]",
            stderr="",
        ),
    )
    def test_non_dict_json_returns_502_analyzer_bad_payload(self, *_mocks) -> None:
        with (
            patch.object(
                server,
                "_current_time",
                side_effect=_timing_points(response_ready_ms=235),
                create=True,
            ),
            patch("builtins.print"),
        ):
            response = asyncio.run(
                server.analyze_audio(
                    track=self._upload_file(),
                    dsp_json_override=None,
                    transcribe=False,
                    separate=False,
                    separate_query=False,
                    separate_flag=False,
                    fast=False,
                    fast_query=False,
                )
            )

        self.assertEqual(response.status_code, 502)
        payload = self._decode_json_response(response)
        self.assertIn("requestId", payload)
        self.assertEqual(payload["error"]["code"], "ANALYZER_BAD_PAYLOAD")
        self.assertEqual(payload["error"]["phase"], "phase1_local_dsp")
        self.assertFalse(payload["error"]["retryable"])
        self.assertEqual(payload["diagnostics"]["stdoutSnippet"], "[1, 2, 3]")


class BuildPhase1CoercionTests(unittest.TestCase):
    """Unit tests for _build_phase1 defensive coercion of scalar fields."""

    def _minimal_payload(self, **overrides) -> dict:
        base = {
            "bpm": 128,
            "bpmConfidence": 0.92,
            "key": "A minor",
            "keyConfidence": 0.88,
            "timeSignature": "4/4",
            "durationSeconds": 214.6,
            "lufsIntegrated": -8.2,
            "lufsRange": 6.3,
            "truePeak": -0.1,
            "crestFactor": 12.5,
            "stereoDetail": {"stereoWidth": 0.74, "stereoCorrelation": 0.82},
            "spectralBalance": {
                "subBass": -0.6,
                "lowBass": 1.0,
                "lowMids": 0.0,
                "mids": -0.2,
                "upperMids": 0.3,
                "highs": 0.9,
                "brilliance": 0.7,
            },
        }
        base.update(overrides)
        return base

    def test_lufs_range_nan_is_coerced_to_none(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(lufsRange=float("nan")))
        self.assertIsNone(phase1["lufsRange"])

    def test_crest_factor_nan_is_coerced_to_none(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(crestFactor=float("nan")))
        self.assertIsNone(phase1["crestFactor"])

    def test_lufs_range_none_stays_none(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(lufsRange=None))
        self.assertIsNone(phase1["lufsRange"])

    def test_crest_factor_none_stays_none(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(crestFactor=None))
        self.assertIsNone(phase1["crestFactor"])

    def test_lufs_range_valid_float_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(lufsRange=6.3))
        self.assertEqual(phase1["lufsRange"], 6.3)

    def test_crest_factor_valid_float_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(crestFactor=12.5))
        self.assertEqual(phase1["crestFactor"], 12.5)

    def test_lufs_range_boolean_is_coerced_to_none(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(lufsRange=True))
        self.assertIsNone(phase1["lufsRange"])

    def test_crest_factor_boolean_is_coerced_to_none(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(crestFactor=True))
        self.assertIsNone(phase1["crestFactor"])

    # ── New field pass-through tests ──────────────────────────────────────

    def test_bpm_percival_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(bpmPercival=127.5))
        self.assertEqual(phase1["bpmPercival"], 127.5)

    def test_bpm_percival_nan_coerced_to_none(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(bpmPercival=float("nan")))
        self.assertIsNone(phase1["bpmPercival"])

    def test_bpm_percival_missing_is_none(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload())
        self.assertIsNone(phase1["bpmPercival"])

    def test_bpm_agreement_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(bpmAgreement=True))
        self.assertTrue(phase1["bpmAgreement"])

    def test_sample_rate_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(sampleRate=44100))
        self.assertEqual(phase1["sampleRate"], 44100)

    def test_dynamic_spread_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(dynamicSpread=0.42))
        self.assertEqual(phase1["dynamicSpread"], 0.42)

    def test_dynamic_spread_nan_coerced_to_none(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(dynamicSpread=float("nan")))
        self.assertIsNone(phase1["dynamicSpread"])

    def test_dynamic_character_passes_through(self) -> None:
        dc = {"dynamicComplexity": 0.5, "loudnessDb": -14.2, "loudnessVariation": -14.2}
        phase1 = server._build_phase1(self._minimal_payload(dynamicCharacter=dc))
        self.assertEqual(phase1["dynamicCharacter"], dc)

    def test_texture_character_passes_through(self) -> None:
        tc = {
            "textureScore": 0.68,
            "lowBandFlatness": 0.51,
            "midBandFlatness": 0.72,
            "highBandFlatness": 0.83,
            "inharmonicity": 0.19,
        }
        phase1 = server._build_phase1(self._minimal_payload(textureCharacter=tc))
        self.assertEqual(phase1["textureCharacter"], tc)

    def test_segment_stereo_passes_through(self) -> None:
        ss = [{"segmentIndex": 0, "stereoWidth": 0.8}]
        phase1 = server._build_phase1(self._minimal_payload(segmentStereo=ss))
        self.assertEqual(phase1["segmentStereo"], ss)

    def test_essentia_features_passes_through(self) -> None:
        ef = {"zeroCrossingRate": 0.12, "hfc": 0.45}
        phase1 = server._build_phase1(self._minimal_payload(essentiaFeatures=ef))
        self.assertEqual(phase1["essentiaFeatures"], ef)

    def test_key_profile_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(keyProfile="edma"))
        self.assertEqual(phase1["keyProfile"], "edma")

    def test_time_signature_source_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(timeSignatureSource="assumed_four_four"))
        self.assertEqual(phase1["timeSignatureSource"], "assumed_four_four")

    def test_time_signature_confidence_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(timeSignatureConfidence=0.0))
        self.assertEqual(phase1["timeSignatureConfidence"], 0.0)

    def test_time_signature_confidence_nan_coerced_to_none(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(timeSignatureConfidence=float("nan")))
        self.assertIsNone(phase1["timeSignatureConfidence"])

    def test_time_signature_fields_null_stay_none(self) -> None:
        phase1 = server._build_phase1(
            self._minimal_payload(timeSignatureSource=None, timeSignatureConfidence=None)
        )
        self.assertIsNone(phase1["timeSignatureSource"])
        self.assertIsNone(phase1["timeSignatureConfidence"])

    def test_tuning_frequency_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(tuningFrequency=440.12))
        self.assertEqual(phase1["tuningFrequency"], 440.12)

    def test_tuning_cents_nan_coerced_to_none(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(tuningCents=float("nan")))
        self.assertIsNone(phase1["tuningCents"])

    def test_lufs_momentary_max_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(lufsMomentaryMax=-3.2))
        self.assertEqual(phase1["lufsMomentaryMax"], -3.2)

    def test_lufs_short_term_max_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(lufsShortTermMax=-4.8))
        self.assertEqual(phase1["lufsShortTermMax"], -4.8)

    def test_plr_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(plr=7.9))
        self.assertEqual(phase1["plr"], 7.9)

    def test_plr_falls_back_to_true_peak_minus_lufs(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(plr=None, truePeak=-0.1, lufsIntegrated=-8.2))
        self.assertEqual(phase1["plr"], 8.1)

    def test_mono_compatible_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(monoCompatible=False))
        self.assertFalse(phase1["monoCompatible"])

    def test_mono_compatible_falls_back_to_sub_bass_mono(self) -> None:
        phase1 = server._build_phase1(
            self._minimal_payload(
                monoCompatible=None,
                stereoDetail={"stereoWidth": 0.74, "stereoCorrelation": 0.82, "subBassMono": True},
            )
        )
        self.assertTrue(phase1["monoCompatible"])

    def test_beats_loudness_passes_through(self) -> None:
        bl = {
            "kickDominantRatio": 0.45,
            "midDominantRatio": 0.35,
            "highDominantRatio": 0.20,
            "patternBeatsPerBar": 4,
            "lowBandAccentPattern": [1.0, 0.3, 0.8, 0.2],
            "midBandAccentPattern": [0.2, 1.0, 0.4, 0.3],
            "highBandAccentPattern": [0.1, 0.2, 0.6, 1.0],
            "overallAccentPattern": [1.0, 0.6, 0.8, 0.5],
            "accentPattern": [1.0, 0.6, 0.8, 0.5],
            "meanBeatLoudness": 0.32,
            "beatLoudnessVariation": 0.18,
            "beatCount": 256,
        }
        phase1 = server._build_phase1(self._minimal_payload(beatsLoudness=bl))
        self.assertEqual(phase1["beatsLoudness"], bl)

    def test_rhythm_timeline_passes_through(self) -> None:
        rhythm_timeline = {
            "beatsPerBar": 4,
            "stepsPerBeat": 4,
            "availableBars": 16,
            "selectionMethod": "representative_dsp_window",
            "windows": [
                {
                    "bars": 8,
                    "startBar": 5,
                    "endBar": 12,
                    "lowBandSteps": [1.0] * 128,
                    "midBandSteps": [0.6] * 128,
                    "highBandSteps": [0.4] * 128,
                    "overallSteps": [0.8] * 128,
                },
                {
                    "bars": 16,
                    "startBar": 1,
                    "endBar": 16,
                    "lowBandSteps": [1.0] * 256,
                    "midBandSteps": [0.6] * 256,
                    "highBandSteps": [0.4] * 256,
                    "overallSteps": [0.8] * 256,
                },
            ],
        }
        phase1 = server._build_phase1(self._minimal_payload(rhythmTimeline=rhythm_timeline))
        self.assertEqual(phase1["rhythmTimeline"], rhythm_timeline)

    def test_envelope_shape_inside_sidechain_detail(self) -> None:
        sd = {
            "pumpingStrength": 0.65,
            "pumpingRegularity": 0.82,
            "pumpingRate": "quarter",
            "pumpingConfidence": 0.71,
            "envelopeShape": [1.0, 0.9, 0.7, 0.5, 0.3, 0.2, 0.15, 0.1,
                              0.08, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01, 0.005],
        }
        phase1 = server._build_phase1(self._minimal_payload(sidechainDetail=sd))
        self.assertEqual(phase1["sidechainDetail"]["envelopeShape"], sd["envelopeShape"])
        self.assertEqual(len(phase1["sidechainDetail"]["envelopeShape"]), 16)

    def test_backward_compat_without_new_fields(self) -> None:
        """Payload without any new fields still builds without error."""
        phase1 = server._build_phase1(self._minimal_payload())
        self.assertIsNotNone(phase1["bpm"])
        self.assertIsNone(phase1.get("bpmPercival"))
        self.assertIsNone(phase1.get("bpmAgreement"))
        self.assertIsNone(phase1.get("sampleRate"))
        self.assertIsNone(phase1.get("dynamicSpread"))
        self.assertIsNone(phase1.get("segmentStereo"))
        self.assertIsNone(phase1.get("essentiaFeatures"))
        self.assertIsNone(phase1.get("beatsLoudness"))
        self.assertIsNone(phase1.get("rhythmTimeline"))
        self.assertIsNone(phase1.get("keyProfile"))
        self.assertIsNone(phase1.get("timeSignatureSource"))
        self.assertIsNone(phase1.get("timeSignatureConfidence"))
        self.assertIsNone(phase1.get("tuningFrequency"))
        self.assertIsNone(phase1.get("tuningCents"))
        self.assertIsNone(phase1.get("lufsMomentaryMax"))
        self.assertIsNone(phase1.get("lufsShortTermMax"))
        self.assertIsNotNone(phase1.get("plr"))
        self.assertIsNone(phase1.get("monoCompatible"))

    def test_bpm_doubletime_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(bpmDoubletime=True))
        self.assertTrue(phase1["bpmDoubletime"])

    def test_bpm_source_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(bpmSource="percival_ratio_corrected"))
        self.assertEqual(phase1["bpmSource"], "percival_ratio_corrected")

    def test_bpm_raw_original_passes_through(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(bpmRawOriginal=66.0))
        self.assertEqual(phase1["bpmRawOriginal"], 66.0)

    def test_bpm_raw_original_nan_coerced_to_none(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload(bpmRawOriginal=float("nan")))
        self.assertIsNone(phase1["bpmRawOriginal"])

    def test_bpm_doubletime_missing_is_none(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload())
        self.assertIsNone(phase1["bpmDoubletime"])

    def test_bpm_source_missing_is_none(self) -> None:
        phase1 = server._build_phase1(self._minimal_payload())
        self.assertIsNone(phase1["bpmSource"])


class Phase2EndpointTests(unittest.TestCase):
    """Tests for the /api/phase2 Gemini advisory endpoint."""

    def _upload_file(self, content: bytes = b"fake-audio", filename: str = "track.mp3") -> UploadFile:
        return UploadFile(filename=filename, file=io.BytesIO(content))

    def _decode(self, response) -> dict:
        return json.loads(response.body.decode("utf-8"))

    def _run(self, coro):
        return asyncio.run(coro)

    def _make_completed_run(
        self,
        runtime,
        *,
        legacy_request_id: str | None = None,
        measurement_payload: dict | None = None,
    ) -> str:
        created = runtime.create_run(
            filename="track.mp3",
            content=b"server-owned-audio",
            mime_type="audio/mpeg",
            pitch_note_mode="off",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
            legacy_request_id=legacy_request_id,
        )
        runtime.complete_measurement(
            created["runId"],
            payload=measurement_payload or {"bpm": 128, "key": "A minor", "durationSeconds": 60.0},
            provenance={"schemaVersion": "measurement.v1", "engineVersion": "analyze.py"},
            diagnostics={"backendDurationMs": 1000},
        )
        return created["runId"]

    def _call(
        self,
        phase1_json=None,
        model_name="gemini-2.5-flash",
        content=b"fake",
        phase1_request_id=None,
        analysis_run_id=None,
    ):
        if phase1_json is None:
            phase1_json = json.dumps({"bpm": 128})
        return self._run(
            server.analyze_phase2(
                track=self._upload_file(content=content),
                phase1_json=phase1_json,
                model_name=model_name,
                phase1_request_id=phase1_request_id,
                analysis_run_id=analysis_run_id,
            )
        )

    def test_returns_500_when_genai_not_installed(self) -> None:
        with patch.object(server, "_GENAI_AVAILABLE", False):
            response = self._call()
        self.assertEqual(response.status_code, 500)
        body = self._decode(response)
        self.assertEqual(body["error"]["code"], "GEMINI_NOT_INSTALLED")
        self.assertFalse(body["error"]["retryable"])

    def test_returns_500_when_api_key_missing(self) -> None:
        with (
            patch.object(server, "_GENAI_AVAILABLE", True),
            patch.dict(server.os.environ, {}, clear=True),
        ):
            response = self._call()
        self.assertEqual(response.status_code, 500)
        body = self._decode(response)
        self.assertEqual(body["error"]["code"], "GEMINI_NOT_CONFIGURED")
        self.assertFalse(body["error"]["retryable"])

    def test_returns_400_when_model_name_not_whitelisted(self) -> None:
        with (
            patch.object(server, "_GENAI_AVAILABLE", True),
            patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
        ):
            response = self._call(model_name="gpt-4o-malicious")
        self.assertEqual(response.status_code, 400)
        body = self._decode(response)
        self.assertEqual(body["error"]["code"], "INVALID_MODEL")
        self.assertFalse(body["error"]["retryable"])

    def test_returns_400_when_analysis_context_is_missing(self) -> None:
        with (
            patch.object(server, "_GENAI_AVAILABLE", True),
            patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
        ):
            response = self._call()
        self.assertEqual(response.status_code, 400)
        body = self._decode(response)
        self.assertEqual(body["error"]["code"], "PHASE2_MISSING_ANALYSIS_CONTEXT")

    def test_returns_404_when_analysis_run_is_unknown(self) -> None:
        with (
            patch.object(server, "_GENAI_AVAILABLE", True),
            patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
        ):
            response = self._call(analysis_run_id="missing-run")
        self.assertEqual(response.status_code, 404)
        body = self._decode(response)
        self.assertEqual(body["error"]["code"], "RUN_NOT_FOUND")

    def test_returns_409_when_measurement_is_not_ready(self) -> None:
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_phase2_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            created = runtime.create_run(
                filename="track.mp3",
                content=b"server-owned-audio",
                mime_type="audio/mpeg",
                pitch_note_mode="off",
                pitch_note_backend="auto",
                interpretation_mode="off",
                interpretation_profile="producer_summary",
                interpretation_model=None,
            )
            with (
                patch.object(server, "_GENAI_AVAILABLE", True),
                patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
                patch.object(server, "get_analysis_runtime", return_value=runtime),
            ):
                response = self._call(analysis_run_id=created["runId"])

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.headers["Deprecation"], "true")
        self.assertEqual(response.headers["Link"], '</api/analysis-runs>; rel="successor-version"')
        body = self._decode(response)
        self.assertEqual(body["analysisRunId"], created["runId"])
        self.assertEqual(body["error"]["code"], "MEASUREMENT_NOT_READY")

    def _mock_successful_gemini(self, response_text: str):
        """Return a mock Gemini client that yields response_text from generate_content."""
        mock_response = unittest.mock.MagicMock()
        mock_response.text = response_text

        mock_model = unittest.mock.MagicMock()
        mock_model.generate_content.return_value = mock_response

        mock_client = unittest.mock.MagicMock()
        mock_client.models = mock_model
        return mock_client

    def test_returns_200_with_phase2_null_when_gemini_returns_empty(self) -> None:
        mock_client = self._mock_successful_gemini("")
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_phase2_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            run_id = self._make_completed_run(runtime)
            with (
                patch.object(server, "get_analysis_runtime", return_value=runtime),
                patch.object(server, "_GENAI_AVAILABLE", True),
                patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
                patch.object(server, "_genai") as mock_genai,
                patch.object(server, "_genai_types") as mock_genai_types,
            ):
                mock_genai.Client.return_value = mock_client
                mock_genai_types.GenerateContentConfig.return_value = unittest.mock.MagicMock()
                response = self._call(analysis_run_id=run_id)

        self.assertEqual(response.status_code, 200)
        body = self._decode(response)
        self.assertIsNone(body["phase2"])
        self.assertIn("skipped", body["message"])

    def test_returns_200_with_phase2_null_when_gemini_returns_bad_shape(self) -> None:
        bad_payload = json.dumps({"trackCharacter": "ok", "missing_all_other_fields": True})
        mock_client = self._mock_successful_gemini(bad_payload)
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_phase2_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            run_id = self._make_completed_run(runtime)
            with (
                patch.object(server, "get_analysis_runtime", return_value=runtime),
                patch.object(server, "_GENAI_AVAILABLE", True),
                patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
                patch.object(server, "_genai") as mock_genai,
                patch.object(server, "_genai_types") as mock_genai_types,
            ):
                mock_genai.Client.return_value = mock_client
                mock_genai_types.GenerateContentConfig.return_value = unittest.mock.MagicMock()
                response = self._call(analysis_run_id=run_id)

        self.assertEqual(response.status_code, 200)
        body = self._decode(response)
        self.assertIsNone(body["phase2"])
        self.assertIn("skipped", body["message"])

    def test_returns_200_with_validation_warnings_when_catalog_semantics_do_not_match(self) -> None:
        invalid_catalog_payload = _valid_phase2_result()
        invalid_catalog_payload["mixAndMasterChain"][0]["device"] = "Transient Shaper"
        invalid_catalog_payload["mixAndMasterChain"][0]["parameter"] = "Attack"
        mock_client = self._mock_successful_gemini(json.dumps(invalid_catalog_payload))
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_phase2_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            run_id = self._make_completed_run(runtime)
            with (
                patch.object(server, "get_analysis_runtime", return_value=runtime),
                patch.object(server, "_GENAI_AVAILABLE", True),
                patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
                patch.object(server, "_genai") as mock_genai,
                patch.object(server, "_genai_types") as mock_genai_types,
            ):
                mock_genai.Client.return_value = mock_client
                mock_genai_types.GenerateContentConfig.return_value = unittest.mock.MagicMock()
                response = self._call(analysis_run_id=run_id)

        self.assertEqual(response.status_code, 200)
        body = self._decode(response)
        self.assertIsNotNone(body["phase2"])
        self.assertIn("validationWarnings", body["diagnostics"])
        self.assertEqual(body["diagnostics"]["validationWarnings"][0]["code"], "UNKNOWN_DEVICE")
        self.assertEqual(body["diagnostics"]["validationWarnings"][0]["path"], "mixAndMasterChain[0].device")

    def test_completed_interpretation_attempt_uses_interpretation_v2_provenance(self) -> None:
        mock_client = self._mock_successful_gemini(json.dumps(_valid_phase2_result()))
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_phase2_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            run_id = self._make_completed_run(runtime)
            with (
                patch.object(server, "get_analysis_runtime", return_value=runtime),
                patch.object(server, "_GENAI_AVAILABLE", True),
                patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
                patch.object(server, "_genai") as mock_genai,
                patch.object(server, "_genai_types") as mock_genai_types,
            ):
                mock_genai.Client.return_value = mock_client
                mock_genai_types.GenerateContentConfig.return_value = unittest.mock.MagicMock()
                response = self._call(analysis_run_id=run_id)
                snapshot = runtime.get_run(run_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            snapshot["stages"]["interpretation"]["provenance"]["schemaVersion"],
            "interpretation.v2",
        )

    def test_returns_502_when_gemini_generate_raises(self) -> None:
        mock_client = unittest.mock.MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("503 service unavailable")
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_phase2_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            run_id = self._make_completed_run(runtime)
            with (
                patch.object(server, "get_analysis_runtime", return_value=runtime),
                patch.object(server, "_GENAI_AVAILABLE", True),
                patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
                patch.object(server, "_genai") as mock_genai,
                patch.object(server, "_genai_types") as mock_genai_types,
            ):
                mock_genai.Client.return_value = mock_client
                mock_genai_types.GenerateContentConfig.return_value = unittest.mock.MagicMock()
                response = self._call(analysis_run_id=run_id)

        self.assertEqual(response.status_code, 502)
        body = self._decode(response)
        self.assertEqual(body["error"]["code"], "GEMINI_GENERATE_FAILED")
        self.assertTrue(body["error"]["retryable"])

    def test_returns_429_when_gemini_quota_error(self) -> None:
        mock_client = unittest.mock.MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("429 quota exceeded")
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_phase2_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            run_id = self._make_completed_run(runtime)
            with (
                patch.object(server, "get_analysis_runtime", return_value=runtime),
                patch.object(server, "_GENAI_AVAILABLE", True),
                patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
                patch.object(server, "_genai") as mock_genai,
                patch.object(server, "_genai_types") as mock_genai_types,
            ):
                mock_genai.Client.return_value = mock_client
                mock_genai_types.GenerateContentConfig.return_value = unittest.mock.MagicMock()
                response = self._call(analysis_run_id=run_id)

        self.assertEqual(response.status_code, 429)
        body = self._decode(response)
        self.assertTrue(body["error"]["retryable"])

    def test_ignores_client_phase1_json_and_uses_server_owned_measurement(self) -> None:
        mock_client = self._mock_successful_gemini(json.dumps(_valid_phase2_result()))
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_phase2_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            run_id = self._make_completed_run(runtime, legacy_request_id="legacy_req_1")
            runtime.create_pitch_note_attempt(
                run_id,
                backend_id="auto",
                mode="stem_notes",
                status="completed",
                result={
                    "transcriptionMethod": "stub-backend",
                    "noteCount": 1,
                    "averageConfidence": 0.8,
                    "stemSeparationUsed": True,
                    "fullMixFallback": False,
                    "stemsTranscribed": ["bass"],
                    "dominantPitches": [],
                    "pitchRange": {
                        "minMidi": 48,
                        "maxMidi": 48,
                        "minName": "C3",
                        "maxName": "C3",
                    },
                    "notes": [],
                },
                provenance={"backendId": "auto"},
            )
            with (
                patch.object(server, "get_analysis_runtime", return_value=runtime),
                patch.object(server, "_GENAI_AVAILABLE", True),
                patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
                patch.object(server, "_genai") as mock_genai,
                patch.object(server, "_genai_types") as mock_genai_types,
            ):
                mock_genai.Client.return_value = mock_client
                mock_genai_types.GenerateContentConfig.return_value = unittest.mock.MagicMock()
                response = self._call(
                    phase1_json=json.dumps({"bpm": 999}),
                    analysis_run_id=run_id,
                )

        self.assertEqual(response.status_code, 200)
        body = self._decode(response)
        self.assertEqual(body["analysisRunId"], run_id)
        prompt = mock_client.models.generate_content.call_args.kwargs["contents"][0]["parts"][1]["text"]
        self.assertIn("AUTHORITATIVE_MEASUREMENT_RESULT_JSON", prompt)
        self.assertIn("OPTIONAL_PITCH_NOTE_TRANSLATION_RESULT_JSON", prompt)
        self.assertIn("GROUNDING_METADATA", prompt)
        self.assertIn('"bpm": 128', prompt)
        self.assertNotIn('"bpm": 999', prompt)
        self.assertIn('"transcriptionMethod": "stub-backend"', prompt)

    def test_server_owned_measurement_prompt_includes_dynamic_character(self) -> None:
        mock_client = self._mock_successful_gemini(json.dumps(_valid_phase2_result()))
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_phase2_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            run_id = self._make_completed_run(
                runtime,
                measurement_payload={
                    "bpm": 128,
                    "key": "A minor",
                    "durationSeconds": 60.0,
                    "dynamicCharacter": {
                        "dynamicComplexity": 3.781,
                        "loudnessVariation": -24.056,
                        "spectralFlatness": 0.0131,
                        "logAttackTime": -4.2565,
                        "attackTimeStdDev": 0.0291,
                    },
                },
            )
            with (
                patch.object(server, "get_analysis_runtime", return_value=runtime),
                patch.object(server, "_GENAI_AVAILABLE", True),
                patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
                patch.object(server, "_genai") as mock_genai,
                patch.object(server, "_genai_types") as mock_genai_types,
            ):
                mock_genai.Client.return_value = mock_client
                mock_genai_types.GenerateContentConfig.return_value = unittest.mock.MagicMock()
                response = self._call(analysis_run_id=run_id)

        self.assertEqual(response.status_code, 200)
        prompt = mock_client.models.generate_content.call_args.kwargs["contents"][0]["parts"][1]["text"]
        self.assertIn('"dynamicCharacter"', prompt)
        self.assertIn('"dynamicComplexity": 3.781', prompt)

    def test_compatibility_wrapper_can_resolve_run_from_legacy_request_id(self) -> None:
        mock_client = self._mock_successful_gemini(json.dumps(_valid_phase2_result()))
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_phase2_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            run_id = self._make_completed_run(runtime, legacy_request_id="legacy_req_2")
            with (
                patch.object(server, "get_analysis_runtime", return_value=runtime),
                patch.object(server, "_GENAI_AVAILABLE", True),
                patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
                patch.object(server, "_genai") as mock_genai,
                patch.object(server, "_genai_types") as mock_genai_types,
            ):
                mock_genai.Client.return_value = mock_client
                mock_genai_types.GenerateContentConfig.return_value = unittest.mock.MagicMock()
                response = self._call(
                    phase1_json="ignored",
                    phase1_request_id="legacy_req_2",
                )

        self.assertEqual(response.status_code, 200)
        body = self._decode(response)
        self.assertEqual(body["analysisRunId"], run_id)

    def test_stem_summary_profile_uses_dedicated_prompt_schema_and_hooks(self) -> None:
        source_audio = b"source-audio"
        bass_audio = b"bass-audio"
        other_audio = b"other-audio"
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_phase2_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            created = runtime.create_run(
                filename="track.mp3",
                content=source_audio,
                mime_type="audio/mpeg",
                pitch_note_mode="stem_notes",
                pitch_note_backend="auto",
                interpretation_mode="off",
                interpretation_profile="producer_summary",
                interpretation_model=None,
            )
            run_id = created["runId"]
            runtime.complete_measurement(
                run_id,
                payload={
                    "bpm": 128,
                    "key": "A minor",
                    "durationSeconds": 60.0,
                    "rhythmDetail": {"downbeats": [0.0, 1.875, 3.75]},
                    "segmentLoudness": [],
                    "sidechainDetail": {
                        "pumpingStrength": 0.7,
                        "pumpingRegularity": 0.8,
                        "pumpingRate": "1/4",
                        "pumpingConfidence": 0.9,
                    },
                },
                provenance={"schemaVersion": "measurement.v1", "engineVersion": "analyze.py"},
                diagnostics={"backendDurationMs": 1000},
            )
            bass_path = Path(temp_dir) / "bass.wav"
            bass_path.write_bytes(bass_audio)
            runtime.record_artifact(
                run_id,
                kind="stem_bass",
                source_path=str(bass_path),
                filename="bass.wav",
                mime_type="audio/wav",
                provenance={"generator": "test"},
            )
            other_path = Path(temp_dir) / "other.wav"
            other_path.write_bytes(other_audio)
            runtime.record_artifact(
                run_id,
                kind="stem_other",
                source_path=str(other_path),
                filename="other.wav",
                mime_type="audio/wav",
                provenance={"generator": "test"},
            )
            runtime.create_pitch_note_attempt(
                run_id,
                backend_id="torchcrepe-viterbi",
                mode="stem_notes",
                status="completed",
                result={
                    "transcriptionMethod": "torchcrepe-viterbi",
                    "noteCount": 1,
                    "averageConfidence": 0.8,
                    "stemSeparationUsed": True,
                    "fullMixFallback": False,
                    "stemsTranscribed": ["bass"],
                    "dominantPitches": [],
                    "pitchRange": {
                        "minMidi": 48,
                        "maxMidi": 48,
                        "minName": "C3",
                        "maxName": "C3",
                    },
                    "notes": [],
                },
                provenance={"backendId": "torchcrepe-viterbi"},
            )
            attempt_id = runtime.create_interpretation_attempt(
                run_id,
                profile_id="stem_summary",
                model_name="gemini-2.5-flash",
                status="queued",
            )
            runtime.reserve_interpretation_attempt(attempt_id)
            with (
                patch.object(server, "_GENAI_AVAILABLE", True),
                patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
                patch.object(server, "_genai") as mock_genai,
                patch.object(server, "_genai_types") as mock_genai_types,
            ):
                mock_response_bass = unittest.mock.MagicMock()
                mock_response_bass.text = json.dumps(
                    _valid_single_stem_summary_result("Bass stem summary.")
                )
                mock_response_other = unittest.mock.MagicMock()
                mock_response_other.text = json.dumps(
                    _valid_single_stem_summary_result("Other stem summary.")
                )
                mock_model = unittest.mock.MagicMock()
                mock_model.generate_content.side_effect = [
                    mock_response_bass,
                    mock_response_other,
                ]
                mock_client = unittest.mock.MagicMock()
                mock_client.models = mock_model
                mock_genai.Client.return_value = mock_client
                mock_genai_types.GenerateContentConfig.return_value = unittest.mock.MagicMock()
                execution = server._execute_interpretation_attempt(
                    runtime,
                    {
                        "attemptId": attempt_id,
                        "runId": run_id,
                        "profileId": "stem_summary",
                        "modelName": "gemini-2.5-flash",
                    },
                )

            self.assertTrue(execution["ok"])
            self.assertEqual(mock_model.generate_content.call_count, 2)
            for call in mock_genai_types.GenerateContentConfig.call_args_list:
                self.assertEqual(
                    call.kwargs["response_schema"],
                    server.STEM_SUMMARY_RESPONSE_SCHEMA,
                )
            prompt = mock_model.generate_content.call_args_list[0].kwargs["contents"][0]["parts"][1]["text"]
            self.assertIn("MEASUREMENT_DERIVED_DESCRIPTOR_HOOKS", prompt)
            self.assertIn("stableBarGrid", prompt)
            self.assertIn("pumpingOrModulationDescriptor", prompt)
            payloads = []
            for call in mock_model.generate_content.call_args_list:
                media_part = call.kwargs["contents"][0]["parts"][0]
                payloads.append(media_part["inline_data"]["data"])
            decoded_payloads = {json.loads(json.dumps(payload)) if False else __import__("base64").b64decode(payload) for payload in payloads}
            self.assertEqual(decoded_payloads, {bass_audio, other_audio})
            snapshot = runtime.get_run(run_id)
            self.assertEqual(snapshot["stages"]["interpretation"]["attemptsSummary"][0]["profileId"], "stem_summary")
            self.assertEqual(
                [stem["stem"] for stem in snapshot["stages"]["interpretation"]["result"]["stems"]],
                ["bass", "other"],
            )
            self.assertEqual(
                snapshot["stages"]["interpretation"]["result"]["stems"][0]["summary"],
                "Bass stem summary.",
            )

    def test_pitch_note_worker_persists_stem_artifacts_from_subprocess_output(self) -> None:
        from analysis_runtime import AnalysisRuntime

        mock_result = json.dumps({"transcriptionDetail": None})

        with tempfile.TemporaryDirectory(prefix="asa_pitch_note_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            created = runtime.create_run(
                filename="track.mp3",
                content=b"fake-audio",
                mime_type="audio/mpeg",
                pitch_note_mode="stem_notes",
                pitch_note_backend="torchcrepe-viterbi",
                interpretation_mode="off",
                interpretation_profile="producer_summary",
                interpretation_model=None,
            )
            attempt_id = runtime.create_pitch_note_attempt(
                created["runId"],
                backend_id="torchcrepe-viterbi",
                mode="stem_notes",
                status="queued",
            )
            runtime.reserve_pitch_note_attempt(attempt_id)

            def fake_subprocess_run(command, **kwargs):
                stem_output_dir = None
                if "--stem-output-dir" in command:
                    idx = command.index("--stem-output-dir")
                    stem_output_dir = command[idx + 1]
                if stem_output_dir:
                    Path(stem_output_dir).mkdir(parents=True, exist_ok=True)
                    (Path(stem_output_dir) / "bass.wav").write_bytes(b"bass-audio")
                    (Path(stem_output_dir) / "other.wav").write_bytes(b"other-audio")
                return subprocess.CompletedProcess(
                    args=command,
                    returncode=0,
                    stdout=mock_result,
                    stderr="",
                )

            with patch.object(server.subprocess, "run", side_effect=fake_subprocess_run) as subprocess_mock:
                server._execute_pitch_note_attempt(
                    runtime,
                    {
                        "attemptId": attempt_id,
                        "runId": created["runId"],
                        "backendId": "torchcrepe-viterbi",
                        "mode": "stem_notes",
                    },
                )

                subprocess_mock.assert_called_once()
                cmd = subprocess_mock.call_args[0][0]
                self.assertIn("--stem-output-dir", cmd)
                snapshot = runtime.get_run(created["runId"])
                stem_kinds = [artifact["kind"] for artifact in snapshot["artifacts"]["stems"]]
                self.assertEqual(stem_kinds, ["stem_bass", "stem_other"])

    def test_openapi_schema_exposes_phase2_route(self) -> None:
        spec = server.app.openapi()
        self.assertIn("/api/phase2", spec["paths"])
        phase2_props = (
            spec["paths"]["/api/phase2"]["post"]["requestBody"]
            ["content"]["multipart/form-data"]["schema"]
        )
        # Resolve $ref if present
        if "$ref" in phase2_props:
            schema_name = phase2_props["$ref"].split("/")[-1]
            props = spec["components"]["schemas"][schema_name]["properties"]
        else:
            props = phase2_props.get("properties", {})
        self.assertIn("track", props)
        self.assertIn("phase1_json", props)
        self.assertIn("analysis_run_id", props)
        self.assertIn("model_name", props)

    def test_response_includes_request_id(self) -> None:
        with (
            patch.object(server, "_GENAI_AVAILABLE", True),
            patch.dict(server.os.environ, {}, clear=True),
        ):
            response = self._call()
        body = self._decode(response)
        self.assertIn("requestId", body)
        self.assertIsInstance(body["requestId"], str)
        self.assertGreater(len(body["requestId"]), 0)


class AnalysisRunCompatibilityTests(unittest.TestCase):
    """Tests for legacy wrappers backed by analysis runs."""

    _MINIMAL_ANALYZE_PAYLOAD = json.dumps({
        "bpm": 128, "bpmConfidence": 0.9, "key": "C major", "keyConfidence": 0.8,
        "timeSignature": "4/4", "durationSeconds": 60.0,
        "lufsIntegrated": -8.0, "truePeak": -0.5,
        "stereoDetail": {"stereoWidth": 0.5, "stereoCorrelation": 0.9},
        "spectralBalance": {"subBass": 0.0, "lowBass": 0.0, "lowMids": 0.0, "mids": 0.0,
                            "upperMids": 0.0, "highs": 0.0, "brilliance": 0.0},
        "melodyDetail": None, "transcriptionDetail": None,
    })

    def _upload_file(self) -> UploadFile:
        return UploadFile(filename="track.mp3", file=io.BytesIO(b"fake-audio"))

    def _decode(self, response) -> dict:
        return json.loads(response.body.decode("utf-8"))

    @patch.object(server, "get_audio_duration_seconds", return_value=60.0, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 60.0,
            "totalSeconds": {"min": 10, "max": 20},
            "stages": [{"key": "dsp", "label": "DSP analysis", "seconds": {"min": 10, "max": 20}}],
        },
        create=True,
    )
    @patch.object(
        server.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=_MINIMAL_ANALYZE_PAYLOAD,
            stderr="",
        ),
    )
    def test_analyze_returns_analysis_run_id_and_persists_measurement(self, *_mocks) -> None:
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_analyze_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            with (
                patch.object(server, "get_analysis_runtime", return_value=runtime),
                patch.object(server, "_current_time", side_effect=_timing_points(), create=True),
                patch("builtins.print"),
            ):
                response = asyncio.run(
                    server.analyze_audio(
                        track=self._upload_file(),
                        dsp_json_override=None,
                        transcribe=False,
                        separate=False,
                        separate_query=False,
                        separate_flag=False,
                        fast=False,
                        fast_query=False,
                    )
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["Deprecation"], "true")
            self.assertEqual(response.headers["Link"], '</api/analysis-runs>; rel="successor-version"')
            payload = self._decode(response)
            self.assertIn("analysisRunId", payload)
            snapshot = runtime.get_run(payload["analysisRunId"])
            self.assertEqual(snapshot["stages"]["measurement"]["status"], "completed")
            self.assertEqual(snapshot["stages"]["measurement"]["result"]["bpm"], 128)

    @patch.object(server, "get_audio_duration_seconds", return_value=60.0, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 60.0,
            "totalSeconds": {"min": 10, "max": 20},
            "stages": [{"key": "dsp", "label": "DSP analysis", "seconds": {"min": 10, "max": 20}}],
        },
        create=True,
    )
    @patch.object(
        server.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="error",
        ),
    )
    def test_analyze_marks_measurement_failed_when_subprocess_errors(self, *_mocks) -> None:
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_analyze_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            with (
                patch.object(server, "get_analysis_runtime", return_value=runtime),
                patch.object(server, "_current_time", side_effect=_timing_points(), create=True),
                patch("builtins.print"),
            ):
                response = asyncio.run(
                    server.analyze_audio(
                        track=self._upload_file(),
                        dsp_json_override=None,
                        transcribe=False,
                        separate=False,
                        separate_query=False,
                        separate_flag=False,
                        fast=False,
                        fast_query=False,
                    )
                )

            self.assertEqual(response.status_code, 502)
            payload = self._decode(response)
            snapshot = runtime.get_run(payload["analysisRunId"])
            self.assertEqual(snapshot["stages"]["measurement"]["status"], "failed")

    @patch.object(server, "get_audio_duration_seconds", return_value=60.0, create=True)
    @patch.object(
        server,
        "build_analysis_estimate",
        return_value={
            "durationSeconds": 60.0,
            "totalSeconds": {"min": 10, "max": 20},
            "stages": [{"key": "dsp", "label": "DSP analysis", "seconds": {"min": 10, "max": 20}}],
        },
        create=True,
    )
    @patch.object(
        server.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({
                "bpm": 128,
                "bpmConfidence": 0.9,
                "key": "C major",
                "keyConfidence": 0.8,
                "timeSignature": "4/4",
                "durationSeconds": 60.0,
                "lufsIntegrated": -8.0,
                "truePeak": -0.5,
                "stereoDetail": {"stereoWidth": 0.5, "stereoCorrelation": 0.9},
                "spectralBalance": {"subBass": 0.0, "lowBass": 0.0, "lowMids": 0.0, "mids": 0.0, "upperMids": 0.0, "highs": 0.0, "brilliance": 0.0},
                "melodyDetail": None,
                "transcriptionDetail": {
                    "transcriptionMethod": "stub-backend",
                    "noteCount": 1,
                    "averageConfidence": 0.8,
                    "stemSeparationUsed": True,
                    "fullMixFallback": False,
                    "stemsTranscribed": ["bass"],
                    "dominantPitches": [],
                    "pitchRange": {
                        "minMidi": 48,
                        "maxMidi": 48,
                        "minName": "C3",
                        "maxName": "C3",
                    },
                    "notes": [],
                },
            }),
            stderr="",
        ),
    )
    def test_analyze_can_return_legacy_transcription_detail_without_contaminating_canonical_measurement(self, *_mocks) -> None:
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_analyze_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            with (
                patch.object(server, "get_analysis_runtime", return_value=runtime),
                patch.object(server, "_current_time", side_effect=_timing_points(), create=True),
                patch("builtins.print"),
            ):
                response = asyncio.run(
                    server.analyze_audio(
                        track=self._upload_file(),
                        dsp_json_override=None,
                        transcribe=True,
                        separate=False,
                        separate_query=False,
                        separate_flag=False,
                        fast=False,
                        fast_query=False,
                    )
                )

            self.assertEqual(response.status_code, 200)
            payload = self._decode(response)
            self.assertIn("transcriptionDetail", payload["phase1"])
            snapshot = runtime.get_run(payload["analysisRunId"])
            self.assertNotIn("transcriptionDetail", snapshot["stages"]["measurement"]["result"])
            self.assertEqual(snapshot["stages"]["pitchNoteTranslation"]["status"], "queued")
            self.assertIsNone(snapshot["stages"]["pitchNoteTranslation"]["result"])


class StageWorkerTests(unittest.TestCase):
    def test_reserved_measurement_job_uses_runtime_pitch_note_mode_resolution(self) -> None:
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_measurement_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            created = runtime.create_run(
                filename="track.mp3",
                content=b"fake-audio",
                mime_type="audio/mpeg",
                pitch_note_mode="stem_notes",
                pitch_note_backend="auto",
                interpretation_mode="off",
                interpretation_profile="producer_summary",
                interpretation_model=None,
            )
            job = runtime.reserve_next_measurement_run()

            with patch.object(
                server,
                "_execute_measurement_run",
                return_value={"ok": True, "payload": {}, "diagnostics": {}},
            ) as execute_measurement_run_mock:
                server._execute_reserved_measurement_job(runtime, job)

        execute_measurement_run_mock.assert_called_once_with(
            runtime,
            created["runId"],
            request_id=created["runId"],
            run_separation=False,
            run_transcribe=False,
            run_fast=False,
            run_standard=False,
        )

    def test_reserved_measurement_job_fails_measurement_for_unsupported_pitch_note_mode(self) -> None:
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_measurement_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            created = runtime.create_run(
                filename="track.mp3",
                content=b"fake-audio",
                mime_type="audio/mpeg",
                pitch_note_mode="melody_only",
                pitch_note_backend="auto",
                interpretation_mode="off",
                interpretation_profile="producer_summary",
                interpretation_model=None,
            )
            job = runtime.reserve_next_measurement_run()

            result = server._execute_reserved_measurement_job(runtime, job)

            self.assertFalse(result["ok"])
            self.assertEqual(result["errorCode"], "PITCH_NOTE_MODE_UNSUPPORTED")
            snapshot = runtime.get_run(created["runId"])
            self.assertEqual(snapshot["stages"]["measurement"]["status"], "failed")
            self.assertEqual(snapshot["stages"]["measurement"]["error"]["code"], "PITCH_NOTE_MODE_UNSUPPORTED")

    def test_pitch_note_worker_runs_as_subprocess(self) -> None:
        """Pitch/note translation runs analyze.py --pitch-note-only as a subprocess."""
        from analysis_runtime import AnalysisRuntime

        mock_result = json.dumps({
            "transcriptionDetail": {
                "transcriptionMethod": "torchcrepe-viterbi",
                "noteCount": 1,
                "averageConfidence": 0.8,
                "dominantPitches": [],
                "pitchRange": {
                    "minMidi": 48,
                    "maxMidi": 48,
                    "minName": "C3",
                    "maxName": "C3",
                },
                "stemSeparationUsed": True,
                "fullMixFallback": False,
                "stemsTranscribed": ["bass", "other"],
                "notes": [],
            }
        })

        with tempfile.TemporaryDirectory(prefix="asa_pitch_note_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            created = runtime.create_run(
                filename="track.mp3",
                content=b"fake-audio",
                mime_type="audio/mpeg",
                pitch_note_mode="stem_notes",
                pitch_note_backend="auto",
                interpretation_mode="off",
                interpretation_profile="producer_summary",
                interpretation_model=None,
            )
            runtime.complete_measurement(
                created["runId"],
                payload={"bpm": 128, "durationSeconds": 60.0},
                provenance={"schemaVersion": "measurement.v1"},
                diagnostics={"backendDurationMs": 1000},
            )
            attempt_id = runtime.create_pitch_note_attempt(
                created["runId"],
                backend_id="auto",
                mode="stem_notes",
                status="queued",
            )
            runtime.reserve_pitch_note_attempt(attempt_id)

            fake_proc = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=mock_result, stderr="",
            )
            with patch.object(
                server.subprocess,
                "run",
                return_value=fake_proc,
            ) as subprocess_mock:
                server._execute_pitch_note_attempt(
                    runtime,
                    {
                        "attemptId": attempt_id,
                        "runId": created["runId"],
                        "backendId": "auto",
                        "mode": "stem_notes",
                    },
                )

            subprocess_mock.assert_called_once()
            call_args = subprocess_mock.call_args
            cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
            self.assertIn("--pitch-note-only", cmd)
            snapshot = runtime.get_run(created["runId"])
            self.assertEqual(snapshot["stages"]["pitchNoteTranslation"]["status"], "completed")
            self.assertEqual(
                snapshot["stages"]["pitchNoteTranslation"]["result"]["transcriptionMethod"],
                "torchcrepe-viterbi",
            )

    def test_pitch_note_worker_passes_backend_flag_to_subprocess(self) -> None:
        from analysis_runtime import AnalysisRuntime

        mock_result = json.dumps({"transcriptionDetail": None})

        with tempfile.TemporaryDirectory(prefix="asa_pitch_note_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            created = runtime.create_run(
                filename="track.mp3",
                content=b"fake-audio",
                mime_type="audio/mpeg",
                pitch_note_mode="stem_notes",
                pitch_note_backend="torchcrepe-viterbi",
                interpretation_mode="off",
                interpretation_profile="producer_summary",
                interpretation_model=None,
            )
            attempt_id = runtime.create_pitch_note_attempt(
                created["runId"],
                backend_id="torchcrepe-viterbi",
                mode="stem_notes",
                status="queued",
            )
            runtime.reserve_pitch_note_attempt(attempt_id)

            fake_proc = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=mock_result,
                stderr="",
            )
            with patch.object(server.subprocess, "run", return_value=fake_proc) as subprocess_mock:
                server._execute_pitch_note_attempt(
                    runtime,
                    {
                        "attemptId": attempt_id,
                        "runId": created["runId"],
                        "backendId": "torchcrepe-viterbi",
                        "mode": "stem_notes",
                    },
                )

        subprocess_mock.assert_called_once()
        cmd = subprocess_mock.call_args[0][0]
        self.assertIn("--pitch-note-backend", cmd)
        self.assertIn("torchcrepe-viterbi", cmd)


if __name__ == "__main__":
    unittest.main()

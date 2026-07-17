"""Tests for the Phase 2 provider abstraction (gemini | claude).

Pure-logic / contract tests — no Essentia, no GPU, no network. Run with the
product venv from apps/backend:
``./venv/bin/python -m unittest tests.test_phase2_provider``.
"""

import json
import os
import unittest
from unittest import mock

from phase2_provider import (
    ClaudeCliProvider,
    Phase2ProviderError,
    Phase2ProviderRequest,
    _gemini_schema_to_json_schema,
    resolve_external_phase2_provider,
    resolve_phase2_provider_name,
)
from server_phase2 import _is_valid_phase2_shape, _validate_phase2_citation_paths


_SAMPLE_PHASE1 = {
    "bpm": 128.0,
    "key": "A Minor",
    "timeSignature": "4/4",
    "sampleRate": 48000,
    "durationSeconds": 16.0,
    "lufsIntegrated": -9.2,
    "lufsRange": 4.1,
    "truePeak": -0.8,
    "crestFactor": 11.2,
    "spectralBalance": {"subBass": 0.2, "lowMid": 0.3},
    "kickDetail": {"fundamentalHz": 55.0},
}


# ---------------------------------------------------------------------------
# Local Phase2Result fixture (was moss_sidecar.mock_interpreter; kept inline so
# Claude provider tests still exercise the shared parse/citation tail).
# ---------------------------------------------------------------------------

_CITATION_CANDIDATES: tuple[str, ...] = (
    "bpm",
    "lufsIntegrated",
    "key",
    "lufsRange",
    "truePeak",
    "crestFactor",
    "timeSignature",
    "durationSeconds",
    "sampleRate",
    "danceability",
)


def _present(phase1: dict, path: str) -> bool:
    parts = path.split(".")
    node = phase1
    for part in parts:
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and node and isinstance(node[0], dict) and part in node[0]:
            node = node[0][part]
        else:
            return False
    return True


def _citations(phase1: dict, limit: int) -> list[str]:
    found = [path for path in _CITATION_CANDIDATES if _present(phase1, path)]
    for parent, _child in (("spectralBalance", None), ("kickDetail", None)):
        node = phase1.get(parent)
        if isinstance(node, dict):
            for child_key, child_val in node.items():
                if isinstance(child_val, (int, float, str)):
                    found.append(f"{parent}.{child_key}")
                    break
    deduped = list(dict.fromkeys(found))
    return (deduped or ["bpm"])[:limit]


def _num(phase1: dict, key: str, default: float) -> float:
    value = phase1.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _str(phase1: dict, key: str, default: str) -> str:
    value = phase1.get(key)
    return value if isinstance(value, str) and value.strip() else default


def _fixture_phase2_result(phase1: dict, *, model_label: str = "test-fixture") -> dict:
    """Schema-valid Phase2Result grounded in ``phase1`` for unit tests."""
    bpm = _num(phase1, "bpm", 120.0)
    key = _str(phase1, "key", "C Minor")
    time_signature = _str(phase1, "timeSignature", "4/4")
    sample_rate = int(_num(phase1, "sampleRate", 48000))
    duration = _num(phase1, "durationSeconds", 16.0)
    lufs = phase1.get("lufsIntegrated")
    lufs_text = f"{lufs:.1f} LUFS" if isinstance(lufs, (int, float)) else "the measured loudness"
    cites_loudness = _citations(phase1, 2)
    cites_tempo = _citations(phase1, 1)
    cites_tonal = _citations(phase1, 2)
    return {
        "trackCharacter": (
            f"A {bpm:.0f} BPM piece in {key} ({time_signature}). This is a "
            f"deterministic mock interpretation grounded in Phase 1 ({model_label})."
        ),
        "projectSetup": {
            "tempoBpm": bpm,
            "timeSignature": time_signature,
            "sampleRate": sample_rate,
            "bitDepth": 24,
            "headroomTarget": "-6 dBFS on the master before limiting",
            "sessionGoal": f"Rebuild the track's character at {bpm:.0f} BPM in {key}.",
        },
        "trackLayout": [
            {
                "order": 1,
                "name": "Drums",
                "type": "Drum Rack",
                "purpose": "Foundational groove and transient energy.",
                "grounding": {"phase1Fields": cites_tempo},
            },
            {
                "order": 2,
                "name": "Bass",
                "type": "Instrument",
                "purpose": "Low-end anchor tuned to the detected key.",
                "grounding": {"phase1Fields": cites_tonal},
            },
        ],
        "routingBlueprint": {
            "sidechainSource": "Kick",
            "sidechainTargets": ["Bass", "Pads"],
            "returns": [
                {
                    "name": "A - Reverb",
                    "purpose": "Shared space for melodic elements.",
                    "sendSources": ["Bass", "Lead"],
                    "deviceFocus": "Reverb",
                    "levelGuidance": "Start at -18 dB return level.",
                }
            ],
            "notes": ["Mock routing blueprint grounded in Phase 1 measurements."],
        },
        "warpGuide": {
            "fullTrack": {
                "warpMode": "Complex Pro",
                "settings": "Formants 100, Envelope 128",
                "reason": "Full-mix material warps cleanest under Complex Pro.",
            },
            "drums": {
                "warpMode": "Beats",
                "settings": "Transient Loop Mode: Loop Off",
                "reason": "Percussive transients preserved with Beats mode.",
            },
            "bass": {
                "warpMode": "Complex",
                "reason": "Sustained low end stays stable under Complex.",
            },
            "melodic": {
                "warpMode": "Tones",
                "reason": "Monophonic-leaning melodic content suits Tones.",
            },
            "rationale": f"Warp choices follow the {bpm:.0f} BPM grid measured in Phase 1.",
        },
        "detectedCharacteristics": [
            {
                "name": "Tempo lock",
                "confidence": "HIGH",
                "explanation": f"Phase 1 measured {bpm:.1f} BPM.",
            },
            {
                "name": "Tonal center",
                "confidence": "MED",
                "explanation": f"Phase 1 estimated the key as {key}.",
            },
        ],
        "arrangementOverview": {
            "summary": "A single-loop mock arrangement spanning the measured duration.",
            "segments": [
                {
                    "index": 0,
                    "startTime": 0.0,
                    "endTime": round(duration, 3),
                    "description": "Full loop.",
                    "sceneName": "Loop",
                    "abletonAction": "Duplicate to a 1-bar clip and loop.",
                    "automationFocus": "Filter cutoff sweep over the loop.",
                }
            ],
        },
        "sonicElements": {
            "kick": "Punchy sine-based kick with a short decay.",
            "bass": f"Sub-forward bass tuned to {key}.",
            "melodicArp": "Plucked arpeggio supporting the lead.",
            "grooveAndTiming": f"Straight {time_signature} groove at {bpm:.0f} BPM.",
            "effectsAndTexture": "Light reverb and saturation for glue.",
        },
        "mixAndMasterChain": [
            {
                "order": 1,
                "device": "EQ Eight",
                "deviceFamily": "NATIVE",
                "trackContext": "Master",
                "workflowStage": "MASTER",
                "parameter": "Low Cut",
                "value": "30 Hz, 24 dB/oct",
                "reason": "Clear inaudible sub-rumble below the fundamental.",
                "phase1Fields": cites_tonal,
            },
            {
                "order": 2,
                "device": "Glue Compressor",
                "deviceFamily": "NATIVE",
                "trackContext": "Master",
                "workflowStage": "MASTER",
                "parameter": "Ratio",
                "value": "2:1, slow attack",
                "reason": f"Gentle bus glue toward {lufs_text}.",
                "phase1Fields": cites_loudness,
            },
        ],
        "secretSauce": {
            "title": "Measurement-grounded mock recipe",
            "explanation": "A deterministic recipe demonstrating the citation contract.",
            "implementationSteps": [
                "Set the project tempo to the measured BPM.",
                "Tune the bass to the detected key.",
            ],
            "workflowSteps": [
                {
                    "step": 1,
                    "trackContext": "Master",
                    "device": "Utility",
                    "parameter": "Gain",
                    "value": "0.0 dB",
                    "instruction": "Confirm gain staging before the limiter.",
                    "measurementJustification": f"Targeting {lufs_text} measured in Phase 1.",
                    "phase1Fields": cites_loudness,
                }
            ],
        },
        "confidenceNotes": [
            {
                "field": "key",
                "value": key,
                "reason": "Key estimate carries moderate confidence.",
            }
        ],
        "abletonRecommendations": [
            {
                "device": "Operator",
                "deviceFamily": "NATIVE",
                "trackContext": "Bass",
                "workflowStage": "SOUND_DESIGN",
                "category": "SYNTHESIS",
                "parameter": "Oscillator A Coarse",
                "value": "tuned to the detected key root",
                "reason": f"Anchor the bass to {key}.",
                "advancedTip": "Add a second detuned voice for width.",
                "phase1Fields": cites_tonal,
            },
            {
                "device": "Glue Compressor",
                "deviceFamily": "NATIVE",
                "trackContext": "Master",
                "workflowStage": "MASTER",
                "category": "DYNAMICS",
                "parameter": "Makeup",
                "value": "+2 dB",
                "reason": f"Move loudness toward {lufs_text}.",
                "advancedTip": "Engage soft-clip for extra glue.",
                "phase1Fields": cites_loudness,
            },
        ],
    }


class ResolveProviderTests(unittest.TestCase):
    def test_defaults_to_gemini_none(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_phase2_provider_name(), "gemini")
            self.assertIsNone(resolve_external_phase2_provider())

    def test_unknown_value_degrades_to_gemini(self):
        with mock.patch.dict(os.environ, {"ASA_PHASE2_PROVIDER": "bogus"}, clear=True):
            self.assertEqual(resolve_phase2_provider_name(), "gemini")
            self.assertIsNone(resolve_external_phase2_provider())

    def test_moss_no_longer_selected(self):
        # Former MOSS provider id degrades to gemini (unknown after trust-diet B1).
        with mock.patch.dict(os.environ, {"ASA_PHASE2_PROVIDER": "moss"}, clear=True):
            self.assertEqual(resolve_phase2_provider_name(), "gemini")
            self.assertIsNone(resolve_external_phase2_provider())

    def test_claude_selected(self):
        with mock.patch.dict(os.environ, {"ASA_PHASE2_PROVIDER": "claude"}, clear=True):
            self.assertEqual(resolve_phase2_provider_name(), "claude")
            provider = resolve_external_phase2_provider()
            self.assertIsInstance(provider, ClaudeCliProvider)
            self.assertEqual(provider.name, "claude")

    def test_claude_env_config(self):
        env = {
            "ASA_PHASE2_PROVIDER": "claude",
            "ASA_CLAUDE_CLI": "/opt/bin/claude",
            "ASA_CLAUDE_MODEL": "sonnet",
            "ASA_CLAUDE_TIMEOUT_SECONDS": "120",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            provider = resolve_external_phase2_provider()
        self.assertEqual(provider.cli_path, "/opt/bin/claude")
        self.assertEqual(provider.model, "sonnet")
        self.assertEqual(provider.timeout_seconds, 120.0)


class FixtureContractTests(unittest.TestCase):
    def test_fixture_is_schema_valid(self):
        result = _fixture_phase2_result(_SAMPLE_PHASE1)
        self.assertTrue(_is_valid_phase2_shape(result))

    def test_fixture_citations_all_resolve(self):
        result = _fixture_phase2_result(_SAMPLE_PHASE1)
        invented = _validate_phase2_citation_paths(result, _SAMPLE_PHASE1)
        self.assertEqual(invented, [], f"fixture cited non-resolving paths: {invented}")


def _claude_cli_stdout(structured=None, raw=None, is_error=False):
    """Build a Claude CLI --output-format json stdout: event array ending in a result."""
    return json.dumps([
        {"type": "system", "subtype": "init"},
        {
            "type": "result",
            "subtype": "success" if not is_error else "error",
            "is_error": is_error,
            "result": raw,
            "structured_output": structured,
        },
    ])


def _completed(returncode=0, stdout="", stderr=""):
    import subprocess

    return subprocess.CompletedProcess(args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr)


class GeminiSchemaConversionTests(unittest.TestCase):
    def test_uppercase_types_lowered(self):
        gemini = {"type": "OBJECT", "properties": {"name": {"type": "STRING"}}, "required": ["name"]}
        converted = _gemini_schema_to_json_schema(gemini)
        self.assertEqual(converted["type"], "object")
        self.assertEqual(converted["properties"]["name"]["type"], "string")
        self.assertEqual(converted["required"], ["name"])

    def test_nested_arrays_and_items(self):
        gemini = {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"n": {"type": "NUMBER"}}}}
        converted = _gemini_schema_to_json_schema(gemini)
        self.assertEqual(converted["items"]["properties"]["n"]["type"], "number")

    def test_nullable_becomes_type_union(self):
        gemini = {"type": "STRING", "nullable": True}
        converted = _gemini_schema_to_json_schema(gemini)
        self.assertEqual(converted["type"], ["string", "null"])
        self.assertNotIn("nullable", converted)

    def test_real_phase2_schema_converts_cleanly(self):
        from server_phase2 import PHASE2_RESPONSE_SCHEMA

        converted = _gemini_schema_to_json_schema(PHASE2_RESPONSE_SCHEMA)
        serialized = json.dumps(converted)
        self.assertNotIn('"OBJECT"', serialized)
        self.assertNotIn('"STRING"', serialized)
        self.assertNotIn('"nullable"', serialized)


class ClaudeCliProviderTests(unittest.TestCase):
    def _request(self):
        return Phase2ProviderRequest(
            prompt="PROMPT",
            response_schema={"type": "OBJECT", "properties": {}},
            phase1_result=_SAMPLE_PHASE1,
            model_name="gemini-2.5-flash",
            request_id="req-c1",
            source_path="/does/not/matter.flac",
        )

    def test_success_prefers_structured_output(self):
        result = _fixture_phase2_result(_SAMPLE_PHASE1)
        provider = ClaudeCliProvider()
        with mock.patch("subprocess.run", return_value=_completed(stdout=_claude_cli_stdout(structured=result))) as run:
            response = provider.generate(self._request())
        self.assertEqual(json.loads(response.text), result)
        self.assertEqual(run.call_args.kwargs["input"], "PROMPT")

    def test_command_is_sandboxed_and_schema_enforced(self):
        provider = ClaudeCliProvider(model="sonnet")
        with mock.patch("subprocess.run", return_value=_completed(stdout=_claude_cli_stdout(structured={}))) as run:
            provider.generate(self._request())
        command = run.call_args.args[0]
        self.assertIn("--safe-mode", command)
        self.assertIn("--no-session-persistence", command)
        self.assertIn("--tools", command)
        self.assertEqual(command[command.index("--tools") + 1], "")
        schema_arg = command[command.index("--json-schema") + 1]
        self.assertEqual(json.loads(schema_arg)["type"], "object")
        self.assertEqual(command[command.index("--model") + 1], "sonnet")

    def test_model_flag_omitted_by_default(self):
        provider = ClaudeCliProvider()
        with mock.patch("subprocess.run", return_value=_completed(stdout=_claude_cli_stdout(structured={}))) as run:
            provider.generate(self._request())
        self.assertNotIn("--model", run.call_args.args[0])

    def test_raw_text_fallback_strips_fences(self):
        raw = "```json\n{\"trackCharacter\": \"warm\"}\n```"
        provider = ClaudeCliProvider()
        with mock.patch("subprocess.run", return_value=_completed(stdout=_claude_cli_stdout(raw=raw))):
            response = provider.generate(self._request())
        self.assertEqual(json.loads(response.text), {"trackCharacter": "warm"})

    def test_empty_result_yields_skip_text(self):
        provider = ClaudeCliProvider()
        with mock.patch("subprocess.run", return_value=_completed(stdout=_claude_cli_stdout())):
            response = provider.generate(self._request())
        self.assertIsNone(response.text)

    def test_error_result_raises(self):
        provider = ClaudeCliProvider()
        with mock.patch(
            "subprocess.run",
            return_value=_completed(stdout=_claude_cli_stdout(raw="rate limited", is_error=True)),
        ):
            with self.assertRaises(Phase2ProviderError) as ctx:
                provider.generate(self._request())
        self.assertEqual(ctx.exception.error_code, "CLAUDE_CLI_FAILED")

    def test_nonzero_exit_raises_retryable(self):
        provider = ClaudeCliProvider()
        with mock.patch("subprocess.run", return_value=_completed(returncode=1, stderr="boom")):
            with self.assertRaises(Phase2ProviderError) as ctx:
                provider.generate(self._request())
        self.assertEqual(ctx.exception.error_code, "CLAUDE_CLI_FAILED")
        self.assertTrue(ctx.exception.retryable)

    def test_nonzero_exit_surfaces_stdout_error_event(self):
        provider = ClaudeCliProvider()
        stdout = _claude_cli_stdout(raw="API rate limit reached", is_error=True)
        with mock.patch("subprocess.run", return_value=_completed(returncode=1, stdout=stdout)):
            with self.assertRaises(Phase2ProviderError) as ctx:
                provider.generate(self._request())
        self.assertIn("API rate limit reached", str(ctx.exception))

    def test_missing_binary_not_retryable(self):
        provider = ClaudeCliProvider(cli_path="/nope/claude")
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("no such file")):
            with self.assertRaises(Phase2ProviderError) as ctx:
                provider.generate(self._request())
        self.assertEqual(ctx.exception.error_code, "CLAUDE_CLI_UNAVAILABLE")
        self.assertFalse(ctx.exception.retryable)

    def test_timeout_raises_retryable(self):
        import subprocess

        provider = ClaudeCliProvider(timeout_seconds=1)
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=1)):
            with self.assertRaises(Phase2ProviderError) as ctx:
                provider.generate(self._request())
        self.assertEqual(ctx.exception.error_code, "CLAUDE_CLI_TIMEOUT")
        self.assertTrue(ctx.exception.retryable)

    def test_non_json_stdout_raises(self):
        provider = ClaudeCliProvider()
        with mock.patch("subprocess.run", return_value=_completed(stdout="Welcome to Claude!")):
            with self.assertRaises(Phase2ProviderError) as ctx:
                provider.generate(self._request())
        self.assertEqual(ctx.exception.error_code, "CLAUDE_CLI_BAD_OUTPUT")

    def test_single_result_object_supported(self):
        result = _fixture_phase2_result(_SAMPLE_PHASE1)
        single = json.dumps({"type": "result", "is_error": False, "structured_output": result, "result": "done"})
        provider = ClaudeCliProvider()
        with mock.patch("subprocess.run", return_value=_completed(stdout=single)):
            response = provider.generate(self._request())
        self.assertEqual(json.loads(response.text), result)


class ClaudeBranchIntegrationTests(unittest.TestCase):
    """Executes the server.py interpretation path through the claude branch."""

    @classmethod
    def setUpClass(cls):
        try:
            import server  # noqa: F401
        except Exception as exc:  # pragma: no cover - env-dependent
            raise unittest.SkipTest(f"server import unavailable (needs full venv): {exc}")

    def test_claude_provider_flows_through_shared_tail_without_gemini_key(self):
        import server

        result = _fixture_phase2_result(_SAMPLE_PHASE1)
        stdout = _claude_cli_stdout(structured=result)
        profile_config = server._resolve_interpretation_profile_config("producer_summary")
        with mock.patch.dict(
            os.environ,
            {"ASA_PHASE2_PROVIDER": "claude", "GEMINI_API_KEY": ""},
            clear=False,
        ), mock.patch("subprocess.run", return_value=_completed(stdout=stdout)) as run:
            execution = server._run_interpretation_request_with_profile_config(
                source_path=__file__,
                filename="loop.flac",
                file_size_bytes=123,
                profile_id="producer_summary",
                profile_config=profile_config,
                measurement_result=_SAMPLE_PHASE1,
                pitch_note_result=None,
                grounding_metadata={},
                model_name="gemini-2.5-flash",
                request_id="itest-claude-1",
            )
        self.assertTrue(execution["ok"], execution)
        self.assertIsNotNone(execution["interpretationResult"])
        self.assertTrue(_is_valid_phase2_shape(execution["interpretationResult"]))
        timings = (execution.get("diagnostics") or {}).get("timings") or {}
        self.assertIn("phase2-provider:claude", timings.get("flagsUsed", []))
        prompt_sent = run.call_args.kwargs["input"]
        self.assertIn('"bpm": 128.0', prompt_sent)

    def test_gemini_default_does_not_invoke_cli(self):
        import server

        with mock.patch.dict(
            os.environ, {"ASA_PHASE2_PROVIDER": "gemini", "GEMINI_API_KEY": ""}, clear=False
        ), mock.patch("subprocess.run") as run:
            execution = server._run_interpretation_request_with_profile_config(
                source_path=__file__,
                filename="loop.flac",
                file_size_bytes=123,
                profile_id="producer_summary",
                profile_config=server._resolve_interpretation_profile_config("producer_summary"),
                measurement_result=_SAMPLE_PHASE1,
                pitch_note_result=None,
                grounding_metadata={},
                model_name="gemini-2.5-flash",
                request_id="itest-gem-2",
            )
        run.assert_not_called()
        self.assertFalse(execution["ok"])
        self.assertEqual(execution["errorCode"], "GEMINI_NOT_CONFIGURED")


if __name__ == "__main__":
    unittest.main()

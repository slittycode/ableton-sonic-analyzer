import asyncio
import io
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

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
                "parameter": "Low shelf",
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
                "category": "Dynamics",
                "parameter": "Attack",
                "value": "3 ms",
                "reason": "Keep transients intact.",
                "advancedTip": "Drive lightly.",
            }
        ],
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
        self.assertIn("transcribe", properties)
        self.assertIn("separate", properties)

    def test_analysis_runs_endpoint_openapi_contract_exposes_stage_request_fields(
        self,
    ) -> None:
        properties = self._request_body_properties("/api/analysis-runs")

        self.assertIn("track", properties)
        self.assertIn("symbolic_mode", properties)
        self.assertIn("symbolic_backend", properties)
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
                        symbolic_mode="stem_notes",
                        symbolic_backend="auto",
                        interpretation_mode="async",
                        interpretation_profile="producer_summary",
                        interpretation_model="gemini-2.5-flash",
                    )
                )

        payload = self._decode_json_response(response)
        self.assertEqual(response.status_code, 200)
        self.assertIn("runId", payload)
        self.assertEqual(payload["stages"]["measurement"]["status"], "queued")
        self.assertEqual(payload["stages"]["symbolicExtraction"]["status"], "blocked")
        self.assertEqual(payload["stages"]["interpretation"]["status"], "blocked")

    def test_get_analysis_run_returns_persisted_stage_snapshot(self) -> None:
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_server_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            created = runtime.create_run(
                filename="track.mp3",
                content=b"fake-audio",
                mime_type="audio/mpeg",
                symbolic_mode="off",
                symbolic_backend="auto",
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
                    "label": "Basic Pitch on bass + other stems",
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
                    "label": "Basic Pitch on bass + other stems",
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
                "--transcribe",
            ],
        )
        self.assertEqual(run_mock.call_args.kwargs["timeout"], 218)
        build_estimate_mock.assert_called_once_with(214.6, True, True)
        payload = self._decode_json_response(response)
        self.assertEqual(payload["diagnostics"]["backendDurationMs"], 200.0)
        self.assertEqual(
            payload["diagnostics"]["timings"],
            {
                "totalMs": 245.0,
                "analysisMs": 200.0,
                "serverOverheadMs": 45.0,
                "flagsUsed": ["--separate", "--transcribe"],
                "fileSizeBytes": 10,
                "fileDurationSeconds": 214.6,
                "msPerSecondOfAudio": 0.93,
            },
        )
        print_mock.assert_called_once()
        self.assertIs(print_mock.call_args.kwargs["file"], server.sys.stderr)
        self.assertIn(
            "[TIMING] total=245.0ms analysis=200.0ms overhead=45.0ms",
            print_mock.call_args.args[0],
        )
        self.assertIn("flags=[--separate, --transcribe]", print_mock.call_args.args[0])
        self.assertIn(
            "fileSize=0.0MB duration=214.6s ms/s=0.93", print_mock.call_args.args[0]
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
                "spectralBalance": {"subBass": 0.0, "lowBass": 0.0, "mids": 0.0, "upperMids": 0.0, "highs": 0.0, "brilliance": 0.0},
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
                "spectralBalance": {"subBass": 0.0, "lowBass": 0.0, "mids": 0.0, "upperMids": 0.0, "highs": 0.0, "brilliance": 0.0},
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
                "flagsUsed": ["--separate", "--transcribe"],
                "fileSizeBytes": 10,
                "fileDurationSeconds": None,
                "msPerSecondOfAudio": None,
            },
        )
        print_mock.assert_called_once()
        self.assertIn("flags=[--separate, --transcribe]", print_mock.call_args.args[0])
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


class Phase2EndpointTests(unittest.TestCase):
    """Tests for the /api/phase2 Gemini advisory endpoint."""

    def _upload_file(self, content: bytes = b"fake-audio", filename: str = "track.mp3") -> UploadFile:
        return UploadFile(filename=filename, file=io.BytesIO(content))

    def _decode(self, response) -> dict:
        return json.loads(response.body.decode("utf-8"))

    def _run(self, coro):
        return asyncio.run(coro)

    def _make_completed_run(self, runtime, *, legacy_request_id: str | None = None) -> str:
        created = runtime.create_run(
            filename="track.mp3",
            content=b"server-owned-audio",
            mime_type="audio/mpeg",
            symbolic_mode="off",
            symbolic_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
            legacy_request_id=legacy_request_id,
        )
        runtime.complete_measurement(
            created["runId"],
            payload={"bpm": 128, "key": "A minor", "durationSeconds": 60.0},
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
                symbolic_mode="off",
                symbolic_backend="auto",
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
            runtime.create_symbolic_attempt(
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
        self.assertIn("OPTIONAL_SYMBOLIC_EXTRACTION_RESULT_JSON", prompt)
        self.assertIn("GROUNDING_METADATA", prompt)
        self.assertIn('"bpm": 128', prompt)
        self.assertNotIn('"bpm": 999', prompt)
        self.assertIn('"transcriptionMethod": "stub-backend"', prompt)

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
        "spectralBalance": {"subBass": 0.0, "lowBass": 0.0, "mids": 0.0,
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
                "spectralBalance": {"subBass": 0.0, "lowBass": 0.0, "mids": 0.0, "upperMids": 0.0, "highs": 0.0, "brilliance": 0.0},
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
            self.assertEqual(snapshot["stages"]["symbolicExtraction"]["status"], "queued")
            self.assertIsNone(snapshot["stages"]["symbolicExtraction"]["result"])


class StageWorkerTests(unittest.TestCase):
    def test_reserved_measurement_job_uses_runtime_symbolic_mode_resolution(self) -> None:
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_measurement_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            created = runtime.create_run(
                filename="track.mp3",
                content=b"fake-audio",
                mime_type="audio/mpeg",
                symbolic_mode="stem_notes",
                symbolic_backend="auto",
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
            run_separation=True,
            run_transcribe=True,
            run_fast=False,
        )

    def test_reserved_measurement_job_fails_measurement_for_unsupported_symbolic_mode(self) -> None:
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_measurement_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            created = runtime.create_run(
                filename="track.mp3",
                content=b"fake-audio",
                mime_type="audio/mpeg",
                symbolic_mode="melody_only",
                symbolic_backend="auto",
                interpretation_mode="off",
                interpretation_profile="producer_summary",
                interpretation_model=None,
            )
            job = runtime.reserve_next_measurement_run()

            result = server._execute_reserved_measurement_job(runtime, job)

            self.assertFalse(result["ok"])
            self.assertEqual(result["errorCode"], "SYMBOLIC_MODE_UNSUPPORTED")
            snapshot = runtime.get_run(created["runId"])
            self.assertEqual(snapshot["stages"]["measurement"]["status"], "failed")
            self.assertEqual(snapshot["stages"]["measurement"]["error"]["code"], "SYMBOLIC_MODE_UNSUPPORTED")

    def test_symbolic_worker_uses_analyze_transcription_protocol_entry_point(self) -> None:
        from analysis_runtime import AnalysisRuntime

        with tempfile.TemporaryDirectory(prefix="asa_symbolic_runtime_") as temp_dir:
            runtime = AnalysisRuntime(Path(temp_dir) / "runtime")
            created = runtime.create_run(
                filename="track.mp3",
                content=b"fake-audio",
                mime_type="audio/mpeg",
                symbolic_mode="stem_notes",
                symbolic_backend="auto",
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
            attempt_id = runtime.create_symbolic_attempt(
                created["runId"],
                backend_id="auto",
                mode="stem_notes",
                status="queued",
            )
            runtime.reserve_symbolic_attempt(attempt_id)

            stem_dir = Path(temp_dir) / "mock_stems"
            stem_dir.mkdir(parents=True, exist_ok=True)
            bass_path = stem_dir / "bass.wav"
            other_path = stem_dir / "other.wav"
            bass_path.write_bytes(b"bass")
            other_path.write_bytes(b"other")

            with (
                patch.object(
                    server,
                    "separate_stems",
                    return_value={"bass": str(bass_path), "other": str(other_path)},
                ),
                patch.object(
                    server,
                    "analyze_transcription",
                    return_value={
                        "transcriptionDetail": {
                            "transcriptionMethod": "stub-backend",
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
                    },
                ) as analyze_transcription_mock,
            ):
                server._execute_symbolic_attempt(
                    runtime,
                    {
                        "attemptId": attempt_id,
                        "runId": created["runId"],
                        "backendId": "auto",
                        "mode": "stem_notes",
                    },
                )

            analyze_transcription_mock.assert_called_once()
            kwargs = analyze_transcription_mock.call_args.kwargs
            self.assertIn("stem_paths", kwargs)
            self.assertEqual(set(kwargs["stem_paths"].keys()), {"bass", "other"})
            snapshot = runtime.get_run(created["runId"])
            self.assertEqual(snapshot["stages"]["symbolicExtraction"]["status"], "completed")
            self.assertEqual(
                snapshot["stages"]["symbolicExtraction"]["result"]["transcriptionMethod"],
                "stub-backend",
            )


if __name__ == "__main__":
    unittest.main()

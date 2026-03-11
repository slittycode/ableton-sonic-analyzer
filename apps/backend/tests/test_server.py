import asyncio
import io
import json
import subprocess
import unittest
from datetime import datetime, timedelta
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


if __name__ == "__main__":
    unittest.main()

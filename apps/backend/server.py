import asyncio
import base64
import json
import logging
import mimetypes
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from math import ceil
from math import isfinite
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

try:
    from google import genai as _genai
    from google.genai import types as _genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    _genai = None  # type: ignore[assignment]
    _genai_types = None  # type: ignore[assignment]
    _GENAI_AVAILABLE = False

from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from python_multipart.multipart import MultipartParseError, MultipartParser, parse_options_header

from analysis_runtime import (
    AnalysisRuntime,
    UnsupportedPitchNoteBackendError,
    UnsupportedPitchNoteModeError,
)
from analyze import (
    build_analysis_estimate,
    get_audio_duration_seconds,
)
import upload_limits
from utils.cleanup import cleanup_artifacts


app = FastAPI(title="Sonic Analyzer Local API")

ANALYZE_TIMEOUT_BUFFER_SECONDS = 120
ANALYZE_TIMEOUT_FLOOR_SECONDS = 300
ANALYZE_TIMEOUT_FALLBACK_SECONDS = 900
ANALYZE_TIMEOUT_ESTIMATE_MULTIPLIER = 2.0
ERROR_PHASE_LOCAL_DSP = "phase1_local_dsp"
ERROR_PHASE_GEMINI = "phase2_gemini"
ENGINE_VERSION = "analyze.py"
MAX_SNIPPET_LENGTH = 2000
DEFAULT_SERVER_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 8100
INLINE_SIZE_LIMIT = 104_857_600  # 100 MiB — confirmed by Google on 2026-01-12
ARTIFACT_CLEANUP_INTERVAL_SECONDS = 3_600
WORKER_IDLE_SECONDS = 0.25
ALLOWED_GEMINI_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3-flash-preview",
    "gemini-3-pro-preview",
    "gemini-3.1-flash-preview",
    "gemini-3.1-pro-preview",
}
GEMINI_TIMEOUT_SECONDS = 300  # 5 minutes — matches TS httpOptions.timeout
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_BASE_DELAY_MS = 2_000
GEMINI_RETRYABLE_SUBSTRINGS = [
    "503",
    "high demand",
    "429",
    "quota",
    "UNAVAILABLE",
    "peer closed connection",
    "incomplete chunked read",
    "RemoteProtocolError",
    "ConnectionError",
    "ConnectionResetError",
]

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_ANALYSIS_RUNTIME: AnalysisRuntime | None = None
_BACKGROUND_TASKS: list[asyncio.Task[Any]] = []
logger = logging.getLogger(__name__)
_ACTIVE_CHILD_PROCESSES: dict[tuple[str, str], subprocess.Popen[Any]] = {}
_ACTIVE_CHILD_PROCESSES_LOCK = threading.Lock()
_ALLOWED_LIVE12_DEVICE_FAMILIES = {"NATIVE", "MAX_FOR_LIVE"}
_ALLOWED_LIVE12_DEVICE_CLASSES = {
    "instrument",
    "audio_effect",
    "midi_effect",
    "utility",
    "routing",
    "mastering",
}
_ALLOWED_PHASE2_RECOMMENDATION_CATEGORIES = {
    "SYNTHESIS",
    "DYNAMICS",
    "EQ",
    "EFFECTS",
    "STEREO",
    "MASTERING",
    "MIDI",
    "ROUTING",
}
_ALLOWED_PHASE2_WORKFLOW_STAGES = {
    "PROJECT_SETUP",
    "SOUND_DESIGN",
    "ARRANGEMENT",
    "MIX",
    "MASTER",
}
_ALLOWED_PHASE2_WARP_MODES = {
    "Beats",
    "Tones",
    "Texture",
    "Re-Pitch",
    "Complex",
    "Complex Pro",
}
_DEVICE_FAMILY_COERCION: dict[str, str] = {
    "STOCK": "NATIVE",
    "BUILT_IN": "NATIVE",
    "BUILT-IN": "NATIVE",
    "BUILTIN": "NATIVE",
    "ABLETON": "NATIVE",
    "LIVE": "NATIVE",
    "THIRD_PARTY": "MAX_FOR_LIVE",
    "PLUGIN": "MAX_FOR_LIVE",
    "M4L": "MAX_FOR_LIVE",
    "MAX4LIVE": "MAX_FOR_LIVE",
}
_WORKFLOW_STAGE_COERCION: dict[str, str] = {
    "SYNTHESIS": "SOUND_DESIGN",
    "PATCHING": "SOUND_DESIGN",
    "PRODUCTION": "SOUND_DESIGN",
    "COMPOSITION": "ARRANGEMENT",
    "RECORDING": "PROJECT_SETUP",
    "MIXING": "MIX",
    "MASTERING": "MASTER",
    "MIXDOWN": "MIX",
}
_RECOMMENDATION_CATEGORY_COERCION: dict[str, str] = {
    "DRUMS": "DYNAMICS",
    "COMPRESSION": "DYNAMICS",
    "SATURATION": "DYNAMICS",
    "SPACE": "EFFECTS",
    "REVERB": "EFFECTS",
    "DELAY": "EFFECTS",
    "MODULATION": "EFFECTS",
    "DISTORTION": "EFFECTS",
    "FILTERING": "EQ",
    "PANNING": "STEREO",
    "IMAGING": "STEREO",
    "WIDTH": "STEREO",
    "LIMITING": "MASTERING",
    "LOUDNESS": "MASTERING",
    "SEQUENCING": "MIDI",
    "AUTOMATION": "ROUTING",
}

LEGACY_ENDPOINT_SUNSET = "Wed, 31 Dec 2026 23:59:59 GMT"


class UploadTooLargeError(ValueError):
    def __init__(self, limit_bytes: int):
        self.limit_bytes = limit_bytes
        super().__init__(
            f"Uploaded audio exceeds the backend upload limit of {limit_bytes} bytes."
        )


def _load_prompt_template(name: str) -> str:
    path = _PROMPTS_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuntimeError(
            f"Prompt template '{name}' not found at {path}. "
            "Re-run from the apps/backend directory."
        ) from None


def _load_live12_device_catalog(path: Path | None = None) -> dict[str, Any]:
    catalog_path = path or (_PROMPTS_DIR / "live12_device_catalog.json")
    try:
        raw = catalog_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuntimeError(
            f"Live 12 device catalog not found at {catalog_path}. "
            "Add apps/backend/prompts/live12_device_catalog.json before starting Phase A."
        ) from None

    try:
        catalog = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Live 12 device catalog at {catalog_path} contains invalid JSON: {exc}"
        ) from exc

    if not isinstance(catalog, dict):
        raise RuntimeError("Live 12 device catalog must be a JSON object with a devices array.")

    devices = catalog.get("devices")
    if not isinstance(devices, list) or not devices:
        raise RuntimeError("Live 12 device catalog must contain a non-empty devices array.")

    seen_names: set[str] = set()
    for index, device in enumerate(devices):
        if not isinstance(device, dict):
            raise RuntimeError(f"Live 12 device catalog entry {index} must be an object.")

        name = device.get("name")
        family = device.get("family")
        device_class = device.get("class")
        allowed_parameters = device.get("allowedParameters")

        if not isinstance(name, str) or not name.strip():
            raise RuntimeError(f"Live 12 device catalog entry {index} is missing a valid name.")
        if name in seen_names:
            raise RuntimeError(f"Live 12 device catalog contains a duplicate device name: {name}")
        seen_names.add(name)

        if family not in _ALLOWED_LIVE12_DEVICE_FAMILIES:
            raise RuntimeError(
                f"Live 12 device catalog entry '{name}' has invalid family '{family}'."
            )
        if device_class not in _ALLOWED_LIVE12_DEVICE_CLASSES:
            raise RuntimeError(
                f"Live 12 device catalog entry '{name}' has invalid class '{device_class}'."
            )
        if (
            not isinstance(allowed_parameters, list)
            or not allowed_parameters
            or not all(isinstance(item, str) and item.strip() for item in allowed_parameters)
        ):
            raise RuntimeError(
                f"Live 12 device catalog entry '{name}' must have a non-empty allowedParameters array."
            )

    return catalog


def _mark_legacy_endpoint_response(response: JSONResponse, *, endpoint: str) -> JSONResponse:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = LEGACY_ENDPOINT_SUNSET
    response.headers["Link"] = '</api/analysis-runs>; rel="successor-version"'
    response.headers["Warning"] = (
        f'299 - "{endpoint} is deprecated; use /api/analysis-runs instead."'
    )
    return response


def _scope_header_value(scope: dict[str, Any], header_name: bytes) -> str | None:
    for name, value in scope.get("headers", []):
        if name.lower() != header_name:
            continue
        try:
            return value.decode("latin-1")
        except UnicodeDecodeError:
            return None
    return None


class _MultipartTrackSizeCounter:
    def __init__(self, *, content_type_header: str | None, track_field_name: str, limit_bytes: int) -> None:
        self.limit_bytes = limit_bytes
        self.track_field_name = track_field_name
        self.track_bytes = 0
        self.overflowed = False
        self.disabled = False
        self._current_headers: dict[bytes, bytes] = {}
        self._current_header_field = bytearray()
        self._current_header_value = bytearray()
        self._current_part_is_track_file = False
        self._parser = self._build_parser(content_type_header)

    def _build_parser(self, content_type_header: str | None) -> MultipartParser | None:
        content_type, options = parse_options_header(content_type_header)
        if content_type != b"multipart/form-data":
            return None
        boundary = options.get(b"boundary")
        if not boundary:
            return None
        return MultipartParser(
            boundary,
            callbacks={
                "on_part_begin": self.on_part_begin,
                "on_header_begin": self.on_header_begin,
                "on_header_field": self.on_header_field,
                "on_header_value": self.on_header_value,
                "on_header_end": self.on_header_end,
                "on_headers_finished": self.on_headers_finished,
                "on_part_data": self.on_part_data,
                "on_part_end": self.on_part_end,
            },
        )

    def feed(self, chunk: bytes) -> None:
        if not chunk or self._parser is None or self.disabled or self.overflowed:
            return
        try:
            self._parser.write(chunk)
        except MultipartParseError:
            self.disabled = True

    def on_part_begin(self) -> None:
        self._current_headers = {}
        self._current_header_field = bytearray()
        self._current_header_value = bytearray()
        self._current_part_is_track_file = False

    def on_header_begin(self) -> None:
        self._current_header_field = bytearray()
        self._current_header_value = bytearray()

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._current_header_field.extend(data[start:end])

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._current_header_value.extend(data[start:end])

    def on_header_end(self) -> None:
        if not self._current_header_field:
            return
        self._current_headers[
            bytes(self._current_header_field).lower()
        ] = bytes(self._current_header_value)

    def on_headers_finished(self) -> None:
        disposition = self._current_headers.get(b"content-disposition")
        if disposition is None:
            return
        _, options = parse_options_header(disposition)
        field_name = options.get(b"name")
        self._current_part_is_track_file = (
            field_name == self.track_field_name.encode("utf-8")
            and b"filename" in options
        )

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if not self._current_part_is_track_file:
            return
        self.track_bytes += end - start
        if self.track_bytes > self.limit_bytes:
            self.overflowed = True

    def on_part_end(self) -> None:
        self._current_part_is_track_file = False


class UploadSizeLimitMiddleware:
    def __init__(self, app: Callable[..., Any]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or scope.get("path") not in upload_limits.UPLOAD_LIMITED_POST_PATHS
        ):
            await self.app(scope, receive, send)
            return

        raw_limit_bytes = upload_limits.MAX_UPLOAD_SIZE_BYTES
        request_limit_bytes = upload_limits.MAX_UPLOAD_REQUEST_BYTES
        content_length = _scope_header_value(scope, b"content-length")
        try:
            declared_length = int(content_length) if content_length is not None else None
        except ValueError:
            declared_length = None
        if declared_length is not None and declared_length > request_limit_bytes:
            response = _upload_too_large_response_for_path(scope["path"], limit_bytes=raw_limit_bytes)
            await response(scope, receive, send)
            return

        size_counter = _MultipartTrackSizeCounter(
            content_type_header=_scope_header_value(scope, b"content-type"),
            track_field_name="track",
            limit_bytes=raw_limit_bytes,
        )
        overflowed = False
        response_started = False
        synthetic_response_sent = False

        def send_upload_limit_response() -> JSONResponse:
            return _upload_too_large_response_for_path(scope["path"], limit_bytes=raw_limit_bytes)

        async def limited_receive() -> dict[str, Any]:
            nonlocal overflowed
            if overflowed:
                return {"type": "http.disconnect"}
            message = await receive()
            if message.get("type") != "http.request":
                return message
            body = message.get("body", b"")
            if isinstance(body, bytes):
                size_counter.feed(body)
            if size_counter.overflowed:
                overflowed = True
                return {"type": "http.disconnect"}
            return message

        async def tracked_send(message: dict[str, Any]) -> None:
            nonlocal response_started, synthetic_response_sent
            if overflowed:
                if not synthetic_response_sent:
                    synthetic_response_sent = True
                    response_started = True
                    await send_upload_limit_response()(scope, receive, send)
                return
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except UploadTooLargeError:
            if response_started:
                raise
            await send_upload_limit_response()(scope, receive, send)
            return

        if overflowed and not synthetic_response_sent and not response_started:
            await send_upload_limit_response()(scope, receive, send)


def _register_active_child_process(
    run_id: str,
    stage_key: str,
    process: subprocess.Popen[Any],
) -> None:
    with _ACTIVE_CHILD_PROCESSES_LOCK:
        _ACTIVE_CHILD_PROCESSES[(run_id, stage_key)] = process


def _unregister_active_child_process(
    run_id: str,
    stage_key: str,
    process: subprocess.Popen[Any],
) -> None:
    with _ACTIVE_CHILD_PROCESSES_LOCK:
        existing = _ACTIVE_CHILD_PROCESSES.get((run_id, stage_key))
        if existing is process:
            _ACTIVE_CHILD_PROCESSES.pop((run_id, stage_key), None)


def _terminate_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def _interrupt_active_child_processes(run_id: str) -> list[str]:
    with _ACTIVE_CHILD_PROCESSES_LOCK:
        active = [
            (stage_key, process)
            for (candidate_run_id, stage_key), process in _ACTIVE_CHILD_PROCESSES.items()
            if candidate_run_id == run_id
        ]

    interrupted_stages: list[str] = []
    for stage_key, process in active:
        _terminate_process(process)
        interrupted_stages.append(stage_key)
    return interrupted_stages


PRODUCER_SUMMARY_PROMPT_TEMPLATE = _load_prompt_template("phase2_system.txt")
STEM_SUMMARY_PROMPT_TEMPLATE = _load_prompt_template("stem_summary_system.txt")
LIVE12_DEVICE_CATALOG = _load_live12_device_catalog()
LIVE12_DEVICE_LOOKUP = {
    device["name"]: device for device in LIVE12_DEVICE_CATALOG["devices"]
}
PHASE2_PROMPT_TEMPLATE = PRODUCER_SUMMARY_PROMPT_TEMPLATE
PRODUCER_SUMMARY_PROMPT_VERSION = "producer_summary.phase_abcd2.current"
SUPPORTED_INTERPRETATION_PROFILES = {"producer_summary", "stem_summary"}

PHASE2_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "trackCharacter": {"type": "STRING"},
        "projectSetup": {
            "type": "OBJECT",
            "properties": {
                "tempoBpm": {"type": "NUMBER"},
                "timeSignature": {"type": "STRING"},
                "sampleRate": {"type": "NUMBER"},
                "bitDepth": {"type": "NUMBER"},
                "headroomTarget": {"type": "STRING"},
                "sessionGoal": {"type": "STRING"},
            },
            "required": [
                "tempoBpm",
                "timeSignature",
                "sampleRate",
                "bitDepth",
                "headroomTarget",
                "sessionGoal",
            ],
        },
        "trackLayout": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "order": {"type": "NUMBER"},
                    "name": {"type": "STRING"},
                    "type": {"type": "STRING"},
                    "purpose": {"type": "STRING"},
                    "grounding": {
                        "type": "OBJECT",
                        "properties": {
                            "phase1Fields": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"},
                            },
                            "segmentIndexes": {
                                "type": "ARRAY",
                                "items": {"type": "NUMBER"},
                            },
                        },
                        "required": ["phase1Fields"],
                    },
                },
                "required": ["order", "name", "type", "purpose", "grounding"],
            },
        },
        "routingBlueprint": {
            "type": "OBJECT",
            "properties": {
                "sidechainSource": {"type": "STRING"},
                "sidechainTargets": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "returns": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "name": {"type": "STRING"},
                            "purpose": {"type": "STRING"},
                            "sendSources": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"},
                            },
                            "deviceFocus": {"type": "STRING"},
                            "levelGuidance": {"type": "STRING"},
                        },
                        "required": [
                            "name",
                            "purpose",
                            "sendSources",
                            "deviceFocus",
                            "levelGuidance",
                        ],
                    },
                },
                "notes": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
            },
            "required": ["sidechainTargets", "returns", "notes"],
        },
        "warpGuide": {
            "type": "OBJECT",
            "properties": {
                "fullTrack": {
                    "type": "OBJECT",
                    "properties": {
                        "warpMode": {"type": "STRING"},
                        "settings": {"type": "STRING"},
                        "reason": {"type": "STRING"},
                    },
                    "required": ["warpMode", "reason"],
                },
                "drums": {
                    "type": "OBJECT",
                    "properties": {
                        "warpMode": {"type": "STRING"},
                        "settings": {"type": "STRING"},
                        "reason": {"type": "STRING"},
                    },
                    "required": ["warpMode", "reason"],
                },
                "bass": {
                    "type": "OBJECT",
                    "properties": {
                        "warpMode": {"type": "STRING"},
                        "settings": {"type": "STRING"},
                        "reason": {"type": "STRING"},
                    },
                    "required": ["warpMode", "reason"],
                },
                "melodic": {
                    "type": "OBJECT",
                    "properties": {
                        "warpMode": {"type": "STRING"},
                        "settings": {"type": "STRING"},
                        "reason": {"type": "STRING"},
                    },
                    "required": ["warpMode", "reason"],
                },
                "vocals": {
                    "type": "OBJECT",
                    "properties": {
                        "warpMode": {"type": "STRING"},
                        "settings": {"type": "STRING"},
                        "reason": {"type": "STRING"},
                    },
                    "required": ["warpMode", "reason"],
                },
                "rationale": {"type": "STRING"},
            },
            "required": ["fullTrack", "drums", "bass", "melodic", "rationale"],
        },
        "detectedCharacteristics": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "confidence": {"type": "STRING"},
                    "explanation": {"type": "STRING"},
                },
                "required": ["name", "confidence", "explanation"],
            },
        },
        "audioObservations": {
            "type": "OBJECT",
            "properties": {
                "soundDesignFingerprint": {"type": "STRING"},
                "elementCharacter": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "element": {"type": "STRING"},
                            "description": {"type": "STRING"},
                        },
                        "required": ["element", "description"],
                    },
                },
                "productionSignatures": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "mixContext": {"type": "STRING"},
            },
            "required": [
                "soundDesignFingerprint",
                "elementCharacter",
                "productionSignatures",
                "mixContext",
            ],
        },
        "arrangementOverview": {
            "type": "OBJECT",
            "properties": {
                "summary": {"type": "STRING"},
                "segments": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "index": {"type": "NUMBER"},
                            "startTime": {"type": "NUMBER"},
                            "endTime": {"type": "NUMBER"},
                            "lufs": {"type": "NUMBER"},
                            "description": {"type": "STRING"},
                            "spectralNote": {"type": "STRING"},
                            "sceneName": {"type": "STRING"},
                            "abletonAction": {"type": "STRING"},
                            "automationFocus": {"type": "STRING"},
                        },
                        "required": [
                            "index",
                            "startTime",
                            "endTime",
                            "description",
                            "sceneName",
                            "abletonAction",
                            "automationFocus",
                        ],
                    },
                },
                "noveltyNotes": {"type": "STRING"},
            },
            "required": ["summary", "segments"],
        },
        "sonicElements": {
            "type": "OBJECT",
            "properties": {
                "kick": {"type": "STRING"},
                "bass": {"type": "STRING"},
                "melodicArp": {"type": "STRING"},
                "grooveAndTiming": {"type": "STRING"},
                "effectsAndTexture": {"type": "STRING"},
                "widthAndStereo": {"type": "STRING"},
                "harmonicContent": {"type": "STRING"},
            },
            "required": ["kick", "bass", "melodicArp", "grooveAndTiming", "effectsAndTexture"],
        },
        "mixAndMasterChain": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "order": {"type": "NUMBER"},
                    "device": {"type": "STRING"},
                    "deviceFamily": {"type": "STRING"},
                    "trackContext": {"type": "STRING"},
                    "workflowStage": {"type": "STRING"},
                    "parameter": {"type": "STRING"},
                    "value": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                },
                "required": [
                    "order",
                    "device",
                    "deviceFamily",
                    "trackContext",
                    "workflowStage",
                    "parameter",
                    "value",
                    "reason",
                ],
            },
        },
        "secretSauce": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING"},
                "icon": {"type": "STRING"},
                "explanation": {"type": "STRING"},
                "implementationSteps": {"type": "ARRAY", "items": {"type": "STRING"}},
                "workflowSteps": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "step": {"type": "NUMBER"},
                            "trackContext": {"type": "STRING"},
                            "device": {"type": "STRING"},
                            "parameter": {"type": "STRING"},
                            "value": {"type": "STRING"},
                            "instruction": {"type": "STRING"},
                            "measurementJustification": {"type": "STRING"},
                        },
                        "required": [
                            "step",
                            "trackContext",
                            "device",
                            "parameter",
                            "value",
                            "instruction",
                            "measurementJustification",
                        ],
                    },
                },
            },
            "required": ["title", "explanation", "implementationSteps", "workflowSteps"],
        },
        "confidenceNotes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "field": {"type": "STRING"},
                    "value": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                },
                "required": ["field", "value", "reason"],
            },
        },
        "abletonRecommendations": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "device": {"type": "STRING"},
                    "deviceFamily": {"type": "STRING"},
                    "trackContext": {"type": "STRING"},
                    "workflowStage": {"type": "STRING"},
                    "category": {"type": "STRING"},
                    "parameter": {"type": "STRING"},
                    "value": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                    "advancedTip": {"type": "STRING"},
                },
                "required": [
                    "device",
                    "deviceFamily",
                    "trackContext",
                    "workflowStage",
                    "category",
                    "parameter",
                    "value",
                    "reason",
                    "advancedTip",
                ],
            },
        },
    },
    "required": [
        "trackCharacter",
        "projectSetup",
        "trackLayout",
        "routingBlueprint",
        "warpGuide",
        "detectedCharacteristics",
        "arrangementOverview",
        "sonicElements",
        "mixAndMasterChain",
        "secretSauce",
        "confidenceNotes",
        "abletonRecommendations",
    ],
}
STEM_SUMMARY_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "bars": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "barStart": {"type": "NUMBER"},
                    "barEnd": {"type": "NUMBER"},
                    "startTime": {"type": "NUMBER"},
                    "endTime": {"type": "NUMBER"},
                    "noteHypotheses": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "scaleDegreeHypotheses": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "rhythmicPattern": {"type": "STRING"},
                    "uncertaintyLevel": {"type": "STRING"},
                    "uncertaintyReason": {"type": "STRING"},
                },
                "required": [
                    "barStart",
                    "barEnd",
                    "startTime",
                    "endTime",
                    "noteHypotheses",
                    "scaleDegreeHypotheses",
                    "rhythmicPattern",
                    "uncertaintyLevel",
                    "uncertaintyReason",
                ],
            },
        },
        "globalPatterns": {
            "type": "OBJECT",
            "properties": {
                "bassRole": {"type": "STRING"},
                "melodicRole": {"type": "STRING"},
                "pumpingOrModulation": {"type": "STRING"},
            },
            "required": ["bassRole", "melodicRole", "pumpingOrModulation"],
        },
        "uncertaintyFlags": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["summary", "bars", "globalPatterns", "uncertaintyFlags"],
}
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3100",
    "http://127.0.0.1:3100",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(UploadSizeLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _start_background_tasks() -> None:
    runtime = get_analysis_runtime()
    runtime.recover_incomplete_attempts()
    logger.info(
        "Upload limits configured: raw_audio_limit_bytes=%s edge_request_limit_bytes=%s",
        upload_limits.MAX_UPLOAD_SIZE_BYTES,
        upload_limits.MAX_UPLOAD_REQUEST_BYTES,
    )

    if not _BACKGROUND_TASKS:
        _BACKGROUND_TASKS.extend(
            [
                asyncio.create_task(_artifact_cleanup_loop(runtime.runtime_dir)),
                asyncio.create_task(_measurement_worker_loop()),
                asyncio.create_task(_pitch_note_worker_loop()),
                asyncio.create_task(_interpretation_worker_loop()),
            ]
        )


async def _artifact_cleanup_loop(runtime_dir: Path) -> None:
    while True:
        try:
            await asyncio.to_thread(cleanup_artifacts, runtime_dir)
        except Exception as exc:
            logger.warning("[warn] artifact cleanup failed: %s", exc)
        await asyncio.sleep(ARTIFACT_CLEANUP_INTERVAL_SECONDS)


@app.on_event("shutdown")
async def _stop_background_tasks() -> None:
    global _BACKGROUND_TASKS
    for task in _BACKGROUND_TASKS:
        task.cancel()
    _BACKGROUND_TASKS = []
    with _ACTIVE_CHILD_PROCESSES_LOCK:
        active = list(_ACTIVE_CHILD_PROCESSES.values())
        _ACTIVE_CHILD_PROCESSES.clear()
    for process in active:
        _terminate_process(process)


def _coerce_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        numeric = float(value)
        if isfinite(numeric):
            return numeric
    return default


def _coerce_string(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _coerce_nullable_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None


def _coerce_positive_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        numeric = int(round(float(value)))
        return numeric if numeric >= 0 else default
    return default


def _coerce_nullable_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if isfinite(numeric):
            return numeric
    return None


def _current_time() -> datetime:
    return datetime.now()


def resolve_runtime_dir() -> Path:
    raw_value = os.getenv("SONIC_ANALYZER_RUNTIME_DIR", "").strip()
    if raw_value:
        return Path(raw_value)
    return Path(__file__).parent / ".runtime"


def get_analysis_runtime() -> AnalysisRuntime:
    global _ANALYSIS_RUNTIME
    if _ANALYSIS_RUNTIME is None:
        _ANALYSIS_RUNTIME = AnalysisRuntime(resolve_runtime_dir())
    return _ANALYSIS_RUNTIME


def resolve_server_port() -> int:
    raw_value = os.getenv("SONIC_ANALYZER_PORT", str(DEFAULT_SERVER_PORT)).strip()
    try:
        port = int(raw_value)
    except ValueError:
        return DEFAULT_SERVER_PORT
    if 0 < port <= 65535:
        return port
    return DEFAULT_SERVER_PORT


def _elapsed_ms(started_at: datetime | None, ended_at: datetime | None) -> float:
    if started_at is None or ended_at is None:
        return 0.0
    return max((ended_at - started_at).total_seconds() * 1000, 0.0)


def _normalize_run_snapshot(
    snapshot: dict[str, Any], runtime: AnalysisRuntime | None = None
) -> dict[str, Any]:
    """Apply _build_phase1 normalization to a run snapshot's measurement result.

    The analysis-run pathway stores raw analyze.py output in the DB, but the
    frontend parser (parsePhase1Result) expects the same normalized shape that
    _build_phase1 produces for the legacy /api/analyze endpoint — notably,
    top-level stereoWidth/stereoCorrelation extracted from stereoDetail.

    When *runtime* is provided, spectral visualization artifacts (spectrogram
    PNGs and time-series JSON) are attached under ``artifacts.spectral``.
    """
    stages = snapshot.get("stages")
    if not isinstance(stages, dict):
        return snapshot
    measurement = stages.get("measurement")
    if not isinstance(measurement, dict):
        return snapshot
    raw_result = measurement.get("result")
    if not isinstance(raw_result, dict):
        return snapshot
    snapshot = dict(snapshot)
    snapshot["stages"] = dict(stages)
    snapshot["stages"]["measurement"] = dict(measurement)
    snapshot["stages"]["measurement"]["result"] = _build_phase1(raw_result)

    if runtime is not None:
        run_id = snapshot.get("runId")
        if run_id:
            snapshot = dict(snapshot)
            snapshot["artifacts"] = dict(snapshot.get("artifacts") or {})
            spectral_artifacts = runtime.get_artifacts_by_kind(run_id, "spectrogram")
            ts_artifacts = runtime.get_artifacts_by_kind(run_id, "spectral_time_series")
            _strip_internal = lambda a: {
                "artifactId": a["artifactId"],
                "kind": a["kind"],
                "filename": a["filename"],
                "mimeType": a["mimeType"],
                "sizeBytes": a["sizeBytes"],
            }
            onset_artifacts = runtime.get_artifacts_by_kind(run_id, "onset_strength")
            chroma_artifacts = runtime.get_artifacts_by_kind(run_id, "chroma_interactive")
            snapshot["artifacts"]["spectral"] = {
                "spectrograms": [_strip_internal(a) for a in spectral_artifacts],
                "timeSeries": _strip_internal(ts_artifacts[0]) if ts_artifacts else None,
                "onsetStrength": _strip_internal(onset_artifacts[0]) if onset_artifacts else None,
                "chromaInteractive": _strip_internal(chroma_artifacts[0]) if chroma_artifacts else None,
            }

    return snapshot


def _normalize_spectral_detail(detail: Any) -> dict[str, Any] | None:
    """Map analyzer field names to the frontend-expected SpectralDetail contract.

    The analyzer emits ``spectralCentroid`` / ``spectralRolloff`` (singular) but
    the frontend ``SpectralDetail`` interface expects ``spectralCentroidMean`` /
    ``spectralRolloffMean``.
    """
    if not isinstance(detail, dict):
        return None
    out = dict(detail)
    if "spectralCentroid" in out and "spectralCentroidMean" not in out:
        out["spectralCentroidMean"] = out.pop("spectralCentroid")
    if "spectralRolloff" in out and "spectralRolloffMean" not in out:
        out["spectralRolloffMean"] = out.pop("spectralRolloff")
    if "spectralBandwidth" in out and "spectralBandwidthMean" not in out:
        out["spectralBandwidthMean"] = out.pop("spectralBandwidth")
    if "spectralFlatness" in out and "spectralFlatnessMean" not in out:
        out["spectralFlatnessMean"] = out.pop("spectralFlatness")
    return out


def _build_phase1(payload: dict[str, Any]) -> dict[str, Any]:
    stereo_detail = payload.get("stereoDetail")
    if not isinstance(stereo_detail, dict):
        stereo_detail = {}

    spectral_balance = payload.get("spectralBalance")
    if not isinstance(spectral_balance, dict):
        spectral_balance = {}

    plr = _coerce_nullable_number(payload.get("plr"))
    if plr is None:
        lufs_integrated = _coerce_nullable_number(payload.get("lufsIntegrated"))
        true_peak = _coerce_nullable_number(payload.get("truePeak"))
        if lufs_integrated is not None and true_peak is not None:
            plr = round(true_peak - lufs_integrated, 2)

    mono_compatible = payload.get("monoCompatible")
    if not isinstance(mono_compatible, bool):
        sub_bass_mono = stereo_detail.get("subBassMono")
        mono_compatible = sub_bass_mono if isinstance(sub_bass_mono, bool) else None

    return {
        "bpm": _coerce_number(payload.get("bpm")),
        "bpmConfidence": _coerce_number(payload.get("bpmConfidence")),
        "bpmPercival": _coerce_nullable_number(payload.get("bpmPercival")),
        "bpmAgreement": payload.get("bpmAgreement"),
        "bpmDoubletime": payload.get("bpmDoubletime"),
        "bpmSource": payload.get("bpmSource"),
        "bpmRawOriginal": _coerce_nullable_number(payload.get("bpmRawOriginal")),
        "key": _coerce_nullable_string(payload.get("key")),
        "keyConfidence": _coerce_number(payload.get("keyConfidence")),
        "keyProfile": payload.get("keyProfile"),
        "tuningFrequency": _coerce_nullable_number(payload.get("tuningFrequency")),
        "tuningCents": _coerce_nullable_number(payload.get("tuningCents")),
        "timeSignature": _coerce_string(payload.get("timeSignature"), "4/4"),
        "timeSignatureSource": _coerce_nullable_string(payload.get("timeSignatureSource")),
        "timeSignatureConfidence": _coerce_nullable_number(payload.get("timeSignatureConfidence")),
        "durationSeconds": _coerce_number(payload.get("durationSeconds")),
        "sampleRate": payload.get("sampleRate"),
        "lufsIntegrated": _coerce_number(payload.get("lufsIntegrated")),
        "lufsRange": _coerce_nullable_number(payload.get("lufsRange")),
        "lufsMomentaryMax": _coerce_nullable_number(payload.get("lufsMomentaryMax")),
        "lufsShortTermMax": _coerce_nullable_number(payload.get("lufsShortTermMax")),
        "truePeak": _coerce_number(payload.get("truePeak")),
        "plr": plr,
        "crestFactor": _coerce_nullable_number(payload.get("crestFactor")),
        "dynamicSpread": _coerce_nullable_number(payload.get("dynamicSpread")),
        "dynamicCharacter": payload.get("dynamicCharacter"),
        "textureCharacter": payload.get("textureCharacter"),
        "stereoWidth": _coerce_number(stereo_detail.get("stereoWidth")),
        "stereoCorrelation": _coerce_number(stereo_detail.get("stereoCorrelation")),
        "stereoDetail": payload.get("stereoDetail"),
        "monoCompatible": mono_compatible,
        "spectralBalance": {
            "subBass": _coerce_number(spectral_balance.get("subBass")),
            "lowBass": _coerce_number(spectral_balance.get("lowBass")),
            "lowMids": _coerce_number(spectral_balance.get("lowMids")),
            "mids": _coerce_number(spectral_balance.get("mids")),
            "upperMids": _coerce_number(spectral_balance.get("upperMids")),
            "highs": _coerce_number(spectral_balance.get("highs")),
            "brilliance": _coerce_number(spectral_balance.get("brilliance")),
        },
        "spectralDetail": _normalize_spectral_detail(payload.get("spectralDetail")),
        "rhythmDetail": payload.get("rhythmDetail"),
        "melodyDetail": payload.get("melodyDetail"),
        "transcriptionDetail": payload.get("transcriptionDetail"),
        "pitchDetail": payload.get("pitchDetail"),
        "grooveDetail": payload.get("grooveDetail"),
        "beatsLoudness": payload.get("beatsLoudness"),
        "rhythmTimeline": payload.get("rhythmTimeline"),
        "sidechainDetail": payload.get("sidechainDetail"),
        "acidDetail": payload.get("acidDetail"),
        "reverbDetail": payload.get("reverbDetail"),
        "vocalDetail": payload.get("vocalDetail"),
        "supersawDetail": payload.get("supersawDetail"),
        "bassDetail": payload.get("bassDetail"),
        "kickDetail": payload.get("kickDetail"),
        "genreDetail": payload.get("genreDetail"),
        "effectsDetail": payload.get("effectsDetail"),
        "synthesisCharacter": payload.get("synthesisCharacter"),
        "danceability": payload.get("danceability"),
        "structure": payload.get("structure"),
        "arrangementDetail": payload.get("arrangementDetail"),
        "segmentLoudness": payload.get("segmentLoudness"),
        "segmentSpectral": payload.get("segmentSpectral"),
        "segmentStereo": payload.get("segmentStereo"),
        "segmentKey": payload.get("segmentKey"),
        "chordDetail": payload.get("chordDetail"),
        "perceptual": payload.get("perceptual"),
        "essentiaFeatures": payload.get("essentiaFeatures"),
    }


def _persist_upload(
    track: UploadFile,
    *,
    max_bytes: int | None = None,
) -> tuple[str, int]:
    effective_max_bytes = (
        upload_limits.MAX_UPLOAD_SIZE_BYTES if max_bytes is None else max_bytes
    )
    suffix = Path(track.filename or "upload.bin").suffix or ".bin"
    temp_path: str | None = None
    try:
        track.file.seek(0)
    except Exception:
        pass
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            total_bytes = 0
            while True:
                chunk = track.file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > effective_max_bytes:
                    raise UploadTooLargeError(effective_max_bytes)
                temp_file.write(chunk)
        return temp_path, total_bytes
    except Exception:
        _cleanup_temp_path(temp_path)
        raise


def _cleanup_temp_path(temp_path: str | None) -> None:
    if temp_path and os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass


def _parse_json_marker(line: str, prefix: str) -> dict[str, Any] | None:
    if not line.startswith(prefix):
        return None
    payload_text = line.removeprefix(prefix).strip()
    if not payload_text:
        return None
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _read_subprocess_stream(
    stream: Any,
    collector: list[str],
    *,
    line_handler: Any = None,
) -> None:
    try:
        for raw_line in iter(stream.readline, ""):
            if raw_line == "":
                break
            collector.append(raw_line)
            if line_handler is not None:
                line_handler(raw_line.rstrip("\r\n"))
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _run_streamed_subprocess(
    *,
    command: list[str],
    timeout_seconds: int,
    run_id: str,
    stage_key: str,
    stderr_line_handler: Any = None,
) -> dict[str, Any]:
    if getattr(subprocess.run, "__module__", "").startswith("unittest.mock"):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "returncode": None,
                "stdout": exc.stdout,
                "stderr": exc.stderr,
                "timedOut": True,
            }
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timedOut": False,
        }

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    _register_active_child_process(run_id, stage_key, process)
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    stdout_thread = threading.Thread(
        target=_read_subprocess_stream,
        args=(process.stdout, stdout_chunks),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_read_subprocess_stream,
        args=(process.stderr, stderr_chunks),
        kwargs={"line_handler": stderr_line_handler},
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process(process)
    finally:
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        _unregister_active_child_process(run_id, stage_key, process)

    return {
        "returncode": process.returncode,
        "stdout": "".join(stdout_chunks),
        "stderr": "".join(stderr_chunks),
        "timedOut": timed_out,
    }


async def _create_analysis_run_record(
    *,
    track: UploadFile,
    analysis_mode: str,
    pitch_note_mode: str,
    pitch_note_backend: str,
    interpretation_mode: str,
    interpretation_profile: str,
    interpretation_model: str | None,
    legacy_request_id: str | None = None,
) -> tuple[AnalysisRuntime, str]:
    temp_path: str | None = None
    runtime = get_analysis_runtime()
    try:
        temp_path, _ = _persist_upload(track)
        analysis_mode = _resolve_analysis_mode_value(analysis_mode)
        if interpretation_mode != "off":
            _resolve_interpretation_profile_config(interpretation_profile)
        created = runtime.create_run_from_source_path(
            filename=track.filename or "upload.bin",
            source_path=temp_path,
            mime_type=track.content_type or _get_audio_mime_type(track.filename or "upload.bin"),
            analysis_mode=analysis_mode,
            pitch_note_mode=pitch_note_mode,
            pitch_note_backend=pitch_note_backend,
            interpretation_mode=interpretation_mode,
            interpretation_profile=interpretation_profile,
            interpretation_model=interpretation_model,
            legacy_request_id=legacy_request_id,
        )
        return runtime, created["runId"]
    finally:
        _cleanup_temp_path(temp_path)


def _build_measurement_provenance(
    *,
    run_separation: bool,
    run_transcribe: bool,
    run_standard: bool,
    run_fast: bool,
) -> dict[str, Any]:
    analysis_mode = "standard" if run_standard else "full"
    return {
        "schemaVersion": "measurement.v1",
        "engineVersion": ENGINE_VERSION,
        "requestOptions": {
            "analysisMode": analysis_mode,
            "separate": run_separation,
            "transcribe": run_transcribe,
            "standard": run_standard,
            "fast": run_fast,
        },
    }


def _resolve_pitch_note_mode_for_legacy(transcribe: bool) -> str:
    return "stem_notes" if transcribe else "off"


def _resolve_estimate_flags_for_stage_request(
    requested_pitch_note_mode: str,
) -> tuple[bool, bool]:
    if requested_pitch_note_mode == "off":
        return False, False
    if requested_pitch_note_mode == "stem_notes":
        return True, True
    raise UnsupportedPitchNoteModeError(requested_pitch_note_mode)


def _value_error_code(value_error: ValueError) -> str:
    message = str(value_error).lower()
    if "analysis mode" in message:
        return "ANALYSIS_MODE_UNSUPPORTED"
    return "INTERPRETATION_PROFILE_UNSUPPORTED"


def _canonical_upload_too_large_response(exc: UploadTooLargeError) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={
            "error": {
                "code": "UPLOAD_TOO_LARGE",
                "message": str(exc),
            }
        },
    )


def _legacy_upload_too_large_response(
    *,
    request_id: str,
    phase: str,
    endpoint: str,
    analysis_run_id: str | None = None,
) -> JSONResponse:
    content: dict[str, Any] = {
        "requestId": request_id,
        "error": {
            "code": "UPLOAD_TOO_LARGE",
            "message": upload_limits.upload_too_large_message(),
            "phase": phase,
            "retryable": False,
        },
    }
    if analysis_run_id is not None:
        content["analysisRunId"] = analysis_run_id
    return _mark_legacy_endpoint_response(
        JSONResponse(status_code=413, content=content),
        endpoint=endpoint,
    )


def _upload_too_large_response_for_path(
    path: str,
    *,
    limit_bytes: int,
) -> JSONResponse:
    if path in {"/api/analyze", "/api/analyze/estimate"}:
        return _legacy_upload_too_large_response(
            request_id=str(uuid4()),
            phase=ERROR_PHASE_LOCAL_DSP,
            endpoint=path,
        )
    if path == "/api/phase2":
        return _legacy_upload_too_large_response(
            request_id=str(uuid4()),
            phase=ERROR_PHASE_GEMINI,
            endpoint=path,
        )
    return _canonical_upload_too_large_response(UploadTooLargeError(limit_bytes))


def _resolve_analysis_mode_value(value: Any) -> str:
    if not isinstance(value, str):
        return "full"
    return AnalysisRuntime._resolve_analysis_mode(value)


async def _estimate_analysis_run(
    *,
    track: UploadFile,
    analysis_mode: str,
    pitch_note_mode: str,
    pitch_note_backend: str,
    interpretation_mode: str,
    interpretation_profile: str,
    interpretation_model: str | None,
    run_separation_override: bool | None = None,
    run_transcribe_override: bool | None = None,
) -> JSONResponse:
    temp_path: str | None = None
    try:
        if interpretation_mode != "off":
            _resolve_interpretation_profile_config(interpretation_profile)

        temp_path, _file_size_bytes = _persist_upload(track)
        analysis_mode = _resolve_analysis_mode_value(analysis_mode)
        _ = AnalysisRuntime._resolve_pitch_note_backend(pitch_note_backend)
        _ = interpretation_model

        resolved_run_separation, resolved_run_transcribe = _resolve_estimate_flags_for_stage_request(
            pitch_note_mode,
        )
        run_separation = (
            resolved_run_separation
            if run_separation_override is None
            else run_separation_override
        )
        run_transcribe = (
            resolved_run_transcribe
            if run_transcribe_override is None
            else run_transcribe_override
        )
        estimate = _build_backend_estimate(
            temp_path,
            run_separation,
            run_transcribe,
            analysis_mode=analysis_mode,
        )
        return JSONResponse(
            content={
                "requestId": str(uuid4()),
                "estimate": estimate,
            }
        )
    finally:
        await track.close()
        _cleanup_temp_path(temp_path)


def _run_measurement_subprocess(
    *,
    runtime: AnalysisRuntime,
    run_id: str,
    audio_path: str,
    file_size_bytes: int,
    request_id: str,
    request_started_at: datetime,
    run_separation: bool,
    run_transcribe: bool,
    run_standard: bool,
    run_fast: bool,
) -> dict[str, Any]:
    estimate = _build_backend_estimate(
        audio_path,
        run_separation,
        run_transcribe,
        analysis_mode="standard" if run_standard else "full",
    )
    command = ["./venv/bin/python", "analyze.py", audio_path, "--yes"]
    flags_used: list[str] = []
    if run_separation:
        command.append("--separate")
        flags_used.append("--separate")
    if run_transcribe:
        command.append("--transcribe")
        flags_used.append("--transcribe")
    if run_standard and not run_fast:
        command.append("--standard")
        flags_used.append("--standard")
    if run_fast:
        command.append("--fast")
        flags_used.append("--fast")

    timeout_seconds = _compute_timeout_seconds(estimate)
    analysis_started_at = _current_time()
    try:
        def handle_stderr_line(line: str) -> None:
            progress_payload = _parse_json_marker(line, "@@ASA_PROGRESS")
            if progress_payload is not None:
                runtime.update_measurement_progress(
                    run_id,
                    step_key=_coerce_string(
                        progress_payload.get("stepKey"), "measurement_progress"
                    ),
                    message=_coerce_string(
                        progress_payload.get("message"),
                        "Local measurement is in progress.",
                    ),
                    fraction=_coerce_nullable_number(progress_payload.get("fraction")),
                )
                return

            if line.startswith("@@SEPARATION_COMPLETE"):
                runtime.update_measurement_pipeline_progress(
                    run_id,
                    pipeline_key="separation",
                    status="completed",
                    step_key="separation_complete",
                    message="Legacy stem separation completed.",
                )
                return

            if line.startswith("@@TRANSCRIPTION_START"):
                runtime.update_measurement_pipeline_progress(
                    run_id,
                    pipeline_key="transcription",
                    status="running",
                    step_key="transcription_running",
                    message="Legacy transcription is running.",
                )
                return

            if line.startswith("@@TRANSCRIPTION_COMPLETE"):
                runtime.update_measurement_pipeline_progress(
                    run_id,
                    pipeline_key="transcription",
                    status="completed",
                    step_key="transcription_complete",
                    message="Legacy transcription completed.",
                )

        result = _run_streamed_subprocess(
            command=command,
            timeout_seconds=timeout_seconds,
            run_id=run_id,
            stage_key="measurement",
            stderr_line_handler=handle_stderr_line,
        )
    except Exception as exc:
        analysis_completed_at = _current_time()
        diagnostics = _build_diagnostics(
            request_id=request_id,
            estimate=estimate,
            timeout_seconds=timeout_seconds,
            request_started_at=request_started_at,
            analysis_started_at=analysis_started_at,
            analysis_completed_at=analysis_completed_at,
            flags_used=flags_used,
            file_size_bytes=file_size_bytes,
            file_duration_seconds=None,
            engine_version=ENGINE_VERSION,
            stderr=exc,
        )
        return {
            "ok": False,
            "statusCode": 500,
            "errorCode": "BACKEND_INTERNAL_ERROR",
            "message": "Local DSP backend hit an unexpected server error.",
            "retryable": False,
            "estimate": estimate,
            "timeoutSeconds": timeout_seconds,
            "flagsUsed": flags_used,
            "requestStartedAt": request_started_at,
            "analysisStartedAt": analysis_started_at,
            "analysisCompletedAt": analysis_completed_at,
            "stderr": exc,
            "diagnostics": diagnostics,
        }

    analysis_completed_at = _current_time()
    if result["timedOut"]:
        diagnostics = _build_diagnostics(
            request_id=request_id,
            estimate=estimate,
            timeout_seconds=timeout_seconds,
            request_started_at=request_started_at,
            analysis_started_at=analysis_started_at,
            analysis_completed_at=analysis_completed_at,
            flags_used=flags_used,
            file_size_bytes=file_size_bytes,
            file_duration_seconds=None,
            engine_version=ENGINE_VERSION,
            stdout=result["stdout"],
            stderr=result["stderr"],
        )
        return {
            "ok": False,
            "statusCode": 504,
            "errorCode": "ANALYZER_TIMEOUT",
            "message": "Local DSP analysis timed out before completion.",
            "retryable": True,
            "estimate": estimate,
            "timeoutSeconds": timeout_seconds,
            "flagsUsed": flags_used,
            "requestStartedAt": request_started_at,
            "analysisStartedAt": analysis_started_at,
            "analysisCompletedAt": analysis_completed_at,
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "diagnostics": diagnostics,
        }

    if result["returncode"] != 0:
        diagnostics = _build_diagnostics(
            request_id=request_id,
            estimate=estimate,
            timeout_seconds=timeout_seconds,
            request_started_at=request_started_at,
            analysis_started_at=analysis_started_at,
            analysis_completed_at=analysis_completed_at,
            flags_used=flags_used,
            file_size_bytes=file_size_bytes,
            file_duration_seconds=None,
            engine_version=ENGINE_VERSION,
            stdout=result["stdout"],
            stderr=result["stderr"],
        )
        return {
            "ok": False,
            "statusCode": 502,
            "errorCode": "ANALYZER_FAILED",
            "message": "Local DSP analysis failed before a valid result was produced.",
            "retryable": True,
            "estimate": estimate,
            "timeoutSeconds": timeout_seconds,
            "flagsUsed": flags_used,
            "requestStartedAt": request_started_at,
            "analysisStartedAt": analysis_started_at,
            "analysisCompletedAt": analysis_completed_at,
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "diagnostics": diagnostics,
        }

    stdout = str(result["stdout"]).strip()
    if not stdout:
        diagnostics = _build_diagnostics(
            request_id=request_id,
            estimate=estimate,
            timeout_seconds=timeout_seconds,
            request_started_at=request_started_at,
            analysis_started_at=analysis_started_at,
            analysis_completed_at=analysis_completed_at,
            flags_used=flags_used,
            file_size_bytes=file_size_bytes,
            file_duration_seconds=None,
            engine_version=ENGINE_VERSION,
            stderr=result["stderr"],
        )
        return {
            "ok": False,
            "statusCode": 502,
            "errorCode": "ANALYZER_EMPTY_OUTPUT",
            "message": "Local DSP analysis completed without returning any JSON.",
            "retryable": False,
            "estimate": estimate,
            "timeoutSeconds": timeout_seconds,
            "flagsUsed": flags_used,
            "requestStartedAt": request_started_at,
            "analysisStartedAt": analysis_started_at,
            "analysisCompletedAt": analysis_completed_at,
            "stderr": result["stderr"],
            "diagnostics": diagnostics,
        }

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        diagnostics = _build_diagnostics(
            request_id=request_id,
            estimate=estimate,
            timeout_seconds=timeout_seconds,
            request_started_at=request_started_at,
            analysis_started_at=analysis_started_at,
            analysis_completed_at=analysis_completed_at,
            flags_used=flags_used,
            file_size_bytes=file_size_bytes,
            file_duration_seconds=None,
            engine_version=ENGINE_VERSION,
            stdout=stdout,
            stderr=result["stderr"],
        )
        return {
            "ok": False,
            "statusCode": 502,
            "errorCode": "ANALYZER_INVALID_JSON",
            "message": "Local DSP analysis returned malformed JSON.",
            "retryable": False,
            "estimate": estimate,
            "timeoutSeconds": timeout_seconds,
            "flagsUsed": flags_used,
            "requestStartedAt": request_started_at,
            "analysisStartedAt": analysis_started_at,
            "analysisCompletedAt": analysis_completed_at,
            "stdout": stdout,
            "stderr": result["stderr"],
            "diagnostics": diagnostics,
        }

    if not isinstance(payload, dict):
        diagnostics = _build_diagnostics(
            request_id=request_id,
            estimate=estimate,
            timeout_seconds=timeout_seconds,
            request_started_at=request_started_at,
            analysis_started_at=analysis_started_at,
            analysis_completed_at=analysis_completed_at,
            flags_used=flags_used,
            file_size_bytes=file_size_bytes,
            file_duration_seconds=None,
            engine_version=ENGINE_VERSION,
            stdout=stdout,
            stderr=result["stderr"],
        )
        return {
            "ok": False,
            "statusCode": 502,
            "errorCode": "ANALYZER_BAD_PAYLOAD",
            "message": "Local DSP analysis returned a JSON payload that did not match the expected contract.",
            "retryable": False,
            "estimate": estimate,
            "timeoutSeconds": timeout_seconds,
            "flagsUsed": flags_used,
            "analysisStartedAt": analysis_started_at,
            "analysisCompletedAt": analysis_completed_at,
            "stdout": stdout,
            "stderr": result["stderr"],
            "diagnostics": diagnostics,
        }

    diagnostics = _build_diagnostics(
        request_id=request_id,
        estimate=estimate,
        timeout_seconds=timeout_seconds,
        request_started_at=request_started_at,
        analysis_started_at=analysis_started_at,
        analysis_completed_at=analysis_completed_at,
        flags_used=flags_used,
        file_size_bytes=file_size_bytes,
        file_duration_seconds=payload.get("durationSeconds"),
        engine_version=ENGINE_VERSION,
    )
    return {
        "ok": True,
        "payload": payload,
        "estimate": estimate,
        "timeoutSeconds": timeout_seconds,
        "flagsUsed": flags_used,
        "requestStartedAt": request_started_at,
        "analysisStartedAt": analysis_started_at,
        "analysisCompletedAt": analysis_completed_at,
        "diagnostics": diagnostics,
    }


def _generate_spectral_artifacts(runtime: AnalysisRuntime, run_id: str) -> None:
    """Generate librosa-based spectrogram PNGs and spectral time-series JSON.

    Runs after successful measurement. Failures are logged but do not fail
    the measurement — spectral visualizations are additive, not critical.
    """
    try:
        from spectral_viz import generate_all_artifacts

        source = runtime.get_source_artifact(run_id)
        with tempfile.TemporaryDirectory(prefix="spectral_viz_") as tmp_dir:
            artifacts = generate_all_artifacts(source["path"], tmp_dir)
            _MIME_TYPES = {
                "spectrogram_mel": "image/png",
                "spectral_time_series": "application/json",
            }
            _FILENAMES = {
                "spectrogram_mel": "mel_spectrogram.png",
                "spectral_time_series": "spectral_time_series.json",
            }
            for kind, path in artifacts.items():
                runtime.record_artifact(
                    run_id,
                    kind=kind,
                    source_path=path,
                    filename=_FILENAMES.get(kind, os.path.basename(path)),
                    mime_type=_MIME_TYPES.get(kind, "application/octet-stream"),
                    provenance={"generator": "spectral_viz", "schemaVersion": "spectral.v1"},
                )
    except Exception as exc:
        print(
            f"[warn] spectral artifact generation failed for run {run_id}: {exc}",
            file=sys.stderr,
        )


def _execute_measurement_run(
    runtime: AnalysisRuntime,
    run_id: str,
    *,
    request_id: str,
    run_separation: bool,
    run_transcribe: bool,
    run_standard: bool,
    run_fast: bool,
) -> dict[str, Any]:
    source_artifact = runtime.get_source_artifact(run_id)
    execution = _run_measurement_subprocess(
        runtime=runtime,
        run_id=run_id,
        audio_path=source_artifact["path"],
        file_size_bytes=source_artifact["sizeBytes"],
        request_id=request_id,
        request_started_at=_current_time(),
        run_separation=run_separation,
        run_transcribe=run_transcribe,
        run_standard=run_standard,
        run_fast=run_fast,
    )
    if runtime.is_run_interrupted(run_id):
        return {
            **execution,
            "ok": False,
            "interrupted": True,
            "statusCode": 202,
            "errorCode": "ANALYSIS_INTERRUPTED",
            "message": "Analysis run was interrupted before completion.",
            "retryable": False,
        }
    provenance = _build_measurement_provenance(
        run_separation=run_separation,
        run_transcribe=run_transcribe,
        run_standard=run_standard,
        run_fast=run_fast,
    )
    if execution["ok"]:
        runtime.complete_measurement(
            run_id,
            payload=execution["payload"],
            provenance=provenance,
            diagnostics=execution["diagnostics"],
        )
        _generate_spectral_artifacts(runtime, run_id)
        return execution

    runtime.fail_measurement(
        run_id,
        error={
            "code": execution["errorCode"],
            "message": execution["message"],
            "retryable": execution["retryable"],
            "phase": ERROR_PHASE_LOCAL_DSP,
        },
        diagnostics=execution["diagnostics"],
        provenance=provenance,
    )
    return execution


def _execute_reserved_measurement_job(
    runtime: AnalysisRuntime,
    job: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(job["runId"])
    requested_analysis_mode = str(job.get("requestedAnalysisMode", "full"))
    requested_pitch_note_mode = str(job.get("requestedPitchNoteMode", "off"))
    try:
        run_separation, run_transcribe = runtime.resolve_measurement_flags(
            requested_pitch_note_mode,
        )
    except UnsupportedPitchNoteModeError as exc:
        runtime.fail_measurement(
            run_id,
            error={
                "code": "PITCH_NOTE_MODE_UNSUPPORTED",
                "message": str(exc),
                "retryable": False,
                "phase": ERROR_PHASE_LOCAL_DSP,
            },
            provenance={
                "schemaVersion": "measurement.v1",
                "engineVersion": ENGINE_VERSION,
                "requestOptions": {
                    "pitchNoteMode": requested_pitch_note_mode,
                },
            },
        )
        return {
            "ok": False,
            "statusCode": 400,
            "errorCode": "PITCH_NOTE_MODE_UNSUPPORTED",
            "message": str(exc),
            "retryable": False,
            "diagnostics": None,
        }
    return _execute_measurement_run(
        runtime,
        run_id,
        request_id=run_id,
        run_separation=run_separation,
        run_transcribe=run_transcribe,
        run_standard=requested_analysis_mode == "standard",
        run_fast=False,
    )


def _execute_pitch_note_attempt(
    runtime: AnalysisRuntime,
    attempt: dict[str, Any],
) -> None:
    """Run pitch/note translation as a subprocess to isolate memory usage.

    Demucs + torchcrepe load ~2-4GB of models and tensors. Running them
    in-process causes the server to retain that memory for its entire
    lifetime because Python/PyTorch allocators don't return memory to the
    OS. Subprocess isolation means all that memory is freed on exit.
    """
    started_at = _current_time()
    run_id = str(attempt["runId"])
    attempt_id = str(attempt["attemptId"])
    source_artifact = runtime.get_source_artifact(run_id)
    provenance: dict[str, Any] = {
        "schemaVersion": "pitch_note_translation.v1",
        "backendId": attempt["backendId"],
        "mode": attempt["mode"],
    }
    stem_output_dir: str | None = None
    try:
        # Build the subprocess command
        command = [
            "./venv/bin/python", "analyze.py",
            source_artifact["path"],
            "--pitch-note-only",
            "--pitch-note-backend",
            attempt["backendId"],
            "--yes",
        ]

        # If stems already exist as artifacts, pass their directory
        # so the subprocess skips Demucs separation
        stem_dir = None
        if attempt["mode"] == "stem_notes":
            existing = runtime.get_artifacts_by_kind(run_id, "stem_")
            stem_paths_map = {
                artifact["kind"].removeprefix("stem_"): artifact["path"]
                for artifact in existing
                if isinstance(artifact.get("path"), str)
                and os.path.isfile(artifact["path"])
            }
            if "bass" in stem_paths_map or "other" in stem_paths_map:
                # Find the common parent directory of existing stems
                stem_dirs = {
                    os.path.dirname(p) for p in stem_paths_map.values()
                }
                if len(stem_dirs) == 1:
                    stem_dir = stem_dirs.pop()
                    command.extend(["--stem-dir", stem_dir])
            if stem_dir is None:
                stem_output_dir = tempfile.mkdtemp(
                    prefix="asa_pitch_note_stems_",
                    dir=str(runtime.runtime_dir),
                )
                command.extend(["--stem-output-dir", stem_output_dir])

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Pitch/note translation subprocess failed (exit {result.returncode}): "
                f"{result.stderr[-500:] if result.stderr else 'no stderr'}"
            )

        pitch_note_payload = json.loads(result.stdout)
        transcription_detail = None
        if isinstance(pitch_note_payload, dict):
            transcription_detail = pitch_note_payload.get("transcriptionDetail")

        # If subprocess ran separation, record new stem artifacts
        if stem_output_dir is not None and attempt["mode"] == "stem_notes":
            for stem_name in ("bass", "other"):
                stem_path = os.path.join(stem_output_dir, f"{stem_name}.wav")
                if not os.path.isfile(stem_path):
                    continue
                runtime.record_artifact(
                    run_id,
                    kind=f"stem_{stem_name}",
                    source_path=stem_path,
                    filename=f"{stem_name}.wav",
                    mime_type="audio/wav",
                    provenance={
                        "schemaVersion": "artifact.v1",
                        "sourceArtifactId": source_artifact["artifactId"],
                        "generator": "pitch_note_translation_subprocess",
                        "stemName": stem_name,
                    },
                )

        diagnostics = {
            "backendDurationMs": round(_elapsed_ms(started_at, _current_time()), 2),
            "stemSeparationUsed": attempt["mode"] == "stem_notes",
            "sourceArtifactId": source_artifact["artifactId"],
            "isolationMode": "subprocess",
        }
        if isinstance(transcription_detail, dict):
            provenance["resolvedBackendId"] = transcription_detail.get("transcriptionMethod")
        runtime.complete_pitch_note_attempt(
            str(attempt["attemptId"]),
            result=transcription_detail if isinstance(transcription_detail, dict) else None,
            provenance=provenance,
            diagnostics=diagnostics,
        )
    except Exception as exc:
        runtime.fail_pitch_note_attempt(
            str(attempt["attemptId"]),
            error={
                "code": "PITCH_NOTE_TRANSLATION_FAILED",
                "message": str(exc),
                "retryable": True,
                "phase": "pitch_note_translation",
            },
            provenance=provenance,
            diagnostics={
                "backendDurationMs": round(_elapsed_ms(started_at, _current_time()), 2),
                "sourceArtifactId": source_artifact["artifactId"],
                "isolationMode": "subprocess",
            },
        )
    finally:
        if stem_output_dir is not None:
            shutil.rmtree(stem_output_dir, ignore_errors=True)


def _run_interpretation_request(
    *,
    source_path: str,
    filename: str,
    file_size_bytes: int,
    profile_id: str,
    measurement_result: dict[str, Any],
    pitch_note_result: dict[str, Any] | None,
    grounding_metadata: dict[str, Any],
    model_name: str,
    request_id: str,
) -> dict[str, Any]:
    try:
        profile_config = _resolve_interpretation_profile_config(profile_id)
    except ValueError as exc:
        return {
            "ok": False,
            "statusCode": 400,
            "errorCode": "INTERPRETATION_PROFILE_UNSUPPORTED",
            "message": str(exc),
            "retryable": False,
            "diagnostics": None,
        }
    return _run_interpretation_request_with_profile_config(
        source_path=source_path,
        filename=filename,
        file_size_bytes=file_size_bytes,
        profile_id=profile_id,
        profile_config=profile_config,
        measurement_result=measurement_result,
        pitch_note_result=pitch_note_result,
        grounding_metadata=grounding_metadata,
        model_name=model_name,
        request_id=request_id,
    )


def _stem_summary_label(stem_kind: str) -> str:
    if stem_kind == "bass":
        return "Bass stem"
    if stem_kind == "other":
        return "Musical stem"
    return f"{stem_kind.title()} stem"


def _build_combined_stem_summary_result(stem_results: list[dict[str, Any]]) -> dict[str, Any]:
    combined_uncertainty: list[str] = []
    combined_summary_parts: list[str] = []
    stems_payload: list[dict[str, Any]] = []

    for stem_result in stem_results:
        stem_kind = str(stem_result["stem"])
        single_result = stem_result["result"]
        stems_payload.append(
            {
                "stem": stem_kind,
                "label": _stem_summary_label(stem_kind),
                "summary": single_result["summary"],
                "bars": single_result["bars"],
                "globalPatterns": single_result["globalPatterns"],
                "uncertaintyFlags": single_result["uncertaintyFlags"],
            }
        )
        combined_summary_parts.append(f"{_stem_summary_label(stem_kind)}: {single_result['summary']}")
        for flag in single_result["uncertaintyFlags"]:
            if flag not in combined_uncertainty:
                combined_uncertainty.append(flag)

    return {
        "summary": " ".join(combined_summary_parts),
        "stems": stems_payload,
        "uncertaintyFlags": combined_uncertainty,
    }


def _run_combined_stem_summary_request(
    *,
    runtime: AnalysisRuntime,
    run_id: str,
    measurement_result: dict[str, Any],
    pitch_note_result: dict[str, Any] | None,
    grounding_metadata: dict[str, Any],
    model_name: str,
    request_id: str,
) -> dict[str, Any]:
    stem_artifacts = runtime.get_artifacts_by_kind(run_id, "stem_")
    usable_stems = [
        artifact
        for artifact in stem_artifacts
        if artifact.get("kind") in {"stem_bass", "stem_other"}
        and isinstance(artifact.get("path"), str)
        and os.path.isfile(str(artifact["path"]))
    ]
    usable_stems.sort(key=lambda artifact: artifact["kind"])
    if not usable_stems:
        return {
            "ok": True,
            "interpretationResult": None,
            "message": "Stem summary skipped because no persisted stem artifacts were available.",
            "diagnostics": {"backendDurationMs": 0, "stemCalls": []},
        }

    profile_config = _resolve_interpretation_profile_config("stem_summary")
    stem_results: list[dict[str, Any]] = []
    diagnostics_by_stem: list[dict[str, Any]] = []

    for artifact in usable_stems:
        stem_kind = str(artifact["kind"]).removeprefix("stem_")
        stem_grounding_metadata = {
            **grounding_metadata,
            "stemKind": stem_kind,
            "stemArtifactId": artifact["artifactId"],
        }
        execution = _run_interpretation_request_with_profile_config(
            source_path=str(artifact["path"]),
            filename=str(artifact["filename"]),
            file_size_bytes=int(artifact["sizeBytes"]),
            profile_id="stem_summary",
            profile_config=profile_config,
            measurement_result=measurement_result,
            pitch_note_result=pitch_note_result,
            grounding_metadata=stem_grounding_metadata,
            model_name=model_name,
            request_id=f"{request_id}:{stem_kind}",
        )
        diagnostics_by_stem.append(
            {
                "stem": stem_kind,
                "artifactId": artifact["artifactId"],
                "diagnostics": execution.get("diagnostics"),
                "message": execution.get("message"),
                "ok": execution.get("ok"),
            }
        )
        if not execution["ok"]:
            execution["diagnostics"] = {
                "backendDurationMs": 0,
                "stemCalls": diagnostics_by_stem,
            }
            return execution
        if isinstance(execution.get("interpretationResult"), dict):
            stem_results.append(
                {
                    "stem": stem_kind,
                    "artifactId": artifact["artifactId"],
                    "result": execution["interpretationResult"],
                }
            )

    if not stem_results:
        return {
            "ok": True,
            "interpretationResult": None,
            "message": "Stem summary skipped because Gemini did not return usable stem results.",
            "diagnostics": {
                "backendDurationMs": 0,
                "stemCalls": diagnostics_by_stem,
            },
        }

    return {
        "ok": True,
        "interpretationResult": _build_combined_stem_summary_result(stem_results),
        "message": "Stem summary complete.",
        "diagnostics": {
            "backendDurationMs": 0,
            "stemCalls": diagnostics_by_stem,
        },
    }


def _run_interpretation_request_with_profile_config(
    *,
    source_path: str,
    filename: str,
    file_size_bytes: int,
    profile_id: str,
    profile_config: dict[str, Any],
    measurement_result: dict[str, Any],
    pitch_note_result: dict[str, Any] | None,
    grounding_metadata: dict[str, Any],
    model_name: str,
    request_id: str,
) -> dict[str, Any]:
    request_started_at = _current_time()
    flags_used: list[str] = []
    mime_type = _get_audio_mime_type(filename)
    descriptor_hooks = _build_descriptor_hooks(measurement_result)

    if not _GENAI_AVAILABLE:
        return {
            "ok": False,
            "statusCode": 500,
            "errorCode": "GEMINI_NOT_INSTALLED",
            "message": "google-genai package is not installed on the backend.",
            "retryable": False,
            "diagnostics": None,
        }

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {
            "ok": False,
            "statusCode": 500,
            "errorCode": "GEMINI_NOT_CONFIGURED",
            "message": "GEMINI_API_KEY is not set on the backend.",
            "retryable": False,
            "diagnostics": None,
        }

    if model_name not in ALLOWED_GEMINI_MODELS:
        return {
            "ok": False,
            "statusCode": 400,
            "errorCode": "INVALID_MODEL",
            "message": f"model_name '{model_name}' is not allowed. Must be one of: {sorted(ALLOWED_GEMINI_MODELS)}",
            "retryable": False,
            "diagnostics": None,
        }

    prompt = profile_config["buildPrompt"](
        measurement_result=measurement_result,
        pitch_note_result=pitch_note_result,
        grounding_metadata=grounding_metadata,
        descriptor_hooks=descriptor_hooks,
    )
    client = _genai.Client(
        api_key=api_key,
        http_options={"timeout": GEMINI_TIMEOUT_SECONDS * 1_000},
    )
    generate_config = _genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=profile_config["responseSchema"],
    )
    api_started_at = _current_time()
    uploaded_gemini_file = None

    try:
        if file_size_bytes <= INLINE_SIZE_LIMIT:
            flags_used.append("inline")
            with open(source_path, "rb") as input_file:
                audio_bytes = input_file.read()
            audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
            media_part = {"inline_data": {"data": audio_b64, "mime_type": mime_type}}

            def _generate_inline() -> Any:
                return client.models.generate_content(
                    model=model_name,
                    contents=[{"parts": [media_part, {"text": prompt}]}],
                    config=generate_config,
                )

            response = asyncio.run(_gemini_with_retry(_generate_inline))
            api_completed_at = _current_time()
            message_suffix = profile_config["successMessage"]
        else:
            flags_used.append("files-api")

            def _upload_file() -> Any:
                return client.files.upload(
                    file=source_path,
                    config=_genai_types.UploadFileConfig(
                        mime_type=mime_type,
                        display_name=filename,
                    ),
                )

            upload_start = _current_time()
            uploaded_gemini_file = asyncio.run(_gemini_with_retry(_upload_file))
            upload_end = _current_time()
            media_part = {
                "file_data": {
                    "file_uri": uploaded_gemini_file.uri,
                    "mime_type": uploaded_gemini_file.mime_type,
                }
            }

            def _generate_files_api() -> Any:
                return client.models.generate_content(
                    model=model_name,
                    contents=[{"parts": [media_part, {"text": prompt}]}],
                    config=generate_config,
                )

            generate_start = _current_time()
            response = asyncio.run(_gemini_with_retry(_generate_files_api))
            generate_end = _current_time()
            api_completed_at = _current_time()
            message_suffix = (
                f"{profile_config['successMessage']} "
                f"Upload: {int(_elapsed_ms(upload_start, upload_end))}ms, "
                f"Generate: {int(_elapsed_ms(generate_start, generate_end))}ms"
            )

        response_text: str | None = getattr(response, "text", None)
        debug_payload = None
        parse_validation_warnings: list[dict[str, Any]] = []
        if callable(profile_config.get("parseDebugResult")):
            debug_payload = profile_config["parseDebugResult"](response_text)
            interpretation_result = debug_payload.get("result")
            skip_message = debug_payload.get("skipMessage")
            payload_warnings = debug_payload.get("validationWarnings")
            if isinstance(payload_warnings, list):
                parse_validation_warnings = [
                    warning for warning in payload_warnings if isinstance(warning, dict)
                ]
        else:
            interpretation_result, skip_message = profile_config["parseResult"](response_text)
        semantic_validation_warnings = (
            _validate_phase2_semantics(interpretation_result)
            if profile_id == "producer_summary" and interpretation_result is not None
            else []
        )
        validation_warnings = parse_validation_warnings + semantic_validation_warnings
        diagnostics = _build_diagnostics(
            request_id=request_id,
            estimate={"totalLowMs": 0, "totalHighMs": 0},
            timeout_seconds=GEMINI_TIMEOUT_SECONDS,
            request_started_at=request_started_at,
            analysis_started_at=api_started_at,
            analysis_completed_at=api_completed_at,
            flags_used=flags_used,
            file_size_bytes=file_size_bytes,
            file_duration_seconds=None,
            engine_version=model_name,
            validation_warnings=validation_warnings,
        )
        if skip_message:
            return {
                "ok": True,
                "interpretationResult": None,
                "message": skip_message,
                "diagnostics": diagnostics,
            }
        return {
            "ok": True,
            "interpretationResult": interpretation_result,
            "message": message_suffix,
            "diagnostics": diagnostics,
        }
    except Exception as exc:
        error_msg = str(exc)
        status_code = 429 if "429" in error_msg or "quota" in error_msg.lower() else 502
        diagnostics = _build_diagnostics(
            request_id=request_id,
            estimate={"totalLowMs": 0, "totalHighMs": 0},
            timeout_seconds=GEMINI_TIMEOUT_SECONDS,
            request_started_at=request_started_at,
            analysis_started_at=api_started_at,
            analysis_completed_at=_current_time(),
            flags_used=flags_used,
            file_size_bytes=file_size_bytes,
            file_duration_seconds=None,
            engine_version=model_name,
            stderr=error_msg,
        )
        return {
            "ok": False,
            "statusCode": status_code,
            "errorCode": "GEMINI_GENERATE_FAILED",
            "message": f"Gemini generation failed: {error_msg[:200]}",
            "retryable": True,
            "diagnostics": diagnostics,
        }
    finally:
        if uploaded_gemini_file:
            try:
                client.files.delete(name=uploaded_gemini_file.name)
            except Exception:
                pass


def _execute_interpretation_attempt(
    runtime: AnalysisRuntime,
    attempt: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(attempt["runId"])
    profile_id = _coerce_string(attempt.get("profileId"), "producer_summary")
    grounding = runtime.get_interpretation_grounding(run_id)
    measurement_result = grounding["measurementResult"] or {}
    pitch_note_result = grounding["pitchNoteResult"]
    grounding_metadata = {
        "measurementIsAuthoritative": True,
        "pitchNoteTranslationIsBestEffort": True,
        "measurementOutputId": grounding["measurementOutputId"],
        "pitchNoteAttemptId": grounding["pitchNoteAttemptId"],
        "doNotPromotePitchNoteToMeasurement": True,
        "profileId": profile_id,
    }
    model_name = _coerce_string(attempt.get("modelName"), "gemini-2.5-flash")
    if profile_id == "stem_summary":
        execution = _run_combined_stem_summary_request(
            runtime=runtime,
            run_id=run_id,
            measurement_result=measurement_result,
            pitch_note_result=pitch_note_result,
            grounding_metadata=grounding_metadata,
            model_name=model_name,
            request_id=str(attempt["attemptId"]),
        )
    else:
        source_artifact = runtime.get_source_artifact(run_id)
        execution = _run_interpretation_request(
            source_path=source_artifact["path"],
            filename=source_artifact["filename"],
            file_size_bytes=source_artifact["sizeBytes"],
            profile_id=profile_id,
            measurement_result=measurement_result,
            pitch_note_result=pitch_note_result,
            grounding_metadata=grounding_metadata,
            model_name=model_name,
            request_id=str(attempt["attemptId"]),
        )
    profile_config = _resolve_interpretation_profile_config(profile_id)
    provenance = {
        "schemaVersion": str(
            profile_config.get("schemaVersion", _interpretation_schema_version(profile_id))
        ),
        "profileId": profile_id,
        "modelName": model_name,
        "groundedMeasurementRunId": run_id,
        "groundedMeasurementOutputId": grounding["measurementOutputId"],
        "groundedPitchNoteAttemptId": grounding["pitchNoteAttemptId"],
    }
    if isinstance(profile_config.get("promptVersion"), str):
        provenance["promptVersion"] = profile_config["promptVersion"]
    if runtime.is_run_interrupted(run_id):
        return {
            **execution,
            "ok": False,
            "interrupted": True,
            "statusCode": 202,
            "errorCode": "ANALYSIS_INTERRUPTED",
            "message": "Analysis run was interrupted before interpretation completed.",
            "retryable": False,
        }
    if execution["ok"]:
        runtime.complete_interpretation_attempt(
            str(attempt["attemptId"]),
            result=execution["interpretationResult"],
            provenance=provenance,
            diagnostics=execution["diagnostics"],
            grounded_measurement_output_id=grounding["measurementOutputId"],
            grounded_pitch_note_attempt_id=grounding["pitchNoteAttemptId"],
        )
        return execution

    runtime.fail_interpretation_attempt(
        str(attempt["attemptId"]),
        error={
            "code": execution["errorCode"],
            "message": execution["message"],
            "retryable": execution["retryable"],
            "phase": ERROR_PHASE_GEMINI,
        },
        provenance=provenance,
        diagnostics=execution["diagnostics"],
        grounded_measurement_output_id=grounding["measurementOutputId"],
        grounded_pitch_note_attempt_id=grounding["pitchNoteAttemptId"],
    )
    return execution


def _resolve_phase2_run_id(
    runtime: AnalysisRuntime,
    *,
    analysis_run_id: str | None,
    phase1_request_id: str | None,
) -> str:
    if analysis_run_id:
        runtime.get_run(analysis_run_id)
        return analysis_run_id
    if phase1_request_id:
        return runtime.get_run_id_by_legacy_request_id(phase1_request_id)
    raise KeyError("Missing analysis context")


async def _measurement_worker_loop() -> None:
    while True:
        try:
            job = await asyncio.to_thread(get_analysis_runtime().reserve_next_measurement_run)
            if job is None:
                await asyncio.sleep(WORKER_IDLE_SECONDS)
                continue
            await asyncio.to_thread(
                _execute_reserved_measurement_job,
                get_analysis_runtime(),
                job,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[warn] measurement worker loop failed: {exc}", file=sys.stderr)
            await asyncio.sleep(WORKER_IDLE_SECONDS)


async def _pitch_note_worker_loop() -> None:
    while True:
        try:
            attempt = await asyncio.to_thread(get_analysis_runtime().reserve_next_pitch_note_attempt)
            if attempt is None:
                await asyncio.sleep(WORKER_IDLE_SECONDS)
                continue
            await asyncio.to_thread(
                _execute_pitch_note_attempt,
                get_analysis_runtime(),
                attempt,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[warn] pitch/note translation worker loop failed: {exc}", file=sys.stderr)
            await asyncio.sleep(WORKER_IDLE_SECONDS)


async def _interpretation_worker_loop() -> None:
    while True:
        try:
            attempt = await asyncio.to_thread(get_analysis_runtime().reserve_next_interpretation_attempt)
            if attempt is None:
                await asyncio.sleep(WORKER_IDLE_SECONDS)
                continue
            await asyncio.to_thread(
                _execute_interpretation_attempt,
                get_analysis_runtime(),
                attempt,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[warn] interpretation worker loop failed: {exc}", file=sys.stderr)
            await asyncio.sleep(WORKER_IDLE_SECONDS)


@app.post("/api/analysis-runs")
async def create_analysis_run(
    track: UploadFile = File(...),
    analysis_mode: str = Form("full"),
    pitch_note_mode: str = Form("off"),
    pitch_note_backend: str = Form("auto"),
    interpretation_mode: str = Form("off"),
    interpretation_profile: str = Form("producer_summary"),
    interpretation_model: str | None = Form(None),
) -> JSONResponse:
    try:
        runtime, run_id = await _create_analysis_run_record(
            track=track,
            analysis_mode=analysis_mode,
            pitch_note_mode=pitch_note_mode,
            pitch_note_backend=pitch_note_backend,
            interpretation_mode=interpretation_mode,
            interpretation_profile=interpretation_profile,
            interpretation_model=interpretation_model,
        )
        return JSONResponse(content=_normalize_run_snapshot(runtime.get_run(run_id), runtime))
    except UploadTooLargeError as exc:
        return _canonical_upload_too_large_response(exc)
    except UnsupportedPitchNoteBackendError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "PITCH_NOTE_BACKEND_UNSUPPORTED",
                    "message": str(exc),
                }
            },
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": _value_error_code(exc),
                    "message": str(exc),
                }
            },
        )
    except RuntimeError as exc:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "MEASUREMENT_QUEUE_FULL",
                    "message": str(exc),
                }
            },
        )
    finally:
        await track.close()


@app.post("/api/analysis-runs/estimate")
async def estimate_analysis_run(
    track: UploadFile = File(...),
    analysis_mode: str = Form("full"),
    pitch_note_mode: str = Form("off"),
    pitch_note_backend: str = Form("auto"),
    interpretation_mode: str = Form("off"),
    interpretation_profile: str = Form("producer_summary"),
    interpretation_model: str | None = Form(None),
) -> JSONResponse:
    try:
        return await _estimate_analysis_run(
            track=track,
            analysis_mode=analysis_mode,
            pitch_note_mode=pitch_note_mode,
            pitch_note_backend=pitch_note_backend,
            interpretation_mode=interpretation_mode,
            interpretation_profile=interpretation_profile,
            interpretation_model=interpretation_model,
        )
    except UploadTooLargeError as exc:
        return _canonical_upload_too_large_response(exc)
    except UnsupportedPitchNoteModeError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "PITCH_NOTE_MODE_UNSUPPORTED",
                    "message": str(exc),
                }
            },
        )
    except UnsupportedPitchNoteBackendError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "PITCH_NOTE_BACKEND_UNSUPPORTED",
                    "message": str(exc),
                }
            },
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": _value_error_code(exc),
                    "message": str(exc),
                }
            },
        )


@app.get("/api/analysis-runs/{run_id}")
async def get_analysis_run(run_id: str) -> JSONResponse:
    runtime = get_analysis_runtime()
    try:
        return JSONResponse(content=_normalize_run_snapshot(runtime.get_run(run_id), runtime))
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "RUN_NOT_FOUND",
                    "message": f"Analysis run '{run_id}' was not found.",
                }
            },
        )


@app.post("/api/analysis-runs/{run_id}/interrupt")
async def interrupt_analysis_run(run_id: str) -> JSONResponse:
    runtime = get_analysis_runtime()
    try:
        terminated_stages = _interrupt_active_child_processes(run_id)
        snapshot = runtime.interrupt_run(run_id)
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "RUN_NOT_FOUND",
                    "message": f"Analysis run '{run_id}' was not found.",
                }
            },
        )

    payload = _normalize_run_snapshot(snapshot, runtime)
    payload["interrupt"] = {
        "stagesTerminated": terminated_stages,
    }
    return JSONResponse(status_code=202, content=payload)


@app.get("/api/analysis-runs/{run_id}/artifacts")
async def list_run_artifacts(
    run_id: str,
    kind: str = Query("", description="Filter by kind prefix"),
) -> JSONResponse:
    runtime = get_analysis_runtime()
    try:
        runtime.get_run(run_id)
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "RUN_NOT_FOUND",
                    "message": f"Analysis run '{run_id}' was not found.",
                }
            },
        )
    prefix = kind if kind else ""
    artifacts = runtime.get_artifacts_by_kind(run_id, prefix)
    return JSONResponse(content=artifacts)


@app.get("/api/analysis-runs/{run_id}/artifacts/{artifact_id}", response_model=None)
async def get_run_artifact(run_id: str, artifact_id: str) -> FileResponse | JSONResponse:
    runtime = get_analysis_runtime()
    try:
        runtime.get_run(run_id)
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "RUN_NOT_FOUND",
                    "message": f"Analysis run '{run_id}' was not found.",
                }
            },
        )
    artifacts = runtime.get_artifacts_by_kind(run_id, "")
    match = next((a for a in artifacts if a["artifactId"] == artifact_id), None)
    if match is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "ARTIFACT_NOT_FOUND",
                    "message": f"Artifact '{artifact_id}' not found in run '{run_id}'.",
                }
            },
        )
    artifact_path = match.get("path", "")
    if not artifact_path or not Path(artifact_path).is_file():
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "ARTIFACT_FILE_MISSING",
                    "message": "Artifact file is no longer available on disk.",
                }
            },
        )
    return FileResponse(
        path=artifact_path,
        media_type=match.get("mimeType", "application/octet-stream"),
        filename=match.get("filename", os.path.basename(artifact_path)),
    )


_ENHANCEMENT_GENERATORS = {
    "cqt": ("generate_cqt_spectrogram", ["spectrogram_cqt"], True),
    "hpss": ("generate_hpss_spectrograms", ["spectrogram_harmonic", "spectrogram_percussive"], True),
    "onset": ("generate_onset_enhancement", ["spectrogram_onset", "onset_strength"], True),
    "chroma_interactive": ("generate_chroma_enhancement", ["spectrogram_chroma", "chroma_interactive"], True),
}


@app.post("/api/analysis-runs/{run_id}/spectral-enhancements/{kind}")
async def generate_spectral_enhancement(run_id: str, kind: str) -> JSONResponse:
    if kind not in _ENHANCEMENT_GENERATORS:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "INVALID_KIND", "message": f"Unknown enhancement kind: '{kind}'. Valid: {', '.join(_ENHANCEMENT_GENERATORS)}"}},
        )

    runtime = get_analysis_runtime()
    try:
        run = runtime.get_run(run_id)
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "RUN_NOT_FOUND", "message": f"Analysis run '{run_id}' was not found."}},
        )

    stages = run.get("stages", {})
    meas_status = stages.get("measurement", {}).get("status")
    if meas_status != "completed":
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "MEASUREMENT_NOT_COMPLETED", "message": "Measurement stage must complete before generating enhancements."}},
        )

    func_name, artifact_kinds, is_image = _ENHANCEMENT_GENERATORS[kind]

    # Idempotent: skip if already generated
    existing = []
    for ak in artifact_kinds:
        existing.extend(runtime.get_artifacts_by_kind(run_id, ak))
    if existing:
        strip = lambda a: {"artifactId": a["artifactId"], "kind": a["kind"], "filename": a["filename"], "mimeType": a["mimeType"], "sizeBytes": a["sizeBytes"]}
        return JSONResponse(content={"artifacts": [strip(a) for a in existing]})

    try:
        import spectral_viz
        gen_func = getattr(spectral_viz, func_name)
        source = runtime.get_source_artifact(run_id)

        _MIME_TYPES = {
            "spectrogram_cqt": "image/png",
            "spectrogram_harmonic": "image/png",
            "spectrogram_percussive": "image/png",
            "spectrogram_onset": "image/png",
            "spectrogram_chroma": "image/png",
            "onset_strength": "application/json",
            "chroma_interactive": "application/json",
        }

        with tempfile.TemporaryDirectory(prefix="spectral_enh_") as tmp_dir:
            if is_image:
                result = gen_func(source["path"], tmp_dir)
            else:
                data = gen_func(source["path"])
                # Write JSON to file for artifact storage
                import json as json_mod
                for ak in artifact_kinds:
                    json_path = os.path.join(tmp_dir, f"{ak}.json")
                    Path(json_path).write_text(json_mod.dumps(data), encoding="utf-8")
                    result = {ak: json_path}

            created = []
            for ak, file_path in result.items():
                art = runtime.record_artifact(
                    run_id,
                    kind=ak,
                    source_path=file_path,
                    filename=os.path.basename(file_path),
                    mime_type=_MIME_TYPES.get(ak, "application/octet-stream"),
                    provenance={"generator": "spectral_viz", "enhancement": kind},
                )
                created.append({
                    "artifactId": art["artifactId"],
                    "kind": art["kind"],
                    "filename": art["filename"],
                    "mimeType": art["mimeType"],
                    "sizeBytes": art["sizeBytes"],
                })
            return JSONResponse(content={"artifacts": created})

    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "ENHANCEMENT_FAILED", "message": str(exc)}},
        )


@app.post("/api/analysis-runs/{run_id}/pitch-note-translations")
async def create_pitch_note_translation_attempt(
    run_id: str,
    pitch_note_mode: str = Form("stem_notes"),
    pitch_note_backend: str = Form("auto"),
) -> JSONResponse:
    runtime = get_analysis_runtime()
    try:
        resolved_backend = runtime._resolve_pitch_note_backend(pitch_note_backend)
        if runtime.get_measurement_status(run_id) != "completed":
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "MEASUREMENT_NOT_READY",
                        "message": "Measurement must complete before pitch/note translation can run.",
                    }
                },
            )
        runtime.create_pitch_note_attempt(
            run_id,
            backend_id=resolved_backend,
            mode=pitch_note_mode,
            status="queued",
            provenance={
                "schemaVersion": "pitch_note_translation.v1",
                "backendId": resolved_backend,
                "mode": pitch_note_mode,
                "requestedViaApi": True,
            },
        )
        return JSONResponse(status_code=202, content=_normalize_run_snapshot(runtime.get_run(run_id), runtime))
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "RUN_NOT_FOUND",
                    "message": f"Analysis run '{run_id}' was not found.",
                }
            },
        )
    except UnsupportedPitchNoteBackendError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "PITCH_NOTE_BACKEND_UNSUPPORTED",
                    "message": str(exc),
                }
            },
        )


@app.post("/api/analysis-runs/{run_id}/interpretations")
async def create_interpretation_attempt(
    run_id: str,
    interpretation_profile: str = Form("producer_summary"),
    interpretation_model: str = Form("gemini-2.5-flash"),
) -> JSONResponse:
    runtime = get_analysis_runtime()
    try:
        _resolve_interpretation_profile_config(interpretation_profile)
        if runtime.get_measurement_status(run_id) != "completed":
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "MEASUREMENT_NOT_READY",
                        "message": "Measurement must complete before interpretation can run.",
                    }
                },
            )
        runtime.create_interpretation_attempt(
            run_id,
            profile_id=interpretation_profile,
            model_name=interpretation_model,
            status="queued",
            provenance={
                "schemaVersion": _interpretation_schema_version(interpretation_profile),
                "profileId": interpretation_profile,
                "modelName": interpretation_model,
                "requestedViaApi": True,
            },
        )
        return JSONResponse(status_code=202, content=_normalize_run_snapshot(runtime.get_run(run_id), runtime))
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": _value_error_code(exc),
                    "message": str(exc),
                }
            },
        )
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "RUN_NOT_FOUND",
                    "message": f"Analysis run '{run_id}' was not found.",
                }
            },
        )


def _safe_snippet(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    snippet = text.strip()
    if not snippet:
        return None
    return snippet[:MAX_SNIPPET_LENGTH]


def _normalize_estimate_stage(raw_stage: dict[str, Any]) -> dict[str, Any]:
    raw_key = _coerce_string(raw_stage.get("key"), "local_dsp")
    raw_label = _coerce_string(raw_stage.get("label"), "Local DSP analysis")
    stage_key = {
        "dsp": "local_dsp",
        "separation": "demucs_separation",
    }.get(raw_key, raw_key)
    stage_label = {
        "local_dsp": "Local DSP analysis",
        "demucs_separation": "Demucs separation",
    }.get(stage_key, raw_label)
    seconds = raw_stage.get("seconds")
    if not isinstance(seconds, dict):
        seconds = {}
    low_ms = _coerce_positive_int(seconds.get("min")) * 1000
    high_ms = _coerce_positive_int(seconds.get("max")) * 1000
    if high_ms < low_ms:
        high_ms = low_ms
    return {
        "key": stage_key,
        "label": stage_label,
        "lowMs": low_ms,
        "highMs": high_ms,
    }


def _build_backend_estimate(
    audio_path: str,
    run_separation: bool,
    run_transcribe: bool,
    *,
    analysis_mode: str = "full",
) -> dict[str, Any]:
    try:
        duration_seconds = get_audio_duration_seconds(audio_path)
    except Exception:
        duration_seconds = None

    safe_duration = duration_seconds if duration_seconds is not None else 0.0
    if analysis_mode == "standard":
        raw_estimate = build_analysis_estimate(
            safe_duration,
            run_separation,
            run_transcribe,
            run_standard=True,
        )
    else:
        raw_estimate = build_analysis_estimate(
            safe_duration,
            run_separation,
            run_transcribe,
        )
    raw_stages = raw_estimate.get("stages")
    stages = (
        [
            _normalize_estimate_stage(stage)
            for stage in raw_stages
            if isinstance(stage, dict)
        ]
        if isinstance(raw_stages, list)
        else []
    )

    total_seconds = raw_estimate.get("totalSeconds")
    if isinstance(total_seconds, dict):
        total_low_ms = _coerce_positive_int(total_seconds.get("min")) * 1000
        total_high_ms = _coerce_positive_int(total_seconds.get("max")) * 1000
    else:
        total_low_ms = sum(stage["lowMs"] for stage in stages)
        total_high_ms = sum(stage["highMs"] for stage in stages)

    if total_high_ms < total_low_ms:
        total_high_ms = total_low_ms

    normalized_duration = (
        round(float(duration_seconds), 1)
        if isinstance(duration_seconds, (int, float))
        and isfinite(float(duration_seconds))
        else round(float(raw_estimate.get("durationSeconds", 0.0)), 1)
    )

    return {
        "durationSeconds": normalized_duration,
        "totalLowMs": total_low_ms,
        "totalHighMs": total_high_ms,
        "stages": stages,
    }


# ---------------------------------------------------------------------------
# Gemini Phase 2 helpers
# ---------------------------------------------------------------------------


def _get_audio_mime_type(filename: str, fallback: str = "audio/mpeg") -> str:
    mime, _ = mimetypes.guess_type(filename)
    if mime and mime.startswith("audio/"):
        return mime
    return fallback


def _is_retryable_gemini_error(error_message: str) -> bool:
    return any(sub in error_message for sub in GEMINI_RETRYABLE_SUBSTRINGS)


async def _gemini_with_retry(
    operation: Any,
    max_retries: int = GEMINI_MAX_RETRIES,
    base_delay_ms: float = GEMINI_RETRY_BASE_DELAY_MS,
) -> Any:
    """Run a synchronous callable in a thread with exponential-backoff retry.

    Retry logic mirrors withRetry() in geminiPhase2Client.ts exactly:
      delay = base * 2^(attempt-1) + random(0..1000) ms
    Retryable substrings match GEMINI_RETRYABLE_SUBSTRINGS.
    """
    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            return await asyncio.to_thread(operation)
        except Exception as exc:
            error_msg = str(exc)
            is_retryable = _is_retryable_gemini_error(error_msg)
            if not is_retryable or attempt >= max_retries:
                raise
            delay_ms = base_delay_ms * (2 ** (attempt - 1)) + random.random() * 1_000
            await asyncio.sleep(delay_ms / 1_000)
    raise RuntimeError("Max retries reached for Gemini Phase 2.")


def _build_phase2_prompt(
    *,
    measurement_result: dict[str, Any],
    pitch_note_result: dict[str, Any] | None,
    grounding_metadata: dict[str, Any],
    descriptor_hooks: dict[str, Any] | None = None,
) -> str:
    sections = [
        PRODUCER_SUMMARY_PROMPT_TEMPLATE.rstrip(),
        "\n\nAUTHORITATIVE_MEASUREMENT_RESULT_JSON:\n",
        json.dumps(measurement_result, indent=2),
        "\n\nOPTIONAL_PITCH_NOTE_TRANSLATION_RESULT_JSON:\n",
        json.dumps(pitch_note_result, indent=2),
        "\n\nLIVE_12_DEVICE_CATALOG_JSON:\n",
        json.dumps(LIVE12_DEVICE_CATALOG, indent=2),
        "\n\nGROUNDING_METADATA:\n",
        json.dumps(grounding_metadata, indent=2),
    ]
    if descriptor_hooks:
        sections.extend(
            [
                "\n\nMEASUREMENT_DERIVED_DESCRIPTOR_HOOKS:\n",
                json.dumps(descriptor_hooks, indent=2),
            ]
    )
    return "".join(sections)


def _build_stem_summary_prompt(
    *,
    measurement_result: dict[str, Any],
    pitch_note_result: dict[str, Any] | None,
    grounding_metadata: dict[str, Any],
    descriptor_hooks: dict[str, Any],
) -> str:
    sections = [
        STEM_SUMMARY_PROMPT_TEMPLATE.rstrip(),
        "\n\nAUTHORITATIVE_MEASUREMENT_RESULT_JSON:\n",
        json.dumps(measurement_result, indent=2),
        "\n\nOPTIONAL_PITCH_NOTE_TRANSLATION_RESULT_JSON:\n",
        json.dumps(pitch_note_result, indent=2),
        "\n\nMEASUREMENT_DERIVED_DESCRIPTOR_HOOKS:\n",
        json.dumps(descriptor_hooks, indent=2),
        "\n\nGROUNDING_METADATA:\n",
        json.dumps(grounding_metadata, indent=2),
    ]
    return "".join(sections)


def _build_descriptor_hooks(measurement_result: dict[str, Any]) -> dict[str, Any]:
    duration_seconds = _coerce_nullable_number(measurement_result.get("durationSeconds"))
    rhythm_detail = measurement_result.get("rhythmDetail")
    segment_loudness = measurement_result.get("segmentLoudness")
    sidechain_detail = measurement_result.get("sidechainDetail")
    melody_detail = measurement_result.get("melodyDetail")
    groove_detail = measurement_result.get("grooveDetail")

    downbeats: list[float] = []
    if isinstance(rhythm_detail, dict) and isinstance(rhythm_detail.get("downbeats"), list):
        for entry in rhythm_detail["downbeats"]:
            if _is_finite_num(entry):
                downbeats.append(round(float(entry), 4))

    bar_grid: list[dict[str, Any]] = []
    if downbeats:
        for index, start_time in enumerate(downbeats):
            end_time = (
                downbeats[index + 1]
                if index + 1 < len(downbeats)
                else duration_seconds
            )
            if end_time is None:
                continue
            bar_grid.append(
                {
                    "barStart": index + 1,
                    "barEnd": index + 1,
                    "startTime": round(float(start_time), 4),
                    "endTime": round(float(end_time), 4),
                }
            )

    energy_curve: dict[str, Any] = {
        "segmentLoudness": [],
        "kickAccent16": [],
        "hihatAccent16": [],
    }
    if isinstance(segment_loudness, list):
        for entry in segment_loudness:
            if not isinstance(entry, dict):
                continue
            energy_curve["segmentLoudness"].append(
                {
                    "segmentIndex": entry.get("segmentIndex"),
                    "start": entry.get("start"),
                    "end": entry.get("end"),
                    "lufs": entry.get("lufs"),
                    "lra": entry.get("lra"),
                }
            )
    if isinstance(groove_detail, dict):
        if isinstance(groove_detail.get("kickAccent"), list):
            energy_curve["kickAccent16"] = groove_detail.get("kickAccent")
        if isinstance(groove_detail.get("hihatAccent"), list):
            energy_curve["hihatAccent16"] = groove_detail.get("hihatAccent")

    pumping_descriptor = {
        "pumpingStrength": None,
        "pumpingRegularity": None,
        "pumpingRate": None,
        "pumpingConfidence": None,
        "vibratoPresent": None,
        "vibratoRate": None,
        "vibratoConfidence": None,
    }
    if isinstance(sidechain_detail, dict):
        pumping_descriptor["pumpingStrength"] = sidechain_detail.get("pumpingStrength")
        pumping_descriptor["pumpingRegularity"] = sidechain_detail.get("pumpingRegularity")
        pumping_descriptor["pumpingRate"] = sidechain_detail.get("pumpingRate")
        pumping_descriptor["pumpingConfidence"] = sidechain_detail.get("pumpingConfidence")
    if isinstance(melody_detail, dict):
        pumping_descriptor["vibratoPresent"] = melody_detail.get("vibratoPresent")
        pumping_descriptor["vibratoRate"] = melody_detail.get("vibratoRate")
        pumping_descriptor["vibratoConfidence"] = melody_detail.get("vibratoConfidence")

    return {
        "stableBarGrid": bar_grid,
        "beatSynchronousEnergyCurve": energy_curve,
        "pumpingOrModulationDescriptor": pumping_descriptor,
    }


def _interpretation_schema_version(profile_id: str) -> str:
    return "interpretation.v2" if profile_id == "producer_summary" else "interpretation.v1"


def _resolve_interpretation_profile_config(profile_id: str) -> dict[str, Any]:
    if profile_id == "producer_summary":
        return {
            "responseSchema": PHASE2_RESPONSE_SCHEMA,
            "buildPrompt": _build_phase2_prompt,
            "parseResult": _parse_phase2_result,
            "parseDebugResult": _parse_phase2_result_debug,
            "successMessage": "AI interpretation complete.",
            "promptVersion": PRODUCER_SUMMARY_PROMPT_VERSION,
            "schemaVersion": "interpretation.v2",
        }
    if profile_id == "stem_summary":
        return {
            "responseSchema": STEM_SUMMARY_RESPONSE_SCHEMA,
            "buildPrompt": _build_stem_summary_prompt,
            "parseResult": _parse_stem_summary_result,
            "parseDebugResult": None,
            "successMessage": "Stem summary complete.",
        }
    raise ValueError(
        f"interpretation_profile '{profile_id}' is unsupported. "
        f"Supported profiles: {sorted(SUPPORTED_INTERPRETATION_PROFILES)}"
    )


def _is_str(v: Any) -> bool:
    return isinstance(v, str)


def _is_finite_num(v: Any) -> bool:
    return not isinstance(v, bool) and isinstance(v, (int, float)) and isfinite(float(v))


def _is_opt_str(v: Any) -> bool:
    """Absent (None) or string — matches TS isOptionalString(undefined | string)."""
    return v is None or _is_str(v)


def _is_opt_num(v: Any) -> bool:
    """Absent (None) or finite number — matches TS isOptionalNumber."""
    return v is None or _is_finite_num(v)


def _is_str_list(v: Any) -> bool:
    return isinstance(v, list) and all(_is_str(i) for i in v)


def _is_num_list(v: Any) -> bool:
    return isinstance(v, list) and all(_is_finite_num(i) for i in v)


def _as_record(v: Any) -> dict[str, Any] | None:
    if not v or not isinstance(v, dict):
        return None
    return v


def _is_project_setup(v: Any) -> bool:
    record = _as_record(v)
    if not record:
        return False
    return (
        _is_finite_num(record.get("tempoBpm"))
        and _is_str(record.get("timeSignature"))
        and _is_finite_num(record.get("sampleRate"))
        and _is_finite_num(record.get("bitDepth"))
        and _is_str(record.get("headroomTarget"))
        and _is_str(record.get("sessionGoal"))
    )


def _is_track_grounding(v: Any) -> bool:
    record = _as_record(v)
    if not record or not _is_str_list(record.get("phase1Fields")):
        return False
    return record.get("segmentIndexes") is None or _is_num_list(record.get("segmentIndexes"))


def _is_track_layout(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        record = _as_record(item)
        if not record:
            return False
        if not (
            _is_finite_num(record.get("order"))
            and _is_str(record.get("name"))
            and _is_str(record.get("type"))
            and _is_str(record.get("purpose"))
            and _is_track_grounding(record.get("grounding"))
        ):
            return False
    return True


def _is_routing_returns(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        record = _as_record(item)
        if not record:
            return False
        if not (
            _is_str(record.get("name"))
            and _is_str(record.get("purpose"))
            and _is_str_list(record.get("sendSources"))
            and _is_str(record.get("deviceFocus"))
            and _is_str(record.get("levelGuidance"))
        ):
            return False
    return True


def _is_routing_blueprint(v: Any) -> bool:
    record = _as_record(v)
    if not record:
        return False
    return (
        _is_opt_str(record.get("sidechainSource"))
        and _is_str_list(record.get("sidechainTargets"))
        and _is_routing_returns(record.get("returns"))
        and _is_str_list(record.get("notes"))
    )


def _is_warp_target(v: Any) -> bool:
    record = _as_record(v)
    if not record:
        return False
    return (
        record.get("warpMode") in _ALLOWED_PHASE2_WARP_MODES
        and _is_opt_str(record.get("settings"))
        and _is_str(record.get("reason"))
    )


def _is_warp_guide(v: Any) -> bool:
    record = _as_record(v)
    if not record:
        return False
    return (
        _is_warp_target(record.get("fullTrack"))
        and _is_warp_target(record.get("drums"))
        and _is_warp_target(record.get("bass"))
        and _is_warp_target(record.get("melodic"))
        and (_is_warp_target(record.get("vocals")) if record.get("vocals") is not None else True)
        and _is_str(record.get("rationale"))
    )


def _is_device_family(v: Any) -> bool:
    return v in _ALLOWED_LIVE12_DEVICE_FAMILIES


def _is_workflow_stage(v: Any) -> bool:
    return v in _ALLOWED_PHASE2_WORKFLOW_STAGES


def _is_recommendation_category(v: Any) -> bool:
    return v in _ALLOWED_PHASE2_RECOMMENDATION_CATEGORIES


def _is_secret_sauce_workflow_steps(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        record = _as_record(item)
        if not record:
            return False
        if not (
            _is_finite_num(record.get("step"))
            and _is_str(record.get("trackContext"))
            and _is_str(record.get("device"))
            and _is_str(record.get("parameter"))
            and _is_str(record.get("value"))
            and _is_str(record.get("instruction"))
            and _is_str(record.get("measurementJustification"))
        ):
            return False
    return True


def _is_detected_characteristics(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        r = _as_record(item)
        if not r:
            return False
        if not (_is_str(r.get("name")) and _is_str(r.get("explanation"))):
            return False
        if r.get("confidence") not in ("HIGH", "MED", "LOW"):
            return False
    return True


def _is_audio_element_character(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        record = _as_record(item)
        if not record:
            return False
        if not (_is_str(record.get("element")) and _is_str(record.get("description"))):
            return False
    return True


def _is_audio_observations(v: Any) -> bool:
    record = _as_record(v)
    if not record:
        return False
    return (
        _is_str(record.get("soundDesignFingerprint"))
        and _is_audio_element_character(record.get("elementCharacter"))
        and _is_str_list(record.get("productionSignatures"))
        and _is_str(record.get("mixContext"))
    )


def _is_arrangement_overview(v: Any) -> bool:
    r = _as_record(v)
    if not r or not _is_str(r.get("summary")) or not isinstance(r.get("segments"), list):
        return False
    for seg in r["segments"]:
        s = _as_record(seg)
        if not s:
            return False
        if not (_is_finite_num(s.get("index")) and _is_finite_num(s.get("startTime"))
                and _is_finite_num(s.get("endTime")) and _is_str(s.get("description"))):
            return False
        if not (
            _is_opt_num(s.get("lufs"))
            and _is_opt_str(s.get("spectralNote"))
            and _is_str(s.get("sceneName"))
            and _is_str(s.get("abletonAction"))
            and _is_str(s.get("automationFocus"))
        ):
            return False
    return _is_opt_str(r.get("noveltyNotes"))


def _is_sonic_elements(v: Any) -> bool:
    r = _as_record(v)
    if not r:
        return False
    required_keys = ("kick", "bass", "melodicArp", "grooveAndTiming", "effectsAndTexture")
    optional_keys = ("widthAndStereo", "harmonicContent")
    return (
        all(_is_str(r.get(k)) for k in required_keys)
        and all(_is_opt_str(r.get(k)) for k in optional_keys)
    )


def _is_mix_and_master_chain_item(v: Any) -> bool:
    r = _as_record(v)
    if not r:
        return False
    return (
        _is_finite_num(r.get("order"))
        and _is_str(r.get("device"))
        and _is_device_family(r.get("deviceFamily"))
        and _is_str(r.get("trackContext"))
        and _is_workflow_stage(r.get("workflowStage"))
        and _is_str(r.get("parameter"))
        and _is_str(r.get("value"))
        and _is_str(r.get("reason"))
    )


def _is_mix_and_master_chain(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        if not _is_mix_and_master_chain_item(item):
            return False
    return True


def _is_secret_sauce(v: Any) -> bool:
    r = _as_record(v)
    if not r:
        return False
    return (
        _is_str(r.get("title"))
        and _is_opt_str(r.get("icon"))
        and _is_str(r.get("explanation"))
        and _is_str_list(r.get("implementationSteps"))
        and _is_secret_sauce_workflow_steps(r.get("workflowSteps"))
    )


def _is_confidence_notes(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        r = _as_record(item)
        if not r:
            return False
        if not (_is_str(r.get("field")) and _is_str(r.get("value")) and _is_str(r.get("reason"))):
            return False
    return True


def _is_ableton_recommendation_item(v: Any) -> bool:
    r = _as_record(v)
    if not r:
        return False
    return (
        _is_str(r.get("device"))
        and _is_device_family(r.get("deviceFamily"))
        and _is_str(r.get("trackContext"))
        and _is_workflow_stage(r.get("workflowStage"))
        and _is_recommendation_category(r.get("category"))
        and _is_str(r.get("parameter"))
        and _is_str(r.get("value"))
        and _is_str(r.get("reason"))
        and _is_str(r.get("advancedTip"))
    )


def _is_ableton_recommendations(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        if not _is_ableton_recommendation_item(item):
            return False
    return True


def _is_valid_phase2_shape(data: Any) -> bool:
    """Mirrors isPhase2Result() in geminiPhase2Client.ts."""
    r = _as_record(data)
    if not r:
        return False
    return (
        _is_str(r.get("trackCharacter"))
        and _is_project_setup(r.get("projectSetup"))
        and _is_track_layout(r.get("trackLayout"))
        and _is_routing_blueprint(r.get("routingBlueprint"))
        and _is_warp_guide(r.get("warpGuide"))
        and _is_detected_characteristics(r.get("detectedCharacteristics"))
        and (r.get("audioObservations") is None or _is_audio_observations(r.get("audioObservations")))
        and _is_arrangement_overview(r.get("arrangementOverview"))
        and _is_sonic_elements(r.get("sonicElements"))
        and _is_mix_and_master_chain(r.get("mixAndMasterChain"))
        and _is_secret_sauce(r.get("secretSauce"))
        and _is_confidence_notes(r.get("confidenceNotes"))
        and _is_ableton_recommendations(r.get("abletonRecommendations"))
    )


def _sanitize_optional_phase2_fields(data: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(data)
    if "audioObservations" in sanitized and not _is_audio_observations(
        sanitized.get("audioObservations")
    ):
        sanitized.pop("audioObservations", None)
    return sanitized


_PHASE2_DEBUG_SHAPE_ISSUE_LIMIT = 16
_PHASE2_SALVAGE_WARNING_CODES = {"COERCED_ENUM_VALUE", "DROPPED_INVALID_ARRAY_ITEM", "BACKFILLED_FIELD"}
_PHASE2_SALVAGE_REQUIRED_ARRAYS = {"abletonRecommendations", "mixAndMasterChain"}


def _stringify_warning_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _collect_mix_and_master_chain_item_issues(item: Any, path: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    record = _as_record(item)
    if record is None:
        return [{"path": path, "message": f"Expected object but got {_type_label(item)}."}]
    if not _is_finite_num(record.get("order")):
        issues.append({"path": f"{path}.order", "message": "Expected finite number."})
    if not _is_str(record.get("device")):
        issues.append({"path": f"{path}.device", "message": "Expected string."})
    if not _is_device_family(record.get("deviceFamily")):
        issues.append(
            {
                "path": f"{path}.deviceFamily",
                "message": (
                    f"Value '{record.get('deviceFamily')}' is not allowed. Expected one of "
                    f"{sorted(_ALLOWED_LIVE12_DEVICE_FAMILIES)}."
                ),
            }
        )
    if not _is_str(record.get("trackContext")):
        issues.append({"path": f"{path}.trackContext", "message": "Expected string."})
    if not _is_workflow_stage(record.get("workflowStage")):
        issues.append(
            {
                "path": f"{path}.workflowStage",
                "message": (
                    f"Value '{record.get('workflowStage')}' is not allowed. Expected one of "
                    f"{sorted(_ALLOWED_PHASE2_WORKFLOW_STAGES)}."
                ),
            }
        )
    if not _is_str(record.get("parameter")):
        issues.append({"path": f"{path}.parameter", "message": "Expected string."})
    if not _is_str(record.get("value")):
        issues.append({"path": f"{path}.value", "message": "Expected string."})
    if not _is_str(record.get("reason")):
        issues.append({"path": f"{path}.reason", "message": "Expected string."})
    return issues


def _collect_ableton_recommendation_item_issues(item: Any, path: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    record = _as_record(item)
    if record is None:
        return [{"path": path, "message": f"Expected object but got {_type_label(item)}."}]
    if not _is_str(record.get("device")):
        issues.append({"path": f"{path}.device", "message": "Expected string."})
    if not _is_device_family(record.get("deviceFamily")):
        issues.append(
            {
                "path": f"{path}.deviceFamily",
                "message": (
                    f"Value '{record.get('deviceFamily')}' is not allowed. Expected one of "
                    f"{sorted(_ALLOWED_LIVE12_DEVICE_FAMILIES)}."
                ),
            }
        )
    if not _is_str(record.get("trackContext")):
        issues.append({"path": f"{path}.trackContext", "message": "Expected string."})
    if not _is_workflow_stage(record.get("workflowStage")):
        issues.append(
            {
                "path": f"{path}.workflowStage",
                "message": (
                    f"Value '{record.get('workflowStage')}' is not allowed. Expected one of "
                    f"{sorted(_ALLOWED_PHASE2_WORKFLOW_STAGES)}."
                ),
            }
        )
    if not _is_recommendation_category(record.get("category")):
        issues.append(
            {
                "path": f"{path}.category",
                "message": (
                    f"Value '{record.get('category')}' is not allowed. Expected one of "
                    f"{sorted(_ALLOWED_PHASE2_RECOMMENDATION_CATEGORIES)}."
                ),
            }
        )
    if not _is_str(record.get("parameter")):
        issues.append({"path": f"{path}.parameter", "message": "Expected string."})
    if not _is_str(record.get("value")):
        issues.append({"path": f"{path}.value", "message": "Expected string."})
    if not _is_str(record.get("reason")):
        issues.append({"path": f"{path}.reason", "message": "Expected string."})
    if not _is_str(record.get("advancedTip")):
        issues.append({"path": f"{path}.advancedTip", "message": "Expected string."})
    return issues


def _coerce_enum_fields(
    normalized: dict[str, Any],
    *,
    base_path: str,
    fields: tuple[tuple[str, frozenset[str], dict[str, str]], ...],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for field, allowed, coercion_map in fields:
        value = normalized.get(field)
        if isinstance(value, str) and value not in allowed:
            coerced = coercion_map.get(value)
            if coerced is not None:
                normalized[field] = coerced
                warnings.append(
                    _build_phase2_validation_warning(
                        code="COERCED_ENUM_VALUE",
                        path=f"{base_path}.{field}",
                        message=f"Coerced {field} '{value}' to '{coerced}' for {base_path.split('[')[0]}.",
                        original_value=value,
                        coerced_value=coerced,
                    )
                )
    return warnings


_RECOMMENDATION_ENUM_FIELDS: tuple[tuple[str, frozenset[str], dict[str, str]], ...] = (
    ("deviceFamily", frozenset(_ALLOWED_LIVE12_DEVICE_FAMILIES), _DEVICE_FAMILY_COERCION),
    ("workflowStage", frozenset(_ALLOWED_PHASE2_WORKFLOW_STAGES), _WORKFLOW_STAGE_COERCION),
    ("category", frozenset(_ALLOWED_PHASE2_RECOMMENDATION_CATEGORIES), _RECOMMENDATION_CATEGORY_COERCION),
)

_MIX_CHAIN_ENUM_FIELDS: tuple[tuple[str, frozenset[str], dict[str, str]], ...] = (
    ("deviceFamily", frozenset(_ALLOWED_LIVE12_DEVICE_FAMILIES), _DEVICE_FAMILY_COERCION),
    ("workflowStage", frozenset(_ALLOWED_PHASE2_WORKFLOW_STAGES), _WORKFLOW_STAGE_COERCION),
)


def _normalize_phase2_recommendation_item(
    item: Any,
    *,
    index: int,
) -> tuple[Any, list[dict[str, Any]]]:
    record = _as_record(item)
    if record is None:
        return item, []
    normalized = dict(record)
    warnings = _coerce_enum_fields(
        normalized,
        base_path=f"abletonRecommendations[{index}]",
        fields=_RECOMMENDATION_ENUM_FIELDS,
    )
    if not _is_str(normalized.get("advancedTip")) and _is_str(normalized.get("reason")):
        normalized["advancedTip"] = normalized["reason"]
        warnings.append(
            _build_phase2_validation_warning(
                code="BACKFILLED_FIELD",
                path=f"abletonRecommendations[{index}].advancedTip",
                message="Backfilled missing advancedTip from reason.",
                original_value=None,
                coerced_value=normalized["reason"],
            )
        )
    return normalized, warnings


def _normalize_mix_chain_item(
    item: Any,
    *,
    index: int,
) -> tuple[Any, list[dict[str, Any]]]:
    record = _as_record(item)
    if record is None:
        return item, []
    normalized = dict(record)
    warnings = _coerce_enum_fields(
        normalized,
        base_path=f"mixAndMasterChain[{index}]",
        fields=_MIX_CHAIN_ENUM_FIELDS,
    )
    return normalized, warnings


def _normalize_track_context_value(
    value: Any,
    *,
    path: str,
) -> tuple[Any, list[dict[str, Any]]]:
    if not isinstance(value, str):
        return value, []
    if not value.startswith("Return: "):
        return value, []
    normalized = f"Return:{value[len('Return: '):].strip()}"
    if normalized == value or normalized == "Return:":
        return value, []
    return normalized, [
        _build_phase2_validation_warning(
            code="COERCED_TRACK_CONTEXT",
            path=path,
            message=(
                f"Coerced trackContext '{value}' to '{normalized}' to match the "
                "required Return:<name> format."
            ),
            original_value=value,
            coerced_value=normalized,
        )
    ]


def _declared_return_names(data: dict[str, Any]) -> list[str]:
    routing_blueprint = _as_record(data.get("routingBlueprint"))
    returns = routing_blueprint.get("returns") if routing_blueprint else None
    if not isinstance(returns, list):
        return []
    names: list[str] = []
    for item in returns:
        record = _as_record(item)
        if record and _is_str(record.get("name")):
            names.append(record["name"])
    return names


def _repair_return_track_context(
    value: str,
    *,
    path: str,
    declared_returns: list[str],
) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(value, str) or not value.startswith("Return:"):
        return value, []
    suffix = value[len("Return:"):]
    if not suffix:
        return value, []
    exact_set = {f"Return:{name}" for name in declared_returns}
    if value in exact_set:
        return value, []
    # Case-insensitive exact match
    suffix_lower = suffix.lower()
    ci_matches = [name for name in declared_returns if suffix_lower == name.lower()]
    if len(ci_matches) == 1:
        repaired = f"Return:{ci_matches[0]}"
        return repaired, [
            _build_phase2_validation_warning(
                code="COERCED_TRACK_CONTEXT",
                path=path,
                message=(
                    f"Coerced trackContext '{value}' to '{repaired}' by matching "
                    "against declared routingBlueprint return names."
                ),
                original_value=value,
                coerced_value=repaired,
            )
        ]
    # Substring match (suffix is a substring of a declared return name)
    sub_matches = [
        name for name in declared_returns if suffix_lower in name.lower()
    ]
    if len(sub_matches) == 1:
        repaired = f"Return:{sub_matches[0]}"
        return repaired, [
            _build_phase2_validation_warning(
                code="COERCED_TRACK_CONTEXT",
                path=path,
                message=(
                    f"Coerced trackContext '{value}' to '{repaired}' by matching "
                    "against declared routingBlueprint return names."
                ),
                original_value=value,
                coerced_value=repaired,
            )
        ]
    return value, []


def _salvage_phase2_array_items(
    items: Any,
    *,
    array_path: str,
    item_validator: Callable[[Any], bool],
    item_issue_collector: Callable[[Any, str], list[dict[str, str]]],
) -> tuple[Any, list[dict[str, Any]], bool]:
    if not isinstance(items, list):
        return items, [], False

    salvaged = False
    warnings: list[dict[str, Any]] = []
    kept_items: list[Any] = []
    for index, item in enumerate(items):
        item_path = f"{array_path}[{index}]"
        if item_validator(item):
            kept_items.append(item)
            continue
        salvaged = True
        issues = item_issue_collector(item, item_path)
        if issues:
            issue_path = issues[0].get("path", item_path)
            issue_field = issue_path.split(".")[-1] if "." in issue_path else issue_path
            drop_reason = f"{issue_field}: {issues[0]['message']}"
        else:
            drop_reason = "Item failed strict validation."
        warnings.append(
            _build_phase2_validation_warning(
                code="DROPPED_INVALID_ARRAY_ITEM",
                path=item_path,
                message=f"Dropped invalid {array_path} item after bounded salvage.",
                original_value=_stringify_warning_value(item),
                drop_reason=drop_reason,
            )
        )
    return kept_items, warnings, salvaged


def _normalize_and_salvage_phase2_result(
    data: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    normalized = dict(data)
    warnings: list[dict[str, Any]] = []
    emptied_required_arrays: set[str] = set()
    declared_returns = _declared_return_names(data)

    recommendations = normalized.get("abletonRecommendations")
    if isinstance(recommendations, list):
        normalized_recommendations: list[Any] = []
        for index, item in enumerate(recommendations):
            normalized_item, item_warnings = _normalize_phase2_recommendation_item(
                item,
                index=index,
            )
            normalized_record = _as_record(normalized_item)
            if normalized_record is not None:
                track_context, track_context_warnings = _normalize_track_context_value(
                    normalized_record.get("trackContext"),
                    path=f"abletonRecommendations[{index}].trackContext",
                )
                track_context, repair_warnings = _repair_return_track_context(
                    track_context,
                    path=f"abletonRecommendations[{index}].trackContext",
                    declared_returns=declared_returns,
                )
                normalized_item = dict(normalized_record)
                normalized_item["trackContext"] = track_context
                warnings.extend(track_context_warnings)
                warnings.extend(repair_warnings)
            normalized_recommendations.append(normalized_item)
            warnings.extend(item_warnings)
        normalized["abletonRecommendations"] = normalized_recommendations

    mix_chain = normalized.get("mixAndMasterChain")
    if isinstance(mix_chain, list):
        normalized_mix_chain: list[Any] = []
        for index, item in enumerate(mix_chain):
            normalized_item, item_enum_warnings = _normalize_mix_chain_item(
                item, index=index,
            )
            warnings.extend(item_enum_warnings)
            record = _as_record(normalized_item)
            if record is None:
                normalized_mix_chain.append(normalized_item)
                continue
            normalized_item = dict(record)
            track_context, track_context_warnings = _normalize_track_context_value(
                normalized_item.get("trackContext"),
                path=f"mixAndMasterChain[{index}].trackContext",
            )
            track_context, repair_warnings = _repair_return_track_context(
                track_context,
                path=f"mixAndMasterChain[{index}].trackContext",
                declared_returns=declared_returns,
            )
            normalized_item["trackContext"] = track_context
            normalized_mix_chain.append(normalized_item)
            warnings.extend(track_context_warnings)
            warnings.extend(repair_warnings)
        normalized["mixAndMasterChain"] = normalized_mix_chain

    secret_sauce = _as_record(normalized.get("secretSauce"))
    workflow_steps = secret_sauce.get("workflowSteps") if secret_sauce else None
    if isinstance(workflow_steps, list):
        normalized_steps: list[Any] = []
        for index, item in enumerate(workflow_steps):
            record = _as_record(item)
            if record is None:
                normalized_steps.append(item)
                continue
            normalized_item = dict(record)
            track_context, track_context_warnings = _normalize_track_context_value(
                normalized_item.get("trackContext"),
                path=f"secretSauce.workflowSteps[{index}].trackContext",
            )
            track_context, repair_warnings = _repair_return_track_context(
                track_context,
                path=f"secretSauce.workflowSteps[{index}].trackContext",
                declared_returns=declared_returns,
            )
            normalized_item["trackContext"] = track_context
            normalized_steps.append(normalized_item)
            warnings.extend(track_context_warnings)
            warnings.extend(repair_warnings)
        normalized_secret_sauce = dict(secret_sauce)
        normalized_secret_sauce["workflowSteps"] = normalized_steps
        normalized["secretSauce"] = normalized_secret_sauce

    for array_path, item_validator, item_issue_collector in (
        (
            "abletonRecommendations",
            _is_ableton_recommendation_item,
            _collect_ableton_recommendation_item_issues,
        ),
        (
            "mixAndMasterChain",
            _is_mix_and_master_chain_item,
            _collect_mix_and_master_chain_item_issues,
        ),
    ):
        salvaged_items, item_warnings, salvaged = _salvage_phase2_array_items(
            normalized.get(array_path),
            array_path=array_path,
            item_validator=item_validator,
            item_issue_collector=item_issue_collector,
        )
        if salvaged:
            normalized[array_path] = salvaged_items
            if isinstance(salvaged_items, list) and len(salvaged_items) == 0:
                emptied_required_arrays.add(array_path)
        warnings.extend(item_warnings)

    return normalized, warnings, emptied_required_arrays


def _type_label(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def _append_shape_issue(
    issues: list[dict[str, str]],
    *,
    path: str,
    message: str,
) -> None:
    if len(issues) >= _PHASE2_DEBUG_SHAPE_ISSUE_LIMIT:
        return
    issues.append({"path": path, "message": message})


def _collect_phase2_shape_issues(data: Any) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    def expect_record(value: Any, path: str) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            _append_shape_issue(
                issues,
                path=path,
                message=f"Expected object but got {_type_label(value)}.",
            )
            return None
        return value

    def expect_list(value: Any, path: str) -> list[Any] | None:
        if not isinstance(value, list):
            _append_shape_issue(
                issues,
                path=path,
                message=f"Expected array but got {_type_label(value)}.",
            )
            return None
        return value

    def expect_str(value: Any, path: str) -> None:
        if not isinstance(value, str):
            _append_shape_issue(
                issues,
                path=path,
                message=f"Expected string but got {_type_label(value)}.",
            )

    def expect_num(value: Any, path: str) -> None:
        if not _is_finite_num(value):
            _append_shape_issue(
                issues,
                path=path,
                message=f"Expected finite number but got {_type_label(value)}.",
            )

    def expect_optional_str(value: Any, path: str) -> None:
        if value is not None and not isinstance(value, str):
            _append_shape_issue(
                issues,
                path=path,
                message=f"Expected string or null but got {_type_label(value)}.",
            )

    def expect_string_list(value: Any, path: str) -> None:
        items = expect_list(value, path)
        if items is None:
            return
        for index, item in enumerate(items):
            if not isinstance(item, str):
                _append_shape_issue(
                    issues,
                    path=f"{path}[{index}]",
                    message=f"Expected string but got {_type_label(item)}.",
                )

    def expect_number_list(value: Any, path: str) -> None:
        items = expect_list(value, path)
        if items is None:
            return
        for index, item in enumerate(items):
            if not _is_finite_num(item):
                _append_shape_issue(
                    issues,
                    path=f"{path}[{index}]",
                    message=f"Expected finite number but got {_type_label(item)}.",
                )

    def expect_enum(value: Any, path: str, allowed: set[str]) -> None:
        if not isinstance(value, str):
            _append_shape_issue(
                issues,
                path=path,
                message=f"Expected one of {sorted(allowed)} but got {_type_label(value)}.",
            )
            return
        if value not in allowed:
            _append_shape_issue(
                issues,
                path=path,
                message=f"Value '{value}' is not allowed. Expected one of {sorted(allowed)}.",
            )

    def validate_track_grounding(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        expect_string_list(record.get("phase1Fields"), f"{path}.phase1Fields")
        if "segmentIndexes" in record and record.get("segmentIndexes") is not None:
            expect_number_list(record.get("segmentIndexes"), f"{path}.segmentIndexes")

    def validate_project_setup(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        expect_num(record.get("tempoBpm"), f"{path}.tempoBpm")
        expect_str(record.get("timeSignature"), f"{path}.timeSignature")
        expect_num(record.get("sampleRate"), f"{path}.sampleRate")
        expect_num(record.get("bitDepth"), f"{path}.bitDepth")
        expect_str(record.get("headroomTarget"), f"{path}.headroomTarget")
        expect_str(record.get("sessionGoal"), f"{path}.sessionGoal")

    def validate_track_layout(value: Any, path: str) -> None:
        items = expect_list(value, path)
        if items is None:
            return
        for index, item in enumerate(items):
            item_path = f"{path}[{index}]"
            record = expect_record(item, item_path)
            if record is None:
                continue
            expect_num(record.get("order"), f"{item_path}.order")
            expect_str(record.get("name"), f"{item_path}.name")
            expect_str(record.get("type"), f"{item_path}.type")
            expect_str(record.get("purpose"), f"{item_path}.purpose")
            validate_track_grounding(record.get("grounding"), f"{item_path}.grounding")

    def validate_routing_blueprint(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        expect_optional_str(record.get("sidechainSource"), f"{path}.sidechainSource")
        expect_string_list(record.get("sidechainTargets"), f"{path}.sidechainTargets")
        returns = expect_list(record.get("returns"), f"{path}.returns")
        if returns is not None:
            for index, item in enumerate(returns):
                item_path = f"{path}.returns[{index}]"
                return_record = expect_record(item, item_path)
                if return_record is None:
                    continue
                expect_str(return_record.get("name"), f"{item_path}.name")
                expect_str(return_record.get("purpose"), f"{item_path}.purpose")
                expect_string_list(return_record.get("sendSources"), f"{item_path}.sendSources")
                expect_str(return_record.get("deviceFocus"), f"{item_path}.deviceFocus")
                expect_str(return_record.get("levelGuidance"), f"{item_path}.levelGuidance")
        expect_string_list(record.get("notes"), f"{path}.notes")

    def validate_warp_target(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        expect_enum(record.get("warpMode"), f"{path}.warpMode", _ALLOWED_PHASE2_WARP_MODES)
        expect_optional_str(record.get("settings"), f"{path}.settings")
        expect_str(record.get("reason"), f"{path}.reason")

    def validate_warp_guide(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        validate_warp_target(record.get("fullTrack"), f"{path}.fullTrack")
        validate_warp_target(record.get("drums"), f"{path}.drums")
        validate_warp_target(record.get("bass"), f"{path}.bass")
        validate_warp_target(record.get("melodic"), f"{path}.melodic")
        if record.get("vocals") is not None:
            validate_warp_target(record.get("vocals"), f"{path}.vocals")
        expect_str(record.get("rationale"), f"{path}.rationale")

    def validate_detected_characteristics(value: Any, path: str) -> None:
        items = expect_list(value, path)
        if items is None:
            return
        for index, item in enumerate(items):
            item_path = f"{path}[{index}]"
            record = expect_record(item, item_path)
            if record is None:
                continue
            expect_str(record.get("name"), f"{item_path}.name")
            expect_enum(record.get("confidence"), f"{item_path}.confidence", {"HIGH", "MED", "LOW"})
            expect_str(record.get("explanation"), f"{item_path}.explanation")

    def validate_audio_observations(value: Any, path: str) -> None:
        if value is None:
            return
        record = expect_record(value, path)
        if record is None:
            return
        expect_str(record.get("soundDesignFingerprint"), f"{path}.soundDesignFingerprint")
        elements = expect_list(record.get("elementCharacter"), f"{path}.elementCharacter")
        if elements is not None:
            for index, item in enumerate(elements):
                item_path = f"{path}.elementCharacter[{index}]"
                element_record = expect_record(item, item_path)
                if element_record is None:
                    continue
                expect_str(element_record.get("element"), f"{item_path}.element")
                expect_str(element_record.get("description"), f"{item_path}.description")
        expect_string_list(record.get("productionSignatures"), f"{path}.productionSignatures")
        expect_str(record.get("mixContext"), f"{path}.mixContext")

    def validate_arrangement_overview(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        expect_str(record.get("summary"), f"{path}.summary")
        segments = expect_list(record.get("segments"), f"{path}.segments")
        if segments is not None:
            for index, item in enumerate(segments):
                item_path = f"{path}.segments[{index}]"
                segment_record = expect_record(item, item_path)
                if segment_record is None:
                    continue
                expect_num(segment_record.get("index"), f"{item_path}.index")
                expect_num(segment_record.get("startTime"), f"{item_path}.startTime")
                expect_num(segment_record.get("endTime"), f"{item_path}.endTime")
                if segment_record.get("lufs") is not None:
                    expect_num(segment_record.get("lufs"), f"{item_path}.lufs")
                expect_str(segment_record.get("description"), f"{item_path}.description")
                expect_optional_str(segment_record.get("spectralNote"), f"{item_path}.spectralNote")
                expect_str(segment_record.get("sceneName"), f"{item_path}.sceneName")
                expect_str(segment_record.get("abletonAction"), f"{item_path}.abletonAction")
                expect_str(segment_record.get("automationFocus"), f"{item_path}.automationFocus")
        expect_optional_str(record.get("noveltyNotes"), f"{path}.noveltyNotes")

    def validate_sonic_elements(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        for key in ("kick", "bass", "melodicArp", "grooveAndTiming", "effectsAndTexture"):
            expect_str(record.get(key), f"{path}.{key}")
        for key in ("widthAndStereo", "harmonicContent"):
            if key in record:
                expect_optional_str(record.get(key), f"{path}.{key}")

    def validate_mix_chain(value: Any, path: str) -> None:
        items = expect_list(value, path)
        if items is None:
            return
        for index, item in enumerate(items):
            item_path = f"{path}[{index}]"
            record = expect_record(item, item_path)
            if record is None:
                continue
            expect_num(record.get("order"), f"{item_path}.order")
            expect_str(record.get("device"), f"{item_path}.device")
            expect_enum(record.get("deviceFamily"), f"{item_path}.deviceFamily", _ALLOWED_LIVE12_DEVICE_FAMILIES)
            expect_str(record.get("trackContext"), f"{item_path}.trackContext")
            expect_enum(record.get("workflowStage"), f"{item_path}.workflowStage", _ALLOWED_PHASE2_WORKFLOW_STAGES)
            expect_str(record.get("parameter"), f"{item_path}.parameter")
            expect_str(record.get("value"), f"{item_path}.value")
            expect_str(record.get("reason"), f"{item_path}.reason")

    def validate_secret_sauce(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        expect_str(record.get("title"), f"{path}.title")
        if "icon" in record:
            expect_optional_str(record.get("icon"), f"{path}.icon")
        expect_str(record.get("explanation"), f"{path}.explanation")
        expect_string_list(record.get("implementationSteps"), f"{path}.implementationSteps")
        workflow_steps = expect_list(record.get("workflowSteps"), f"{path}.workflowSteps")
        if workflow_steps is not None:
            for index, item in enumerate(workflow_steps):
                item_path = f"{path}.workflowSteps[{index}]"
                step_record = expect_record(item, item_path)
                if step_record is None:
                    continue
                expect_num(step_record.get("step"), f"{item_path}.step")
                expect_str(step_record.get("trackContext"), f"{item_path}.trackContext")
                expect_str(step_record.get("device"), f"{item_path}.device")
                expect_str(step_record.get("parameter"), f"{item_path}.parameter")
                expect_str(step_record.get("value"), f"{item_path}.value")
                expect_str(step_record.get("instruction"), f"{item_path}.instruction")
                expect_str(
                    step_record.get("measurementJustification"),
                    f"{item_path}.measurementJustification",
                )

    def validate_confidence_notes(value: Any, path: str) -> None:
        items = expect_list(value, path)
        if items is None:
            return
        for index, item in enumerate(items):
            item_path = f"{path}[{index}]"
            record = expect_record(item, item_path)
            if record is None:
                continue
            expect_str(record.get("field"), f"{item_path}.field")
            expect_str(record.get("value"), f"{item_path}.value")
            expect_str(record.get("reason"), f"{item_path}.reason")

    def validate_ableton_recommendations(value: Any, path: str) -> None:
        items = expect_list(value, path)
        if items is None:
            return
        for index, item in enumerate(items):
            item_path = f"{path}[{index}]"
            record = expect_record(item, item_path)
            if record is None:
                continue
            expect_str(record.get("device"), f"{item_path}.device")
            expect_enum(record.get("deviceFamily"), f"{item_path}.deviceFamily", _ALLOWED_LIVE12_DEVICE_FAMILIES)
            expect_str(record.get("trackContext"), f"{item_path}.trackContext")
            expect_enum(record.get("workflowStage"), f"{item_path}.workflowStage", _ALLOWED_PHASE2_WORKFLOW_STAGES)
            expect_enum(record.get("category"), f"{item_path}.category", _ALLOWED_PHASE2_RECOMMENDATION_CATEGORIES)
            expect_str(record.get("parameter"), f"{item_path}.parameter")
            expect_str(record.get("value"), f"{item_path}.value")
            expect_str(record.get("reason"), f"{item_path}.reason")
            expect_str(record.get("advancedTip"), f"{item_path}.advancedTip")

    record = expect_record(data, "root")
    if record is None:
        return issues

    expect_str(record.get("trackCharacter"), "trackCharacter")
    validate_project_setup(record.get("projectSetup"), "projectSetup")
    validate_track_layout(record.get("trackLayout"), "trackLayout")
    validate_routing_blueprint(record.get("routingBlueprint"), "routingBlueprint")
    validate_warp_guide(record.get("warpGuide"), "warpGuide")
    validate_detected_characteristics(record.get("detectedCharacteristics"), "detectedCharacteristics")
    validate_audio_observations(record.get("audioObservations"), "audioObservations")
    validate_arrangement_overview(record.get("arrangementOverview"), "arrangementOverview")
    validate_sonic_elements(record.get("sonicElements"), "sonicElements")
    validate_mix_chain(record.get("mixAndMasterChain"), "mixAndMasterChain")
    validate_secret_sauce(record.get("secretSauce"), "secretSauce")
    validate_confidence_notes(record.get("confidenceNotes"), "confidenceNotes")
    validate_ableton_recommendations(record.get("abletonRecommendations"), "abletonRecommendations")
    return issues


def _parse_phase2_result_debug(response_text: str | None) -> dict[str, Any]:
    raw = (response_text or "").strip()
    if not raw:
        return {
            "result": None,
            "skipMessage": "Phase 2 advisory skipped because Gemini returned an empty response.",
            "skipReason": "empty_response",
            "parseOutcome": "skipped",
            "rawResponseText": raw,
            "shapeIssues": [],
            "validationWarnings": [],
        }
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            "result": None,
            "skipMessage": "Phase 2 advisory skipped because Gemini returned invalid JSON.",
            "skipReason": "invalid_json",
            "parseOutcome": "skipped",
            "rawResponseText": raw,
            "shapeIssues": [],
            "parseError": str(exc),
            "validationWarnings": [],
        }
    validation_warnings: list[dict[str, Any]] = []
    emptied_required_arrays: set[str] = set()
    record = _as_record(parsed)
    if record is not None:
        parsed = _sanitize_optional_phase2_fields(record)
        parsed, validation_warnings, emptied_required_arrays = _normalize_and_salvage_phase2_result(
            parsed
        )
    shape_issues = _collect_phase2_shape_issues(parsed)
    for array_path in sorted(emptied_required_arrays):
        _append_shape_issue(
            shape_issues,
            path=array_path,
            message="Required array became empty after bounded salvage.",
        )
    if shape_issues:
        return {
            "result": None,
            "skipMessage": "Phase 2 advisory skipped because Gemini returned an invalid response shape.",
            "skipReason": "invalid_shape",
            "parseOutcome": "skipped",
            "rawResponseText": raw,
            "shapeIssues": shape_issues,
            "validationWarnings": validation_warnings,
        }
    return {
        "result": parsed,
        "skipMessage": None,
        "skipReason": None,
        "parseOutcome": "valid",
        "rawResponseText": raw,
        "shapeIssues": [],
        "validationWarnings": validation_warnings,
    }


def _parse_phase2_result(
    response_text: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Returns (result, skip_message). Mirrors parsePhase2Result() in geminiPhase2Client.ts.

    Skip cases return 200 with phase2=null — they are NOT errors.
    """
    debug = _parse_phase2_result_debug(response_text)
    return debug["result"], debug["skipMessage"]


def _build_phase2_validation_warning(
    *,
    code: str,
    path: str,
    message: str,
    original_value: str | None = None,
    coerced_value: str | None = None,
    drop_reason: str | None = None,
) -> dict[str, Any]:
    warning = {
        "code": code,
        "path": path,
        "message": message,
    }
    if original_value is not None:
        warning["originalValue"] = original_value
    if coerced_value is not None:
        warning["coercedValue"] = coerced_value
    if drop_reason is not None:
        warning["dropReason"] = drop_reason
    return warning


def _validate_phase2_catalog_entry(
    *,
    warnings: list[dict[str, Any]],
    device: str,
    device_family: str | None,
    parameter: str,
    base_path: str,
) -> None:
    catalog_entry = LIVE12_DEVICE_LOOKUP.get(device)
    if catalog_entry is None:
        warnings.append(
            _build_phase2_validation_warning(
                code="UNKNOWN_DEVICE",
                path=f"{base_path}.device",
                message=f"Device '{device}' is not in the curated Live 12 catalog.",
            )
        )
        return

    expected_family = catalog_entry["family"]
    if device_family is not None and device_family != expected_family:
        warnings.append(
            _build_phase2_validation_warning(
                code="DEVICE_FAMILY_MISMATCH",
                path=f"{base_path}.deviceFamily",
                message=(
                    f"Device '{device}' is tagged as '{device_family}', "
                    f"but the catalog says '{expected_family}'."
                ),
            )
        )

    allowed_parameters = set(catalog_entry.get("allowedParameters", []))
    if parameter not in allowed_parameters:
        warnings.append(
            _build_phase2_validation_warning(
                code="UNKNOWN_PARAMETER",
                path=f"{base_path}.parameter",
                message=(
                    f"Parameter '{parameter}' is not allowed for device '{device}' "
                    "in the curated Live 12 catalog."
                ),
            )
        )


def _valid_track_contexts(phase2_result: dict[str, Any]) -> set[str]:
    contexts = {"Master"}
    track_layout = phase2_result.get("trackLayout")
    if isinstance(track_layout, list):
        for item in track_layout:
            record = _as_record(item)
            if record and _is_str(record.get("name")):
                contexts.add(record["name"])

    routing_blueprint = _as_record(phase2_result.get("routingBlueprint"))
    returns = routing_blueprint.get("returns") if routing_blueprint else None
    if isinstance(returns, list):
        for item in returns:
            record = _as_record(item)
            if record and _is_str(record.get("name")):
                contexts.add(f"Return:{record['name']}")
    return contexts


def _validate_track_context(
    *,
    warnings: list[dict[str, Any]],
    track_context: str,
    base_path: str,
    valid_contexts: set[str],
) -> None:
    if track_context in valid_contexts:
        return
    warnings.append(
        _build_phase2_validation_warning(
            code="UNKNOWN_TRACK_CONTEXT",
            path=f"{base_path}.trackContext",
            message=(
                f"Track context '{track_context}' does not match trackLayout names, "
                "Master, or any Return:<name> context."
            ),
        )
    )


def _validate_phase2_semantics(phase2_result: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    valid_contexts = _valid_track_contexts(phase2_result)

    for index, item in enumerate(phase2_result.get("mixAndMasterChain") or []):
        record = _as_record(item)
        if not record:
            continue
        base_path = f"mixAndMasterChain[{index}]"
        _validate_phase2_catalog_entry(
            warnings=warnings,
            device=str(record.get("device")),
            device_family=str(record.get("deviceFamily")),
            parameter=str(record.get("parameter")),
            base_path=base_path,
        )
        _validate_track_context(
            warnings=warnings,
            track_context=str(record.get("trackContext")),
            base_path=base_path,
            valid_contexts=valid_contexts,
        )

    for index, item in enumerate(phase2_result.get("abletonRecommendations") or []):
        record = _as_record(item)
        if not record:
            continue
        base_path = f"abletonRecommendations[{index}]"
        _validate_phase2_catalog_entry(
            warnings=warnings,
            device=str(record.get("device")),
            device_family=str(record.get("deviceFamily")),
            parameter=str(record.get("parameter")),
            base_path=base_path,
        )
        _validate_track_context(
            warnings=warnings,
            track_context=str(record.get("trackContext")),
            base_path=base_path,
            valid_contexts=valid_contexts,
        )

    workflow_steps = _as_record(phase2_result.get("secretSauce"))
    steps = workflow_steps.get("workflowSteps") if workflow_steps else None
    if isinstance(steps, list):
        for index, item in enumerate(steps):
            record = _as_record(item)
            if not record:
                continue
            base_path = f"secretSauce.workflowSteps[{index}]"
            _validate_phase2_catalog_entry(
                warnings=warnings,
                device=str(record.get("device")),
                device_family=None,
                parameter=str(record.get("parameter")),
                base_path=base_path,
            )
            _validate_track_context(
                warnings=warnings,
                track_context=str(record.get("trackContext")),
                base_path=base_path,
                valid_contexts=valid_contexts,
            )

    return warnings


def _is_string_array(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_stem_summary_bars(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        record = _as_record(item)
        if not record:
            return False
        if not (
            _is_finite_num(record.get("barStart"))
            and _is_finite_num(record.get("barEnd"))
            and _is_finite_num(record.get("startTime"))
            and _is_finite_num(record.get("endTime"))
            and _is_string_array(record.get("noteHypotheses"))
            and _is_string_array(record.get("scaleDegreeHypotheses"))
            and _is_str(record.get("rhythmicPattern"))
            and record.get("uncertaintyLevel") in ("LOW", "MED", "HIGH")
            and _is_str(record.get("uncertaintyReason"))
        ):
            return False
    return True


def _is_stem_summary_global_patterns(value: Any) -> bool:
    record = _as_record(value)
    if not record:
        return False
    return (
        _is_str(record.get("bassRole"))
        and _is_str(record.get("melodicRole"))
        and _is_str(record.get("pumpingOrModulation"))
    )


def _is_valid_stem_summary_shape(value: Any) -> bool:
    record = _as_record(value)
    if not record:
        return False
    return (
        _is_str(record.get("summary"))
        and _is_stem_summary_bars(record.get("bars"))
        and _is_stem_summary_global_patterns(record.get("globalPatterns"))
        and _is_string_array(record.get("uncertaintyFlags"))
    )


def _parse_stem_summary_result(
    response_text: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    raw = (response_text or "").strip()
    if not raw:
        return None, "Stem summary skipped because Gemini returned an empty response."
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None, "Stem summary skipped because Gemini returned invalid JSON."
    if not _is_valid_stem_summary_shape(parsed):
        return None, "Stem summary skipped because Gemini returned an invalid response shape."
    return parsed, None


def _build_phase2_success_response(
    *,
    request_id: str,
    phase2_result: dict[str, Any] | None,
    message: str,
    model_name: str,
    request_started_at: datetime,
    api_started_at: datetime | None,
    api_completed_at: datetime | None,
    flags_used: list[str],
    file_size_bytes: int,
) -> JSONResponse:
    estimate: dict[str, Any] = {"totalLowMs": 0, "totalHighMs": 0}
    diagnostics = _build_diagnostics(
        request_id=request_id,
        estimate=estimate,
        timeout_seconds=GEMINI_TIMEOUT_SECONDS,
        request_started_at=request_started_at,
        analysis_started_at=api_started_at,
        analysis_completed_at=api_completed_at,
        flags_used=flags_used,
        file_size_bytes=file_size_bytes,
        file_duration_seconds=None,
        engine_version=model_name,
    )
    return JSONResponse(
        content={
            "requestId": request_id,
            "phase2": phase2_result,
            "message": message,
            "diagnostics": diagnostics,
        }
    )


def _build_phase2_error_response(
    *,
    request_id: str,
    analysis_run_id: str | None = None,
    status_code: int,
    error_code: str,
    message: str,
    retryable: bool,
    model_name: str,
    request_started_at: datetime,
    api_started_at: datetime | None,
    api_completed_at: datetime | None,
    flags_used: list[str],
    file_size_bytes: int,
    stderr: Any = None,
) -> JSONResponse:
    estimate: dict[str, Any] = {"totalLowMs": 0, "totalHighMs": 0}
    diagnostics = _build_diagnostics(
        request_id=request_id,
        estimate=estimate,
        timeout_seconds=GEMINI_TIMEOUT_SECONDS,
        request_started_at=request_started_at,
        analysis_started_at=api_started_at,
        analysis_completed_at=api_completed_at,
        flags_used=flags_used,
        file_size_bytes=file_size_bytes,
        file_duration_seconds=None,
        engine_version=model_name,
        stderr=stderr,
    )
    return _mark_legacy_endpoint_response(JSONResponse(
        status_code=status_code,
        content={
            "requestId": request_id,
            **({"analysisRunId": analysis_run_id} if analysis_run_id else {}),
            "error": {
                "code": error_code,
                "message": message,
                "phase": ERROR_PHASE_GEMINI,
                "retryable": retryable,
            },
            "diagnostics": diagnostics,
        },
    ), endpoint="/api/phase2")


# ---------------------------------------------------------------------------
# End Gemini Phase 2 helpers
# ---------------------------------------------------------------------------


def _compute_timeout_seconds(estimate: dict[str, Any]) -> int:
    estimated_high_ms = _coerce_positive_int(estimate.get("totalHighMs"))
    if estimated_high_ms > 0:
        estimated_high_seconds = ceil(estimated_high_ms / 1000)
        estimated_budget_seconds = (
            ceil(estimated_high_seconds * ANALYZE_TIMEOUT_ESTIMATE_MULTIPLIER)
            + ANALYZE_TIMEOUT_BUFFER_SECONDS
        )
        return max(
            estimated_budget_seconds,
            ANALYZE_TIMEOUT_FLOOR_SECONDS,
        )
    return ANALYZE_TIMEOUT_FALLBACK_SECONDS


def _compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _round_timing_value(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _format_timing_summary_value(
    value: float | None, suffix: str = "", digits: int = 1
) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}{suffix}"


def _build_timings(
    *,
    request_started_at: datetime,
    analysis_started_at: datetime | None,
    analysis_completed_at: datetime | None,
    flags_used: list[str],
    file_size_bytes: int,
    file_duration_seconds: float | None,
) -> dict[str, Any]:
    response_ready_at = _current_time()
    total_ms = _elapsed_ms(request_started_at, response_ready_at)
    analysis_ms = _elapsed_ms(analysis_started_at, analysis_completed_at)
    server_overhead_ms = max(total_ms - analysis_ms, 0.0)
    normalized_duration_seconds = _coerce_nullable_number(file_duration_seconds)
    ms_per_second_of_audio = None
    if normalized_duration_seconds is not None and normalized_duration_seconds > 0:
        ms_per_second_of_audio = analysis_ms / normalized_duration_seconds

    return {
        "totalMs": _round_timing_value(total_ms),
        "analysisMs": _round_timing_value(analysis_ms),
        "serverOverheadMs": _round_timing_value(server_overhead_ms),
        "flagsUsed": list(flags_used),
        "fileSizeBytes": int(file_size_bytes),
        "fileDurationSeconds": _round_timing_value(normalized_duration_seconds),
        "msPerSecondOfAudio": _round_timing_value(ms_per_second_of_audio),
    }


def _log_timing_summary(timings: dict[str, Any]) -> None:
    flags_used = timings.get("flagsUsed")
    flags_label = (
        f"[{', '.join(flags_used)}]"
        if isinstance(flags_used, list) and flags_used
        else "[]"
    )
    file_size_bytes = _coerce_positive_int(timings.get("fileSizeBytes"))
    file_size_mb = file_size_bytes / (1024 * 1024)
    print(
        f"[TIMING] total={_format_timing_summary_value(timings.get('totalMs'), 'ms')} "
        f"analysis={_format_timing_summary_value(timings.get('analysisMs'), 'ms')} "
        f"overhead={_format_timing_summary_value(timings.get('serverOverheadMs'), 'ms')} "
        f"flags={flags_label} "
        f"fileSize={_format_timing_summary_value(file_size_mb, 'MB')} "
        f"duration={_format_timing_summary_value(timings.get('fileDurationSeconds'), 's')} "
        f"ms/s={_format_timing_summary_value(timings.get('msPerSecondOfAudio'), digits=2)}",
        file=sys.stderr,
    )


def _build_diagnostics(
    *,
    request_id: str,
    estimate: dict[str, Any],
    timeout_seconds: int,
    request_started_at: datetime,
    analysis_started_at: datetime | None,
    analysis_completed_at: datetime | None,
    flags_used: list[str],
    file_size_bytes: int,
    file_duration_seconds: float | None,
    engine_version: str | None = None,
    stdout: Any = None,
    stderr: Any = None,
    validation_warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    timings = _build_timings(
        request_started_at=request_started_at,
        analysis_started_at=analysis_started_at,
        analysis_completed_at=analysis_completed_at,
        flags_used=flags_used,
        file_size_bytes=file_size_bytes,
        file_duration_seconds=file_duration_seconds,
    )
    _log_timing_summary(timings)
    return _compact_dict(
        {
            "requestId": request_id,
            "backendDurationMs": timings["analysisMs"],
            "engineVersion": engine_version,
            "estimatedLowMs": _coerce_positive_int(estimate.get("totalLowMs")),
            "estimatedHighMs": _coerce_positive_int(estimate.get("totalHighMs")),
            "timeoutSeconds": timeout_seconds,
            "timings": timings,
            "stdoutSnippet": _safe_snippet(stdout),
            "stderrSnippet": _safe_snippet(stderr),
            "validationWarnings": validation_warnings if validation_warnings else None,
        }
    )


def _build_error_response(
    *,
    request_id: str,
    status_code: int,
    error_code: str,
    message: str,
    retryable: bool,
    timeout_seconds: int,
    estimate: dict[str, Any],
    request_started_at: datetime,
    analysis_started_at: datetime | None,
    analysis_completed_at: datetime | None,
    flags_used: list[str],
    file_size_bytes: int,
    file_duration_seconds: float | None,
    stdout: Any = None,
    stderr: Any = None,
) -> JSONResponse:
    diagnostics = _build_diagnostics(
        request_id=request_id,
        estimate=estimate,
        timeout_seconds=timeout_seconds,
        request_started_at=request_started_at,
        analysis_started_at=analysis_started_at,
        analysis_completed_at=analysis_completed_at,
        flags_used=flags_used,
        file_size_bytes=file_size_bytes,
        file_duration_seconds=file_duration_seconds,
        stdout=stdout,
        stderr=stderr,
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "requestId": request_id,
            "error": {
                "code": error_code,
                "message": message,
                "phase": ERROR_PHASE_LOCAL_DSP,
                "retryable": retryable,
            },
            "diagnostics": diagnostics,
        },
    )


def _build_success_response(
    *,
    request_id: str,
    analysis_run_id: str | None,
    payload: dict[str, Any],
    timeout_seconds: int,
    estimate: dict[str, Any],
    request_started_at: datetime,
    analysis_started_at: datetime,
    analysis_completed_at: datetime,
    flags_used: list[str],
    file_size_bytes: int,
) -> JSONResponse:
    diagnostics = _build_diagnostics(
        request_id=request_id,
        estimate=estimate,
        timeout_seconds=timeout_seconds,
        request_started_at=request_started_at,
        analysis_started_at=analysis_started_at,
        analysis_completed_at=analysis_completed_at,
        flags_used=flags_used,
        file_size_bytes=file_size_bytes,
        file_duration_seconds=payload.get("durationSeconds"),
        engine_version=ENGINE_VERSION,
    )
    return JSONResponse(
        content={
            "requestId": request_id,
            "analysisRunId": analysis_run_id,
            "phase1": _build_phase1(payload),
            "diagnostics": diagnostics,
        }
    )


@app.post("/api/analyze/estimate")
async def estimate_analysis(
    track: UploadFile = File(...),
    dsp_json_override: str | None = Form(None),
    analysis_mode: str = Form("full"),
    transcribe: bool = Form(False),
    separate: bool = Form(False),
    separate_query: bool = Query(
        False, alias="separate", description="Pass --separate to analyze.py when true"
    ),
    separate_flag: bool = Query(
        False,
        alias="--separate",
        description="Alias for separate; accepts query key --separate",
    ),
):
    logger.warning("Legacy compatibility endpoint hit: /api/analyze/estimate")
    _ = dsp_json_override
    try:
        response = await _estimate_analysis_run(
            track=track,
            analysis_mode=analysis_mode,
            pitch_note_mode=_resolve_pitch_note_mode_for_legacy(transcribe),
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
            run_separation_override=bool(separate or separate_query or separate_flag),
            run_transcribe_override=bool(transcribe),
        )
        return _mark_legacy_endpoint_response(response, endpoint="/api/analyze/estimate")
    except UploadTooLargeError:
        return _legacy_upload_too_large_response(
            request_id=str(uuid4()),
            phase=ERROR_PHASE_LOCAL_DSP,
            endpoint="/api/analyze/estimate",
        )


@app.post("/api/analyze")
async def analyze_audio(
    track: UploadFile = File(...),
    dsp_json_override: str | None = Form(None),
    analysis_mode: str = Form("full"),
    transcribe: bool = Form(False),
    separate: bool = Form(False),
    separate_query: bool = Query(
        False, alias="separate", description="Pass --separate to analyze.py when true"
    ),
    separate_flag: bool = Query(
        False,
        alias="--separate",
        description="Alias for separate; accepts query key --separate",
    ),
    fast: bool = Form(False),
    fast_query: bool = Query(
        False, alias="fast", description="Pass --fast to analyze.py when true"
    ),
):
    request_id = str(uuid4())
    logger.warning("Legacy compatibility endpoint hit: /api/analyze request_id=%s", request_id)
    try:
        _ = dsp_json_override
        analysis_mode = _resolve_analysis_mode_value(analysis_mode)
        requested_pitch_note_mode = _resolve_pitch_note_mode_for_legacy(transcribe)
        runtime, run_id = await _create_analysis_run_record(
            track=track,
            analysis_mode=analysis_mode,
            pitch_note_mode=requested_pitch_note_mode,
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
            legacy_request_id=request_id,
        )
        runtime.reserve_measurement_run(run_id)
        resolved_run_separation = bool(separate or separate_query or separate_flag)
        resolved_run_transcribe = False
        execution = await asyncio.to_thread(
            _execute_measurement_run,
            runtime,
            run_id,
            request_id=request_id,
            run_separation=resolved_run_separation,
            run_transcribe=resolved_run_transcribe,
            run_standard=analysis_mode == "standard",
            run_fast=bool(fast or fast_query),
        )
        if not execution["ok"]:
            return _mark_legacy_endpoint_response(JSONResponse(
                status_code=execution["statusCode"],
                content={
                    "requestId": request_id,
                    "analysisRunId": run_id,
                    "error": {
                        "code": execution["errorCode"],
                        "message": execution["message"],
                        "phase": ERROR_PHASE_LOCAL_DSP,
                        "retryable": execution["retryable"],
                    },
                    "diagnostics": execution["diagnostics"],
                },
            ), endpoint="/api/analyze")

        return _mark_legacy_endpoint_response(JSONResponse(
            content={
                "requestId": request_id,
                "analysisRunId": run_id,
                "phase1": _build_phase1(execution["payload"]),
                "diagnostics": execution["diagnostics"],
            }
        ), endpoint="/api/analyze")
    except UploadTooLargeError:
        return _legacy_upload_too_large_response(
            request_id=request_id,
            phase=ERROR_PHASE_LOCAL_DSP,
            endpoint="/api/analyze",
        )
    except RuntimeError as exc:
        return _mark_legacy_endpoint_response(JSONResponse(
            status_code=429,
            content={
                "requestId": request_id,
                "error": {
                    "code": "MEASUREMENT_QUEUE_FULL",
                    "message": str(exc),
                    "phase": ERROR_PHASE_LOCAL_DSP,
                    "retryable": True,
                },
            },
        ), endpoint="/api/analyze")
    except ValueError as exc:
        return _mark_legacy_endpoint_response(JSONResponse(
            status_code=400,
            content={
                "requestId": request_id,
                "error": {
                    "code": _value_error_code(exc),
                    "message": str(exc),
                    "phase": ERROR_PHASE_LOCAL_DSP,
                    "retryable": False,
                },
            },
        ), endpoint="/api/analyze")
    finally:
        await track.close()


@app.post("/api/phase2")
async def analyze_phase2(
    track: UploadFile = File(...),
    phase1_json: str | None = Form(None),
    model_name: str = Form("gemini-2.5-flash"),
    phase1_request_id: str | None = Form(None),
    analysis_run_id: str | None = Form(None),
) -> JSONResponse:
    """Run Gemini Phase 2 advisory reconstruction server-side.

    Accepts the audio file plus deprecated compatibility fields.
    Canonical measurement input is always resolved from server-owned analysis state.
    Returns { requestId, phase2: Phase2Result | null, message, diagnostics }.
    Skip cases (empty/bad JSON/bad shape from Gemini) return 200 with phase2=null.
    Infrastructure failures (timeout, auth, quota) return 4xx/5xx.
    """
    request_id = str(uuid4())
    temp_path: str | None = None
    logger.warning("Legacy compatibility endpoint hit: /api/phase2 request_id=%s", request_id)
    try:
        temp_path, _ = _persist_upload(track)

        if not _GENAI_AVAILABLE:
            return _mark_legacy_endpoint_response(JSONResponse(
                status_code=500,
                content={
                    "requestId": request_id,
                    "error": {
                        "code": "GEMINI_NOT_INSTALLED",
                        "message": "google-genai package is not installed on the backend.",
                        "phase": ERROR_PHASE_GEMINI,
                        "retryable": False,
                    },
                },
            ), endpoint="/api/phase2")

        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            return _mark_legacy_endpoint_response(JSONResponse(
                status_code=500,
                content={
                    "requestId": request_id,
                    "error": {
                        "code": "GEMINI_NOT_CONFIGURED",
                        "message": "GEMINI_API_KEY is not set on the backend.",
                        "phase": ERROR_PHASE_GEMINI,
                        "retryable": False,
                    },
                },
            ), endpoint="/api/phase2")

        if model_name not in ALLOWED_GEMINI_MODELS:
            return _mark_legacy_endpoint_response(JSONResponse(
                status_code=400,
                content={
                    "requestId": request_id,
                    "error": {
                        "code": "INVALID_MODEL",
                        "message": f"model_name '{model_name}' is not allowed. Must be one of: {sorted(ALLOWED_GEMINI_MODELS)}",
                        "phase": ERROR_PHASE_GEMINI,
                        "retryable": False,
                    },
                },
            ), endpoint="/api/phase2")

        runtime = get_analysis_runtime()
        try:
            run_id = _resolve_phase2_run_id(
                runtime,
                analysis_run_id=analysis_run_id,
                phase1_request_id=phase1_request_id,
            )
        except KeyError:
            missing_context = not analysis_run_id and not phase1_request_id
            return _build_phase2_error_response(
                request_id=request_id,
                status_code=400 if missing_context else 404,
                error_code="PHASE2_MISSING_ANALYSIS_CONTEXT" if missing_context else "RUN_NOT_FOUND",
                message=(
                    "Phase 2 now requires a server-owned analysis run. "
                    "Provide analysis_run_id or phase1_request_id from /api/analyze."
                    if missing_context
                    else "The referenced analysis run was not found."
                ),
                retryable=False,
                model_name=model_name,
                request_started_at=_current_time(),
                api_started_at=None,
                api_completed_at=None,
                flags_used=[],
                file_size_bytes=0,
            )

        if runtime.get_measurement_status(run_id) != "completed":
            return _build_phase2_error_response(
                request_id=request_id,
                status_code=409,
                analysis_run_id=run_id,
                error_code="MEASUREMENT_NOT_READY",
                message="Server-owned measurement output is not ready for interpretation yet.",
                retryable=False,
                model_name=model_name,
                request_started_at=_current_time(),
                api_started_at=None,
                api_completed_at=None,
                flags_used=[],
                file_size_bytes=0,
            )

        attempt_id = runtime.create_interpretation_attempt(
            run_id,
            profile_id="producer_summary",
            model_name=model_name,
            status="queued",
            provenance={
                "schemaVersion": _interpretation_schema_version("producer_summary"),
                "compatibilityWrapper": True,
                "deprecatedPhase1JsonAccepted": phase1_json is not None,
                "requestedVia": "legacy_phase2_endpoint",
            },
        )
        runtime.reserve_interpretation_attempt(attempt_id)
        execution = await asyncio.to_thread(
            _execute_interpretation_attempt,
            runtime,
            {
                "attemptId": attempt_id,
                "runId": run_id,
                "profileId": "producer_summary",
                "modelName": model_name,
            },
        )
        if execution["ok"]:
            return _mark_legacy_endpoint_response(JSONResponse(
                content={
                    "requestId": request_id,
                    "analysisRunId": run_id,
                    "phase2": execution["interpretationResult"],
                    "message": execution["message"],
                    "diagnostics": execution["diagnostics"],
                }
            ), endpoint="/api/phase2")
        return _mark_legacy_endpoint_response(JSONResponse(
            status_code=execution["statusCode"],
            content={
                "requestId": request_id,
                "analysisRunId": run_id,
                "error": {
                    "code": execution["errorCode"],
                    "message": execution["message"],
                    "phase": ERROR_PHASE_GEMINI,
                    "retryable": execution["retryable"],
                },
                "diagnostics": execution["diagnostics"],
            },
        ), endpoint="/api/phase2")

    except UploadTooLargeError:
        return _legacy_upload_too_large_response(
            request_id=request_id,
            phase=ERROR_PHASE_GEMINI,
            endpoint="/api/phase2",
        )
    except Exception as exc:
        return _build_phase2_error_response(
            request_id=request_id,
            status_code=500,
            error_code="BACKEND_INTERNAL_ERROR",
            message="Phase 2 backend hit an unexpected server error.",
            retryable=False,
            model_name=model_name,
            request_started_at=_current_time(),
            api_started_at=None,
            api_completed_at=_current_time(),
            flags_used=[],
            file_size_bytes=0,
            stderr=str(exc),
        )
    finally:
        _cleanup_temp_path(temp_path)
        await track.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host=DEFAULT_SERVER_HOST, port=resolve_server_port(), reload=False)

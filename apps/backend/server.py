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
from datetime import datetime, timedelta
from math import ceil
from math import isfinite
from pathlib import Path
from typing import Any
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
from fastapi.responses import JSONResponse

from analysis_runtime import AnalysisRuntime, UnsupportedSymbolicModeError
from analyze import (
    BasicPitchBackend,
    analyze_transcription,
    build_analysis_estimate,
    get_audio_duration_seconds,
    separate_stems,
)


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

LEGACY_ENDPOINT_SUNSET = "Wed, 31 Dec 2026 23:59:59 GMT"


def _load_prompt_template(name: str) -> str:
    path = _PROMPTS_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuntimeError(
            f"Prompt template '{name}' not found at {path}. "
            "Re-run from the apps/backend directory."
        ) from None


def _mark_legacy_endpoint_response(response: JSONResponse, *, endpoint: str) -> JSONResponse:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = LEGACY_ENDPOINT_SUNSET
    response.headers["Link"] = '</api/analysis-runs>; rel="successor-version"'
    response.headers["Warning"] = (
        f'299 - "{endpoint} is deprecated; use /api/analysis-runs instead."'
    )
    return response


PRODUCER_SUMMARY_PROMPT_TEMPLATE = _load_prompt_template("phase2_system.txt")
STEM_SUMMARY_PROMPT_TEMPLATE = _load_prompt_template("stem_summary_system.txt")
PHASE2_PROMPT_TEMPLATE = PRODUCER_SUMMARY_PROMPT_TEMPLATE
SUPPORTED_INTERPRETATION_PROFILES = {"producer_summary", "stem_summary"}

PHASE2_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "trackCharacter": {"type": "STRING"},
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
                        },
                        "required": ["index", "startTime", "endTime", "description"],
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
                    "parameter": {"type": "STRING"},
                    "value": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                },
                "required": ["order", "device", "parameter", "value", "reason"],
            },
        },
        "secretSauce": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING"},
                "icon": {"type": "STRING"},
                "explanation": {"type": "STRING"},
                "implementationSteps": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
            "required": ["title", "explanation", "implementationSteps"],
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
                    "category": {"type": "STRING"},
                    "parameter": {"type": "STRING"},
                    "value": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                    "advancedTip": {"type": "STRING"},
                },
                "required": ["device", "category", "parameter", "value", "reason"],
            },
        },
    },
    "required": [
        "trackCharacter",
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_FILE_CACHE: dict[str, tuple[str, datetime]] = {}
_FILE_CACHE_TTL_SECONDS = 900  # 15 minutes
_FILE_CACHE_LOCK = threading.Lock()


def _cache_temp_file(request_id: str, temp_path: str, now: datetime | None = None) -> None:
    if now is None:
        now = _current_time()
    expires_at = now + timedelta(seconds=_FILE_CACHE_TTL_SECONDS)
    with _FILE_CACHE_LOCK:
        _FILE_CACHE[request_id] = (temp_path, expires_at)


def _pop_cached_temp_file(request_id: str | None) -> str | None:
    if not request_id:
        return None
    with _FILE_CACHE_LOCK:
        entry = _FILE_CACHE.pop(request_id, None)
    if entry is None:
        return None
    temp_path, expires_at = entry
    if _current_time() > expires_at:
        _cleanup_temp_path(temp_path)
        return None
    return temp_path


def _evict_expired_cache_entries() -> None:
    now = _current_time()
    with _FILE_CACHE_LOCK:
        expired = [rid for rid, (_, exp) in _FILE_CACHE.items() if now > exp]
        for rid in expired:
            path, _ = _FILE_CACHE.pop(rid)
            _cleanup_temp_path(path)


@app.on_event("startup")
async def _start_cache_eviction() -> None:
    get_analysis_runtime().recover_incomplete_attempts()

    async def _evict_loop() -> None:
        while True:
            await asyncio.sleep(300)
            _evict_expired_cache_entries()

    if not _BACKGROUND_TASKS:
        _BACKGROUND_TASKS.extend(
            [
                asyncio.create_task(_evict_loop()),
                asyncio.create_task(_measurement_worker_loop()),
                asyncio.create_task(_symbolic_worker_loop()),
                asyncio.create_task(_interpretation_worker_loop()),
            ]
        )


@app.on_event("shutdown")
async def _stop_background_tasks() -> None:
    global _BACKGROUND_TASKS
    for task in _BACKGROUND_TASKS:
        task.cancel()
    _BACKGROUND_TASKS = []


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


def _normalize_run_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Apply _build_phase1 normalization to a run snapshot's measurement result.

    The analysis-run pathway stores raw analyze.py output in the DB, but the
    frontend parser (parsePhase1Result) expects the same normalized shape that
    _build_phase1 produces for the legacy /api/analyze endpoint — notably,
    top-level stereoWidth/stereoCorrelation extracted from stereoDetail.
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
    return snapshot


def _build_phase1(payload: dict[str, Any]) -> dict[str, Any]:
    stereo_detail = payload.get("stereoDetail")
    if not isinstance(stereo_detail, dict):
        stereo_detail = {}

    spectral_balance = payload.get("spectralBalance")
    if not isinstance(spectral_balance, dict):
        spectral_balance = {}

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
        "durationSeconds": _coerce_number(payload.get("durationSeconds")),
        "sampleRate": payload.get("sampleRate"),
        "lufsIntegrated": _coerce_number(payload.get("lufsIntegrated")),
        "lufsRange": _coerce_nullable_number(payload.get("lufsRange")),
        "lufsMomentaryMax": _coerce_nullable_number(payload.get("lufsMomentaryMax")),
        "lufsShortTermMax": _coerce_nullable_number(payload.get("lufsShortTermMax")),
        "truePeak": _coerce_number(payload.get("truePeak")),
        "crestFactor": _coerce_nullable_number(payload.get("crestFactor")),
        "dynamicSpread": _coerce_nullable_number(payload.get("dynamicSpread")),
        "dynamicCharacter": payload.get("dynamicCharacter"),
        "stereoWidth": _coerce_number(stereo_detail.get("stereoWidth")),
        "stereoCorrelation": _coerce_number(stereo_detail.get("stereoCorrelation")),
        "stereoDetail": payload.get("stereoDetail"),
        "spectralBalance": {
            "subBass": _coerce_number(spectral_balance.get("subBass")),
            "lowBass": _coerce_number(spectral_balance.get("lowBass")),
            "mids": _coerce_number(spectral_balance.get("mids")),
            "upperMids": _coerce_number(spectral_balance.get("upperMids")),
            "highs": _coerce_number(spectral_balance.get("highs")),
            "brilliance": _coerce_number(spectral_balance.get("brilliance")),
        },
        "spectralDetail": payload.get("spectralDetail"),
        "rhythmDetail": payload.get("rhythmDetail"),
        "melodyDetail": payload.get("melodyDetail"),
        "transcriptionDetail": payload.get("transcriptionDetail"),
        "grooveDetail": payload.get("grooveDetail"),
        "beatsLoudness": payload.get("beatsLoudness"),
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


def _persist_upload(track: UploadFile) -> tuple[str, int]:
    suffix = Path(track.filename or "upload.bin").suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = temp_file.name
        total_bytes = 0
        while True:
            chunk = track.file.read(1024 * 1024)
            if not chunk:
                break
            total_bytes += len(chunk)
            temp_file.write(chunk)
    return temp_path, total_bytes


def _cleanup_temp_path(temp_path: str | None) -> None:
    if temp_path and os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass


async def _create_analysis_run_record(
    *,
    track: UploadFile,
    symbolic_mode: str,
    symbolic_backend: str,
    interpretation_mode: str,
    interpretation_profile: str,
    interpretation_model: str | None,
    legacy_request_id: str | None = None,
) -> tuple[AnalysisRuntime, str]:
    content = await track.read()
    runtime = get_analysis_runtime()
    if interpretation_mode != "off":
        _resolve_interpretation_profile_config(interpretation_profile)
    created = runtime.create_run(
        filename=track.filename or "upload.bin",
        content=content,
        mime_type=track.content_type or _get_audio_mime_type(track.filename or "upload.bin"),
        symbolic_mode=symbolic_mode,
        symbolic_backend=symbolic_backend,
        interpretation_mode=interpretation_mode,
        interpretation_profile=interpretation_profile,
        interpretation_model=interpretation_model,
        legacy_request_id=legacy_request_id,
    )
    return runtime, created["runId"]


def _build_measurement_provenance(
    *,
    run_separation: bool,
    run_transcribe: bool,
    run_fast: bool,
) -> dict[str, Any]:
    return {
        "schemaVersion": "measurement.v1",
        "engineVersion": ENGINE_VERSION,
        "requestOptions": {
            "separate": run_separation,
            "transcribe": run_transcribe,
            "fast": run_fast,
        },
    }


def _resolve_symbolic_mode_for_legacy(transcribe: bool) -> str:
    return "stem_notes" if transcribe else "off"


def _run_measurement_subprocess(
    *,
    audio_path: str,
    file_size_bytes: int,
    request_id: str,
    request_started_at: datetime,
    run_separation: bool,
    run_transcribe: bool,
    run_fast: bool,
) -> dict[str, Any]:
    estimate = _build_backend_estimate(audio_path, run_separation, run_transcribe)
    command = ["./venv/bin/python", "analyze.py", audio_path, "--yes"]
    flags_used: list[str] = []
    if run_separation:
        command.append("--separate")
        flags_used.append("--separate")
    if run_transcribe:
        command.append("--transcribe")
        flags_used.append("--transcribe")
    if run_fast:
        command.append("--fast")
        flags_used.append("--fast")

    timeout_seconds = _compute_timeout_seconds(estimate)
    analysis_started_at = _current_time()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
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
            stdout=exc.stdout,
            stderr=exc.stderr,
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
            "stdout": exc.stdout,
            "stderr": exc.stderr,
            "diagnostics": diagnostics,
        }
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
    if result.returncode != 0:
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
            stdout=result.stdout,
            stderr=result.stderr,
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
            "stdout": result.stdout,
            "stderr": result.stderr,
            "diagnostics": diagnostics,
        }

    stdout = result.stdout.strip()
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
            stderr=result.stderr,
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
            "stderr": result.stderr,
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
            stderr=result.stderr,
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
            "stderr": result.stderr,
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
            stderr=result.stderr,
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
            "stderr": result.stderr,
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


def _execute_measurement_run(
    runtime: AnalysisRuntime,
    run_id: str,
    *,
    request_id: str,
    run_separation: bool,
    run_transcribe: bool,
    run_fast: bool,
) -> dict[str, Any]:
    source_artifact = runtime.get_source_artifact(run_id)
    execution = _run_measurement_subprocess(
        audio_path=source_artifact["path"],
        file_size_bytes=source_artifact["sizeBytes"],
        request_id=request_id,
        request_started_at=_current_time(),
        run_separation=run_separation,
        run_transcribe=run_transcribe,
        run_fast=run_fast,
    )
    provenance = _build_measurement_provenance(
        run_separation=run_separation,
        run_transcribe=run_transcribe,
        run_fast=run_fast,
    )
    if execution["ok"]:
        runtime.complete_measurement(
            run_id,
            payload=execution["payload"],
            provenance=provenance,
            diagnostics=execution["diagnostics"],
        )
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
    requested_symbolic_mode = str(job.get("requestedSymbolicMode", "off"))
    try:
        run_separation, run_transcribe = runtime.resolve_measurement_flags(
            requested_symbolic_mode,
        )
    except UnsupportedSymbolicModeError as exc:
        runtime.fail_measurement(
            run_id,
            error={
                "code": "SYMBOLIC_MODE_UNSUPPORTED",
                "message": str(exc),
                "retryable": False,
                "phase": ERROR_PHASE_LOCAL_DSP,
            },
            provenance={
                "schemaVersion": "measurement.v1",
                "engineVersion": ENGINE_VERSION,
                "requestOptions": {
                    "symbolicMode": requested_symbolic_mode,
                },
            },
        )
        return {
            "ok": False,
            "statusCode": 400,
            "errorCode": "SYMBOLIC_MODE_UNSUPPORTED",
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
        run_fast=False,
    )


def _resolve_transcription_backend(backend_id: str) -> Any:
    if backend_id in ("", "auto", "default", "transcription-backend:auto"):
        return None
    if backend_id in ("basic-pitch", "basic-pitch-legacy", "transcription-backend:basic-pitch-legacy"):
        return BasicPitchBackend()
    raise RuntimeError(f"Unsupported symbolic backend '{backend_id}'.")


def _get_or_materialize_stem_paths(
    runtime: AnalysisRuntime,
    run_id: str,
    source_path: str,
) -> dict[str, str] | None:
    existing = runtime.get_artifacts_by_kind(run_id, "stem_")
    stem_paths = {
        artifact["kind"].removeprefix("stem_"): artifact["path"]
        for artifact in existing
        if isinstance(artifact.get("path"), str) and os.path.isfile(artifact["path"])
    }
    if "bass" in stem_paths or "other" in stem_paths:
        return stem_paths

    output_dir = tempfile.mkdtemp(prefix=f"asa_stems_{run_id}_", dir=runtime.runtime_dir)
    try:
        separated = separate_stems(source_path, output_dir=output_dir)
        if not isinstance(separated, dict) or not separated:
            return None

        recorded_paths: dict[str, str] = {}
        for stem_name, stem_path in separated.items():
            if not isinstance(stem_path, str) or not os.path.isfile(stem_path):
                continue
            artifact = runtime.record_artifact(
                run_id,
                kind=f"stem_{stem_name}",
                source_path=stem_path,
                filename=Path(stem_path).name,
                mime_type="audio/wav",
                provenance={
                    "generator": "demucs_htdemucs",
                    "sourceRunId": run_id,
                },
            )
            recorded_paths[stem_name] = artifact["path"]
        return recorded_paths if recorded_paths else None
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def _execute_symbolic_attempt(
    runtime: AnalysisRuntime,
    attempt: dict[str, Any],
) -> None:
    started_at = _current_time()
    run_id = str(attempt["runId"])
    source_artifact = runtime.get_source_artifact(run_id)
    provenance = {
        "schemaVersion": "symbolic.v1",
        "backendId": attempt["backendId"],
        "mode": attempt["mode"],
    }
    try:
        stem_paths = None
        if attempt["mode"] == "stem_notes":
            stem_paths = _get_or_materialize_stem_paths(
                runtime,
                run_id,
                source_artifact["path"],
            )
        backend = _resolve_transcription_backend(str(attempt["backendId"]))
        symbolic_payload = analyze_transcription(
            source_artifact["path"],
            stem_paths=stem_paths,
            backend=backend,
        )
        transcription_detail = None
        if isinstance(symbolic_payload, dict):
            transcription_detail = symbolic_payload.get("transcriptionDetail")
        diagnostics = {
            "backendDurationMs": round(_elapsed_ms(started_at, _current_time()), 2),
            "stemSeparationUsed": bool(stem_paths),
            "sourceArtifactId": source_artifact["artifactId"],
        }
        if isinstance(transcription_detail, dict):
            provenance["resolvedBackendId"] = transcription_detail.get("transcriptionMethod")
        runtime.complete_symbolic_attempt(
            str(attempt["attemptId"]),
            result=transcription_detail if isinstance(transcription_detail, dict) else None,
            provenance=provenance,
            diagnostics=diagnostics,
        )
    except Exception as exc:
        runtime.fail_symbolic_attempt(
            str(attempt["attemptId"]),
            error={
                "code": "SYMBOLIC_EXTRACTION_FAILED",
                "message": str(exc),
                "retryable": True,
                "phase": "symbolic_extraction",
            },
            provenance=provenance,
            diagnostics={
                "backendDurationMs": round(_elapsed_ms(started_at, _current_time()), 2),
                "sourceArtifactId": source_artifact["artifactId"],
            },
        )


def _run_interpretation_request(
    *,
    source_path: str,
    filename: str,
    file_size_bytes: int,
    profile_id: str,
    measurement_result: dict[str, Any],
    symbolic_result: dict[str, Any] | None,
    grounding_metadata: dict[str, Any],
    model_name: str,
    request_id: str,
) -> dict[str, Any]:
    request_started_at = _current_time()
    flags_used: list[str] = []
    mime_type = _get_audio_mime_type(filename)
    descriptor_hooks = _build_descriptor_hooks(measurement_result)

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
        symbolic_result=symbolic_result,
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
        interpretation_result, skip_message = profile_config["parseResult"](response_text)
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
    source_artifact = runtime.get_source_artifact(run_id)
    grounding = runtime.get_interpretation_grounding(run_id)
    measurement_result = grounding["measurementResult"] or {}
    symbolic_result = grounding["symbolicResult"]
    grounding_metadata = {
        "measurementIsAuthoritative": True,
        "symbolicExtractionIsBestEffort": True,
        "measurementOutputId": grounding["measurementOutputId"],
        "symbolicAttemptId": grounding["symbolicAttemptId"],
        "doNotPromoteSymbolicToMeasurement": True,
        "profileId": profile_id,
    }
    model_name = _coerce_string(attempt.get("modelName"), "gemini-2.5-flash")
    execution = _run_interpretation_request(
        source_path=source_artifact["path"],
        filename=source_artifact["filename"],
        file_size_bytes=source_artifact["sizeBytes"],
        profile_id=profile_id,
        measurement_result=measurement_result,
        symbolic_result=symbolic_result,
        grounding_metadata=grounding_metadata,
        model_name=model_name,
        request_id=str(attempt["attemptId"]),
    )
    provenance = {
        "schemaVersion": "interpretation.v1",
        "profileId": profile_id,
        "modelName": model_name,
        "groundedMeasurementRunId": run_id,
        "groundedMeasurementOutputId": grounding["measurementOutputId"],
        "groundedSymbolicAttemptId": grounding["symbolicAttemptId"],
    }
    if execution["ok"]:
        runtime.complete_interpretation_attempt(
            str(attempt["attemptId"]),
            result=execution["interpretationResult"],
            provenance=provenance,
            diagnostics=execution["diagnostics"],
            grounded_measurement_output_id=grounding["measurementOutputId"],
            grounded_symbolic_attempt_id=grounding["symbolicAttemptId"],
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
        grounded_symbolic_attempt_id=grounding["symbolicAttemptId"],
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


async def _symbolic_worker_loop() -> None:
    while True:
        try:
            attempt = await asyncio.to_thread(get_analysis_runtime().reserve_next_symbolic_attempt)
            if attempt is None:
                await asyncio.sleep(WORKER_IDLE_SECONDS)
                continue
            await asyncio.to_thread(
                _execute_symbolic_attempt,
                get_analysis_runtime(),
                attempt,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[warn] symbolic worker loop failed: {exc}", file=sys.stderr)
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
    symbolic_mode: str = Form("off"),
    symbolic_backend: str = Form("auto"),
    interpretation_mode: str = Form("off"),
    interpretation_profile: str = Form("producer_summary"),
    interpretation_model: str | None = Form(None),
) -> JSONResponse:
    try:
        runtime, run_id = await _create_analysis_run_record(
            track=track,
            symbolic_mode=symbolic_mode,
            symbolic_backend=symbolic_backend,
            interpretation_mode=interpretation_mode,
            interpretation_profile=interpretation_profile,
            interpretation_model=interpretation_model,
        )
        return JSONResponse(content=_normalize_run_snapshot(runtime.get_run(run_id)))
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INTERPRETATION_PROFILE_UNSUPPORTED",
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


@app.get("/api/analysis-runs/{run_id}")
async def get_analysis_run(run_id: str) -> JSONResponse:
    runtime = get_analysis_runtime()
    try:
        return JSONResponse(content=_normalize_run_snapshot(runtime.get_run(run_id)))
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


@app.post("/api/analysis-runs/{run_id}/symbolic-extractions")
async def create_symbolic_extraction_attempt(
    run_id: str,
    symbolic_mode: str = Form("stem_notes"),
    symbolic_backend: str = Form("auto"),
) -> JSONResponse:
    runtime = get_analysis_runtime()
    try:
        if runtime.get_measurement_status(run_id) != "completed":
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "MEASUREMENT_NOT_READY",
                        "message": "Measurement must complete before symbolic extraction can run.",
                    }
                },
            )
        runtime.create_symbolic_attempt(
            run_id,
            backend_id=symbolic_backend,
            mode=symbolic_mode,
            status="queued",
            provenance={
                "schemaVersion": "symbolic.v1",
                "backendId": symbolic_backend,
                "mode": symbolic_mode,
                "requestedViaApi": True,
            },
        )
        return JSONResponse(status_code=202, content=_normalize_run_snapshot(runtime.get_run(run_id)))
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
                "schemaVersion": "interpretation.v1",
                "profileId": interpretation_profile,
                "modelName": interpretation_model,
                "requestedViaApi": True,
            },
        )
        return JSONResponse(status_code=202, content=_normalize_run_snapshot(runtime.get_run(run_id)))
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INTERPRETATION_PROFILE_UNSUPPORTED",
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
) -> dict[str, Any]:
    try:
        duration_seconds = get_audio_duration_seconds(audio_path)
    except Exception:
        duration_seconds = None

    safe_duration = duration_seconds if duration_seconds is not None else 0.0
    raw_estimate = build_analysis_estimate(
        safe_duration, run_separation, run_transcribe
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
    symbolic_result: dict[str, Any] | None,
    grounding_metadata: dict[str, Any],
    descriptor_hooks: dict[str, Any] | None = None,
) -> str:
    sections = [
        PRODUCER_SUMMARY_PROMPT_TEMPLATE.rstrip(),
        "\n\nAUTHORITATIVE_MEASUREMENT_RESULT_JSON:\n",
        json.dumps(measurement_result, indent=2),
        "\n\nOPTIONAL_SYMBOLIC_EXTRACTION_RESULT_JSON:\n",
        json.dumps(symbolic_result, indent=2),
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
    symbolic_result: dict[str, Any] | None,
    grounding_metadata: dict[str, Any],
    descriptor_hooks: dict[str, Any],
) -> str:
    sections = [
        STEM_SUMMARY_PROMPT_TEMPLATE.rstrip(),
        "\n\nAUTHORITATIVE_MEASUREMENT_RESULT_JSON:\n",
        json.dumps(measurement_result, indent=2),
        "\n\nOPTIONAL_SYMBOLIC_EXTRACTION_RESULT_JSON:\n",
        json.dumps(symbolic_result, indent=2),
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


def _resolve_interpretation_profile_config(profile_id: str) -> dict[str, Any]:
    if profile_id == "producer_summary":
        return {
            "responseSchema": PHASE2_RESPONSE_SCHEMA,
            "buildPrompt": _build_phase2_prompt,
            "parseResult": _parse_phase2_result,
            "successMessage": "AI interpretation complete.",
        }
    if profile_id == "stem_summary":
        return {
            "responseSchema": STEM_SUMMARY_RESPONSE_SCHEMA,
            "buildPrompt": _build_stem_summary_prompt,
            "parseResult": _parse_stem_summary_result,
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


def _as_record(v: Any) -> dict[str, Any] | None:
    if not v or not isinstance(v, dict):
        return None
    return v


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
        if not _is_opt_num(s.get("lufs")) or not _is_opt_str(s.get("spectralNote")):
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


def _is_mix_and_master_chain(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        r = _as_record(item)
        if not r:
            return False
        if not (_is_finite_num(r.get("order")) and _is_str(r.get("device"))
                and _is_str(r.get("parameter")) and _is_str(r.get("value"))
                and _is_str(r.get("reason"))):
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


def _is_ableton_recommendations(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        r = _as_record(item)
        if not r:
            return False
        required = ("device", "category", "parameter", "value", "reason")
        if not all(_is_str(r.get(k)) for k in required):
            return False
        if not _is_opt_str(r.get("advancedTip")):
            return False
    return True


def _is_valid_phase2_shape(data: Any) -> bool:
    """Mirrors isPhase2Result() in geminiPhase2Client.ts."""
    r = _as_record(data)
    if not r:
        return False
    return (
        _is_str(r.get("trackCharacter"))
        and _is_detected_characteristics(r.get("detectedCharacteristics"))
        and _is_arrangement_overview(r.get("arrangementOverview"))
        and _is_sonic_elements(r.get("sonicElements"))
        and _is_mix_and_master_chain(r.get("mixAndMasterChain"))
        and _is_secret_sauce(r.get("secretSauce"))
        and _is_confidence_notes(r.get("confidenceNotes"))
        and _is_ableton_recommendations(r.get("abletonRecommendations"))
    )


def _parse_phase2_result(
    response_text: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Returns (result, skip_message). Mirrors parsePhase2Result() in geminiPhase2Client.ts.

    Skip cases return 200 with phase2=null — they are NOT errors.
    """
    raw = (response_text or "").strip()
    if not raw:
        return None, "Phase 2 advisory skipped because Gemini returned an empty response."
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None, "Phase 2 advisory skipped because Gemini returned invalid JSON."
    if not _is_valid_phase2_shape(parsed):
        return None, "Phase 2 advisory skipped because Gemini returned an invalid response shape."
    return parsed, None


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
    temp_path: str | None = None
    try:
        temp_path, _file_size_bytes = _persist_upload(track)
        _ = dsp_json_override
        run_separation = bool(separate or separate_query or separate_flag)
        estimate = _build_backend_estimate(temp_path, run_separation, transcribe)
        return JSONResponse(
            content={
                "requestId": str(uuid4()),
                "estimate": estimate,
            }
        )
    finally:
        await track.close()
        _cleanup_temp_path(temp_path)


@app.post("/api/analyze")
async def analyze_audio(
    track: UploadFile = File(...),
    dsp_json_override: str | None = Form(None),
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
        requested_symbolic_mode = _resolve_symbolic_mode_for_legacy(transcribe)
        runtime, run_id = await _create_analysis_run_record(
            track=track,
            symbolic_mode=requested_symbolic_mode,
            symbolic_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
            legacy_request_id=request_id,
        )
        runtime.reserve_measurement_run(run_id)
        resolved_run_separation, resolved_run_transcribe = runtime.resolve_measurement_flags(
            requested_symbolic_mode,
        )
        execution = await asyncio.to_thread(
            _execute_measurement_run,
            runtime,
            run_id,
            request_id=request_id,
            run_separation=resolved_run_separation or bool(separate or separate_query or separate_flag),
            run_transcribe=resolved_run_transcribe,
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
    logger.warning("Legacy compatibility endpoint hit: /api/phase2 request_id=%s", request_id)
    try:
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
                "schemaVersion": "interpretation.v1",
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
        await track.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host=DEFAULT_SERVER_HOST, port=resolve_server_port(), reload=False)

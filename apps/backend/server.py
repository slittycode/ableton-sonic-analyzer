import asyncio
import base64
import json
import mimetypes
import os
import random
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

from analyze import build_analysis_estimate, get_audio_duration_seconds


app = FastAPI(title="Sonic Analyzer Local API")

ANALYZE_TIMEOUT_BUFFER_SECONDS = 15
ERROR_PHASE_LOCAL_DSP = "phase1_local_dsp"
ERROR_PHASE_GEMINI = "phase2_gemini"
ENGINE_VERSION = "analyze.py"
MAX_SNIPPET_LENGTH = 2000
DEFAULT_SERVER_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 8100

INLINE_SIZE_LIMIT = 20_971_520  # 20 MiB — matches geminiPhase2Client.ts
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


def _load_prompt_template(name: str) -> str:
    path = _PROMPTS_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuntimeError(
            f"Prompt template '{name}' not found at {path}. "
            "Re-run from the apps/backend directory."
        ) from None


PHASE2_PROMPT_TEMPLATE = _load_prompt_template("phase2_system.txt")

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
    async def _evict_loop() -> None:
        while True:
            await asyncio.sleep(300)
            _evict_expired_cache_entries()
    asyncio.create_task(_evict_loop())


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
        "key": _coerce_nullable_string(payload.get("key")),
        "keyConfidence": _coerce_number(payload.get("keyConfidence")),
        "timeSignature": _coerce_string(payload.get("timeSignature"), "4/4"),
        "durationSeconds": _coerce_number(payload.get("durationSeconds")),
        "lufsIntegrated": _coerce_number(payload.get("lufsIntegrated")),
        "lufsRange": _coerce_nullable_number(payload.get("lufsRange")),
        "truePeak": _coerce_number(payload.get("truePeak")),
        "crestFactor": _coerce_nullable_number(payload.get("crestFactor")),
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
        "sidechainDetail": payload.get("sidechainDetail"),
        "effectsDetail": payload.get("effectsDetail"),
        "synthesisCharacter": payload.get("synthesisCharacter"),
        "danceability": payload.get("danceability"),
        "structure": payload.get("structure"),
        "arrangementDetail": payload.get("arrangementDetail"),
        "segmentLoudness": payload.get("segmentLoudness"),
        "segmentSpectral": payload.get("segmentSpectral"),
        "segmentKey": payload.get("segmentKey"),
        "chordDetail": payload.get("chordDetail"),
        "perceptual": payload.get("perceptual"),
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


def _build_phase2_prompt(phase1_dict: dict[str, Any]) -> str:
    return PHASE2_PROMPT_TEMPLATE + json.dumps(phase1_dict, indent=2)


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
    return JSONResponse(
        status_code=status_code,
        content={
            "requestId": request_id,
            "error": {
                "code": error_code,
                "message": message,
                "phase": ERROR_PHASE_GEMINI,
                "retryable": retryable,
            },
            "diagnostics": diagnostics,
        },
    )


# ---------------------------------------------------------------------------
# End Gemini Phase 2 helpers
# ---------------------------------------------------------------------------


def _compute_timeout_seconds(estimate: dict[str, Any]) -> int:
    estimated_high_ms = _coerce_positive_int(estimate.get("totalHighMs"))
    estimated_high_seconds = (
        ceil(estimated_high_ms / 1000) if estimated_high_ms > 0 else 45
    )
    return estimated_high_seconds + ANALYZE_TIMEOUT_BUFFER_SECONDS


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
    temp_path: str | None = None
    request_id = str(uuid4())
    request_started_at = _current_time()
    analysis_started_at: datetime | None = None
    analysis_completed_at: datetime | None = None
    try:
        temp_path, file_size_bytes = _persist_upload(track)
        _ = dsp_json_override
        run_separation = bool(separate or separate_query or separate_flag)
        run_fast = bool(fast or fast_query)
        estimate = _build_backend_estimate(temp_path, run_separation, transcribe)

        command = ["./venv/bin/python", "analyze.py", temp_path, "--yes"]
        flags_used: list[str] = []
        if run_separation:
            command.append("--separate")
            flags_used.append("--separate")
        if transcribe:
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
            return _build_error_response(
                request_id=request_id,
                status_code=504,
                error_code="ANALYZER_TIMEOUT",
                message="Local DSP analysis timed out before completion.",
                retryable=True,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                request_started_at=request_started_at,
                analysis_started_at=analysis_started_at,
                analysis_completed_at=analysis_completed_at,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
                file_duration_seconds=None,
                stdout=exc.stdout,
                stderr=exc.stderr,
            )
        except Exception as exc:
            analysis_completed_at = _current_time()
            return _build_error_response(
                request_id=request_id,
                status_code=500,
                error_code="BACKEND_INTERNAL_ERROR",
                message="Local DSP backend hit an unexpected server error.",
                retryable=False,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                request_started_at=request_started_at,
                analysis_started_at=analysis_started_at,
                analysis_completed_at=analysis_completed_at,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
                file_duration_seconds=None,
                stderr=exc,
            )
        analysis_completed_at = _current_time()

        if result.returncode != 0:
            return _build_error_response(
                request_id=request_id,
                status_code=502,
                error_code="ANALYZER_FAILED",
                message="Local DSP analysis failed before a valid result was produced.",
                retryable=True,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                request_started_at=request_started_at,
                analysis_started_at=analysis_started_at,
                analysis_completed_at=analysis_completed_at,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
                file_duration_seconds=None,
                stdout=result.stdout,
                stderr=result.stderr,
            )

        stdout = result.stdout.strip()
        if not stdout:
            return _build_error_response(
                request_id=request_id,
                status_code=502,
                error_code="ANALYZER_EMPTY_OUTPUT",
                message="Local DSP analysis completed without returning any JSON.",
                retryable=False,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                request_started_at=request_started_at,
                analysis_started_at=analysis_started_at,
                analysis_completed_at=analysis_completed_at,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
                file_duration_seconds=None,
                stderr=result.stderr,
            )

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return _build_error_response(
                request_id=request_id,
                status_code=502,
                error_code="ANALYZER_INVALID_JSON",
                message="Local DSP analysis returned malformed JSON.",
                retryable=False,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                request_started_at=request_started_at,
                analysis_started_at=analysis_started_at,
                analysis_completed_at=analysis_completed_at,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
                file_duration_seconds=None,
                stdout=stdout,
                stderr=result.stderr,
            )

        if not isinstance(payload, dict):
            return _build_error_response(
                request_id=request_id,
                status_code=502,
                error_code="ANALYZER_BAD_PAYLOAD",
                message="Local DSP analysis returned a JSON payload that did not match the expected contract.",
                retryable=False,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                request_started_at=request_started_at,
                analysis_started_at=analysis_started_at,
                analysis_completed_at=analysis_completed_at,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
                file_duration_seconds=None,
                stdout=stdout,
                stderr=result.stderr,
            )

        # Retain temp file for optional Phase 2 reuse; _pop_cached_temp_file owns cleanup
        _cache_temp_file(request_id, temp_path, now=analysis_completed_at)
        temp_path = None  # prevent finally block from deleting it

        return _build_success_response(
            request_id=request_id,
            payload=payload,
            timeout_seconds=timeout_seconds,
            estimate=estimate,
            request_started_at=request_started_at,
            analysis_started_at=analysis_started_at,
            analysis_completed_at=analysis_completed_at,
            flags_used=flags_used,
            file_size_bytes=file_size_bytes,
        )
    finally:
        await track.close()
        _cleanup_temp_path(temp_path)


@app.post("/api/phase2")
async def analyze_phase2(
    track: UploadFile = File(...),
    phase1_json: str = Form(...),
    model_name: str = Form("gemini-2.5-flash"),
    phase1_request_id: str | None = Form(None),
) -> JSONResponse:
    """Run Gemini Phase 2 advisory reconstruction server-side.

    Accepts the audio file + stringified Phase1Result.
    Returns { requestId, phase2: Phase2Result | null, message, diagnostics }.
    Skip cases (empty/bad JSON/bad shape from Gemini) return 200 with phase2=null.
    Infrastructure failures (timeout, auth, quota) return 4xx/5xx.
    """
    if not _GENAI_AVAILABLE:
        return JSONResponse(
            status_code=500,
            content={
                "requestId": str(uuid4()),
                "error": {
                    "code": "GEMINI_NOT_INSTALLED",
                    "message": "google-genai package is not installed on the backend.",
                    "phase": ERROR_PHASE_GEMINI,
                    "retryable": False,
                },
            },
        )

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return JSONResponse(
            status_code=500,
            content={
                "requestId": str(uuid4()),
                "error": {
                    "code": "GEMINI_NOT_CONFIGURED",
                    "message": "GEMINI_API_KEY is not set on the backend.",
                    "phase": ERROR_PHASE_GEMINI,
                    "retryable": False,
                },
            },
        )

    if model_name not in ALLOWED_GEMINI_MODELS:
        return JSONResponse(
            status_code=400,
            content={
                "requestId": str(uuid4()),
                "error": {
                    "code": "INVALID_MODEL",
                    "message": f"model_name '{model_name}' is not allowed. Must be one of: {sorted(ALLOWED_GEMINI_MODELS)}",
                    "phase": ERROR_PHASE_GEMINI,
                    "retryable": False,
                },
            },
        )

    temp_path: str | None = None
    request_id = str(uuid4())
    request_started_at = _current_time()
    api_started_at: datetime | None = None
    api_completed_at: datetime | None = None
    flags_used: list[str] = []
    file_size_bytes = 0

    try:
        # 1. Persist upload (use cached path from Phase 1 if available)
        cached_path = _pop_cached_temp_file(phase1_request_id)
        if cached_path:
            temp_path = cached_path
            file_size_bytes = os.path.getsize(cached_path)
            filename = track.filename or "upload.bin"
            await track.close()
        else:
            temp_path, file_size_bytes = _persist_upload(track)
            filename = track.filename or "upload.bin"
        mime_type = _get_audio_mime_type(filename)

        # 2. Parse phase1_json — use as-is (already normalized by frontend)
        try:
            phase1_dict = json.loads(phase1_json)
        except json.JSONDecodeError:
            return _build_phase2_error_response(
                request_id=request_id,
                status_code=400,
                error_code="PHASE2_BAD_PHASE1_JSON",
                message="phase1_json field could not be parsed as JSON.",
                retryable=False,
                model_name=model_name,
                request_started_at=request_started_at,
                api_started_at=None,
                api_completed_at=None,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
            )
        if not isinstance(phase1_dict, dict):
            return _build_phase2_error_response(
                request_id=request_id,
                status_code=400,
                error_code="PHASE2_BAD_PHASE1_JSON",
                message="phase1_json must be a JSON object.",
                retryable=False,
                model_name=model_name,
                request_started_at=request_started_at,
                api_started_at=None,
                api_completed_at=None,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
            )

        # 3. Build prompt
        prompt = _build_phase2_prompt(phase1_dict)

        # 4. Create Gemini client
        client = _genai.Client(
            api_key=api_key,
            http_options={"timeout": GEMINI_TIMEOUT_SECONDS * 1_000},
        )
        generate_config = _genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PHASE2_RESPONSE_SCHEMA,
        )

        # 5. Inline or Files API path — threshold matches INLINE_SIZE_LIMIT in TS
        api_started_at = _current_time()
        uploaded_gemini_file = None

        if file_size_bytes <= INLINE_SIZE_LIMIT:
            flags_used.append("inline")
            with open(temp_path, "rb") as f:
                audio_bytes = f.read()
            audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
            media_part = {"inline_data": {"data": audio_b64, "mime_type": mime_type}}

            def _generate_inline() -> Any:
                return client.models.generate_content(
                    model=model_name,
                    contents=[{"parts": [media_part, {"text": prompt}]}],
                    config=generate_config,
                )

            try:
                response = await _gemini_with_retry(_generate_inline)
            except Exception as exc:
                api_completed_at = _current_time()
                error_msg = str(exc)
                status_code = 429 if "429" in error_msg or "quota" in error_msg.lower() else 502
                return _build_phase2_error_response(
                    request_id=request_id,
                    status_code=status_code,
                    error_code="GEMINI_GENERATE_FAILED",
                    message=f"Gemini generation failed: {error_msg[:200]}",
                    retryable=True,
                    model_name=model_name,
                    request_started_at=request_started_at,
                    api_started_at=api_started_at,
                    api_completed_at=_current_time(),
                    flags_used=flags_used,
                    file_size_bytes=file_size_bytes,
                    stderr=error_msg,
                )

            api_completed_at = _current_time()
            message_suffix = "Phase 2 advisory complete."

        else:
            flags_used.append("files-api")

            def _upload_file() -> Any:
                return client.files.upload(
                    file=temp_path,
                    config=_genai_types.UploadFileConfig(
                        mime_type=mime_type,
                        display_name=filename,
                    ),
                )

            try:
                upload_start = _current_time()
                uploaded_gemini_file = await _gemini_with_retry(_upload_file)
                upload_end = _current_time()
            except Exception as exc:
                api_completed_at = _current_time()
                return _build_phase2_error_response(
                    request_id=request_id,
                    status_code=502,
                    error_code="GEMINI_UPLOAD_FAILED",
                    message=f"Gemini file upload failed: {str(exc)[:200]}",
                    retryable=True,
                    model_name=model_name,
                    request_started_at=request_started_at,
                    api_started_at=api_started_at,
                    api_completed_at=_current_time(),
                    flags_used=flags_used,
                    file_size_bytes=file_size_bytes,
                    stderr=str(exc),
                )

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

            try:
                generate_start = _current_time()
                response = await _gemini_with_retry(_generate_files_api)
                generate_end = _current_time()
            except Exception as exc:
                api_completed_at = _current_time()
                error_msg = str(exc)
                status_code = 429 if "429" in error_msg or "quota" in error_msg.lower() else 502
                return _build_phase2_error_response(
                    request_id=request_id,
                    status_code=status_code,
                    error_code="GEMINI_GENERATE_FAILED",
                    message=f"Gemini generation failed: {error_msg[:200]}",
                    retryable=True,
                    model_name=model_name,
                    request_started_at=request_started_at,
                    api_started_at=api_started_at,
                    api_completed_at=_current_time(),
                    flags_used=flags_used,
                    file_size_bytes=file_size_bytes,
                    stderr=error_msg,
                )
            finally:
                # Always delete the uploaded file — mirrors try/finally in TS
                if uploaded_gemini_file:
                    try:
                        await asyncio.to_thread(
                            lambda: client.files.delete(name=uploaded_gemini_file.name)
                        )
                    except Exception:
                        pass  # files auto-expire ~24h; cleanup failures must not fail the analysis

            api_completed_at = _current_time()
            upload_ms = int(_elapsed_ms(upload_start, upload_end))
            generate_ms = int(_elapsed_ms(generate_start, generate_end))
            message_suffix = f"Phase 2 advisory complete. Upload: {upload_ms}ms, Generate: {generate_ms}ms"

        # 6. Parse and validate Gemini response
        response_text: str | None = getattr(response, "text", None)
        phase2_result, skip_message = _parse_phase2_result(response_text)

        if skip_message:
            return _build_phase2_success_response(
                request_id=request_id,
                phase2_result=None,
                message=skip_message,
                model_name=model_name,
                request_started_at=request_started_at,
                api_started_at=api_started_at,
                api_completed_at=api_completed_at,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
            )

        return _build_phase2_success_response(
            request_id=request_id,
            phase2_result=phase2_result,
            message=message_suffix,
            model_name=model_name,
            request_started_at=request_started_at,
            api_started_at=api_started_at,
            api_completed_at=api_completed_at,
            flags_used=flags_used,
            file_size_bytes=file_size_bytes,
        )

    except Exception as exc:
        api_completed_at = api_completed_at or _current_time()
        return _build_phase2_error_response(
            request_id=request_id,
            status_code=500,
            error_code="BACKEND_INTERNAL_ERROR",
            message="Phase 2 backend hit an unexpected server error.",
            retryable=False,
            model_name=model_name,
            request_started_at=request_started_at,
            api_started_at=api_started_at,
            api_completed_at=api_completed_at,
            flags_used=flags_used,
            file_size_bytes=file_size_bytes,
            stderr=str(exc),
        )
    finally:
        await track.close()
        _cleanup_temp_path(temp_path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host=DEFAULT_SERVER_HOST, port=resolve_server_port(), reload=False)

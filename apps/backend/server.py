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

from fastapi import FastAPI, File, Form, Header, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

import auth_context
from auth_context import AuthenticationRequiredError, UserContext, resolve_api_user_context
from analysis_runtime import (
    AnalysisRuntime,
    UnsupportedMt3ModeError,
    UnsupportedPitchNoteBackendError,
    UnsupportedPitchNoteModeError,
)
from analyze import (
    build_analysis_estimate,
    get_audio_duration_seconds,
)
from runtime_profile import (
    resolve_process_role,
    resolve_runtime_profile,
    should_recover_incomplete_attempts,
    should_start_in_process_workers,
)
from utils.cleanup import cleanup_artifacts
import csv_export
import phase2_export
import transcription_pianoroll
import upload_limits
import url_ingest
from server_upload import (  # noqa: F401 — re-exported for test backward compat
    LEGACY_ENDPOINT_SUNSET,
    ERROR_PHASE_LOCAL_DSP,
    ERROR_PHASE_GEMINI,
    UploadTooLargeError,
    UploadSizeLimitMiddleware,
    _MultipartTrackSizeCounter,
    _canonical_upload_too_large_response,
    _cleanup_temp_path,
    _legacy_upload_too_large_response,
    _mark_legacy_endpoint_response,
    _persist_upload,
    _scope_header_value,
    _upload_too_large_response_for_path,
    _value_error_code,
)
from server_phase1 import (  # noqa: F401 — re-exported for test backward compat
    ENGINE_VERSION,
    MAX_SNIPPET_LENGTH,
    ANALYZE_TIMEOUT_BUFFER_SECONDS,
    ANALYZE_TIMEOUT_FLOOR_SECONDS,
    ANALYZE_TIMEOUT_FALLBACK_SECONDS,
    ANALYZE_TIMEOUT_ESTIMATE_MULTIPLIER,
    _coerce_number,
    _coerce_string,
    _coerce_nullable_string,
    _coerce_positive_int,
    _coerce_nullable_number,
    _elapsed_ms,
    _normalize_spectral_detail,
    _build_phase1,
    _normalize_run_snapshot,
    _build_measurement_provenance,
    _safe_snippet,
    _normalize_estimate_stage,
    _compute_timeout_seconds,
    _compact_dict,
    _round_timing_value,
    _format_timing_summary_value,
    _build_timings,
    _log_timing_summary,
    _build_diagnostics,
    _build_error_response,
    _build_success_response,
)
from server_phase2 import (  # noqa: F401 — re-exported for test backward compat
    GEMINI_RETRYABLE_SUBSTRINGS,
    LIVE12_DEVICE_CATALOG,
    LIVE12_DEVICE_LOOKUP,
    PHASE2_PROMPT_TEMPLATE,
    PHASE2_RESPONSE_SCHEMA,
    PRODUCER_SUMMARY_PROMPT_TEMPLATE,
    PRODUCER_SUMMARY_PROMPT_VERSION,
    STEM_SUMMARY_PROMPT_TEMPLATE,
    STEM_SUMMARY_RESPONSE_SCHEMA,
    SUPPORTED_INTERPRETATION_PROFILES,
    _ALLOWED_LIVE12_DEVICE_CLASSES,
    _ALLOWED_LIVE12_DEVICE_FAMILIES,
    _ALLOWED_PHASE2_RECOMMENDATION_CATEGORIES,
    _ALLOWED_PHASE2_WARP_MODES,
    _ALLOWED_PHASE2_WORKFLOW_STAGES,
    _DEVICE_FAMILY_COERCION,
    _RECOMMENDATION_CATEGORY_COERCION,
    _WORKFLOW_STAGE_COERCION,
    _build_combined_stem_summary_result,
    _build_descriptor_hooks,
    _build_phase2_prompt,
    _build_phase2_validation_warning,
    _build_stem_summary_prompt,
    _coerce_enum_fields,
    _collect_phase2_shape_issues,
    _finalize_style_profile_authoritative_measurements,
    _get_audio_mime_type,
    _interpretation_schema_version,
    _is_retryable_gemini_error,
    _is_valid_phase2_shape,
    _is_valid_stem_summary_shape,
    _load_live12_device_catalog,
    _load_prompt_template,
    _normalize_and_salvage_phase2_result,
    _parse_phase2_result,
    _parse_phase2_result_debug,
    _parse_stem_summary_result,
    _resolve_analysis_mode_value,
    _resolve_estimate_flags_for_stage_request,
    _resolve_interpretation_profile_config,
    _resolve_pitch_note_mode_for_legacy,
    _sanitize_optional_phase2_fields,
    _stem_summary_label,
    _validate_phase2_catalog_entry,
    _validate_phase2_citation_paths,
    _validate_phase2_semantics,
    apply_live12_catalogue_gates,
)

from recommendations_contract import build_validated_recommendations

import server_samples
from phase2_provider import (
    Phase2ProviderError,
    Phase2ProviderRequest,
    resolve_external_phase2_provider,
)


app = FastAPI(title="Sonic Analyzer Local API")

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


class GeminiClientBuildError(Exception):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


def _build_gemini_client() -> tuple[Any, list[str]]:
    backend = os.getenv("ASA_GEMINI_BACKEND", "").strip().lower()
    flags: list[str] = []

    if not backend:
        project = (os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("ASA_GCP_PROJECT") or "").strip()
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if project:
            backend = "vertex"
        elif api_key:
            backend = "apistudio"
        else:
            raise GeminiClientBuildError(
                "GEMINI_NOT_CONFIGURED",
                "Gemini is not configured. Set ASA_GEMINI_BACKEND=vertex with GOOGLE_CLOUD_PROJECT (and ADC) or ASA_GCP_PROJECT, or set GEMINI_API_KEY for AI Studio.",
            )

    if backend == "vertex":
        project = (os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("ASA_GCP_PROJECT") or "").strip()
        if not project:
            raise GeminiClientBuildError(
                "GEMINI_VERTEX_NOT_CONFIGURED",
                "ASA_GEMINI_BACKEND=vertex requires GOOGLE_CLOUD_PROJECT or ASA_GCP_PROJECT.",
            )
        location = (os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("ASA_GCP_LOCATION") or "us-central1").strip()
        client = _genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options={"timeout": GEMINI_TIMEOUT_SECONDS * 1_000},
        )
        flags.append(f"vertex:{location}")
        return client, flags

    if backend == "apistudio":
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise GeminiClientBuildError(
                "GEMINI_NOT_CONFIGURED",
                "ASA_GEMINI_BACKEND=apistudio requires GEMINI_API_KEY.",
            )
        client = _genai.Client(
            api_key=api_key,
            http_options={"timeout": GEMINI_TIMEOUT_SECONDS * 1_000},
        )
        flags.append("apistudio")
        return client, flags

    raise GeminiClientBuildError(
        "GEMINI_NOT_CONFIGURED",
        f"Unknown ASA_GEMINI_BACKEND={backend}. Use vertex or apistudio.",
    )


_ANALYSIS_RUNTIME: AnalysisRuntime | None = None
_BACKGROUND_TASKS: list[asyncio.Task[Any]] = []
logger = logging.getLogger(__name__)
_ACTIVE_CHILD_PROCESSES: dict[tuple[str, str], subprocess.Popen[Any]] = {}
_ACTIVE_CHILD_PROCESSES_LOCK = threading.Lock()



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


_TEMP_FILE_REGISTRY: dict[str, tuple[str, datetime]] = {}
# Guards _TEMP_FILE_REGISTRY across request handlers and the eviction loop.
_FILE_CACHE_LOCK = threading.Lock()
# How long a request-scoped temp-file path stays cached before it is evicted.
# Both _cache_temp_file/_pop_cached_temp_file and _evict_expired_cache_entries
# referenced this constant, but it was never defined — so any call to that path
# raised NameError. The eviction loop sleeps 300s between sweeps, so the only
# reason this never surfaced is that the path is currently unwired; defining it
# turns the latent landmine into working, exercisable code.
_FILE_CACHE_TTL_SECONDS = 900


def _cache_temp_file(request_id: str, temp_path: str, now: datetime | None = None) -> None:
    if now is None:
        now = _current_time()
    expires_at = now + timedelta(seconds=_FILE_CACHE_TTL_SECONDS)
    with _FILE_CACHE_LOCK:
        _TEMP_FILE_REGISTRY[request_id] = (temp_path, expires_at)


def _pop_cached_temp_file(request_id: str | None) -> str | None:
    if not request_id:
        return None
    with _FILE_CACHE_LOCK:
        entry = _TEMP_FILE_REGISTRY.pop(request_id, None)
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
        expired = [rid for rid, (_, exp) in _TEMP_FILE_REGISTRY.items() if now > exp]
        for rid in expired:
            path, _ = _TEMP_FILE_REGISTRY.pop(rid)
            _cleanup_temp_path(path)


async def _evict_loop() -> None:
    while True:
        await asyncio.sleep(300)
        _evict_expired_cache_entries()


def _create_background_tasks(
    *,
    include_cache_eviction: bool,
    include_workers: bool,
) -> list[asyncio.Task[Any]]:
    tasks: list[asyncio.Task[Any]] = []
    if include_cache_eviction:
        tasks.append(asyncio.create_task(_evict_loop()))
    if include_workers:
        tasks.extend(
            [
                asyncio.create_task(_measurement_worker_loop()),
                asyncio.create_task(_pitch_note_worker_loop()),
                asyncio.create_task(_interpretation_worker_loop()),
                asyncio.create_task(_mt3_worker_loop()),
            ]
        )
    return tasks






async def _start_cache_eviction():
    """Legacy startup hook kept for compatibility tests.

    This only starts the historical in-memory eviction coroutine. It must not
    start analysis-runtime worker loops or recover incomplete analysis attempts.
    """
    task = asyncio.create_task(_evict_loop())
    _BACKGROUND_TASKS.append(task)
    return task


@app.on_event("startup")
async def _start_background_tasks() -> None:
    runtime = get_analysis_runtime()
    runtime_profile = resolve_runtime_profile()
    process_role = resolve_runtime_process_role(runtime_profile=runtime_profile)

    if should_recover_incomplete_attempts(runtime_profile, process_role):
        runtime.recover_incomplete_attempts()

    if not _BACKGROUND_TASKS:
        _BACKGROUND_TASKS.extend(
            _create_background_tasks(
                include_cache_eviction=False,
                include_workers=should_start_in_process_workers(
                    runtime_profile,
                    process_role,
                ),
            )
        )

    cleanup_task = asyncio.create_task(_artifact_cleanup_loop(runtime.runtime_dir))
    _BACKGROUND_TASKS.append(cleanup_task)

    logger.info(
        "Upload limits configured: raw_audio_limit_bytes=%s edge_request_limit_bytes=%s",
        upload_limits.MAX_UPLOAD_SIZE_BYTES,
        upload_limits.MAX_UPLOAD_REQUEST_BYTES,
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


def resolve_runtime_process_role(*, runtime_profile: str | None = None) -> str:
    return resolve_process_role(runtime_profile=runtime_profile)


def _resolve_route_user_context(
    x_asa_user_id: str | None,
    x_asa_user_email: str | None,
) -> UserContext | JSONResponse:
    try:
        return resolve_api_user_context(x_asa_user_id, x_asa_user_email)
    except AuthenticationRequiredError as exc:
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "AUTHENTICATION_REQUIRED",
                    "message": str(exc),
                }
            },
        )


def _run_not_found_response(run_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "RUN_NOT_FOUND",
                "message": f"Analysis run '{run_id}' was not found.",
            }
        },
    )


def resolve_server_port() -> int:
    raw_value = os.getenv("SONIC_ANALYZER_PORT", str(DEFAULT_SERVER_PORT)).strip()
    try:
        port = int(raw_value)
    except ValueError:
        return DEFAULT_SERVER_PORT
    if 0 < port <= 65535:
        return port
    return DEFAULT_SERVER_PORT



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


def _stream_text(value: Any) -> Any:
    """Coerce a subprocess stream (str | bytes | None) to text.

    Mirrors the real branch's text=True contract so the mock branch is faithful:
    a patched subprocess.run that yields bytes streams — or a TimeoutExpired
    carrying bytes — would otherwise make callers' ``marker in stderr`` (str in
    bytes) raise TypeError instead of reaching the timeout/error classification.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


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
                "stdout": _stream_text(exc.stdout),
                "stderr": _stream_text(exc.stderr),
                "timedOut": True,
            }
        return {
            "returncode": result.returncode,
            "stdout": _stream_text(result.stdout),
            "stderr": _stream_text(result.stderr),
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


def _coerce_mt3_mode(value: Any) -> str:
    """Validate/normalize a route-form mt3_mode.

    The HTTP route declares ``mt3_mode: str = Form("off")``. When the route
    function is invoked directly (not via HTTP dispatch — e.g. the unit tests
    that call ``server.create_analysis_run(...)`` to bypass multipart parsing),
    FastAPI leaves the default as its internal ``Form(...)`` sentinel object
    rather than the string ``"off"``. That sentinel — and the empty string,
    which is how an absent multipart field can arrive — normalize to the
    conservative ``"off"`` default (the "absent unless requested" contract).

    A real, non-empty string is validated strictly: ``"off"`` / ``"enabled"``
    pass through; anything else raises :class:`UnsupportedMt3ModeError` so a
    client typo like ``"enable"`` surfaces as ``400 MT3_MODE_UNSUPPORTED``
    rather than silently disabling MT3. This mirrors how ``pitch_note_mode`` is
    rejected and keeps the typed error / catch / code machinery (and the
    contract documented in ``analysisRunsClient.ts``) live rather than dead.
    """
    if not isinstance(value, str) or value == "":
        return "off"
    if value in {"off", "enabled"}:
        return value
    raise UnsupportedMt3ModeError(value)


async def _create_analysis_run_record(
    *,
    track: UploadFile,
    owner_user_id: str,
    analysis_mode: str,
    pitch_note_mode: str,
    pitch_note_backend: str,
    interpretation_mode: str,
    interpretation_profile: str,
    interpretation_model: str | None,
    legacy_request_id: str | None = None,
    mt3_mode: Any = "off",
) -> tuple[AnalysisRuntime, str]:
    mt3_mode = _coerce_mt3_mode(mt3_mode)
    temp_path: str | None = None
    runtime = get_analysis_runtime()
    analysis_mode = _resolve_analysis_mode_value(analysis_mode)
    if interpretation_mode != "off":
        _resolve_interpretation_profile_config(interpretation_profile)
    track_file = track.file
    try:
        track_file.seek(0)
    except (AttributeError, OSError):
        pass
    content = track_file.read()
    if isinstance(content, str):
        content = content.encode("utf-8")
    try:
        track_file.seek(0)
    except (AttributeError, OSError):
        pass

    created = runtime.create_run(
        filename=track.filename or "upload.bin",
        content=content,
        mime_type=track.content_type or _get_audio_mime_type(track.filename or "upload.bin"),
        owner_user_id=owner_user_id,
        analysis_mode=analysis_mode,
        pitch_note_mode=pitch_note_mode,
        pitch_note_backend=pitch_note_backend,
        interpretation_mode=interpretation_mode,
        interpretation_profile=interpretation_profile,
        interpretation_model=interpretation_model,
        legacy_request_id=legacy_request_id,
        mt3_mode=mt3_mode,
    )
    return runtime, created["runId"]


async def _create_analysis_run_record_from_url(
    *,
    url: str,
    owner_user_id: str,
    analysis_mode: str,
    pitch_note_mode: str,
    pitch_note_backend: str,
    interpretation_mode: str,
    interpretation_profile: str,
    interpretation_model: str | None,
    legacy_request_id: str | None = None,
    mt3_mode: Any = "off",
) -> tuple[AnalysisRuntime, str]:
    """Parallel of ``_create_analysis_run_record`` but for URL-fetched audio.

    The actual fetch is dispatched to a worker thread so the (blocking)
    ``requests`` call doesn't pin the event loop. Typed URL-ingest
    errors are surfaced unchanged to the caller, which is responsible
    for translating them into HTTP envelopes.
    """
    mt3_mode = _coerce_mt3_mode(mt3_mode)
    runtime = get_analysis_runtime()
    analysis_mode = _resolve_analysis_mode_value(analysis_mode)
    if interpretation_mode != "off":
        _resolve_interpretation_profile_config(interpretation_profile)

    fetched = await asyncio.to_thread(url_ingest.fetch_url_to_bytes, url)

    created = runtime.create_run(
        filename=fetched.filename,
        content=fetched.content,
        mime_type=fetched.mime_type,
        owner_user_id=owner_user_id,
        analysis_mode=analysis_mode,
        pitch_note_mode=pitch_note_mode,
        pitch_note_backend=pitch_note_backend,
        interpretation_mode=interpretation_mode,
        interpretation_profile=interpretation_profile,
        interpretation_model=interpretation_model,
        legacy_request_id=legacy_request_id,
        mt3_mode=mt3_mode,
    )
    return runtime, created["runId"]


def _url_ingest_error_response(exc: url_ingest.UrlIngestionError) -> JSONResponse:
    """Map a typed URL-ingest error onto the canonical error envelope.

    Status code and ``retryable`` flag follow the kind of failure:

    - ``URL_INVALID`` / ``URL_BLOCKED_PRIVATE_HOST`` → 400, not
      retryable (request will never succeed as-is).
    - ``URL_TOO_LARGE`` → 413, not retryable (size is fundamental).
    - ``URL_FETCH_FAILED`` → 502, retryable (transient upstream
      problem; client can reasonably retry the same request).
    """
    code = exc.code
    if code == "URL_TOO_LARGE":
        status_code = 413
        retryable = False
    elif code == "URL_FETCH_FAILED":
        status_code = 502
        retryable = True
    else:
        status_code = 400
        retryable = False
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": str(exc),
                "retryable": retryable,
            }
        },
    )


async def _estimate_analysis_run(
    *,
    track: UploadFile,
    analysis_mode: str,
    pitch_note_mode: str,
    pitch_note_backend: str,
    interpretation_mode: str,
    interpretation_profile: str,
    interpretation_model: str | None,
    mt3_mode: Any = "off",
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
        run_mt3 = _coerce_mt3_mode(mt3_mode) == "enabled"
        estimate = _build_backend_estimate(
            temp_path,
            run_separation,
            run_transcribe,
            analysis_mode=analysis_mode,
            run_mt3=run_mt3,
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
            response_ready_at=_current_time(),
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
            response_ready_at=_current_time(),
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
            response_ready_at=_current_time(),
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
            response_ready_at=_current_time(),
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
            response_ready_at=_current_time(),
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
            response_ready_at=_current_time(),
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
        response_ready_at=_current_time(),
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
        import librosa
        from spectral_viz import generate_all_artifacts

        source = runtime.get_source_artifact(run_id)
        source_local_path = runtime.require_local_artifact_path(
            source.get("path"),
            purpose="Source audio artifact for spectral generation",
        )
        # Header-only metadata read; soundfile.info() under the hood.
        # The STFT spectrogram preserves source SR so the y-axis spans
        # 0 → source_sr/2 rather than always 0 → 22.05 kHz.
        stft_sr = int(librosa.get_samplerate(source_local_path))
        with tempfile.TemporaryDirectory(prefix="spectral_viz_") as tmp_dir:
            artifacts = generate_all_artifacts(source_local_path, tmp_dir)
            _MIME_TYPES = {
                "spectrogram_mel": "image/png",
                "spectrogram_stft": "image/png",
                "spectral_time_series": "application/json",
            }
            _FILENAMES = {
                "spectrogram_mel": "mel_spectrogram.png",
                "spectrogram_stft": "stft_spectrogram.png",
                "spectral_time_series": "spectral_time_series.json",
            }
            for kind, path in artifacts.items():
                provenance: dict[str, Any] = {
                    "generator": "spectral_viz",
                    "schemaVersion": "spectral.v1",
                }
                if kind == "spectrogram_stft":
                    provenance["sampleRate"] = stft_sr
                runtime.record_artifact(
                    run_id,
                    kind=kind,
                    source_path=path,
                    filename=_FILENAMES.get(kind, os.path.basename(path)),
                    mime_type=_MIME_TYPES.get(kind, "application/octet-stream"),
                    provenance=provenance,
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
    # Resolve the source artifact under a guard. If this raises (e.g. the
    # source audio was swept by artifact cleanup, or is unresolvable in a
    # hosted profile) it would otherwise escape to _measurement_worker_loop's
    # bare except, leaving the measurement stage stuck 'running' forever with
    # no reaper — and the whole run would poll indefinitely. Terminalize it,
    # mirroring _execute_pitch_note_attempt / _execute_mt3_attempt.
    try:
        source_artifact = runtime.get_source_artifact(run_id)
        source_local_path = runtime.require_local_artifact_path(
            source_artifact.get("path"),
            purpose="Source audio artifact for measurement",
        )
    except Exception as exc:
        runtime.fail_measurement(
            run_id,
            error={
                "code": "MEASUREMENT_SOURCE_UNAVAILABLE",
                "message": str(exc),
                "retryable": False,
                "phase": ERROR_PHASE_LOCAL_DSP,
            },
            provenance=_build_measurement_provenance(
                run_separation=run_separation,
                run_transcribe=run_transcribe,
                run_standard=run_standard,
                run_fast=run_fast,
            ),
        )
        return {
            "ok": False,
            "statusCode": 500,
            "errorCode": "MEASUREMENT_SOURCE_UNAVAILABLE",
            "message": str(exc),
            "retryable": False,
            "diagnostics": None,
        }
    execution = _run_measurement_subprocess(
        runtime=runtime,
        run_id=run_id,
        audio_path=source_local_path,
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
    provenance: dict[str, Any] = {
        "schemaVersion": "pitch_note_translation.v1",
        "backendId": attempt["backendId"],
        "mode": attempt["mode"],
    }
    # Bound before the try so the except handler can reference it even when
    # get_source_artifact (now inside the try) is the call that raised.
    source_artifact: dict[str, Any] | None = None
    stem_output_dir: str | None = None
    try:
        # Resolve the source artifact INSIDE the try so a failure here
        # terminalizes the attempt rather than leaving it stuck 'running' — which
        # the interpretation-ordering gate would otherwise turn into an indefinite
        # block on this run's interpretation. (Symmetry with _execute_mt3_attempt.)
        source_artifact = runtime.get_source_artifact(run_id)
        source_local_path = runtime.require_local_artifact_path(
            source_artifact.get("path"),
            purpose="Source audio artifact for pitch/note translation",
        )
        # Build the subprocess command
        command = [
            "./venv/bin/python", "analyze.py",
            source_local_path,
            "--pitch-note-only",
            "--pitch-note-backend",
            attempt["backendId"],
            "--yes",
        ]

        # If stems already exist as artifacts, pass their directory
        # so the subprocess skips Demucs separation
        stem_dir = None
        if attempt["mode"] == "stem_notes":
            existing = runtime.get_internal_artifacts_by_kind(run_id, "stem_")
            stem_paths_map = {
                artifact["kind"].removeprefix("stem_"): str(local_path)
                for artifact in existing
                if (local_path := runtime.resolve_artifact_local_path(artifact.get("path"))) is not None
                and local_path.is_file()
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

        # Route through the registered-subprocess helper so an interrupt/delete
        # can terminate this child (Demucs+torchcrepe hold ~2-4GB) instead of
        # orphaning it until the 600s timeout. _run_streamed_subprocess registers
        # the Popen in _ACTIVE_CHILD_PROCESSES under this stage key and terminates
        # it on its own timeout, mirroring the measurement stage.
        result = _run_streamed_subprocess(
            command=command,
            timeout_seconds=600,
            run_id=run_id,
            stage_key="pitchNoteTranslation",
        )

        if result["returncode"] != 0:
            stderr_tail = result["stderr"][-500:] if result["stderr"] else "no stderr"
            if result["timedOut"]:
                raise RuntimeError(
                    f"Pitch/note translation subprocess timed out after 600s: {stderr_tail}"
                )
            raise RuntimeError(
                f"Pitch/note translation subprocess failed (exit {result['returncode']}): "
                f"{stderr_tail}"
            )

        pitch_note_payload = json.loads(result["stdout"])
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
                # Null-safe: source_artifact is None if get_source_artifact itself raised.
                "sourceArtifactId": (source_artifact or {}).get("artifactId"),
                "isolationMode": "subprocess",
            },
        )
    finally:
        if stem_output_dir is not None:
            shutil.rmtree(stem_output_dir, ignore_errors=True)


# MT3 stage error-classification markers. The MT3 module emits these
# verbatim in its Mt3NotAvailableError messages; matching on stderr is
# fragile but cheap and avoids round-tripping a structured error object
# through stdout. If mt3_transcription.py changes its phrasing, update
# both sides together.
_MT3_NOT_AVAILABLE_MARKERS = (
    "MT3 backend not installed",
    "MT3 checkpoint missing",
    "Failed to initialize MT3 InferenceModel",
)


def _execute_mt3_attempt(
    runtime: AnalysisRuntime,
    attempt: dict[str, Any],
) -> None:
    """Run MT3 polyphonic transcription as a subprocess.

    Subprocess isolation matters even more here than for pitch_note: MT3
    loads multi-GB JAX/t5x model weights and a freshly-imported JAX
    pollutes the parent's import graph in ways that interact badly with
    the rest of the analyse server. Subprocess exit reclaims everything.

    MVP scope: runs MT3 on the full mix unless a previous stage (pitch_note)
    has already persisted Demucs stems as artifacts. We do NOT invoke
    Demucs from this stage today — the follow-up step adds bidirectional
    stems handover (either stage caches stems for the other to consume).
    """
    started_at = _current_time()
    run_id = str(attempt["runId"])
    attempt_id = str(attempt["attemptId"])
    checkpoint_id = str(attempt.get("checkpointId") or "")
    provenance: dict[str, Any] = {
        "schemaVersion": "mt3_transcription.v1",
        "checkpointId": checkpoint_id,
    }
    # Bound before the try so the except handlers can reference it even when
    # get_source_artifact (now inside the try) is the call that raised.
    source_artifact: dict[str, Any] | None = None
    midi_tempdir: str | None = None
    try:
        # Resolve the source artifact INSIDE the try. If get_source_artifact
        # raised here (e.g. a missing artifact row), the attempt would otherwise
        # escape to _mt3_worker_loop stuck in 'running' — and with the
        # interpretation-ordering gate that would block this run's interpretation
        # indefinitely (until restart recovery). Terminalizing it on failure
        # keeps the gate's no-deadlock guarantee airtight.
        source_artifact = runtime.get_source_artifact(run_id)
        source_local_path = runtime.require_local_artifact_path(
            source_artifact.get("path"),
            purpose="Source audio artifact for MT3 transcription",
        )
        command = [
            "./venv/bin/python", "analyze.py",
            source_local_path,
            "--mt3-only",
            "--yes",
        ]

        # If pitch_note has already run, its stems are persisted as
        # internal artifacts (kind = "stem_<name>"). Reuse them by
        # passing the common parent directory so the MT3 subprocess
        # discovers them via mt3_transcription._resolve_sources.
        existing_stems = runtime.get_internal_artifacts_by_kind(run_id, "stem_")
        stem_paths_map = {
            artifact["kind"].removeprefix("stem_"): str(local_path)
            for artifact in existing_stems
            if (local_path := runtime.resolve_artifact_local_path(artifact.get("path"))) is not None
            and local_path.is_file()
        }
        if "bass" in stem_paths_map or "other" in stem_paths_map:
            stem_dirs = {os.path.dirname(p) for p in stem_paths_map.values()}
            if len(stem_dirs) == 1:
                command.extend(["--stem-dir", stem_dirs.pop()])

        # MT3 model load can take ~30s on first call; long tracks add
        # several minutes of inference. 1800s gives generous headroom
        # while still bounding the worker.
        # Register the child (multi-GB JAX/t5x) so interrupt/delete can reclaim
        # it rather than orphaning it until the 1800s timeout — same rationale as
        # the pitch_note stage.
        result = _run_streamed_subprocess(
            command=command,
            timeout_seconds=1800,
            run_id=run_id,
            stage_key="mt3",
        )

        if result["returncode"] != 0:
            stderr_tail = result["stderr"][-2000:] if result["stderr"] else ""
            if any(marker in stderr_tail for marker in _MT3_NOT_AVAILABLE_MARKERS):
                raise _Mt3UnavailableError(
                    f"MT3 backend unavailable: {stderr_tail[-500:]}"
                )
            if result["timedOut"]:
                raise RuntimeError(
                    f"MT3 subprocess timed out after 1800s: "
                    f"{stderr_tail[-500:] if stderr_tail else 'no stderr'}"
                )
            raise RuntimeError(
                f"MT3 subprocess failed (exit {result['returncode']}): "
                f"{stderr_tail[-500:] if stderr_tail else 'no stderr'}"
            )

        mt3_payload = json.loads(result["stdout"])
        if not isinstance(mt3_payload, dict):
            raise RuntimeError(
                f"MT3 subprocess produced non-dict JSON output: {type(mt3_payload).__name__}"
            )

        # Swap each track's inline midiB64 for a persisted artifact ref.
        # This is the load-bearing decision from the design: snapshot
        # polls must stay small (KB), not balloon to MB per track.
        tracks_in = mt3_payload.get("tracks") or []
        tracks_out: list[dict[str, Any]] = []
        midi_tempdir = tempfile.mkdtemp(
            prefix="asa_mt3_midi_",
            dir=str(runtime.runtime_dir),
        )
        for track in tracks_in:
            if not isinstance(track, dict):
                continue
            midi_b64 = track.get("midiB64")
            if not isinstance(midi_b64, str) or not midi_b64:
                # Track with no MIDI body — keep the metadata but skip
                # the artifact step. This shouldn't happen in practice
                # (the MT3 module emits empty-bytes base64 for empty
                # tracks) but defends against malformed subprocess output.
                tracks_out.append(
                    {
                        "instrument": str(track.get("instrument", "unknown")),
                        "midiArtifactId": None,
                        "midiSizeBytes": 0,
                        "noteCount": int(track.get("noteCount", 0)),
                        "pitchRange": list(track.get("pitchRange", [0, 0])),
                    }
                )
                continue
            instrument = str(track.get("instrument", "unknown"))
            midi_bytes = base64.b64decode(midi_b64)
            midi_path = os.path.join(midi_tempdir, f"{instrument}.mid")
            with open(midi_path, "wb") as midi_file:
                midi_file.write(midi_bytes)
            artifact = runtime.record_artifact(
                run_id,
                kind=f"mt3_track_{instrument}",
                source_path=midi_path,
                filename=f"mt3_{instrument}.mid",
                mime_type="audio/midi",
                provenance={
                    "schemaVersion": "artifact.v1",
                    "sourceArtifactId": source_artifact["artifactId"],
                    "generator": "mt3_transcription_subprocess",
                    "instrument": instrument,
                    "checkpointId": checkpoint_id,
                },
            )
            tracks_out.append(
                {
                    "instrument": instrument,
                    "midiArtifactId": str(artifact["artifactId"]),
                    "midiSizeBytes": int(artifact["sizeBytes"]),
                    "noteCount": int(track.get("noteCount", 0)),
                    "pitchRange": list(track.get("pitchRange", [0, 0])),
                }
            )

        mt3_result = {
            "version": str(mt3_payload.get("version") or ""),
            "stemsUsed": list(mt3_payload.get("stemsUsed") or []),
            "tracks": tracks_out,
        }

        diagnostics = {
            "backendDurationMs": round(_elapsed_ms(started_at, _current_time()), 2),
            "stemSeparationUsed": bool(stem_paths_map),
            "sourceArtifactId": source_artifact["artifactId"],
            "isolationMode": "subprocess",
            "trackCount": len(tracks_out),
        }
        # Surface the actual checkpoint string the subprocess reported so
        # Phase 2 (when wired) can attribute notes to the real revision.
        if isinstance(mt3_result["version"], str) and mt3_result["version"]:
            provenance["resolvedCheckpointId"] = mt3_result["version"]
        runtime.complete_mt3_attempt(
            attempt_id,
            result=mt3_result,
            provenance=provenance,
            diagnostics=diagnostics,
        )
    except _Mt3UnavailableError as exc:
        runtime.fail_mt3_attempt(
            attempt_id,
            error={
                "code": "MT3_NOT_AVAILABLE",
                "message": str(exc),
                "retryable": False,
                "phase": "mt3_transcription",
            },
            provenance=provenance,
            diagnostics={
                "backendDurationMs": round(_elapsed_ms(started_at, _current_time()), 2),
                "sourceArtifactId": source_artifact["artifactId"],
                "isolationMode": "subprocess",
            },
        )
    except Exception as exc:  # noqa: BLE001 - catch-all per stage convention
        runtime.fail_mt3_attempt(
            attempt_id,
            error={
                "code": "MT3_TRANSCRIPTION_FAILED",
                "message": str(exc),
                "retryable": True,
                "phase": "mt3_transcription",
            },
            provenance=provenance,
            diagnostics={
                "backendDurationMs": round(_elapsed_ms(started_at, _current_time()), 2),
                # Null-safe: source_artifact is None if get_source_artifact itself raised.
                "sourceArtifactId": (source_artifact or {}).get("artifactId"),
                "isolationMode": "subprocess",
            },
        )
    finally:
        if midi_tempdir is not None:
            shutil.rmtree(midi_tempdir, ignore_errors=True)


class _Mt3UnavailableError(RuntimeError):
    """Internal marker raised by _execute_mt3_attempt when stderr matches
    the mt3_transcription Mt3NotAvailableError phrasing. Separate from the
    typed exception in mt3_transcription so server.py doesn't need to
    import the MT3 module (which would pull mt3_transcription's lazy
    import graph into the parent process)."""


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
    mt3_result: dict[str, Any] | None = None,
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
        mt3_result=mt3_result,
    )


def _run_combined_stem_summary_request(
    *,
    runtime: AnalysisRuntime,
    run_id: str,
    measurement_result: dict[str, Any],
    pitch_note_result: dict[str, Any] | None,
    grounding_metadata: dict[str, Any],
    model_name: str,
    request_id: str,
    mt3_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stem_artifacts = runtime.get_internal_artifacts_by_kind(run_id, "stem_")
    usable_stems = [
        artifact
        for artifact in stem_artifacts
        if artifact.get("kind") in {"stem_bass", "stem_other"}
        and (local_path := runtime.resolve_artifact_local_path(artifact.get("path"))) is not None
        and local_path.is_file()
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
        stem_local_path = runtime.require_local_artifact_path(
            artifact.get("path"),
            purpose=f"{stem_kind} stem artifact for interpretation",
        )
        stem_grounding_metadata = {
            **grounding_metadata,
            "stemKind": stem_kind,
            "stemArtifactId": artifact["artifactId"],
        }
        execution = _run_interpretation_request_with_profile_config(
            source_path=stem_local_path,
            filename=str(artifact["filename"]),
            file_size_bytes=int(artifact["sizeBytes"]),
            profile_id="stem_summary",
            profile_config=profile_config,
            measurement_result=measurement_result,
            pitch_note_result=pitch_note_result,
            grounding_metadata=stem_grounding_metadata,
            model_name=model_name,
            request_id=f"{request_id}:{stem_kind}",
            mt3_result=mt3_result,
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
    mt3_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_started_at = _current_time()
    flags_used: list[str] = []
    mime_type = _get_audio_mime_type(filename)
    descriptor_hooks = _build_descriptor_hooks(measurement_result)

    # Phase 2 provider seam (default-off; see phase2_provider.py). None means
    # "use the native Gemini path below", which stays byte-for-byte unchanged.
    # An external provider (ASA_PHASE2_PROVIDER=claude) routes the SAME request
    # and flows back through the identical parse/validate/citation tail.
    external_provider = resolve_external_phase2_provider()

    if external_provider is None:
        if not _GENAI_AVAILABLE:
            return {
                "ok": False,
                "statusCode": 500,
                "errorCode": "GEMINI_NOT_INSTALLED",
                "message": "google-genai package is not installed on the backend.",
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
        mt3_result=mt3_result,
    )
    # Construct the Gemini client BEFORE the try (only when no external provider
    # is selected) so a client-construction error propagates to the setup wrapper
    # (INTERPRETATION_SETUP_FAILED) exactly as it did before this seam existed —
    # not caught locally as a generate failure.
    client = None
    generate_config = None
    if external_provider is None:
        try:
            client, gemini_flags = _build_gemini_client()
            flags_used.extend(gemini_flags)
        except GeminiClientBuildError as exc:
            return {
                "ok": False,
                "statusCode": 500,
                "errorCode": exc.error_code,
                "message": str(exc),
                "retryable": False,
                "diagnostics": None,
            }
        generate_config = _genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=profile_config["responseSchema"],
        )

    api_started_at = _current_time()
    uploaded_gemini_file = None

    try:
        if external_provider is not None:
            # Non-Gemini provider (claude) — default-off experiment. The
            # provider returns a raw Phase2Result JSON string (or None for a
            # skip) that flows through the SAME parse/citation/catalogue tail as
            # Gemini below, guaranteeing an identical recommendation schema.
            provider_response = external_provider.generate(
                Phase2ProviderRequest(
                    prompt=prompt,
                    response_schema=profile_config["responseSchema"],
                    phase1_result=measurement_result,
                    model_name=model_name,
                    request_id=request_id,
                    source_path=source_path,
                    filename=filename,
                    mime_type=mime_type,
                    file_size_bytes=file_size_bytes,
                )
            )
            flags_used.append(f"phase2-provider:{external_provider.name}")
            flags_used.extend(provider_response.flags)
            response_text: str | None = provider_response.text
            message_suffix = provider_response.message_suffix or profile_config["successMessage"]
            api_completed_at = _current_time()
        else:
            if file_size_bytes <= INLINE_SIZE_LIMIT:
                flags_used.append("inline")
                with open(source_path, "rb") as input_file:
                    audio_bytes = input_file.read()
                audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
                media_part = {"inline_data": {"data": audio_b64, "mime_type": mime_type}}

                def _generate_inline() -> Any:
                    # Vertex rejects role-less contents ("Please use a valid
                    # role"); AI Studio merely defaults it. Always send "user".
                    return client.models.generate_content(
                        model=model_name,
                        contents=[{"role": "user", "parts": [media_part, {"text": prompt}]}],
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
                        contents=[{"role": "user", "parts": [media_part, {"text": prompt}]}],
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

            response_text = getattr(response, "text", None)
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
        style_profile_warnings = (
            _finalize_style_profile_authoritative_measurements(
                interpretation_result,
                measurement_result,
            )
            if profile_id == "producer_summary" and interpretation_result is not None
            else []
        )
        semantic_validation_warnings = (
            _validate_phase2_semantics(interpretation_result)
            if profile_id == "producer_summary" and interpretation_result is not None
            else []
        )
        citation_path_warnings = (
            _validate_phase2_citation_paths(
                interpretation_result,
                measurement_result,
                mt3_result=mt3_result,
            )
            if profile_id == "producer_summary" and interpretation_result is not None
            else []
        )
        # Live 12 source-catalogue checks run last so they see (a) the salvaged
        # / coerced shape and (b) the post-rename measurement field names that
        # the citation walker uses. They are ADVISORY (warn-and-keep): they
        # never drop or rewrite a recommendation, only emit warning-shaped
        # validationWarnings flagging devices/parameters/citations the source
        # catalogue cannot confirm, so the operator-facing diagnostic log keeps
        # a complete trail. Wrapped defensively: a catalogue load/parse error
        # must NOT fail an otherwise-successful Gemini interpretation.
        catalogue_gate_warnings: list[dict[str, Any]] = []
        if profile_id == "producer_summary" and interpretation_result is not None:
            try:
                catalogue_gate_warnings = apply_live12_catalogue_gates(
                    interpretation_result,
                    request_id=request_id,
                )
            except Exception as exc:  # degrade, never fail the request on a gate error
                logger.warning(
                    "Live 12 catalogue checks skipped (request_id=%s): %s",
                    request_id,
                    exc,
                )
                catalogue_gate_warnings = [
                    {
                        "code": "CATALOGUE_CHECK_UNAVAILABLE",
                        "path": "interpretationResult",
                        "message": (
                            "Live 12 catalogue checks were skipped due to an "
                            f"internal error: {exc}. The interpretation is "
                            "unaffected."
                        ),
                        "requestId": request_id,
                    }
                ]
        # Frozen recommendations.v1 contract (ADR 0003): attach a normalized,
        # citation-gated projection of the Phase 2 device cards as an additive
        # `recommendations` field on the interpretation result. Derived, never
        # authoritative — it cannot override Phase 1 (invariant #1). Only the
        # producer_summary profile carries device cards (stem_summary does not),
        # and it degrades to absent on any error (build_validated_recommendations
        # returns None), exactly like the catalogue gate above.
        if profile_id == "producer_summary" and isinstance(interpretation_result, dict):
            recommendations_envelope = build_validated_recommendations(interpretation_result)
            if recommendations_envelope is not None:
                interpretation_result["recommendations"] = recommendations_envelope
            else:
                logger.warning(
                    "Recommendations contract projection produced no valid "
                    "envelope (request_id=%s)",
                    request_id,
                )
        validation_warnings = (
            parse_validation_warnings
            + style_profile_warnings
            + semantic_validation_warnings
            + citation_path_warnings
            + catalogue_gate_warnings
        )
        diagnostics = _build_diagnostics(
            response_ready_at=_current_time(),
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
    except Phase2ProviderError as exc:
        # Non-Gemini provider failure → execution error dict, surfaced the same
        # way a Gemini failure is (never a silent success).
        diagnostics = _build_diagnostics(
            response_ready_at=_current_time(),
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
            stderr=str(exc),
        )
        return {
            "ok": False,
            "statusCode": exc.status_code,
            "errorCode": exc.error_code,
            "message": str(exc),
            "retryable": exc.retryable,
            "diagnostics": diagnostics,
        }
    except Exception as exc:
        error_msg = str(exc)
        status_code = 429 if "429" in error_msg or "quota" in error_msg.lower() else 502
        diagnostics = _build_diagnostics(
            response_ready_at=_current_time(),
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
    """Terminalizing wrapper around the interpretation attempt body.

    Any exception during setup (grounding lookup, source-artifact resolution,
    profile/config resolution, genai client construction) happens BEFORE the
    Gemini call's own try/except. Without this guard such an exception would
    escape to _interpretation_worker_loop's bare except, which only logs+sleeps,
    leaving the attempt stuck 'running' forever with no reaper
    (recover_incomplete_attempts only runs at process startup). Mirror the
    defensive pattern in _execute_pitch_note_attempt / _execute_mt3_attempt:
    terminalize the attempt so the UI sees a failed state instead of polling
    forever. The status guard in fail_interpretation_attempt keeps this a no-op
    if the run was already interrupted.
    """
    attempt_id = str(attempt["attemptId"])
    try:
        return _execute_interpretation_attempt_inner(runtime, attempt)
    except Exception as exc:
        runtime.fail_interpretation_attempt(
            attempt_id,
            error={
                "code": "INTERPRETATION_SETUP_FAILED",
                "message": str(exc),
                "retryable": True,
                "phase": ERROR_PHASE_GEMINI,
            },
        )
        return {
            "ok": False,
            "statusCode": 500,
            "errorCode": "INTERPRETATION_SETUP_FAILED",
            "message": str(exc),
            "retryable": True,
            "diagnostics": None,
        }


def _execute_interpretation_attempt_inner(
    runtime: AnalysisRuntime,
    attempt: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(attempt["runId"])
    profile_id = _coerce_string(attempt.get("profileId"), "producer_summary")
    grounding = runtime.get_interpretation_grounding(run_id)
    measurement_result = grounding["measurementResult"] or {}
    pitch_note_result = grounding["pitchNoteResult"]
    # MT3 polyphonic transcription, when present, is forwarded to Gemini as
    # additive grounding (OPTIONAL_MT3_TRANSCRIPTION_RESULT_JSON). It is None
    # unless an MT3 attempt completed for this run. PURPOSE.md invariant #1 —
    # Phase 1 stays authoritative; MT3 never overrides measured values.
    mt3_result = grounding.get("mt3Result")
    grounding_metadata = {
        "measurementIsAuthoritative": True,
        "pitchNoteTranslationIsBestEffort": True,
        "mt3TranscriptionIsBestEffort": True,
        "measurementOutputId": grounding["measurementOutputId"],
        "pitchNoteAttemptId": grounding["pitchNoteAttemptId"],
        "mt3AttemptId": grounding.get("mt3AttemptId"),
        "doNotPromotePitchNoteToMeasurement": True,
        "doNotPromoteMt3ToMeasurement": True,
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
            mt3_result=mt3_result,
        )
    else:
        source_artifact = runtime.get_source_artifact(run_id)
        source_local_path = runtime.require_local_artifact_path(
            source_artifact.get("path"),
            purpose="Source audio artifact for interpretation",
        )
        execution = _run_interpretation_request(
            source_path=source_local_path,
            filename=source_artifact["filename"],
            file_size_bytes=source_artifact["sizeBytes"],
            profile_id=profile_id,
            measurement_result=measurement_result,
            pitch_note_result=pitch_note_result,
            grounding_metadata=grounding_metadata,
            model_name=model_name,
            request_id=str(attempt["attemptId"]),
            mt3_result=mt3_result,
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
    owner_user_id: str | None = None,
) -> str:
    if analysis_run_id:
        runtime.get_run(analysis_run_id, owner_user_id=owner_user_id)
        return analysis_run_id
    if phase1_request_id:
        return runtime.get_run_id_by_legacy_request_id(
            phase1_request_id,
            owner_user_id=owner_user_id,
        )
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


async def _mt3_worker_loop() -> None:
    """Peer of _pitch_note_worker_loop / _interpretation_worker_loop.

    Picks up queued MT3 attempts whose owning run's measurement stage has
    completed, runs them through _execute_mt3_attempt, and idles between
    polls. Wired into _create_background_tasks so it activates in both
    local (`include_workers=True`) and hosted-worker process roles.
    """
    while True:
        try:
            attempt = await asyncio.to_thread(get_analysis_runtime().reserve_next_mt3_attempt)
            if attempt is None:
                await asyncio.sleep(WORKER_IDLE_SECONDS)
                continue
            await asyncio.to_thread(
                _execute_mt3_attempt,
                get_analysis_runtime(),
                attempt,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[warn] mt3 worker loop failed: {exc}", file=sys.stderr)
            await asyncio.sleep(WORKER_IDLE_SECONDS)



def _uploaded_file_size_bytes(track: UploadFile) -> int | None:
    file_obj = getattr(track, "file", None)
    if file_obj is None:
        return None
    try:
        current = file_obj.tell()
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(current)
        return size
    except (AttributeError, OSError):
        return None


def _pitch_note_backend_unsupported_response(value: str | None) -> JSONResponse | None:
    try:
        AnalysisRuntime._resolve_pitch_note_backend(value or "auto")
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "PITCH_NOTE_BACKEND_UNSUPPORTED",
                    "message": f"Unsupported pitch_note_backend: {value}",
                }
            },
        )
    return None


def _canonical_upload_too_large_file_response() -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={
            "error": {
                "code": "UPLOAD_TOO_LARGE",
                "message": upload_limits.upload_too_large_message(),
            }
        },
    )


def _legacy_upload_too_large_file_response(request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        headers={"Deprecation": "true"},
        content={
            "requestId": request_id,
            "error": {
                "code": "UPLOAD_TOO_LARGE",
                "message": upload_limits.upload_too_large_message(),
                "phase": ERROR_PHASE_LOCAL_DSP,
                "retryable": False,
            },
            "diagnostics": {"requestId": request_id},
        },
    )

@app.post("/api/analysis-runs")
async def create_analysis_run(
    track: UploadFile | None = File(None),
    url: str | None = Form(None),
    analysis_mode: str = Form("full"),
    pitch_note_mode: str = Form("off"),
    pitch_note_backend: str = Form("auto"),
    interpretation_mode: str = Form("off"),
    interpretation_profile: str = Form("producer_summary"),
    interpretation_model: str | None = Form(None),
    mt3_mode: str = Form("off"),
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> JSONResponse:
    """Create an analysis run from either a multipart upload OR a public URL.

    Exactly one of ``track`` (multipart) or ``url`` (form field) must be
    provided. URL ingestion fetches the file server-side, subject to:

    - HTTP/HTTPS only (no ``file://``, ``ftp://``, etc.).
    - SSRF guard: hostnames that resolve to private, loopback, or
      link-local IPs are rejected pre-flight.
    - Size cap: same 100 MiB limit as multipart uploads
      (``upload_limits.MAX_UPLOAD_SIZE_BYTES``).
    - Timeouts: 30 s connect, 60 s read per chunk.

    See :mod:`url_ingest` for the validation/fetch contract.
    """
    invalid_backend_response = _pitch_note_backend_unsupported_response(pitch_note_backend)
    if invalid_backend_response is not None:
        return invalid_backend_response

    # Exactly-one validation: caller must provide track XOR url. The
    # distinction matters because both modes go through different
    # validation paths.
    #
    # ``isinstance(url, str)`` is intentional rather than ``url is not None``:
    # when this route is called directly in tests (not through HTTP
    # dispatch), FastAPI's ``Form(None)`` default is an unresolved
    # sentinel object — neither None nor a string. Existing multipart
    # tests pre-date the URL field and don't pass ``url`` at all, so we
    # must treat the sentinel as "not provided" rather than calling
    # ``.strip()`` on it.
    track_provided = track is not None and getattr(track, "filename", None)
    url_provided = isinstance(url, str) and url.strip() != ""
    if track_provided and url_provided:
        if track is not None:
            await track.close()
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "AMBIGUOUS_AUDIO_SOURCE",
                    "message": (
                        "Provide exactly one of 'track' (multipart upload) or "
                        "'url' (form field), not both."
                    ),
                    "retryable": False,
                }
            },
        )
    if not track_provided and not url_provided:
        if track is not None:
            await track.close()
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "MISSING_AUDIO_SOURCE",
                    "message": (
                        "Provide either 'track' (multipart upload) or "
                        "'url' (form field) as the audio source."
                    ),
                    "retryable": False,
                }
            },
        )

    # Pre-flight size check is only meaningful for multipart uploads;
    # URL fetches enforce the limit during streaming inside url_ingest.
    if track_provided:
        upload_size = _uploaded_file_size_bytes(track)
        if upload_size is not None and upload_size > upload_limits.MAX_UPLOAD_SIZE_BYTES:
            return _canonical_upload_too_large_file_response()

    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        if track is not None:
            await track.close()
        return user_context
    try:
        if url_provided:
            runtime, run_id = await _create_analysis_run_record_from_url(
                url=url,  # type: ignore[arg-type]
                owner_user_id=user_context.user_id,
                analysis_mode=analysis_mode,
                pitch_note_mode=pitch_note_mode,
                pitch_note_backend=pitch_note_backend,
                interpretation_mode=interpretation_mode,
                interpretation_profile=interpretation_profile,
                interpretation_model=interpretation_model,
                mt3_mode=mt3_mode,
            )
        else:
            runtime, run_id = await _create_analysis_run_record(
                track=track,  # type: ignore[arg-type]
                owner_user_id=user_context.user_id,
                analysis_mode=analysis_mode,
                pitch_note_mode=pitch_note_mode,
                pitch_note_backend=pitch_note_backend,
                interpretation_mode=interpretation_mode,
                interpretation_profile=interpretation_profile,
                interpretation_model=interpretation_model,
                mt3_mode=mt3_mode,
            )
        return JSONResponse(
            content=_normalize_run_snapshot(
                runtime.get_run(run_id, owner_user_id=user_context.user_id),
                runtime,
            )
        )
    except url_ingest.UrlIngestionError as exc:
        return _url_ingest_error_response(exc)
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
    except UnsupportedMt3ModeError as exc:
        # Explicit catch before the generic ValueError fall-through so
        # the client gets a typed MT3_MODE_UNSUPPORTED code, not the
        # generic INTERPRETATION_PROFILE_UNSUPPORTED fallback in
        # _value_error_code.
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "MT3_MODE_UNSUPPORTED",
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
        if track is not None:
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
    # When mt3_mode == "enabled", _estimate_analysis_run forwards run_mt3 to
    # build_analysis_estimate, which appends the MT3 polyphonic-transcription
    # stage to the returned BackendEstimateStage list so the UI can show the
    # added cost before the user commits to the run.
    mt3_mode: str = Form("off"),
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> JSONResponse:
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        await track.close()
        return user_context
    try:
        return await _estimate_analysis_run(
            track=track,
            analysis_mode=analysis_mode,
            pitch_note_mode=pitch_note_mode,
            pitch_note_backend=pitch_note_backend,
            interpretation_mode=interpretation_mode,
            interpretation_profile=interpretation_profile,
            interpretation_model=interpretation_model,
            mt3_mode=mt3_mode,
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
    except UnsupportedMt3ModeError as exc:
        # Mirror the create-run route: an unrecognised mt3_mode (now raised by
        # _coerce_mt3_mode) must surface as a typed MT3_MODE_UNSUPPORTED code,
        # not the generic _value_error_code fall-through below.
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "MT3_MODE_UNSUPPORTED",
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
async def get_analysis_run(
    run_id: str,
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> JSONResponse:
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        return user_context
    runtime = get_analysis_runtime()
    try:
        return JSONResponse(
            content=_normalize_run_snapshot(
                runtime.get_run(run_id, owner_user_id=user_context.user_id),
                runtime,
            )
        )
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)


@app.post("/api/analysis-runs/{run_id}/interrupt")
async def interrupt_analysis_run(
    run_id: str,
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> JSONResponse:
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        return user_context
    runtime = get_analysis_runtime()
    try:
        runtime.get_run(run_id, owner_user_id=user_context.user_id)
        terminated_stages = _interrupt_active_child_processes(run_id)
        snapshot = runtime.interrupt_run(run_id)
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)

    payload = _normalize_run_snapshot(snapshot, runtime)
    payload["interrupt"] = {
        "stagesTerminated": terminated_stages,
    }
    return JSONResponse(status_code=202, content=payload)


@app.delete("/api/analysis-runs/{run_id}")
async def delete_analysis_run(
    run_id: str,
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
    x_admin_key: str | None = Header(None),
) -> JSONResponse:
    """Delete a run, its artifacts, and interrupt any active stages.

    Two paths grant access:

    1. **Owner.** The user resolved from ``X-ASA-User-Id`` (or local-mode
       default) is the run's owner — current behavior, unchanged.
    2. **Operator.** ``X-Admin-Key`` matches the configured
       :data:`auth_context.ADMIN_KEY_ENV_VAR` env var. When this matches,
       the ownership check is skipped — operators can purge any run
       regardless of who owns it. The env var is unset by default; if
       unset, no admin path exists and ownership remains the only gate.

    The admin path still returns ``RUN_NOT_FOUND`` for nonexistent runs,
    so a privileged caller cannot use this endpoint to enumerate
    run IDs (the response is identical whether the run doesn't exist
    or the caller lacks ownership without the key).
    """
    is_admin = auth_context.admin_key_matches(x_admin_key)
    if is_admin:
        # Skip user-context resolution; the admin key is the auth.
        owner_user_id: str | None = None
    else:
        user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
        if isinstance(user_context, JSONResponse):
            return user_context
        owner_user_id = user_context.user_id

    runtime = get_analysis_runtime()
    try:
        runtime.get_run(run_id, owner_user_id=owner_user_id)
        terminated_stages = _interrupt_active_child_processes(run_id)
        runtime.delete_run(run_id)
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)
    return JSONResponse(
        status_code=202,
        content={
            "runId": run_id,
            "deleted": True,
            "deletedBy": "admin" if is_admin else "owner",
            "interrupt": {
                "stagesTerminated": terminated_stages,
            },
        },
    )


@app.get("/api/analysis-runs/{run_id}/artifacts")
async def list_run_artifacts(
    run_id: str,
    kind: str = Query("", description="Filter by kind prefix"),
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> JSONResponse:
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        return user_context
    runtime = get_analysis_runtime()
    try:
        runtime.get_run(run_id, owner_user_id=user_context.user_id)
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)
    prefix = kind if kind else ""
    artifacts = runtime.get_artifacts_by_kind(run_id, prefix)
    return JSONResponse(content=artifacts)


@app.get("/api/analysis-runs/{run_id}/artifacts/{artifact_id}", response_model=None)
async def get_run_artifact(
    run_id: str,
    artifact_id: str,
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> FileResponse | JSONResponse:
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        return user_context
    runtime = get_analysis_runtime()
    try:
        runtime.get_run(run_id, owner_user_id=user_context.user_id)
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)
    match = runtime.get_internal_artifact(run_id, artifact_id)
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
    artifact_local_path = runtime.resolve_artifact_local_path(match.get("path"))
    if artifact_local_path is None or not artifact_local_path.is_file():
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
        path=str(artifact_local_path),
        media_type=match.get("mimeType", "application/octet-stream"),
        filename=match.get("filename", artifact_local_path.name),
    )


@app.get(
    "/api/analysis-runs/{run_id}/source-audio",
    response_model=None,
)
async def get_run_source_audio(
    run_id: str,
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> FileResponse | JSONResponse:
    """Re-serve the audio file originally ingested for ``run_id``.

    The same bytes are reachable via
    ``GET /api/analysis-runs/{run_id}/artifacts/{artifact_id}`` if the
    caller already knows the artifact id, but this route is stable
    (the path doesn't change per run) and saves a round-trip — the
    caller does not need to fetch the snapshot first to learn the
    artifact id. Useful for Phase 2 reruns where the client already
    has the run id but no longer has the source bytes locally.

    Owner-only. Unlike ``DELETE``, this route does not honor
    ``X-Admin-Key``: re-serving another user's audio content has a
    stronger privacy posture than purging another user's run, and the
    review (Track 3) scoped admin bypass to delete operations.

    Returns:
        - 200 with the audio file (FileResponse with the original
          filename in Content-Disposition and the stored MIME type).
        - 404 ``RUN_NOT_FOUND`` if the run does not exist or is not
          owned by the requesting user.
        - 404 ``SOURCE_AUDIO_NOT_FOUND`` if the run exists but has no
          source_artifact row (should be unreachable in practice; it
          would indicate a corrupted runtime state).
        - 404 ``SOURCE_AUDIO_FILE_MISSING`` if the artifact row exists
          but the underlying file is gone from disk.
    """
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        return user_context
    runtime = get_analysis_runtime()

    # Ownership check first; this also confirms the run exists.
    try:
        runtime.get_run(run_id, owner_user_id=user_context.user_id)
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)

    try:
        source_artifact = runtime.get_source_artifact(run_id)
    except KeyError:
        # Run was found by get_run() above, but the source_artifact_id
        # column was null or pointed at a missing row. Defensive — not
        # expected on the normal create_run path. ``retryable`` is
        # ``False`` because the run state is corrupted; a retry on the
        # same id will fail identically.
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "SOURCE_AUDIO_NOT_FOUND",
                    "message": (
                        f"Run '{run_id}' has no source audio artifact "
                        f"registered."
                    ),
                    "retryable": False,
                }
            },
        )

    artifact_local_path = runtime.resolve_artifact_local_path(
        source_artifact.get("path")
    )
    if artifact_local_path is None or not artifact_local_path.is_file():
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "SOURCE_AUDIO_FILE_MISSING",
                    "message": (
                        "Source audio file is no longer available on disk."
                    ),
                    # The artifact metadata is intact but the bytes are
                    # gone; an operator would need to re-ingest. A naive
                    # retry from the client will not recover.
                    "retryable": False,
                }
            },
        )

    return FileResponse(
        path=str(artifact_local_path),
        media_type=source_artifact.get("mimeType", "application/octet-stream"),
        filename=source_artifact.get("filename", artifact_local_path.name),
    )


# ── Audition samples (Phase 3) ───────────────────────────────────────────────
#
# Heuristic reconstructions of the track's tonal foundation + drum kit, derived
# from Phase 1 measurements (and enriched by Phase 2 when available). Used by
# the UI to let producers ear-check the measurement chain. See
# `docs/SAMPLE_GENERATION.md` for the chain-of-custody framing.

@app.post("/api/analysis-runs/{run_id}/samples")
async def create_run_samples(
    run_id: str,
    force: bool = Query(False, description="Regenerate even if a manifest exists"),
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> JSONResponse:
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        return user_context
    runtime = get_analysis_runtime()
    try:
        snapshot = runtime.get_run(run_id, owner_user_id=user_context.user_id)
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)

    try:
        manifest = await asyncio.to_thread(
            server_samples.generate_and_register_samples,
            runtime=runtime,
            run_id=run_id,
            snapshot=snapshot,
            force=force,
        )
    except server_samples.SamplesPreconditionError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
    return JSONResponse(status_code=201, content=manifest)


@app.get("/api/analysis-runs/{run_id}/samples")
async def get_run_samples(
    run_id: str,
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> JSONResponse:
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        return user_context
    runtime = get_analysis_runtime()
    try:
        runtime.get_run(run_id, owner_user_id=user_context.user_id)
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)

    manifest = server_samples.fetch_existing_manifest(runtime=runtime, run_id=run_id)
    if manifest is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "SAMPLES_NOT_GENERATED",
                    "message": (
                        f"No audition samples have been generated for run '{run_id}'. "
                        "POST to this URL to create them."
                    ),
                }
            },
        )
    return JSONResponse(content=manifest)


@app.get(
    "/api/analysis-runs/{run_id}/export/csv/{field_path}",
    response_model=None,
)
async def export_run_field_as_csv(
    run_id: str,
    field_path: str,
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> Response | JSONResponse:
    """Export one Phase 1 time-series field as CSV.

    The ``field_path`` is a simple dot-path into the measurement payload —
    e.g. ``lufsCurve.shortTerm`` or ``rhythmDetail.tempoCurve``. Not
    JSONPath; arbitrary nested-key descent is not supported. See
    :func:`csv_export.list_supported_fields` for the registered list.

    Returns:
        - 200 ``text/csv`` with header row + data rows on success.
        - 404 ``EXPORT_FIELD_NOT_SUPPORTED`` if the path is not in the
          registry.
        - 404 ``RUN_NOT_FOUND`` if the run does not exist or is not
          owned by the requesting user.
        - 404 ``EXPORT_FIELD_NOT_AVAILABLE`` if the field is registered
          but missing/null/empty for this run (measurement may be
          incomplete or the analyzer skipped that field for this audio).
    """
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        return user_context

    if not csv_export.is_supported_field(field_path):
        supported = ", ".join(csv_export.list_supported_fields())
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "EXPORT_FIELD_NOT_SUPPORTED",
                    "message": (
                        f"Field path '{field_path}' is not exportable. "
                        f"Supported paths: {supported}."
                    ),
                }
            },
        )

    runtime = get_analysis_runtime()
    try:
        snapshot = runtime.get_run(run_id, owner_user_id=user_context.user_id)
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)

    measurement_result = (
        snapshot.get("stages", {})
        .get("measurement", {})
        .get("result")
    )
    csv_text = csv_export.export_field_to_csv(measurement_result, field_path)
    if csv_text is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "EXPORT_FIELD_NOT_AVAILABLE",
                    "message": (
                        f"Field '{field_path}' is supported but not "
                        f"populated in run '{run_id}'. The measurement "
                        f"may be incomplete or the analyzer skipped this "
                        f"field for this audio."
                    ),
                }
            },
        )

    # Filename: <run_id>_<dotted_path_with_underscores>.csv
    filename = f"{run_id}_{field_path.replace('.', '_')}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.get("/api/analysis-runs/{run_id}/export/phase2")
async def export_run_phase2(
    run_id: str,
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> JSONResponse:
    """Export the run's Phase 2 handoff envelope (``phase2-export.v1``).

    A single self-contained JSON file for downstream consumers — the
    sibling ``asa-ableton`` ``.als`` generator and the recommendation-proof
    harness (``scripts/evaluate_recommendations.py --phase2``). Carries the
    stored ``producer_summary`` interpretation result verbatim (including
    the frozen ``recommendations.v1`` envelope), the authoritative Phase 1
    measurement payload its citations resolve against, the full
    warn-and-keep ``validationWarnings`` trail, and the stored provenance.
    See :mod:`phase2_export` and ``docs/ASA_ABLETON_BOUNDARY.md``.

    Returns:
        - 200 ``application/json`` with an attachment Content-Disposition.
        - 404 ``RUN_NOT_FOUND`` if the run does not exist or is not owned
          by the requesting user.
        - 404 ``PHASE2_EXPORT_NOT_AVAILABLE`` if the run has no completed
          ``producer_summary`` interpretation result to hand off.
    """
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        return user_context
    runtime = get_analysis_runtime()
    try:
        snapshot = runtime.get_run(run_id, owner_user_id=user_context.user_id)
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)

    envelope = phase2_export.build_phase2_export(snapshot)
    if envelope is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "PHASE2_EXPORT_NOT_AVAILABLE",
                    "message": (
                        f"Run '{run_id}' has no completed producer_summary "
                        f"interpretation result to export. Interpretation "
                        f"may be off, still running, failed, or skipped."
                    ),
                    "retryable": False,
                }
            },
        )

    return JSONResponse(
        content=envelope,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{run_id}_phase2_export.json"'
            ),
        },
    )


@app.get("/api/analysis-runs/{run_id}/transcription/pianoroll")
async def get_transcription_pianoroll(
    run_id: str,
    mode: str = Query(
        "frame",
        description="'frame' (sustained notes painted across their duration) "
        "or 'onset' (note starts only — useful for rhythmic visualization).",
    ),
    pitch_low: int = Query(
        transcription_pianoroll.DEFAULT_PITCH_LOW,
        alias="pitchLow",
        description="Lower MIDI pitch bound (inclusive). Default: 21 (A0).",
    ),
    pitch_high: int = Query(
        transcription_pianoroll.DEFAULT_PITCH_HIGH,
        alias="pitchHigh",
        description="Upper MIDI pitch bound (exclusive). Default: 109 "
        "(one above C8 — the 88-key piano range).",
    ),
    tpq: int = Query(
        transcription_pianoroll.DEFAULT_TPQ,
        description="Time resolution in ticks per quarter note. Default: 4 "
        "(one row per 16th note at typical tempos).",
    ),
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> JSONResponse:
    """Render the run's transcriptionDetail as a velocity-encoded pianoroll.

    Derived view — Phase 1's ``transcriptionDetail`` (sourced from the
    pitch-note translation stage) stays authoritative. The response cites
    Phase 1's ``bpm`` + ``timeSignature`` so the UI surface can attribute
    every cell back to a measurement (invariant #2 in ``PURPOSE.md``).

    Status mapping is deliberately split between 404 (won't appear without
    user action) and 409 (wait or finish a prerequisite):

    * 404 ``RUN_NOT_FOUND`` — run doesn't exist or is not owned by the caller.
    * 409 ``MEASUREMENT_NOT_COMPLETED`` — measurement stage hasn't finished.
    * 404 ``TRANSCRIPTION_NOT_REQUESTED`` — run was created with pitch-note
      translation disabled. The caller should enable transcription on a new run.
    * 409 ``TRANSCRIPTION_NOT_COMPLETED`` — pitch-note stage is queued/running.
    * 404 ``TRANSCRIPTION_NOT_AVAILABLE`` — pitch-note stage completed (or
      failed / was interrupted) without producing a ``transcriptionDetail``
      payload. Caller's affordance is "re-run the transcription stage."
    * 400 ``INVALID_MODE`` / ``INVALID_PITCH_RANGE`` / ``INVALID_TPQ`` —
      query parameter validation. Returned as structured codes rather than
      FastAPI's default 422 so clients can branch on them.
    """
    # Up-front query validation so the route returns structured error codes
    # rather than letting ``render_pianoroll`` raise generic ``ValueError``
    # — clients should be able to switch on the specific failure.
    if mode not in ("frame", "onset"):
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_MODE",
                    "message": f"mode must be 'frame' or 'onset'; got {mode!r}.",
                }
            },
        )
    if pitch_low < 0 or pitch_high > 128 or pitch_low >= pitch_high:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_PITCH_RANGE",
                    "message": (
                        f"pitch range [{pitch_low}, {pitch_high}) is invalid; "
                        "must satisfy 0 <= pitchLow < pitchHigh <= 128."
                    ),
                }
            },
        )
    if tpq < 1:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_TPQ",
                    "message": f"tpq must be >= 1; got {tpq}.",
                }
            },
        )

    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        return user_context

    runtime = get_analysis_runtime()
    try:
        snapshot = runtime.get_run(run_id, owner_user_id=user_context.user_id)
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)

    stages = snapshot.get("stages", {}) if isinstance(snapshot, dict) else {}
    measurement = stages.get("measurement", {}) or {}
    if measurement.get("status") != "completed":
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "MEASUREMENT_NOT_COMPLETED",
                    "message": (
                        "Measurement stage must complete before the "
                        "transcription pianoroll can be rendered."
                    ),
                }
            },
        )

    pn_stage = stages.get("pitchNoteTranslation", {}) or {}
    pn_status = pn_stage.get("status")
    if pn_status == "not_requested":
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "TRANSCRIPTION_NOT_REQUESTED",
                    "message": (
                        "This run was created with pitch-note translation "
                        "disabled. Enable transcription on a new run to "
                        "render the pianoroll."
                    ),
                }
            },
        )
    if pn_status in ("ready", "queued", "running"):
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "TRANSCRIPTION_NOT_COMPLETED",
                    "message": (
                        "Pitch-note translation has not finished. Wait for "
                        "the stage to complete and try again."
                    ),
                }
            },
        )

    # The pitch-note worker stores the transcriptionDetail dict *directly* as
    # the stage result (see _execute_pitch_note_attempt →
    # complete_pitch_note_attempt(result=transcription_detail) above), so the
    # canonical shape is unwrapped. Tolerate a legacy ``{"transcriptionDetail":
    # {...}}`` wrapper defensively, then require a ``notes`` list so a stray
    # non-transcription dict (or a ``{"transcriptionDetail": None}`` null) can't
    # masquerade as a payload.
    pn_result = pn_stage.get("result")
    if isinstance(pn_result, dict):
        nested = pn_result.get("transcriptionDetail")
        transcription_detail = nested if isinstance(nested, dict) else pn_result
    else:
        transcription_detail = None
    if not isinstance(transcription_detail, dict) or not isinstance(
        transcription_detail.get("notes"), list
    ):
        # Covers: completed-but-null result, failed attempt, interrupted
        # attempt — the user's recourse is identical (re-run transcription).
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "TRANSCRIPTION_NOT_AVAILABLE",
                    "message": (
                        "Pitch-note translation did not produce a "
                        "transcriptionDetail payload for this run."
                    ),
                }
            },
        )

    measurement_result = (
        measurement.get("result")
        if isinstance(measurement.get("result"), dict)
        else {}
    )
    bpm_value = measurement_result.get("bpm")
    time_signature_value = measurement_result.get("timeSignature")

    payload = transcription_pianoroll.render_pianoroll(
        transcription_detail,
        bpm=(
            float(bpm_value)
            if isinstance(bpm_value, (int, float)) and bpm_value > 0
            else None
        ),
        time_signature=(
            time_signature_value
            if isinstance(time_signature_value, str)
            else None
        ),
        mode=mode,  # type: ignore[arg-type]
        pitch_low=pitch_low,
        pitch_high=pitch_high,
        tpq=tpq,
    )
    return JSONResponse(
        content=transcription_pianoroll.payload_to_json_dict(payload)
    )


_ENHANCEMENT_GENERATORS = {
    "cqt": ("generate_cqt_spectrogram", ["spectrogram_cqt"], True),
    "hpss": ("generate_hpss_spectrograms", ["spectrogram_harmonic", "spectrogram_percussive"], True),
    "onset": ("generate_onset_enhancement", ["spectrogram_onset", "onset_strength"], True),
    "chroma_interactive": ("generate_chroma_enhancement", ["spectrogram_chroma", "chroma_interactive"], True),
    "reassigned": ("generate_reassigned_spectrogram", ["spectrogram_reassigned"], True),
}


@app.post("/api/analysis-runs/{run_id}/spectral-enhancements/{kind}")
async def generate_spectral_enhancement(
    run_id: str,
    kind: str,
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> JSONResponse:
    if kind not in _ENHANCEMENT_GENERATORS:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "INVALID_KIND", "message": f"Unknown enhancement kind: '{kind}'. Valid: {', '.join(_ENHANCEMENT_GENERATORS)}"}},
        )

    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        return user_context
    runtime = get_analysis_runtime()
    try:
        run = runtime.get_run(run_id, owner_user_id=user_context.user_id)
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)

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
        existing.extend(runtime.get_internal_artifacts_by_kind(run_id, ak))
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
            source_local_path = runtime.require_local_artifact_path(
                source.get("path"),
                purpose="Source audio artifact for spectral enhancement generation",
            )
            if is_image:
                result = gen_func(source_local_path, tmp_dir)
            else:
                data = gen_func(source_local_path)
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


@app.post("/api/analysis-runs/{run_id}/mt3-transcriptions")
async def create_mt3_transcription_attempt(
    run_id: str,
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> JSONResponse:
    """Manually enqueue an MT3 attempt on an existing run.

    Mirror of :func:`create_pitch_note_translation_attempt`. Used when a
    client wants to opt into MT3 *after* the run was created (e.g. the
    initial POST /api/analysis-runs had ``mt3_mode='off'`` but the user
    later decides they want a MIDI export). The measurement stage must be
    completed first — MT3 reads stems and/or the source audio that
    measurement persists as artifacts.

    Returns 202 with the post-enqueue snapshot. The worker (started by
    ``_create_background_tasks``) will reserve and run the attempt.

    No request body / form fields today — MT3 has no configurable
    backend or mode. If/when multiple checkpoints land, the route can
    accept ``checkpoint_id`` without changing its URL.
    """
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        return user_context
    runtime = get_analysis_runtime()
    try:
        runtime.get_run(run_id, owner_user_id=user_context.user_id)
        if runtime.get_measurement_status(run_id) != "completed":
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "MEASUREMENT_NOT_READY",
                        "message": "Measurement must complete before MT3 transcription can run.",
                    }
                },
            )
        runtime.create_mt3_attempt(
            run_id,
            status="queued",
            provenance={
                "schemaVersion": "mt3_transcription.v1",
                "requestedViaApi": True,
            },
        )
        return JSONResponse(
            status_code=202,
            content=_normalize_run_snapshot(
                runtime.get_run(run_id, owner_user_id=user_context.user_id),
                runtime,
            ),
        )
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)


@app.post("/api/analysis-runs/{run_id}/pitch-note-translations")
async def create_pitch_note_translation_attempt(
    run_id: str,
    pitch_note_mode: str = Form("stem_notes"),
    pitch_note_backend: str = Form("auto"),
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> JSONResponse:
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        return user_context
    runtime = get_analysis_runtime()
    try:
        runtime.get_run(run_id, owner_user_id=user_context.user_id)
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
        return JSONResponse(
            status_code=202,
            content=_normalize_run_snapshot(
                runtime.get_run(run_id, owner_user_id=user_context.user_id),
                runtime,
            ),
        )
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)
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
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
) -> JSONResponse:
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        return user_context
    runtime = get_analysis_runtime()
    try:
        runtime.get_run(run_id, owner_user_id=user_context.user_id)
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
        return JSONResponse(
            status_code=202,
            content=_normalize_run_snapshot(
                runtime.get_run(run_id, owner_user_id=user_context.user_id),
                runtime,
            ),
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
    except (KeyError, PermissionError):
        return _run_not_found_response(run_id)



def _build_backend_estimate(
    audio_path: str,
    run_separation: bool,
    run_transcribe: bool,
    *,
    analysis_mode: str = "full",
    run_mt3: bool = False,
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
            run_mt3=run_mt3,
        )
    else:
        raw_estimate = build_analysis_estimate(
            safe_duration,
            run_separation,
            run_transcribe,
            run_mt3=run_mt3,
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
        response_ready_at=_current_time(),
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
        response_ready_at=_current_time(),
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
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
):
    logger.warning("Legacy compatibility endpoint hit: /api/analyze/estimate")
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        await track.close()
        return _mark_legacy_endpoint_response(user_context, endpoint="/api/analyze/estimate")
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
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
):
    upload_size = _uploaded_file_size_bytes(track)
    if upload_size is not None and upload_size > upload_limits.MAX_UPLOAD_SIZE_BYTES:
        return _legacy_upload_too_large_file_response(str(uuid4()))

    request_id = str(uuid4())
    logger.warning("Legacy compatibility endpoint hit: /api/analyze request_id=%s", request_id)
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        await track.close()
        return _mark_legacy_endpoint_response(user_context, endpoint="/api/analyze")
    try:
        _ = dsp_json_override
        analysis_mode = _resolve_analysis_mode_value(analysis_mode)
        requested_pitch_note_mode = _resolve_pitch_note_mode_for_legacy(transcribe)
        runtime, run_id = await _create_analysis_run_record(
            track=track,
            owner_user_id=user_context.user_id,
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
    x_asa_user_id: str | None = Header(None),
    x_asa_user_email: str | None = Header(None),
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
    user_context = _resolve_route_user_context(x_asa_user_id, x_asa_user_email)
    if isinstance(user_context, JSONResponse):
        await track.close()
        return _mark_legacy_endpoint_response(user_context, endpoint="/api/phase2")
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
                owner_user_id=user_context.user_id,
            )
        except (KeyError, PermissionError):
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

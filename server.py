import json
import os
import subprocess
import tempfile
import time
from math import ceil
from math import isfinite
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from analyze import build_analysis_estimate, get_audio_duration_seconds


app = FastAPI(title="Sonic Analyzer Local API")

ANALYZE_TIMEOUT_BUFFER_SECONDS = 15
ERROR_PHASE_LOCAL_DSP = "phase1_local_dsp"
ENGINE_VERSION = "analyze.py"
MAX_SNIPPET_LENGTH = 2000
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
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
        "lufsRange": payload.get("lufsRange"),
        "truePeak": _coerce_number(payload.get("truePeak")),
        "crestFactor": payload.get("crestFactor"),
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


def _persist_upload(track: UploadFile) -> str:
    suffix = Path(track.filename or "upload.bin").suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = temp_file.name
        while True:
            chunk = track.file.read(1024 * 1024)
            if not chunk:
                break
            temp_file.write(chunk)
    return temp_path


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


def _build_backend_estimate(audio_path: str, run_separation: bool) -> dict[str, Any]:
    try:
        duration_seconds = get_audio_duration_seconds(audio_path)
    except Exception:
        duration_seconds = None

    safe_duration = duration_seconds if duration_seconds is not None else 0.0
    raw_estimate = build_analysis_estimate(safe_duration, run_separation, False)
    raw_stages = raw_estimate.get("stages")
    stages = (
        [_normalize_estimate_stage(stage) for stage in raw_stages if isinstance(stage, dict)]
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
        if isinstance(duration_seconds, (int, float)) and isfinite(float(duration_seconds))
        else round(float(raw_estimate.get("durationSeconds", 0.0)), 1)
    )

    return {
        "durationSeconds": normalized_duration,
        "totalLowMs": total_low_ms,
        "totalHighMs": total_high_ms,
        "stages": stages,
    }


def _compute_timeout_seconds(estimate: dict[str, Any]) -> int:
    estimated_high_ms = _coerce_positive_int(estimate.get("totalHighMs"))
    estimated_high_seconds = ceil(estimated_high_ms / 1000) if estimated_high_ms > 0 else 45
    return estimated_high_seconds + ANALYZE_TIMEOUT_BUFFER_SECONDS


def _compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _build_error_response(
    *,
    request_id: str,
    status_code: int,
    error_code: str,
    message: str,
    retryable: bool,
    backend_duration_ms: float,
    timeout_seconds: int,
    estimate: dict[str, Any],
    stdout: Any = None,
    stderr: Any = None,
) -> JSONResponse:
    diagnostics = _compact_dict(
        {
            "backendDurationMs": round(float(backend_duration_ms), 2),
            "timeoutSeconds": timeout_seconds,
            "estimatedLowMs": _coerce_positive_int(estimate.get("totalLowMs")),
            "estimatedHighMs": _coerce_positive_int(estimate.get("totalHighMs")),
            "stdoutSnippet": _safe_snippet(stdout),
            "stderrSnippet": _safe_snippet(stderr),
        }
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
    backend_duration_ms: float,
    timeout_seconds: int,
    estimate: dict[str, Any],
) -> JSONResponse:
    return JSONResponse(
        content={
            "requestId": request_id,
            "phase1": _build_phase1(payload),
            "diagnostics": {
                "backendDurationMs": round(float(backend_duration_ms), 2),
                "engineVersion": ENGINE_VERSION,
                "estimatedLowMs": _coerce_positive_int(estimate.get("totalLowMs")),
                "estimatedHighMs": _coerce_positive_int(estimate.get("totalHighMs")),
                "timeoutSeconds": timeout_seconds,
            },
        }
    )


@app.post("/api/analyze/estimate")
async def estimate_analysis(
    track: UploadFile = File(...),
    dsp_json_override: str | None = Form(None),
    transcribe: bool = Form(False),
    separate: bool = Query(False, description="Pass --separate to analyze.py when true"),
    separate_flag: bool = Query(
        False,
        alias="--separate",
        description="Alias for separate; accepts query key --separate",
    ),
):
    temp_path: str | None = None
    try:
        temp_path = _persist_upload(track)
        _ = dsp_json_override, transcribe
        run_separation = bool(separate or separate_flag)
        estimate = _build_backend_estimate(temp_path, run_separation)
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
    separate: bool = Query(False, description="Pass --separate to analyze.py when true"),
    separate_flag: bool = Query(
        False,
        alias="--separate",
        description="Alias for separate; accepts query key --separate",
    ),
):
    temp_path: str | None = None
    request_id = str(uuid4())
    backend_duration_ms = 0.0
    try:
        temp_path = _persist_upload(track)
        _ = dsp_json_override
        run_separation = bool(separate or separate_flag)
        estimate = _build_backend_estimate(temp_path, run_separation)

        command = ["./venv/bin/python", "analyze.py", temp_path, "--yes"]
        if run_separation:
            command.append("--separate")
        if transcribe:
            command.append("--transcribe")

        timeout_seconds = _compute_timeout_seconds(estimate)
        started_at = time.perf_counter()
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            backend_duration_ms = (time.perf_counter() - started_at) * 1000
            return _build_error_response(
                request_id=request_id,
                status_code=504,
                error_code="ANALYZER_TIMEOUT",
                message="Local DSP analysis timed out before completion.",
                retryable=True,
                backend_duration_ms=backend_duration_ms,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                stdout=exc.stdout,
                stderr=exc.stderr,
            )
        except Exception as exc:
            backend_duration_ms = (time.perf_counter() - started_at) * 1000
            return _build_error_response(
                request_id=request_id,
                status_code=500,
                error_code="BACKEND_INTERNAL_ERROR",
                message="Local DSP backend hit an unexpected server error.",
                retryable=False,
                backend_duration_ms=backend_duration_ms,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                stderr=exc,
            )
        backend_duration_ms = (time.perf_counter() - started_at) * 1000

        if result.returncode != 0:
            return _build_error_response(
                request_id=request_id,
                status_code=502,
                error_code="ANALYZER_FAILED",
                message="Local DSP analysis failed before a valid result was produced.",
                retryable=True,
                backend_duration_ms=backend_duration_ms,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
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
                backend_duration_ms=backend_duration_ms,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
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
                backend_duration_ms=backend_duration_ms,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
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
                backend_duration_ms=backend_duration_ms,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                stdout=stdout,
                stderr=result.stderr,
            )

        return _build_success_response(
            request_id=request_id,
            payload=payload,
            backend_duration_ms=backend_duration_ms,
            timeout_seconds=timeout_seconds,
            estimate=estimate,
        )
    finally:
        await track.close()
        _cleanup_temp_path(temp_path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)

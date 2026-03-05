import json
import os
import subprocess
import tempfile
import time
from math import isfinite
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


app = FastAPI(title="Sonic Analyzer Local API")

DEFAULT_ANALYZE_TIMEOUT_SECONDS = 30
SEPARATE_ANALYZE_TIMEOUT_SECONDS = 60
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
        "truePeak": _coerce_number(payload.get("truePeak")),
        "stereoWidth": _coerce_number(stereo_detail.get("stereoWidth")),
        "stereoCorrelation": _coerce_number(stereo_detail.get("stereoCorrelation")),
        "spectralBalance": {
            "subBass": _coerce_number(spectral_balance.get("subBass")),
            "lowBass": _coerce_number(spectral_balance.get("lowBass")),
            "mids": _coerce_number(spectral_balance.get("mids")),
            "upperMids": _coerce_number(spectral_balance.get("upperMids")),
            "highs": _coerce_number(spectral_balance.get("highs")),
            "brilliance": _coerce_number(spectral_balance.get("brilliance")),
        },
    }


@app.post("/api/analyze")
async def analyze_audio(
    track: UploadFile = File(...),
    dsp_json_override: str | None = Form(None),
    separate: bool = Query(False, description="Pass --separate to analyze.py when true"),
    separate_flag: bool = Query(
        False,
        alias="--separate",
        description="Alias for separate; accepts query key --separate",
    ),
):
    temp_path: str | None = None
    try:
        suffix = Path(track.filename or "upload.bin").suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            while True:
                chunk = await track.read(1024 * 1024)
                if not chunk:
                    break
                temp_file.write(chunk)

        _ = dsp_json_override

        command = ["./venv/bin/python", "analyze.py", temp_path]
        if separate or separate_flag:
            command.append("--separate")

        timeout_seconds = (
            SEPARATE_ANALYZE_TIMEOUT_SECONDS
            if (separate or separate_flag)
            else DEFAULT_ANALYZE_TIMEOUT_SECONDS
        )
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
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            raise HTTPException(
                status_code=504,
                detail={
                    "message": "analyze.py timed out",
                    "timeoutSeconds": timeout_seconds,
                    "durationMs": duration_ms,
                    "stdout": (exc.stdout or ""),
                    "stderr": (exc.stderr or ""),
                },
            ) from exc
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "analyze.py returned a non-zero exit code",
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )

        stdout = result.stdout.strip()
        if not stdout:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "analyze.py returned empty stdout",
                    "stderr": result.stderr,
                },
            )

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "analyze.py stdout was not valid JSON",
                    "stdout": stdout,
                    "stderr": result.stderr,
                },
            ) from exc

        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "analyze.py JSON root was not an object",
                    "stdout": stdout,
                    "stderr": result.stderr,
                },
            )

        response = {
            "requestId": str(uuid4()),
            "phase1": _build_phase1(payload),
            "diagnostics": {
                "backendDurationMs": duration_ms,
                "engineVersion": "analyze.py",
            },
        }

        return JSONResponse(content=response)
    finally:
        await track.close()
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)

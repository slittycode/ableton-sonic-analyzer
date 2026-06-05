"""MOSS-Audio Phase 2 sidecar — a standalone FastAPI service.

Fed the same inputs as Gemini (built prompt + audio + authoritative Phase 1 JSON
+ ``response_schema``), it returns a ``Phase2Result`` that the ASA backend
validates through the *identical* parse / citation / catalogue path as Gemini
(see ``apps/backend/phase2_provider.py``). Run it on its **own venv** (FastAPI +
uvicorn — and, only if/when licensing is resolved, the model stack), isolated
from the product venv exactly like the MSST separation runner.

Modes (env ``ASA_MOSS_SIDECAR_MODE``):
  - ``mock`` (default): deterministic, schema-valid, Phase-1-grounded output via
    ``mock_interpreter``. No model, no GPU. This is what the experiment + eval use.
  - ``model``: the real MOSS-Audio path — a **gated stub**. STEP ONE found the
    MOSS-Audio *weights* are Apache-2.0 but the *modeling code* you must run has
    no effective licence (the GitHub repo's ``pyproject`` points at a ``LICENSE``
    file that does not exist). So this service ships **no** OpenMOSS code and the
    ``model`` path raises a 501 explaining what would unblock it. See
    ``docs/PHASE2_PROVIDER.md`` and the README in this directory.

Run:
    uvicorn moss_sidecar.app:app --host 127.0.0.1 --port 8200    # from apps/backend
    # or: python -m moss_sidecar.app
"""

from __future__ import annotations

import os
from typing import Any

try:  # allow both `uvicorn moss_sidecar.app:app` and `python -m moss_sidecar.app`
    from .mock_interpreter import build_mock_phase2_result
except ImportError:  # pragma: no cover - direct-script fallback
    from mock_interpreter import build_mock_phase2_result  # type: ignore

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


SIDECAR_MODE = os.getenv("ASA_MOSS_SIDECAR_MODE", "mock").strip().lower()

app = FastAPI(title="ASA MOSS-Audio Phase 2 Sidecar", version="0.1.0")


class AudioPayload(BaseModel):
    filename: str
    mime_type: str
    base64: str


class Phase2SidecarRequest(BaseModel):
    prompt: str
    response_schema: dict[str, Any] = Field(default_factory=dict)
    phase1: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None
    request_id: str | None = None
    audio: AudioPayload | None = None


class Phase2SidecarResponse(BaseModel):
    result: dict[str, Any] | None
    provider: str
    warnings: list[str] = Field(default_factory=list)


def _run_model_interpreter(request: Phase2SidecarRequest) -> dict[str, Any]:
    """Real MOSS-Audio inference — intentionally a licence-gated stub.

    This deliberately imports and executes **no** OpenMOSS code. Two independent
    conditions must hold before a real implementation may live here:

      1. The MOSS-Audio inference/modeling code carries an effective licence
         permitting self-host + derivative use (today it does not — the GitHub
         repo has no ``LICENSE`` file; only the *weights* are Apache-2.0), OR a
         cleanly-licensed runtime (e.g. an Apache/MIT reimplementation) can serve
         the Apache-2.0 weights for audio-in inference.
      2. The operator opts in explicitly via ``ASA_MOSS_ALLOW_UNLICENSED_MODEL=1``
         and supplies a runner path — and accepts the licence risk.

    Until then this raises 501 so the failure is loud and honest rather than a
    silent fabrication.
    """
    if os.getenv("ASA_MOSS_ALLOW_UNLICENSED_MODEL", "").strip() != "1":
        raise HTTPException(
            status_code=501,
            detail=(
                "MOSS-Audio model mode is not wired: the modeling code has no "
                "effective licence (STEP ONE gate). Use ASA_MOSS_SIDECAR_MODE=mock, "
                "or resolve the licence and supply a cleanly-licensed runtime. See "
                "docs/PHASE2_PROVIDER.md."
            ),
        )
    raise HTTPException(
        status_code=501,
        detail=(
            "Real MOSS-Audio inference is not implemented in this sidecar by "
            "design — it would execute currently-unlicensed OpenMOSS modeling "
            "code. Provide a cleanly-licensed runtime and implement "
            "_run_model_interpreter against it."
        ),
    )


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ok", "mode": SIDECAR_MODE, "provider": _provider_label()}


def _provider_label() -> str:
    return "moss-mock" if SIDECAR_MODE == "mock" else "moss"


@app.post("/v1/phase2", response_model=Phase2SidecarResponse)
def interpret(request: Phase2SidecarRequest) -> Phase2SidecarResponse:
    if SIDECAR_MODE == "mock":
        result = build_mock_phase2_result(request.phase1, prompt=request.prompt)
        return Phase2SidecarResponse(result=result, provider="moss-mock", warnings=[])
    if SIDECAR_MODE == "model":
        result = _run_model_interpreter(request)
        return Phase2SidecarResponse(result=result, provider="moss", warnings=[])
    raise HTTPException(
        status_code=500,
        detail=f"Unknown ASA_MOSS_SIDECAR_MODE '{SIDECAR_MODE}' (expected 'mock' or 'model').",
    )


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("ASA_MOSS_SIDECAR_HOST", "127.0.0.1"),
        port=int(os.getenv("ASA_MOSS_SIDECAR_PORT", "8200")),
    )

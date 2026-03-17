# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Full Stack

```bash
./scripts/dev.sh                    # Start both services (UI: 3100, backend: 8100)
```

### Frontend (`apps/ui`)

```bash
npm run dev:local                   # Dev server on 127.0.0.1:3100
npm run verify                      # lint + test:unit + build + test:smoke (full gate)
npm run lint                        # TypeScript type-check only (no ESLint/Prettier)
npm test                            # All Vitest unit tests
npm run test:unit                   # Unit tests only (tests/services/)
npm run test:smoke                  # Playwright smoke tests
npx vitest run tests/services/backendPhase1Client.test.ts   # Single test file
```

### Backend (`apps/backend`)

```bash
./scripts/bootstrap.sh              # Create/recreate venv (Python 3.11.x required)
./venv/bin/python server.py         # FastAPI server on 8100
./venv/bin/python analyze.py <file> [--separate] [--transcribe] [--fast] [--yes]
./venv/bin/python -m unittest discover -s tests             # All backend tests
./venv/bin/python -m unittest tests.test_server             # Single test module
./venv/bin/python -m unittest tests.test_analyze            # Snapshot tests
```

## Architecture

This is a two-phase audio analysis system:

- **Phase 1 (local DSP):** Audio file → Python backend → structured metrics
- **Phase 2 (optional AI):** Phase 1 result + audio → Gemini API directly from browser → Ableton Live recommendations

### Backend (`apps/backend`)

Two-file design:

- **`analyze.py`** (~112KB): Pure DSP pipeline. Runs as a subprocess. Extracts BPM, key, LUFS, stereo width, spectral balance, rhythm/melody detail, transcription (Basic Pitch), stem separation (Demucs). **Writes JSON to stdout, diagnostics to stderr** — this contract is load-bearing.
- **`server.py`** (~24KB): FastAPI HTTP wrapper. Accepts multipart uploads, invokes `analyze.py` as a subprocess, normalizes raw output into the `phase1` HTTP contract, returns structured JSON.

The subprocess isolation means `analyze.py` can be used standalone via CLI and the HTTP contract is a deliberate subset of the raw CLI output. Fields like `bpmPercival`, `bpmAgreement`, `dynamicCharacter`, `essentiaFeatures` are in the raw CLI output but are **not exposed** over HTTP.

**Python 3.12+ is unsupported on macOS arm64** because `basic-pitch` pulls a `tensorflow-macos`/NumPy combination that doesn't resolve cleanly.

### Frontend (`apps/ui`)

Single-page React 19 app with no router. View states are managed via React conditionals (upload → estimate → analysis → results).

Key service files:

- **`src/services/backendPhase1Client.ts`**: All HTTP transport to the backend. Multipart POST, typed error classes (`BackendClientError`), `AbortController` timeouts (estimate: 30s, analyze: 600s+), identity probe via `/openapi.json`.
- **`src/services/geminiPhase2Client.ts`**: Direct Gemini API calls from browser. Handles file upload for large files, structured prompt engineering, retry with exponential backoff.
- **`src/types.ts`**: Source of truth for `Phase1Result`, `Phase2Result`, and all backend response shapes.
- **`src/config.ts`**: Runtime resolution of `VITE_API_BASE_URL` and feature flags.

`AnalysisResults.tsx` (~45KB) is lazy-loaded via Suspense. Manual vendor chunks in `vite.config.ts` control bundle splitting (react, google-ai, waveform, midi).

### Frontend-Backend Contract

The `phase1` field in `BackendAnalyzeResponse` and `Phase1Result` in `types.ts` are the interface between the two apps. **Do not rename fields on either side without updating both.** The backend normalizes raw analyzer output into this shape; the frontend expects it exactly.

Error envelopes always include `requestId`, `error.code`, `error.message`, `error.retryable`, and `diagnostics`.

## Environment Variables

```bash
# apps/ui/.env (copy from .env.example)
VITE_API_BASE_URL="http://127.0.0.1:8100"
VITE_ENABLE_PHASE2_GEMINI="true"
VITE_GEMINI_API_KEY="your_key_here"

# Backend (env var, no .env file)
SONIC_ANALYZER_PORT=8100
```

Phase 2 Gemini is gated by `VITE_ENABLE_PHASE2_GEMINI`. Without it, only Phase 1 runs. The API key lives in the browser bundle — this project is marked as local/dev only (`v1.0.0`) until that moves server-side.

## Key Guardrails

- **Backend contract:** `analyze.py` stdout → JSON only. `server.py` HTTP shapes → match `types.ts`. Read `apps/backend/ARCHITECTURE.md` and `apps/backend/JSON_SCHEMA.md` before changing analyzer output or HTTP responses.
- **No linter/formatter:** No ESLint, Prettier, or Ruff configured. Follow the style of the surrounding code.
- **Backend tests use stdlib `unittest`**, not pytest. Frontend tests use Vitest in `node` environment (not jsdom).
- **`npm run lint`** only type-checks `src/`; test files and `playwright.config.ts` are excluded from `tsconfig.json`.
- **Canonical ports:** UI on 3100, backend on 8100. `./scripts/dev.sh` will fail loudly if either port is occupied.
- **`--fast` flag** is accepted by `analyze.py` but is currently a no-op.

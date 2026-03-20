# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Full Stack

```bash
./scripts/dev.sh                    # Start both services (UI: 3100, backend: 8100)
```

`scripts/dev.sh` waits for the backend contract (`/openapi.json` with title `"Sonic Analyzer Local API"`) before launching the UI. It reads `apps/ui/.env` but overrides `VITE_API_BASE_URL` for the spawned process, so stale `.env` files won't break the stack.

### Frontend (`apps/ui`)

```bash
npm run dev:local                   # Dev server on 127.0.0.1:3100
npm run verify                      # lint + test:unit + build + test:smoke (full gate)
npm run lint                        # TypeScript type-check only (no ESLint/Prettier)
npm test                            # All Vitest unit tests
npm run test:unit                   # Unit tests only (tests/services/)
npm run test:smoke                  # Playwright smoke tests

# Single test file
npx vitest run tests/services/backendPhase1Client.test.ts
# Single test by name
npx vitest run tests/services/backendPhase1Client.test.ts -t "accepts a valid backend payload"
# Single smoke spec
npm run test:smoke -- tests/smoke/upload-phase1.spec.ts
```

### Backend (`apps/backend`)

```bash
./scripts/bootstrap.sh              # Create/recreate venv (Python 3.11.x required)
./venv/bin/python server.py         # FastAPI server on 8100
./venv/bin/python analyze.py <file> [--separate] [--transcribe] [--fast] [--yes]

# All backend tests
./venv/bin/python -m unittest discover -s tests
# Single test module
./venv/bin/python -m unittest tests.test_server
./venv/bin/python -m unittest tests.test_analyze
# Single test class
./venv/bin/python -m unittest tests.test_server.ServerContractTests
# Single test case
./venv/bin/python -m unittest tests.test_server.ServerContractTests.test_analyze_endpoint_combines_separate_and_transcribe_in_subprocess
```

## Architecture

### Three-Layer Model

ASA's hybrid architecture splits work into three layers. Read `docs/ARCHITECTURE_STRATEGY.md` before proposing changes to this structure — it records *why* the design is shaped this way.

```
Layer 1 — MEASUREMENT (Essentia/DSP)    → deterministic, authoritative for numbers
Layer 2 — SYMBOLIC EXTRACTION (torchcrepe/PENN) → best-effort pitch/note extraction on stems
Layer 3 — INTERPRETATION (Gemini)        → contextual advice grounded in Layer 1 measurements
```

Core thesis: measure locally, extract symbolically where honest, interpret with AI grounded in measurements. Phase 2 (Gemini) never overrides Phase 1 measured values.

### Staged Analysis Runs

The backend supports staged execution via `analysis_runtime.py`, which persists run state in SQLite (`.runtime/analysis_runs.sqlite3`) and artifacts on disk. Stages execute as a queue:

1. **measurement** — Phase 1 DSP via `analyze.py`
2. **symbolic extraction** — pitch/note extraction on Demucs-separated stems
3. **interpretation** — Gemini Phase 2 advisory

Run-oriented endpoints (`/api/analysis-runs*`) are the canonical interface for staged execution. Legacy `POST /api/analyze` and `POST /api/analyze/estimate` remain but are not the primary path.

Frontend polling: `src/services/analysisRunsClient.ts` creates runs and polls stage snapshots. `src/services/analyzer.ts` orchestrates the create-run + poll loop and projects display payloads.

### Backend (`apps/backend`)

**Two-file core plus runtime:**

1. **`analyze.py`** (~112KB): Pure DSP pipeline. Runs as a subprocess invoked by `server.py`. Extracts BPM, key, LUFS, stereo width, spectral balance, rhythm/melody detail, transcription, stem separation. **Writes JSON to stdout, diagnostics to stderr** — this contract is load-bearing.
2. **`server.py`** (~24KB): FastAPI HTTP wrapper. Accepts multipart uploads, invokes `analyze.py` as a subprocess, normalizes raw output into the `phase1` HTTP contract, returns structured JSON. Also hosts the staged run endpoints.
3. **`analysis_runtime.py`**: SQLite-backed run state and stage queue management. Artifacts stored in `.runtime/artifacts/`.

The subprocess isolation means `analyze.py` works as a standalone CLI. Check `apps/backend/JSON_SCHEMA.md` before adding new analyzer output fields. Check `apps/backend/ARCHITECTURE.md` for the full HTTP flow and contract details.

**Phase 2 (`POST /api/phase2`):** Uploads audio to Gemini inline if ≤20MiB, or via the Gemini Files API if larger. Phase 1 JSON is appended to the system prompt from `prompts/phase2_system.txt`.

**Python version constraint:** Python 3.11.x required on macOS arm64. `basic-pitch` pulls `tensorflow-macos`/NumPy combinations that don't resolve on 3.12+. `requirements.txt` pins `setuptools<71` because `resampy 0.4.2` imports `pkg_resources`, which `setuptools>=71` no longer ships.

### Frontend (`apps/ui`)

Single-page React 19 + Vite + TypeScript + Tailwind CSS v4 app with no router. View states managed via React conditionals (upload → estimate → analysis → results). Vitest for unit tests, Playwright for smoke tests.

**Key service files:**

1. **`src/services/analysisRunsClient.ts`**: Typed transport for run-oriented APIs (create run, poll snapshots, fetch artifacts).
2. **`src/services/backendPhase1Client.ts`**: Legacy HTTP transport. Multipart POST, typed error classes (`BackendClientError`), `AbortController` timeouts, identity probe via `/openapi.json`.
3. **`src/services/backendPhase2Client.ts`**: Phase 2 transport to `/api/phase2`.
4. **`src/services/analyzer.ts`**: Phase orchestration entry point — sequences run creation, polling, and display payload projection.
5. **`src/types.ts`**: Source of truth for `Phase1Result`, `Phase2Result`, `AnalysisRunSnapshot`, and all backend response shapes.
6. **`src/config.ts`**: Runtime resolution of `VITE_API_BASE_URL` and feature flags; falls back to `http://127.0.0.1:8100`.

`AnalysisResults.tsx` (~45KB) is lazy-loaded via Suspense. Manual vendor chunks in `vite.config.ts` control bundle splitting.

### Frontend-Backend Contract

`Phase1Result` in `src/types.ts` and the `phase1` field in `BackendAnalyzeResponse` are the interface between apps. **Do not rename fields on either side without updating both.** Error envelopes always include `requestId`, `error.code`, `error.message`, `error.retryable`, and `diagnostics`.

## Environment Variables

```bash
# apps/ui/.env (copy from .env.example)
VITE_API_BASE_URL="http://127.0.0.1:8100"
VITE_ENABLE_PHASE2_GEMINI="true"

# Backend (env var, no .env file)
SONIC_ANALYZER_PORT=8100
GEMINI_API_KEY="your_key_here"  # read by server.py at runtime, not in browser bundle
```

Phase 2 is gated by `VITE_ENABLE_PHASE2_GEMINI`. `GEMINI_API_KEY` is backend-only.

## Key Guardrails

- **Backend contract:** `analyze.py` stdout → JSON only. `server.py` HTTP shapes → match `types.ts`. Read `apps/backend/ARCHITECTURE.md` and `apps/backend/JSON_SCHEMA.md` before changing analyzer output or HTTP responses.
- **Architecture strategy:** Read `docs/ARCHITECTURE_STRATEGY.md` before proposing structural changes to the dependency stack, transcription pipeline, or layer boundaries.
- **No linter/formatter:** No ESLint, Prettier, or Ruff configured. Follow the style of the surrounding code.
- **Backend tests use stdlib `unittest`**, not pytest. Frontend tests use Vitest in `node` environment (not jsdom).
- **`npm run lint`** only type-checks `src/`; test files and `playwright.config.ts` are excluded from `tsconfig.json`.
- **Canonical ports:** UI on 3100, backend on 8100. `./scripts/dev.sh` fails loudly if either port is occupied.
- **`--fast` flag** is currently a no-op in `analyze.py` but is forwarded through the HTTP API via form field or query param.
- **`dsp_json_override`** is accepted by the server but ignored.

## Backport Candidates

`BACKLOG.md` lists 12 DSP services + 2 data files from `active/sonic-architect-app` that are candidates for porting into ASA. Consult it before implementing genre detection, mix analysis, or synthesis features — implementations may already exist in that reference project.

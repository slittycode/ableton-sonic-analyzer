# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Full Stack

```bash
./scripts/dev.sh                    # Start both services (UI: 3100, backend: 8100)
```

`scripts/dev.sh` waits for the backend contract (`/openapi.json` with title `"Sonic Analyzer Local API"`) before launching the UI. It reads `apps/ui/.env` but overrides `VITE_API_BASE_URL` for the spawned process, so stale `.env` files pointing at `localhost:8000` won't break the stack.

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

Two-phase audio analysis system with a Python backend and React UI.

- **Phase 1 (local DSP):** Audio file → Python backend → structured metrics
- **Phase 2 (optional AI):** Phase 1 result + audio → backend `/api/phase2` → Gemini API → Ableton Live recommendations

### Backend (`apps/backend`)

**Two-file design:**

- **`analyze.py`** (~112KB): Pure DSP pipeline. Runs as a subprocess invoked by `server.py`. Extracts BPM, key, LUFS, stereo width, spectral balance, rhythm/melody detail, transcription (Basic Pitch), stem separation (Demucs). **Writes JSON to stdout, diagnostics to stderr** — this contract is load-bearing.
- **`server.py`** (~24KB): FastAPI HTTP wrapper. Accepts multipart uploads, invokes `analyze.py` as a subprocess, normalizes raw output into the `phase1` HTTP contract, returns structured JSON.

The subprocess isolation means `analyze.py` works as a standalone CLI. All raw analyzer fields are now forwarded through the HTTP `phase1` contract. Check `apps/backend/JSON_SCHEMA.md` before adding new analyzer output fields.

**Phase 2 (`POST /api/phase2`):** The backend uploads audio to Gemini inline if ≤20MiB, or via the Gemini Files API if larger. Phase 1 JSON is appended to the system prompt from `prompts/phase2_system.txt`.

**Python version constraint:** Python 3.11.x required on macOS arm64. `basic-pitch` pulls `tensorflow-macos`/NumPy combinations that don't resolve on 3.12+. `requirements.txt` also pins `setuptools<71` because `resampy 0.4.2` (pinned by `basic-pitch 0.4.0`) imports `pkg_resources`, which `setuptools>=71` no longer ships.

### Frontend (`apps/ui`)

Single-page React 19 app with no router. View states are managed via React conditionals (upload → estimate → analysis → results).

**Key service files:**

- **`src/services/backendPhase1Client.ts`**: All HTTP transport to the backend. Multipart POST, typed error classes (`BackendClientError`), `AbortController` timeouts (estimate: 30s, analyze: 600s+), identity probe via `/openapi.json`.
- **`src/services/backendPhase2Client.ts`**: Phase 2 transport to `/api/phase2`. Sends audio + Phase 1 JSON, receives Gemini advisory result.
- **`src/services/analyzer.ts`**: Phase orchestration entry point — sequences Phase 1, then conditionally Phase 2.
- **`src/types.ts`**: Source of truth for `Phase1Result`, `Phase2Result`, and all backend response shapes.
- **`src/config.ts`**: Runtime resolution of `VITE_API_BASE_URL` and feature flags; falls back to `http://127.0.0.1:8100`.

`AnalysisResults.tsx` (~45KB) is lazy-loaded via Suspense. Manual vendor chunks in `vite.config.ts` control bundle splitting (react, google-ai, waveform, midi).

### Frontend-Backend Contract

`Phase1Result` in `src/types.ts` and the `phase1` field in `BackendAnalyzeResponse` are the interface between apps. **Do not rename fields on either side without updating both.** Error envelopes always include `requestId`, `error.code`, `error.message`, `error.retryable`, and `diagnostics`. Read `apps/backend/ARCHITECTURE.md` before changing the HTTP shape.

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
- **No linter/formatter:** No ESLint, Prettier, or Ruff configured. Follow the style of the surrounding code.
- **Backend tests use stdlib `unittest`**, not pytest. Frontend tests use Vitest in `node` environment (not jsdom).
- **`npm run lint`** only type-checks `src/`; test files and `playwright.config.ts` are excluded from `tsconfig.json`.
- **Canonical ports:** UI on 3100, backend on 8100. `./scripts/dev.sh` fails loudly if either port is occupied.
- **`--fast` flag** is currently a no-op in `analyze.py` but is forwarded through the HTTP API via form field or query param.
- **`dsp_json_override`** is accepted by the server but ignored.

## Backport Candidates

`BACKLOG.md` lists 12 DSP services + 2 data files from `active/sonic-architect-app` that are candidates for porting into ASA. Consult it before implementing genre detection, mix analysis, or synthesis features — implementations may already exist in that reference project.

# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Scope

- Monorepo root for ASA (`apps/ui` + `apps/backend`).
- Root scripts/docs are authoritative for full-stack orchestration.
- App-specific implementation details live in:
  - `apps/ui/AGENTS.md`
  - `apps/backend/AGENTS.md`

## Canonical Commands

### Full stack (recommended)

```bash
./scripts/dev.sh
```

- Starts backend on `127.0.0.1:8100`, waits for expected OpenAPI contract (`Sonic Analyzer Local API`), then starts UI on `127.0.0.1:3100`.
- Reads `apps/ui/.env`, but enforces the spawned UI backend URL for synced local runs.

### Backend setup/run (`apps/backend`)

```bash
./apps/backend/scripts/bootstrap.sh
./apps/backend/venv/bin/python apps/backend/server.py
```

From `apps/backend`:

```bash
./scripts/bootstrap.sh
./venv/bin/python server.py
```

### Frontend setup/run (`apps/ui`)

```bash
cd apps/ui
npm install
npm run dev:local
```

### Verification

Frontend full gate:

```bash
cd apps/ui
npm run verify
```

Frontend targeted checks:

```bash
cd apps/ui
npm run lint
npm run build
npm test
```

Backend full tests:

```bash
cd apps/backend
./venv/bin/python -m unittest discover -s tests
```

Backend syntax check:

```bash
cd apps/backend
./venv/bin/python -m py_compile server.py
```

### Single-test commands

Frontend (Vitest):

```bash
cd apps/ui
npx vitest run tests/services/backendPhase1Client.test.ts
npx vitest run tests/services/backendPhase1Client.test.ts -t "accepts a valid backend payload"
```

Frontend (Playwright smoke spec):

```bash
cd apps/ui
npm run test:smoke -- tests/smoke/upload-phase1.spec.ts
```

Backend (single module/class/test):

```bash
cd apps/backend
./venv/bin/python -m unittest tests.test_server
./venv/bin/python -m unittest tests.test_server.ServerContractTests
./venv/bin/python -m unittest tests.test_server.ServerContractTests.test_analyze_endpoint_combines_separate_and_transcribe_in_subprocess
```

## High-level Architecture

### System model

- UI drives analysis as a staged run, not a single blocking call.
- Backend is authoritative for measurement (deterministic DSP).
- Symbolic extraction and AI interpretation are non-authoritative follow-on stages.

### Backend (`apps/backend`)

- `analyze.py` is the DSP engine/CLI (JSON on stdout contract).
- `server.py` is the FastAPI API surface and orchestration layer.
- `analysis_runtime.py` persists run state in SQLite (`.runtime/analysis_runs.sqlite3`) and artifacts on disk, with stage queues:
  - measurement
  - symbolic extraction
  - interpretation
- Stage snapshots and attempt history are first-class; frontend polls run state.
- Legacy `POST /api/analyze` and `POST /api/analyze/estimate` remain, but run-oriented endpoints (`/api/analysis-runs*`) are the canonical interface for staged execution.

### Frontend (`apps/ui`)

- `src/services/analysisRunsClient.ts` is the typed transport for run APIs.
- `src/services/analyzer.ts` orchestrates create-run + poll loop and projects display payloads.
- `src/types.ts` defines shared response contracts used across transport/UI.
- `src/App.tsx` manages stage UI state and uses estimate + run polling for progress UX.

### Contract boundaries to preserve

- Measurement result is authoritative; symbolic transcription is injected from symbolic stage (not copied from measurement payload).
- UI/backend contract is strict and strongly typed; if fields are renamed or moved, update both backend normalization and frontend types/parsers together.
- Error envelopes and stage statuses are part of the UI contract (not incidental).

## Repo-specific Constraints

- Canonical local ports: UI `3100`, backend `8100`.
- Backend bootstrap baseline is Python `3.11.x` (macOS arm64). Python `3.12+` is not supported for full-feature local bootstrap.
- No repo-wide ESLint/Prettier/Ruff baseline is enforced; follow surrounding file style.
- Before structural architecture changes (dependency stack, transcription pipeline, layer boundaries), read `docs/ARCHITECTURE_STRATEGY.md` first.

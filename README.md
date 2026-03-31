# asa

Local/dev monorepo for the Sonic Analyzer project.

This repo preserves the history of the existing UI and backend repos and brings
them together under one roof:

- `apps/ui` contains the React/Vite frontend
- `apps/backend` contains the Python/FastAPI local DSP backend
- `scripts/dev.sh` starts the full local stack on the canonical ports

Migration note:

- `apps/ui` and `apps/backend` were imported with history from the former standalone repos.
- The monorepo root is now the source of truth for release notes, local-stack commands, and push workflow.
- App-level changelogs remain imported app history rather than monorepo release history.
- App-specific editing and test guidance lives in `apps/ui/AGENTS.md` and `apps/backend/AGENTS.md`.

## Canonical Local Stack

- UI: `http://127.0.0.1:3100`
- backend: `http://127.0.0.1:8100`

## Canonical Runtime Flow

- `POST /api/analysis-runs/estimate`
- `POST /api/analysis-runs`
- `GET /api/analysis-runs/{run_id}`
- `GET /api/analysis-runs/{run_id}/artifacts...`

Runtime profiles:

- `local`: current local/dev mode with SQLite + local artifact files + in-process workers.
- `hosted`: hosted-service mode with auth hooks and worker separation boundaries.

In plain English: the analysis engine is still shared, but the repo now has an explicit split between local mode and hosted mode so public-hosting work does not have to change the local product path.

Artifact storage now sits behind a backend storage service boundary. In plain English: ASA still writes files locally today, but the code is no longer hard-wired to assume that every stored artifact is just a disk path on the same machine.

Implementation record:

- see `docs/PUBLIC_HOSTING_FOUNDATION.md` for the full summary of the hosted-foundation work, the follow-up fixes, the verification that was run, and the remaining work before any true public deployment.

Legacy `POST /api/analyze`, `POST /api/analyze/estimate`, and `POST /api/phase2` remain available only as temporary compatibility wrappers during the migration window.

## Local Setup

Frontend dependencies:

```bash
cd apps/ui
npm install
```

Backend environment:

```bash
./apps/backend/scripts/bootstrap.sh
```

The backend bootstrap path is verified on Python `3.11.x`. The bootstrap
script recreates `apps/backend/venv` from scratch and is the supported recovery
path if the local backend environment becomes stale or broken.

Manual equivalent:

```bash
cd apps/backend
python3.11 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

The backend dependency stack is pinned and validated on Python `3.11.x` for
full-feature local development on macOS arm64.

Current limitation: Python `3.12+` is not yet supported because Essentia
2.1b6 wheels are only published for 3.11 on macOS arm64.

Run the full stack from the repo root:

```bash
./scripts/dev.sh
```

### Phase 2 Local Setup

`./scripts/dev.sh` now reads `apps/ui/.env` before starting Vite. This is the
recommended persistent way to enable Gemini Phase 2 locally.

Persistent `.env` setup:

```bash
cd apps/ui
cp .env.example .env
```

Then set:

```bash
VITE_API_BASE_URL="http://127.0.0.1:8100"
VITE_ENABLE_PHASE2_GEMINI="true"
```

Optional hosted-mode request-header bootstrap for private beta testing:

```bash
VITE_API_REQUEST_HEADERS_JSON='{"X-ASA-User-Id":"beta-user-123"}'
```

Supported shell-based overrides:

```bash
export GEMINI_API_KEY="your_real_key_here"
./scripts/dev.sh
```

```bash
GEMINI_API_KEY="your_real_key_here" ./scripts/dev.sh
```

This does **not** work because the variable is not exported to the next
command:

```bash
GEMINI_API_KEY="your_real_key_here"
./scripts/dev.sh
```

Manual equivalent:

```bash
cd apps/backend
SONIC_ANALYZER_PORT=8100 ./venv/bin/python server.py
```

Hosted worker process:

```bash
cd apps/backend
SONIC_ANALYZER_RUNTIME_PROFILE=hosted SONIC_ANALYZER_PROCESS_ROLE=worker ./venv/bin/python worker.py
```

```bash
cd apps/ui
VITE_API_BASE_URL=http://127.0.0.1:8100 npm run dev:local
```

## Verification

Frontend:

```bash
cd apps/ui
npm run verify
```

Backend:

```bash
cd apps/backend
./venv/bin/python -m unittest discover -s tests
```

Canonical live end-to-end verification is local-only and requires a real audio file plus backend Gemini credentials:

```bash
TEST_FLAC_PATH=/path/to/track.flac \
GEMINI_API_KEY=your_real_key_here \
VITE_ENABLE_PHASE2_GEMINI=true \
./scripts/test-e2e.sh
```

## Release Position

The initial monorepo cut was **local/dev `v1.0.0`**. Current tags: `v1.2.0` (root), `ui-v1.6.0` (frontend).

The current quality bar is met for local development and iterative product work.
It should not be presented as a stronger production/security milestone until
authentication, stronger input hardening, and non-local artifact/database infrastructure are in place.

Keep the backend bootstrap limitation in mind when handing the repo to another machine:

- prefer Python `3.11.x`
- run `./apps/backend/scripts/bootstrap.sh` from the repo root before starting the local stack

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

Current limitation: Python `3.12+` is not a supported full-feature backend
bootstrap target on macOS arm64 because `basic-pitch` on Darwin pulls a
`tensorflow-macos` / NumPy combination that does not resolve cleanly.

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
VITE_GEMINI_API_KEY="your_real_key_here"
```

Supported shell-based overrides:

```bash
export VITE_GEMINI_API_KEY="your_real_key_here"
./scripts/dev.sh
```

```bash
VITE_GEMINI_API_KEY="your_real_key_here" ./scripts/dev.sh
```

This does **not** work because the variable is not exported to the next
command:

```bash
VITE_GEMINI_API_KEY="your_real_key_here"
./scripts/dev.sh
```

Manual equivalent:

```bash
cd apps/backend
SONIC_ANALYZER_PORT=8100 ./venv/bin/python server.py
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

## Release Position

The initial monorepo cut was **local/dev `v1.0.0`**. Current tags: `v1.2.0` (root), `ui-v1.6.0` (frontend).

The current quality bar is met for local development and iterative product work.
It should not be presented as a stronger production/security milestone until
Gemini access is moved out of the browser bundle.

Keep the backend bootstrap limitation in mind when handing the repo to another machine:

- prefer Python `3.11.x`
- run `./apps/backend/scripts/bootstrap.sh` from the repo root before starting the local stack

# ableton-sonic-analyzer

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

This monorepo is being cut as a **local/dev `v1.0.0`** baseline.

The current quality bar is met for local development and iterative product work.
It should not be presented as a stronger production/security milestone until
Gemini access is moved out of the browser bundle.

## Push Checklist

```bash
git remote add origin <new-repo-url>
git push -u origin main
git push origin v1.0.0
```

Keep the backend bootstrap limitation in mind when handing the repo to another machine:

- prefer Python `3.11.x`
- run `./apps/backend/scripts/bootstrap.sh` from the repo root before starting the local stack

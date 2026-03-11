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
cd apps/backend
python3.13 -m venv venv
./venv/bin/pip install -r requirements.txt
```

The backend dependency stack is currently verified on Python `3.13.x` for local
development. A fresh `3.14.x` environment is not a supported bootstrap target
for this `v1.0.0` cut.

Current limitation: the backend dependency set is still under-constrained enough
that some clean `pip install -r requirements.txt` runs can backtrack into an
older NumPy/basic-pitch build path and fail. The existing backend repo's
pre-provisioned Python `3.13.x` environment remains the known-good local setup
until those pins are tightened in a follow-up pass.

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

- prefer Python `3.13.x`
- expect follow-up dependency pinning work in `apps/backend/requirements.txt`

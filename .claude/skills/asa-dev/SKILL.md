---
name: asa-dev
description: Use this skill when the user wants to start ASA's full development stack (frontend + backend together) and says "start asa", "run asa locally", "/asa-dev", "bring asa up", "spin up the dev server", or asks to launch ASA for local testing. Runs preflight checks (Python 3.11, venv, npm deps, ports 3100/8100 free, .env wiring) BEFORE invoking scripts/dev.sh, and routes specific failure modes to specific fixes instead of dumping cryptic stack traces.
version: 0.1.0
---

# ASA Dev Launcher (Guarded)

## Purpose

`scripts/dev.sh` is the canonical entry point for the full ASA stack — it starts the backend on 8100, waits for the OpenAPI contract, and then launches the UI on 3100. The script already does some preflight, but new contributors (and AI agents) hit the same setup gaps repeatedly: missing venv, missing `node_modules`, occupied ports, stale `.env.local` files. This skill front-runs those checks so the failure mode is named, not mysterious.

## When to use

- The user wants ASA running and asks for it ("start asa", "/asa-dev", "bring up the dev environment").
- An AI agent has been asked to do work that requires a live ASA instance (e.g., smoke-testing a UI change end-to-end).
- After a fresh clone, or after `git pull` brought in dependency changes.

**Do NOT use** for: single-process invocations (`python analyze.py <file>`), running tests (use `asa-verify`), or background CI work.

## Procedure

### Step 1 — Locate the repo

Default to `~/code/projects/asa`. If the user is in a different working directory and clearly wants ASA, confirm before continuing.

### Step 2 — Run preflight checks in order

Stop at the first failure and route the user to the fix. Do NOT auto-fix — these checks gate real environmental decisions.

#### 2a. Python 3.11.x available

```bash
python3.11 --version 2>/dev/null || python3 --version
```

The Python version constraint is load-bearing — Essentia 2.1b6 wheels are only published for 3.11 on macOS arm64. If neither `python3.11` is on PATH nor `python3 --version` reports 3.11.x:

- **Fix:** Install Python 3.11.x (typically via `brew install python@3.11`).
- Do not attempt to run the backend with Python 3.12+ — `apps/backend/scripts/bootstrap.sh` will fail.

#### 2b. Backend venv exists

```bash
test -x ~/code/projects/asa/apps/backend/venv/bin/python && \
  ~/code/projects/asa/apps/backend/venv/bin/python --version
```

- If the venv is missing or the Python inside it is not 3.11.x:
  **Fix:** Run `~/code/projects/asa/apps/backend/scripts/bootstrap.sh` (must be invoked from inside `apps/backend/`). Bootstrap is destructive (recreates the venv) — ask the user before running.

#### 2c. Frontend `node_modules` exists

```bash
test -d ~/code/projects/asa/apps/ui/node_modules && \
  test -f ~/code/projects/asa/apps/ui/node_modules/.package-lock.json
```

- If missing or stale:
  **Fix:** `npm --prefix ~/code/projects/asa/apps/ui install`. Ask before running (npm install can be slow).

#### 2d. Ports 3100 and 8100 are free

```bash
lsof -nP -iTCP:3100 -sTCP:LISTEN
lsof -nP -iTCP:8100 -sTCP:LISTEN
```

- If anything is listening on 3100, identify the process (name + PID).
- If anything is listening on 8100, same.
- **Two common cases:**
  1. **A stale ASA backend or UI** from a previous run — kill with `kill <PID>` after confirming with the user.
  2. **Something unrelated** (another dev server, a system service) — abort and let the user decide. Do not kill blindly.

The canonical ports are baked in: UI on 3100, backend on 8100 (or `SONIC_ANALYZER_PORT`). `scripts/dev.sh` fails loudly if they're occupied — better to surface that here with the process identified.

#### 2e. UI `.env` is sane

```bash
cat ~/code/projects/asa/apps/ui/.env 2>/dev/null
```

Check:
- File exists. If missing, copy from `.env.example` and proceed.
- `VITE_API_BASE_URL` is set. `scripts/dev.sh` overrides this for the spawned process to point at the local backend, but a stale file with a hosted URL can still confuse later builds. Surface the value to the user.
- `VITE_ENABLE_PHASE2_GEMINI` — if `true`, the user should know that Phase 2 calls will need `GEMINI_API_KEY` set in the backend environment. Mention it.

### Step 3 — Launch

If all preflight passes:

```bash
cd ~/code/projects/asa && ./scripts/dev.sh
```

This is a long-running foreground process. Run it in the foreground (NOT background) so the user sees the logs and can Ctrl-C it. Do not wrap it in `nohup` or `&`.

### Step 4 — Confirm it came up

The user will see `dev.sh`'s own output, including:
- Backend startup banner
- OpenAPI contract check passing
- UI startup (Vite reporting `Local:   http://127.0.0.1:3100`)

If you're verifying from outside the terminal, wait 8–10 seconds and check:

```bash
curl -fsS http://127.0.0.1:8100/openapi.json | jq -r '.info.title'
# expected: Sonic Analyzer Local API
curl -fsS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3100
# expected: 200
```

## Failure modes — fast routing

| Symptom | Likely cause | Fix |
|---|---|---|
| `python3.11: command not found` | Python 3.11 not installed | `brew install python@3.11` |
| `Missing required command: jq` (from dev.sh) | jq not installed | `brew install jq` |
| `Address already in use: 8100` | Stale backend | `lsof -nP -iTCP:8100 -sTCP:LISTEN` → `kill <PID>` |
| `ModuleNotFoundError: essentia` | Venv broken or wrong Python | `apps/backend/scripts/bootstrap.sh` (run from `apps/backend/`) |
| `Vite reports the wrong API URL` | Stale `apps/ui/.env` overriding | confirm what `dev.sh` is exporting; clear stale `.env` |
| UI 200s but `/api/analyze` 502s | Backend is up but errored | tail backend stderr; check `GEMINI_API_KEY` if Phase 2 was attempted |
| OpenAPI title is wrong | Someone changed `server.py` title | revert or update the contract probe expectations in `asa-verify` |

## Gotchas

- **`scripts/dev.sh` overrides `VITE_API_BASE_URL`** for the spawned UI process. A stale value in `apps/ui/.env` won't break the dev session but *will* break `npm run build` if used as-is. If the user reports "production-like behavior" surprises after `dev.sh`, check `.env`.
- **`SONIC_ANALYZER_PORT` is honored by `dev.sh`** but not by every script. If the user is on a non-default port, mention it explicitly in the report so they don't get confused later.
- **Bootstrap is destructive** — it recreates the venv from scratch. Always ask first.
- **AI agents in restricted shells:** if you cannot run interactive long-lived processes, run `dev.sh` in background mode and tell the user where to watch the logs — but explicitly note that interrupting it requires killing the PID.

## After launch

Do not start coding or testing immediately. Wait for the user to confirm:
- The UI is accessible at http://127.0.0.1:3100
- The backend is responsive at http://127.0.0.1:8100

If they want to verify with a real upload, point them at `apps/ui/tests/fixtures/` (if it exists) for a small sample file, or let them drop in their own.

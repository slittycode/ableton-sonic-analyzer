# Local Setup

Full setup, environment variables, and verification details for ASA. For a
30-second overview, see the root [`README.md`](../README.md).

> **FROZEN 2026-07 (trust diet):** hosted runtime profile is a non-goal. Local is
> the product. Do not expand hosted deployment without the owner naming that
> subsystem. See `plans/trust-diet-2026-07.md`.

## Prerequisites

- **Python `3.11.x`** — Essentia 2.1b6 wheels are only published for 3.11.
  Python 3.12+ is not yet supported.
- **Node.js 20+**.
- macOS arm64 is the validated platform; Linux works for most paths.

## Backend

```bash
./apps/backend/scripts/bootstrap.sh
```

`bootstrap.sh` recreates `apps/backend/venv` from scratch. It is also the
supported recovery path if the local backend environment becomes stale.

Manual equivalent:

```bash
cd apps/backend
python3.11 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

## Frontend

```bash
cd apps/ui
npm install
```

## Full stack

Install the `asa` CLI once (`./bin/asa install`, symlinks into `~/.local/bin`), then start
everything with a single command (`asa` wraps `./scripts/dev.sh`, which still works directly):

```bash
asa
```

This boots backend on `127.0.0.1:8100` and UI on `127.0.0.1:3100`. It waits
for the backend `/openapi.json` contract before launching Vite, and overrides
`VITE_API_BASE_URL` for the spawned UI process so stale `apps/ui/.env` files
don't break the stack.

## Phase 2 (Gemini) setup

Phase 2 is gated by `VITE_ENABLE_PHASE2_GEMINI`. The Gemini API key is
backend-only — it never reaches the browser bundle.

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

Backend Gemini key — must be exported in the same shell that runs `dev.sh`:

```bash
export GEMINI_API_KEY="your_real_key_here"
./scripts/dev.sh
```

Inline on a single command line also works:

```bash
GEMINI_API_KEY="your_real_key_here" ./scripts/dev.sh
```

This does **not** work (the variable is not exported to the next command):

```bash
GEMINI_API_KEY="your_real_key_here"
./scripts/dev.sh
```

## Running services individually

Backend only (`asa backend`, or directly):

```bash
cd apps/backend
SONIC_ANALYZER_PORT=8100 ./venv/bin/python server.py
```

Hosted worker process:

```bash
cd apps/backend
SONIC_ANALYZER_RUNTIME_PROFILE=hosted SONIC_ANALYZER_PROCESS_ROLE=worker \
  ./venv/bin/python worker.py
```

UI only (`asa frontend`, or directly):

```bash
cd apps/ui
VITE_API_BASE_URL=http://127.0.0.1:8100 npm run dev:local
```

## Verification

Run both gates at once with `asa verify` (or narrow: `asa verify backend` /
`asa verify frontend`). The underlying gates still work directly:

Frontend gate:

```bash
cd apps/ui
npm run verify   # lint + test:unit + build + test:smoke
```

Backend tests:

```bash
cd apps/backend
./venv/bin/python -m unittest discover -s tests
```

Local end-to-end (boots the real backend, drives the UI against canonical
`/api/analysis-runs` routes, no Gemini credentials required):

```bash
./scripts/test-e2e-integration.sh
```

Full live Gemini end-to-end (requires a real audio file and backend Gemini
credentials):

```bash
TEST_FLAC_PATH=/path/to/track.flac \
GEMINI_API_KEY=your_real_key_here \
VITE_ENABLE_PHASE2_GEMINI=true \
./scripts/test-e2e.sh
```

## Upload limits

The backend distinguishes between:

- raw audio limit: **100 MiB**
- HTTP request envelope limit: **101 MiB**

The audio file itself must stay at or below 100 MiB; the whole multipart
request is allowed to be slightly larger so filenames and form wrapping don't
cause false `413` errors.

The canonical operator view is generated from backend code:

```bash
cd apps/backend
./venv/bin/python scripts/render_upload_limit_contract.py
```

If you put the local stack behind a reverse proxy or load balancer, mirror the
generated `101 MiB` request-body limit on the protected upload routes rather
than copying numbers from old docs.

## Runtime profiles

The backend supports two profiles, selected via `SONIC_ANALYZER_RUNTIME_PROFILE`
(`local` | `hosted`) and `SONIC_ANALYZER_PROCESS_ROLE` (`all` | `api` | `worker`):

- **`local`** — SQLite + local artifact files + in-process workers. Default for development.
- **`hosted`** — Adds auth-context resolution and worker-process separation. The local product path is unaffected.

Implementation record for the hosted foundation (archived):
[`docs/history/public-hosting-foundation-2026-04-01.md`](history/public-hosting-foundation-2026-04-01.md).

## Release position

The current local quality bar is met for local development and iterative
product work. It should not be presented as a stronger production/security
milestone until authentication, stronger input hardening, and non-local
artifact/database infrastructure are in place.

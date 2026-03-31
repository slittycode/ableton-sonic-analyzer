# ASA Public Hosting Foundation

_Last updated: 2026-04-01_

## Why this work exists

ASA was built as a local-first tool. That was fine for development, but it meant the code implicitly assumed:

- the backend and worker logic lived in one process
- artifacts were local files on the same machine
- run state lived in local SQLite only
- the browser talked to a localhost API
- there was no concept of per-user ownership for runs

That shape is acceptable for local development, but it is not a safe base for public hosting.

In plain English: this work does **not** make ASA production-hosted yet. What it does is prepare the codebase so ASA can eventually be hosted publicly without breaking the current local app.

## Goals

- Keep the analysis engine shared between local and hosted usage.
- Preserve the current local workflow as a first-class path.
- Add explicit hosted-mode boundaries so future cloud work does not leak into the local happy path.
- Remove public API assumptions that would be unsafe in a hosted environment.

## Non-goals

This work does **not** yet provide:

- real cloud object storage
- real PostgreSQL persistence
- real queue infrastructure
- real identity provider token validation
- rate limiting, quota enforcement, or billing protection
- production deployment manifests

In plain English: the code is now shaped correctly for those systems, but those external systems are still future work.

## What was implemented

### 1. Explicit runtime profiles

Files:

- `apps/backend/runtime_profile.py`
- `apps/backend/server.py`
- `apps/backend/worker.py`
- `apps/ui/src/config.ts`

Implemented:

- Added explicit backend runtime profiles: `local` and `hosted`.
- Added explicit backend process roles: `all`, `api`, and `worker`.
- Kept `local` as the default profile.
- Kept the existing local behavior as the default local process role.
- Made hosted API startup and hosted worker startup separable.
- Added frontend runtime-profile handling so hosted builds do not depend on localhost fallback behavior.

In plain English:

- Local mode still behaves like the current app.
- Hosted mode now has its own switch, so future hosting work does not have to mutate the local runtime path.

### 2. Dedicated worker process boundary

Files:

- `apps/backend/server.py`
- `apps/backend/worker.py`
- `apps/backend/tests/test_cleanup.py`
- `apps/backend/tests/test_runtime_profile.py`

Implemented:

- Extracted background-task startup into a reusable helper.
- Added a dedicated `worker.py` entrypoint for background stage execution.
- In hosted mode, the API process no longer starts in-process workers by default.
- Recovery of incomplete attempts is now restricted to the worker role in hosted mode.

Why this matters:

- A hosted API process should serve HTTP and enqueue or observe work.
- A hosted worker process should own long-running analysis work and restart recovery.

In plain English:

- Restarting the web server no longer pretends to be a worker.
- Background jobs now have a clean process boundary, which is required before real queue infrastructure can be introduced.

### 3. Hosted auth and run ownership groundwork

Files:

- `apps/backend/auth_context.py`
- `apps/backend/server.py`
- `apps/backend/analysis_runtime.py`
- `apps/backend/tests/test_server.py`
- `apps/backend/tests/test_analysis_runtime.py`

Implemented:

- Added hosted-mode user-context resolution from request headers.
- Added `owner_user_id` to `analysis_runs`.
- Backfilled older local rows to a local development owner.
- Enforced ownership checks on canonical run routes.
- Added hosted-mode authentication-required behavior.
- Added a delete-run endpoint: `DELETE /api/analysis-runs/{run_id}`.

Current hosted auth contract:

- hosted mode requires `X-ASA-User-Id`
- local mode continues to use a local development user context automatically

Important limitation:

- this is a hosting foundation hook, not final production auth
- there is not yet token verification against a real identity provider

In plain English:

- ASA now knows which user owns which hosted run.
- One hosted user can no longer read or interrupt another user’s run through the canonical API.

### 4. Public artifact contract cleanup

Files:

- `apps/backend/analysis_runtime.py`
- `apps/backend/server.py`
- `apps/ui/src/types.ts`
- `apps/ui/src/services/analysisRunsClient.ts`
- related frontend fixtures and tests

Implemented:

- Removed internal filesystem `path` values from the public run snapshot contract.
- Split artifact access into:
  - public artifact metadata for API responses
  - internal artifact records for server-side file operations
- Updated frontend transport parsing to stop expecting `path` in shared API payloads.

Why this matters:

- Returning internal disk paths in a hosted API is unsafe and incorrect.
- Hosted storage will eventually use object-store references or signed access instead of local paths.

In plain English:

- The browser now gets only the information it should have.
- The server keeps the internal storage details to itself.

### 5. Artifact storage boundary

Files:

- `apps/backend/artifact_storage.py`
- `apps/backend/analysis_runtime.py`
- `apps/backend/server.py`
- `apps/backend/tests/test_analysis_runtime.py`

Implemented:

- Introduced an artifact storage abstraction.
- Added the current filesystem implementation as the default storage backend.
- Updated runtime artifact writes to go through that abstraction instead of writing files inline at each call site.
- Added helpers for resolving whether a stored artifact is available as a local file.
- Updated measurement, pitch-note, interpretation, download, and spectral generation paths to use the runtime storage boundary.

Why this matters:

- Local filesystem storage still works.
- The code is now structurally prepared for a future object-storage backend.

In plain English:

- ASA still saves files on disk today.
- The code no longer assumes disk is the only possible storage system forever.

### 6. Frontend hosted request plumbing

Files:

- `apps/ui/src/config.ts`
- `apps/ui/src/vite-env.d.ts`
- `apps/ui/.env.example`
- `apps/ui/src/services/analysisRunsClient.ts`
- `apps/ui/src/services/backendPhase1Client.ts`
- `apps/ui/src/services/spectralArtifactsClient.ts`
- `apps/ui/tests/services/config.test.ts`

Implemented:

- Added `VITE_RUNTIME_PROFILE`.
- Added `VITE_API_REQUEST_HEADERS_JSON`.
- Added shared request-header injection from runtime config.
- Applied configured hosted headers across:
  - canonical run requests
  - backend identity probing
  - multipart estimate/create requests
  - spectral artifact fetches
- Changed hosted API-base fallback to use the current web origin instead of localhost.

Why this matters:

- Hosted mode needs a clean way to pass auth-related headers or private-beta routing metadata.
- Browser code should not accidentally assume the API lives on `127.0.0.1`.

In plain English:

- The frontend can now talk to a hosted backend without silently dropping the headers that identify the user.

### 7. Hosted spectrogram image loading fix

Files:

- `apps/ui/src/services/spectralArtifactsClient.ts`
- `apps/ui/src/components/SpectrogramViewer.tsx`
- `apps/ui/tests/services/spectralArtifactsClient.test.ts`

Implemented:

- Added authenticated blob fetching for artifact images.
- Updated the spectrogram viewer to use direct URLs when no request headers are configured.
- Updated the spectrogram viewer to use fetched object URLs when hosted-mode headers are present.

Why this matters:

- Plain `<img src="...">` loads cannot carry custom auth headers.
- Hosted/private-beta artifact access needs an authenticated fetch path.

In plain English:

- Spectrogram images still load locally the simple way.
- In hosted mode, they now load in a way that can respect auth headers.

### 8. Local-mode preservation

Files touched across backend and frontend.

Preserved intentionally:

- `./scripts/dev.sh`
- local UI on `127.0.0.1:3100`
- local backend on `127.0.0.1:8100`
- local SQLite runtime
- local filesystem artifact storage
- existing local-first workflow and canonical dev defaults

Design rule enforced by this work:

- hosted-only concerns must be isolated behind runtime-profile boundaries
- local mode must not require new cloud infrastructure

In plain English:

- this work was specifically designed so the current local app keeps working
- the hosted prep should not slow down or complicate normal local development

## Verification completed

Backend:

- `cd apps/backend && ./venv/bin/python -m py_compile analysis_runtime.py artifact_storage.py auth_context.py runtime_profile.py server.py worker.py`
- `cd apps/backend && ./venv/bin/python -m unittest tests.test_analysis_runtime tests.test_cleanup tests.test_server`
- `cd apps/backend && ./venv/bin/python -m unittest discover -s tests`
- focused follow-up checks:
  - `cd apps/backend && ./venv/bin/python -m unittest tests.test_server tests.test_cleanup tests.test_runtime_profile`

Frontend:

- `cd apps/ui && npx vitest run tests/services/analysisRunsClient.test.ts tests/services/analyzer.test.ts tests/services/diagnosticLogs.test.ts`
- `cd apps/ui && npm run test:unit`
- `cd apps/ui && npm run build`
- focused follow-up checks:
  - `cd apps/ui && npm run lint`
  - `cd apps/ui && npm run test -- --run tests/services/config.test.ts tests/services/spectralArtifactsClient.test.ts tests/services/analysisRunsClient.test.ts`

Results:

- backend full suite passed
- frontend targeted service tests passed
- frontend production build passed
- follow-up hosted-mode regression checks passed

## Remaining work before real public hosting

These are still intentionally unresolved:

- swap the current local runtime persistence for a real hosted persistence adapter such as PostgreSQL
- swap filesystem artifact storage for real object storage
- add real hosted upload creation and signed-upload flow
- replace header-based hosted identity hooks with verified user tokens
- add queue infrastructure for hosted workers
- add rate limiting, quotas, abuse protection, and billing guardrails
- add observability, alerting, and retention policy enforcement

In plain English:

- the codebase is now ready for those next steps
- it is not yet claiming they already exist

## Practical reading guide

If you want the shortest possible overview:

- read this file first
- then read `README.md`

If you want the backend implementation details:

- `apps/backend/runtime_profile.py`
- `apps/backend/auth_context.py`
- `apps/backend/artifact_storage.py`
- `apps/backend/analysis_runtime.py`
- `apps/backend/server.py`
- `apps/backend/worker.py`

If you want the frontend hosted-mode changes:

- `apps/ui/src/config.ts`
- `apps/ui/src/services/analysisRunsClient.ts`
- `apps/ui/src/services/backendPhase1Client.ts`
- `apps/ui/src/services/spectralArtifactsClient.ts`
- `apps/ui/src/components/SpectrogramViewer.tsx`

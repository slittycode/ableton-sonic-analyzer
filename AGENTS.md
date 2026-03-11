# AGENTS.md

## Scope

- This file applies to the monorepo root.
- The repo contains:
  - `apps/ui`: React/Vite frontend
  - `apps/backend`: Python/FastAPI local DSP backend
- Root docs and scripts are the source of truth for release workflow and local stack orchestration.

## Working Style

- Prefer making root-level release, workflow, and orchestration changes here rather than duplicating policy across imported app docs.
- Preserve imported app histories and app-local changelogs.
- Treat the monorepo root as the entrypoint for development, verification, and release prep.

## Main Commands

- Full local stack from repo root:

```bash
./scripts/dev.sh
```

- Frontend verification:

```bash
cd apps/ui
npm run verify
```

- Backend verification:

```bash
cd apps/backend
./venv/bin/python -m unittest discover -s tests
```

## Release Notes

- The monorepo tag `v1.0.0` is a root release marker.
- App-level changelogs remain app-local history and should not be rewritten to mirror the root tag.
- This release is local/dev only until Gemini access moves out of the browser.

## Known Gotchas

- The canonical local stack is UI `3100` and backend `8100`.
- `apps/backend/requirements.txt` is not yet fully pinned for reproducible fresh bootstrap in all environments.
- Root docs should be preferred over imported app docs when release messaging conflicts.


# AGENTS.md

## Scope

- This file applies to the monorepo root.
- The repo contains:
  - `apps/ui`: React/Vite frontend
  - `apps/backend`: Python/FastAPI local DSP backend
- Root docs and scripts are the source of truth for release workflow and local stack orchestration.
- App-local implementation rules live in `apps/ui/AGENTS.md` and `apps/backend/AGENTS.md`.

## Working Style

- Prefer making root-level release, workflow, and orchestration changes here rather than duplicating policy across imported app docs.
- Preserve imported app histories and app-local changelogs.
- Treat the monorepo root as the entrypoint for development, verification, and release prep.
- Start here for stack-wide work, then switch to the app-local AGENTS file for app-specific editing and testing guidance.
- Before proposing structural changes to the architecture, dependency stack, or transcription pipeline, read `docs/ARCHITECTURE_STRATEGY.md`. It records why the current design is shaped the way it is, the dependency health verdicts, and the planned experiment sequence. It is a living document — update it when experiments produce results.

## Main Commands

- Backend bootstrap from the repo root:

```bash
./apps/backend/scripts/bootstrap.sh
```

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

- The monorepo root tag `v1.0.0` was the initial release marker. Current tags: `v1.2.0` (root), `ui-v1.6.0` (frontend).
- App-level changelogs remain app-local history and should not be rewritten to mirror the root tag.
- This release is local/dev only until Gemini access moves out of the browser.

## Known Gotchas

- The canonical local stack is UI `3100` and backend `8100`.
- Full-feature backend bootstrap is pinned and validated on Python `3.11.x` for macOS arm64.
- Python `3.12+` is not a supported full-feature backend bootstrap target on macOS arm64 because `basic-pitch` pulls a Darwin `tensorflow-macos` / NumPy combination that does not resolve cleanly.
- Root docs should be preferred over imported app docs when release messaging conflicts.

# Changelog

All notable changes to `ableton-sonic-analyzer` are documented here.

## v1.1.0

- Standardized full-feature backend bootstrap on Python `3.11.x` for macOS arm64 and documented the `3.12+` Darwin limitation across all root and backend docs.
- Added `apps/backend/scripts/bootstrap.sh` — requires `python3.11`, creates the backend venv, upgrades pip, and installs the pinned stack.
- Replaced the loose backend dependency list with the validated Python 3.11 frozen lock set in `apps/backend/requirements.txt`.
- Updated `scripts/dev.sh` so a missing backend venv error points directly to `./apps/backend/scripts/bootstrap.sh`.
- Added `apps/backend/tests/test_bootstrap_scripts.py` covering the missing-interpreter and missing-venv failure paths.
- Closed the `v1.0.0` known limitation: fresh backend bootstrap is now reproducible from a clean Python 3.11 install.

## v1.0.0

- Cut the first monorepo release and preserved the imported history of the former UI and backend repos under:
  - `apps/ui`
  - `apps/backend`
- Established the monorepo root as the source of truth for local development, verification, and release notes.
- Standardized the canonical local stack on:
  - UI `http://127.0.0.1:3100`
  - backend `http://127.0.0.1:8100`
- Added the root `scripts/dev.sh` launcher for the full local stack.
- Kept app-level changelog history intact inside the imported apps rather than rewriting their release history to match the monorepo tag.

Known limitations for this `v1.0.0` cut:

- Gemini access is still browser-held, so this is a local/dev release, not a stronger production/security milestone.
- Fresh backend bootstrap from raw `apps/backend/requirements.txt` is still under-constrained and may require follow-up dependency pinning.


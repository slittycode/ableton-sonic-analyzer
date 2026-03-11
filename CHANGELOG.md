# Changelog

All notable changes to `ableton-sonic-analyzer` are documented here.

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


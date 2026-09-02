---
description: Backend/DSP change checklist (contracts + tripwires)
---

You are changing ASA **backend / Phase 1 / Phase 2** code.

## Before edits

1. Read `apps/backend/AGENTS.md` and the contract sections of `CLAUDE.md`.
2. If changing measurements or stdout shape: open `apps/backend/JSON_SCHEMA.md`.
3. If changing HTTP shapes: open `apps/ui/src/types.ts` / backend client types.

## Tripwires (do not violate)

1. `print(...)` in `analyze.py` path must use `file=sys.stderr` — stdout is JSON only.
2. Subprocess `analyze.py` calls need `--yes`.
3. New top-level analyzer keys → update `EXPECTED_TOP_LEVEL_KEYS` + schema + UI types.
4. Phase 2 text must cite Phase 1 paths; no invented devices outside Live 12 catalog.
5. Artifacts via `artifact_storage.py`, not hard-coded paths.

## Task

${1:-Describe the backend change and implement the smallest safe fix with tests.}

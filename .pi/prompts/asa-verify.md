---
description: Pre-ship ASA verification (frontend + backend + contracts)
---

Run ASA verification before claiming the change is done.

## Scope

${1:-whatever is dirty in git related to this task}

## Procedure

1. `git status -sb` and identify touched surfaces (UI / backend / both / docs-only).
2. Prefer the project skill `/skill:asa-verify` if available; otherwise:
   1. Frontend (if `apps/ui` touched): `cd apps/ui && npm run verify`
   2. Backend (if `apps/backend` touched):  
      `./apps/backend/venv/bin/python -m unittest discover -s apps/backend/tests`
   3. Or full: `asa verify` if the CLI is on PATH
3. If analyzer stdout / HTTP envelope / `types.ts` changed: re-check
   `JSON_SCHEMA.md`, `EXPECTED_TOP_LEVEL_KEYS`, and matching frontend types.
4. Report per layer: pass/fail + failing test name (no “should be fine”).

Do not ship with failing verify unless the human explicitly accepts a partial.

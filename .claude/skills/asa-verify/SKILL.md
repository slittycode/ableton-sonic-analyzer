---
name: asa-verify
description: Use this skill when the user wants to verify ASA before commit or merge, says "verify asa", "/asa-verify", "run all the tests", "is asa green", "make sure i didn't break anything", or after a meaningful code change to apps/backend or apps/ui. Orchestrates the full ASA test pipeline — frontend lint+unit+build+smoke, backend unittest discover, and an optional contract probe — and isolates failures to a specific layer and test name.
version: 0.1.0
---

# ASA Full-Stack Verifier

## Purpose

ASA has three test surfaces that must all pass before a change is safe: the frontend verify pipeline, the backend `unittest` suite, and the HTTP contract (the schema the UI relies on). This skill runs them in order, aggregates pass/fail per layer, and on failure surfaces the failing test name plus one line of relevant output — replacing "did I run all the things?" guesswork.

## When to use

- Pre-commit / pre-push, after any change touching `apps/backend/`, `apps/ui/`, or `apps/backend/prompts/`.
- Before merging a worktree branch.
- When the user asks "is asa green", "run all asa tests", "/asa-verify", "verify before i ship".
- When debugging a regression and you need to know which layer (UI, backend, contract) broke.

## Procedure

### Step 1 — Confirm working tree state

Print the current branch and a one-line dirty/clean status from `git -C ~/code/projects/asa status --porcelain | head -5`. This goes into the report so the user knows what they verified.

### Step 2 — Frontend verify pipeline

```bash
npm --prefix ~/code/projects/asa/apps/ui run verify
```

`npm run verify` is the canonical aggregate. Composition (from `apps/ui/package.json`):

1. `npm run lint` — `tsc --noEmit` (TypeScript type-check; no ESLint/Prettier are configured)
2. `npm run test:unit` — `vitest run tests/services`
3. `npm run build` — `vite build`
4. `npm run test:smoke` — Playwright smoke tests (stubbed backend + Gemini)

If `verify` fails, **do not fall back to the sub-commands silently** — the failing sub-step is informative. Capture the first failing step's name and the failing test/error line.

### Step 3 — Backend test suite

```bash
~/code/projects/asa/apps/backend/venv/bin/python -m unittest discover -s ~/code/projects/asa/apps/backend/tests
```

Backend uses stdlib `unittest`, not pytest. If the venv doesn't exist, surface that as a setup failure — point the user at `~/code/projects/asa/apps/backend/scripts/bootstrap.sh` (must be invoked from `apps/backend/`; do not auto-run; bootstrap recreates the venv and the user should approve).

On failure, parse the unittest output for the line beginning `FAIL: ` or `ERROR: ` followed by the test path (e.g., `FAIL: test_analyze_endpoint_combines_separate_and_transcribe (tests.test_server.ServerContractTests)`). Quote that line plus the first 2–3 lines of the traceback.

### Step 4 — Contract probe (optional but recommended)

This is light — skip if both Step 2 and Step 3 already passed and the user is in a hurry. Run if the user explicitly asked, or if changes touched `apps/backend/server.py`.

1. Check port 8100 is free: `lsof -nP -iTCP:8100 -sTCP:LISTEN`. If occupied by anything other than an ASA backend, abort the probe.
2. Start the backend in the background: `~/code/projects/asa/apps/backend/venv/bin/python ~/code/projects/asa/apps/backend/server.py &` (background mode).
3. Wait up to 10 seconds for `/openapi.json` to respond: `curl -fsS http://127.0.0.1:8100/openapi.json | jq -r '.info.title'`.
4. Confirm the title is exactly `Sonic Analyzer Local API`.
5. Kill the backend (`kill %1` or the captured PID).

A contract probe failure means `server.py` is producing the wrong OpenAPI document — that's a real bug.

### Step 5 — Aggregate and report

Output format:

```
ASA verify on <branch> (<clean|dirty: N files>)

[1/3] Frontend verify ......... <PASS in 42s | FAIL at step: test:unit>
[2/3] Backend unittest ........ <PASS, 187 tests in 31s | FAIL: tests.test_server.ServerContractTests.test_x>
[3/3] Contract probe .......... <PASS | SKIPPED | FAIL: openapi title was "X" expected "Sonic Analyzer Local API">

Result: PASS | FAIL

<If FAIL: first failing step's most relevant output line(s), max 5 lines>
```

### Step 6 — On failure, route the user

For each failure mode, suggest the next step:

- **lint failure (tsc):** name the file and the first error. Suggest `npx tsc --noEmit -p apps/ui` to iterate.
- **test:unit failure:** name the failing test and suggest `npx --prefix apps/ui vitest run -t "<test name>"` to focus.
- **build failure:** likely Vite/TS error or import path issue; suggest reading the first error and the file it points at.
- **test:smoke failure:** Playwright failures often need `npm --prefix apps/ui run test:smoke -- --reporter=list <spec-file>` and the trace flag. Suggest that.
- **backend unittest failure:** suggest the targeted runner: `apps/backend/venv/bin/python -m unittest <test.dotted.path>`.
- **contract failure:** point at `apps/backend/server.py` and ask the user whether they intentionally changed the OpenAPI title.

## Quality bar

The skill's output is correct if:

1. The three layers are reported separately. A backend pass does not gloss over a frontend fail.
2. On failure, the failing test/step is named explicitly (not "frontend failed" — instead "test:smoke failed in tests/smoke/upload-phase1.spec.ts: expected ...").
3. Timing is reported per step (rough seconds is fine; helps the user notice when tests are dragging).
4. If a step is skipped, the report says SKIPPED, not silently absent.

## Gotchas

- **`npm run verify` runs `test:smoke` which needs Playwright browsers.** First run on a fresh machine may need `npx playwright install`. If smoke fails with a "browser not found" error, name that fix specifically.
- **`RUN_GEMINI_LIVE_SMOKE=true` runs against the real Gemini Files API** — do not set this unintentionally. Default is `false` and the verify pipeline does not need it.
- **The contract probe assumes nothing else is on 8100.** If `scripts/dev.sh` is already running, skip the probe rather than fight for the port.
- **Backend tests use stdlib `unittest`**, not pytest. Don't run `pytest`; it will discover nothing.

## After the report

If everything is green, congratulate briefly and stop — don't volunteer follow-up work.

If there's a failure, ask once whether to attempt a fix or just report the failure and stop. Don't start editing files without confirmation.

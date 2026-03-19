# CODEX.md

This file provides guidance to Codex when working in this repository.

## Source Mapping

- Product mission and quality bar: `PURPOSE.md` and `ASA_System_Design.docx`.
- Repo workflow and policy: `AGENTS.md` at root, then app-local `apps/ui/AGENTS.md` or `apps/backend/AGENTS.md`.
- Command and runtime specifics: `CLAUDE.md`.

When guidance differs:

1. Mission and quality invariants from `PURPOSE.md` and `ASA_System_Design.docx` win.
2. Repo workflow and contract rules from the `AGENTS.md` chain win next.
3. `CODEX.md` files provide Codex-tailored execution guidance.

## Read Order For Codex

1. `PURPOSE.md`
2. `ASA_System_Design.docx`
3. `AGENTS.md`
4. app-local `CODEX.md` + app-local `AGENTS.md` for the area you edit
5. `CLAUDE.md` for command details and additional guardrails

## Mission Gate

Before implementing changes, run this test:

1. Does this improve measurement accuracy?
2. Does this improve recommendation specificity/quality?
3. Does this improve a producer's ability to act in Ableton?
4. If it is maintenance-only, does it clearly unblock one of the above?
5. If none apply, stop and reconsider.

## Non-Negotiable Invariants

- Phase 1 measurements are ground truth; Phase 2 does not override measured values.
- Phase 2 recommendations must cite specific Phase 1 measurements.
- Recommendations must be Ableton Live 12 specific (device, parameter, value).
- Low-confidence measurements must lead to hedged recommendations.
- Reconstruction guidance must cover the full production surface.
- Output must remain usable for intermediate producers without DSP expertise.

## Architecture Snapshot

- Layer 1 (`apps/backend/analyze.py`): deterministic DSP measurement engine.
- Layer 2 (`apps/backend/server.py` + `/api/phase2`): interpretation using measured data plus audio.
- Layer 3 (`apps/ui`): upload, estimate, analysis, and reconstruction-facing presentation.
- Contract boundary: `phase1`/`phase2` shapes consumed by UI types must remain aligned with backend responses.

## Codex Workflow Expectations

- Treat monorepo root as entrypoint for stack orchestration and release context.
- Prefer surgical edits; avoid broad rewrites unless explicitly requested.
- Preserve `analyze.py` `stdout` JSON vs `stderr` diagnostics behavior.
- Keep frontend/backend contracts in sync when adding/removing fields.
- Read `docs/ARCHITECTURE_STRATEGY.md` before proposing structural architecture or pipeline changes.

## Canonical Commands

From repo root:

```bash
./scripts/dev.sh
```

Frontend verification:

```bash
cd apps/ui
npm run verify
```

Backend verification:

```bash
cd apps/backend
./venv/bin/python -m unittest discover -s tests
```

## App Routing

- UI work: read `apps/ui/CODEX.md` and `apps/ui/AGENTS.md`.
- Backend work: read `apps/backend/CODEX.md` and `apps/backend/AGENTS.md`.

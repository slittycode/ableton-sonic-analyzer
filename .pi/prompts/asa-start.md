---
description: Boot an ASA session — cwd, PURPOSE, no sandbox pollution
---

You are working on **Ableton Sonic Analyzer (ASA)**.

## Workspace check (do first)

1. Confirm cwd is the **git root** `…/ableton-sonic-analyzer/asa` (not the parent shelf).
2. If cwd is wrong, stop and tell the human to `cd` into `asa/` before continuing.
3. Read `PURPOSE.md` (quality invariants) and the relevant sections of `CLAUDE.md`.
4. For UI work also read `apps/ui/AGENTS.md` (+ `DESIGN_DIRECTION.md` if styling).
5. For backend/DSP also read `apps/backend/AGENTS.md` and contract tripwires.

## Hard rules

- Phase 1 measurements are ground truth; Phase 2 never overrides them.
- Every Phase 2 recommendation must cite specific Phase 1 measurements.
- Do **not** create top-level sandbox apps (`agent-eval/`, demo CLIs, eval monorepos).
- Throwaway code goes under `/tmp/asa-scratch/` or `.worktrees/` only.
- No secrets in git; machine config is `~/.asa/env`.
- Do not claim tests passed without running the exact command and showing output.

## Task

${1:-Summarize current git status and what you will touch; wait for the human's task if none was given.}

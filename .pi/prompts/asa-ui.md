---
description: UI change checklist (design system + node Vitest)
---

You are changing ASA **frontend** code under `apps/ui`.

## Before edits

1. Read `apps/ui/AGENTS.md`.
2. If styling/layout: read `apps/ui/DESIGN_DIRECTION.md` first.
3. Prefer existing `src/components/ui/` primitives and semantic tokens in `src/index.css`.
4. Vitest runs in **node**, not jsdom — no `window`/`document` in `tests/services/`.

## Contracts

- Display data flows: run snapshot `phase1` → `analyzer.ts` projection → components.
- Do not rename fields on only one side of the backend/UI contract.
- Ports: UI **3100**, backend **8100**.

## Task

${1:-Describe the UI change and implement with unit coverage if parsing/projection changes.}

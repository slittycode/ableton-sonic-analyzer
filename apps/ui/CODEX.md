# CODEX.md

Codex instructions for `apps/ui`.

## Source Mapping

- Product intent and quality bar: `../../PURPOSE.md` and `../../ASA_System_Design.docx`.
- Repo and app policy: `../../AGENTS.md` and `./AGENTS.md`.
- Runtime command details and additional guardrails: `../../CLAUDE.md`.

When guidance differs, keep mission and quality invariants from `PURPOSE.md` and the system design document as the primary decision filter.

## UI Mission In This Repo

- Present deterministic Phase 1 measurements clearly and faithfully.
- Present Phase 2 interpretation as measurement-cited Ableton reconstruction guidance.
- Improve producer actionability over visual novelty.

## Contract-Critical Rules

- Preserve backend client and shared type contracts in:
  - `src/services/backendPhase1Client.ts`
  - `src/types.ts`
- Do not silently rename fields expected by backend envelopes.
- Keep diagnostics behavior stable unless intentionally changing contract + tests/docs together.
- Respect the Phase 1 ground-truth model when rendering or explaining results.

## Canonical Commands

```bash
npm run dev
npm run dev:local
npm run lint
npm run test:unit
npm run test:smoke
npm run verify
```

Preferred synced stack from repo root:

```bash
./scripts/dev.sh
```

## Codex Change Checklist

- Run focused tests first (single file/spec), then broaden as needed.
- If editing upload/orchestration/rendering flow, run relevant smoke specs.
- If editing shared types or transport parsing, run lint + targeted service tests.
- Avoid style-only churn in mixed-style files.

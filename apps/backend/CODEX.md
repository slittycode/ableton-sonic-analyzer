# CODEX.md

Codex instructions for `apps/backend`.

## Source Mapping

- Product intent and quality bar: `../../PURPOSE.md` and `../../ASA_System_Design.docx`.
- Repo and app policy: `../../AGENTS.md` and `./AGENTS.md`.
- Runtime command details and additional guardrails: `../../CLAUDE.md`.

When guidance differs, keep mission and quality invariants from `PURPOSE.md` and the system design document as the primary decision filter.

## Backend Mission In This Repo

- Keep deterministic measurement quality high and trustworthy.
- Preserve the chain of custody from Phase 1 metrics to Phase 2 advice.
- Protect producer-facing reliability over internal abstraction complexity.

## Contract-Critical Rules

- `analyze.py` emits machine-readable JSON to `stdout`; diagnostics/logs go to `stderr`.
- `server.py` normalizes raw analyzer output into stable HTTP envelopes for UI consumption.
- Treat backend output shape as contract; update tests/docs with any intentional schema change.
- Keep Phase 1 measurement authority intact; never add behavior that lets Phase 2 override measured values.

## Canonical Commands

```bash
./scripts/bootstrap.sh
./venv/bin/python server.py
./venv/bin/python analyze.py <audio_file> [--separate] [--transcribe] [--fast] [--yes]
./venv/bin/python -m unittest discover -s tests
```

Preferred synced stack from repo root:

```bash
./scripts/dev.sh
```

## Codex Change Checklist

- If request parsing, subprocess behavior, or envelopes change: run `tests/test_server.py` or broader.
- If raw analyzer output changes: run `tests/test_analyze.py` and sync docs.
- Preserve bounded diagnostics and structured error responses.
- Keep edits surgical unless an explicit broader refactor is requested.

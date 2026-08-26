# AGENTS.md

Pointer for AI coding agents that look for `AGENTS.md` by convention (Codex,
OpenHands, and others).

**The canonical agent guidance for this repo is [`CLAUDE.md`](CLAUDE.md).** Read it first.

**Start agents from this directory (`asa/`), not the parent `ableton-sonic-analyzer/` shelf.**
Pi project config lives in [`.pi/`](.pi/) (see [`.pi/README.md`](.pi/README.md)).

Order of precedence when guidance conflicts:

1. [`PURPOSE.md`](PURPOSE.md) — why ASA exists and the non-negotiable quality invariants.
2. [`CLAUDE.md`](CLAUDE.md) — canonical agent guide: commands, architecture, tripwires, change map.
3. [`docs/ARCHITECTURE_STRATEGY.md`](docs/ARCHITECTURE_STRATEGY.md) — why the three-layer design is shaped the way it is.

App-local entry points:

- [`apps/backend/AGENTS.md`](apps/backend/AGENTS.md)
- [`apps/ui/AGENTS.md`](apps/ui/AGENTS.md)

Recommendation-proof campaign status (`GOAL.md` retired 2026-07-18 — recover via git history; `plans/trust-diet-closeout-2026-07.md` is the current record):

- [`apps/backend/NEEDS.md`](apps/backend/NEEDS.md) — living status of the recommendation-proof campaign (PROXY-SCORED — non-authoritative).
- [`apps/backend/RECOMMENDATION_VERDICT.md`](apps/backend/RECOMMENDATION_VERDICT.md) — provisional Gemini-vs-deterministic write-up (PROXY-SCORED — non-authoritative; do not cite as settled).

Historical plan and audit documents were archived in the 2026-07 trust diet. Restore via `git checkout archive/pre-trust-diet-2026-07 -- docs/history`. See `docs/history/README.md`.

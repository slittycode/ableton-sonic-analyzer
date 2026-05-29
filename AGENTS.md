# AGENTS.md

Pointer for AI coding agents that look for `AGENTS.md` by convention (Codex,
OpenHands, and others).

**The canonical agent guidance for this repo is [`CLAUDE.md`](CLAUDE.md).** Read it first.

Order of precedence when guidance conflicts:

1. [`PURPOSE.md`](PURPOSE.md) — why ASA exists and the non-negotiable quality invariants.
2. [`CLAUDE.md`](CLAUDE.md) — canonical agent guide: commands, architecture, tripwires, change map.
3. [`GOAL.md`](GOAL.md) — the current north-star recommendation-proof campaign; per-app `AGENTS.md` files defer to it as well.
4. [`docs/ARCHITECTURE_STRATEGY.md`](docs/ARCHITECTURE_STRATEGY.md) — why the three-layer design is shaped the way it is.

App-local entry points:

- [`apps/backend/AGENTS.md`](apps/backend/AGENTS.md)
- [`apps/ui/AGENTS.md`](apps/ui/AGENTS.md)

Campaign status (read alongside `GOAL.md`):

- [`apps/backend/NEEDS.md`](apps/backend/NEEDS.md) — living status of the recommendation-proof campaign.
- [`apps/backend/RECOMMENDATION_VERDICT.md`](apps/backend/RECOMMENDATION_VERDICT.md) — provisional Gemini-vs-deterministic write-up (proxy-render caveats inside).

Historical plan and audit documents live in [`docs/history/`](docs/history/) — past-tense, not living docs.

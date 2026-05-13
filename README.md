# Ableton Sonic Analyzer (ASA)

A local-first tool that answers **"how do I make something that sounds like
this?"** for intermediate Ableton Live 12 producers.

ASA runs deterministic DSP measurements on a track (Phase 1) and feeds them to
an AI interpreter (Phase 2) that produces specific, measurement-cited Ableton
device recommendations. The chain of custody from measured number to
recommendation is the product — see [`PURPOSE.md`](PURPOSE.md) for the design
brief and quality invariants.

## Architecture

```
Layer 1 — MEASUREMENT (Essentia/DSP)       → deterministic, authoritative
Layer 2 — PITCH/NOTE TRANSLATION (torchcrepe) → best-effort on separated stems
Layer 3 — INTERPRETATION (Gemini)          → grounded in Layer 1 measurements
```

Phase 2 never overrides Phase 1. See [`docs/ARCHITECTURE_STRATEGY.md`](docs/ARCHITECTURE_STRATEGY.md) for *why* the stack is shaped this way.

## Repo layout

```
apps/backend/    Python 3.11 + FastAPI + Essentia DSP pipeline
apps/ui/         React 19 + Vite + TypeScript + Tailwind
scripts/         dev.sh, e2e harnesses
docs/            ARCHITECTURE_STRATEGY, SETUP, topic docs
docs/history/    Completed plans and one-shot audits (reference only)
```

## Quickstart

Requires **Python 3.11.x** (Essentia 2.1b6 wheels aren't published for 3.12+) and **Node.js 20+**.

```bash
# One-time backend setup
./apps/backend/scripts/bootstrap.sh

# One-time frontend setup
cd apps/ui && npm install && cd -

# Start the full stack (UI on :3100, backend on :8100)
./scripts/dev.sh
```

Full setup, environment variables, Phase 2 (Gemini) configuration, and
verification commands live in [`docs/SETUP.md`](docs/SETUP.md).

## Verification

```bash
cd apps/ui && npm run verify                              # lint + unit + build + smoke
cd apps/backend && ./venv/bin/python -m unittest discover -s tests
./scripts/test-e2e-integration.sh                         # local-only e2e, no Gemini key
```

## Documentation

| Where | What |
|---|---|
| [`PURPOSE.md`](PURPOSE.md) | Why ASA exists; non-negotiable quality invariants. |
| [`CLAUDE.md`](CLAUDE.md) | Canonical guide for AI coding agents and contributors: commands, architecture, tripwires, change map. |
| [`docs/ARCHITECTURE_STRATEGY.md`](docs/ARCHITECTURE_STRATEGY.md) | Why the three-layer design is shaped the way it is. |
| [`docs/SETUP.md`](docs/SETUP.md) | Detailed local setup, env vars, Phase 2 wiring. |
| [`apps/backend/ARCHITECTURE.md`](apps/backend/ARCHITECTURE.md) | Backend HTTP flow and contract. |
| [`apps/backend/JSON_SCHEMA.md`](apps/backend/JSON_SCHEMA.md) | Phase 1 stdout JSON schema. |
| [`BACKLOG.md`](BACKLOG.md) | What's next. |
| [`CHANGELOG.md`](CHANGELOG.md) | What's shipped. |

## License

[MIT](LICENSE).

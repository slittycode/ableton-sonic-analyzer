# docs/history

One-shot deliverables and completed plan docs. Kept for reference; not living docs.

If you need to know *why* something looks the way it does today, prefer:

1. `PURPOSE.md` (root) — why ASA exists and the quality invariants.
2. `docs/ARCHITECTURE_STRATEGY.md` — why the three-layer architecture is shaped the way it is.
3. `apps/backend/ARCHITECTURE.md` + `apps/backend/JSON_SCHEMA.md` — current backend contract.

Everything in this directory is past-tense. Treat it as a paper trail, not a source of truth.

## Contents

- `optimization-plan.md` — completed optimization workstream.
- `phase1-hardening-plan.md` — completed Phase 1 hardening plan.
- `library-review-torchfx-2026-05-13.md` — one-shot library evaluation of torchfx against ASA's DSP path.
- `phase1-audit/` — one-shot advisory deliverable: audit, decks, evidence index, visual story pack.
- `external-repo-review-2026-05-13.md` — completed external-repo incorporation review (openmeters / soundscope / Partiels / forever-jukebox). All three tracks resolved.
- `track1-spike-outcome-2026-05-13.md` — completed loudness verification spike. Fix shipped; regression test retained.
- `audio-analyzer-rs-decision-2026-05-20.md` — completed evaluation/decision on the audio-analyzer-rs path.
- `public-hosting-foundation-2026-04-01.md` — completion record for the hosted runtime foundation (`runtime_profile.py`, `worker.py`, `artifact_storage.py`, `auth_context.py`, plus frontend runtime overrides). The implementation it describes is current code; the "Remaining work before real public hosting" punch list inside is aspirational — re-open items in `BACKLOG.md` if needed.
- `field_utilization_report.md` — point-in-time (2026-03-26) snapshot of which Phase 1 fields appear in Phase 2 recommendations. Field names and removal recommendations are stale; see `apps/backend/JSON_SCHEMA.md` for the authoritative field list.
- `generate_phase2_truthfulness_doc.js` — one-shot Node script that generated a Phase 2 truthfulness analysis document. Past-tense; not part of the product path.
- `archive/` — older archived plans and result stubs.

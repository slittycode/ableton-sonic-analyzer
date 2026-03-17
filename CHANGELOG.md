# Changelog

All notable changes to `ableton-sonic-analyzer` are documented here.

## v2.1.0

- Hardened `transcriptionDetail` in `apps/backend/analyze.py` for bass + hook extraction:
  - added a backend noise floor (`0.05`) before merge
  - added stem-aware deduplication for overlapping/near-duplicate notes
  - capped retained notes at `500` for stem-aware runs and `200` for full-mix fallback
  - added `fullMixFallback` to the transcription payload and stderr warnings for full-mix mode and truncation
- Updated the Session Musician UI to parse `fullMixFallback` and show a subtle `FULL MIX — quality limited` badge without blocking the piano roll or export flow.
- Flipped the App default so `MIDI TRANSCRIPTION` is on by default while leaving `STEM SEPARATION` off.
- Updated backend docs for the two-layer confidence filtering model (backend noise floor plus UI slider) and the new transcription payload contract.

## v1.2.0

- Added `apps/backend/scripts/genre_check.py`: DSP preflight reporter emitting rhythm cluster, synthesis tier, sidechain status, BPM, kickSwing, kickAccentVariance, and inharmonicity — no genre labels.
- Added `apps/backend/scripts/genre_corpus.md`: 10-track ground truth validation corpus.
- Added `apps/backend/analyze_fast.py`: fast analysis path for core fields only (BPM, key, loudness, dynamics).
- Added `scripts/calibrate_confidence.py`: F1-based threshold calibration for pitchConfidence, chordStrength, and pumpingConfidence against a ground truth dataset.
- Added `tests/ground_truth/labels.json`: ground truth label schema (placeholder tracks — replace with real library entries from genre_corpus.md before running calibration).
- Applied `math.tanh(raw * 0.5)` normalization to `grooveDetail.kickSwing` and `grooveDetail.hihatSwing` in `analyze.py`, compressing the unbounded std/mean ratio to a consistent 0–1 scale.
- Added `apps/ui/src/services/phase2Validator.ts` and `apps/ui/src/services/fieldAnalytics.ts`.
- Backend tests: 29. UI tests: 128 across 16 files.

## v1.1.0

- Standardized full-feature backend bootstrap on Python `3.11.x` for macOS arm64 and documented the `3.12+` Darwin limitation across all root and backend docs.
- Added `apps/backend/scripts/bootstrap.sh` — requires `python3.11`, creates the backend venv, upgrades pip, and installs the pinned stack.
- Replaced the loose backend dependency list with the validated Python 3.11 frozen lock set in `apps/backend/requirements.txt`.
- Updated `scripts/dev.sh` so a missing backend venv error points directly to `./apps/backend/scripts/bootstrap.sh`.
- Added `apps/backend/tests/test_bootstrap_scripts.py` covering the missing-interpreter and missing-venv failure paths.
- Closed the `v1.0.0` known limitation: fresh backend bootstrap is now reproducible from a clean Python 3.11 install.

## v1.0.0

- Cut the first monorepo release and preserved the imported history of the former UI and backend repos under:
  - `apps/ui`
  - `apps/backend`
- Established the monorepo root as the source of truth for local development, verification, and release notes.
- Standardized the canonical local stack on:
  - UI `http://127.0.0.1:3100`
  - backend `http://127.0.0.1:8100`
- Added the root `scripts/dev.sh` launcher for the full local stack.
- Kept app-level changelog history intact inside the imported apps rather than rewriting their release history to match the monorepo tag.

Known limitations for this `v1.0.0` cut:

- Gemini access is still browser-held, so this is a local/dev release, not a stronger production/security milestone.
- Fresh backend bootstrap from raw `apps/backend/requirements.txt` is still under-constrained and may require follow-up dependency pinning.

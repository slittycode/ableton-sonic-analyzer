# Changelog

All notable changes to `asa` are documented here.

## Unreleased

### Added
- **`packages/loudness-spectro-wasm`** (Phase 1): browser-first Rust→WASM DSP that lifts openmeters' ITU-R BS.1770-5 / EBU R128 loudness (K-weighting, momentary/short-term, 4× true-peak) and adds integrated loudness + gating + LRA. Validated against absolute EBU Tech 3341/3342 conformance signals, the `ebur128` crate, and a pyloudnorm cross-check, with CI. Standalone — not yet imported by `apps/ui` or `apps/backend`; the Essentia path remains the authoritative Phase 1 loudness source. GPL-3.0-or-later (inherited from openmeters). See [`packages/loudness-spectro-wasm/README.md`](packages/loudness-spectro-wasm/README.md).
- **Phase 3 audition samples** (`POST/GET /api/analysis-runs/{run_id}/samples`): on-demand heuristic WAV/MIDI clips derived from Phase 1 measurements (and Phase 2 context when available), with a citation manifest. PyTheory generates the musical plan, FluidSynth (with sine-additive fallback) renders audio, NumPy synthesizes drum one-shots. Not part of the staged-execution queue. See [`docs/SAMPLE_GENERATION.md`](docs/SAMPLE_GENERATION.md).
- **URL-mode ingestion** for `POST /api/analysis-runs`: provide a public `http`/`https` `url` form field instead of a multipart `track`. SSRF-guarded against private/loopback/link-local addresses; streams through the shared 100 MiB cap. See [`apps/backend/url_ingest.py`](apps/backend/url_ingest.py).
- **Operator `X-Admin-Key` DELETE bypass** for `DELETE /api/analysis-runs/{run_id}`: when `SONIC_ANALYZER_ADMIN_KEY` is set, operators can purge any run; otherwise owner-only deletes apply. Admin path is closed by default.
- **`GET /api/analysis-runs/{run_id}/source-audio`**: owner-only re-serve of the originally ingested audio (no admin bypass). Saves a round-trip vs looking up the source artifact id.
- **CSV export** of Phase 1 time-series fields: `GET /api/analysis-runs/{run_id}/export/csv/{field_path}`, backed by the registry in [`apps/backend/csv_export.py`](apps/backend/csv_export.py). Schema record: [`docs/adr/0001-phase1-json-schema-v1.md`](docs/adr/0001-phase1-json-schema-v1.md).
- **Additive `publicStatus` field** on every stage in the run snapshot — collapses the eight internal stage statuses into a five-value client-facing vocabulary (`queued`, `running`, `completed`, `failed`, `interrupted`, plus `null` for `not_requested`). See [`apps/backend/stage_status.py`](apps/backend/stage_status.py).
- **Reassigned spectrogram** as an opt-in spectral enhancement (`POST /api/analysis-runs/{run_id}/spectral-enhancements/reassigned`): sharper transient/frequency localization via `librosa.reassigned_spectrogram`. Joins existing `cqt`, `hpss`, `onset`, `chroma_interactive`.
- **Chain-of-custody audit pass**: recommendations-first information architecture, applied-recommendations tracker, and grammar post-process on Phase 2 output. New components: [`CitationBlock.tsx`](apps/ui/src/components/CitationBlock.tsx), [`appliedRecommendations.ts`](apps/ui/src/services/appliedRecommendations.ts).
- **Stem summary interpretation** (Experiment B): Gemini stem listening via Structured Outputs on separated bass and musical stems, producing bar-aligned musical descriptions with scale degrees, rhythmic patterns, and uncertainty flags
  - Backend: stem files persist as run artifacts during pitch/note work; `stem_summary` profile runs against persisted `stem_bass` and `stem_other` audio; per-stem Gemini outputs combined into one product-facing result
  - Frontend: polling loop auto-queues `stem_summary` after pitch/note translation completes; renders separate "AI stem summary" section alongside Session Musician draft notes
  - Run snapshots expose stem artifacts and per-profile interpretation payloads
- **Phase2ConsistencyReport** wired into results flow: runs `phase2Validator` against Phase 1 + Phase 2 data, renders violation table after Phase 2 content when issues detected
- `StructureSegment` interface replaces `unknown[]` in `StructureData.segments`
- **Genre classification** card in Phase 1 detector grid (genreDetail with family, confidence, topScores)
- **Sidechain detection** card showing pump depth and timing
- **Synthesis character** card with three-tier inharmonicity + harmonic shape labels
- **Spectral balance** six-band visualization in Phase 1
- **MixDoctor** scoring engine: spectral balance, dynamics (crest factor), PLR, loudness, and stereo field vs genre-specific targets
- **MixDoctor panel** with profile selector, delta chart, diagnostic cards, and band-issue details
- **Genre profiles** data (35 genres) with spectral, dynamics, PLR, and loudness targets
- **MixDoctor** in both markdown and JSON exports
- `dynamicCharacter` in markdown export
- `genreDetail` strong parsing and typing in frontend client
- Dense techno boundary regression test (145 BPM)

### Changed
- **UI design-system migration ("D-series").** Introduced a shared primitive layer in `apps/ui/src/components/ui/` (`Button`, `Panel`, `DeviceRack`, `SectionHeader`, `MetricBar`/`MetricBarRow`/`MetricTile`, `DataTable`, `EmptyState`, `LedIndicator`, `Pill`, `SignalChain`, `ChainSeparator`, `TimeReadout`, `Checkbox`, `Tooltip`) with Storybook stories and semantic design tokens in `src/index.css`, then migrated feature components onto it — inline hex colors replaced with tokens and bespoke layout boxes replaced with primitives. Also: TypeScript strict mode, `prefers-reduced-motion` support, and a source-SR-preserving STFT spectrogram as the default spectrogram tab.
- **Backend monolith split** into domain modules (commit `5c40dd44`): `analyze_core.py`, `analyze_audio_io.py`, `analyze_detection.py`, `analyze_estimate.py`, `analyze_rhythm.py`, `analyze_segments.py`, `analyze_structure.py`, `analyze_transcription.py`, `analyze_fast.py`. Server routes likewise split into `server_phase1.py`, `server_phase2.py`, `server_upload.py`, `server_samples.py`.
- **`BatchedBandpass` centralization** ([`apps/backend/dsp_bandbank.py`](apps/backend/dsp_bandbank.py)): per-band 4th-order Butterworth filtering with zero-phase `filtfilt` now lives in one place instead of being duplicated across detectors.
- **Hosted runtime foundation** landed without disturbing local mode: [`runtime_profile.py`](apps/backend/runtime_profile.py), [`worker.py`](apps/backend/worker.py), [`artifact_storage.py`](apps/backend/artifact_storage.py), [`auth_context.py`](apps/backend/auth_context.py). See [`docs/PUBLIC_HOSTING_FOUNDATION.md`](docs/PUBLIC_HOSTING_FOUNDATION.md).
- Synthesis character labels aligned to phase2 prompt thresholds (three-tier: clean subtractive / FM-acid / wavetable-noise)
- Removed citation instructions from Phase 2 system prompt (citations added noise, not value)
- `dynamicCharacter` forwarded through `_build_phase1()` to Gemini Phase 2
- **Structure detection overhaul** in `apps/backend/analyze.py`: replaced the invalid direct-PCM SBic call path with an explicit matrix-based SBic feature-input path; added shared helpers for MFCC feature extraction, SBic frame-to-seconds boundary conversion, novelty computation reuse, and a clamped merge-floor policy; tuned SBic via an offline 36-config sweep over three reference tracks and hardcoded the winner (`featurePreset=mfcc_z`, `cpw=0.7`, `size1=300 size2=200 inc1=60 inc2=20 minLength=24`, `mergePolicy=adaptive_clamped`); added novelty-peak fallback (reusing existing `arrangementDetail` signal) for coarse SBic outputs plus a single-segment safe fallback when both paths fail; improved primary reference track output (Vtss - Can't Catch Me, 145 BPM, 125s) from `segmentCount=2` to `segmentCount=8`; added offline sweep tooling at `apps/backend/scripts/evaluate_structure_sweep.py` with JSON/Markdown reporting; expanded structure test coverage (matrix input assertion, winner-parameter assertion, novelty fallback gate, all-paths-fail fallback, duration clamp), with 238 tests passing.
- `timeSignatureSource` and `timeSignatureConfidence` are now surfaced in HTTP `phase1` via `server.py`; live preflight on `VTSS-Cant-Catch-Me.mp3` confirmed raw analyzer emits `timeSignatureSource="assumed_four_four"` (`string`) and `timeSignatureConfidence=0.0` (`float`) before passthrough wiring.
- UI truthfulness pass: surfaced Phase 2 `trackCharacter`; labeled assumed meter from `timeSignatureSource` / `timeSignatureConfidence`; replaced fake BPM-confidence percentages with raw score + source; made arrangement bars prefer backend `phraseGrid.totalBars` with derived fallback only when absent; fixed segment-key rendering so index `0` and string keys survive; split Session Musician `Total note time` from track duration and exposed melody MIDI/source/vibrato provenance; and made System Diagnostics fall back to persisted stage diagnostics when transient live logs are empty.

### Fixed
- **Interpretation stage status** now reflects all in-flight attempts: if any profile (e.g. `stem_summary`) is still queued/running, the stage reports non-terminal status so the frontend polling loop waits for it to complete
- **Stem summary failure surfacing**: console warning when `stem_summary` fails, with final snapshot emitted for UI inspection
- **Fallback parser duplicate text**: legacy flat stem-summary response no longer duplicates the top-level summary as the per-stem summary
- **TypeScript limiter fallback card**: `deviceFamily` and `workflowStage` narrowed with `as const` to satisfy `DeviceFamily` / `WorkflowStage` union types in the `satisfies` clause
- MixDoctor null-genre fallback: prompts for manual selection instead of silently using first profile
- Genre abstention logic with tests for empty, sparse, ambiguous, and fast-mode inputs
- **Confidence calibration invalidated**: `docs/confidence_calibration_results.md` (now archived at [`docs/history/archive/confidence-calibration-results-stubs.md`](docs/history/archive/confidence-calibration-results-stubs.md)) was generated from hand-crafted cache stubs with no real audio. All F1=1.0 results and threshold recommendations were artefacts of the stub data. Thresholds reverted to original engineering-judgment values (`pitchConfidence=0.15`, `chordStrength=0.70`, `pumpingConfidence=0.40`) in `apps/backend/prompts/phase2_system.txt`. Calibration script now aborts if all tracks are cache-only with no audio files present, and warns when only a partial real-audio subset is available.

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

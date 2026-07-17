# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose — Read This First

**Read `PURPOSE.md` before making any changes.** It defines why ASA exists, who it serves, and how to evaluate whether a change is worthwhile.

The short version: ASA helps intermediate Ableton Live 12 producers answer "how do I make something that sounds like this?" by running deterministic DSP measurements (Phase 1) and feeding them to an AI interpreter (Phase 2) that produces specific, measurement-cited Ableton device recommendations. The chain of custody from number to recommendation is the product. Every change should make that chain sturdier, more specific, or more useful.

**Before implementing any feature, fix, or refactor, ask:** Does this improve the reconstruction blueprint the user receives? If the answer is not clearly yes, read the decision framework in `PURPOSE.md` and reconsider.

**Quality invariants (from `PURPOSE.md` — non-negotiable):**
1. Phase 1 measurements are ground truth. Phase 2 never overrides them.
2. Every Phase 2 recommendation cites the specific measurement(s) that justify it.
3. Recommendations name exact Ableton Live 12 devices, parameters, and values.
4. Low-confidence measurements produce hedged recommendations, not confident guesses.
5. Phase 2 covers the full production surface (kick, bass, melody, groove, effects, stereo, mastering).
6. Results are accessible to intermediate producers without DSP expertise.

## Working Principles

Behavioral guidelines to reduce common LLM coding mistakes, brought in from [`forrestchang/andrej-karpathy-skills`](https://github.com/forrestchang/andrej-karpathy-skills) — a community CLAUDE.md derived from Andrej Karpathy's observations on LLM coding pitfalls (not authored by Karpathy himself). These sit *beneath* the project rules above, never above them: when guidance conflicts, `PURPOSE.md` and the quality invariants win, and Phase 1 measurements remain ground truth.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
  1. State your assumptions explicitly. If uncertain, ask.
  2. If multiple interpretations exist, present them — don't pick silently.
  3. If a simpler approach exists, say so. Push back when warranted.
  4. If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

  1. No features beyond what was asked.
  2. No abstractions for single-use code.
  3. No "flexibility" or "configurability" that wasn't requested.
  4. No error handling for impossible scenarios.
  5. If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
  1. Don't "improve" adjacent code, comments, or formatting.
  2. Don't refactor things that aren't broken.
  3. Match existing style, even if you'd do it differently.
  4. If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
  1. Remove imports/variables/functions that YOUR changes made unused.
  2. Don't remove pre-existing dead code unless asked.

The test: every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
  1. "Add validation" → "Write tests for invalid inputs, then make them pass"
  2. "Fix the bug" → "Write a test that reproduces it, then make it pass"
  3. "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Merging PRs — green is the go signal

When a PR opened during a session has **all CI checks green**, merge it — don't stop to report "it's green" and wait for a manual go-ahead. This is standing authorization: green means merge, no confirmation needed. Match the repo's history with a **squash** merge.

Stop and check in only when:
- CI is **red or still pending** (fix the failure or wait — never merge yellow/incomplete),
- a review **requests changes** (address it first), or
- the merge is genuinely contentious (touches release/migration paths, or is otherwise hard to reverse).

Everything else — green checks, optionally an approving review — is a merge, not a question.

## Commands

First-time local setup (Python 3.11 venv, Node deps, Phase 2 Gemini wiring) is documented step-by-step in [`docs/SETUP.md`](docs/SETUP.md) — start there on a fresh checkout.

### `asa` developer CLI (primary entry point)

`asa` is the single command for running and managing the local stack. It **wraps** the
scripts documented below — they still work directly. Install it once with `./bin/asa install`
(symlinks `bin/asa` into `~/.local/bin`), then:

```bash
asa                 # start the full stack (UI 3100 + backend 8100) — wraps scripts/dev.sh
asa backend         # backend only (port 8100, SONIC_ANALYZER_PORT-aware)
asa frontend        # UI only (port 3100)
asa stop            # free ports 3100 + 8100
asa status          # preflight: Python 3.11, venv, node_modules, ports, .env
asa bootstrap       # recreate backend venv + install UI deps
asa verify          # frontend verify + backend tests (narrow: asa verify backend|frontend)
asa cleanup         # delete artifacts >24h old via the safe cleanup path
                    #   (--dry-run / --ttl-hours N / --max N)
asa analyze <file>  # run the Phase 1 analyzer (always passes --yes)
asa help            # full command list
```

The script lives at [bin/asa](bin/asa); on macOS it shadows the near-dead `/usr/bin/asa`
system utility (run `hash -r` after install). The sections below document the underlying
commands `asa` wraps.

### Full Stack

```bash
./scripts/dev.sh                    # Start both services (UI: 3100, backend: 8100)
```

`scripts/dev.sh` waits for the backend contract (`/openapi.json` with title `"Sonic Analyzer Local API"`) before launching the UI. It reads `apps/ui/.env` but overrides `VITE_API_BASE_URL` for the spawned process, so stale `.env` files won't break the stack.

### Frontend (`apps/ui`)

```bash
npm run dev:local                   # Dev server on 127.0.0.1:3100
npm run verify                      # lint + test:unit + build + test:smoke (full gate)
npm run lint                        # TypeScript type-check only (no ESLint/Prettier)
npm test                            # All Vitest tests (vitest.config.ts include: tests/**/*.test.ts)
npm run test:unit                   # Vitest, restricted to tests/services/ (the unit subset)
npx playwright install chromium      # first-time Playwright setup (run once from apps/ui/)
npm run test:smoke                  # Playwright smoke suite (tests/smoke/, default config)
npm run test:smoke:live-gemini      # Playwright smoke against the real Gemini Files API (tests/smoke/upload-phase2-live-gemini.spec.ts)
npm run test:e2e                    # Playwright full e2e suite (playwright.full.config.ts)
npm run test:e2e:integration        # Playwright analysis-runs integration spec (playwright.integration.config.ts)
npm run test:e2e:headed             # Same as test:e2e but headed for local debugging

# Single test file
npx vitest run tests/services/backendPhase1Client.test.ts
# Single test by name
npx vitest run tests/services/backendPhase1Client.test.ts -t "accepts a valid backend payload"
# Single smoke spec
npm run test:smoke -- tests/smoke/upload-phase1.spec.ts
```

The smoke suite (`tests/smoke/`) is the fast Playwright gate that `verify` runs; the larger e2e suite (`tests/e2e/`) sits behind `test:e2e` / `test:e2e:integration` and is what the repo-root `scripts/test-e2e*.sh` harnesses drive.

### Backend (`apps/backend`)

```bash
./apps/backend/scripts/bootstrap.sh         # Create/recreate venv (Python 3.11.x required)
./apps/backend/venv/bin/python apps/backend/server.py  # FastAPI server on 8100
./apps/backend/venv/bin/python apps/backend/analyze.py <file> [--separate] [--transcribe] [--fast] [--standard] [--yes] [--pitch-note-only] [--stem-dir DIR] [--stem-output-dir DIR] [--pitch-note-backend BACKEND]

# All backend tests (run from apps/backend/)
./venv/bin/python -m unittest discover -s tests
# Single test module
./venv/bin/python -m unittest tests.test_server
./venv/bin/python -m unittest tests.test_analyze
# Single test class
./venv/bin/python -m unittest tests.test_server.ServerContractTests
# Single test case
./venv/bin/python -m unittest tests.test_server.ServerContractTests.test_analyze_endpoint_combines_separate_and_transcribe_in_subprocess
```

### End-to-End Integration

```bash
./scripts/test-e2e-integration.sh   # Local-only, boots real backend, drives UI via /api/analysis-runs. No Gemini key required.
TEST_FLAC_PATH=/path/to/track.flac GEMINI_API_KEY=… VITE_ENABLE_PHASE2_GEMINI=true ./scripts/test-e2e.sh  # Full live Gemini run
```

### Scripts at a glance

Operational and one-shot scripts live in two places. They are not on the request-path; reach for them when the situation calls for it.

`scripts/` (repo root):
1. `dev.sh` — full-stack dev launcher (covered above). Covered by `apps/backend/tests/test_root_dev_script.py`.
2. `test-e2e.sh` / `test-e2e-integration.sh` — e2e harnesses (covered above). Covered by `apps/backend/tests/test_root_e2e_script.py`.
3. `calibrate_confidence.py` — threshold-sweep harness for the pitch / chord / sidechain detectors. Research-only. Its unit test lives in `scripts/tests/test_calibrate_confidence.py`.
4. `build_live12_catalogue.py` — regenerates `data/live12_catalogue.json` (the source-extracted Live 12 device/parameter catalogue) from the upstream `gluon/AbletonLive12_MIDIRemoteScripts` checkout. Static AST extraction; carries no proprietary code. Re-run when the upstream commit shifts or the schema bumps; the published `data/live12_catalogue.schema.json` validates the output. Invocation: `scripts/build_live12_catalogue.py --source /path/to/gluon/AbletonLive12_MIDIRemoteScripts --output data/live12_catalogue.json` (or set `SONIC_ANALYZER_LIVE12_SOURCE` env var to omit `--source`).

`apps/backend/scripts/`:
1. `bootstrap.sh` — recreate the Python 3.11 venv (covered above). `dev.sh` here is a thin shim that `exec`s the repo-root `scripts/dev.sh` full-stack launcher. `bin/asa` script contracts (install, bootstrap, cleanup) are covered by `apps/backend/tests/test_bootstrap_scripts.py`.
2. `render_upload_limit_contract.py` — regenerate the operator-facing upload-limit contract text from `upload_limits.py`. Run after changing the canonical limits.
3. `evaluate_phase1.py`, `evaluate_polyphonic.py`, `evaluate_structure_sweep.py`, `evaluate_beats.py`, `evaluate_loudness_recs.py`, `evaluate_recommendations.py` — offline evaluation harnesses for the Phase 1 detector battery, the research polyphonic transcriber, structure-segmentation parameter sweeps, the beat/downbeat measurement gate, loudness-recommendation reachability, and the recommendation-quality scorer (`GOAL.md`'s recommendation-proof campaign — scores Phase 2 recs against the `tests/fixtures/recommendation_tracks/` answer-key corpus). Wired to `phase1_evaluation.py` / `polyphonic_evaluation.py` / `beat_evaluation.py` / `loudness_rec_evaluation.py` / `recommendation_evaluation.py`. `intake_recommendation_fixture.py` is the one-command real-render intake: render validation → canonical Phase 1 → measurable-intent gate → Claude/deterministic/baseline scores → UI verification artifact. `build_beat_manifest.py` assembles the beat-eval corpus manifest. `emit_deterministic_recs.ts` is the recommendation harness's deterministic-source bridge (Node 23+ native TS; wraps `apps/ui/src/data/abletonDevices.ts` to score the free path). All research-only. The beat gate's optional neural deps (`beat_this`, `mir_eval`) live in `apps/backend/requirements-eval.txt` — install into a separate venv, never the product venv.
4. `audit_pass1.py`, `genre_check.py`, `replay_catalog_validation.py` — corpus auditing and Live 12 device-catalog validation. `genre_corpus.md` is the corpus manifest. `genre_check.py` is covered by `apps/backend/tests/test_genre_check.py`.
5. `import_midi_to_ground_truth.py`, `score_polyphonic_clip.py` — corpus-building helpers for the transcription/polyphonic ground-truth fixtures (`tests/fixtures/transcription_tracks/`, `tests/fixtures/polyphonic_tracks/`). Research-only; see those fixtures' READMEs and `docs/LAYER2_EVALUATION.md` / `docs/POLYPHONIC_TRANSCRIPTION_SPIKE.md`.
6. `parity_probe_synth_backends.py` — maintainer probe that renders the same `ClipPlan` through FluidSynth and `symusic.Synthesizer` and reports RMS/peak/spectral-centroid deltas before flipping the `ASA_SAMPLE_SYNTH_BACKEND` auto default. Research/operator-only; not invoked by the runtime.
7. `gen_claude_phase2.py` — generates Claude-provider Phase 2 recommendations for the ground-truth corpus. For each fixture under `tests/fixtures/recommendation_tracks/` that has a stored `phase1_fingerprint.json`, runs the producer_summary interpretation through the exact server path with `ASA_PHASE2_PROVIDER=claude` and writes the fully validated `Phase2Result` (including `validationWarnings` and the `recommendations.v1` envelope) to `phase2.claude.json` in the fixture dir, where `evaluate_recommendations.py --source claude` picks it up. Zero Gemini cost — the Claude provider grounds entirely on the embedded Phase 1 JSON and never receives audio. Needs a logged-in Claude Code CLI. Research-only; drives the provider-comparison half of `GOAL.md`'s recommendation-proof campaign.

## Architecture

### Repo Layout — what's on the product path

`apps/backend/`, `apps/ui/`, `scripts/`, and `data/` are the product path. `packages/` holds forward-looking product code that isn't wired into the request path yet (see below). The full top-level layout (product-path entries called out per item; everything else is off-path and safe to skip unless the task names it):

1. `data/` — generated, source-extracted Live 12 catalogue (`live12_catalogue.json` + `live12_catalogue.schema.json`) consumed at runtime by `apps/backend/live12_catalogue.py`. Regenerated via `scripts/build_live12_catalogue.py` from the upstream `gluon/AbletonLive12_MIDIRemoteScripts` checkout. Static device/parameter metadata only; no upstream code is committed.
2. `packages/loudness-spectro-wasm/` — browser-first WebAssembly DSP (ITU-R BS.1770-5 / EBU R128 loudness, A-weighted spectrum, and spectral-reassignment spectrogram). Rust lifted from [openmeters](https://github.com/httpsworldview/openmeters) and compiled via `wasm-bindgen`, GPL-3.0-or-later. **Phase 1: standalone, not yet imported by `apps/ui` or `apps/backend`.** Has its own Cargo workspace, `npm`/`cargo` build, and EBU/ebur128/pyloudnorm validation layers — see [`packages/loudness-spectro-wasm/README.md`](packages/loudness-spectro-wasm/README.md). When integration lands, the canonical Phase 1 LUFS contract still comes from the Essentia path until this is wired in and proven at parity. (The reassigned spectrogram on the product path today comes from librosa via the `reassigned` spectral-enhancement endpoint, not this package.)
3. `audits/` — dated audit reports and assessments (e.g. `nightly-2026-05-14.md`, `nightly-2026-05-16.md`, `nightly-2026-05-19.md`, `phase2-recommendation-surface-2026-05-24.md`, `full-review-2026-05-30.md`, `owner-assessment-2026-06-10.md`). Past-tense paper trail; not imported by either app. (Older one-shot advisory deliverables like the phase 1 audit have been archived under `docs/history/phase1-audit/`.)
4. `incorporations/` — planning docs for incorporating upstream projects (e.g. `forking-plans-2026-05-14.md`, `beat-this-measurement-gate-2026-05-20.md`, `msst-separation-licence-gate-2026-06-05.md`). Planning notes only; not code.
5. `plans/` — owner-facing action plans (e.g. `owner-actions-recommendation-proof-plan.md`). Steps that require owner credentials or hardware; not code.
6. `docs/` — long-form rationale and architectural records. Key contents: `ARCHITECTURE_STRATEGY.md` (three-layer design rationale), `SETUP.md` (first-run setup), `LAYER2_EVALUATION.md` and `POLYPHONIC_TRANSCRIPTION_SPIKE.md` (Layer 2 research), `SAMPLE_GENERATION.md` (Phase 3 design), `PHASE2_PROVIDER.md` (Phase 2 provider selection — Gemini default / Claude CLI; MOSS tombstone), `ASA_ABLETON_BOUNDARY.md` (the file-coupled contract between ASA and the sibling `asa-ableton` `.als` generator — the `phase2-export.v1` handoff envelope), `adr/` (Architecture Decision Records — `0001-phase1-json-schema-v1.md` declares the v1 schema stability contract; `0002-phase1-loudness-units-v2.md` bumped `truePeak` to dBTP and `bpmConfidence` to normalized 0–1, schema now at `phase1.v2`; `0003-recommendations-contract-v1.md` freezes the Phase 2 `recommendations` contract (`recommendations.v1`) — a normalized, schema-validated, citation-gated projection of the device cards), and `history/` (completed plans, one-shot audits, and deliverables — past-tense). Read the relevant doc *before* structural changes; do not treat them as living API docs.
7. `tests/ground_truth/` — labeled-corpus fixtures consumed by `scripts/calibrate_confidence.py` (see `tests/ground_truth/README.md`). Not a test suite — each app owns its own (`apps/backend/tests/`, `apps/ui/tests/`).

### Three-Layer Model

ASA's hybrid architecture splits work into three layers. Read `docs/ARCHITECTURE_STRATEGY.md` before proposing changes to this structure — it records *why* the design is shaped this way.

```
Layer 1 — MEASUREMENT (Essentia/DSP)    → deterministic, authoritative for numbers
Layer 2 — PITCH/NOTE TRANSLATION (torchcrepe) → best-effort pitch/note extraction on stems
Layer 3 — INTERPRETATION (Gemini)       → contextual advice grounded in Layer 1 measurements
```

Core thesis: measure locally, translate pitch/notes where honest, interpret with AI grounded in measurements. Phase 2 (Gemini) never overrides Phase 1 measured values.

**One-request trace** (useful for orienting):

```
file in FileUpload.tsx
   └─► analysisRunsClient.ts (multipart POST /api/analysis-runs)
        └─► server.py route + analysis_runtime.py (persist run, enqueue stages)
             └─► analyze.py subprocess with --yes  ──► stdout: camelCase JSON
                                                  └─► stderr: timings, [warn] lines
                  └─► server.py normalizes into `phase1` envelope
                       └─► analysisRunsClient.ts polls snapshot
                            └─► analyzer.ts projects display payload
                                 └─► AnalysisResults.tsx renders
                                      └─► phase2Validator.ts checks chain of custody
```

The two contracts that matter on that path: `analyze.py` stdout (raw schema in [JSON_SCHEMA.md](apps/backend/JSON_SCHEMA.md)) and the `phase1` HTTP envelope ([src/types.ts](apps/ui/src/types.ts)). Everything else is plumbing.

### Staged Analysis Runs

The backend supports staged execution via `analysis_runtime.py`, which persists run state in SQLite (`.runtime/analysis_runs.sqlite3`) and artifacts on disk. Stages execute as a queue:

1. **measurement** — Phase 1 DSP via `analyze.py`
2. **pitch/note translation** — pitch/note extraction on Demucs-separated stems
3. **interpretation** — Gemini Phase 2 advisory
4. **mt3** *(optional, peer of pitch/note translation)* — MT3 polyphonic transcription, gated on `mt3_mode=enabled` per run; emits per-stem MIDI as artifacts. Additive only — never overrides measurement (PURPOSE.md invariant #1). Run by `_execute_mt3_attempt`/`_mt3_worker_loop` in `server.py`. See [`JSON_SCHEMA.md` "Optional MT3 Namespace"](apps/backend/JSON_SCHEMA.md#optional-mt3-namespace).

Run-oriented endpoints (`/api/analysis-runs*`) are the canonical interface for staged execution. Legacy `POST /api/analyze`, `POST /api/analyze/estimate`, and `POST /api/phase2` remain only as temporary compatibility wrappers — do not build new functionality on them.

Phase 3 audition-sample generation (`POST/GET /api/analysis-runs/{run_id}/samples`) is **on-demand**, not a queue stage — the UI explicitly requests it after interpretation completes. See `server_samples.py` and the `sample_*.py` modules. On the frontend, `apps/ui/src/components/SamplePlayback.tsx` is the entry point — mounted from `AnalysisResults.tsx` and driven by `src/services/sampleGenerationClient.ts` (`generateSamples` posts, `fetchExistingManifest` retrieves).

Frontend polling: `src/services/analysisRunsClient.ts` creates runs and polls stage snapshots. `src/services/analyzer.ts` orchestrates the create-run + poll loop and projects display payloads.

### Runtime Profiles

The backend supports two profiles, selected at startup via `SONIC_ANALYZER_RUNTIME_PROFILE` (`local` | `hosted`) and `SONIC_ANALYZER_PROCESS_ROLE` (`all` | `api` | `worker`):

1. **`local`**: SQLite + local artifact files + in-process workers. Default for development.
2. **`hosted`**: Adds auth-context resolution (`auth_context.py`) and worker-process separation (`worker.py`). Designed so the local product path is unaffected by hosted concerns.

Artifact access goes through `artifact_storage.py` rather than direct disk paths — preserve this indirection when adding new artifacts.

### Backend (`apps/backend`)

**Core files:**

1. **`analyze.py`**: Pure DSP pipeline entry point. Runs as a subprocess invoked by `server.py`. Coordinates the split feature modules below. **Writes JSON to stdout, diagnostics to stderr** — this contract is load-bearing.
2. **`analyze_core.py`, `analyze_audio_io.py`, `analyze_detection.py`, `analyze_estimate.py`, `analyze_rhythm.py`, `analyze_segments.py`, `analyze_structure.py`, `analyze_transcription.py`, `analyze_fast.py`**: Feature modules. Loadouts: BPM/key/LUFS/stereo/spectral balance, rhythm/melody detail, segment boundaries, transcription. `analyze_fast.py` is the streamlined pipeline used by `--fast`.
3. **`server.py`**: FastAPI app and router composition. Routes are organized into `server_phase1.py`, `server_phase2.py`, `server_upload.py`, `server_samples.py`. Handles multipart uploads, invokes `analyze.py` (or worker), normalizes raw output into the `phase1` HTTP contract.
4. **`analysis_runtime.py`**: SQLite-backed run state and stage queue management. Run state in `.runtime/analysis_runs.sqlite3`; artifacts in `.runtime/artifacts/`. New artifact-producing code calls `record_artifact` — do not write `.runtime/` paths directly (see also Tripwire #6 and `artifact_storage.py`).
5. **`worker.py`**: Dedicated worker-process entry point for hosted-style background stage execution. In `local` profile, work runs in-process; in `hosted` profile, this is the worker role.
6. **`runtime_profile.py`**: Switchboard for `local` vs `hosted` profile and `all` vs `api` vs `worker` process roles (env: `SONIC_ANALYZER_RUNTIME_PROFILE`, `SONIC_ANALYZER_PROCESS_ROLE`).
7. **`artifact_storage.py`**: Storage-service boundary. Today writes to local disk; the interface is designed so callers do not assume disk paths forever.
8. **`auth_context.py`**: Hosted-mode user-context resolution and ownership checks on canonical run routes.
9. **`upload_limits.py`**: Canonical 100 MiB raw-audio / 101 MiB request-envelope limits. Regenerate the operator contract via `scripts/render_upload_limit_contract.py` if numbers change.
10. **`spectral_viz.py`**: Librosa-based spectrogram/time-series artifacts. Called after measurement; failures are non-critical.
11. **`url_ingest.py` + `audio_mime.py`**: `url_ingest.py` is SSRF-guarded URL-mode ingestion for `POST /api/analysis-runs` — fetches a public `http`/`https` audio URL and feeds it through the same downstream pipeline as a multipart upload. `audio_mime.py` is the canonical, host-independent filename→MIME map for ingested audio (`canonical_audio_mime`); it mirrors the frontend contract in [src/services/audioFile.ts](apps/ui/src/services/audioFile.ts) so both sides agree, avoiding stdlib `mimetypes` host divergence (macOS `audio/x-flac` vs Linux `audio/flac`) that can mislabel a FLAC sent to Gemini. Imported directly by `server_phase2.py` and `url_ingest.py`, and reached by `server.py` via `server_phase2._get_audio_mime_type`.
12. **`csv_export.py`**: CSV exporters for Phase 1 time-series fields, backing `GET /api/analysis-runs/{run_id}/export/csv/{field_path}`. Keeps the route handler a thin lookup-and-serve. Field paths are an explicit allowlist (`csv_export.list_supported_fields()` — currently `lufsCurve.shortTerm`, `lufsCurve.momentary`, `rhythmDetail.tempoCurve`, `spectralBalanceTimeSeries`); arbitrary descent into the payload is not supported. Example: `curl http://127.0.0.1:8100/api/analysis-runs/<run_id>/export/csv/rhythmDetail.tempoCurve -o tempo.csv`.
13. **`stage_status.py`**: Collapses the eight internal stage statuses into the additive client-facing `publicStatus` field on every stage snapshot.
14. **`server_samples.py` + `sample_generation.py`, `sample_theory.py`, `sample_synthesis.py`, `sample_drums.py`**: Phase 3 audition-sample generation. `sample_theory.py` builds the PyTheory musical plan, `sample_synthesis.py` renders audio (FluidSynth with sine-additive fallback), `sample_drums.py` synthesizes drum one-shots, `sample_generation.py` orchestrates and emits the citation manifest. On-demand only.
15. **`dsp_bandbank.py` + `dsp_utils.py`**: Shared DSP primitives — `BatchedBandpass` (4th-order Butterworth bandpass bank) and cross-module utility functions.
16. **`phase1_evaluation.py` + `phase1_report_html.py`, `polyphonic_evaluation.py`, `beat_evaluation.py` + `beat_report_html.py`, `loudness_rec_evaluation.py`, `recommendation_evaluation.py`**: Offline evaluation harnesses (deterministic-metric / detector-stability reporting, research-only polyphonic transcription, the beat/downbeat measurement gate that benchmarks CPJKU/beat_this against the shipping kick-accent heuristic, loudness-recommendation reachability, and the recommendation-quality scorer that grades Phase 2 recommendations against known-settings fixtures — see [`apps/backend/NEEDS.md`](apps/backend/NEEDS.md)). Not on the product path; driven by `scripts/evaluate_*.py`. Deleting them restores the product exactly. The Layer 2 transcription path of `phase1_evaluation.py` has dedicated pure-function coverage in `tests/test_phase1_evaluation_transcription.py`.

16a. **`recommendation_fixture_intake.py`** + **`scripts/intake_recommendation_fixture.py`**: Research-only one-command real-render intake for the recommendation corpus. Validates 48 kHz/24-bit audio and measurable intent, stores the canonical Phase 1 contract, drives Claude + deterministic generation, scores Claude/deterministic/baseline, and refreshes the UI verification artifact only after the fixture passes. `recommendation_fixture_intake.py` is the backend module; `scripts/intake_recommendation_fixture.py` is the operator CLI wrapper. Covered by `tests/test_recommendation_fixture_intake.py`.
17. **`utils/cleanup.py`**: Periodic artifact-cleanup helpers used by the server background-task loop. Covered by `tests/test_cleanup.py`.
18. **`transcription_pianoroll.py`**: Renders the pitch-note translation stage's `transcriptionDetail` as a velocity-encoded `(pitch, time)` uint8 matrix via [`symusic`](https://github.com/Yikai-Liao/symusic). Backs `GET /api/analysis-runs/{run_id}/transcription/pianoroll`. Derived view, never overrides Phase 1; the response cites Phase 1's `bpm` + `timeSignature` so chain of custody is preserved. Note: `transcriptionDetail` is *stripped* from `measurement.result` (see `analysis_runtime.py` ~L800) and lives in the `pitchNoteTranslation` stage instead — the route reads from there.
19. **`mt3_transcription.py`**: Optional polyphonic transcription via Google MT3 (T5X). Additive only — never overrides measurement (PURPOSE.md invariant #1). Gated on the env var `ASA_ENABLE_MT3=1` for the legacy CLI path and the run-level form field `mt3_mode='enabled'` for the canonical staged API. Driven from `_execute_mt3_attempt`/`_mt3_worker_loop` in `server.py`; emits per-stem MIDI as artifacts and an `mt3` namespace on the run snapshot. Heavy dependencies pinned in `requirements-mt3.txt`. See [`JSON_SCHEMA.md` "Optional MT3 Namespace"](apps/backend/JSON_SCHEMA.md#optional-mt3-namespace).
20. **`live12_catalogue.py` + `phase2_catalogue_gates.py`**: Source-extracted Live 12 catalogue lookup and Phase 2 output-validation gates. `live12_catalogue.py` loads `data/live12_catalogue.json` (generated by `scripts/build_live12_catalogue.py`), validates it against the published schema, and exposes a `Live12Catalogue` API with case-insensitive `has_device`, exact-match parameter lookup, and a `fuzzy_resolve` escape hatch. `phase2_catalogue_gates.py` cross-checks every `{device, parameter, value, phase1Fields}` record in `mixAndMasterChain`, `abletonRecommendations`, and `secretSauce.workflowSteps` against the catalogue and emits **warn-and-keep** `RECOMMENDATION_UNVERIFIED` events on `validationWarnings` (reasons: `device_unknown`, `parameter_unknown`, `value_out_of_range`, `citation_missing`). NEVER drops a recommendation, NEVER rewrites a parameter — an earlier fuzzy-rewrite path produced confidently-wrong output (wrong EQ band + wrong A/B curve), so the contract is now warn-only. Mirrors `_validate_phase2_citation_paths` in spirit. Wired into `server.py` after `_validate_phase2_citation_paths`; load/parse errors degrade to a single skip warning instead of failing the response.

21. **`loudness_backend.py`**: Selectable Phase 1 loudness backend (default-off experiment). `ASA_LOUDNESS_BACKEND=wasm` overrides the four integrated/range/momentary-max/short-term-max LUFS scalars with readings from the native `measure-cli` binary (source-identical to `packages/loudness-spectro-wasm`). `truePeak` and `lufsCurve` always stay on Essentia. Any failure degrades back to Essentia. Default is `essentia` (no-op).

22. **`separation_backend.py`**: Thin Phase 1 stem-separation seam over torchaudio Hybrid Demucs (`analyze_audio_io.separate_stems`). `separate_stems_backend` is the entry point called from `analyze.py`'s three separation sites (measurement `--separate`, `--pitch-note-only`, `--mt3-only`). The former MSST/BS-RoFormer optional path was removed in the 2026-07 trust diet (research-only licence gate; see `incorporations/msst-separation-licence-gate-2026-06-05.md`).

23. **`recommendations_contract.py` + `schemas/recommendations.v1.schema.json`**: Frozen, versioned Phase 2 recommendation contract (ADR 0003). `project_recommendations` normalizes the three Phase 2 device-card arrays (`abletonRecommendations`, `mixAndMasterChain`, `secretSauce.workflowSteps`) into a flat `{device, parameter, value, unit, range, cited_measurements[]}` envelope (`version: "recommendations.v1"`); `validate_envelope` checks it against the committed JSON Schema via `jsonschema` (the real file, not a hand-rolled mirror — see ADR 0001's drift warning). Derived and additive — it never overrides Phase 1 (invariant #1) and admits ONLY cited cards (`cited_measurements.minItems: 1`); uncited cards stay in the raw arrays where the warn-and-keep catalogue gate flags them. `server.py` attaches the validated envelope to the producer_summary interpretation result as a `recommendations` field (degrades to absent on error). TS mirror: `RecommendationsContract` in [src/types/interpretation.ts](apps/ui/src/types/interpretation.ts). CI gate: `tests/test_recommendations_contract.py` (schema validity + projection-validates + round-trip + freeze).

24. **`phase2_provider.py`**: Selectable Phase 2 interpretation provider (default-off experiment). `ASA_PHASE2_PROVIDER=claude` routes the producer_summary interpretation to `ClaudeCliProvider` — a text-only interpreter that runs the local Claude Code CLI headless (sandboxed: `--safe-mode`, `--tools ""`, `--no-session-persistence`, response schema enforced via `--json-schema`), grounds purely on the prompt's embedded Phase 1 JSON, and needs no `GEMINI_API_KEY`. All paths flow through the identical parse/citation/catalogue validators. The former MOSS sidecar was a permanent licence dead-end and was removed in the 2026-07 trust diet — see `docs/PHASE2_PROVIDER.md`.

25. **`phase2_export.py`** + **`schemas/phase2-export.v1.schema.json`**: Versioned Phase 2 handoff envelope (`phase2-export.v1`) for downstream consumers — the sibling `asa-ableton` repo (turns ASA recommendations into an openable Live 12 `.als` starter set) and `scripts/evaluate_recommendations.py --phase2`. Backs `GET /api/analysis-runs/{run_id}/export/phase2`: the stored `producer_summary` interpretation result verbatim (including the frozen `recommendations.v1` projection), the authoritative Phase 1 payload its citations resolve against, the full `validationWarnings` trail, and provenance — one curl, one self-contained file, no snapshot surgery. Same thin lookup-and-serve pattern as `csv_export.py`; envelope structure described in `schemas/phase2-export.v1.schema.json`; key set frozen by `tests/test_phase2_export.py`. Cross-repo contract documented in `docs/ASA_ABLETON_BOUNDARY.md`.

The subprocess isolation means `analyze.py` works as a standalone CLI. Check `apps/backend/JSON_SCHEMA.md` before adding new analyzer output fields. Check `apps/backend/ARCHITECTURE.md` for the full HTTP flow and contract details.

**Phase 2 (`POST /api/phase2`, legacy compat):** Uploads audio to Gemini inline if ≤100 MiB, or via the Gemini Files API if larger. Phase 1 JSON is appended to the system prompt from `prompts/phase2_system.txt`. Also relevant: `prompts/stem_summary_system.txt` and `prompts/live12_device_catalog.json` (the *prompt-injected* device catalogue — distinct from the runtime-validation `data/live12_catalogue.json` consumed by `phase2_catalogue_gates.py`). Backend defense-in-depth: `server_phase2.py`'s `_validate_phase2_citation_paths` mirrors the frontend citation-existence check and emits `validationWarnings` when a recommendation cites a Phase 1 path that doesn't exist — it flags invented citations rather than failing, since Phase 1 stays authoritative (invariant #1). `phase2_catalogue_gates.apply_live12_catalogue_gates` runs immediately after for source-catalogue checks (see backend file #20 above). Additional regression gates: `tests/test_phase2_grammar_fix.py` locks in the gerund-fix post-process in `server_phase2.py`; `tests/test_phase2_prompt_catalog.py` pins prompt examples against the Live 12 catalogue.

**Python version constraint:** Python 3.11.x required on macOS arm64. Essentia 2.1b6 wheels are only published for 3.11; this constraint may be relaxable if Essentia publishes 3.12+ wheels.

### Frontend (`apps/ui`)

Single-page React 19 + Vite + TypeScript + Tailwind CSS v4 app with no router. View states managed via React conditionals (upload → estimate → analysis → results). Vitest for unit tests, Playwright for smoke tests.

**Key service files** (canonical transport + chain-of-custody contracts):

1. **`src/services/analysisRunsClient.ts`**: Canonical transport. Creates runs against `/api/analysis-runs`, polls snapshots, fetches pitch/note translations and interpretations.
2. **`src/services/analyzer.ts`**: Phase orchestration entry point — sequences run creation, polling, and display payload projection.
3. **`src/services/backendPhase1Client.ts`**: Legacy multipart transport (typed error classes, `AbortController` timeouts, identity probe via `/openapi.json`). Kept for the compatibility wrappers; new flows should go through `analysisRunsClient.ts`.
4. **`src/services/httpClient.ts`**: Shared fetch helpers and request-header injection used by the run/artifact/sample clients.
5. **`src/services/spectralArtifactsClient.ts`**: Fetches spectrogram/spectral-evolution artifacts via `/api/analysis-runs/{run_id}/artifacts/…`.
6. **`src/services/transcriptionPianorollClient.ts`**: Fetches the velocity-encoded transcription pianoroll matrix via `/api/analysis-runs/{run_id}/transcription/pianoroll`. Backed by `apps/backend/transcription_pianoroll.py`. Rendered by `TranscriptionPianoroll.tsx` (canvas heatmap) inside `TranscriptionPianorollBlock.tsx`, which `AnalysisResults.tsx` mounts in the Session Musician suite when `transcriptionDetail.noteCount > 0`.
6a. **`src/services/mt3Client.ts`**: Opt-in MT3 polyphonic transcription client. POSTs `/api/analysis-runs/{run_id}/mt3-transcriptions` and reads the additive `mt3` namespace from the run snapshot. Only fires when the user enables MT3 at upload time (form field `mt3_mode='enabled'`); measurement stays authoritative.
7. **`src/services/sampleGenerationClient.ts`**: Phase 3 audition-sample POST/GET against `/api/analysis-runs/{run_id}/samples`, plus per-clip artifact streaming.
7a. **`src/services/patchSmith.ts`**: Phase 3 Vital preset generation — builds a `.vital` preset JSON from Phase 1 measurements, with every parameter citing the exact Phase 1 field(s) that justify it (PURPOSE.md invariant #2). Hedges or skips parameters whose evidence is weak (invariant #4). Surfaced in `components/PatchSmithPanel.tsx`.
8. **`src/services/mixDoctor.ts`**: Mix advisory logic — client-side scoring and suggestions against measured spectral balance. Genre profile data lives in **`src/data/genreProfiles.ts`**.
9. **`src/services/phase2Validator.ts`** + **`loudnessGuardrails.ts`**: Runtime guardrail. Validates Phase 2 consistency against Phase 1 (`validateBPMConsistency`, `validateKeyConsistency`, `validateLUFSConsistency`, `validateGenreDSPConsistency`, `validateNumericBounds`, `validateLoudnessActionPresence`). `loudnessGuardrails.ts` defines the objective loudness defects (digital clipping via `saturationDetail.clippedSampleCount`, true-peak overs via `truePeak`) that a Phase 2 mastering/dynamics card *must* address — a missing action surfaces as a `MISSING_LOUDNESS_ACTION` violation. The aggregate `validatePhase2Consistency` drives **`Phase2ConsistencyReport.tsx`**, which renders the chain-of-custody report on the results surface (`AnalysisResults.tsx`, `hideWhenClean`) and in full inside the diagnostic log (`DiagnosticLog.tsx`); `App.tsx` computes the report and passes it down.
10. **`src/services/appliedRecommendations.ts`** + **`userLabels.ts`**: Applied-recommendations tracker and persisted-label state used by the audit overhaul.
9a. **`src/services/recommendationVerification.ts`** + **`src/data/recommendationVerification.ts`** + **`components/RecommendationVerificationBadge.tsx`**: Per-recommendation corpus-verification badge (`GOAL.md` sub-goal 4). The data module is a generated artifact from `apps/backend/scripts/evaluate_recommendations.py --verification-artifact` (all-`NONE` until the ground-truth corpus has renders); the service infers a card's domain (mirroring the backend scorer's `infer_domain`) and looks up its confidence band; the badge renders on `AnalysisResults.tsx` recommendation cards, hidden when there is no corpus evidence. Research/proof surface — see [`apps/backend/NEEDS.md`](apps/backend/NEEDS.md).
9b. **`src/services/recommendationsContract.ts`**: UI-side reader for the frozen `recommendations.v1` envelope (ADR 0003). Indexes the backend-projected envelope so render surfaces can pair each raw device card with its validated contract entry — a match means the card is schema-checked and cites at least one Phase 1 measurement; absence means an uncited card the contract refused to admit. Matching is by `(device, parameter, normalized value)`; the value parser is a deliberate TS mirror of the backend's `parse_value` in `recommendations_contract.py` — keep both in sync. The `RecommendationsContract` interface itself lives in `src/types/interpretation.ts` (not this service file).
11. **`src/services/phase1Picker.ts`** + **`phaseLabels.ts`**: Phase-snapshot projection helpers consumed by the results surface.
12. **`src/services/audioFile.ts`**: Client-side audio validation, blank-MIME extension fallback, preview-URL lifecycle.
13. **`src/services/fieldAnalytics.ts`** + **`diagnosticLogs.ts`**: Instrumentation hooks and diagnostic-log capture for the request panel.
14. **`src/services/midi/`**: MIDI export, preview, and quantization utilities (`midiExport.ts`, `midiPreview.ts`, `quantization.ts`, `types.ts`).
15. **`src/services/sessionMusician/`**: Session Musician helpers — `confidenceBand.ts`, `index.ts`, `noteConversion.ts`, `renderState.ts`, `stemListeningNotes.ts`.
15a. **`src/services/browserLoudness/`**: Browser-side WASM loudness integration (WS3c). `loader.ts` dynamically imports the `loudness-spectro-wasm` web build from `VITE_BROWSER_LOUDNESS_WASM_URL` (off by default — the WASM `pkg/` is not a build dependency and not built in CI). `wavDecoder.ts` decodes audio to PCM. `parity.ts` defines the shared `BrowserLoudnessReading` type. Unavailable when the WASM URL is unset; UI degrades gracefully.
16. **`src/types.ts`** + **`src/types/`**: `types.ts` re-exports through `./types/index.ts`, which barrels `measurement.ts`, `interpretation.ts`, and `backend.ts`. `Phase1Result` lives in `types/measurement.ts`; `AnalysisRunSnapshot` in `types/backend.ts`; `Phase2Result` in `types/interpretation.ts`. `./types/samples.ts` is imported directly by callers, not through the barrel.
17. **`src/config.ts`**: Runtime resolution of `VITE_API_BASE_URL` and feature flags; falls back to `http://127.0.0.1:8100`. Supports window-level overrides (`window.__VITE_API_BASE_URL_OVERRIDE__`, `window.__VITE_ENABLE_PHASE2_GEMINI_OVERRIDE__`) for hosted deployments that inject config at runtime without a rebuild.
18. **`src/hooks/`**: Custom React hooks — `useCpuMeter.ts`, `useGlobalDrag.ts`, `useImageZoom.ts`, `useSpectralCursorBus.tsx`.
19. **`src/utils/`**: Pure utility helpers — `appView.ts`, `assertNever.ts`, `chordTheory.ts`, `colorScales.ts`, `displayText.ts`, `exportUtils.ts`, `phase2Preference.ts`, `renderBenchmark.ts`, `spectralScales.ts`.

`AnalysisResults.tsx` is the large results surface, lazy-loaded via Suspense; `analysisResultsViewModel.ts` (same directory) holds its pure projection helpers. `waveformPlayerUtils.ts` (same directory) provides peak-tracking and spectrum-activity utilities for `WaveformPlayer.tsx`. `src/components/analysisResults/` is a subdirectory holding extracted Phase 2 static section components (`AudioObservationsSection.tsx`, `DetectedCharacteristicsSection.tsx`, `ProjectSetupSection.tsx`, `RoutingBlueprintSection.tsx`, `TrackLayoutSection.tsx`, `WarpGuideSection.tsx`, `shared.tsx`) — split from the `AnalysisResults.tsx` monolith in the UI overhaul Phase 5 series (don't consolidate them back). Manual vendor chunks in `vite.config.ts` control bundle splitting.

`src/components/sessionMusician/` holds the Session Musician UI components (`ConfidenceBandBadge.tsx`, `MelodyContourBlock.tsx`, `MidiControlsRow.tsx`, `NoteDraftBlock.tsx`, `PianoRollCanvas.tsx`, `QuantizeControls.tsx`, `usePreviewController.ts`) mounted by `SessionMusicianPanel.tsx`. Distinct from the service helpers in `src/services/sessionMusician/`.

**Design-system primitives (`src/components/ui/`):** the shared, Ableton-inspired UI vocabulary (`Button`, `Panel`, `DeviceRack`, `SectionHeader`, `MetricBar`/`MetricBarRow`/`MetricTile`, `DataTable`, `EmptyState`, `LedIndicator`, `Pill`, `SignalChain`, `ChainSeparator`, `TimeReadout`, `Checkbox`, `Tooltip`, `CollapsibleCard`, `DeltaBadge`, `Lane`, `TokenBadgeList`), barrel-exported from `src/components/ui/index.ts`. Each primitive ships a `*.stories.tsx`; variants live in `variants.ts`, the class-merge helper in `cn.ts`. Feature components were migrated onto these primitives and onto the semantic design tokens in `src/index.css` (the "D-series" migration — see Recent Refactors). Build new UI from these primitives and reuse the tokens before adding raw colors or one-off components.

### Frontend-Backend Contract

The interface between apps is `Phase1Result` (in [src/types/measurement.ts](apps/ui/src/types/measurement.ts)) matched against the `phase1` payload inside the analysis-run snapshot (`AnalysisRunSnapshot` in [src/types/backend.ts](apps/ui/src/types/backend.ts)). **Do not rename fields on either side without updating both.** Error envelopes always include `requestId`, `error.code`, `error.message`, `error.retryable`, and `diagnostics`.

## Environment Variables

```bash
# apps/ui/.env (copy from .env.example)
VITE_RUNTIME_PROFILE="local"             # frontend profile; controls API-URL fallback when VITE_API_BASE_URL is omitted
VITE_API_BASE_URL="http://127.0.0.1:8100"
VITE_API_REQUEST_HEADERS_JSON=""         # optional JSON object of headers injected on every API request (e.g. `{"X-ASA-User-Id":"beta-user-123"}` for hosted-mode beta access). Empty = no extra headers.
VITE_ENABLE_PHASE2_GEMINI="true"
RUN_GEMINI_LIVE_SMOKE="false"    # set "true" to run live Playwright tests against real Gemini Files API
DISABLE_HMR="false"              # set "true" for dev environments that need HMR disabled

# Backend (env var, no .env file)
SONIC_ANALYZER_PORT=8100
GEMINI_API_KEY="your_key_here"           # read by server.py at runtime, not in browser bundle
SONIC_ANALYZER_ADMIN_KEY="optional"      # if set, DELETE /api/analysis-runs/{run_id} accepts an X-Admin-Key header that bypasses ownership for operator-level purge. Unset by default; admin path is closed.
ASA_ENABLE_MT3="0"                       # set to "1" on the legacy analyze.py CLI path to run the optional MT3 polyphonic transcription pass. Canonical staged API uses the run-level form field `mt3_mode='enabled'` instead. Heavy deps in apps/backend/requirements-mt3.txt.
ASA_SAMPLE_SYNTH_BACKEND="auto"          # Phase 3 audition-sample synth backend: `auto` (default, prefers FluidSynth and falls back to symusic), `symusic`, or `fluidsynth` to pin one. See apps/backend/sample_synthesis.py.
ASA_LOUDNESS_BACKEND="essentia"          # Phase 1 loudness source for the LUFS scalars: `essentia` (default, authoritative) or `wasm` to override lufsIntegrated/lufsRange/lufsMomentaryMax/lufsShortTermMax with the asa-dsp (loudness-spectro-wasm) reading via the native measure-cli binary. truePeak + lufsCurve stay Essentia; degrades back to Essentia if measure-cli is unbuilt. Default-off experiment. See apps/backend/loudness_backend.py.
ASA_MEASURE_CLI=""                       # optional absolute path to the measure-cli binary used by ASA_LOUDNESS_BACKEND=wasm; defaults to packages/loudness-spectro-wasm/target/release/measure-cli.
ASA_SEPARATION_BACKEND="demucs"          # Phase 1 stem-separation backend. Only Demucs is supported after the 2026-07 trust diet MSST cut; unknown values fall back to demucs. See apps/backend/separation_backend.py.
ASA_PHASE2_PROVIDER="gemini"             # Phase 2 interpretation provider: `gemini` (default, product path, unchanged) or `claude` to run the local Claude Code CLI headless as a TEXT-ONLY interpreter (no audio sent; grounds on the prompt's embedded Phase 1 JSON; needs no GEMINI_API_KEY — rides the operator's existing Claude Code login). Default-off for non-Gemini; both providers flow through the identical parse/citation/catalogue validators. The former MOSS path was removed (licence dead-end) — see docs/PHASE2_PROVIDER.md.
ASA_CLAUDE_CLI="claude"                  # path to the Claude Code CLI binary used when ASA_PHASE2_PROVIDER=claude; defaults to `claude` on PATH.
ASA_CLAUDE_MODEL=""                      # optional model override for the claude provider (e.g. `sonnet`); empty = the CLI's default model. The subprocess runs sandboxed: --safe-mode, --tools "", --no-session-persistence, schema enforced via --json-schema.
ASA_CLAUDE_TIMEOUT_SECONDS="600"         # per-call timeout for the claude provider subprocess (a full producer_summary prompt on the CLI default model measures ~6 min). For headless runs also set MAX_THINKING_TOKENS=0 — a thinking-enabled model can spend the entire budget deliberating before the structured output starts (see docs/PHASE2_PROVIDER.md, 2026-06-11 addendum).
```

Phase 2 is gated by `VITE_ENABLE_PHASE2_GEMINI`. `GEMINI_API_KEY` is backend-only. `SONIC_ANALYZER_ADMIN_KEY` is backend-only and never exposed to clients.

## Key Guardrails

- **Backend contract:** `analyze.py` stdout → JSON only. `server.py` HTTP shapes → match `types.ts`. Read `apps/backend/ARCHITECTURE.md` and `apps/backend/JSON_SCHEMA.md` before changing analyzer output or HTTP responses.
- **Architecture strategy:** Read `docs/ARCHITECTURE_STRATEGY.md` before proposing structural changes to the dependency stack, transcription pipeline, or layer boundaries.
- **No linter/formatter:** No ESLint, Prettier, or Ruff configured. Follow the style of the surrounding code.
- **Backend tests use stdlib `unittest`**, not pytest. Frontend tests use Vitest in `node` environment (not jsdom).
- **`npm run lint`** only type-checks `src/`; `tests/`, `dist/`, `node_modules/`, `playwright.config.ts`, and `vitest.config.ts` are excluded from `tsconfig.json`.
- **Canonical ports:** UI on 3100, backend on 8100. `./scripts/dev.sh` fails loudly if either port is occupied.
- **`--fast` flag** runs a streamlined pipeline (BPM, key, loudness, basic dynamics) via `analyze_fast.py`. It is forwarded through the HTTP API via form field or query param.
- **`dsp_json_override`** is accepted by the server but ignored. It's a legacy field; don't repurpose it.

## Tripwires

Things that look like normal code changes but silently break the contract. Most have bitten this codebase before:

1. **`print(...)` in [analyze.py](apps/backend/analyze.py) without `file=sys.stderr`.** Stdout is the JSON contract. Any stray print corrupts it and the server reports a parse error with no useful trace. The existing code is consistent about this — match the pattern (`print(f"[warn] ...", file=sys.stderr)`).
2. **Calling `analyze.py` as a subprocess without `--yes`.** The CLI prompts for confirmation when stdin is a TTY. Subprocess invocations must pass `--yes` or hang waiting for input. `server.py` already does; new callers must too.
3. **Renaming a field on only one side.** Python emits *camelCase* JSON directly (`bpmConfidence`, not `bpm_confidence`) — there is no conversion layer. A rename in [analyze.py](apps/backend/analyze.py) without a matching update in [src/types.ts](apps/ui/src/types.ts) is undetectable by either type system; the field just disappears from the UI. A subtler variant: the ~12 `parseOptional*` reconstructors in [src/services/backendPhase1Client.ts](apps/ui/src/services/backendPhase1Client.ts) rebuild their block field-by-field, so a backend field one of them forgets to forward is *silently dropped* — and if Phase 2 cites it, the citation fails the existence check (this bit `reverbDetail.preDelayMs` + the vocal stem proxies). The executable guard is [tests/services/phase1CitationContract.test.ts](apps/ui/tests/services/phase1CitationContract.test.ts): it parses a comprehensive payload and asserts every citable path survives `collectPhase1FieldPaths`. Add a new citable field to both its fixture and its `CITABLE_DETAIL_PATHS` list.
4. **Adding a top-level key without updating `EXPECTED_TOP_LEVEL_KEYS`.** [tests/test_analyze.py](apps/backend/tests/test_analyze.py) holds a snapshot of every root key. New fields require updating that set *and* [JSON_SCHEMA.md](apps/backend/JSON_SCHEMA.md). The same test enforces that `--fast` only populates `FAST_MODE_POPULATED_FIELDS`. A change to *measured values* (not just keys) can also trip the golden-snapshot regression gate in [tests/test_phase1_golden.py](apps/backend/tests/test_phase1_golden.py) (fixture `tests/fixtures/golden/phase1_default.json`) — re-baseline it deliberately, never blindly (from `apps/backend/`): `UPDATE_PHASE1_GOLDEN=1 ./venv/bin/python -m unittest tests.test_phase1_golden` The golden also carries a recursive `keyTree` (nested key structure); re-baselining it is what arms/updates the frontend parity gate's nested check, so expect `apps/ui/tests/services/phase1ContractParity.test.ts` to demand the matching frontend sync.
5. **Using `document` or `window` in `tests/services/`.** Vitest runs in `node`, not `jsdom`. Service-layer tests are pure logic; if you need DOM, it's a Playwright test in `tests/smoke/` instead.
6. **Hard-coding `Path(...)` for artifacts in new code.** Artifact access must go through [artifact_storage.py](apps/backend/artifact_storage.py). Direct paths work in `local` profile and break silently in `hosted`.
7. **Editing `apps/ui/.env` and expecting `dev.sh` to honor it.** `dev.sh` reads `apps/ui/.env` but *overrides* `VITE_API_BASE_URL` for the spawned UI process so stale `.env` files don't break the stack. To point the UI at a non-canonical backend, edit `dev.sh` or run the UI directly with the env var on the command line.
8. **Phase 2 prompts that don't reference Phase 1 measurements.** The chain-of-custody invariant is enforced at runtime by [phase2Validator.ts](apps/ui/src/services/phase2Validator.ts) (`validateBPMConsistency`, `validateKeyConsistency`, `validateLUFSConsistency`, `validateGenreDSPConsistency`). If a prompt change lets Phase 2 emit a contradicting value, the validator surfaces it in the UI as a violation — not a silent failure, but worth knowing where the check lives. The backend independently mirrors the citation-existence half of this check: `_validate_phase2_citation_paths` in [server_phase2.py](apps/backend/server_phase2.py) (called from [server.py](apps/backend/server.py)) flags cited `phase1Fields` paths that don't resolve against the authoritative measurement payload — WARNING-only, ridden on the `validationWarnings` channel, so a non-browser API consumer can't silently accept invented citations.
9. **Editing one side of the audio MIME map without the other.** [audio_mime.py](apps/backend/audio_mime.py) (`CANONICAL_AUDIO_MIME_BY_EXT`) and [src/services/audioFile.ts](apps/ui/src/services/audioFile.ts) (`AUDIO_EXTENSION_MIME_TYPES`) are a deliberately duplicated cross-boundary contract. They must agree, or the same file resolves to a different MIME on each side and a FLAC sent to Gemini (which expects `audio/flac`) can be mislabeled. Change both together.
10. **Assuming `truePeak` is linear or `bpmConfidence` is the raw Essentia value.** ADR 0002 (`docs/adr/0002-phase1-loudness-units-v2.md`) changed both: `truePeak` is now **dBTP** (was linear amplitude), `bpmConfidence` is now **0–1 normalized** (was raw Essentia ~0–5.32), and `phase1Version: "phase1.v2"` was added as a top-level field. Code that treats `truePeak` as linear or `bpmConfidence` as a raw score is silently wrong — the type system won't catch it.

## Where to Make the Change

A quick map from intent to the right place to start:

| If you're changing… | Touch | Then |
|---|---|---|
| What gets measured | [analyze.py](apps/backend/analyze.py) + the relevant `analyze_*.py` module | Update [JSON_SCHEMA.md](apps/backend/JSON_SCHEMA.md), `EXPECTED_TOP_LEVEL_KEYS` in [test_analyze.py](apps/backend/tests/test_analyze.py), and [src/types.ts](apps/ui/src/types.ts) |
| How a measurement renders | `apps/ui/src/components/` | Add Vitest coverage in `tests/services/` if any new parsing/projection logic |
| How Phase 2 advises | [prompts/phase2_system.txt](apps/backend/prompts/phase2_system.txt) and/or [prompts/live12_device_catalog.json](apps/backend/prompts/live12_device_catalog.json) | Verify with the live Gemini smoke (`RUN_GEMINI_LIVE_SMOKE=true`) on a known track |
| The HTTP envelope shape | [server.py](apps/backend/server.py) (router) + the `server_*.py` module | [test_server.py](apps/backend/tests/test_server.py) contract tests + frontend client types |
| Run-state or stage flow | [analysis_runtime.py](apps/backend/analysis_runtime.py) | Frontend polling in [analysisRunsClient.ts](apps/ui/src/services/analysisRunsClient.ts) |
| Upload limits or proxies | [upload_limits.py](apps/backend/upload_limits.py) | Regenerate the operator contract via `scripts/render_upload_limit_contract.py` |
| Hosted-mode behavior | [runtime_profile.py](apps/backend/runtime_profile.py), [auth_context.py](apps/backend/auth_context.py), [worker.py](apps/backend/worker.py) | Keep the `local` profile path unaffected — that's the load-bearing dev loop |

## Debugging Recipes

- **"The UI is missing a field that should be there."** Hit `http://127.0.0.1:8100/openapi.json` to confirm the server contract, then run `analyze.py <same file> --yes` directly and grep its stdout for the field name. If the analyzer emits it but the UI doesn't see it, the rename slipped — check both sides of the camelCase boundary.
- **"Subprocess returned no usable JSON."** Re-run `analyze.py` directly. If stderr shows real diagnostics but stdout has extra text, search for `print(` without `file=sys.stderr` in the modules you touched.
- **"Backend test passes locally, fails on a fresh checkout."** Usually a `venv` issue. Recreate with `./apps/backend/scripts/bootstrap.sh` — Python 3.11.x is required and Essentia wheels don't exist for 3.12+.
- **"Phase 2 says something the measurements don't support."** Open the analysis result in the UI; [phase2Validator.ts](apps/ui/src/services/phase2Validator.ts) violations render inline. The validator is the source of truth for "did Phase 2 break the chain of custody."
- **"Reproduce a hung subprocess."** Try `./venv/bin/python analyze.py <file>` *without* `--yes` and you'll see the confirmation prompt that hangs in non-TTY contexts.

## Recent Refactors (don't undo)

- **Backend and frontend monoliths were intentionally split** into domain modules — on the backend, `analyze.py` coordinates sibling modules `analyze_core.py`, `analyze_audio_io.py`, `analyze_detection.py`, `analyze_estimate.py`, `analyze_rhythm.py`, `analyze_segments.py`, `analyze_structure.py`, `analyze_transcription.py`, and `analyze_fast.py`; on the frontend, focused service files under `apps/ui/src/services/`. The split is the current target shape; resist consolidating it back.
- **Hosted runtime foundation landed without disturbing local mode.** `runtime_profile.py`, `worker.py`, `artifact_storage.py`, and `auth_context.py` are the seams. Local-mode code should not branch on profile unless it has to; the boundary handles it.
- **UI design-system migration (the "D-series") and overhaul.** A shared primitive layer landed in `apps/ui/src/components/ui/` (with Storybook stories and semantic design tokens in `src/index.css`), and feature components were migrated onto it — inline hex colors were replaced with tokens and bespoke layout boxes with primitives like `DeviceRack`/`SectionHeader`. The overhaul continued through Phase 5: `CollapsibleCard` was added as a layout primitive (Phase 5a), and the `AnalysisResults.tsx` Phase 2 static sections were extracted into `src/components/analysisResults/` (Phases 5b–5d). Build on the primitives and tokens; don't reintroduce one-off styled boxes or raw hex; don't merge the extracted section components back into the monolith.
- **WASM loudness/spectro library (Phase 1, partially wired).** `packages/loudness-spectro-wasm/` lifts openmeters' BS.1770-5 / EBU R128 loudness, an A-weighted spectrum, and a spectral-reassignment spectrogram into a Rust→WASM package with EBU 3341/3342, `ebur128`, and pyloudnorm conformance layers. The **browser** side has a guarded dynamic-import loader (`src/services/browserLoudness/`) — activates only when `VITE_BROWSER_LOUDNESS_WASM_URL` is set and the built `pkg/` is served; off by default. The **backend** side (`loudness_backend.py`, `ASA_LOUDNESS_BACKEND=wasm`) invokes the native `measure-cli` binary to override four LUFS scalars; also default-off. Leave the Essentia loudness path authoritative (`truePeak`, `lufsCurve`, and all measurements unrelated to LUFS scalars) until scalar parity is proven at scale. The product reassigned-spectrogram endpoint runs on librosa, not this package. Don't reimplement this DSP in JS; the package is the home for it.

## Backport Candidates

The full original `sonic-architect-app` backlog is **shipped** — genre profiles, Ableton device mappings (`abletonDevices.ts` — **product-wired 2026-07-02** as the Phase-2-off deterministic fallback via `src/services/deterministicRecommendations.ts` (cited + hedged, renders only when interpretation is unavailable), reversing the 2026-06-11 research-only demotion; the eval bridge that scores it as the harness baseline is unchanged — see `apps/backend/NEEDS.md`), mix doctor, eight detectors, Phase 3 audition-sample generation, and `patchSmith.ts` (Phase 3 Vital preset generation, [`apps/ui/src/services/patchSmith.ts`](apps/ui/src/services/patchSmith.ts)). See [`BACKLOG.md`](BACKLOG.md) for the landed inventory. Consult it before re-implementing genre detection, mix analysis, acid/reverb/vocal/supersaw/bass/kick detection — they're already in [`apps/backend/analyze_detection.py`](apps/backend/analyze_detection.py) and emit fields visible in `EXPECTED_TOP_LEVEL_KEYS`.

## Companion Agent Docs

This repo carries parallel guidance for non-Claude agents:

1. **`AGENTS.md`** (root) — pointer for Codex / OpenHands / any tool that looks for `AGENTS.md` by name. Defers to this file.
2. **`apps/backend/AGENTS.md`**, **`apps/ui/AGENTS.md`** — per-app overlays with technology-stack details and app-specific change checklists.
3. **`docs/ARCHITECTURE_STRATEGY.md`** — *why* the three-layer architecture is shaped the way it is.
4. **`GOAL.md`** — the recommendation-proof campaign (north-star goal). `apps/backend/NEEDS.md` is its living status doc (PROXY-SCORED — non-authoritative); `apps/backend/RECOMMENDATION_VERDICT.md` is the provisional Gemini-vs-deterministic write-up (PROXY-SCORED — non-authoritative; do not cite as settled).
5. **`docs/history/`** — completed plans and one-shot audits. Past-tense, not living docs.
6. **`docs/adr/`** — Architecture Decision Records. `0001-phase1-json-schema-v1.md` declares the Phase 1 JSON schema v1 stability contract (field-rename policy, CSV column pinning, `publicStatus` collapse). `0002-phase1-loudness-units-v2.md` accepted a breaking unit change: `truePeak` is now dBTP (was linear), `bpmConfidence` is now 0–1 normalized (was raw Essentia ~0–5.32), and a `phase1Version: "phase1.v2"` top-level field was added. `0003-recommendations-contract-v1.md` freezes the Phase 2 recommendation surface as the versioned JSON Schema `recommendations.v1` — each entry `{device, parameter, value, unit, range, cited_measurements[]}`, validated in CI against `apps/backend/schemas/recommendations.v1.schema.json`. Consult these before proposing changes to the Phase 1 payload shape or the recommendation contract.

When information conflicts: `PURPOSE.md` > `CLAUDE.md` > `GOAL.md` > per-app `AGENTS.md`.

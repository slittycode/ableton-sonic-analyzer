# AGENTS.md

## Scope

- This file applies to `apps/backend` inside the `asa` monorepo.
- Root-level agent guidance lives in `../../CLAUDE.md`; this file is the backend overlay.
- The repo is a local Python audio-analysis service with two entry points:
  - `analyze.py`: raw CLI analyzer
  - `server.py`: FastAPI wrapper around the CLI
- There are no repo-local Cursor rules, `.cursorrules`, or Copilot instruction files in this repo as of 2026-05-30.

## Working Style For Agents

- Prefer small, surgical edits over broad refactors.
- Preserve the current contract between `analyze.py`, `server.py`, and the UI.
- Read `README.md`, `ARCHITECTURE.md`, and `JSON_SCHEMA.md` before changing API or payload behavior.
- Read `../../docs/ARCHITECTURE_STRATEGY.md` before proposing structural changes to the dependency stack, transcription pipeline, or the Layer 1/2/3 architecture. It records why the current design is shaped the way it is, dependency health verdicts, and the planned experiment sequence.
- Treat `stdout` vs `stderr` behavior as part of the product contract, not just an implementation detail.
- Do not silently change field names in raw CLI output or HTTP envelopes.

## Environment And Setup

- Python: use Python `3.11.x` for the supported full-feature local setup on macOS arm64.
- Preferred bootstrap from `apps/backend`:

```bash
./scripts/bootstrap.sh
```

- Manual equivalent:

```bash
python3.11 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

- Main runtime dependencies are pinned in `requirements.txt`.
- Python `3.12+` is not a supported full-feature local bootstrap target on macOS arm64 because Essentia 2.1b6 wheels are only published for 3.11 on arm64.
- Basic Pitch has been removed. `TorchcrepeBackend` is the canonical Layer 2 (monophonic pitch/note) backend. PENN was assessed and removed after local benchmarks showed no meaningful win over torchcrepe for ASA's stem-aware note workflow.
- MT3 polyphonic transcription is now an **optional, opt-in staged backend** (`mt3_transcription.py`, gated by run-level `mt3_mode=enabled` and the env var `ASA_ENABLE_MT3=1` for the legacy CLI path). It is additive — measurement remains authoritative (PURPOSE.md invariant #1). Do not add Basic Pitch as a production backend; use `polyphonic_evaluation.py` and `scripts/evaluate_polyphonic.py` for research-only comparison of other candidates.
- If audio/DSP imports fail, check local native dependencies before editing code.

## Main Commands

- Preferred: the `asa` developer CLI — `asa` (full stack), `asa backend` (backend only), `asa cleanup`, `asa verify`. It wraps the commands below, which still work directly.
- Preferred synced local stack from the monorepo root: `./scripts/dev.sh`
- Run the CLI analyzer:

```bash
./venv/bin/python analyze.py <audio_file> [--separate] [--transcribe] [--fast] [--yes]
```

- Run the FastAPI server:

```bash
./venv/bin/python server.py
```

- The server currently binds to `0.0.0.0:8100` by default and honors `SONIC_ANALYZER_PORT`.
- The UI expects the backend at `http://127.0.0.1:8100` unless overridden.
- The monorepo root `./scripts/dev.sh` starts `apps/ui` on `http://127.0.0.1:3100` and overrides stale UI `.env` backend URLs for that session.
- If `./scripts/dev.sh` reports a missing backend virtualenv, run `./scripts/bootstrap.sh` in `apps/backend` or `./apps/backend/scripts/bootstrap.sh` from the repo root.

## Validation Commands

- `asa verify backend` runs the full suite below; `asa verify` adds the frontend gate.
- Minimal syntax validation:

```bash
./venv/bin/python -m py_compile server.py
```

- Run all backend tests:

```bash
./venv/bin/python -m unittest discover -s tests
```

- Run one test module:

```bash
./venv/bin/python -m unittest tests.test_server
./venv/bin/python -m unittest tests.test_analyze
```

- Run one test class:

```bash
./venv/bin/python -m unittest tests.test_server.ServerContractTests
./venv/bin/python -m unittest tests.test_analyze.AnalyzeStructuralSnapshotTests
```

- Run one test case:

```bash
./venv/bin/python -m unittest tests.test_server.ServerContractTests.test_analyze_endpoint_combines_separate_and_transcribe_in_subprocess
./venv/bin/python -m unittest tests.test_analyze.AnalyzeStructuralSnapshotTests.test_duration_is_close_to_fixture_length
```

## Testing Expectations

- This repo uses stdlib `unittest`, not `pytest`.
- `tests/test_server.py` is the API contract suite; run it after changing request parsing, subprocess behavior, diagnostics, timing, or error envelopes.
- `tests/test_analyze.py` is a structural snapshot test for the raw analyzer JSON; run it after changing emitted fields or raw output shape.
- Prefer the narrowest useful test first, then the full suite.
- If you change CLI output keys, update docs and tests in the same change.

## File Map

- `analyze.py`: CLI entry point. Coordinates the split `analyze_*.py` feature modules and emits the raw JSON.
- `analyze_core.py`, `analyze_audio_io.py`, `analyze_detection.py`, `analyze_estimate.py`, `analyze_rhythm.py`, `analyze_segments.py`, `analyze_structure.py`, `analyze_transcription.py`, `analyze_fast.py`: Feature modules (BPM/key/LUFS/stereo, rhythm/melody/groove, segments, structure, transcription, the `--fast` pipeline). Split from the original `analyze.py` monolith — keep the split when adding features, don't merge them back in.
- `mt3_transcription.py`: Optional polyphonic transcription via Google MT3 (research-grade T5X model). Gated on the env var `ASA_ENABLE_MT3=1` for the legacy CLI path and on run-level `mt3_mode=enabled` for the staged API. Additive only — never overrides measurement (PURPOSE.md invariant #1). Heavy dependency footprint pinned separately in `requirements-mt3.txt`. Driven from `_execute_mt3_attempt`/`_mt3_worker_loop` in `server.py`; the staged-run handler emits per-stem MIDI as artifacts and surfaces an `mt3` namespace per the "Optional MT3 Namespace" section of `JSON_SCHEMA.md`.
- `server.py` + `server_phase1.py`, `server_phase2.py`, `server_upload.py`, `server_samples.py`: FastAPI app + route modules. Multipart/URL upload handling, subprocess execution, envelope normalization, and the on-demand Phase 3 audition-sample routes.
- `analysis_runtime.py`: SQLite-backed run state, stage queue, artifact metadata.
- `worker.py`, `runtime_profile.py`, `auth_context.py`, `artifact_storage.py`: Hosted-mode foundation. Local mode shouldn't branch through these unless it has to.
- `upload_limits.py`: Canonical 100 MiB raw-audio / 101 MiB request-envelope limits. Operator contract is generated, not hand-edited.
- `url_ingest.py`: SSRF-guarded URL-mode ingestion for `POST /api/analysis-runs`. Fetches a public `http`/`https` audio file and streams the bytes through the same downstream pipeline as a multipart upload, enforcing the shared 100 MiB cap.
- `audio_mime.py`: Canonical, host-independent filename→MIME map for ingested audio (`canonical_audio_mime`). Mirrors `apps/ui/src/services/audioFile.ts` so a `.flac` resolves to `audio/flac` on every OS (stdlib `mimetypes` is host-dependent). Imported directly by `server_phase2.py` and `url_ingest.py`, and reached by `server.py` via `server_phase2._get_audio_mime_type` — keep the two maps in sync.
- `csv_export.py`: CSV exporters for Phase 1 time-series fields; backs `GET /api/analysis-runs/{run_id}/export/csv/{field_path}`.
- `stage_status.py`: Collapses the eight internal stage statuses into the additive client-facing `publicStatus` field carried on every stage in the run snapshot.
- `sample_generation.py`, `sample_theory.py`, `sample_synthesis.py`, `sample_drums.py`: Phase 3 audition-sample generation — PyTheory plan, FluidSynth/sine-additive render, NumPy drum one-shots, citation manifest. On-demand only.
- `dsp_bandbank.py`, `dsp_utils.py`: Shared DSP primitives — `BatchedBandpass` Butterworth bank and cross-module utilities.
- `spectral_viz.py`: Librosa spectrogram and spectral time-series artifacts. Non-critical — failures don't break a run.
- `phase1_evaluation.py` + `phase1_report_html.py`: Offline Phase 1 evaluation harness — deterministic-metric and detector-stability reporting, with a standalone HTML render. Not on the product path; driven by `scripts/evaluate_phase1.py`.
- `polyphonic_evaluation.py` + `scripts/evaluate_polyphonic.py`: **Research-only.** Offline polyphonic-transcription evaluation harness, not part of the shipped product path.
- `beat_evaluation.py` + `beat_report_html.py`: **Research-only.** Beat/downbeat measurement gate benchmarking CPJKU/beat_this against the shipping kick-accent downbeat heuristic. Driven by `scripts/evaluate_beats.py`; deleting it restores the product exactly.
- `loudness_rec_evaluation.py`: **Eval/test-only.** Reachability check for the deterministic subset of a loudness recommendation (gain-to-target-LUFS + true-peak ceiling). Must not be imported by `analyze.py` or `server.py`.
- `recommendation_evaluation.py` + `scripts/evaluate_recommendations.py`: **Research-only.** Recommendation-quality scorer for `GOAL.md`'s recommendation-proof campaign. Grades Phase 2 recs against `tests/fixtures/recommendation_tracks/` known-settings fixtures using a role/parameter/direction-band rubric, per-domain breakdown, and a chain-of-custody penalty that mirrors `phase2Validator.ts`. CLI supports `--source baseline|gemini|deterministic`, `--self-test`, `--report`, `--verification-artifact`. Companion: `scripts/emit_deterministic_recs.ts` is the Node 23+ TS bridge that wraps `apps/ui/src/data/abletonDevices.ts` into the scorer's normalized shape. Status doc: `NEEDS.md`; verdict write-up: `RECOMMENDATION_VERDICT.md`. Off the product path.
- `live12_catalogue.py`: Source-extracted Live 12 device/parameter catalogue loader. Reads `data/live12_catalogue.json` (generated by repo-root `scripts/build_live12_catalogue.py` from upstream `gluon/AbletonLive12_MIDIRemoteScripts`), validates against the published schema, and exposes `Live12Catalogue.has_device` (case-insensitive), exact-match parameter lookup, and `fuzzy_resolve`. Static-source extraction carries no `type/min/max/unit/default`; reserved for future runtime-introspection enrichment. Imported by `phase2_catalogue_gates.py` and the catalogue tests.
- `loudness_backend.py`: Selectable Phase 1 loudness backend (default-off experiment, WS3b). `ASA_LOUDNESS_BACKEND=wasm` overrides the four integrated/range/momentary-max/short-term-max LUFS scalars with readings from the native `measure-cli` binary (source-identical to `packages/loudness-spectro-wasm`). `truePeak` and `lufsCurve` stay on Essentia. Any failure degrades back to Essentia silently. Default is `essentia` (no-op). Covered by `tests/test_loudness_backend.py`.
- `separation_backend.py`: Selectable Phase 1 stem-separation backend (default-off experiment). `ASA_SEPARATION_BACKEND=msst` swaps torchaudio Hybrid Demucs for MSST/BS-RoFormer from a `SUC-DriverOld/MSST-WebUI` checkout, keeping the `{stem_name: wav_path}` contract (`vocals/bass/drums/other`, 44.1 kHz) unchanged. MSST runs in its own venv via `scripts/msst_separate_runner.py` subprocess under `ASA_MSST_PYTHON`; any failure degrades back to Demucs silently. Default is `demucs` (no-op). See `separation_ab.py` for the research-only A/B harness. Covered by `tests/test_separation_backend.py`.
- `separation_ab.py`: Research-only A/B harness for comparing Demucs and MSST separation backends on quality (SI-SDR) and runtime. Driven by `scripts/ab_separation_backends.py`. Deleting this file restores the product exactly. Covered by `tests/test_separation_ab.py`.
- `phase2_provider.py` + `moss_sidecar/`: Selectable Phase 2 interpretation provider (default-off experiment). `ASA_PHASE2_PROVIDER=moss` routes the producer_summary to a self-hosted MOSS-Audio sidecar instead of Gemini; both paths run through the same parse/citation/catalogue validators. The real-model path is a 501 licence-gated stub — research-only. See `docs/PHASE2_PROVIDER.md`. Covered by `tests/test_phase2_provider.py`.
- `phase2_catalogue_gates.py`: **Warn-and-keep** Live 12 source-catalogue annotation of Phase 2 recommendations. Cross-checks every `{device, parameter, value, phase1Fields}` record against `Live12Catalogue` and emits `RECOMMENDATION_UNVERIFIED` events on `validationWarnings` for `device_unknown`, `parameter_unknown`, `value_out_of_range`, `citation_missing`. NEVER drops or rewrites — an earlier fuzzy-rewrite path produced confidently-wrong output (wrong EQ band + wrong A/B curve), so the contract is warn-only. Wired into `server.py` after `_validate_phase2_citation_paths`. Lives separately from `server_phase2.py` so unit tests can run without the FastAPI/pydantic import chain.
- `utils/cleanup.py`: Periodic artifact cleanup helpers used by the server background-task loop. Covered by `tests/test_cleanup.py`.
- `tests/test_server.py`: OpenAPI and envelope contract tests.
- `tests/test_analyze.py`: generated WAV fixture, `EXPECTED_TOP_LEVEL_KEYS` snapshot, raw payload assertions.
- `tests/test_csv_export.py`, `tests/test_sample_*.py`, `tests/test_server_samples.py`: Coverage for CSV export and Phase 3 audition samples.
- `tests/test_phase1_golden.py`: golden-snapshot regression gate over measured Phase 1 values (`tests/fixtures/golden/phase1_default.json`). Re-baseline deliberately when a measurement change is intended.
- `tests/test_beat_evaluation.py`, `tests/test_loudness_rec_evaluation.py`: unit coverage for the research/eval-only beat and loudness-recommendation harnesses.
- `tests/test_mt3_transcription.py`: unit coverage for the optional MT3 polyphonic backend module.
- `tests/test_loudness_backend.py`: unit coverage for `loudness_backend.py` (the selectable LUFS backend).
- `tests/test_separation_backend.py`: unit coverage for `separation_backend.py` (dispatch, fallback, model registry, and runner-helper contracts — no MSST install required).
- `tests/test_loudness_r128.py`: contract tests for ADR 0002 unit changes — `analyze_true_peak` emits dBTP, `analyze_plr` is a dB-domain subtraction.
- `tests/test_analysis_runtime.py`: SQLite run-state, stage queue, and artifact-metadata behavior.
- `tests/test_server_phase2.py`: Phase 2 route contracts, `_validate_phase2_citation_paths`, and Gemini upload path behavior.
- `tests/test_transcription_pianoroll.py`: pianoroll matrix rendering and chain-of-custody header contracts.
- `tests/test_url_ingest.py`: SSRF guard, MIME detection, and URL-mode ingestion behavior.
- `tests/test_upload_limits.py`: upload-limit constant contracts (matches `upload_limits.py`).
- `tests/test_worker.py`: hosted-mode worker entry point contracts.
- `tests/test_audio_mime.py`: canonical MIME map parity with the frontend `audioFile.ts` contract (tripwire #9 in `CLAUDE.md`).
- `tests/test_artifact_storage.py`: storage-boundary contracts and profile-switching behavior.
- `tests/test_stage_status.py`: `publicStatus` collapse behavior for all eight internal stage statuses.
- `tests/test_analyze_audio_io.py`, `tests/test_analyze_detection_*.py`: coverage for the audio-I/O and detection feature modules.
- `tests/test_auth_context.py`, `tests/test_runtime_profile.py`: hosted-mode auth and profile-switching contracts.
- `tests/test_dsp_bandbank.py`, `tests/test_dsp_utils.py`: shared DSP primitive contracts.
- `tests/test_live12_catalogue.py`, `tests/test_phase2_validator_catalogue.py`, `tests/test_phase2_citation_paths.py`: catalogue lookup and Phase 2 warn-and-keep gate behavior.
- `tests/test_spectral_viz.py`, `tests/test_transcription_backends.py`: spectral-artifact and transcription-backend contracts.
- `tests/test_phase1_evaluation.py`, `tests/test_polyphonic_evaluation.py`, `tests/test_recommendation_evaluation.py`: unit coverage for research/eval-only harnesses (mirror their production counterparts).
- `tests/test_phase1_evaluation_transcription.py`: pure-function tests for the Layer 2 transcription evaluation harness path in `phase1_evaluation.py` (no torchcrepe model load required).
- `tests/test_audio_fixture.py`: WAV-fixture helper used by tests that need a deterministic audio file without running the full CLI; carries a copy of `EXPECTED_TOP_LEVEL_KEYS` for structural assertions.
- `tests/test_audio_fixture_smoke.py`: deterministic 440 Hz sine wave generation and basic audio-I/O smoke (no model load required).
- `tests/test_bootstrap_scripts.py`: unit coverage for `bin/asa` install / bootstrap / cleanup script contracts.
- `tests/test_cleanup.py`: unit coverage for `utils/cleanup.py` artifact-cleanup helpers.
- `tests/test_genre_check.py`: unit coverage for `scripts/genre_check.py`.
- `tests/test_phase2_grammar_fix.py`: regression tests for the Phase 2 gerund-fix post-process in `server_phase2.py` (audit-final round fix).
- `tests/test_phase2_prompt_catalog.py`: regression tests for Phase 2 prompt examples against the Live 12 catalogue (`prompts/live12_device_catalog.json`).
- `tests/test_root_dev_script.py`: unit coverage for root `scripts/dev.sh` env-loading behavior.
- `tests/test_root_e2e_script.py`: unit coverage for root `scripts/test-e2e.sh` / `scripts/test-e2e-integration.sh` script contracts.
- `tests/test_separation_ab.py`: focused tests for `separation_ab.py` SI-SDR aggregation math and MUSDB-style on-disk loader.
- `ARCHITECTURE.md`: backend responsibilities and request flow.
- `JSON_SCHEMA.md`: raw CLI schema plus HTTP mapping notes.

## Operator and Research Scripts

Under `apps/backend/scripts/` (not on the product path):

- `bootstrap.sh`: create/recreate the venv with the pinned Python 3.11 dependencies.
- `dev.sh`: convenience shim that `exec`s the monorepo root `./scripts/dev.sh` full-stack launcher. It does not start the backend on its own — the root launcher boots both backend and UI.
- `render_upload_limit_contract.py`: re-renders the operator-facing upload-limit contract whenever `upload_limits.py` numbers change.
- `evaluate_phase1.py`, `evaluate_structure_sweep.py`, `evaluate_polyphonic.py`, `evaluate_beats.py`, `evaluate_loudness_recs.py`, `evaluate_recommendations.py`, `evaluate_phase2_providers.py`, `build_beat_manifest.py`, `genre_check.py`, `audit_pass1.py`, `replay_catalog_validation.py`: research and audit harnesses for measurement quality, beat/downbeat and loudness-recommendation gates, the recommendation-quality scorer, the Phase 2 provider comparison harness (benchmarks Gemini vs MOSS quality and latency via `phase2_provider_evaluation.py`), and prompt-output review. Outputs land under `.runtime/` and are intentionally not wired into the live API. The beat gate's optional neural deps (`beat_this`, `mir_eval`) live in `requirements-eval.txt` — install into a separate venv, never the product venv.
- `emit_deterministic_recs.ts`: Node 23+ native-TS bridge for `evaluate_recommendations.py --source deterministic`. Wraps `apps/ui/src/data/abletonDevices.ts` so the deterministic recommendation path can be scored against the same fixtures as Gemini without a TypeScript build step. No `npm install` needed.
- `parity_probe_synth_backends.py`: Maintainer probe that renders the same deterministic `ClipPlan` through both FluidSynth and `symusic.Synthesizer` and reports RMS / peak / spectral-centroid deltas, with a documented tolerance and pass/fail verdict written to `.runtime/parity/synth_parity.json`. Use before flipping the `ASA_SAMPLE_SYNTH_BACKEND` auto default away from FluidSynth — never invoked by the runtime.
- `msst_separate_runner.py`: Runs in the MSST venv (not the product venv) under `ASA_MSST_PYTHON`. Invoked by `separation_backend.py` as a subprocess; imports `MSSeparator` from a `SUC-DriverOld/MSST-WebUI` checkout, writes canonical `vocals/bass/drums/other` 44.1 kHz WAVs, and prints a one-line JSON manifest to stdout. Operator tooling only — never imported by the product venv.
- `ab_separation_backends.py`: A/B harness CLI (wraps `separation_ab.py`) comparing Demucs vs MSST on quality and runtime: always-available synthetic SI-SDR smoke-test plus optional real-track reference-free proxies. Writes `.runtime/separation_ab/report.json`. Research-only; deleting `separation_ab.py` restores the product exactly.

## Code Style

- Follow the surrounding file style instead of introducing a new formatter profile.
- Use 4-space indentation.
- Prefer double quotes in Python files.
- Keep imports grouped in this order:
  1. standard library
  2. third-party packages
  3. local imports
- Separate import groups with a single blank line.
- Prefer short helper functions when they clarify coercion, normalization, or envelope building.
- Use trailing commas in multiline literals and call sites when the surrounding file does.

## Types And Data Handling

- Keep type hints on public helpers and contract-shaping functions.
- Use Python 3.10 style annotations such as `str | None`, `dict[str, Any]`, and `list[datetime]`.
- Preserve the current pattern of explicit coercion helpers for API payload normalization.
- When mapping raw analyzer output to `phase1`, prefer defensive conversion over blind passthrough for scalar fields.
- Default to returning stable, typed values instead of leaking inconsistent raw types into HTTP responses.

## Naming Conventions

- Use `snake_case` for functions, variables, and module-level helpers.
- Use `UPPER_SNAKE_CASE` for constants.
- Use descriptive private helpers prefixed with `_` when they are internal to a module.
- Use `PascalCase` for `unittest.TestCase` classes.
- Name tests after observable contract behavior, not implementation trivia.

## Error Handling

- Be defensive. Many analyzer feature functions intentionally catch exceptions and degrade gracefully.
- In `analyze.py`, preserve the pattern of logging warnings to `stderr` and returning `None`/null-friendly payload fragments when a feature fails.
- In `server.py`, preserve structured JSON error envelopes with `requestId`, `error`, and optional `diagnostics`.
- Do not replace stable backend errors with generic uncaught exceptions.
- When adding new failure paths, include enough detail for local debugging without changing public response shape unnecessarily.

## Output And Logging Contracts

- `analyze.py` must emit machine-readable JSON to `stdout` only.
- Human-readable progress, warnings, and errors belong on `stderr`.
- `server.py` emits a `[TIMING]` summary line to `stderr`; preserve that behavior when touching timing logic.
- Keep snippets and diagnostics bounded; avoid dumping massive payloads into error responses.

## Backend Contract Rules

- `POST /api/analysis-runs/estimate`, `POST /api/analysis-runs`, and `GET /api/analysis-runs/{run_id}` are the primary app-facing routes.
- `POST /api/analyze`, `POST /api/analyze/estimate`, and `POST /api/phase2` are compatibility wrappers only.
- `server.py` normalizes raw analyzer output into `phase1`; it does not expose every raw field.
- The raw CLI schema and the HTTP schema are intentionally different; check `JSON_SCHEMA.md` before expanding or removing fields.
- `transcriptionDetail` is only present when `analyze.py` runs with `--transcribe`.

## Known Gotchas

- `--fast` runs the reduced fast-analysis preset: core fields stay populated, while most detail-heavy fields remain `null`.
- `dsp_json_override` is accepted by the server but ignored.
- The server always appends `--yes` when invoking `analyze.py`.
- README CORS docs have drifted before; trust `server.py` constants over prose if they disagree.
- The UI depends on the existing envelope structure, diagnostics fields, and timing keys.

## Change Checklist

- If you change API request parsing, run `tests/test_server.py`.
- If you change raw analyzer output, run `tests/test_analyze.py` and update docs.
- If you change timeout or diagnostics behavior, inspect both tests and `ARCHITECTURE.md`.
- If you add a new field, document whether it belongs to raw CLI output, HTTP `phase1`, or both.
- Before finishing, run the narrowest relevant test plus `./venv/bin/python -m unittest discover -s tests` if the change is broad.

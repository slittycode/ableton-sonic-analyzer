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

## Commands

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
npm test                            # All Vitest unit tests
npm run test:unit                   # Unit tests only (tests/services/)
npm run test:smoke                  # Playwright smoke tests

# Single test file
npx vitest run tests/services/backendPhase1Client.test.ts
# Single test by name
npx vitest run tests/services/backendPhase1Client.test.ts -t "accepts a valid backend payload"
# Single smoke spec
npm run test:smoke -- tests/smoke/upload-phase1.spec.ts
```

### Backend (`apps/backend`)

```bash
./apps/backend/scripts/bootstrap.sh         # Create/recreate venv (Python 3.11.x required)
./apps/backend/venv/bin/python apps/backend/server.py  # FastAPI server on 8100
./apps/backend/venv/bin/python apps/backend/analyze.py <file> [--separate] [--transcribe] [--fast] [--yes]

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
1. `dev.sh` — full-stack dev launcher (covered above).
2. `test-e2e.sh` / `test-e2e-integration.sh` — e2e harnesses (covered above).
3. `calibrate_confidence.py` — threshold-sweep harness for the pitch / chord / sidechain detectors. Research-only.

`apps/backend/scripts/`:
1. `bootstrap.sh` — recreate the Python 3.11 venv (covered above).
2. `render_upload_limit_contract.py` — regenerate the operator-facing upload-limit contract text from `upload_limits.py`. Run after changing the canonical limits.
3. `evaluate_phase1.py`, `evaluate_polyphonic.py`, `evaluate_structure_sweep.py` — offline evaluation harnesses for the Phase 1 detector battery, the research polyphonic transcriber, and structure-segmentation parameter sweeps. Wired to `phase1_evaluation.py` / `polyphonic_evaluation.py`.
4. `audit_pass1.py`, `genre_check.py`, `replay_catalog_validation.py` — corpus auditing and Live 12 device-catalog validation. `genre_corpus.md` is the corpus manifest.

## Architecture

### Repo Layout — what's on the product path

`apps/backend/`, `apps/ui/`, and `scripts/` are the product. The remaining top-level directories are off-path and safe to skip unless the task explicitly names them:

1. `advisory/` — auditor notes and one-shot reviews (e.g. `phase1_audit/`). Not imported by either app.
2. `experiments/` — sandbox scratch space (e.g. `crepe_test/` carries only a venv). Throwaway by intent; do not wire production code here.
3. `docs/` — long-form rationale (`ARCHITECTURE_STRATEGY.md`, `history/`). Read these *before* structural changes; do not treat them as living API docs.
4. `tests/ground_truth/` — labeled-corpus fixtures consumed by `scripts/calibrate_confidence.py` (see `tests/ground_truth/README.md`). Not a test suite — each app owns its own (`apps/backend/tests/`, `apps/ui/tests/`).

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

Run-oriented endpoints (`/api/analysis-runs*`) are the canonical interface for staged execution. Legacy `POST /api/analyze`, `POST /api/analyze/estimate`, and `POST /api/phase2` remain only as temporary compatibility wrappers — do not build new functionality on them.

Phase 3 audition-sample generation (`POST/GET /api/analysis-runs/{run_id}/samples`) is **on-demand**, not a queue stage — the UI explicitly requests it after interpretation completes. See `server_samples.py` and the `sample_*.py` modules. On the frontend, `apps/ui/src/components/SamplePlayback.tsx` is the entry point — mounted from `AnalysisResults.tsx` and driven by `src/services/sampleGenerationClient.ts` (`generateSamples` posts, `fetchSamples` retrieves).

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
4. **`analysis_runtime.py`**: SQLite-backed run state and stage queue management. Run state in `.runtime/analysis_runs.sqlite3`; artifacts in `.runtime/artifacts/`.
5. **`worker.py`**: Dedicated worker-process entry point for hosted-style background stage execution. In `local` profile, work runs in-process; in `hosted` profile, this is the worker role.
6. **`runtime_profile.py`**: Switchboard for `local` vs `hosted` profile and `all` vs `api` vs `worker` process roles (env: `SONIC_ANALYZER_RUNTIME_PROFILE`, `SONIC_ANALYZER_PROCESS_ROLE`).
7. **`artifact_storage.py`**: Storage-service boundary. Today writes to local disk; the interface is designed so callers do not assume disk paths forever.
8. **`auth_context.py`**: Hosted-mode user-context resolution and ownership checks on canonical run routes.
9. **`upload_limits.py`**: Canonical 100 MiB raw-audio / 101 MiB request-envelope limits. Regenerate the operator contract via `scripts/render_upload_limit_contract.py` if numbers change.
10. **`spectral_viz.py`**: Librosa-based spectrogram/time-series artifacts. Called after measurement; failures are non-critical.
11. **`url_ingest.py`**: SSRF-guarded URL-mode ingestion for `POST /api/analysis-runs` — fetches a public `http`/`https` audio URL and feeds it through the same downstream pipeline as a multipart upload.
12. **`csv_export.py`**: CSV exporters for Phase 1 time-series fields, backing `GET /api/analysis-runs/{run_id}/export/csv/{field_path}`. Keeps the route handler a thin lookup-and-serve. Field paths are an explicit allowlist (`csv_export.list_supported_fields()` — currently `lufsCurve.shortTerm`, `lufsCurve.momentary`, `rhythmDetail.tempoCurve`, `spectralBalanceTimeSeries`); arbitrary descent into the payload is not supported. Example: `curl http://127.0.0.1:8100/api/analysis-runs/<run_id>/export/csv/rhythmDetail.tempoCurve -o tempo.csv`.
13. **`stage_status.py`**: Collapses the eight internal stage statuses into the additive client-facing `publicStatus` field on every stage snapshot.
14. **`server_samples.py` + `sample_generation.py`, `sample_theory.py`, `sample_synthesis.py`, `sample_drums.py`**: Phase 3 audition-sample generation. `sample_theory.py` builds the PyTheory musical plan, `sample_synthesis.py` renders audio (FluidSynth with sine-additive fallback), `sample_drums.py` synthesizes drum one-shots, `sample_generation.py` orchestrates and emits the citation manifest. On-demand only.
15. **`dsp_bandbank.py` + `dsp_utils.py`**: Shared DSP primitives — `BatchedBandpass` (4th-order Butterworth bandpass bank) and cross-module utility functions.
16. **`phase1_evaluation.py` + `phase1_report_html.py`, `polyphonic_evaluation.py`**: Offline evaluation harnesses (deterministic-metric / detector-stability reporting and research-only polyphonic transcription). Not on the product path; driven by `scripts/evaluate_*.py`.

The subprocess isolation means `analyze.py` works as a standalone CLI. Check `apps/backend/JSON_SCHEMA.md` before adding new analyzer output fields. Check `apps/backend/ARCHITECTURE.md` for the full HTTP flow and contract details.

**Phase 2 (`POST /api/phase2`, legacy compat):** Uploads audio to Gemini inline if ≤100 MiB, or via the Gemini Files API if larger. Phase 1 JSON is appended to the system prompt from `prompts/phase2_system.txt`. Also relevant: `prompts/stem_summary_system.txt` and `prompts/live12_device_catalog.json`.

**Python version constraint:** Python 3.11.x required on macOS arm64. Essentia 2.1b6 wheels are only published for 3.11; this constraint may be relaxable if Essentia publishes 3.12+ wheels.

### Frontend (`apps/ui`)

Single-page React 19 + Vite + TypeScript + Tailwind CSS v4 app with no router. View states managed via React conditionals (upload → estimate → analysis → results). Vitest for unit tests, Playwright for smoke tests.

**Key service files:**

1. **`src/services/analysisRunsClient.ts`**: Canonical transport. Creates runs against `/api/analysis-runs`, polls snapshots, fetches pitch/note translations and interpretations.
2. **`src/services/analyzer.ts`**: Phase orchestration entry point — sequences run creation, polling, and display payload projection.
3. **`src/services/backendPhase1Client.ts`**: Legacy multipart transport (typed error classes, `AbortController` timeouts, identity probe via `/openapi.json`). Kept for the compatibility wrappers; new flows should go through `analysisRunsClient.ts`.
4. **`src/services/spectralArtifactsClient.ts`**: Fetches spectrogram/spectral-evolution artifacts via `/api/analysis-runs/{run_id}/artifacts/…`.
5. **`src/services/mixDoctor.ts`**: Mix advisory logic — client-side scoring and suggestions against measured spectral balance.
6. **`src/services/phase2Validator.ts`**: Runtime guardrail. Validates Phase 2 consistency against Phase 1 (`validateBPMConsistency`, `validateKeyConsistency`, `validateLUFSConsistency`, `validateGenreDSPConsistency`, `validateNumericBounds`).
7. **`src/services/midi/`**: MIDI export, preview, and quantization utilities (`midiExport.ts`, `midiPreview.ts`, `quantization.ts`).
8. **`src/types.ts`** + **`src/types/`**: `types.ts` is a barrel re-export of `./types/{measurement,interpretation,backend}.ts`. `Phase1Result` lives in `types/measurement.ts`; `AnalysisRunSnapshot` in `types/backend.ts`; `Phase2Result` in `types/interpretation.ts`.
9. **`src/config.ts`**: Runtime resolution of `VITE_API_BASE_URL` and feature flags; falls back to `http://127.0.0.1:8100`. Supports window-level overrides (`window.__VITE_API_BASE_URL_OVERRIDE__`, `window.__VITE_ENABLE_PHASE2_GEMINI_OVERRIDE__`) for hosted deployments that inject config at runtime without a rebuild.

`AnalysisResults.tsx` is the large results surface, lazy-loaded via Suspense. Manual vendor chunks in `vite.config.ts` control bundle splitting.

### Frontend-Backend Contract

The interface between apps is `Phase1Result` (in [src/types/measurement.ts](apps/ui/src/types/measurement.ts)) matched against the `phase1` payload inside the analysis-run snapshot (`AnalysisRunSnapshot` in [src/types/backend.ts](apps/ui/src/types/backend.ts)). **Do not rename fields on either side without updating both.** Error envelopes always include `requestId`, `error.code`, `error.message`, `error.retryable`, and `diagnostics`.

## Environment Variables

```bash
# apps/ui/.env (copy from .env.example)
VITE_API_BASE_URL="http://127.0.0.1:8100"
VITE_ENABLE_PHASE2_GEMINI="true"
RUN_GEMINI_LIVE_SMOKE="false"    # set "true" to run live Playwright tests against real Gemini Files API
DISABLE_HMR="false"              # set "true" for dev environments that need HMR disabled

# Backend (env var, no .env file)
SONIC_ANALYZER_PORT=8100
GEMINI_API_KEY="your_key_here"           # read by server.py at runtime, not in browser bundle
SONIC_ANALYZER_ADMIN_KEY="optional"      # if set, DELETE /api/analysis-runs/{run_id} accepts an X-Admin-Key header that bypasses ownership for operator-level purge. Unset by default; admin path is closed.
```

Phase 2 is gated by `VITE_ENABLE_PHASE2_GEMINI`. `GEMINI_API_KEY` is backend-only. `SONIC_ANALYZER_ADMIN_KEY` is backend-only and never exposed to clients.

## Key Guardrails

- **Backend contract:** `analyze.py` stdout → JSON only. `server.py` HTTP shapes → match `types.ts`. Read `apps/backend/ARCHITECTURE.md` and `apps/backend/JSON_SCHEMA.md` before changing analyzer output or HTTP responses.
- **Architecture strategy:** Read `docs/ARCHITECTURE_STRATEGY.md` before proposing structural changes to the dependency stack, transcription pipeline, or layer boundaries.
- **No linter/formatter:** No ESLint, Prettier, or Ruff configured. Follow the style of the surrounding code.
- **Backend tests use stdlib `unittest`**, not pytest. Frontend tests use Vitest in `node` environment (not jsdom).
- **`npm run lint`** only type-checks `src/`; test files and `playwright.config.ts` are excluded from `tsconfig.json`.
- **Canonical ports:** UI on 3100, backend on 8100. `./scripts/dev.sh` fails loudly if either port is occupied.
- **`--fast` flag** runs a streamlined pipeline (BPM, key, loudness, basic dynamics) via `analyze_fast.py`. It is forwarded through the HTTP API via form field or query param.
- **`dsp_json_override`** is accepted by the server but ignored. It's a legacy field; don't repurpose it.

## Tripwires

Things that look like normal code changes but silently break the contract. Most have bitten this codebase before:

1. **`print(...)` in [analyze.py](apps/backend/analyze.py) without `file=sys.stderr`.** Stdout is the JSON contract. Any stray print corrupts it and the server reports a parse error with no useful trace. The existing code is consistent about this — match the pattern (`print(f"[warn] ...", file=sys.stderr)`).
2. **Calling `analyze.py` as a subprocess without `--yes`.** The CLI prompts for confirmation when stdin is a TTY. Subprocess invocations must pass `--yes` or hang waiting for input. `server.py` already does; new callers must too.
3. **Renaming a field on only one side.** Python emits *camelCase* JSON directly (`bpmConfidence`, not `bpm_confidence`) — there is no conversion layer. A rename in [analyze.py](apps/backend/analyze.py) without a matching update in [src/types.ts](apps/ui/src/types.ts) is undetectable by either type system; the field just disappears from the UI.
4. **Adding a top-level key without updating `EXPECTED_TOP_LEVEL_KEYS`.** [tests/test_analyze.py](apps/backend/tests/test_analyze.py) holds a snapshot of every root key. New fields require updating that set *and* [JSON_SCHEMA.md](apps/backend/JSON_SCHEMA.md). The same test enforces that `--fast` only populates `FAST_MODE_POPULATED_FIELDS`.
5. **Using `document` or `window` in `tests/services/`.** Vitest runs in `node`, not `jsdom`. Service-layer tests are pure logic; if you need DOM, it's a Playwright test in `tests/smoke/` instead.
6. **Hard-coding `Path(...)` for artifacts in new code.** Artifact access must go through [artifact_storage.py](apps/backend/artifact_storage.py). Direct paths work in `local` profile and break silently in `hosted`.
7. **Editing `apps/ui/.env` and expecting `dev.sh` to honor it.** `dev.sh` reads `apps/ui/.env` but *overrides* `VITE_API_BASE_URL` for the spawned UI process so stale `.env` files don't break the stack. To point the UI at a non-canonical backend, edit `dev.sh` or run the UI directly with the env var on the command line.
8. **Phase 2 prompts that don't reference Phase 1 measurements.** The chain-of-custody invariant is enforced at runtime by [phase2Validator.ts](apps/ui/src/services/phase2Validator.ts) (`validateBPMConsistency`, `validateKeyConsistency`, `validateLUFSConsistency`, `validateGenreDSPConsistency`). If a prompt change lets Phase 2 emit a contradicting value, the validator surfaces it in the UI as a violation — not a silent failure, but worth knowing where the check lives.

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

- **Backend and frontend monoliths were intentionally split** (commit `5c40dd44`, "refactor: split monoliths into domain modules") into domain modules — `analyze_core/_detection/_rhythm/_segments/_structure/_transcription` on the backend, focused service files on the frontend. The split is the current target shape; resist consolidating it back.
- **Hosted runtime foundation landed without disturbing local mode.** `runtime_profile.py`, `worker.py`, `artifact_storage.py`, and `auth_context.py` are the seams. Local-mode code should not branch on profile unless it has to; the boundary handles it.

## Backport Candidates

Most of the original `sonic-architect-app` port (genre profiles, Ableton device mappings, mix doctor, eight detectors) is **shipped**, as is Phase 3 audition-sample generation. The remaining open item in [`BACKLOG.md`](BACKLOG.md) is `patchSmith.ts` (Phase 3 synth-patch generation — distinct from audition samples, which validate measurements rather than producing a saveable preset). Consult `BACKLOG.md` before re-implementing genre detection, mix analysis, acid/reverb/vocal/supersaw/bass/kick detection — they're already in [`apps/backend/analyze_detection.py`](apps/backend/analyze_detection.py) and emit fields visible in `EXPECTED_TOP_LEVEL_KEYS`.

## Companion Agent Docs

This repo carries parallel guidance for non-Claude agents:

1. **`AGENTS.md`** (root) — pointer for Codex / OpenHands / any tool that looks for `AGENTS.md` by name. Defers to this file.
2. **`apps/backend/AGENTS.md`**, **`apps/ui/AGENTS.md`** — per-app overlays with technology-stack details and app-specific change checklists.
3. **`docs/ARCHITECTURE_STRATEGY.md`** — *why* the three-layer architecture is shaped the way it is.
4. **`docs/history/`** — completed plans and one-shot audits. Past-tense, not living docs.

When information conflicts: `PURPOSE.md` > this file > per-app `AGENTS.md`.

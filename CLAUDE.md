# CLAUDE.md

**Read `PURPOSE.md` before making any changes.** It defines why ASA exists and the non-negotiable quality invariants.

Short version: ASA helps intermediate Ableton Live 12 producers answer "how do I make something that sounds like this?" by running deterministic DSP measurements (Phase 1) and feeding them to an AI interpreter (Phase 2) that produces specific, measurement-cited Ableton device recommendations. The chain of custody from number to recommendation is the product.

**Quality invariants (non-negotiable):**
1. Phase 1 measurements are ground truth. Phase 2 never overrides them.
2. Every Phase 2 recommendation cites the specific measurement(s) that justify it.
3. Recommendations name exact Ableton Live 12 devices, parameters, and values.
4. Low-confidence measurements produce hedged recommendations, not confident guesses.
5. Phase 2 covers the full production surface (kick, bass, melody, groove, effects, stereo, mastering).
6. Results are accessible to intermediate producers without DSP expertise.

## Commands

First-time local setup is documented in [`docs/SETUP.md`](docs/SETUP.md).

### `asa` developer CLI

```bash
asa                 # full stack (UI 3100 + backend 8100)
asa backend         # backend only (port 8100)
asa frontend        # UI only (port 3100)
asa stop            # free ports 3100 + 8100
asa status          # preflight
asa verify          # frontend verify + backend tests
asa analyze <file>  # run Phase 1 analyzer (always passes --yes)
```

### Frontend (`apps/ui`)

```bash
npm run dev:local                   # dev on 127.0.0.1:3100
npm run verify                      # lint + test:unit + build + test:smoke
npm run test:smoke                  # Playwright smoke suite
npm run test:smoke:live-gemini      # live Gemini smoke (requires key)
```

### Backend (`apps/backend`)

```bash
./apps/backend/scripts/bootstrap.sh         # recreate venv (Python 3.11.x)
./apps/backend/venv/bin/python server.py    # FastAPI on 8100
./apps/backend/venv/bin/python analyze.py <file> [--separate] [--transcribe] [--fast] [--yes]
./venv/bin/python -m unittest discover -s tests
```

### End-to-End

```bash
./scripts/test-e2e-integration.sh   # local-only, real backend + UI
TEST_FLAC_PATH=... GEMINI_API_KEY=... VITE_ENABLE_PHASE2_GEMINI=true ./scripts/test-e2e.sh
```

See the full original `CLAUDE.md` (pre-Wave 4) or `apps/backend/AGENTS.md` / `apps/ui/AGENTS.md` for the complete script catalog.

## One-Request Trace + Contracts

```
file in FileUpload.tsx
   └─▶ analysisRunsClient.ts (multipart POST /api/analysis-runs)
        └─▶ server.py + analysis_runtime.py (persist run, enqueue stages)
             └─▶ analyze.py subprocess with --yes  ──▶ stdout: camelCase JSON
                  └─▶ server.py normalizes into `phase1` envelope
                       └─▶ analysisRunsClient.ts polls snapshot
                            └─▶ analyzer.ts projects display payload
                                 └─▶ AnalysisResults.tsx renders
                                      └─▶ phase2Validator.ts checks chain of custody
```

The two contracts: `analyze.py` stdout (raw schema in `apps/backend/JSON_SCHEMA.md`) and the `phase1` HTTP envelope (`apps/ui/src/types.ts`).

**Backend contract:** `analyze.py` stdout → JSON only. `server.py` HTTP shapes → match `types.ts`. Read `apps/backend/ARCHITECTURE.md` and `apps/backend/JSON_SCHEMA.md` before changing analyzer output or HTTP responses.

**Frontend contract:** `Phase1Result` (types/measurement.ts) must match `phase1` in the run snapshot (types/backend.ts). Do not rename fields on only one side.

## Architecture Pointers

- **Backend core files:** see `apps/backend/ARCHITECTURE.md` (analyze.py + analyze_*.py modules, server.py + server_phase*.py, analysis_runtime.py, live12_catalogue.py, phase2_catalogue_gates.py, recommendations_contract.py, phase2_provider.py, separation_backend.py, loudness_backend.py, etc.).
- **Frontend key services:** see `apps/ui/ARCHITECTURE.md` (analysisRunsClient.ts, analyzer.ts, phase2Validator.ts, recommendationsContract.ts, patchSmith.ts, browserLoudness/, etc.).
- **Three-layer model:** Layer 1 (Essentia/DSP measurement) → Layer 2 (torchcrepe pitch/note on stems) → Layer 3 (Gemini interpretation). Phase 2 never overrides Phase 1.
- **Staged runs:** measurement → pitch/note translation → interpretation → mt3 (optional). Phase 3 samples are on-demand.
- **Runtime profiles:** local (default) vs hosted (non-goal). Local product path is unaffected.

Frozen/optional subsystems (MT3, Phase 3 samples, PatchSmith, hosted) carry `FROZEN 2026-07` banners. See `docs/OPTIONAL_BACKENDS.md`.

**Python version:** 3.11.x required on macOS arm64 (Essentia 2.1b6 wheels).

## Environment Variables

Product vars (see `docs/OPTIONAL_BACKENDS.md` for frozen-experiment vars):

```bash
# apps/ui/.env
VITE_API_BASE_URL="http://127.0.0.1:8100"
VITE_ENABLE_PHASE2_GEMINI="true"

# Backend (no .env file)
SONIC_ANALYZER_PORT=8100
GEMINI_API_KEY="your_key_here"          # AI Studio (legacy)
# Vertex AI + ADC (preferred; bills to Cloud credits):
# GOOGLE_CLOUD_PROJECT=your-project-id
# ASA_GCP_PROJECT=...                   # alias
# ASA_GEMINI_BACKEND=vertex             # auto if project set; or "apistudio"
# GOOGLE_CLOUD_LOCATION=us-central1     # optional (default)
SONIC_ANALYZER_ADMIN_KEY="optional"
ASA_SAMPLE_SYNTH_BACKEND="auto"
ASA_SEPARATION_BACKEND="demucs"
ASA_PHASE2_PROVIDER="gemini"
ASA_CLAUDE_CLI="claude"
```

Phase 2 is gated by `VITE_ENABLE_PHASE2_GEMINI`. Gemini backend config uses `GEMINI_API_KEY` (AI Studio) or Vertex ADC + `GOOGLE_CLOUD_PROJECT` (or `ASA_GCP_PROJECT`). `ASA_GEMINI_BACKEND` forces the path.

## Key Guardrails

- No linter/formatter (follow surrounding style).
- Backend tests use stdlib `unittest`; frontend uses Vitest in `node` (not jsdom).
- `npm run lint` only type-checks `src/`; `tests/`, `dist/`, `node_modules/` are excluded.
- Canonical ports: UI 3100, backend 8100.
- `--fast` runs the streamlined pipeline; `dsp_json_override` is accepted but ignored.

## Tripwires

Things that look like normal code changes but silently break the contract:

1. `print(...)` in `analyze.py` without `file=sys.stderr`. Stdout is the JSON contract.
2. Calling `analyze.py` as a subprocess without `--yes`. The CLI prompts for confirmation.
3. Renaming a field on only one side. Python emits camelCase JSON directly; the ~12 `parseOptional*` reconstructors in `backendPhase1Client.ts` rebuild block-by-block.
4. Adding a top-level key without updating `EXPECTED_TOP_LEVEL_KEYS` in `tests/test_analyze.py` and `JSON_SCHEMA.md`.
5. Using `document` or `window` in `tests/services/`. Vitest runs in `node`, not jsdom.
6. Hard-coding `Path(...)` for artifacts. Use `artifact_storage.py`.
7. Editing `apps/ui/.env` and expecting `dev.sh` to honor it. `dev.sh` overrides `VITE_API_BASE_URL`.
8. Phase 2 prompts that don't reference Phase 1 measurements. `phase2Validator.ts` and `_validate_phase2_citation_paths` will surface violations.
9. Editing one side of the audio MIME map without the other (`audio_mime.py` and `audioFile.ts`).
10. Assuming `truePeak` is linear or `bpmConfidence` is the raw Essentia value (ADR 0002: dBTP and 0–1 normalized; `phase1Version: "phase1.v2"`).

## Where to Make the Change

| If you're changing… | Touch | Then |
|---|---|---|
| What gets measured | `analyze.py` + relevant `analyze_*.py` | Update `JSON_SCHEMA.md`, `EXPECTED_TOP_LEVEL_KEYS`, `src/types.ts` |
| How a measurement renders | `apps/ui/src/components/` | Add Vitest coverage in `tests/services/` if new parsing/projection |
| How Phase 2 advises | `prompts/phase2_system.txt` + `live12_device_catalog.json` | Verify with live Gemini smoke |
| The HTTP envelope shape | `server.py` (router) + `server_*.py` | `test_server.py` + frontend client types |
| Run-state or stage flow | `analysis_runtime.py` | Frontend polling in `analysisRunsClient.ts` |
| Upload limits or proxies | `upload_limits.py` | Regenerate via `scripts/render_upload_limit_contract.py` |
| Hosted-mode behavior | `runtime_profile.py`, `auth_context.py`, `worker.py` | Keep the `local` profile path unaffected |

## Debugging Recipes

- "UI missing a field": hit `/openapi.json`, run `analyze.py <file> --yes`, grep stdout.
- "No usable JSON": re-run `analyze.py`; search for `print(` without `file=sys.stderr`.
- "Backend test passes locally, fails fresh": recreate venv with `./apps/backend/scripts/bootstrap.sh`.
- "Phase 2 contradicts measurements": open result in UI; `phase2Validator.ts` violations are the source of truth.
- "Hung subprocess": run `analyze.py <file>` without `--yes` to see the confirmation prompt.

## Recent Refactors (don't undo)

- Backend/frontend monoliths intentionally split into domain modules (`analyze_*.py`; `src/services/*`). Resist consolidating.
- Hosted runtime foundation landed without disturbing local mode (`runtime_profile.py`, `worker.py`, `artifact_storage.py`, `auth_context.py`).
- UI design-system migration ("D-series"): primitives in `src/components/ui/`, semantic tokens in `src/index.css`. Build from these; don't reintroduce one-off boxes or raw hex.
- WASM loudness package archived in the 2026-07 trust diet (`archive/loudness-spectro-wasm`). Backend `loudness_backend.py` still degrades to Essentia when measure-cli is absent; leave Essentia authoritative for LUFS scalars. Product reassigned-spectrogram uses librosa.

## Backport Candidates

Full original backlog is shipped (genre profiles, Ableton device mappings, mix doctor, eight detectors, Phase 3 samples, patchSmith). See `BACKLOG.md`. Consult before re-implementing — already in `analyze_detection.py` and `EXPECTED_TOP_LEVEL_KEYS`.

## Companion Agent Docs

1. `AGENTS.md` (root) — pointer for Codex / OpenHands. Defers to this file.
2. `apps/backend/AGENTS.md`, `apps/ui/AGENTS.md` — per-app overlays with stack details and change checklists.
3. `docs/ARCHITECTURE_STRATEGY.md` — why the three-layer design is shaped the way it is.
4. Recommendation-proof campaign: `GOAL.md` retired 2026-07-18 (recover via git history). `apps/backend/NEEDS.md` and `RECOMMENDATION_VERDICT.md` are PROXY-SCORED — non-authoritative; do not cite as settled. Current record: `plans/trust-diet-closeout-2026-07.md`.
5. `docs/history/` — archived (trust diet Wave 1). Restore via `git checkout archive/pre-trust-diet-2026-07 -- docs/history`.
6. `docs/adr/` — Architecture Decision Records (schema stability, loudness units, recommendations contract).

When information conflicts: `PURPOSE.md` > `CLAUDE.md` > per-app `AGENTS.md`.

# sonic-analyzer-UI

React and Vite frontend for the Sonic Analyzer workflow.

The app uploads a track to the local DSP backend, shows the estimate and execution status for measurement plus downstream stages, optionally runs AI interpretation, and renders the returned analysis in a browser UI.

## Current Features

 - file upload with drag-and-drop and file picker, audio type validation with extension fallback when browser MIME is blank, and local audio preview
- file size warning for uploads exceeding 100 MB (non-blocking)
- inline error messages for invalid files with dismiss and retry controls
- automatic measurement estimate request on file selection
- local DSP execution status with elapsed time, stage estimates, and progress bar
- cancel button during analysis with end-to-end abort handling across measurement and AI interpretation
- optional pitch/note translation toggle for the backend request
- optional Demucs stem separation toggle for the backend request, independent of pitch/note translation
- optional Gemini AI interpretation pass with a selectable model
- analysis result dashboard with arrangement, sonic, mix-chain, patch, and secret-sauce sections
- Session Musician panel with:
  - pitch/note view when `transcriptionDetail` exists
  - Essentia melody guide when `melodyDetail` exists
  - source toggle when both are available
  - confidence threshold slider (pitch/note mode only; disabled in melody-guide mode with tooltip)
  - quantize grid and swing controls
  - browser preview and `.mid` download
- JSON export and markdown report export
- collapsible diagnostic log with request IDs, durations, estimate ranges, and backend or Gemini status
- semantic theme token system for status colors and surface backgrounds
- mobile-responsive layouts across header, results grid, and upload flow
- optimised initial bundle: 48kB entry chunk via Vite manual chunk splitting and lazy-loaded result components with skeleton fallback

## Tech Stack

- React 19
- TypeScript
- Vite 6
- Tailwind CSS v4
- WaveSurfer.js
- Google Gen AI SDK
- MIDI Writer JS
- Vitest
- Playwright

## Prerequisites

- Node.js 20+
- npm
- a running `sonic-analyzer` backend

Recommended backend URL for the current Python server:

- `http://127.0.0.1:8100`

## Environment

Copy `.env.example` to `.env` and set the values you want to use.

```bash
cp .env.example .env
```

### Variables

| Variable | Meaning | Current behavior |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Base URL for the backend API. | `src/config.ts` falls back to `http://127.0.0.1:8100` when unset. The checked-in `.env.example` uses `http://127.0.0.1:8100`. If another FastAPI app is answering on your configured URL, the UI now reports that it found the wrong service and disables `Run Analysis`. |
| `VITE_ENABLE_PHASE2_GEMINI` | Hard kill-switch for the optional Gemini interpretation pass. | Defaults to `"true"` when unset. Set it to `"false"` only when you want to disable AI interpretation for the whole build. |
| `RUN_GEMINI_LIVE_SMOKE` | Enables the opt-in live Playwright proof for the Gemini Files API path. | Must be `"true"` to run `npm run test:smoke:live-gemini`; default smoke coverage keeps Gemini mocked. |
| `DISABLE_HMR` | Vite dev-server knob. | `vite.config.ts` disables HMR only when this is `"true"`. |

Gemini interpretation is now backend-mediated. The backend reads `GEMINI_API_KEY` from the shell environment; the UI does not consume `VITE_GEMINI_API_KEY`.

## Running Locally

Recommended full-stack launcher from the monorepo root:

```bash
./scripts/dev.sh
```

`./scripts/dev.sh` now reads `apps/ui/.env` before starting Vite. The simplest
persistent local setup is:

```bash
cd apps/ui
cp .env.example .env
```

Then set:

```bash
VITE_API_BASE_URL="http://127.0.0.1:8100"
VITE_ENABLE_PHASE2_GEMINI="true"
```

Supported shell-based overrides:

```bash
export GEMINI_API_KEY="your_real_key_here"
cd /Users/christiansmith/code/projects/asa
./scripts/dev.sh
```

```bash
cd /Users/christiansmith/code/projects/asa
GEMINI_API_KEY="your_real_key_here" ./scripts/dev.sh
```

This does **not** work because the variable is only local to the shell line and
is not exported to the next command:

```bash
GEMINI_API_KEY="your_real_key_here"
./scripts/dev.sh
```

Manual equivalent from the monorepo root:

```bash
cd apps/backend
SONIC_ANALYZER_PORT=8100 ./venv/bin/python server.py
```

```bash
cd apps/ui
VITE_API_BASE_URL=http://127.0.0.1:8100 npm run dev:local
```

Canonical local URLs:

- UI: `http://127.0.0.1:3100`
- backend: `http://127.0.0.1:8100`

Legacy note:

- older local `.env` files may still pin `VITE_API_BASE_URL=http://localhost:8000` or `http://127.0.0.1:8010`
- the monorepo root `./scripts/dev.sh` overrides those stale values for the spawned UI process
- `npm run dev` remains available for custom local setups, but it is not the recommended synced-stack command

## Backend Contract Used by the UI

The app talks to two backend routes.

### `POST /api/analysis-runs/estimate`

When it runs:

- automatically after the user selects a file

What the UI sends today:

- multipart `track`
- multipart `pitch_note_mode`
- multipart `pitch_note_backend`
- multipart `interpretation_mode`
- multipart `interpretation_profile`
- multipart `interpretation_model` when interpretation is enabled

What the UI expects back:

- `requestId`
- `estimate.durationSeconds`
- `estimate.totalLowMs`
- `estimate.totalHighMs`
- `estimate.stages[]` with `key`, `label`, `lowMs`, and `highMs`

Current note:

- the UI uses this response only for display
- if this request fails, the app still lets the user start analysis

### `POST /api/analysis-runs`

When it runs:

- after the user clicks `Run Analysis`

What the UI sends today:

- multipart `track`
- multipart `pitch_note_mode=stem_notes|off` based on the pitch/note translation toggle
- multipart `pitch_note_backend=auto`
- multipart `interpretation_mode=async|off` based on the interpretation toggle and config gate
- multipart `interpretation_profile=producer_summary`
- multipart `interpretation_model` when interpretation is enabled

### Known Behavior

- the canonical UI flow no longer uses the legacy `POST /api/analyze` wrapper
- the UI polls `GET /api/analysis-runs/{run_id}` and derives display-oriented `phase1` and `phase2` views from the run snapshot

### Success Response

The UI expects the canonical run-creation response to contain:

- `runId`
- `requestedStages`
- `stages`
- `artifacts`

Core measurement fields the app depends on after projection:

- `bpm`
- `bpmConfidence`
- `key`
- `keyConfidence`
- `timeSignature`
- `durationSeconds`
- `lufsIntegrated`
- `lufsRange`
- `truePeak`
- `crestFactor`
- `stereoWidth`
- `stereoCorrelation`
- `spectralBalance`

Expanded `phase1` sections the current app can consume:

- `stereoDetail`
- `spectralDetail`
- `rhythmDetail`
- `melodyDetail`
- `transcriptionDetail`
- `grooveDetail`
- `sidechainDetail`
- `effectsDetail`
- `synthesisCharacter`
- `danceability`
- `structure`
- `arrangementDetail`
- `segmentLoudness`
- `segmentSpectral`
- `segmentKey`
- `chordDetail`
- `perceptual`

Diagnostics fields the UI uses or preserves:

- `backendDurationMs`
- `engineVersion`
- `estimatedLowMs`
- `estimatedHighMs`
- `timeoutSeconds`
- `timings.totalMs`
- `timings.analysisMs`
- `timings.serverOverheadMs`
- `timings.flagsUsed`
- `timings.msPerSecondOfAudio`
- `stdoutSnippet`
- `stderrSnippet`

Important current limitations:

- the backend omits raw analyzer fields such as `bpmPercival`, `bpmAgreement`, `dynamicCharacter`, `segmentStereo`, and `essentiaFeatures`, so the UI never receives them from `server.py`

### Error Response

The UI also understands the backend error envelope:

- `requestId`
- `error.code`
- `error.message`
- `error.phase`
- `error.retryable`
- optional `diagnostics`

This is what powers the visible backend error message and the diagnostic log entries.

## AI Interpretation

AI interpretation is optional and backend-mediated.

Current behavior:

- AI interpretation is on by default unless `VITE_ENABLE_PHASE2_GEMINI="false"` is used as a hard kill-switch.
- The app remembers the user's AI interpretation toggle in browser storage.
- The backend must have `GEMINI_API_KEY` in its shell environment before interpretation can run.
- The user can choose from the baked-in Gemini model list in `src/App.tsx`.
- The prompt uses the uploaded audio file plus the completed measurement payload and any server-owned downstream context.
- Phase 2 results drive the arrangement narrative, sonic element cards, mix chain, patch framework, secret sauce, and recommendation sections.
- Audio files at or below 100MB are sent to Gemini as inline base64. Audio files above 100MB are uploaded via the Gemini Files API before generation and deleted immediately after; the diagnostic log shows upload and generation durations separately.

## Export Behavior

Available exports after Phase 1 completes:

- `track-analysis.json`
- `track-analysis.md`
- `track-analysis.mid` from the Session Musician panel when note data is available

## Validation

```bash
npm run lint
npm run test:unit
npm run build
npm run test:smoke
```

Or run everything:

```bash
npm run verify
```

Notes about tests:

- most smoke tests stub the backend and Gemini calls
- `tests/smoke` remains the mocked, CI-friendly UI-contract layer
- `tests/e2e/analysis-runs-integration.spec.ts` is the canonical no-Gemini integration proof and uses the current staged runtime contract: `POST /api/analysis-runs/estimate`, `POST /api/analysis-runs`, `GET /api/analysis-runs/{run_id}`, and artifact endpoints
- the no-Gemini integration lane generates its own local WAV, boots the real backend, and keeps AI interpretation off
- the full live Gemini lane stays separate and requires:
  - `TEST_FLAC_PATH` pointing at a readable audio file
  - `GEMINI_API_KEY` in the backend environment
  - `VITE_ENABLE_PHASE2_GEMINI=true`
- `tests/smoke/upload-phase1-live.spec.ts` is a lightweight opt-in proof against the canonical `analysis-runs` flow
- `tests/smoke/upload-phase2-live-gemini.spec.ts` is an opt-in Files API proof using a generated `>100MB` WAV and backend-mediated Gemini

Run the canonical no-Gemini local integration suite:

```bash
./scripts/test-e2e-integration.sh
```

Run the same no-Gemini lane directly from `apps/ui` when the backend is already up on `http://127.0.0.1:8100`:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8100 \
npm run test:e2e:integration
```

Run the separate full live Gemini suite:

```bash
TEST_FLAC_PATH=/path/to/track.flac \
GEMINI_API_KEY=your_real_key_here \
VITE_ENABLE_PHASE2_GEMINI=true \
VITE_API_BASE_URL=http://127.0.0.1:8100 \
./scripts/test-e2e.sh
```

Run the lightweight live backend smoke explicitly:

```bash
TEST_FLAC_PATH=/path/to/track.flac \
VITE_API_BASE_URL=http://127.0.0.1:8100 \
npm run test:smoke -- tests/smoke/upload-phase1-live.spec.ts
```

Run the live Gemini Files API smoke explicitly:

```bash
RUN_GEMINI_LIVE_SMOKE=true \
VITE_ENABLE_PHASE2_GEMINI=true \
GEMINI_API_KEY=your_real_key_here \
VITE_API_BASE_URL=http://127.0.0.1:8100 \
npm run test:smoke:live-gemini
```

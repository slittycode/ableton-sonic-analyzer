# sonic-analyzer-UI

React and Vite frontend for the Sonic Analyzer workflow.

The app uploads a track to the local DSP backend, shows the estimate and execution status for Phase 1, optionally runs a Gemini advisory pass for Phase 2, and renders the returned analysis in a browser UI.

## Current Features

 - file upload with drag-and-drop and file picker, audio type validation with extension fallback when browser MIME is blank, and local audio preview
- file size warning for uploads exceeding 100 MB (non-blocking)
- inline error messages for invalid files with dismiss and retry controls
- automatic Phase 1 estimate request on file selection
- local DSP execution status with elapsed time, stage estimates, and progress bar
 - cancel button during analysis with end-to-end abort handling across Phase 1 and Phase 2
- optional Basic Pitch transcription toggle for the backend request
- optional Demucs stem separation toggle for the backend request, independent of MIDI transcription
- optional Gemini Phase 2 advisory pass with a selectable model
- analysis result dashboard with arrangement, sonic, mix-chain, patch, and secret-sauce sections
- Session Musician panel with:
  - polyphonic Basic Pitch note view when `transcriptionDetail` exists
  - monophonic Essentia note view when `melodyDetail` exists
  - source toggle when both are available
  - confidence threshold slider (polyphonic mode only; disabled in monophonic mode with tooltip)
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
| `VITE_API_BASE_URL` | Base URL for the backend API. | `src/config.ts` falls back to `http://127.0.0.1:8100` when unset. The checked-in `.env.example` uses `http://127.0.0.1:8100`. If another FastAPI app is answering on your configured URL, the UI now reports that it found the wrong service and disables `Initiate Analysis`. |
| `VITE_ENABLE_PHASE2_GEMINI` | Enables the optional Gemini pass. | Must be `"true"` to allow Phase 2. |
| `VITE_GEMINI_API_KEY` | Gemini API key. | Phase 2 only runs when this value is non-empty and `VITE_ENABLE_PHASE2_GEMINI=true`. |
| `RUN_GEMINI_LIVE_SMOKE` | Enables the opt-in live Playwright proof for the Gemini Files API path. | Must be `"true"` to run `npm run test:smoke:live-gemini`; default smoke coverage keeps Gemini mocked. |
| `DISABLE_HMR` | Vite dev-server knob. | `vite.config.ts` disables HMR only when this is `"true"`. |

## Running Locally

Recommended synced launcher from the workspace root:

```bash
cd /Users/christiansmith/code/projects/sonic-analyzer-workspace
./scripts/dev.sh
```

Manual equivalent:

```bash
cd /Users/christiansmith/code/projects/sonic-analyzer-workspace/sonic-analyzer
SONIC_ANALYZER_PORT=8100 ./venv/bin/python server.py
```

```bash
cd /Users/christiansmith/code/projects/sonic-analyzer-workspace/sonic-analyzer-UI
VITE_API_BASE_URL=http://127.0.0.1:8100 npm run dev:local
```

Canonical local URLs:

- UI: `http://127.0.0.1:3100`
- backend: `http://127.0.0.1:8100`

Legacy note:

- older local `.env` files may still pin `VITE_API_BASE_URL=http://localhost:8000` or `http://127.0.0.1:8010`
- `./scripts/dev.sh` overrides those stale values for the spawned UI process
- `npm run dev` remains available for custom local setups, but it is not the recommended synced-stack command

## Backend Contract Used by the UI

The app talks to two backend routes.

### `POST /api/analyze/estimate`

When it runs:

- automatically after the user selects a file

What the UI sends today:

- multipart `track`
- multipart `transcribe=false`
- no `separate` query parameter

What the UI expects back:

- `requestId`
- `estimate.durationSeconds`
- `estimate.totalLowMs`
- `estimate.totalHighMs`
- `estimate.stages[]` with `key`, `label`, `lowMs`, and `highMs`

Current note:

- the UI uses this response only for display
- if this request fails, the app still lets the user start Phase 1

### `POST /api/analyze`

When it runs:

- after the user clicks `Initiate Analysis`

What the UI sends today:

- multipart `track`
- multipart `transcribe=true|false` based on the MIDI transcription toggle
- multipart `separate=true|false` based on the stem separation toggle
- no `separate` query parameter

### Known Behavior

- the UI no longer exposes `dsp_json_override` because the current backend ignores it
- the frontend client transport still supports `dsp_json_override` as a reserved multipart field, but the visible App flow does not send it

What the backend actually does with those fields today:

- `track` is required and used
- `transcribe` is used by `server.py`

### Success Response

The UI expects the backend success envelope to contain:

- `requestId`
- `phase1`
- `diagnostics`

Core `phase1` fields the app depends on:

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

## Phase 2

Phase 2 is optional and entirely frontend-owned.

Current behavior:

- Phase 2 is skipped when Gemini is disabled or `VITE_GEMINI_API_KEY` is missing.
- The user can choose from the baked-in Gemini model list in `src/App.tsx`.
- The prompt uses the uploaded audio file plus the completed `phase1` payload.
- Phase 2 results drive the arrangement narrative, sonic element cards, mix chain, patch framework, secret sauce, and recommendation sections.
- Audio files at or below 20MB are sent to Gemini as inline base64. Audio files above 20MB are uploaded via the Gemini Files API before generation and deleted immediately after; the diagnostic log shows upload and generation durations separately.

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
- `tests/smoke/upload-phase1-live.spec.ts` checks a real backend if `VITE_API_BASE_URL` is reachable
- `tests/smoke/upload-phase1-live.spec.ts` uses `TEST_FLAC_PATH` when it points to an existing file, otherwise it silently falls back to `tests/smoke/fixtures/silence.wav`
- `tests/smoke/upload-phase2-live-gemini.spec.ts` is opt-in and checks the real Gemini Files API path against a generated `>20MB` WAV when `RUN_GEMINI_LIVE_SMOKE=true`, `VITE_ENABLE_PHASE2_GEMINI=true`, and `VITE_GEMINI_API_KEY` is set

Run the live backend smoke against a real FLAC when one is available:

```bash
TEST_FLAC_PATH=/path/to/track.flac \
VITE_API_BASE_URL=http://127.0.0.1:8100 \
npm run test:smoke -- tests/smoke/upload-phase1-live.spec.ts
```

Run the live Gemini proof explicitly:

```bash
RUN_GEMINI_LIVE_SMOKE=true \
VITE_ENABLE_PHASE2_GEMINI=true \
VITE_GEMINI_API_KEY=your_key_here \
VITE_API_BASE_URL=http://127.0.0.1:8100 \
npm run test:smoke:live-gemini
```

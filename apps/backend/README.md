# sonic-analyzer

Local audio analysis backend for the Sonic Analyzer workflow.

This repo contains two entry points:

- `analyze.py`: the raw CLI that runs Essentia-based analysis and prints JSON to `stdout`
- `server.py`: a FastAPI wrapper that accepts uploads, runs `analyze.py`, and returns a normalized HTTP contract for the UI

## Current Scope

`analyze.py` measures tempo, key, loudness, stereo, rhythm, melody, arrangement, segment-level metrics, chord content, perceptual features, optional Demucs separation, and optional torchcrepe pitch/note translation.

`server.py` now exposes a staged canonical runtime API plus legacy compatibility wrappers.

Canonical live-analysis routes:

- `POST /api/analysis-runs/estimate`
- `POST /api/analysis-runs`
- `GET /api/analysis-runs/{run_id}`
- `GET /api/analysis-runs/{run_id}/artifacts...`

Legacy compatibility routes:

- `POST /api/analyze` (legacy compatibility wrapper)
- `POST /api/phase2` (legacy compatibility wrapper)

FastAPI also serves the usual generated endpoints at `/openapi.json`, `/docs`, and `/redoc`.

## Tech Stack

- Python 3.10+
- Essentia
- NumPy
- Demucs
- torchcrepe (pitch/note translation)
- mido
- FastAPI
- Uvicorn

## Installation

```bash
./scripts/bootstrap.sh
```

Manual equivalent:

```bash
python3.11 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

Bootstrap contract for this monorepo `v1.0.0` cut:

- the pinned full-feature local baseline is Python `3.11.x` on macOS arm64
- Python `3.12+` is not a supported full-feature bootstrap target on macOS arm64 because Essentia 2.1b6 wheels are only published for 3.11 on arm64

## CLI Usage

### Command

```bash
./venv/bin/python analyze.py <audio_file> [--separate] [--transcribe] [--fast] [--yes] [--pitch-note-backend BACKEND]
```

### Flags

| Flag | Current behavior |
| --- | --- |
| `<audio_file>` | Required input path. |
| `--separate` | Runs Demucs before melody analysis. If `--transcribe` is also enabled, the selected pitch backend uses the `bass` and `other` stems when they exist. |
| `--transcribe` | Runs the selected pitch backend and returns `transcriptionDetail`. Without Demucs it transcribes the full mix; with Demucs it transcribes `bass` and `other` separately and merges the notes. |
| `--pitch-note-backend BACKEND` | Selects the Layer 2 backend for `--pitch-note-only`. Supported values are `auto`, `torchcrepe-viterbi`, and alias `torchcrepe`. |
| `--fast` | Runs the reduced fast-analysis preset. Core fields such as BPM, key, duration, LUFS, true peak, and crest factor are populated; most detail-heavy fields remain `null`. |
| `--yes` | Skips the interactive confirmation prompt after the CLI prints its runtime estimate. |

### Runtime Behavior

- If the CLI is attached to a TTY and `--yes` is not supplied, it prints an estimate and asks for confirmation before starting.
- JSON output is written to `stdout`.
- Logs, warnings, and progress updates are written to `stderr`.
- Temporary Demucs stems are deleted at the end of a `--separate` run.

### Examples

```bash
./venv/bin/python analyze.py track.wav
./venv/bin/python analyze.py track.wav --separate --yes
./venv/bin/python analyze.py track.wav --transcribe --yes
./venv/bin/python analyze.py track.wav --pitch-note-only --pitch-note-backend torchcrepe-viterbi --yes
./venv/bin/python analyze.py track.wav --separate --transcribe --yes > analysis.json
```

### PENN assessment outcome

PENN was evaluated as an alternative Layer 2 backend and then removed.

In plain English: it did not produce a useful quality win over the existing stem-aware torchcrepe path, it was slower in local benchmarks, and it added extra setup cost and first-run model downloads. ASA stays on `torchcrepe-viterbi` for pitch/note translation.

### Polyphonic full-track research spike

ASA does not ship a production polyphonic full-track transcription backend.

In plain English: for dense mixed songs, current public models still do not clear the quality bar needed for a reliable producer feature. If you want to compare research candidates anyway, use the offline harness:

```bash
./venv/bin/python scripts/evaluate_polyphonic.py --manifest /absolute/path/to/polyphonic_manifest.json
```

That harness is isolated from the product runtime. It writes MIDI or note-event artifacts plus a JSON report, and it supports:

- `basic-pitch` as the lightweight baseline when installed in the active environment
- `MT3` through an explicit `--mt3-command` template when you have a local runner or Colab-exported wrapper
- optional Demucs stem exports for diagnostics only

See [docs/POLYPHONIC_TRANSCRIPTION_SPIKE.md](../../docs/POLYPHONIC_TRANSCRIPTION_SPIKE.md) for the manifest format, command examples, and the manual usefulness gates.

## Raw CLI Output

The raw `analyze.py` payload is documented in [JSON_SCHEMA.md](JSON_SCHEMA.md).

Notable top-level sections include:

- core timing and loudness fields such as `bpm`, `key`, `durationSeconds`, `lufsIntegrated`, and `truePeak`
- detailed objects such as `dynamicCharacter`, `stereoDetail`, `spectralDetail`, `rhythmDetail`, `melodyDetail`, `transcriptionDetail`, `effectsDetail`, `arrangementDetail`, and `essentiaFeatures`
- segment-level outputs such as `segmentLoudness`, `segmentStereo`, `segmentSpectral`, and `segmentKey`

## Running the HTTP Server

Recommended full-stack launcher from the monorepo root:

```bash
./scripts/dev.sh
```

If the root launcher reports a missing backend virtualenv, create it first with:

```bash
./apps/backend/scripts/bootstrap.sh
```

The root launcher starts the backend on `http://127.0.0.1:8100`, waits for the FastAPI contract to come up, then starts the monorepo UI on `http://127.0.0.1:3100` with `VITE_API_BASE_URL=http://127.0.0.1:8100`.

If `apps/ui/.env` still contains `http://localhost:8000`, the root launcher prints a warning and overrides it for that session so the UI does not hit the wrong local service by mistake.

Manual backend command:

```bash
SONIC_ANALYZER_PORT=8100 ./venv/bin/python server.py
```

Manual full-stack pair from the monorepo root:

```bash
cd apps/backend
SONIC_ANALYZER_PORT=8100 ./venv/bin/python server.py
```

```bash
cd apps/ui
VITE_API_BASE_URL=http://127.0.0.1:8100 npm run dev:local
```

Override the port when needed:

```bash
SONIC_ANALYZER_PORT=8456 ./venv/bin/python server.py
```

Runtime profile and process role:

- `SONIC_ANALYZER_RUNTIME_PROFILE=local` keeps the current local-first behavior.
- `SONIC_ANALYZER_RUNTIME_PROFILE=hosted` turns on hosted-only guardrails such as required user identity headers on the run APIs.
- `SONIC_ANALYZER_PROCESS_ROLE=all` is the local default and starts the API plus in-process workers together.
- `SONIC_ANALYZER_PROCESS_ROLE=api` is the hosted default and starts the API without in-process workers.
- `SONIC_ANALYZER_PROCESS_ROLE=worker` is reserved for dedicated worker processes.

Hosted worker entry point:

```bash
cd apps/backend
SONIC_ANALYZER_RUNTIME_PROFILE=hosted SONIC_ANALYZER_PROCESS_ROLE=worker ./venv/bin/python worker.py
```

Current bind:

- host: `0.0.0.0`
- port: `8100` by default, or `SONIC_ANALYZER_PORT` when set

Current CORS allow list:

- `http://localhost:3000`
- `http://127.0.0.1:3000`
- `http://localhost:3100`
- `http://127.0.0.1:3100`
- `http://localhost:5173`
- `http://127.0.0.1:5173`

Hosted auth hook:

- In hosted mode, canonical run endpoints require `X-ASA-User-Id`.
- In plain English: the backend now expects the hosted platform to tell ASA which signed-in user owns the run before it will create, fetch, interrupt, or delete that run.

Artifact storage boundary:

- Run artifacts are now written through `artifact_storage.py` instead of being created inline directly from every runtime call site.
- In plain English: the backend still stores files on local disk today, but the read/write boundary is now isolated so hosted object storage can replace it later without rewriting every analysis path.

## HTTP API

### `POST /api/analysis-runs/estimate`

Purpose:

- Persist the uploaded file temporarily
- Read duration metadata
- Return the canonical runtime estimate for the staged run request

Multipart form fields:

- `track` required file upload
- `pitch_note_mode` optional string; `stem_notes` includes Demucs plus pitch/note translation time
- `pitch_note_backend` optional string; supported values are `auto`, `torchcrepe-viterbi`, and `torchcrepe`
- `interpretation_mode` optional string
- `interpretation_profile` optional string
- `interpretation_model` optional string
- `X-ASA-User-Id` required in hosted mode

Response shape:

| Field | Type | Notes |
| --- | --- | --- |
| `requestId` | `string` | Generated UUID per request. |
| `estimate.durationSeconds` | `number` | Duration from metadata when available. |
| `estimate.totalLowMs` | `number` | Sum of low-end stage estimates in milliseconds. |
| `estimate.totalHighMs` | `number` | Sum of high-end stage estimates in milliseconds. |
| `estimate.stages[]` | `array<object>` | Each stage has `key`, `label`, `lowMs`, and `highMs`. |

Current stage keys returned by the server:

- `local_dsp`
- `demucs_separation` when `separate` is enabled
- `transcription_full_mix` when `transcribe` is enabled without `separate`
- `transcription_stems` when both `transcribe` and `separate` are enabled

Example:

```bash
curl -X POST "http://127.0.0.1:8100/api/analysis-runs/estimate" \
  -F "track=@track.wav" \
  -F "pitch_note_mode=stem_notes"
```

### `POST /api/analyze` (legacy compatibility wrapper)

Purpose:

- Persist the uploaded file temporarily
- Build a timeout from the backend estimate
- Invoke `analyze.py` with `--yes` and any requested runtime flags
- Return a normalized `phase1` object plus diagnostics
- Emit a `[TIMING]` summary line to `stderr` for the completed request

Multipart form fields:

- `track` required file upload
- `dsp_json_override` optional string, accepted but ignored
- `transcribe` optional boolean-like form value; when true the server appends `--transcribe`
- `X-ASA-User-Id` required in hosted mode

Query parameters:

- `separate=true`
- `--separate=true`

The server always appends `--yes` when it shells out to `analyze.py`.

#### Success Envelope

Top-level fields:

- `requestId`
- `phase1`
- `diagnostics`

`diagnostics` currently contains:

- `requestId` mirrors the top-level request ID
- `backendDurationMs`
- `engineVersion` currently `"analyze.py"`
- `estimatedLowMs`
- `estimatedHighMs`
- `timeoutSeconds`
- `timings`
  - `totalMs` end-to-end wall time from request receipt to response construction
  - `analysisMs` subprocess wall time for `analyze.py`
  - `serverOverheadMs` `totalMs - analysisMs`
  - `flagsUsed` optional runtime flags passed to `analyze.py` such as `--separate` and `--transcribe`
  - `fileSizeBytes` uploaded file size after persistence
  - `fileDurationSeconds` analyzer-reported duration when available
  - `msPerSecondOfAudio` analyzer wall time divided by `fileDurationSeconds`, or `null`

Compatibility note:

- `backendDurationMs` remains the subprocess wall time for backward compatibility and matches `diagnostics.timings.analysisMs`.

`phase1` currently contains these normalized scalar fields:

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

All raw `analyze.py` fields are now forwarded through the server `phase1` wrapper. See `JSON_SCHEMA.md` for the complete list of forwarded sections and scalar fields.

Example:

```bash
curl -X POST "http://127.0.0.1:8100/api/analyze" \
  -F "track=@track.wav" \
  -F "transcribe=true"
```

#### Error Envelope

Top-level fields:

- `requestId`
- `error`
- `diagnostics`

`error` currently contains:

- `code`
- `message`
- `phase` currently always `phase1_local_dsp`
- `retryable`

Possible backend error codes emitted by `server.py` today:

- `ANALYZER_TIMEOUT`
- `BACKEND_INTERNAL_ERROR`
- `ANALYZER_FAILED`
- `ANALYZER_EMPTY_OUTPUT`
- `ANALYZER_INVALID_JSON`
- `ANALYZER_BAD_PAYLOAD`

`diagnostics` on error may include:

- `requestId`
- `backendDurationMs`
- `timeoutSeconds`
- `estimatedLowMs`
- `estimatedHighMs`
- `timings`
- `stdoutSnippet`
- `stderrSnippet`

When the analyzer does not produce a valid payload, `diagnostics.timings.fileDurationSeconds` and `diagnostics.timings.msPerSecondOfAudio` are `null`.

## Known Behavior Worth Documenting

- `dsp_json_override` is accepted by both endpoints but is currently ignored by the backend.
- The server timeout budget is derived from the estimate path and now reflects requested separation and transcription work.
- `transcriptionDetail` is only present when `analyze.py` runs with `--transcribe`; otherwise it is `null`.
- `--fast` runs the reduced fast-analysis preset instead of the full descriptor pass.

## Validation

```bash
./venv/bin/python -m py_compile server.py
./venv/bin/python -m unittest discover -s tests
```

Canonical local end-to-end verification is local-only and runs from the repo root without Gemini credentials or a user-provided audio file:

```bash
./scripts/test-e2e-integration.sh
```

The separate full live Gemini end-to-end verification still requires a real audio fixture plus backend Gemini credentials:

```bash
TEST_FLAC_PATH=/path/to/track.flac \
GEMINI_API_KEY=your_real_key_here \
VITE_ENABLE_PHASE2_GEMINI=true \
./scripts/test-e2e.sh
```

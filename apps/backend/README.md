# sonic-analyzer

Local audio analysis backend for the Sonic Analyzer workflow.

This repo contains two entry points:

- `analyze.py`: the raw CLI that runs Essentia-based analysis and prints JSON to `stdout`
- `server.py`: a FastAPI wrapper that accepts uploads, runs `analyze.py`, and returns a normalized HTTP contract for the UI

## Current Scope

`analyze.py` measures tempo, key, loudness, stereo, rhythm, melody, arrangement, segment-level metrics, chord content, perceptual features, optional Demucs separation, and optional Basic Pitch transcription.

`server.py` exposes two custom analysis routes:

- `POST /api/analyze/estimate`
- `POST /api/analyze`

FastAPI also serves the usual generated endpoints at `/openapi.json`, `/docs`, and `/redoc`.

## Tech Stack

- Python 3.10+
- Essentia
- NumPy
- Demucs
- Basic Pitch
- mido
- FastAPI
- Uvicorn

## Installation

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## CLI Usage

### Command

```bash
./venv/bin/python analyze.py <audio_file> [--separate] [--transcribe] [--fast] [--yes]
```

### Flags

| Flag | Current behavior |
| --- | --- |
| `<audio_file>` | Required input path. |
| `--separate` | Runs Demucs before melody analysis. If `--transcribe` is also enabled, Basic Pitch uses the `bass` and `other` stems when they exist. |
| `--transcribe` | Runs Basic Pitch and returns `transcriptionDetail`. Without Demucs it transcribes the full mix; with Demucs it transcribes `bass` and `other` separately and merges the notes. |
| `--fast` | Accepted, but currently a no-op parser stub. |
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
./venv/bin/python analyze.py track.wav --separate --transcribe --yes > analysis.json
```

## Raw CLI Output

The raw `analyze.py` payload is documented in [JSON_SCHEMA.md](JSON_SCHEMA.md).

Notable top-level sections include:

- core timing and loudness fields such as `bpm`, `key`, `durationSeconds`, `lufsIntegrated`, and `truePeak`
- detailed objects such as `dynamicCharacter`, `stereoDetail`, `spectralDetail`, `rhythmDetail`, `melodyDetail`, `transcriptionDetail`, `effectsDetail`, `arrangementDetail`, and `essentiaFeatures`
- segment-level outputs such as `segmentLoudness`, `segmentStereo`, `segmentSpectral`, and `segmentKey`

## Running the HTTP Server

Recommended synced launcher from this backend repo:

```bash
cd /Users/christiansmith/code/projects/sonic-analyzer-workspace/sonic-analyzer
./scripts/dev.sh
```

This tracked launcher starts the backend on `http://127.0.0.1:8100`, waits for the FastAPI contract to come up, then starts the sibling UI on `http://127.0.0.1:3100` with `VITE_API_BASE_URL=http://127.0.0.1:8100`.

If `../sonic-analyzer-UI/.env` still contains `http://localhost:8000`, the launcher prints a warning and overrides it for that session so the UI does not hit the dashboard service by mistake.

The older workspace-root `./scripts/dev.sh` flow is deprecated because it is not version-controlled in either repo.

Manual backend command:

```bash
SONIC_ANALYZER_PORT=8100 ./venv/bin/python server.py
```

Manual full-stack pair:

```bash
SONIC_ANALYZER_PORT=8100 ./venv/bin/python server.py
cd ../sonic-analyzer-UI && VITE_API_BASE_URL=http://127.0.0.1:8100 npm run dev:local
```

Override the port when needed:

```bash
SONIC_ANALYZER_PORT=8456 ./venv/bin/python server.py
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

## HTTP API

### `POST /api/analyze/estimate`

Purpose:

- Persist the uploaded file temporarily
- Read duration metadata
- Return a backend runtime estimate for local DSP and optional Demucs separation

Multipart form fields:

- `track` required file upload
- `dsp_json_override` optional string, accepted but ignored
- `transcribe` optional boolean-like form value; when true the estimate includes transcription runtime

Query parameters:

- `separate=true`
- `--separate=true`

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
curl -X POST "http://127.0.0.1:8100/api/analyze/estimate" \
  -F "track=@track.wav"
```

### `POST /api/analyze`

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

`phase1` also forwards these 17 sections from the raw analyzer payload:

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

Raw `analyze.py` fields that are not included in the HTTP `phase1` wrapper today:

- `bpmPercival`
- `bpmAgreement`
- `sampleRate`
- `dynamicSpread`
- `dynamicCharacter`
- `segmentStereo`
- `essentiaFeatures`

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
- `--fast` is accepted by the CLI but does not change analysis behavior yet.

## Validation

```bash
./venv/bin/python -m py_compile server.py
./venv/bin/python -m unittest discover -s tests
```

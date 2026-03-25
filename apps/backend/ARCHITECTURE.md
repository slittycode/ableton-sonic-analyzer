# Architecture

## Components

| Component | Role |
| --- | --- |
| `analyze.py` | Raw CLI analyzer. Loads audio, runs DSP, optionally separates stems and transcribes notes through torchcrepe, then prints JSON to `stdout`. |
| `server.py` | FastAPI wrapper. Accepts uploads, computes an estimate, shells out to `analyze.py`, normalizes the result into the HTTP `phase1` contract, and returns diagnostics or structured errors. |
| `tests/test_server.py` | Contract tests for estimate, timeout, and success envelopes. |
| `spectral_viz.py` | Librosa-based spectrogram generation and spectral time-series extraction. Produces mel/chroma PNG spectrograms and per-frame spectral evolution JSON. Called after successful measurement; failures are non-critical. |
| `tests/test_analyze.py` | Structural snapshot tests for the raw analyzer JSON output. |
| `tests/test_spectral_viz.py` | Unit tests for spectrogram generation, time-series computation, and artifact orchestration. |

## Separation of Responsibilities

### `analyze.py`

Responsibilities:

- read the input file
- optionally run Demucs separation
- run the Phase 1 DSP analysis functions
- optionally run pitch/note transcription through torchcrepe
- emit the raw analyzer JSON

Interface:

```bash
./venv/bin/python analyze.py <audio_file> [--separate] [--transcribe] [--fast] [--yes]
```

### `server.py`

Responsibilities:

- receive multipart uploads
- write the upload to a temporary file
- compute a backend estimate and timeout
- invoke `analyze.py` with `--yes`
- translate raw analyzer output into the HTTP `phase1` envelope
- return structured error diagnostics when the subprocess fails
- clean up temporary files

Custom routes:

- `POST /api/analysis-runs/estimate`
- `POST /api/analysis-runs`
- `GET /api/analysis-runs/{run_id}`
- `POST /api/analyze` (legacy compatibility)
- `POST /api/analyze/estimate` (legacy compatibility)
- `POST /api/phase2` (legacy compatibility)

FastAPI-generated routes remain available at `/openapi.json`, `/docs`, and `/redoc`.

## CLI Flow

1. Parse the positional audio path and the optional flags `--separate`, `--transcribe`, `--fast`, and `--yes`.
2. Read duration metadata with `get_audio_duration_seconds()`.
3. If running in a TTY and `--yes` is not set, print a stage-by-stage estimate and prompt the user to continue.
4. Load mono audio for most DSP features.
5. Load stereo audio for loudness, true peak, stereo, and segment-loudness measurements.
6. If `--separate` is enabled, run Demucs and keep the temporary stem paths.
7. Run shared rhythm extraction once and reuse it across BPM, rhythm, groove, and sidechain analyses.
8. Run the individual feature analyzers and merge their return dictionaries into a single result object.
9. If `--transcribe` is enabled, run the torchcrepe transcription backend:
   - on `bass` and `other` stems when Demucs output is available
   - otherwise on the full mix
10. Print the final JSON to `stdout` and logs to `stderr`.
11. Remove temporary stems after a separated run.

## Raw Analyzer Output

`analyze.py` emits the full schema documented in [JSON_SCHEMA.md](JSON_SCHEMA.md).

Important sections:

- core metrics: tempo, key, duration, loudness, true peak
- detail objects: `dynamicCharacter`, `stereoDetail`, `spectralDetail`, `rhythmDetail`, `melodyDetail`, `transcriptionDetail`, `grooveDetail`, `beatsLoudness`, `sidechainDetail`, `effectsDetail`, `synthesisCharacter`, `danceability`, `perceptual`, `essentiaFeatures`
- arrangement and segment data: `structure`, `arrangementDetail`, `segmentLoudness`, `segmentStereo`, `segmentSpectral`, `segmentKey`

## HTTP Flow

### `POST /api/analysis-runs/estimate`

1. Persist the uploaded file to a temporary path.
2. Read duration metadata with `get_audio_duration_seconds()`.
3. Resolve staged estimate flags from the requested run shape.
4. Call `build_analysis_estimate(duration, run_separation, run_transcribe)`.
5. Normalize stage keys into the server contract:
   - `dsp` -> `local_dsp`
   - `separation` -> `demucs_separation`
6. Return:
   - `requestId`
   - `estimate.durationSeconds`
   - `estimate.totalLowMs`
   - `estimate.totalHighMs`
   - `estimate.stages[]`
7. Close the upload and delete the temporary file.

### `POST /api/analyze` (legacy compatibility wrapper)

1. Persist the uploaded file to a temporary path.
2. Build the same estimate object used by the estimate route.
3. Convert the estimated upper bound into a timeout with a 15-second buffer.
4. Build the subprocess command:
   - base command: `./venv/bin/python analyze.py <temp_path> --yes`
   - add `--separate` when the query parameter is present
   - add `--transcribe` when the multipart form field is truthy
5. Run the subprocess with `capture_output=True`.
6. Handle failures with structured JSON error envelopes:
   - timeout
   - internal subprocess launch failure
   - non-zero exit
   - empty stdout
   - malformed JSON
   - non-object JSON
7. Build `diagnostics.timings` from request wall time, subprocess wall time, flag usage, upload size, and analyzer-reported duration.
8. Emit a `[TIMING]` summary line to `stderr` for every completed request, including structured errors.
9. On success, normalize the raw payload into `phase1` and attach diagnostics.
10. Close the upload and delete the temporary file.

## HTTP Contract

### Shared Request Inputs

Multipart form fields accepted by both routes:

- `track` required
- `dsp_json_override` optional and currently ignored
- `transcribe` optional; the legacy `POST /api/analyze` wrapper forwards it to `analyze.py`, and the legacy `POST /api/analyze/estimate` wrapper uses it for runtime estimation

Query parameters accepted by both routes:

- `separate`
- `--separate`

### Success Envelope

`POST /api/analyze` returns:

- `requestId`
- `phase1`
- `diagnostics`

`phase1` contains normalized scalars:

- `bpm`
- `bpmConfidence`
- `bpmPercival`
- `bpmAgreement`
- `key`
- `keyConfidence`
- `keyProfile`
- `tuningFrequency`
- `tuningCents`
- `timeSignature`
- `durationSeconds`
- `sampleRate`
- `lufsIntegrated`
- `lufsRange`
- `lufsMomentaryMax`
- `lufsShortTermMax`
- `truePeak`
- `crestFactor`
- `dynamicSpread`
- `stereoWidth`
- `stereoCorrelation`
- `spectralBalance`

`phase1` forwards these raw analyzer sections unchanged:

- `dynamicCharacter`
- `stereoDetail`
- `spectralDetail`
- `rhythmDetail` (includes `tempoStability`, `phraseGrid`)
- `melodyDetail`
- `transcriptionDetail`
- `grooveDetail`
- `beatsLoudness`
- `sidechainDetail` (includes `envelopeShape`)
- `effectsDetail`
- `synthesisCharacter`
- `danceability`
- `structure`
- `arrangementDetail`
- `segmentLoudness`
- `segmentSpectral`
- `segmentStereo`
- `segmentKey`
- `chordDetail`
- `perceptual`
- `essentiaFeatures`

All raw `analyze.py` fields are now forwarded through the server `phase1` wrapper.

`diagnostics` currently contains:

- `requestId`
- `backendDurationMs`
- `engineVersion`
- `estimatedLowMs`
- `estimatedHighMs`
- `timeoutSeconds`
- `timings.totalMs`
- `timings.analysisMs`
- `timings.serverOverheadMs`
- `timings.flagsUsed`
- `timings.fileSizeBytes`
- `timings.fileDurationSeconds`
- `timings.msPerSecondOfAudio`

Compatibility note:

- `backendDurationMs` remains the subprocess wall time for backward compatibility and mirrors `timings.analysisMs`.

### Error Envelope

`server.py` returns a consistent error envelope with:

- `requestId`
- `error.code`
- `error.message`
- `error.phase`
- `error.retryable`
- `diagnostics`

Error diagnostics can include:

- `requestId`
- `backendDurationMs`
- `timeoutSeconds`
- `estimatedLowMs`
- `estimatedHighMs`
- `timings`
- `stdoutSnippet`
- `stderrSnippet`

When the analyzer never produces a valid JSON object, `timings.fileDurationSeconds` and `timings.msPerSecondOfAudio` are `null`.

### `POST /api/phase2` (legacy compatibility wrapper)

1. Optionally use a cached temp file from a prior Phase 1 request (keyed by `phase1_request_id` form field); fall back to persisting the uploaded file if no cache hit.
2. Parse `phase1_json` form field — used as-is (already normalized by the frontend).
3. Build the Gemini prompt: system prompt from `prompts/phase2_system.txt` + Phase 1 JSON appended.
4. Upload the audio inline (≤100 MiB) or via the Gemini Files API (>100 MiB).
5. Call `generateContent` with structured output schema; retry on transient errors.
6. Parse and validate the response against the Phase 2 schema.
7. Return `{ requestId, phase2: Phase2Result | null, message, diagnostics }`.
8. Clean up the temporary file in the `finally` block.

## Transcription Pipeline

`transcriptionDetail` is produced only when `--transcribe` is active.

Flow:

1. Resolve the requested pitch backend and import the torchcrepe transcription backend.
2. Choose transcription sources:
   - `bass` and `other` stems when Demucs succeeded
   - otherwise `full_mix`
3. If the pipeline falls back to `full_mix`, emit a warning to `stderr` because dense material is lower quality without stem separation.
4. Run `predict()` once per source.
5. Normalize each note into:
   - `pitchMidi`
   - `pitchName`
   - `onsetSeconds`
   - `durationSeconds`
   - `confidence`
   - `stemSource`
6. Drop notes below the backend noise floor (`0.05`) before merge. This is not the user-facing quality dial; the UI confidence slider remains the primary filter.
7. Merge all sources, then deduplicate overlapping stem collisions with an active-window sweep:
   - active window: `onsetSeconds` through `onsetSeconds + max(durationSeconds, 0.1)`
   - overlap tolerance: `±1` semitone across different stems
   - exact-pitch near-duplicates: onsets within `30ms`
   - stem priority: `bass` wins below MIDI 48, `other` wins at or above MIDI 48, `full_mix` loses to both
8. Apply the post-dedup cap:
   - `500` notes for stem-aware transcription
   - `200` notes for `full_mix` fallback
9. Recompute `noteCount`, `averageConfidence`, `dominantPitches`, and `pitchRange` from the retained notes and return `transcriptionDetail`, including `fullMixFallback`.

## Current Caveats

- `dsp_json_override` is a reserved field only. The backend accepts it but does not use it.
- `--fast` is forwarded via form field `fast` or query param `fast` on the legacy `POST /api/analyze` wrapper. The estimate endpoint does not account for fast mode.
- The HTTP API is intentionally narrower than the raw CLI schema.

## Verification Surface

`tests/test_server.py` currently verifies:

- estimate contract normalization
- timeout error envelopes
- success responses with diagnostics

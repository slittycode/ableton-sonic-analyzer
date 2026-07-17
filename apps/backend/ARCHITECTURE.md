# Architecture

## Components

| Component | Role |
| --- | --- |
| `analyze.py` | Raw CLI analyzer entry point. Loads audio, coordinates the `analyze_*.py` feature modules (see [Analyzer Submodules](#analyzer-submodules) below), optionally separates stems and transcribes notes through torchcrepe, optionally runs MT3 polyphonic transcription (gated by `ASA_ENABLE_MT3=1`), then prints JSON to `stdout`. |
| `mt3_transcription.py` | Optional polyphonic transcription via Google MT3 (T5X). Additive only — never overrides measurement. Gated by `ASA_ENABLE_MT3=1` for the CLI path and by run-level `mt3_mode=enabled` for the staged API. Driven by `_execute_mt3_attempt`/`_mt3_worker_loop` in `server.py`. Optional dependencies in `requirements-mt3.txt`. |
| `server.py` + `server_phase1.py` / `server_phase2.py` / `server_upload.py` / `server_samples.py` | FastAPI app and router composition. Accepts uploads, computes estimates, manages the canonical staged run API, normalizes measurement results, serves artifact access, and exposes the on-demand Phase 3 audition-sample routes. |
| `analysis_runtime.py` | Run-state persistence and staged-analysis orchestration. Owns run snapshots, stage status, artifact metadata, and ownership checks. |
| `artifact_storage.py` | Artifact storage boundary. The current implementation uses the local filesystem, but the runtime now talks to a storage service interface instead of assuming every artifact is a local disk path forever. |
| `runtime_profile.py` | Runtime/profile switchboard for `local` vs `hosted` behavior and `all` vs `api` vs `worker` process roles. |
| `auth_context.py` | Hosted-mode user-context resolution. Establishes the current run owner in the canonical API path. |
| `worker.py` | Dedicated worker-process entry point for hosted-style background stage execution. |
| `upload_limits.py` | Canonical raw-audio (100 MiB) and request-envelope (101 MiB) limits, plus the protected-route list. Operator contract is generated, not hand-edited — see `scripts/render_upload_limit_contract.py`. |
| `spectral_viz.py` | Librosa-based spectrogram generation and spectral time-series extraction. Produces mel/STFT/chroma PNG spectrograms and per-frame spectral evolution JSON. The STFT variant preserves the source file's native sample rate so the y-axis spans 0 → source_sr/2 (rather than always 0 → 22.05 kHz); other variants render at 44.1 kHz. Called after successful measurement; failures are non-critical. |
| `url_ingest.py` | SSRF-guarded URL-mode ingestion for `POST /api/analysis-runs`. Fetches a public `http`/`https` audio file and streams the bytes through the same downstream pipeline as a multipart upload, enforcing the shared 100 MiB cap. |
| `audio_mime.py` | Canonical, host-independent filename→MIME resolution for ingested audio (`canonical_audio_mime`). Mirrors the frontend map in `apps/ui/src/services/audioFile.ts` so a `.flac` resolves to `audio/flac` on every OS — stdlib `mimetypes` is host-dependent (`audio/x-flac` on macOS vs `audio/flac` on Linux), which failed the test gate and could mislabel a FLAC handed to Gemini. Imported directly by `server_phase2.py` and `url_ingest.py`, and reached by `server.py` via `server_phase2._get_audio_mime_type`. |
| `csv_export.py` | CSV exporters for Phase 1 time-series fields, keyed by dotted JSON path. Backs `GET /api/analysis-runs/{run_id}/export/csv/{field_path}` and keeps the route handler a thin lookup-and-serve. |
| `phase2_export.py` | Versioned Phase 2 handoff envelope (`phase2-export.v1`) for downstream consumers — the sibling `asa-ableton` `.als` generator and `scripts/evaluate_recommendations.py --phase2`. Backs `GET /api/analysis-runs/{run_id}/export/phase2`; same thin lookup-and-serve pattern as `csv_export.py`. See [`docs/ASA_ABLETON_BOUNDARY.md`](../../docs/ASA_ABLETON_BOUNDARY.md). |
| `transcription_pianoroll.py` | Renders the pitch-note translation stage's `transcriptionDetail` as a velocity-encoded `(pitch, time)` uint8 matrix via `symusic`. Backs `GET /api/analysis-runs/{run_id}/transcription/pianoroll`. Derived view — Phase 1 stays authoritative; the response cites the Phase 1 `bpm` and `timeSignature` so chain of custody (PURPOSE invariant #2) is preserved. |
| `stage_status.py` | Collapses the eight internal stage statuses into the additive client-facing `publicStatus` field carried on every stage in the run snapshot. |
| `server_samples.py` + `sample_generation.py` / `sample_theory.py` / `sample_synthesis.py` / `sample_drums.py` | Phase 3 audition-sample generation. PyTheory musical plan, FluidSynth (sine-additive fallback) audio render, NumPy drum one-shots, and a citation manifest tying every clip back to a Phase 1 field. On-demand only — not part of the staged-execution queue. See [`docs/SAMPLE_GENERATION.md`](../../docs/SAMPLE_GENERATION.md). |
| `dsp_bandbank.py` + `dsp_utils.py` | Shared DSP primitives: `BatchedBandpass` (4th-order Butterworth bandpass bank with zero-phase `filtfilt`) and cross-module utility functions. |
| `phase1_evaluation.py` + `phase1_report_html.py` | Offline Phase 1 evaluation harness — deterministic-metric and detector-stability reporting, with a standalone HTML render. Not on the product path; driven by `scripts/evaluate_phase1.py`. |
| `polyphonic_evaluation.py` + `scripts/evaluate_polyphonic.py` | Research-only offline polyphonic-transcription evaluation harness. Not on the product path. |
| `beat_evaluation.py` + `beat_report_html.py` | Research-only beat/downbeat measurement gate. Benchmarks the neural tracker CPJKU/beat_this against the shipping kick-accent downbeat heuristic on a labeled corpus. Off the product path; driven by `scripts/evaluate_beats.py` (corpus manifest from `scripts/build_beat_manifest.py`). Deleting it restores the product exactly. |
| `loudness_rec_evaluation.py` + `scripts/evaluate_loudness_recs.py` | Research/test-only reachability check for the deterministic subset of a loudness recommendation (gain-to-target-LUFS + true-peak ceiling). Renders/re-measures audio with ASA's own Essentia measurements as oracle. Must not be imported by `analyze.py` or `server.py`. |
| `recommendation_evaluation.py` + `scripts/evaluate_recommendations.py` | Research-only recommendation-quality scorer for `GOAL.md`'s recommendation-proof campaign. Grades Phase 2 recommendations against `tests/fixtures/recommendation_tracks/` known-settings fixtures using a role/parameter/direction-band rubric and a chain-of-custody penalty (mirrors `phase2Validator.ts` semantics). `--source baseline|gemini|deterministic` switches the recommendation source; `--verification-artifact` emits the per-domain match-rate artifact consumed by `apps/ui/src/data/recommendationVerification.ts`. Off the product path. See `RECOMMENDATION_VERDICT.md` and `NEEDS.md`. |
| `live12_catalogue.py` | Source-extracted Live 12 device/parameter catalogue loader. Loads `data/live12_catalogue.json` (generated by repo-root `scripts/build_live12_catalogue.py` from the upstream `gluon/AbletonLive12_MIDIRemoteScripts`), validates against the published schema, and exposes a `Live12Catalogue` API with case-insensitive `has_device`, exact-match parameter lookup, and a `fuzzy_resolve` escape hatch. Static-source extraction does not carry `type/min/max/unit/default`; the `ParamSpec` slots are reserved for future runtime-introspection enrichment. |
| `phase2_catalogue_gates.py` | Live 12 source-catalogue checks that ANNOTATE Phase 2 recommendations. **Warn-and-keep contract:** every check (`device_unknown`, `parameter_unknown`, `value_out_of_range`, `citation_missing`) emits a `RECOMMENDATION_UNVERIFIED` warning on the `validationWarnings` channel; nothing is dropped or rewritten. Cross-checks every `{device, parameter, value, phase1Fields}` record in `mixAndMasterChain`, `abletonRecommendations`, and `secretSauce.workflowSteps`. Lives separately from `server_phase2.py` so unit tests can exercise it without the FastAPI/pydantic import chain. Wired into `server.py` after `_validate_phase2_citation_paths`. |
| `utils/cleanup.py` | Periodic artifact cleanup helpers used by the server background-task loop. |
| `tests/test_server.py` | Contract tests for estimate, timeout, and success envelopes. |
| `tests/test_analyze.py` | Structural snapshot tests for the raw analyzer JSON output. Owns `EXPECTED_TOP_LEVEL_KEYS` — update it whenever you add a root field. |
| `tests/test_phase1_golden.py` | Golden-snapshot regression gate over measured Phase 1 *values* (fixture `tests/fixtures/golden/phase1_default.json`). Re-baseline deliberately when a measurement change is intended. |
| `tests/test_spectral_viz.py` | Unit tests for spectrogram generation, time-series computation, and artifact orchestration. |
| `tests/test_csv_export.py` | Round-trip CSV-exporter tests against the registry in `csv_export.py`. |
| `tests/test_sample_*.py` + `tests/test_server_samples.py` | Phase 3 audition-sample synthesis and HTTP contract tests. |

### Analyzer Submodules

`analyze.py` was split from a monolith and now imports from the modules below. Add new measurements in the module that matches the domain, not back into `analyze.py`.

| Module | Domain |
| --- | --- |
| `analyze_core.py` | Shared coordination, BPM/key/loudness/stereo core measurements. |
| `analyze_audio_io.py` | Audio loading (mono + stereo), duration, sample-rate handling. |
| `analyze_detection.py` | Genre, acid, vocal, supersaw, sidechain, reverb, bass, kick detectors. |
| `analyze_estimate.py` | Per-stage time/cost estimates for the staged-run API. |
| `analyze_rhythm.py` | Rhythm extraction (shared once across BPM, groove, sidechain), groove timing, beats loudness. |
| `analyze_segments.py` | Segment boundaries and per-segment measurements (loudness, stereo, spectral, key). |
| `analyze_structure.py` | Arrangement structure and section labels. |
| `analyze_transcription.py` | torchcrepe pitch/note translation on Demucs-separated stems. |
| `analyze_fast.py` | Streamlined `--fast` pipeline (BPM, key, loudness, basic dynamics only). |

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
- write uploads to the runtime through the canonical run path
- compute backend estimates and timeouts
- invoke `analyze.py` with `--yes` through worker-owned stage execution
- translate raw analyzer output into the canonical measurement envelope
- enforce hosted-mode ownership on canonical run routes
- serve artifact metadata and artifact downloads without leaking internal paths
- return structured error diagnostics when subprocess execution fails

Custom routes:

- `POST /api/analysis-runs/estimate`
- `POST /api/analysis-runs` — multipart upload OR URL ingestion. Provide *exactly one* of `track` (multipart `UploadFile`) or `url` (form field with a public `http`/`https` URL). URL mode is SSRF-guarded against private/loopback/link-local addresses and enforces the same 100 MiB cap via streaming. See [`url_ingest.py`](url_ingest.py).
- `GET /api/analysis-runs/{run_id}`
- `POST /api/analysis-runs/{run_id}/interrupt` — terminate any active child processes for the run and mark stages interrupted.
- `DELETE /api/analysis-runs/{run_id}` — owner can delete their own run; operators with `SONIC_ANALYZER_ADMIN_KEY` set can supply `X-Admin-Key` to delete any run. Admin path is closed when the env var is unset.
- `GET /api/analysis-runs/{run_id}/artifacts` and `…/artifacts/{artifact_id}`
- `GET /api/analysis-runs/{run_id}/source-audio` — re-serves the original ingested audio for the run. Owner-only (no admin bypass). Saves a round-trip vs looking up the source artifact id first.
- `GET /api/analysis-runs/{run_id}/export/csv/{field_path}` — CSV export of a Phase 1 time-series field. See [`docs/adr/0001-phase1-json-schema-v1.md`](../../docs/adr/0001-phase1-json-schema-v1.md) and the registry in [`csv_export.py`](csv_export.py).
- `GET /api/analysis-runs/{run_id}/export/phase2` — single-file `phase2-export.v1` handoff envelope: the stored `producer_summary` interpretation result verbatim (including the frozen `recommendations.v1` projection), the authoritative Phase 1 payload its citations resolve against, the full `validationWarnings` trail, and provenance. The cross-repo contract for the sibling `asa-ableton` `.als` generator and the input format `scripts/evaluate_recommendations.py --phase2` accepts. Status codes: 200 (attachment), 404 (`RUN_NOT_FOUND`/`PHASE2_EXPORT_NOT_AVAILABLE`). Implementation in [`phase2_export.py`](phase2_export.py); contract doc at [`docs/ASA_ABLETON_BOUNDARY.md`](../../docs/ASA_ABLETON_BOUNDARY.md).
- `GET /api/analysis-runs/{run_id}/transcription/pianoroll` — velocity-encoded pianoroll matrix derived from the pitch-note translation stage's `transcriptionDetail`. Query params: `mode` (`frame`|`onset`, default `frame`), `pitchLow` (default 21), `pitchHigh` (default 109, exclusive), `tpq` (default 4). Response cites the Phase 1 `bpm` and `timeSignature` so every cell traces back to a measurement. Status codes: 200 (payload), 400 (`INVALID_MODE`/`INVALID_PITCH_RANGE`/`INVALID_TPQ`), 404 (`RUN_NOT_FOUND`/`TRANSCRIPTION_NOT_REQUESTED`/`TRANSCRIPTION_NOT_AVAILABLE`), 409 (`MEASUREMENT_NOT_COMPLETED`/`TRANSCRIPTION_NOT_COMPLETED`). Implementation in [`transcription_pianoroll.py`](transcription_pianoroll.py).
- `POST /api/analysis-runs/{run_id}/spectral-enhancements/{kind}` — on-demand spectral artifacts. `kind` is one of `cqt`, `hpss`, `onset`, `chroma_interactive`, or `reassigned` (sharper transient/frequency localization via `librosa.reassigned_spectrogram`).
- `POST /api/analysis-runs/{run_id}/pitch-note-translations`
- `POST /api/analysis-runs/{run_id}/mt3-transcriptions` — opt-in MT3 polyphonic transcription, peer of pitch-note translation. Runs only when the create-run request had `mt3_mode='enabled'` (or this route is hit explicitly to re-attempt). Additive — never overrides measurement; emits per-stem MIDI as artifacts. See the "Optional MT3 Namespace" section of [`JSON_SCHEMA.md`](JSON_SCHEMA.md).
- `POST /api/analysis-runs/{run_id}/interpretations`
- `POST /api/analysis-runs/{run_id}/samples` and `GET /api/analysis-runs/{run_id}/samples` — on-demand Phase 3 audition-sample generation and retrieval. Nothing in the staged-execution loop runs these automatically; the UI POSTs after interpretation completes. See [`server_samples.py`](server_samples.py) and [`docs/SAMPLE_GENERATION.md`](../../docs/SAMPLE_GENERATION.md).
- `POST /api/analyze` (legacy compatibility)
- `POST /api/analyze/estimate` (legacy compatibility)
- `POST /api/phase2` (legacy compatibility)

FastAPI-generated routes remain available at `/openapi.json`, `/docs`, and `/redoc`.

The upload limit contract is the canonical source for the raw-audio limit, the
request-envelope limit, the protected route list, and the edge proxy examples.
In plain English: if those numbers ever change, operators should regenerate the
contract instead of trusting old documentation.

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

1. Reject requests above the `101 MiB` request-envelope limit when `Content-Length` is present.
2. For valid multipart uploads, count only the `track` part bytes toward the shared `100 MiB` raw-audio limit.
3. Persist the uploaded file to a temporary path.
4. Read duration metadata with `get_audio_duration_seconds()`.
5. Resolve staged estimate flags from the requested run shape.
6. Call `build_analysis_estimate(duration, run_separation, run_transcribe)`.
7. Normalize stage keys into the server contract:
   - `dsp` -> `local_dsp`
   - `separation` -> `demucs_separation`
8. Return:
   - `requestId`
   - `estimate.durationSeconds`
   - `estimate.totalLowMs`
   - `estimate.totalHighMs`
   - `estimate.stages[]`
9. Close the upload and delete the temporary file.

### `POST /api/analyze` (legacy compatibility wrapper)

1. Reject requests above the `101 MiB` request-envelope limit when `Content-Length` is present.
2. For valid multipart uploads, count only the `track` part bytes toward the shared `100 MiB` raw-audio limit.
3. Persist the uploaded file to a temporary path.
4. Build the same estimate object used by the estimate route.
5. Convert the estimated upper bound into a timeout with a 15-second buffer.
6. Build the subprocess command:
   - base command: `./venv/bin/python analyze.py <temp_path> --yes`
   - add `--separate` when the query parameter is present
   - add `--transcribe` when the multipart form field is truthy
7. Run the subprocess with `capture_output=True`.
8. Handle failures with structured JSON error envelopes:
   - timeout
   - internal subprocess launch failure
   - non-zero exit
   - empty stdout
   - malformed JSON
   - non-object JSON
9. Build `diagnostics.timings` from request wall time, subprocess wall time, flag usage, upload size, and analyzer-reported duration.
10. Emit a `[TIMING]` summary line to `stderr` for every completed request, including structured errors.
11. On success, normalize the raw payload into `phase1` and attach diagnostics.
12. Close the upload and delete the temporary file.

### Hosted foundation additions

The backend now has an explicit local-versus-hosted runtime split.

- `local` mode preserves the current local-first behavior.
- `hosted` mode enables hosted-only guardrails such as user ownership and API/worker separation.

In plain English: the analysis engine is still the same, but the service wrapper around it can now behave like a hosted app without forcing the local app to work that way too.

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

`phase1` contains normalized scalars (see [`server_phase1.py`](server_phase1.py) `_build_phase1` for the authoritative list):

- BPM family: `bpm`, `bpmConfidence`, `bpmPercival`, `bpmAgreement`, `bpmDoubletime`, `bpmSource`, `bpmRawOriginal`
- Key family: `key`, `keyConfidence`, `keyProfile`, `tuningFrequency`, `tuningCents`
- Time signature: `timeSignature`, `timeSignatureSource`, `timeSignatureConfidence`
- Duration / sample rate: `durationSeconds`, `sampleRate`
- Loudness: `lufsIntegrated`, `lufsRange`, `lufsMomentaryMax`, `lufsShortTermMax`, `lufsCurve`, `truePeak`, `plr`, `crestFactor`, `dynamicSpread`
- Dynamics character: `dynamicCharacter`, `textureCharacter`
- Stereo: `stereoWidth`, `stereoCorrelation`, `monoCompatible`
- Spectral balance: `spectralBalance` (seven-band scalar object)

`phase1` forwards these raw analyzer sections (re-normalized where noted):

- `stereoDetail`
- `spectralDetail` (per-stem keys are renamed to the top-level `Mean`-suffix shape by `_normalize_spectral_detail`)
- `spectralBalanceTimeSeries`
- `stemAnalysis` (per-stem spectralDetail renamed to match the top-level contract by `_normalize_stem_analysis`)
- `transientDensityDetail`
- `saturationDetail`
- `snareDetail`
- `hihatDetail`
- `rhythmDetail` (includes `tempoStability`, `phraseGrid`, `tempoCurve`)
- `rhythmTimeline`
- `melodyDetail`
- `transcriptionDetail`
- `pitchDetail`
- `grooveDetail`
- `beatsLoudness`
- `sidechainDetail` (includes `envelopeShape`)
- `acidDetail`
- `reverbDetail`
- `vocalDetail`
- `supersawDetail`
- `bassDetail`
- `kickDetail`
- `genreDetail`
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

1. Validate the uploaded audio against the shared backend upload limit.
2. Resolve the server-owned analysis run from `analysis_run_id` or `phase1_request_id`.
3. Parse `phase1_json` form field for compatibility only; canonical grounding comes from the server-owned run state.
4. Build the Gemini prompt: system prompt from `prompts/phase2_system.txt` + grounded analysis data.
5. Upload the audio inline (≤100 MiB) or via the Gemini Files API (>100 MiB).
6. Call `generateContent` with structured output schema; retry on transient errors.
7. Parse and validate the response against the Phase 2 schema.
8. Return `{ requestId, phase2: Phase2Result | null, message, diagnostics }`.
9. Clean up the temporary file in the `finally` block.

### Phase 2 citation-path verification

When an interpretation result is produced (the canonical `…/interpretations` route and the legacy `/api/phase2` wrapper both route through the same handling), `_validate_phase2_citation_paths` (in [`server_phase2.py`](server_phase2.py), called from [`server.py`](server.py)) checks every recommendation's `phase1Fields` citations against the *normalized* authoritative measurement payload — the same shape Gemini is prompted with. Cited dotted paths that don't resolve are flagged as **WARNING-only** entries on the `validationWarnings` channel; they never reject the response and never raise. This is a backend defense-in-depth mirror of the frontend's `validatePhase1FieldCitations` (in `apps/ui/src/services/phase2Validator.ts`), so a non-browser API consumer can't silently accept invented citations. Phase 1 stays authoritative either way.

### Phase 2 Live 12 catalogue gates

Running immediately after citation-path verification, [`phase2_catalogue_gates.apply_live12_catalogue_gates`](phase2_catalogue_gates.py) cross-checks each `{device, parameter, value, phase1Fields}` record in `mixAndMasterChain`, `abletonRecommendations`, and `secretSauce.workflowSteps` against the source-extracted [`data/live12_catalogue.json`](../../data/live12_catalogue.json). All findings are emitted as warn-and-keep `RECOMMENDATION_UNVERIFIED` events on the same `validationWarnings` channel (reasons: `device_unknown`, `parameter_unknown`, `value_out_of_range`, `citation_missing`); nothing is dropped or rewritten — an earlier fuzzy-rewrite path landed on the wrong EQ band and wrong A/B curve, so the contract is now warn-only. Catalogue load/parse errors degrade to a single `_unverified` warning rather than failing the response.

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

21. **`loudness_backend.py`**: Selectable Phase 1 loudness backend (default-off experiment). `ASA_LOUDNESS_BACKEND=wasm` overrides the four integrated/range/momentary-max/short-term-max LUFS scalars with readings from the native `measure-cli` binary when present. `truePeak` and `lufsCurve` always stay on Essentia. Any failure degrades back to Essentia. Default is `essentia` (no-op). The WASM package sources were archived in the 2026-07 trust diet — see `docs/OPTIONAL_BACKENDS.md` and branch `archive/loudness-spectro-wasm`.

22. **`separation_backend.py`**: Thin Phase 1 stem-separation seam over torchaudio Hybrid Demucs (`analyze_audio_io.separate_stems`). `separate_stems_backend` is the entry point called from `analyze.py`'s three separation sites (measurement `--separate`, `--pitch-note-only`, `--mt3-only`). The former MSST/BS-RoFormer optional path was removed in the 2026-07 trust diet (research-only licence gate; see `incorporations/msst-separation-licence-gate-2026-06-05.md`).

23. **`recommendations_contract.py` + `schemas/recommendations.v1.schema.json`**: Frozen, versioned Phase 2 recommendation contract (ADR 0003). `project_recommendations` normalizes the three Phase 2 device-card arrays (`abletonRecommendations`, `mixAndMasterChain`, `secretSauce.workflowSteps`) into a flat `{device, parameter, value, unit, range, cited_measurements[]}` envelope (`version: "recommendations.v1"`); `validate_envelope` checks it against the committed JSON Schema via `jsonschema` (the real file, not a hand-rolled mirror — see ADR 0001's drift warning). Derived and additive — it never overrides Phase 1 (invariant #1) and admits ONLY cited cards (`cited_measurements.minItems: 1`); uncited cards stay in the raw arrays where the warn-and-keep catalogue gate flags them. `server.py` attaches the validated envelope to the producer_summary interpretation result as a `recommendations` field (degrades to absent on error). TS mirror: `RecommendationsContract` in [src/types/interpretation.ts](apps/ui/src/types/interpretation.ts). CI gate: `tests/test_recommendations_contract.py` (schema validity + projection-validates + round-trip + freeze).

24. **`phase2_provider.py`**: Selectable Phase 2 interpretation provider (default-off experiment). `ASA_PHASE2_PROVIDER=claude` routes the producer_summary interpretation to `ClaudeCliProvider` — a text-only interpreter that runs the local Claude Code CLI headless (sandboxed: `--safe-mode`, `--tools ""`, `--no-session-persistence`, response schema enforced via `--json-schema`), grounds purely on the prompt's embedded Phase 1 JSON, and needs no `GEMINI_API_KEY`. All paths flow through the identical parse/citation/catalogue validators. The former MOSS sidecar was a permanent licence dead-end and was removed in the 2026-07 trust diet — see `docs/PHASE2_PROVIDER.md`.

25. **`phase2_export.py`** + **`schemas/phase2-export.v1.schema.json`**: Versioned Phase 2 handoff envelope (`phase2-export.v1`) for downstream consumers — the sibling `asa-ableton` repo (turns ASA recommendations into an openable Live 12 `.als` starter set) and `scripts/evaluate_recommendations.py --phase2`. Backs `GET /api/analysis-runs/{run_id}/export/phase2`: the stored `producer_summary` interpretation result verbatim (including the frozen `recommendations.v1` projection), the authoritative Phase 1 payload its citations resolve against, the full `validationWarnings` trail, and provenance — one curl, one self-contained file, no snapshot surgery. Same thin lookup-and-serve pattern as `csv_export.py`; envelope structure described in `schemas/phase2-export.v1.schema.json`; key set frozen by `tests/test_phase2_export.py`. Cross-repo contract documented in `docs/ASA_ABLETON_BOUNDARY.md`.

The subprocess isolation means `analyze.py` works as a standalone CLI. Check `apps/backend/JSON_SCHEMA.md` before adding new analyzer output fields. Check `apps/backend/ARCHITECTURE.md` for the full HTTP flow and contract details.

**Phase 2 (`POST /api/phase2`, legacy compat):** Uploads audio to Gemini inline if ≤100 MiB, or via the Gemini Files API if larger. Phase 1 JSON is appended to the system prompt from `prompts/phase2_system.txt`. Also relevant: `prompts/stem_summary_system.txt` and `prompts/live12_device_catalog.json` (the *prompt-injected* device catalogue — distinct from the runtime-validation `data/live12_catalogue.json` consumed by `phase2_catalogue_gates.py`). Backend defense-in-depth: `server_phase2.py`'s `_validate_phase2_citation_paths` mirrors the frontend citation-existence check and emits `validationWarnings` when a recommendation cites a Phase 1 path that doesn't exist — it flags invented citations rather than failing, since Phase 1 stays authoritative (invariant #1). `phase2_catalogue_gates.apply_live12_catalogue_gates` runs immediately after for source-catalogue checks (see backend file #20 above). Additional regression gates: `tests/test_phase2_grammar_fix.py` locks in the gerund-fix post-process in `server_phase2.py`; `tests/test_phase2_prompt_catalog.py` pins prompt examples against the Live 12 catalogue.

**Python version constraint:** Python 3.11.x required on macOS arm64. Essentia 2.1b6 wheels are only published for 3.11; this constraint may be relaxable if Essentia publishes 3.12+ wheels.

### Frontend (`apps/ui`)

Frontend service inventory, design-system notes, and UI-side contracts live in
[`apps/ui/ARCHITECTURE.md`](../ui/ARCHITECTURE.md). Do not duplicate that map here.

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
ASA_LOUDNESS_BACKEND="essentia"          # Phase 1 loudness source for the LUFS scalars: `essentia` (default, authoritative) or `wasm` to override lufsIntegrated/lufsRange/lufsMomentaryMax/lufsShortTermMax with the asa-dsp reading via the native measure-cli binary when present. truePeak + lufsCurve stay Essentia; degrades to Essentia if measure-cli is unbuilt. The `packages/loudness-spectro-wasm` sources were archived in the 2026-07 trust diet (restore from branch `archive/loudness-spectro-wasm`). Default-off. See apps/backend/loudness_backend.py and docs/OPTIONAL_BACKENDS.md.
ASA_MEASURE_CLI=""                       # optional absolute path to the measure-cli binary used by ASA_LOUDNESS_BACKEND=wasm; defaults to the archived package path packages/loudness-spectro-wasm/target/release/measure-cli if restored locally.
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

A quick map from intent to the right place to start (also in root `CLAUDE.md`):

| If you're changing… | Touch | Then |
|---|---|---|
| What gets measured | `analyze.py` + relevant `analyze_*.py` | Update `JSON_SCHEMA.md`, `EXPECTED_TOP_LEVEL_KEYS`, `apps/ui/src/types.ts` |
| How a measurement renders | `apps/ui/src/components/` | Add Vitest coverage in `tests/services/` if new parsing/projection |
| How Phase 2 advises | `prompts/phase2_system.txt` + `live12_device_catalog.json` | Verify with live Gemini smoke |
| The HTTP envelope shape | `server.py` (router) + `server_*.py` | `test_server.py` + frontend client types |
| Run-state or stage flow | `analysis_runtime.py` | Frontend polling in `analysisRunsClient.ts` |
| Upload limits or proxies | `upload_limits.py` | Regenerate via `scripts/render_upload_limit_contract.py` |
| Hosted-mode behavior | `runtime_profile.py`, `auth_context.py`, `worker.py` | Keep the `local` profile path unaffected (FROZEN — non-goal) |

Frozen/optional backends (MT3, samples, loudness wasm path, hosted): see [`docs/OPTIONAL_BACKENDS.md`](../../docs/OPTIONAL_BACKENDS.md).

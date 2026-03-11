# Changelog

All notable changes to `sonic-analyzer` are documented here in reverse chronological order.

## Unreleased

- Standardized the canonical local backend port on `8100` so it stays in sync with the UI's `3100` local-dev convention and the new workspace launcher flow.
- Added a tracked backend-owned `scripts/dev.sh` launcher that starts the full local stack, overrides stale UI backend env values at runtime, and deprecates the unversioned workspace-root launcher flow.

## v0.10.0

- Added raw `analyze.py` structural snapshot coverage using a generated short WAV fixture so the core DSP CLI has automated regression checks beyond the FastAPI wrapper contract tests.
- Added `http://localhost:3100` and `http://127.0.0.1:3100` to the FastAPI CORS allowlist so the Playwright smoke harness can reach the backend from port 3100.

## v0.9.0

- Fixed `POST /api/analyze/estimate` to include Demucs separation time in the estimate when `separate=true` is requested, so the UI timeout budget and displayed estimate range correctly reflect stem separation runs.

## v0.8.0

- `server.py` now respects the multipart `transcribe` form field on both `POST /api/analyze` and `POST /api/analyze/estimate`, so transcription runtime can be reflected in the estimate and timeout budget when requested.
- `POST /api/analyze` diagnostics now include a nested `timings` breakdown covering total wall time, subprocess time, overhead, flags used, file size, analyzer-reported duration, and milliseconds per second of audio.
- The server now prints a single `[TIMING]` summary line to `stderr` for every completed `POST /api/analyze` request, including structured error responses.

## v0.7.0

- Expanded the HTTP `phase1` contract to forward 17 analyzer sections, including `transcriptionDetail`, `effectsDetail`, `arrangementDetail`, segment-level outputs, and harmonic/perceptual sections.
- Added stem-aware Basic Pitch transcription to `analyze.py`. When Demucs is available, transcription runs on the `bass` and `other` stems and merges the note events into a single `transcriptionDetail`.
- Added `basic-pitch` to runtime dependencies.
- Hardened the server contract with structured success and error envelopes plus `tests/test_server.py`.
- Updated the raw schema and README to describe the expanded analyzer output and HTTP wrapper.

## v0.6.0

- Added `server.py`, a FastAPI wrapper around `analyze.py`.
- Added `POST /api/analyze/estimate` for backend runtime estimates and `POST /api/analyze` for normalized phase-1 execution.
- Added structured diagnostics and timeout handling around the CLI subprocess.
- Added the newer Phase 1 analyzer sections introduced by the current codebase, including arrangement novelty, vibrato-aware melody detail, rhythmic gating detection, and `effectsDetail`.

## v0.5

- Per-segment key detection
- Per-segment stereo width
- Sub-bass mono check
- Sidechain pumping detection with `pumpingConfidence`
- `stereoDetail` schema replacing top-level stereo-only fields in the raw analyzer output
- Shared helpers:
  - `_slice_segments`
  - `_compute_stereo_metrics`
  - `_extract_beat_loudness_data`

## v0.4

- `DynamicComplexity`, `Flatness`, `LogAttackTime`
- `BarkBands` (24), `ERBBands` (40), `SpectralContrast`
- Per-segment loudness (`segmentLoudness`)
- Per-segment spectral Bark bands (`segmentSpectral`)
- `--fast` CLI stub

## v0.3

- Source separation via Demucs (`--separate` flag)
- `PitchContourSegmentation` replacing PredominantPitchMelodia-only melody output
- MIDI file export
- Chord detection with HPF pre-processing
- BPM cross-check via `PercivalBpmEstimator`
- Danceability and DFA

## v0.2

- `BeatLoudness` groove analysis (`kickSwing`, `hihatSwing`)
- Synthesis character (`inharmonicity`, `oddToEvenRatio`)
- Structure segmentation (`SBic`)
- Onset rate and beat positions

## v0.1

- Initial DSP engine
- BPM (`RhythmExtractor2013`), Key (`KeyExtractor/Temperley`), LUFS (`LoudnessEBUR128`)
- True peak, stereo width, and stereo correlation
- Spectral balance (6 bands)
- MFCC, chroma, spectral centroid, and spectral rolloff

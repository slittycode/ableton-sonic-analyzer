# Changelog

All notable changes to `sonic-analyzer-UI` are documented here in reverse chronological order.

## Unreleased

- Fixed REPORT_MD export to serialize Arrangement Overview and Mix and Master Chain sections as human-readable markdown instead of object coercion output.

## v0.4.0

- Phase 1 analyze requests now derive the UI timeout budget from the backend estimate instead of a fixed 120s cutoff, so long-running transcription and stem-separation runs do not abort prematurely in the browser.
- Browser-side request aborts now surface as `CLIENT_TIMEOUT` with explicit “UI timed out waiting” copy, while real backend `504` analyzer timeouts still report as `BACKEND_TIMEOUT`.
- Added the Phase 1 MIDI transcription toggle and wired it through the backend request as `transcribe=true|false`.
- Added stem separation toggle (Demucs pre-processing) wired through the backend request as `separate=true|false`; disabled unless MIDI transcription is also enabled.
- Added the Session Musician polyphonic and monophonic source toggle when both `transcriptionDetail` and `melodyDetail` are present.
- Tightened the Phase 2 prompt around 8-device minimum mix chains and protected group compaction.
- Fixed the estimate and status panel labels to render seconds with a lowercase `s`.
- Confidence threshold slider added to Session Musician panel. Filters notes at or above the threshold before quantize, preview, and MIDI export. Default 20%. Stats label shows "N / total NOTES" when threshold is active. `filterNotesByConfidence` and `formatFilteredNoteCount` exported as tested helpers.
- Confidence slider disabled in monophonic (Essentia) mode. Essentia exposes only one aggregate `pitchConfidence` scalar so per-note filtering is not meaningful there. Slider shows a tooltip explaining why it is inactive.
- Fixed duplicate metadata block rendering in Session Musician panel when `stats` is present (Range, Confidence, and source badge were appearing twice).
- Fixed `formatFilteredNoteCount` numerator to use `filteredNotes.length` instead of `displayNotes.length` (post-quantize count was used instead of pre-quantize confidence-filtered count).
- Vite manual chunk splitting: `vendor-react`, `vendor-google-ai`, `vendor-waveform`, `vendor-midi`. Initial entry chunk reduced from ~770kB to 48kB.
- `AnalysisResults` lazy-loaded via `React.lazy` and `Suspense` so result code is excluded from the initial bundle.
- `geminiPhase2Client` switched to a dynamic import gated on Gemini config availability, removing it from the eager load path.
- Backend timings contract synced to the frontend. `BackendTimingDiagnostics` type added. `backendPhase1Client` parses and validates the nested `diagnostics.timings` object on both success and error envelopes. Phase 1 success and backend error log entries now carry timings through to `DiagnosticLogEntry`. `DiagnosticLog` renders a full-width `TIMINGS:` row showing total, analysis, overhead, flags, and ms/s of audio.
- Gemini Phase 2 audio transport now branches on file size. Files at or below 20MB are sent as inline base64 (existing path). Files above 20MB are uploaded via the Gemini Files API (`ai.files.upload`), referenced by URI in the prompt, and deleted after generation in a best-effort `finally`. Upload and generation durations are reported separately in the Phase 2 diagnostic log message.
- Test suite expanded from 40 to 54 tests across 9 files. New coverage: confidence filtering helpers, monophonic mode guard, backend timings parsing and rendering, Phase 1 log propagation, and Gemini File API transport.
- Fixed MIME type fallback for FLAC and WAV files in Phase 2 audio transport. Browser `File.type` is often blank for these formats; the client now infers `audio/flac` or `audio/wav` from the file extension before falling back to `audio/mpeg`.
- Fixed stale Playwright smoke selector in `upload-phase1-midi.spec.ts` that was targeting a removed UI element and causing false negatives in the smoke suite.
- End-to-end FLAC validation confirmed: full pipeline against a 46MB FLAC completed without premature timeout; Files API upload path used for Phase 2; backend timings and Gemini upload/generation durations rendered correctly in the diagnostic log.

## v0.3.0

- Added `transcriptionDetail` parsing and typing across the frontend.
- Added the Session Musician panel for polyphonic transcription workflows.
- Added the Phase 1 estimate status panel and estimate smoke coverage.
- Expanded the diagnostic log and request-phase labeling.
- Added favicon and React Strict Mode coverage.

## v0.2.0

- Split backend communication into a dedicated Phase 1 client and a dedicated Gemini Phase 2 client.
- Added explicit environment handling through `src/config.ts` and `src/vite-env.d.ts`.
- Added mocked smoke tests plus unit tests for the backend client and UI flows.
- Updated the frontend schema expectations for arrangement overview, mix-chain output, sonic element fields, BPM rounding, and the spectral-balance note.

## Pre-v0.2.0

- Repository bootstrap and initial Ableton reconstruction UI work predate the first tagged release in this repo.

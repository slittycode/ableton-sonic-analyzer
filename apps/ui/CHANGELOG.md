# Changelog

All notable changes to `sonic-analyzer-UI` are documented here in reverse chronological order.

## Unreleased

## v1.3.0 — Downstream Section Hardening

- sonicElements kick: now derives device recommendations directly from kickAccentVariance and kickSwing thresholds rather than from the genre label inferred in trackCharacter.
- sonicElements bass: added explicit rule that inharmonicity-based synth selection applies regardless of genre label — the measured value is ground truth.
- mixAndMasterChain: replaced the genre-native technique requirement with a measurement-based justification rule; LOW/MED genre confidence now requires explicit DSP-grounded reasoning.
- secretSauce: title and explanation now derive from the dominant measured DSP characteristic, not the genre label. Genre is named as context, not as the primary driver.
- confidenceNotes: now always includes a genre inference result entry reporting label, confidence level, and which Step 1/Step 2 indicators matched or conflicted.

## v1.2.0 — Genre Inference Hardening (Prompt Pass)

- Replaced the descriptive `GENRE INFERENCE AND ADAPTATION` block with a three-step classification process: Step 1 rhythm profile (kickAccentVariance + kickSwing + danceability), Step 2 synthesis profile (inharmonicity + oddToEvenRatio + pumpingStrength), Step 3 BPM as tiebreaker only when Step 2 leaves ambiguity within a cluster.
- Added explicit genre buckets covering Acid Techno, Techno, House/Electro, EDM, Acid/Psychedelic Electronica, Hip-Hop, Trap, D&B/Breakbeat, Dark Electronica, and Pure Ambient — each tied to measured DSP thresholds, not audio perception.
- Added confidence reporting rules: 3+ indicators = HIGH, 2 = MED with conflict noted, 1 or 0 = LOW with both candidate genres named.
- Removed stale `grooveAmount` references from the FIELD GLOSSARY and `sonicElements.grooveAndTiming` (this field does not exist in the DSP payload). Replaced with correct `grooveDetail.kickSwing`, `grooveDetail.hihatSwing`, and `grooveDetail.kickAccent` descriptions.
- BPM is now explicitly prohibited from being the primary genre classifier — it is Step 3 only.

- Standardized the canonical local stack on UI `127.0.0.1:3100` and backend `127.0.0.1:8100`, added `npm run dev:local`, and documented the new workspace launcher flow.
- Wrong-backend diagnostics now mention stale local env overrides and point users to `./scripts/dev.sh` or `npm run dev:local`.

### UI/UX Improvements (Tiers 1–3)

Implemented all 15 items from the UI/UX improvement plan (`UI_UX_IMPROVEMENTS.md`). `npm run verify` passes: typecheck clean, 73 unit tests, production build, 33 smoke tests.

#### Tier 1 — High-impact, low-risk

- Replaced browser `alert()` calls with inline drop-zone error messages in the file upload component.
- Added dismiss (X) and Retry buttons to the error banner in the main app view.
- Made the diagnostic log collapsible with a chevron toggle, defaulting to collapsed.
- Fixed mobile header overflow so the title and controls no longer break out of the viewport.

#### Tier 2 — Noticeable polish

- Added a Cancel button during analysis. Threaded `AbortSignal` through both the backend client and the Phase 2 Gemini path; cancellation logs as `skipped`, suppresses late advisory results, and does not trigger the error banner. New `USER_CANCELLED` error code.
- Fixed accent color inconsistency: replaced 6 hardcoded `#ff9500`/`#ff9933` values with the theme token `#ff8800` (or CSS var references in Tailwind contexts).
- Adopted semantic theme tokens for status colors (`text-error`, `bg-success/10`, `border-warning/30`, etc.) across 6 component files, replacing 25+ hardcoded color classes.
- Fixed `EXEC_TIME: 0ms` on running diagnostic log entries; now shows `--` while a stage is still running.
- Added a Suspense skeleton fallback for lazy-loaded analysis results, replacing the blank `fallback={null}`.
- Fixed mobile grid layout in Mix & Master / Patch sections: `grid-cols-2` → `grid-cols-1 sm:grid-cols-2`.

#### Tier 3 — Nice-to-have

- Added file size validation warning for files exceeding 100 MB. Non-blocking yellow warning with `AlertTriangle` icon; analysis still proceeds.
- Added a progress bar to the analysis status panel. Uses elapsed time vs estimate midpoint, caps at 95%, pulses when exceeding the estimate, and shows an indeterminate bar when no estimate is available.
- Added shared audio-file validation across both the file input handler and drag-and-drop path. Valid `.mp3`, `.wav`, `.flac`, `.aiff`, and `.aif` uploads now succeed even when the browser leaves `File.type` blank; non-audio files still trigger an inline error.
- Replaced hardcoded `bg-[#222]` and `bg-[#1a1a1a]` values with new theme tokens (`--color-bg-surface-dark`, `--color-bg-surface-darker`) across 3 source files and the `.ableton-header` CSS class.
- Stabilized Session ID with `useMemo` so it no longer regenerates on every re-render.

#### Test updates

- Updated smoke test selectors in `error-states.spec.ts` (5 existing selector changes plus a new Phase 2 cancel regression), `ui-details.spec.ts` (2 selector changes), and `file-validation.spec.ts` (blank-MIME picker/drop regressions) to match the shipped behavior.
- Updated unit test assertions in `analysisResultsUi.test.ts` for responsive grid classes and semantic color classes, and added a Phase 2 cancellation regression in `analyzer.test.ts`.

## v0.7.0

- Made stem separation an independent App toggle so Demucs can be requested without enabling MIDI transcription.
- Added optional `TEST_FLAC_PATH` support to the live backend smoke so it can exercise a real FLAC when one is available and otherwise fall back silently to the checked-in WAV fixture.
- Corrected `.env.example` so `VITE_API_BASE_URL` points to `http://127.0.0.1:8100`, matching the current local backend server.
- Removed the stale `bpmAgreement` reference from the Phase 2 Gemini prompt because the frontend Phase 1 payload never includes that field.
- Removed the no-op DSP JSON override UI control from the App and documented the behavior as reserved transport support only.
- Completed markdown export so `widthAndStereo` and `harmonicContent` are included in the Sonic Elements section when present.
- Instrumented large-file Gemini upload retries with attempt, retry, and exhaustion warnings for debugging unexpected extra upload attempts.

## v0.6.0

- Tightened the Phase 2 Gemini prompt with explicit genre detection, genre-adaptive reconstruction guidance, and genre-native secret-sauce framing.
- Fixed Phase 1 danceability handling to preserve the backend `{ danceability, dfa }` object and render a dedicated Danceability section in the results UI.
- Fixed stem separation estimate: the estimate request now includes the `separate` flag so the displayed estimate range accounts for Demucs runtime when stem separation is toggled on.

## v0.5.0

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

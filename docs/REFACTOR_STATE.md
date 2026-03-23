# ASA Refactor — Architecture State

_Last updated: 2026-03-18_

## Current State

Phase A, Phase B1, and Phase B2 complete.

## What's Done

### Backend

- Measurement never persists `transcriptionDetail` — stripped at `complete_measurement()`
- Interpretation grounded from server-owned data, not client-supplied `phase1_json`
- Pitch/note mode resolver is strict — `UnsupportedPitchNoteMode` on unknown modes
- CAS-based job reservation — no duplicate worker claims
- Recovery is idempotent — targets `status = 'running'` rows only
- `build_legacy_phase1_projection()` deleted — no callers remained
- Deprecation headers on `/api/analyze` and `/api/phase2`

### Frontend

- `MeasurementResult = Omit<Phase1Result, 'transcriptionDetail'>` — canonical transport type
- `parseCanonicalMeasurementResult()` — private to `analysisRunsClient.ts`, strips `transcriptionDetail` at the transport boundary
- `projectPhase1FromRun()` — the **only** merge point that reconstructs `transcriptionDetail` from `stages.pitchNoteTranslation.result`
- Dead legacy clients deleted: `analyzePhase1WithBackend()`, `backendPhase2Client.ts`
- Constants renamed: `PHASE1_LABEL → MEASUREMENT_LABEL`, `PHASE2_LABEL → INTERPRETATION_LABEL`

### Phase B2 — Display component split (2026-03-18)

- `App.tsx` state split: `phase1Result` → `measurementResult` + `pitchNoteResult` (two separate `useState` vars)
- Destructure pattern: `const { transcriptionDetail, ...measurement } = merged` — type-safe by structural subtyping, no cast
- `AnalysisResults.tsx` props: `phase1: Phase1Result | null` → `measurement: MeasurementResult | null; pitchNote: TranscriptionDetail | null`
- `SessionMusicianPanel.tsx` props: same split; accesses `measurement.melodyDetail` and `pitchNote` directly
- `analysisResultsViewModel.ts`: all function signatures updated to `MeasurementResult`; `buildMelodyInsights` and `buildSonicElementCards`/`buildPatchCards` accept explicit `pitchNote: TranscriptionDetail | null` param
- `backendPhase1Client.ts` legacy direct-HTTP path deferred until `/api/analyze` is fully retired (4 active callers)

## Architecture Invariants (verified by tests)

1. `measurement.result` never carries `transcriptionDetail` on the canonical path
2. Pitch/note translation output is only available at `stages.pitchNoteTranslation.result`
3. `projectPhase1FromRun()` is the only place these are merged into a flat `Phase1Result`
4. Display components receive `MeasurementResult` directly — `transcriptionDetail` is passed as a separate explicit `pitchNote` prop

## What's Left

### Other deferred

- Runtime artifact TTL / disk cleanup
- Terminology sweep across docs, exports, analytics
- TOCTOU fix on `max_pending_per_stage` admission check (low severity, single-user desktop)

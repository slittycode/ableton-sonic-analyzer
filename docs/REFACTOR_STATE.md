# ASA Refactor — Architecture State

_Last updated: March 2026_

## Current State

Phase A and Phase B1 complete. Phase B2 (display-component UI type split) deferred.

## What's Done

### Backend

- Measurement never persists `transcriptionDetail` — stripped at `complete_measurement()`
- Interpretation grounded from server-owned data, not client-supplied `phase1_json`
- Symbolic mode resolver is strict — `UnsupportedSymbolicModeError` on unknown modes
- CAS-based job reservation — no duplicate worker claims
- Recovery is idempotent — targets `status = 'running'` rows only
- `build_legacy_phase1_projection()` deleted — no callers remained
- Deprecation headers on `/api/analyze` and `/api/phase2`

### Frontend

- `MeasurementResult = Omit<Phase1Result, 'transcriptionDetail'>` — canonical transport type
- `parseCanonicalMeasurementResult()` — private to `analysisRunsClient.ts`, strips `transcriptionDetail` at the transport boundary
- `projectPhase1FromRun()` — the **only** merge point that reconstructs `transcriptionDetail` from `stages.symbolicExtraction.result`
- Dead legacy clients deleted: `analyzePhase1WithBackend()`, `backendPhase2Client.ts`
- Constants renamed: `PHASE1_LABEL → MEASUREMENT_LABEL`, `PHASE2_LABEL → INTERPRETATION_LABEL`

## Architecture Invariants (verified by tests)

1. `measurement.result` never carries `transcriptionDetail` on the canonical path
2. Symbolic output is only available at `stages.symbolicExtraction.result`
3. `projectPhase1FromRun()` is the only place these are merged into a flat `Phase1Result`
4. No component receives `MeasurementResult` directly yet — display layer still consumes the compatibility projection

## What's Left

### Phase B2 — Display component split

- Replace `Phase1Result` in `App.tsx` state, `AnalysisResults` props, and downstream components with `MeasurementResult` + optional symbolic as distinct props
- `SessionMusicianPanel.tsx` and `analysisResultsViewModel.ts` are the primary consumers to update
- `backendPhase1Client.ts` legacy direct-HTTP path is the cleanup target when `/api/analyze` is fully retired

### Other deferred

- Runtime artifact TTL / disk cleanup
- Terminology sweep across docs, exports, analytics
- TOCTOU fix on `max_pending_per_stage` admission check (low severity, single-user desktop)

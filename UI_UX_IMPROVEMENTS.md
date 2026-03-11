# UI/UX Improvement Plan

Prioritized backlog of UI/UX improvements for `sonic-analyzer-UI`.
All three tiers are implemented.

---

## Tier 1 — High-impact, low-risk (DONE)

All four items are implemented and tested. See commit history for details.

| # | Change | Files |
|---|--------|-------|
| 1 | Replace `alert()` with inline drop-zone error | `src/components/FileUpload.tsx` |
| 2 | Add dismiss (X) + Retry button to error banner | `src/App.tsx` |
| 3 | Make diagnostic log collapsible | `src/components/DiagnosticLog.tsx`, `src/App.tsx` |
| 4 | Fix mobile header overflow | `src/App.tsx` |

---

## Tier 2 — Noticeable polish (DONE)

All six items are implemented and tested. `npm run verify` passes (typecheck, 73 unit tests, build, 33 smoke tests).

| # | Change | Files |
|---|--------|-------|
| 5 | Cancel button during analysis | `src/services/backendPhase1Client.ts`, `src/services/analyzer.ts`, `src/components/AnalysisStatusPanel.tsx`, `src/App.tsx` |
| 6 | Fix accent color inconsistency (`#ff9500` → `#ff8800`) | `src/App.tsx`, `src/components/AnalysisResults.tsx`, `src/components/SessionMusicianPanel.tsx`, `src/components/WaveformPlayer.tsx` |
| 7 | Use semantic theme tokens for status colors | `src/components/AnalysisResults.tsx`, `src/components/DiagnosticLog.tsx`, `src/components/SessionMusicianPanel.tsx`, `src/App.tsx`, `src/components/WaveformPlayer.tsx`, `src/components/FileUpload.tsx` |
| 8 | Fix `EXEC_TIME: 0ms` on running entries | `src/components/DiagnosticLog.tsx` |
| 9 | Suspense skeleton for lazy-loaded results | `src/App.tsx` |
| 10 | Fix mobile grid in Mix & Master / Patch sections | `src/components/AnalysisResults.tsx` |

### Implementation details

**Item 5 — Cancel button:** Added `USER_CANCELLED` error code. Threaded `AbortSignal` through `AnalyzePhase1Options` → `postBackendMultipart` and into the Phase 2 Gemini path. External signal abort is forwarded to the internal timeout controller for Phase 1, and advisory generation is guarded so cancellation suppresses late Phase 2 results. Cancel button appears in `AnalysisStatusPanel` during analysis. Cancellation logs as `skipped` (not `error`) and does not show the error banner.

**Item 6 — Accent color:** Replaced 6 hardcoded `#ff9500`/`#ff9933` occurrences with `#ff8800` (JS contexts) or CSS var references like `hover:bg-accent/90` and `shadow-[0_0_5px_var(--color-accent)]` (Tailwind contexts).

**Item 7 — Semantic tokens:** Replaced 25+ hardcoded status color classes (e.g., `text-red-400`, `bg-green-500/10`, `text-yellow-500`) with semantic tokens (`text-error`, `bg-success/10`, `border-warning/30`) across 6 component files. Tailwind v4's `@theme` block already registered these tokens as first-class colors. Updated smoke tests to use new selectors.

**Item 8 — EXEC_TIME:** Shows `--` instead of `0ms` when `log.status === 'running'`.

**Item 9 — Suspense fallback:** Replaced `fallback={null}` with a skeleton loader (pulse-animated cards matching results panel layout).

**Item 10 — Mobile grid:** Changed `grid-cols-2` to `grid-cols-1 sm:grid-cols-2` at two grid locations. Updated unit test assertion to match.

---

## Tier 3 — Nice-to-have (DONE)

All five items are implemented and tested. `npm run verify` passes (typecheck, 73 unit tests, build, 33 smoke tests).

| # | Change | Files |
|---|--------|-------|
| 11 | File size validation warning (>100MB) | `src/components/FileUpload.tsx` |
| 12 | Progress bar in AnalysisStatusPanel | `src/components/AnalysisStatusPanel.tsx` |
| 13 | File type check in `handleFileInput` | `src/components/FileUpload.tsx` |
| 14 | Replace hardcoded `bg-[#222]` / `bg-[#1a1a1a]` with theme tokens | `src/index.css`, `src/App.tsx`, `src/components/WaveformPlayer.tsx`, `src/components/DiagnosticLog.tsx` |
| 15 | Stabilize Session ID | `src/components/AnalysisResults.tsx` |

### Implementation details

**Item 11 — File size warning:** Added `FILE_SIZE_WARNING_BYTES` constant (100 MB). Both `handleDrop` and `handleFileInput` now check file size and set a non-blocking yellow warning via `fileSizeWarning` state. Warning appears below the "Ready" status in the selected-file view with an `AlertTriangle` icon. Analysis still proceeds normally.

**Item 12 — Progress bar:** Added `computeProgress` helper that calculates percentage from `elapsedMs` vs the midpoint of the estimate range. Shows an indeterminate pulsing bar when no estimate is available. Caps at 95% and pulses when the analysis exceeds the estimate. Bar is placed below the stats grid in `AnalysisStatusPanel`.

**Item 13 — File type check:** Added a shared audio-file validation helper used by both `handleFileInput` and `handleDrop`. Valid `.mp3`, `.wav`, `.flac`, `.aiff`, and `.aif` uploads now succeed even when the browser reports a blank `File.type`, while non-audio files still trigger the same inline error message. Added `showFileError` to the dependency array.

**Item 14 — Theme tokens:** Added `--color-bg-surface-dark: #222222` and `--color-bg-surface-darker: #1a1a1a` to the `@theme` block in `index.css`. Replaced 3 `bg-[#222]` occurrences in `App.tsx`, 1 `bg-[#1a1a1a]` in `WaveformPlayer.tsx`, and 1 `bg-[#1a1a1a]` in `DiagnosticLog.tsx` with semantic `bg-bg-surface-dark` / `bg-bg-surface-darker` utilities. Updated `.ableton-header` CSS class to use the new token. Updated smoke test selector in `ui-details.spec.ts`.

**Item 15 — Session ID:** Wrapped the inline `new Date().getTime().toString(36).toUpperCase()` in `useMemo` with an empty dependency array. The session ID is now generated once when `AnalysisResults` mounts, eliminating the flickering value on re-renders.

---

## Test files updated

Changes to source files required corresponding updates to test selectors and assertions:

| Test file | Reason |
|-----------|--------|
| `tests/services/analysisResultsUi.test.ts` | Grid class assertion (`grid-cols-2` → `grid-cols-1 sm:grid-cols-2`) and pill color class assertions (hardcoded → semantic tokens) — Items 7, 10 |
| `tests/services/analyzer.test.ts` | New Phase 2 cancellation regression ensures advisory results are suppressed after user abort — Item 5 |
| `tests/smoke/error-states.spec.ts` | Error banner selector updated from `text-red-400` to `text-error` (5 occurrences) and new Phase 2 cancel regression — Items 5, 7 |
| `tests/smoke/file-validation.spec.ts` | New blank-MIME picker/drop regressions for `.wav` and `.flac` uploads — Item 13 |
| `tests/smoke/ui-details.spec.ts` | SUCCESS badge selector (`bg-green-500\\/10` → `bg-success\\/10`) and diagnostic log content selector (`bg-\\[\\#1a1a1a\\]` → `bg-bg-surface-darker`) — Items 7, 14 |

## Summary

- **Source files changed:** 11 (`audioFile.ts`, `index.css`, `App.tsx`, `AnalysisResults.tsx`, `AnalysisStatusPanel.tsx`, `DiagnosticLog.tsx`, `FileUpload.tsx`, `SessionMusicianPanel.tsx`, `WaveformPlayer.tsx`, `backendPhase1Client.ts`, `analyzer.ts`)
- **Test files changed:** 5 (`analyzer.test.ts`, `analysisResultsUi.test.ts`, `error-states.spec.ts`, `file-validation.spec.ts`, `ui-details.spec.ts`)
- **New theme tokens added:** 4 (`--color-success`, `--color-warning`, `--color-error` already existed; `--color-bg-surface-dark` and `--color-bg-surface-darker` added in Tier 3)
- **New error code:** `USER_CANCELLED`
- **New constants:** `FILE_SIZE_WARNING_BYTES`
- **New helpers:** `computeProgress`, `resolveAudioMimeType`, `isSupportedAudioFile`, `getAudioMimeTypeOrDefault`
- **Verification:** `npm run verify` — typecheck clean, 73 unit tests passed, production build succeeded, 33/33 smoke tests passed (3 skipped are live-backend/live-Gemini tests requiring real services)

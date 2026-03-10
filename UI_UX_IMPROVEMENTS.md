# UI/UX Improvement Plan

Prioritized backlog of UI/UX improvements for `sonic-analyzer-UI`.
Tier 1 is implemented. Tiers 2 and 3 are documented for future implementation.

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

## Tier 2 — Noticeable polish

### Item 5: Add cancel button during analysis

**Why:** Analysis can take 10+ minutes with no way to abort.

**Files:**
- `src/App.tsx` — add Cancel button next to the status panel, wire an `AbortController` ref
- `src/components/AnalysisStatusPanel.tsx` — optionally accept an `onCancel` prop
- `src/services/analyzer.ts` — accept and forward `AbortSignal`
- `src/services/backendPhase1Client.ts:192` — already creates an `AbortController` internally; refactor to accept an external signal or expose the controller

**Implementation notes:**
- Create an `AbortController` ref in `App.tsx` when analysis starts
- Pass `signal` through `analyzer.ts` → `backendPhase1Client.ts`
- The backend client already has `AbortController` at line 192; merge the external signal with the existing timeout controller
- Show a "Cancel" button in the analysis status area; on click, call `controller.abort()`
- Handle `AbortError` in the error callback — set a user-friendly "Analysis cancelled" message instead of a generic error
- Clean up the controller ref on completion or unmount

---

### Item 6: Fix accent color inconsistency (`#ff9500` vs `#ff8800`)

**Why:** The theme defines `--color-accent: #ff8800` in `src/index.css:18`, but 5 files hardcode `#ff9500` or `#ff9933`.

**Files and locations:**
- `src/App.tsx:425` — `hover:bg-[#ff9933]` (button hover state)
- `src/components/AnalysisResults.tsx:207` — `shadow-[0_0_5px_#ff9500]`
- `src/components/AnalysisResults.tsx:231` — `shadow-[0_0_5px_#ff9500]`
- `src/components/SessionMusicianPanel.tsx:25` — `fill: '#ff9500'` (inline style)
- `src/components/WaveformPlayer.tsx:31` — `progressColor: '#ff9500'`
- `src/components/WaveformPlayer.tsx:181` — `let fillStyle = '#ff9500'`

**Implementation notes:**
- For Tailwind classes, replace with `shadow-accent` or `shadow-[0_0_5px_var(--color-accent)]`
- For `App.tsx:425`, replace `hover:bg-[#ff9933]` with `hover:bg-accent/90` or a lighter variant
- For inline JS styles (WaveformPlayer, SessionMusicianPanel), read the CSS variable at runtime: `getComputedStyle(document.documentElement).getPropertyValue('--color-accent')` or define a JS constant that matches the theme
- Test: visual regression screenshots at `/tmp/sonic-screenshots/` to compare before/after

---

### Item 7: Use semantic theme tokens for status colors

**Why:** `src/index.css` defines `--color-success` (line 24), `--color-warning` (line 25), `--color-error` (line 26) but they are unused. Components hardcode `text-red-400`, `bg-green-500/10`, etc.

**Files with hardcoded status colors (30+ occurrences):**
- `src/components/AnalysisResults.tsx:59-76` — `getConfidenceStyles()` and `getRatingStyles()`
- `src/components/AnalysisResults.tsx:340-343` — inline ternary status colors
- `src/components/AnalysisResults.tsx:440-442` — pass/fail styling
- `src/components/DiagnosticLog.tsx:19-23` — `getStatusColor()` returns hardcoded red/yellow/green
- `src/components/SessionMusicianPanel.tsx:463` — yellow warning badge
- `src/App.tsx:439,480,500,502,517` — status dots, warning text, error banner
- `src/components/WaveformPlayer.tsx:217` — ready/not-ready dot
- `src/components/FileUpload.tsx:88,116,132,143` — error styling and status dots

**Implementation notes:**
- Add Tailwind v4 utility classes in `src/index.css` that map to the semantic tokens, e.g.:
  ```css
  .text-success { color: var(--color-success); }
  .bg-success-subtle { background: color-mix(in srgb, var(--color-success) 10%, transparent); }
  ```
- Or use Tailwind's `theme()` function / `@theme` block to register them as first-class colors
- Replace incrementally, file by file, comparing screenshots
- This is a large surface area change — consider doing it in a dedicated PR

---

### Item 8: Fix `EXEC_TIME: 0ms` on running entries

**Why:** `DiagnosticLog.tsx:103` displays `{log.durationMs}ms` unconditionally. In-progress log entries have `durationMs: 0`, showing "EXEC_TIME: 0ms" which is misleading.

**File:** `src/components/DiagnosticLog.tsx:102-103`

**Implementation notes:**
- Check if the log entry is still in-progress (e.g., `log.status === 'running'` or `log.durationMs === 0` combined with being the last entry)
- Show `--` or a live elapsed timer instead of `0ms`
- For a live timer: store `startTime` on the log entry, use `useEffect` with `setInterval` to update display
- Simpler approach: just show `--` when `durationMs === 0`

---

### Item 9: Add Suspense fallback for lazy-loaded results

**Why:** `App.tsx:528` has `<Suspense fallback={null}>` which causes a blank flash when the `AnalysisResults` component chunk loads on slow connections.

**File:** `src/App.tsx:528`

**Implementation notes:**
- Replace `fallback={null}` with a skeleton or spinner that matches the results panel layout
- A simple approach: a `div` with the same dimensions, a subtle pulse animation, and the panel's background color
- Keep it lightweight — this is a one-time load per session

---

### Item 10: Fix Mix & Master / Patch Framework mobile grid

**Why:** Two grids in `AnalysisResults.tsx` use `grid-cols-2` with no responsive breakpoint, making them cramped on mobile.

**Files and locations:**
- `src/components/AnalysisResults.tsx:618` — `grid gap-4 grid-cols-2` (Mix & Master section)
- `src/components/AnalysisResults.tsx:695` — `grid gap-4 grid-cols-2` (Patch Framework section)

**Implementation notes:**
- Change to `grid gap-4 grid-cols-1 sm:grid-cols-2` so items stack on mobile
- Other grids in the file already use responsive breakpoints correctly (e.g., line 190: `grid-cols-2 md:grid-cols-4`)
- Test with mobile viewport (375px width) via Playwright or browser devtools

---

## Tier 3 — Nice-to-have

### Item 11: Add file size validation warning (>100MB)

**File:** `src/components/FileUpload.tsx`

**Notes:** Show a non-blocking warning when the selected file exceeds 100MB. The analysis will still proceed, but the user should know it may take significantly longer. Add the check in both `handleDrop` (line 38) and `handleFileInput` (line 59). Use the existing inline error pattern from Item 1 but with a yellow/warning style instead of red.

---

### Item 12: Progress bar in AnalysisStatusPanel

**File:** `src/components/AnalysisStatusPanel.tsx`

**Notes:** The estimate endpoint returns expected duration. Use elapsed time vs estimate to show a progress bar. Handle edge cases: estimate unavailable (show indeterminate), analysis exceeding estimate (bar stays at ~95% and pulses). Keep the existing status text; add the bar below it.

---

### Item 13: File type check in `handleFileInput` (matches `handleDrop`)

**File:** `src/components/FileUpload.tsx:59-71`

**Notes:** `handleDrop` (line 47) checks `file.type.startsWith('audio/')` and shows an inline error for non-audio files. `handleFileInput` (line 59) does NOT check — it accepts any file. Add the same `audio/` type check to `handleFileInput`. Note: the `<input>` element likely has an `accept` attribute that filters at the OS level, but programmatic validation is still needed as `accept` is advisory, not enforced.

---

### Item 14: Replace hardcoded `bg-[#222]` / `bg-[#1a1a1a]` with theme tokens

**Files and locations:**
- `src/App.tsx:322` — `bg-[#222]` (header bar)
- `src/App.tsx:366` — `bg-[#222]` (tab)
- `src/App.tsx:437` — `bg-[#222]` (tab)
- `src/components/WaveformPlayer.tsx:247` — `bg-[#1a1a1a]` (waveform container)
- `src/components/DiagnosticLog.tsx:75` — `bg-[#1a1a1a]` (log container)

**Notes:** These should use existing theme tokens like `bg-bg-panel` or `bg-bg-card`. Check `src/index.css` for the closest semantic match. If no exact match exists, add new tokens (e.g., `--color-bg-surface`) rather than leaving raw hex values.

---

### Item 15: Stabilize Session ID

**File:** `src/components/AnalysisResults.tsx:169`

**Notes:** The "SESSION ID" display uses `new Date().getTime().toString(36).toUpperCase()` inline in JSX, which regenerates on every render. Wrap in `useMemo` with an empty dependency array, or generate once when analysis results arrive and store in a `useRef`. The ID is cosmetic (not used for any logic), so stability is purely a UX concern — the flickering value looks broken.

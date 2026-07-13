# UI Overhaul — Completion Record (2026-06-21)

Past-tense paper trail for the front-end (`apps/ui`) design-system overhaul. The
work described here is current code on `main`. This document records what shipped,
what was deliberately **not** done and why, and the one piece left deferred.

## Goal

Move the UI from an organically-grown collection of one-off styled boxes onto a
single, enforceable design-system vocabulary — without changing any Phase 1
measurement, Phase 2 recommendation, or chain-of-custody behaviour. The overhaul
was scoped to presentation only; `PURPOSE.md` invariants were never in play.

## What shipped

Nine UI-overhaul PRs (`#165`–`#174`), plus `#164` which deflaked a stop-monitoring
smoke test to unblock the work. Every PR landed with `tsc` clean, the full Vitest
unit suite green, a passing production build, and Chromatic — squash-merged under
the repo's green-is-go rule.

### Uniformity

- **Phase 0 (`#165`)** — added a style-discipline CI guard that blocks raw hex
  colours and off-scale type sizes from re-entering `src/components/ui/`, and
  tokenized the primitive layer's type sizes onto the `--text-*` scale. This guard
  is what keeps the rest of the overhaul from eroding over time.
- **Phase 1 (`#166`)** — unified all typography onto the `--text-*` scale tokens;
  removed ad-hoc `text-[..px]` and mismatched Tailwind size utilities.
- **Phase 2a–d (`#167`–`#170`)** — migrated every feature component onto a single
  `src/components/ui/` primitive layer (`Button`, `Panel`, `DeviceRack`,
  `SectionHeader`, `Pill`, `DataTable`, `LedIndicator`, metric/lane primitives,
  …) and **deleted the duplicate `MeasurementPrimitives` set**. The codebase now
  has one primitive vocabulary, not two.

### Integrity

- **Phase 4a (`#174`)** — replaced remaining hand-rolled markup with primitives
  (DiagnosticLog status dot → `LedIndicator`; consistency table → `DataTable`) and
  removed a duplicate "Signal Monitor" heading. The chain-of-custody consistency
  report (`Phase2ConsistencyReport`) was held behaviourally identical throughout,
  guarded by its existing pinning suite.

### Accessibility

- **Phase 3a (`#172`)** — keyboard-operable file upload, visible focus rings on
  interactive elements, and accessible labels on the canvas-based visualizers.
- **Phase 3b (`#173`)** — lifted muted text colours to meet WCAG AA contrast on the
  dark surfaces.

## What was deliberately not done

Two phases from the original plan were dropped after inspection revealed the
foundation was already more mature than the plan assumed. Implementing them would
have produced diff-churn rather than improvement, violating the repo's working
principle that *every changed line trace directly to the request*.

- **Chip/badge declutter** — the chip system is already disciplined: status and
  semantic chips are correctly colour-coded, and a real four-band confidence
  ladder (`solid`/`workable`/`rough`/`unreliable`) is shared across
  `ConfidenceBandBadge`, `RecommendationVerificationBadge`, and citations. The only
  genuine gap is *label-tier hierarchy* among static section labels, which lives
  inside the `AnalysisResults` monolith and is best addressed there (see Deferred).

- **Radius / elevation / motion token scales** — elevation is already a token
  system (`--shadow-device-face/rack/active/success/error`); motion is only ~8
  `duration-*` call-sites over a consistent 150 ms default with
  `prefers-reduced-motion` already handled; the `rounded` vs `rounded-sm` split is
  plausibly intentional hierarchy. No clean, non-speculative win remained.

## Deferred

The `AnalysisResults` (~2,800 lines) and `App` (~2,600 lines) monoliths were left
untouched by design. Two distinct pieces of work remain available if prioritized:

1. **In-place restyle (user-visible)** — give the monolith's flat cards
   device-rack character (`DeviceRack`/`SectionHeader`/`Panel`) and apply the
   label-tier + accent discipline. Best done as small per-section PRs that respect
   the pinned smoke tests (`tests/smoke/`) and the `analysisResultsUi` unit
   coverage.
2. **Code split (maintainability-only)** — extract cohesive sub-components from the
   two monoliths as pure moves, verifying tests green per slice. No user-visible
   payoff; the highest-risk item in the original plan.

Neither is required for the overhaul's stated goal, which is complete.

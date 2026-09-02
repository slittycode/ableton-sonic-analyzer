# UI Recovery — Baseline Inventory

**Date:** 2026-07-18  
**Branch:** `main` (dirty; no recovery branch yet)  
**Purpose:** Wave 0 step 0 — snapshot in-flight work so autonomous waves do not re-do or thrash mid-migration patterns.

## Snapshot summary

Working tree already contains substantial UI recovery / discipline work that is **not committed**:

| Area | State | Notes |
| --- | --- | --- |
| `DESIGN_DIRECTION.md` + `design/reference/01–06` | **new (untracked)** | DNA + north-star shots already present |
| `scripts/check-style-discipline.mjs` | **mid-migration** | Expanded rules (+74/− lines); keep as enforcement spine |
| `App.tsx` | **mid-migration** | Small shell touch (~13 lines) — not full dual-rack recovery |
| `MeasurementDashboard.tsx` | **mid-migration** | Net delete-heavy (~80 lines); partial instrument cleanup |
| `analysisResults/*` (many sections) | **mid-migration** | Type-role / debris cleanup across most sections |
| `AnalysisResults.tsx` | **mid-migration** | Larger orchestration changes (+112-ish) |
| `phase1Picker.ts` + tests | **mid-migration** | Picker/export related; Wave 3 allowlist |
| `exportUtils.ts` + tests | **mid-migration** | Export surface; Wave 3 allowlist |
| `uiCapture.ts` + test | **new** | Capture helper — useful for compare gate |
| smoke `upload-phase1.spec.ts` | **mid-migration** | Small assertions added |
| package.json / lock | **deps touch** | Review before baseline commit (avoid unrelated dep churn if possible) |

Non-UI dirty paths also exist (backend, AGENTS, CLAUDE, skills, `.hallmark/`, etc.) — **out of scope** for UI recovery waves; owner should isolate UI baseline commit from agent-skill noise if possible.

## File classification (apps/ui)

Legend: `already-recovered` · `mid-migration` · `still-drifted` · `out-of-scope` · `scaffold`

### DNA / references
| Path | Class | Wave |
| --- | --- | --- |
| `apps/ui/DESIGN_DIRECTION.md` | already-recovered (docs) | 0 — tighten only |
| `apps/ui/design/reference/*` | already-recovered | 0 |
| `apps/ui/design/compare/` | scaffold | 1+ screenshots |

### Shell (Wave 1)
| Path | Class | Notes |
| --- | --- | --- |
| `src/App.tsx` | mid-migration | Partial; dual-rack proportions still open |
| `src/components/FileUpload.tsx` | still-drifted* | *not in current dirty list — treat as still-drifted until scouted |
| `src/components/InputSettingsForm.tsx` | still-drifted* | same |
| `src/components/WaveformPlayer.tsx` | still-drifted* | same |
| `src/components/RetroVisualizer.tsx` | still-drifted* | same |
| `src/components/IdleValuePropPanel.tsx` | still-drifted* | risk of marketing voice |
| `src/components/DiagnosticLog.tsx` | still-drifted* | terminal density target |
| `src/components/AnalysisStatusPanel.tsx` | still-drifted* | |
| `src/components/ui/**` | mid-migration / present | DeviceRack etc. exist — Wave 1 owns lock |
| `src/index.css` | still-drifted* | tokens already good; shell chrome may need polish |

### Measurement (Wave 2)
| Path | Class | Notes |
| --- | --- | --- |
| `src/components/MeasurementDashboard.tsx` | mid-migration | Do not thrash — continue from current diff |
| `src/components/measurementDashboard/**` | still-drifted* / mid | Scout before edits |
| `src/components/MixDoctorPanel.tsx` | still-drifted* | |

### Results / Live action (Wave 3)
| Path | Class | Notes |
| --- | --- | --- |
| `src/components/AnalysisResults.tsx` | mid-migration | |
| `src/components/analysisResults/*` | mid-migration | Most sections already touched for roles/debris |
| `src/services/phase1Picker.ts` | mid-migration | |
| `src/utils/exportUtils.ts` | mid-migration | |
| `src/utils/uiCapture.ts` | scaffold | Prefer for compare captures |

### Enforcement / tests
| Path | Class | Notes |
| --- | --- | --- |
| `scripts/check-style-discipline.mjs` | mid-migration | Keep green; extend carefully |
| `tests/services/analysisResultsUi.test.ts` | mid-migration | |
| `tests/services/exportUtils.test.ts` | mid-migration | |
| `tests/services/phase1Picker.test.ts` | mid-migration | |
| `tests/smoke/upload-phase1.spec.ts` | mid-migration | |

## Owner baseline actions (required before pilot)

1. **Branch** e.g. `ui-recovery/baseline` from current `main` dirty state (or commit on feature branch).
2. Prefer a **UI-only baseline commit** (exclude skill harness noise: `.agents/`, `.claude/skills/*`, `.pi/` unless intentional).
3. After commit, mark this inventory `status: baselined` and note commit SHA here.
4. Only then authorize Wave 1 pilot hour-block.

## Agent rules from this inventory

1. Treat `mid-migration` files as **continue, don’t rewrite**.
2. Prefer options that finish half-done surfaces over greenfield restyles.
3. Wave 1 pilot should assume shell is **not** done despite App.tsx dirt.
4. Wave 2/3 must read current section diffs before editing.

## Status

- [x] Dirty tree listed
- [x] Classification first pass
- [ ] Owner branch/commit SHA: _pending_
- [ ] Post-commit re-scout: _pending_

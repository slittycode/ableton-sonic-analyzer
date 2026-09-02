# ASA UI Recovery — Long-Horizon Autonomous Plan

**Status:** approved shape · **patched after high-level review** · pilot-only until Wave 1 handoff proves the loop  
**Date:** 2026-07-18 (rev 2)  
**Owner role:** sparse gate reviewer (handoff packs only; not every turn)  
**Agent role:** scout → residual option bank → **one deep change** → verify + **mandatory screenshots** → log  
**North star:** `~/Desktop/ASA UI Old` + `apps/ui/design/reference/` + **`apps/ui/DESIGN_DIRECTION.md` (single DNA source of truth)**  
**Audience / tone:** Ableton Live producers · brutalist · utilitarian · technical  

**Do not auto-launch multi-wave Ralph.** Pilot = one Wave 1 hour-block after Wave 0 baseline. Owner authorizes further waves only if that handoff is scannable and useful.

---

## 0. Review patches applied (rev 2)

| Review finding | Patch |
| --- | --- |
| Dirty tree unaddressed | Wave 0 step 0 = baseline inventory + owner commit cadence |
| Dual DNA docs | **No `apps/ui/design.md`.** Only tighten `DESIGN_DIRECTION.md` |
| ≥10 options every block = filler | Maintain **≥10 open residual** options; seed once; add only on real drift |
| Visual truth too late | **Compare screenshots required from Wave 1** (not Wave 5 only) |
| Hand-wavy allowlists | Absolute paths under `apps/ui/…`; shared-primitives single-owner lock |
| Self-scored DNA fit | SAFE requires **explicit reference screenshot ID** |
| 1–3 options too wide | **Default 1 SAFE option / block**; 2 only if same surface + pure presentation |
| Device spelling ungated | Wave 3 verify includes device-name catalog check |
| Optimistic calendar | Waves may take **multiple sessions**; not one calendar day |
| Dual logbooks | **One path only:** `plans/ui-recovery/logbook.md` (Ralph may symlink) |
| Debris detector late | Promote to Wave 2/3 **queued** work, not optional seed |
| Handoff screenshots optional | **Mandatory** side-by-side in every implement handoff |

---

## 1. Why this shape (not babysitting)

You do **not** want turn-by-turn co-piloting. You want a loop that:

1. Works for ~1 hour without asking permission on every micro-decision.
2. Comes back with a **ranked residual option bank (≥10 open items)** + what was done, not a vague status.
3. Stays **consistent** across sessions (same DNA, same gates, same file boundaries).
4. Only interrupts you at **hard gates** (scope change, deletion, contract break, visual identity fork).

This is a **Ralph-compatible** program: large, iterative, verifiable, repo-stateful.  
It is **not** freestyle redesign. Catalog Hallmark themes are **banned** — studied DNA only (old ASA + Live chrome).

---

## 2. Operating model

### 2.1 Cadence (hour-block)

Each autonomous **block** is 45–90 minutes wall time:

| Phase | Time | Output artifact |
| --- | --- | --- |
| A. Scout | 10–15 min | Diff DNA vs current surfaces; update residual bank only if real drift |
| B. Rank residual | 5 min | Ensure **≥10 open** options ranked; no junk filler |
| C. Implement | 30–50 min | **One** deep SAFE option (see §5.3) |
| D. Verify | 5–10 min | Mechanical gates + **mandatory compare screenshots** |
| E. Handoff pack | 5 min | TL;DR + screenshots + residual top 10 + `continue` default |

Owner reviews **only** the handoff pack + screenshots, then says:  
`continue` · `pivot to option ID` · `freeze` · `ship`.

**Owner commit cadence (explicit):** after each accepted handoff, owner commits (or instructs agent to prepare a commit message only — agent never auto-commits). Do not stack multiple uncommitted waves on a dirty tree.

### 2.2 Roles (cost routing)

| Role | Model class | Does | Never does |
| --- | --- | --- | --- |
| **Planner / Fable** | high-judgment, occasional | option banks, DNA judgments, kill lists | bulk implement |
| **Implementer** | Sonnet / budget obedient | file edits inside wave allowlist | invent new IA |
| **Verifier** | cheap + scripts | `npm run verify`, style discipline, smoke, screenshots | redesign |
| **Reviewer** | second pass | punch list vs DNA; no code unless asked | silent rewrites |

### 2.3 Autonomy budget

**Allowed without ping:**
1. Read any file under `apps/ui/`, screenshots, `DESIGN_DIRECTION.md`, reference, this plan, `plans/ui-recovery/*`.
2. Edit only files on the **active wave allowlist** (§4).
3. Adjust CSS tokens only if orange-first Ableton ladder is preserved.
4. Run from `apps/ui`: `npm run lint`, `lint:style`, `test:unit`, `build`, `test:smoke`, `verify`.
5. Append to `plans/ui-recovery/logbook.md` and update `options-bank.md`.
6. Write screenshots under `apps/ui/design/compare/` (required for implement blocks).

**Must stop and ask (hard gates):**
1. Delete production components, routes, or whole panels.
2. Change backend contracts / Phase 1–2 schema / `analysisRunsClient` shape.
3. Change brand identity (accent away from `#ff8800`, light theme, marketing layout).
4. New top-level information architecture (reorder entire results narrative).
5. Commit / push / branch switch (owner-controlled).
6. Install new dependencies.
7. Touch `apps/backend/**` (report-only if UI proves a contract defect).
8. Edit `apps/ui/src/components/ui/**` or `apps/ui/src/index.css` unless the active wave **owns** shared primitives (§4.0).

---

## 3. Success criteria (program-level)

### Done when (UI recovery “settled”)
1. Side-by-side: current shell vs `design/reference/01-input-monitor` + `06-signal-monitor` reads as **same family**.
2. Measurement racks use numbered Live-style headers + big-number metric tiles consistently.
3. Mix/results surfaces use `DeviceRack` + Live device grammar; no raw field paths / CONF % theater.
4. `apps/ui`: `npm run verify` green.
5. `scripts/check-style-discipline.mjs` green on results surfaces.
6. Debris detector (once added) green.
7. Owner sign-off: “UI settled” recorded in `DESIGN_DIRECTION.md`.

### Non-goals
1. New product features, DSP, Phase 2 prompt quality (separate programs).
2. Landing page / marketing redesign.
3. Pixel-perfect clone of every old screenshot (recover **grammar + density**, not every experiment).
4. Stealing focus from chain-of-custody / measurement truth work — this is a **parallel presentation track**.

---

## 4. Wave map (long horizon)

Waves are **serial**. A wave may span **multiple hour-blocks / sessions**.  
Calendar sketch of “6–10 hours” is a lower bound, not a promise.

### 4.0 Shared-primitives lock

| Path | Owner rule |
| --- | --- |
| `apps/ui/src/components/ui/**` | Only **one** active wave/agent at a time. Default owner: **Wave 1** for shell-needed primitives; then Wave 4 for consistency. Waves 2–3 consume primitives, don’t redesign them. |
| `apps/ui/src/index.css` | Same lock as above. |
| Parallel Build A/B | Forbidden to both touch shared primitives. |

### Wave 0 — Baseline + DNA lock (docs + inventory, no feature spam)

**Step 0 (mandatory before any implement wave):**
1. Snapshot dirty tree (see `plans/ui-recovery/baseline-inventory.md`).
2. Classify each in-flight UI file: `already-recovered` · `mid-migration` · `still-drifted` · `out-of-scope`.
3. Owner creates branch and/or commits baseline (agent does not commit).
4. Seed residual option bank ranked against **current diff** (mark already-done).

**DNA:**
1. **Single source of truth:** `apps/ui/DESIGN_DIRECTION.md` only.  
2. Tighten that file with a short portable DNA section if missing (shell / rack / metric / LED / bans).  
3. **Do not create** `apps/ui/design.md`.

**Verify:** docs + inventory only.

### Wave 1 — Shell recovery only (pilot wave)

**Allowlist (absolute):**
- `apps/ui/src/App.tsx`
- `apps/ui/src/components/FileUpload.tsx`
- `apps/ui/src/components/InputSettingsForm.tsx`
- `apps/ui/src/components/WaveformPlayer.tsx`
- `apps/ui/src/components/waveformPlayerUtils.ts`
- `apps/ui/src/components/RetroVisualizer.tsx`
- `apps/ui/src/components/IdleValuePropPanel.tsx`
- `apps/ui/src/components/DiagnosticLog.tsx`
- `apps/ui/src/components/AnalysisStatusPanel.tsx`
- `apps/ui/src/components/ui/**` *(Wave 1 owns shared primitives for this pilot)*
- `apps/ui/src/index.css`
- Related stories/tests for the above only

**Not in Wave 1:** `MeasurementDashboard.tsx`, `analysisResults/**`, export/picker helpers.

**Targets:**
1. Dual rack INPUT | SIGNAL MONITOR proportions (**ref: `01-input-monitor`, `06-signal-monitor`**).
2. Orange RUN ANALYSIS CTA language.
3. AWAITING SIGNAL / active spectrum chrome.
4. Terminal diagnostics density (**ref: structure/diagnostics shots in Desktop archive + ref 05/06 family**).

**Visual gate (every implement block):** screenshots of input+monitor to `apps/ui/design/compare/` + side-by-side in handoff.

### Wave 2 — Measurement instrument density

**Allowlist:**
- `apps/ui/src/components/MeasurementDashboard.tsx`
- `apps/ui/src/components/measurementDashboard/**`
- `apps/ui/src/components/MixDoctorPanel.tsx`
- `apps/ui/src/components/StructureLanes.tsx`
- `apps/ui/src/components/HarmonyLanes.tsx`
- `apps/ui/src/components/ChromaHeatmap.tsx`
- `apps/ui/src/components/MiniHeatmap.tsx`
- `apps/ui/src/components/SpectralEvolutionChart.tsx`
- `apps/ui/src/components/SpectrogramViewer.tsx`
- `apps/ui/src/components/Sparkline.tsx`
- Tests for the above
- **Do not** redesign `components/ui/**` unless Wave 1 lock released / Wave 4 owns it

**Targets:**
1. Numbered rack headers (**ref: mixdoctor / harmony numbered headers**).
2. Metric tile recipe everywhere.
3. Phrase / harmony / sidechain as instruments (**ref: `04-dynamics-panel`, structure refs**).
4. Remove uncalibrated score heroes.
5. **Debris detector test** introduced (DOM fails on raw field paths / CONF theater patterns).

**Visual gate:** one measurement rack + Mixdoctor surface screenshots every implement block.

### Wave 3 — Results + Live action surface

**Allowlist:**
- `apps/ui/src/components/AnalysisResults.tsx`
- `apps/ui/src/components/analysisResults/**`
- `apps/ui/src/components/analysisResultsViewModel.ts`
- `apps/ui/src/components/PatchSmithPanel.tsx`
- `apps/ui/src/components/StickyNav.tsx`
- `apps/ui/src/utils/exportUtils.ts`
- `apps/ui/src/services/phase1Picker.ts`
- `apps/ui/src/utils/uiCapture.ts` (if present)
- Related tests (`analysisResultsUi`, `exportUtils`, `phase1Picker`, smoke that assert UI copy)

**Targets:**
1. Sticky section rail like old results.
2. Mix chain device cards Live-named.
3. Secret sauce / reconstruction as protocol racks.
4. Zero developer debris in DOM.
5. Debris detector green.

**Verify extras:**
- Device-name spelling against Live 12 catalog / `asa-verify-device` for any rewritten recommendation chrome.
- Pretty wrong device names are worse than ugly right ones — park if catalog check fails.

**Visual gate:** mix-chain + one results section screenshots every implement block.

### Wave 4 — Cross-surface consistency

**Allowlist:** shared UI primitives + global CSS + remaining style-discipline offenders (explicit file list updated from residual bank at wave start).  
Wave 4 **takes** shared-primitives ownership from Wave 1.

### Wave 5 — Compare pack + settle

1. Full screenshot matrix vs reference 01–06.
2. Owner gallery review.
3. Declare UI settled or residual backlog only.

---

## 5. Option bank (residual, not filler)

**Path:** `plans/ui-recovery/options-bank.md` (single bank).

### 5.1 Rules
1. Wave 0 **seeds** ~20 themes ranked against current dirty-tree inventory.
2. Maintain **≥10 open** (`proposed` | `queued`) items whenever possible.
3. Hour-blocks **do not** invent 10 new rows by reflex.
4. Add options only when scout finds **real drift** not already banked.
5. Reject/park with reason — never silently delete.

### 5.2 Schema

```markdown
| ID | Option | Surface | Ref | Effort | Risk | DNA fit | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| W1-01 | Dual-rack 40/60 split | shell | 01, 06 | S | L | high | queued | |
```

**Ref** = `design/reference/` id(s) or Desktop SCR id. **Required for SAFE implement.**  
**Status:** `proposed` · `queued` · `doing` · `done` · `rejected` · `parked` · `already-done` (from baseline inventory).

### 5.3 SAFE auto-pick (no owner)

An option is **SAFE** only if **all** hold:

1. Active wave allowlist covers every file needed.
2. Risk ≤ M, Effort ≤ M.
3. **Ref** column cites a real screenshot id.
4. Not `parked` / `rejected` / `already-done`.
5. Does not require shared-primitives edit unless this wave owns them.

**Implement count:**
- Default: **1** SAFE option per block (deep).
- **2** only if both pure presentation and **same surface**.
- **Never 3** unless owner explicitly says so.

**Scoring (tie-break only):**  
`DNA fit` high=3 · Risk H=−2 M=−1 L=0 · Effort L=−2 M=−1 S=0.  
If no Ref → auto-`parked` for owner.

---

## 6. Verification

### Mechanical (every implement block)
From `apps/ui`:

```bash
npm run lint
npm run lint:style
npm run test:unit
npm run build
```

Prefer `npm run verify` when time allows; **wave done** requires full `verify` (includes smoke).

### Visual (every implement block from Wave 1+)
1. Capture 2–3 fixed surfaces for the active wave.
2. Write under `apps/ui/design/compare/YYYYMMDD-HHMM/`.
3. Handoff **must** include side-by-side vs reference (paths or embedded).  
   Green CI without screenshots = **failed block**.

### Wave-specific
- Wave 2+: debris detector once introduced.
- Wave 3: device-name catalog check for recommendation chrome.
- Wave 5: full ref matrix 01–06.

---

## 7. Logbook + handoff (single paths)

| Artifact | Path |
| --- | --- |
| Logbook (append-only) | `plans/ui-recovery/logbook.md` |
| Options bank | `plans/ui-recovery/options-bank.md` |
| Baseline inventory | `plans/ui-recovery/baseline-inventory.md` |
| Handoffs | `plans/ui-recovery/handoffs/YYYYMMDD-HHMM.md` |
| Screenshots | `apps/ui/design/compare/` |

If Ralph needs `.ralph/logbook.md`, **symlink** to `plans/ui-recovery/logbook.md`. Never dual-write.

### Handoff template (mandatory screenshots)

```markdown
# Handoff · Wave N · YYYY-MM-DD HH:MM

## TL;DR
1–3 bullets: Ableton familiarity delta.

## Implemented
- option ID · one-line · files

## Verify
- lint / style / unit / build / smoke: pass|fail
- compare shots: paths (required)

## Side-by-side
- before/after or current vs design/reference/<id>

## Residual top 10 (open)
1. ID — …
…

## Need from owner
- continue | pivot to <ID> | freeze | ship
```

---

## 8. Ralph contract (after pilot authorization)

### Pilot first
1. Complete Wave 0 (baseline + bank + DNA tighten).
2. Owner branch/commit baseline.
3. **One** Ralph (or agent) Wave 1 hour-block.
4. Owner judges handoff quality.
5. Only then authorize multi-block / multi-wave autonomy.

### Mission prompt (Wave-scoped)

```text
ASA UI Recovery · Wave {N} only · ONE deep SAFE option.

Read and obey:
- PURPOSE.md
- apps/ui/DESIGN_DIRECTION.md   # single DNA — no second design.md
- apps/ui/design/reference/*
- plans/ui-recovery-autonomous-horizon-2026-07.md
- plans/ui-recovery/baseline-inventory.md
- plans/ui-recovery/logbook.md
- plans/ui-recovery/options-bank.md

North star: old ASA UI + Ableton Live device chrome.
Tone: brutalist utilitarian technical. Orange-first charcoal.
NO Hallmark catalog themes. NO marketing layouts. NO backend contract changes.
NO commits. NO branch switches. NO new dependencies.
NO filler option spam. Maintain residual ≥10 open if possible; add only on real drift.

This iteration:
1. Scout allowlisted files for Wave {N} only.
2. Update residual bank if real new drift (do not invent 10 junk rows).
3. Implement exactly ONE SAFE option (Ref required; Risk≤M; Effort≤M; allowlist).
4. From apps/ui: npm run lint && npm run lint:style && npm run test:unit && npm run build
   Prefer full npm run verify when possible.
5. Write compare screenshots under apps/ui/design/compare/ (mandatory).
6. Append logbook + handoff pack with residual top 10.
7. Stop at hard gates.

Wave done only when verify green + wave targets mostly met + visual same-family on refs.
```

### Init / run
Only after owner says so:

```bash
python3 <ralph-skill>/scripts/ralphctl.py init --cwd /Users/christiansmith/code/projects/ableton-sonic-analyzer/asa --prompt "…"
python3 <ralph-skill>/scripts/ralphctl.py run --cwd /Users/christiansmith/code/projects/ableton-sonic-analyzer/asa
```

---

## 9. Consistency rails (anti-drift)

1. Single DNA: `DESIGN_DIRECTION.md`.
2. Wave allowlists with absolute paths.
3. Shared-primitives single-owner lock.
4. Style-discipline script.
5. Debris detector (Wave 2+).
6. Early + mandatory compare screenshots.
7. SAFE requires reference cite.
8. One deep change per block.
9. Append-only logbook; residual bank never silently drops items.
10. Owner commit after accepted handoffs.

---

## 10. Parallel multi-agent (optional, later)

Only after pilot handoff proves the loop. If used:

```
tasks/ableton-sonic-analyzer--ui-recovery/
  task.md / research.md / build-a.md / build-b.md / review.md
```

Rules: research never implements; build never changes DNA; review never “improves” without a parked option ID; **A and B never share `components/ui/**` ownership**.

---

## 11. Owner moves (current)

| Step | Action | Status |
| --- | --- | --- |
| A | Patch plan (this rev 2) | done |
| B | Wave 0: baseline inventory + residual bank seed | do next |
| C | Tighten `DESIGN_DIRECTION.md` only (no design.md) | do next |
| D | Owner: branch/commit baseline | owner |
| E | Pilot one Wave 1 hour-block | needs owner go |
| F | Multi-wave Ralph | only if E handoff is good |

---

## 12. Explicit non-babysitting contract

**You will not be asked:** class renames, padding micro-choices, “should I run tests?”

**You will be asked only when:** hard gate · wave boundary handoff · verify red after two fix attempts · DNA conflict between two references.

**You will receive after each block:** implemented option · verify evidence · **mandatory screenshots** · residual top 10 · one-line next command (`continue` default).

---

*Rev 2 end. Pilot path: Wave 0 complete → owner baseline commit → one Wave 1 block.*

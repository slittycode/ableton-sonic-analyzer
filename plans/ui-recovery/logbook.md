# UI Recovery Logbook (append-only)

Single log path for the program. Ralph may symlink `.ralph/logbook.md` → this file. **Never dual-write.**

---

## 2026-07-18 · Wave 0 · plan patch + scaffold

**Actor:** agent (plan rev 2 after high-level review)  
**Did:**
1. Patched `plans/ui-recovery-autonomous-horizon-2026-07.md` (dirty-tree baseline, single DNA, residual bank, early compare, absolute allowlists, 1 deep option/block, device-name gate, single logbook).
2. Created `plans/ui-recovery/baseline-inventory.md` from current dirty `apps/ui` tree.
3. Seeded `plans/ui-recovery/options-bank.md` (20+ residual options; mid-migration marked).
4. Tightened `apps/ui/DESIGN_DIRECTION.md` with Portable DNA section (no second design.md).
5. Ensured `apps/ui/design/compare/` and `plans/ui-recovery/handoffs/` exist.

**Did not:**
- Commit / branch
- Ralph init/run
- UI implementation

**Verify:** n/a (docs only)

**Owner next:**
1. Baseline branch/commit (UI-only preferred)
2. Record commit SHA in baseline-inventory
3. Authorize Wave 1 pilot (one hour-block, one deep SAFE option — default W1-01)

**Residual top open:** W0-01, W1-01, W1-02, W1-03, W1-05, W1-06, W2-01, W2-06, W2-07, W3-04 (see options-bank)

---

## 2026-07-18 · Wave 1 pilot · W1-01 dual-rack

**Actor:** agent (owner said go)
**Implemented:** W1-01 only (one deep SAFE option)
**Files:** `apps/ui/src/App.tsx`, `apps/ui/src/index.css`
**Changes:** top-anchored workbench; `max-w-7xl`; dual-rack `items-stretch` + min-heights; DeviceRack signal rails; flatter shell shadow; `data-testid="dual-rack"` body flex fill.
**Verify:** lint · style · unit(892) · build · smoke responsive+theme (6) pass
**Screenshots:** `apps/ui/design/compare/20260718-wave1-w101/`
**Handoff:** `plans/ui-recovery/handoffs/20260718-wave1-w101.md`
**Did not:** commit, multi-option spray, Wave 2+
**Owner next:** continue (W1-02/W1-03) · freeze · commit baseline

---

## 2026-07-18 · Wave 1 continue · flat chrome + W1-02 + W1-03 + research

**Did:**
1. Flattened device gradients/bevels/glows (owner feedback).
2. W1-02 full-width Run Analysis.
3. W1-03 IdleValueProp → instrument AWAITING SIGNAL frame (copy locks preserved).
4. Research note: `plans/ui-recovery/research-live12-and-peers.md` (Live 12 stock cleanup, Bitwig orange-on-dark, REAPER density, FabFilter flat meters, Max signal-flow, terminal DAW peers).

**Verify:** idle unit tests + tsc green (full unit/build next in block).
**Owner next:** continue Wave 1 (W1-04/W1-05) or commit.

---

## 2026-07-18 · Wave 1 · W1-05 diagnostics + CHARACTER smoke debt

**Did:**
1. W1-05: DiagnosticLog → DeviceRack flat terminal log (no left stripe, no soft card).
2. Smoke: CHARACTER → LOUDNESS (matches intentional mid-migration + unit tests).
3. Smoke selectors updated for system-diagnostics testid.

**Verify:** unit 892 · lint · build · ui-details + upload-phase1 smokes **13 pass**

**Handoff:** plans/ui-recovery/handoffs/20260718-wave1-w105.md

# UI Recovery — Residual Option Bank

**Rules:** Maintain ≥10 **open** (`proposed`/`queued`) items. Do **not** append 10 junk rows per block. Add only on real scout drift. SAFE implement requires **Ref** + Risk≤M + Effort≤M + wave allowlist. Default **1** option per block.

**Refs:** `01`…`06` = `apps/ui/design/reference/0N-*.png`. Desktop SCR ids allowed when refs thin.

| ID | Option | Surface | Ref | Effort | Risk | DNA fit | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| W1-01 | Dual-rack INPUT\|MONITOR proportions (≈40/60 Live shell) | shell | 01, 06 | M | L | high | done | Pilot 2026-07-18: max-w-7xl, top-anchor, equal-height, signal rails |
| W1-02 | Orange outline RUN ANALYSIS primary CTA | shell | 06 | S | L | high | done | 2026-07-18 full-width primary |
| W1-03 | Monitor idle: AWAITING SIGNAL + spectrum placeholder chrome | shell | 01, 06 | M | L | high | done | 2026-07-18 instrument idle; locked copy kept |
| W1-04 | Active multi-band spectrum legend chrome (LOW/MID/HIGH) | shell | 06 | M | M | high | queued | Only when live signal |
| W1-05 | Terminal diagnostics density (mono log + SUCCESS pills) | shell | 05 | M | L | high | done | 2026-07-18 DeviceRack + flat log; smokes updated |
| W1-06 | IdleValueProp as instrument idle, not marketing | shell | 01 | M | M | high | queued | Copy risk — keep utilitarian |
| W1-07 | Title-strip LED + mono labels on shell racks | shell | 01, 06 | S | L | high | queued | May need ui/* ownership |
| W1-08 | Focus rings / LED active states on primary shell controls | shell | 06 | S | L | med | proposed | |
| W2-01 | Unify MetricTile recipe across measurement dashboard | measurement | 02, 03 | M | L | high | queued | Continue mid-migration MD |
| W2-02 | Numbered rack headers for ordinal measurement groups | measurement | 03, 04 | S | L | high | queued | |
| W2-03 | Phrase structure 16/8/4 lanes visual recovery | measurement | 04 | M | M | high | queued | |
| W2-04 | Harmony palette + progression strip density | measurement | 04 | M | M | high | queued | |
| W2-05 | Sidechain / dynamics panels as instruments not cards | measurement | 04 | M | L | high | queued | |
| W2-06 | Kill uncalibrated score heroes (health/CONF %) | measurement | 03 | S | L | high | queued | Align DESIGN_DIRECTION ban |
| W2-07 | **Debris detector test** (fail raw field paths / CONF theater in DOM) | tests | — | M | L | high | queued | Promote early; Ref N/A for test |
| W3-01 | Sticky results section nav (mono anchors) | results | Desktop archive | M | M | high | queued | Scout mid-migration AnalysisResults |
| W3-02 | Mix chain DeviceRack + Live device-name cards | results | 01 family | M | M | high | queued | Device catalog check required |
| W3-03 | Secret sauce / reconstruction as protocol racks | results | Desktop archive | M | M | med | proposed | |
| W3-04 | Zero developer debris in results DOM (finish mid-migration) | results | DESIGN_DIRECTION | M | L | high | queued | Many sections already touched |
| W3-05 | Export/share chrome demoted to rack action slot | results | — | S | M | med | proposed | exportUtils mid-migration |
| W3-06 | Device-name catalog verify step in wave checklist | results | Live catalog | S | L | high | queued | Wave 3 gate |
| W4-01 | Type-role sweep of remaining text-xs\|sm\|base offenders | global | DESIGN_DIRECTION | M | L | high | proposed | After shell/measure/results |
| W4-02 | Empty/loading/error states for every major rack | global | 01, 06 | M | M | high | proposed | |
| W4-03 | Reduced-motion + contrast pass | global | — | M | L | med | proposed | |
| W5-01 | Full compare matrix vs reference 01–06 | settle | 01–06 | M | L | high | proposed | Wave 5 only |
| W0-01 | Owner baseline branch/commit of in-flight UI | process | — | S | L | high | queued | Blocks pilot |
| W0-02 | DESIGN_DIRECTION portable DNA section | docs | — | S | L | high | done | Single DNA doc; rev 2026-07-18 |

## Already-done / do-not-redo (from baseline inventory)

| ID | Item | Status | Notes |
| --- | --- | --- | --- |
| DONE-01 | DESIGN_DIRECTION + reference 01–06 introduced | already-done | Tighten only |
| DONE-02 | Style-discipline script expansion in progress | mid-migration | Don’t rewrite from scratch |
| DONE-03 | analysisResults section role/debris pass (partial) | mid-migration | Finish via W3-04, don’t restart |
| DONE-04 | MeasurementDashboard partial cleanup | mid-migration | Continue via W2-* |
| DONE-05 | uiCapture helper added | already-done | Use for compare gate |
| DONE-06 | DeviceRack / MetricTile primitives exist | already-done | Consume; Wave 1 owns edits |

## Parked (need owner or later wave)

| ID | Option | Why parked |
| --- | --- | --- |
| PARK-01 | Full IA reorder of results narrative | Hard gate — new IA |
| PARK-02 | Hallmark catalog theme experiment | Banned |
| PARK-03 | Backend contract changes for UI convenience | Hard gate |

## Open count

Count of `proposed`+`queued` above should stay **≥10**. Seed satisfies this.

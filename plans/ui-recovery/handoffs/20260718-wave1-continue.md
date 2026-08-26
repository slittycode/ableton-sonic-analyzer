# Handoff · Wave 1 continue · 2026-07-18

## TL;DR
1. Flat Live chrome locked (no gradient edges) + research vs Live 12 / peers.
2. Full-width **Run Analysis** (W1-02).
3. Idle monitor is **Awaiting signal** instrument frame (W1-03) while keeping audit copy.

## Implemented
| ID | What | Files |
| --- | --- | --- |
| flat chrome | solid fills, no bevel/glow | `index.css`, `Button.tsx`, `DESIGN_DIRECTION.md` |
| W1-02 | full-width primary CTA | `App.tsx` |
| W1-03 | instrument idle monitor | `IdleValuePropPanel.tsx` |
| research | Live 12 + peers | `plans/ui-recovery/research-live12-and-peers.md` |

## Research punch (read full note for sources)
1. **Live 12 stock:** declutter, align, flatter themes; not plastic gradients.
2. **Bitwig:** orange-on-dark works as *one* accent language.
3. **REAPER:** density > polish for power users.
4. **FabFilter:** flat meters carry the visual weight.
5. **Max / terminal DAWs:** signal-flow + mono density culture — use sparingly in main shell.

## Verify
- unit 892 pass · lint · build pass
- smoke: theme-shell + responsive pass
- smoke `ui-details` **1 fail pre-existing mid-migration:** expects label `CHARACTER` after analysis (results surface, not shell). Parked as Wave 2/3 residual — not introduced by this block.

## Residual top 10
1. W1-04 active multi-band spectrum chrome  
2. W1-05 terminal diagnostics density  
3. W1-07 title-strip LED polish  
4. Fix CHARACTER metric label smoke (mid-migration debt)  
5. W2-01 MetricTile unify  
6. W2-06 kill score theater  
7. W2-07 debris detector  
8. W0-01 owner baseline commit  
9. W3-04 finish results debris pass  
10. W1-06 residual idle copy tone (optional further)

## Need from owner
`continue` (default W1-04/W1-05 or fix CHARACTER smoke) · `freeze` · commit

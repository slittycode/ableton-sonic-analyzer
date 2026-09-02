# ASA UI Design Direction

**Standing agent instructions.** All UI changes MUST follow this doc until the
owner declares the UI settled. When in doubt, look at `design/reference/` and
move toward it — a bit, not completely.

## Owner intent

Recover the old ASA UI’s trustworthy, terminal-chrome density: charcoal panels,
orange-first signal, big measured numbers, no developer debris. The current
results surface drifted into uneven type sizes, raw field paths, and uncalibrated
confidence theater. Move back toward the old screenshots without a full redesign.

## Reference

Committed screenshots live in `apps/ui/design/reference/`. They were selected
from the owner’s old-UI archive (`~/Desktop/ASA UI Old/`) as the visual north
star:

- input + monitor shell
- spectrum / analysis racks
- Mixdoctor-style cards
- dynamics / meters
- structure & arrangement
- signal monitor chrome

Prefer matching those screens over inventing a new aesthetic.

## Principles (distilled from the old UI)

1. **Charcoal panels + terminal chrome.** Section headers read like device racks:
   monospace, status LEDs, tight borders (`border-border`, `bg-bg-card` /
   `bg-bg-surface-dark`). Not marketing cards. **Flat fills only** — no
   gradient device faces, no beveled inset edge highlights, no soft drop
   shadows on racks. Status = 1px ring / LED, not glow.
2. **Eyebrow labels.** Monospace, uppercase, letterspaced meta labels
   (`text-role-eyebrow` / `text-meta` tokens). Small and quiet.
3. **Orange-first palette.** Accent is `#ff8800` / `var(--color-accent)`. Use
   muted multi-hue spectrum **only** where hue encodes data (chroma pitches,
   stereo correlation, segment differentiation). Heat ramps = orange → amber →
   red. Sparing green/red pills for status only.
4. **Big numbers, small units.** Measured values use `text-role-value` /
   `text-value-lg` / `text-value-xl` with small unit suffixes. Don’t let body
   copy compete with the readout.
5. **Generous spacing.** The old UI breathes — prefer the spacing already used
   by migrated sections (`MixChainSection`, `SonicElementsSection`,
   `RoutingBlueprintSection`) over cramped stacks.
6. **Numbered section headers** where the surface is a rack (“08 Structure &
   Arrangement”), not free-form marketing titles.
7. **No raw percentages for uncalibrated scores.** Band badges only
   (`ConfidenceBandBadge`). Do not show “CONF 100%” theater.
8. **No developer debris in user-facing copy.** No raw Phase 1 field paths
   (`bpm · lufsIntegrated`), no `[object Object]`, no internal schema keys.
9. **Type sizes only via role tokens.** Use `text-role-*` / `data-text-role` /
   scale utilities (`text-nano` … `text-value-xl`). Do **not** use raw Tailwind
   `text-xs|sm|base|lg|xl` inside results surfaces. Enforced by
   `scripts/check-style-discipline.mjs`.

## Model sections

Copy role usage and density from:

- `src/components/analysisResults/MixChainSection.tsx`
- `src/components/analysisResults/SonicElementsSection.tsx`
- `src/components/analysisResults/RoutingBlueprintSection.tsx`

Avoid reintroducing patterns from pre-migration offenders once cleaned.

## Out of scope (for this direction)

- DSP / measurement algorithm changes
- Backend JSON contract shape (`EXPECTED_TOP_LEVEL_KEYS`)
- Full layout rewrites or new information architecture
- Re-enabling genre classification display until calibrated

## Portable DNA (single source of truth)

This file is the **only** agent-facing design bible for ASA UI recovery.
Do **not** invent a parallel `design.md` / Hallmark catalog theme.
Long-horizon autonomous work is governed by
`plans/ui-recovery-autonomous-horizon-2026-07.md` but must not contradict this doc.

Peer research (Live 12 stock + Bitwig/REAPER/FabFilter/Max density culture):
`plans/ui-recovery/research-live12-and-peers.md`. Live 12’s own redesign
emphasized **less clutter, flatter alignment, neutral greys + one accent** —
not gradient device cosplay.

### Shell
1. Top chrome: wordmark · engine badge · interpretation model · CPU/status.
2. Dual rack: **INPUT SOURCE** (left) | **SIGNAL MONITOR** (right).
3. Primary action: orange outline **RUN ANALYSIS** (Live-button energy).
4. Monitor states: idle `AWAITING SIGNAL` / active multi-band spectrum chrome.
5. Diagnostics: terminal log density (mono, SUCCESS pills), not soft marketing cards.

### Rack grammar
1. Title strip + LED status + mono uppercase name (device rack, not SaaS card).
2. Numbered section headers only when the surface is ordinal (`03 Mixdoctor`).
3. Tight 1px borders, charcoal ladder (`bg-app` / `bg-panel` / `bg-card` / `bg-surface-dark`).
4. Shared primitives live in `src/components/ui/*` + `src/index.css` — do not redesign tokens mid-feature.

### Metric / readout
1. Big measured number + small unit + quiet mono label (`MetricTile` / text-role-value*).
2. Status via green/red pills sparingly; orange = active/accent only.
3. Multi-hue only when hue encodes data (spectrum bands, chroma, stereo).

### Absolute bans
1. Uncalibrated CONF % / health-score theater as proof.
2. Raw Phase 1 field paths or schema keys in user-facing DOM.
3. Marketing hero layouts, glassmorphism, gradient text, cream/SaaS cards.
4. Hallmark catalog theme rotation (Specimen, Coral, etc.).
5. Backend contract or DSP changes under a “UI recovery” banner.

### Reference map
| ID | Surface |
| --- | --- |
| `design/reference/01-input-monitor.png` | Input + monitor shell family |
| `design/reference/02-spectrum-rack.png` | Spectrum / analysis rack density |
| `design/reference/03-mixdoctor-cards.png` | Mixdoctor-style cards |
| `design/reference/04-dynamics-panel.png` | Dynamics / meters / phrase |
| `design/reference/05-structure-section.png` | Structure / diagnostics density |
| `design/reference/06-signal-monitor.png` | Signal monitor chrome |
| `~/Desktop/ASA UI Old/` | Full historical archive (when refs are thin) |

## Checklist before shipping UI

- [ ] Read this file and glanced at `design/reference/`
- [ ] Type sizes use `text-role-*` / scale tokens only in results surfaces
- [ ] Accent is orange-first; multi-hue only for data-encoding
- [ ] No raw field paths or `[object Object]` in rendered DOM
- [ ] Uncalibrated scores use band badges, not raw %
- [ ] Any recommendation chrome uses real Live 12 device names (catalog check)
- [ ] Implement handoffs include compare screenshots vs reference (Wave 1+)
- [ ] `npm run verify` (or at least style-discipline + targeted unit tests) green

# Research · Live 12 chrome + peer music-tech UI (2026-07-18)

Feeds Wave 1+ DNA. Not a redesign brief — a compare pack so ASA stays **familiar to Live users** without cosplaying custom themes or SaaS.

## 1. Ableton Live 12 (stock)

### What changed in 12 (UI)
Source: [CDM — Live 12 everything new](https://cdm.link/ableton-live-12-everything-new/)

1. **Biggest single-version UI cleanup** while staying instantly recognizable.
2. **View styling** — less clutter: scrollbars, outlines, corner radius, padding, spacing reworked so elements align.
3. **New themes** — contrast / complementary color system; default can follow OS light/dark.
4. **Less decoration, more alignment** — themes often used to *hide* misaligned chrome; 12 fixed the structure instead.
5. Devices still read as **flat racks with title strips**, mono-ish labels, clear hierarchy — not skeuomorphic plastic.

### Theme system (technical)
1. Live 12 themes use **HEX** in `.ask` XML (`SurfaceBackground`, control colors, etc.) — not Live 10/11 ARGB.
2. Community themes (Sonic Bloom dark sets, killihu, Dracula ports, INFRA|Light) cluster around:
   - **Neutral dark greys** for surfaces
   - **One control accent** (orange, ochre, bronze, phosphor…)
   - Low chroma — studio-night friendly
3. Stock Live is **not** gradient-heavy device faces; custom “bevel” skins are the exception, not the brand.

### Implications for ASA (already partly applied)
| Live 12 signal | ASA action |
| --- | --- |
| Flat surfaces, tidy borders | Kill gradient faces / inset lips (done 2026-07-18) |
| Neutral charcoal ladder | Keep `#2b2b2b / #3c3c3c / #444 / #222` |
| Orange as control accent (classic Live) | Keep `#ff8800` orange-first |
| Title-strip device grammar | DeviceRack stays; solid strip fill |
| Less chrome noise | Prefer 1px rings over glow blooms |
| Meter / idle instrument language | Idle monitor = AWAITING SIGNAL, not hero marketing |

## 2. Peer / adjacent “nerd music tech” UI (same era vibe)

### Bitwig Studio
1. Recognizable **orange-on-dark** brand (users often love/hate the fixed palette).
2. Clean modern panels, hardware-accelerated feedback.
3. **Takeaway:** one strong accent + dark work surface = DAW-native; don’t invent a second accent language.

### REAPER 7
1. Default theme is **engineer dense**, highly adjustable (Theme Adjuster).
2. Community still calls stock “90s workstation”; power users theme it into flat dark.
3. **Takeaway:** density + information hierarchy beat polish; ASA should stay dense, not “pretty empty.”

### Max / Max for Live
1. Patcher culture = **boxes, cables, mono labels**, functional not decorative.
2. Dark themes common; UI is about signal flow readability.
3. **Takeaway:** signal rails / IN–OUT language on racks is on-brand (we added this); keep it subtle, not neon.

### FabFilter (plugin-era gold standard)
1. **Flat, modern, non-skeuomorphic** — clarity over hardware cosplay.
2. Strong metering / response curves as the visual center.
3. **Takeaway:** spectrum / meters should carry visual weight; chrome should disappear.

### Terminal-native DAWs (Phosphor, Imbolc — 2025–26 nerd edge)
1. Pure mono/TUI density, solarized or phosphor themes.
2. **Takeaway:** diagnostics log + mono meta labels are a feature for this audience, not a bug — but the main product surface should stay Live-rack, not full CRT cosplay.

### What to avoid (from peer landscape)
1. **Skeuomorphic plastic** (bevels, gradient faces, fake metal) — Live 12 moved away; owner already rejected.
2. **Bitwig-orange overload** everywhere — accent ≤ control/active, not wallpaper.
3. **REAPER default chaos** without hierarchy.
4. **Marketing SaaS cards** inside a DAW shell (our idle panel was drifting here).

## 3. Synthesis for ASA DNA (actionable)

**Stay:** Live charcoal ladder · orange accent · DeviceRack · mono eyebrows · big numbers · terminal diagnostics.

**Push harder:**
1. Flat only (done).
2. Full-width primary actions (W1-02).
3. Idle = instrument offline state + short facts (W1-03).
4. Spectrum / waveform as hero when armed (W1-04 later).
5. Numbered racks / metric grids like Live device rows (Wave 2).

**Do not borrow:**
1. Custom Live theme rainbow accents.
2. FabFilter’s full product chrome (we’re not a plugin window).
3. Terminal-only aesthetic for the main shell.

## 4. Sources
1. CDM Live 12 guide — https://cdm.link/ableton-live-12-everything-new/
2. Sonic Bloom Live 12 theme sets — dark grey collections
3. Ableton theme HEX notes (community editors / forum)
4. Bitwig / REAPER / FabFilter forum consensus (KVR, REAPER Blog)
5. Phosphor / Imbolc terminal DAW projects (adjacent density culture)

# dnb_reese_174

**Genre:** drum & bass · **Tempo:** 174 BPM · **Key:** F minor · **Render:** 48 kHz / 24-bit, 16 s loop

## What this fixture isolates

Drum & bass at 174 BPM built on the two genre pillars:

1. **The Reese bass** — detuned-unison saws in `Wavetable` (Unison 40 %) through a
   lowpass, saturated for harmonics. Recovering it means recommending a
   detuned/unison synth + drive, not a clean sub.
2. **Sampled breaks** — `Drum Rack` kick + amen-style breaks with hard bus
   compression (fast attack, short release).

Low end mono'd via `Utility`. Tests fast-tempo handling and the supersaw-like
detection on the Reese (`supersawDetail.isSupersaw`). Covers all seven domains.

## Answer key

`manifest.json` → `deviceSpec`. Build verbatim in Live 12 (checklist in
`../README.md`), render to `audio.flac`, store `phase1_fingerprint.json`.

## Status
- [x] Catalog-valid spec authored
- [ ] **NEEDS-FIXTURE:** rendered `audio.flac`
- [ ] **NEEDS-FIXTURE:** stored `phase1_fingerprint.json`

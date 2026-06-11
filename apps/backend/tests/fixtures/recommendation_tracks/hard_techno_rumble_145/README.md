# hard_techno_rumble_145

**Genre:** hard techno · **Tempo:** 145 BPM · **Key:** F minor · **Render:** 48 kHz / 24-bit, 16 s loop

## What this fixture isolates

A driving hard-techno loop — the rumble technique pushed harder and faster:

1. **Distorted sine kick** — `Operator` sine kick into `Drum Buss` *on the kick
   chain itself* (Drive 8, Boom Frequency 45 Hz). Recovering it means
   recommending kick-channel distortion, not just "a saturator somewhere."
2. **The rumble** — the kick fed through `Reverb` (2.5 s decay, 35 % wet) on a
   return, summed with a held sub `Operator`. The defining techno low-end move,
   here at peak-time tempo.
3. **Dark bandpass stab** (`Wavetable`, BP @ 1.5 kHz, no sustain) for the mid.
4. **Driving offbeat hats** (`Drum Rack`) and a **mono'd low end** (`Utility`
   Bass Mono).
5. **Master glue** (`Glue Compressor` 4:1) into `Limiter` (-0.3 dBFS).

`measurableIntent` targets the Drum Buss boom (kick fundamental ~45 Hz) and a
brighter `spectralDetail.spectralCentroidMean` than dark techno — distortion
adds harmonics — so an equivalent reconstruction by a different device path
still earns credit.

Covers all seven production domains. **This is the pilot fixture** — smallest
spec; build and render this one first per
`plans/owner-actions-recommendation-proof-plan.md` §3b.

## Answer key

The exact device chain is in `manifest.json` → `deviceSpec`. Build it verbatim in
Live 12 (checklist in `../README.md`), render to `audio.flac`, then store
`phase1_fingerprint.json`.

## Status

- [x] Catalog-valid spec authored
- [ ] **NEEDS-FIXTURE:** rendered `audio.flac` (owner builds + renders)
- [ ] **NEEDS-FIXTURE:** stored `phase1_fingerprint.json`

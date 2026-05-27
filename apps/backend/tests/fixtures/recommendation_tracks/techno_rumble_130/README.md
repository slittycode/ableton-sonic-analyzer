# techno_rumble_130

**Genre:** techno · **Tempo:** 130 BPM · **Key:** F minor · **Render:** 48 kHz / 24-bit, 16 s loop

## What this fixture isolates

A dark, driving techno loop centered on the "rumble" technique:

1. **Sine kick** with a lowpassed body (`Operator`, Filter 120 Hz, 300 ms decay).
2. **The rumble** — the kick fed through a long `Reverb` (3.0 s decay, 40 % wet)
   on a return, summed with a held sub `Operator`. This is the defining techno
   low-end move; recovering it means recommending a reverb-on-kick send plus a
   sustained sub, not just "a bass."
3. **Bandpass stab** (`Wavetable`, BP @ 1.2 kHz, no sustain) for the mid.
4. **Saturated bass drive** (`Saturator`, 8 dB) and a **mono'd low end**
   (`Utility` Bass Mono) — the kind of stereo discipline techno needs.
5. **Master glue** (`Glue Compressor` 4:1) into `Limiter` (-0.3 dBFS).

`measurableIntent` records a dark `spectralDetail.spectralCentroidMean` target so
a recommendation that achieves the right tonal balance by a different device path
still earns credit.

Covers all seven production domains.

## Answer key

The exact device chain is in `manifest.json` → `deviceSpec`. Build it verbatim in
Live 12, render to `audio.flac`, then store `phase1_fingerprint.json`.

## Status

- [x] Catalog-valid spec authored
- [ ] **NEEDS-FIXTURE:** rendered `audio.flac` (owner builds + renders)
- [ ] **NEEDS-FIXTURE:** stored `phase1_fingerprint.json`

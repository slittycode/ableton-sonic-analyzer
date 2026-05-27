# house_sidechain_pluck_124

**Genre:** house · **Tempo:** 124 BPM · **Key:** A minor · **Render:** 48 kHz / 24-bit, 16 s loop

## What this fixture isolates

A clean, sparse house loop built around the techniques an intermediate producer
most wants to recover from a reference:

1. **Sub-sine kick + sub-sine bass** — pure-sine fundamentals, no inharmonic
   content (tests `kickDetail.fundamentalHz` recovery and bass synth-role recall).
2. **The classic 1/4-note sidechain pump** — bass keyed off the kick via a
   `Compressor` (Threshold -20 dB, Ratio 4:1, fast attack, 120 ms release). This
   is the single most-requested house move; the manifest's `measurableIntent`
   records `sidechainDetail.pumpingStrength`/`pumpingRate` so an equivalent
   route (e.g. a volume-LFO duck) still earns credit.
3. **Saw pluck lead** with a resonant lowpass and a short envelope, widened with
   `Utility` and given space with `Reverb`.
4. **A two-stage master** — `Glue Compressor` (2:1 glue) into `Limiter`
   (-0.3 dBFS ceiling).

It deliberately covers all seven production domains (kick/bass/melody/groove/fx/
stereo/master) so it exercises full-surface coverage (PURPOSE.md invariant #5).

## Answer key

The exact device chain is in `manifest.json` → `deviceSpec`. Build it verbatim in
Live 12 (see the authoring checklist in `../README.md`), render to `audio.flac`,
then store `phase1_fingerprint.json`.

## Status

- [x] Catalog-valid spec authored
- [ ] **NEEDS-FIXTURE:** rendered `audio.flac` (owner builds + renders)
- [ ] **NEEDS-FIXTURE:** stored `phase1_fingerprint.json`

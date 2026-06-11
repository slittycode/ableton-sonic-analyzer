# ukg_2step_shuffle_132

**Genre:** UK garage · **Tempo:** 132 BPM · **Key:** G minor · **Render:** 48 kHz / 24-bit, 16 s loop

## What this fixture isolates

A UK garage / 2-step loop built on the genre's defining pillar — the shuffle:

1. **The 2-step shuffle** — kick is broken (NOT four-on-floor), snare on 2 and 4,
   closed hats on swung 16ths. **The swing lives in the MIDI, not in a device**:
   16th swing ≈ 57 % is baked into the committed `audio_melody.mid` and
   `audio_drums.mid` — equivalently, apply Live's groove pool **"Swing 16ths" at
   57 %** to the drum and bass clips. The answer key asserts it via
   `grooveDetail.hihatSwing`, `grooveDetail.perDrumSwing.snare`, and
   `bassDetail.grooveType`, so a recommendation that recovers the feel by any
   valid route (groove pool, MIDI nudge) earns credit.
2. **Warm plucky sub** — `Operator` sine with decay/sustain shaped for bounce,
   not a drone. The bounce is what swings.
3. **Chopped organ-style chord stab** — `Wavetable` (no sustain, fast attack)
   through `Chorus-Ensemble` for the classic organ/vocal-chop warble.
4. **Dub delay return** — `Echo`, synced 3/16 against 1/4, filtered, on a return.
5. **Gentle master glue** (`Glue Compressor` 2:1 — UKG breathes, don't slam)
   into `Limiter` (-0.3 dBFS).

Covers all seven production domains.

The swing targets in `measurableIntent` are **pre-render estimates** on the
tanh-compressed 0–1 scale — after rendering, re-baseline them (and
`bassDetail.grooveType`) from the stored fingerprint per `../README.md` step 6.
If the rendered bass reads `"straight"`, relax the manifest rather than forcing
the MIDI.

## Answer key

`manifest.json` → `deviceSpec`. Build verbatim in Live 12 (checklist in
`../README.md`), render to `audio.flac`, store `phase1_fingerprint.json`.
`audio_melody.mid` carries the swung G-minor stab/bass material;
`audio_drums.mid` carries the swung 2-step kit pattern (kick 36 / snare 38 /
closed hat 42) so the shuffle is reproducible without hand-programming groove.

## Status

- [x] Catalog-valid spec authored
- [ ] **NEEDS-FIXTURE:** rendered `audio.flac` (owner builds + renders)
- [ ] **NEEDS-FIXTURE:** stored `phase1_fingerprint.json`

# acid_303_128

**Genre:** acid techno · **Tempo:** 128 BPM · **Key:** A minor · **Render:** 48 kHz / 24-bit, 16 s loop

## What this fixture isolates

The 303 acid line: a **sawtooth through a high-resonance lowpass with glide**
(`Operator`, Resonance 70 %, Glide 60 ms), swept by `Auto Filter` and distorted by
`Saturator`. This fixture deliberately exercises ASA's **acid detector** — the
answer key asserts `acidDetail.isAcid` true with `acidDetail.confidence ≥ 0.5`, so
it doubles as a measurement-recovery check for that detector and a recommendation
check (does ASA recommend a resonant filter + drive for the acid character?).

Covers all seven production domains.

## Answer key

`manifest.json` → `deviceSpec`. Build verbatim in Live 12 (checklist in
`../README.md`), render to `audio.flac`, store `phase1_fingerprint.json`.

## Status
- [x] Catalog-valid spec authored
- [ ] **NEEDS-FIXTURE:** rendered `audio.flac`
- [ ] **NEEDS-FIXTURE:** stored `phase1_fingerprint.json`

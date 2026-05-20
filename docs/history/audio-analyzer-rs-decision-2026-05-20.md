# audio-analyzer-rs incorporation — decision: declined — 2026-05-20

> **Decided 2026-05-20.** ASA will **not** incorporate
> [`JuzzyDee/audio-analyzer-rs`](https://github.com/JuzzyDee/audio-analyzer-rs).
> tonnetz (the one feature ASA lacked) is **dropped**, not added. The crate's
> WASM phase stays pivot-gated. This **supersedes** the "cross-check oracle first —
> cheap and high-value" recommendation in
> [`incorporations/forking-plans-2026-05-14.md`](../../incorporations/forking-plans-2026-05-14.md)
> (Plan 4). Past-tense paper trail; not a living doc.

## Scope

The discovery framing proposed adopting `audio-analyzer-rs` as ASA's core engine —
compiling it to WASM and retiring Essentia.js — or, failing that, running it as a
cross-check oracle (Plan 4). This note records the decision after grounding that framing
against the actual codebase.

## Decision

1. **Do not incorporate the crate** — not as core engine (a), not as a selective vendor
   (b), not as a cross-check oracle (c).
2. **Drop tonnetz.** It is the only crate feature ASA lacks; it has no consumer; the
   sibling project that would use it can compute it itself.
3. **WASM stays pivot-gated.** A Rust→WASM build only matters if ASA becomes a
   client-side product — not on today's roadmap (Plan 4, phase 2).

## Why

**The premise was inverted.** ASA is server-side Python (native Essentia via
`analyze_core.py`), not an in-browser Essentia.js library. There is no Essentia.js to
retire.

**ASA already computes a superset of the crate**, usually via the more-validated,
EBU-verified Essentia, plus chords/genre/detectors the crate has none of:

| Crate output | ASA equivalent (already shipped) |
| --- | --- |
| centroid / bandwidth / rolloff / flatness, 7 bands, contrast, 13 MFCC, chroma | `spectralDetail.*`, `spectralBalance` · Essentia |
| key (Krumhansl-Schmuckler) | `key` · Essentia `KeyExtractor` (EDMA profile) |
| LUFS / LRA / true-peak / crest | `lufsIntegrated` / `lufsRange` / `truePeak` / `crestFactor` · Essentia (EBU Tech 3341/3342-verified in `apps/backend/tests/test_loudness_r128.py`) |
| stereo width / correlation / mono-compat | `stereoDetail.*` (richer: per-band correlations, correlation curve) |
| BPM / beats / onsets, sections | `bpm` + `rhythmDetail.*`, `structure.*` |
| HPSS (median-filter split) | Demucs learned stems (`stemAnalysis.*`) — a different technique, not "better HPSS"; `librosa.effects.hpss` covers a literal split if ever needed |
| **tonnetz** | **none → dropped** |
| chords / melody / 11 detectors | crate has none; ASA has `chordDetail`, transcription, acid/reverb/vocal/supersaw/bass/kick/snare/hihat/sidechain/genre/saturation |

**The oracle (c) is decorative.** An oracle that is *less validated than the thing it
checks* yields ambiguous signal: on disagreement we trust Essentia by default, so the
disagreement is logged and ignored. Cross-implementation agreement ≠ correctness. And:

- The crate's `Cargo.toml` lists **no `ebur128` dependency** — its EBU R128 is a
  from-scratch implementation, i.e. weaker as a loudness reference than Essentia (already
  verified here) or `pyloudnorm` / `ffmpeg -af ebur128`.
- ASA already runs **independent cross-checks in-product**: BPM via Essentia
  `RhythmExtractor2013` vs `PercivalBpmEstimator` (`bpmAgreement`), and chords via Viterbi
  vs Essentia `ChordExtractor` (`chordDetail.chordTimelineAgreement`).

This contradicts Plan 4's "cheap and high-value" call: cheap, yes; valuable, no. The
correct way to serve PURPOSE.md invariants #1 (measurement authority) and #4 (honest
uncertainty) is Python-native validation (reference libraries + labeled datasets), not a
same-class Rust oracle — see Follow-up.

**tonnetz has no consumer.** Repo-wide, "tonnetz" appears only inside
`incorporations/forking-plans-2026-05-14.md`. The Phase 2 prompt's harmonic inputs are
`key`, `keyConfidence`, `chordDetail.*`, and `chroma` — no tonnetz. The sibling
**Harmonia** project (React + Tonal.js) can derive tonnetz from the chroma ASA already
exports (`spectralDetail.chroma`). Emitting it now would be speculative schema surface.

## Verified facts (provenance)

- **Crate** (via its GitHub `Cargo.toml` / README): Rust edition 2024, MIT, v1.0.0, ~21★;
  **no `[lib]` target** (two bins: `cli` = `src/main.rs`, `mcp-server` = `src/mcp_server.rs`);
  deps `symphonia 0.5`, `rustfft 6.2`, `rmcp 1.1`, `tokio 1` (full), `serde`, `serde_json`,
  `schemars`, `tracing` — **no `ebur128`**. Reads a file path; analysis core (`src/lib.rs`
  `pub mod analysis`) is separable from the MCP transport (`rmcp`/`tokio`, confined to the
  `mcp-server` bin) — relevant only to a future WASM build.
- **ASA**: 56-key Phase 1 schema; key = Essentia EDMA (not K-S); chroma = HPCP; loudness =
  `LoudnessEBUR128` (`analyze_core.py`).

## Follow-up (tracked separately — not in this change)

A **Python-native Phase 1 validation harness** is greenlit as its own plan + PR, gated on
a stated trigger (e.g. an upcoming `analyze.py`/Essentia change, distrusted key/tempo
accuracy, observed regressions, or populating the stalled `tests/ground_truth/` corpus).
The trigger should drive the gate design. Recorded design intent:

- [ ] **Loudness → reference gate** (`pyloudnorm`; BS.1770 is a spec, so it is a true
      reference). Builds on `apps/backend/tests/test_loudness_r128.py`.
- [ ] **chroma / MFCC / spectral-centroid → regression (golden-snapshot) gate, not
      cross-impl.** Essentia HPCP vs librosa chroma (and MFCC mel/DCT/liftering) are
      different algorithms; tolerance-tuning to force agreement is a calibration tar pit.
- [ ] **key / tempo accuracy → labeled datasets** (e.g. GiantSteps), MIREX-style weighted
      key scoring + ±4% tempo (×2/÷2 octave credit) inline. Audio fetched to a gitignored
      cache, never committed. (The real payoff is actual accuracy numbers, which may be
      network-gated in CI — don't count scaffolding-without-a-baseline as done.)
- [ ] Pin `librosa`/`pyloudnorm`/`numpy`; make "the gate bites" a committed meta-test.

## Out of scope

- Vendoring the crate, adding a Rust toolchain to repo/CI.
- Any `analyze.py` output / schema change (tonnetz not added; contract unchanged).
- The crate's WASM phase (revisit only under a client-side-product decision).

# Phase 1 accuracy baseline — synthetic fundamentals corpus (2026-07-03)

First measured baseline for the accuracy program (`plans` → accuracy-program
Phase A). Source: `scripts/build_synthetic_corpus.py` (29 deterministic
clips) scored by `scripts/evaluate_fundamentals.py` against
`tests/fixtures/fundamentals_eval_manifest.synthetic.json`, current DSP
pipeline (Essentia RhythmExtractor2013 + Percival, EDMA KeyExtractor,
librosa 25-state Viterbi chords, kick-accent downbeats,
onset-autocorrelation meter). All numbers reproduce with:

```bash
cd apps/backend
./venv/bin/python scripts/build_synthetic_corpus.py
./venv/bin/python scripts/evaluate_fundamentals.py \
  --manifest tests/fixtures/fundamentals_eval_manifest.synthetic.json --fail-on-skip
```

## Summary

29/29 clips evaluated · **54 active checks passed, 0 failed** · 8 checks
informational (`knownGaps` — measured baseline weaknesses that do not gate).

## What the current pipeline gets RIGHT on clean synthetic material

| Domain | Result |
|---|---|
| Tempo (4/4, 70–128 BPM) | exact within ±1 BPM, incl. 70 BPM (no octave error on a clean pulse) |
| Beat grid (all meters incl. 3/4, 6/8, 7/8) | F1 0.95–0.98 at ±70 ms — the *beat* tracker is meter-agnostic and strong |
| Downbeats (4/4, accented kick) | F1 0.875 at ±100 ms (kick-accent heuristic works when accents exist) |
| Key (12 roots, major+minor, sine triads) | 14/14 exact (enharmonic-folded) |
| Chords (triad progressions, chords-only) | segment accuracy ≥ 0.65 on 13/14; F# major full marks after flat-spelling fix |
| Chords under a full mix (`--separate`) | ≥ 0.45 floor on both multi-layer clips — the PR-B4 stem-aware-chords target |
| Percussion counts (band-disjoint fixture) | kick 32/32, snare 16/16, hihat 16/16 exact |
| Monophonic transcription (bass, `--transcribe`) | note F1 ≥ 0.75 |

## Measured baseline gaps (the improvement targets — `knownGaps`, non-gating)

| Clip | Check | Baseline | Target owner |
|---|---|---|---|
| grid_3_4_90 | meter | reads 4/4 (truth 3/4) | PR-B1 evidence / PR-C1 beats backend |
| grid_3_4_90 | downbeats F1 | 0.286 | follows meter |
| grid_6_8_110 | meter | reads 4/4 (truth 6/8) | PR-B1 / PR-C1 |
| grid_6_8_110 | downbeats F1 | 0.400 | follows meter |
| grid_7_8_140 | meter | reads 4/4 (truth 7/8) | PR-B1 / PR-C1 |
| grid_7_8_140 | downbeats F1 | 0.182 | follows meter |
| grid_7_8_140 | tempo | 142.6 (truth 140.0) | PR-C1 |
| grid_4_4_174 | tempo | 86.9 (truth 174 — octave halving) | PR-C1 beats backend |

Pattern: **the beat grid is reliable everywhere; meter and therefore
downbeats are the weak layer on anything that isn't 4/4, and tempo octaves
break at range extremes.** This is precisely the case for running the
pre-registered beat_this gate (`incorporations/beat-this-measurement-gate-2026-05-20.md`).

## Trust-layer change recorded

`fundamentals_quality._tempo_quality` now treats `bpmAgreement=True` (two
independent estimators within tolerance) as settling evidence: mid-range
extractor confidence (≥ 0.5) with a confirming Percival cross-check is
`authoritative`, not `ambiguous`. Previously a clip with BPM measured
*exactly right* and cross-confirmed was hedged as "cross-check is not strong
enough", which was factually wrong.

## Caveats

- Synthetic sine/burst renders are easy mode: real-mix numbers will be lower.
  GiantSteps (key/tempo) and GTZAN (beats) intake — Phase A2/A3 — are the
  real-audio checks; never promote a backend on synthetic-only evidence.
- Swing ground truth (50–66%) is rendered and stored under each swing clip's
  manifest `truth` key, awaiting the PR-B2 swing measurement to become an
  active check.

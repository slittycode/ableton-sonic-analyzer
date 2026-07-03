# Fundamentals Benchmark Audio

Audio in this directory is generated on demand and is never committed.

Generate the default verify corpus (audio only — the committed default
manifest carries hand-maintained `requiredQuality` gates that the generator
does not emit, so never regenerate it):

```bash
./venv/bin/python scripts/build_synthetic_corpus.py \
  --out-dir tests/fixtures/fundamentals_tracks \
  --manifest tests/fixtures/fundamentals_eval_manifest.json \
  --check --audio-only
```

Generate the expanded synthetic corpus (this one's manifest IS generator-
owned; rerunning without `--audio-only` rewrites it deliberately):

```bash
./venv/bin/python scripts/build_synthetic_corpus.py --check
```

The committed manifests live one directory up. When a listed file is absent,
`scripts/evaluate_fundamentals.py` reports a skip; pass `--fail-on-skip` to make
missing audio fail the gate instead of producing a vacuous green run.

## Fixture design constraints (validated against the shipping detectors)

- **Grid clips** (tempo/beatGrid/downbeats/meter checks) are a bare accented
  kick pulse. Off-beat onsets bin ambiguously in `analyze_time_signature`'s
  ±half-beat onset counting and flip a straight 4/4 read to 3/4 or 6/8.
- **Count clips** (kick/snare/hihat counts) use band-disjoint engineered
  one-shots (kick ≤ ~60 Hz sine, snare 300–1500 Hz burst, hat 4–10 kHz burst)
  placed so no two instruments share an instant. The kick's 20 ms fade-in and
  0.20 s total length are load-bearing — see `_eng_kick` in
  `scripts/build_synthetic_corpus.py`.
- **Swing clips** carry swung-hat ground truth (under each manifest entry's
  `truth` key) for the future swing measurement; only BPM is an active check.
- **`knownGaps`** entries mark measured baseline weaknesses (odd-meter
  detection, tempo octave errors at range extremes). Those checks still run
  and report scores but don't gate the run — they are the accuracy program's
  improvement targets.

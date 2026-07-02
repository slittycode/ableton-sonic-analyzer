# Fundamentals Benchmark Audio

Audio in this directory is generated on demand and is never committed.

Generate the default verify corpus with:

```bash
./venv/bin/python scripts/build_synthetic_corpus.py \
  --out-dir tests/fixtures/fundamentals_tracks \
  --manifest tests/fixtures/fundamentals_eval_manifest.json \
  --check
```

Generate the expanded synthetic corpus with:

```bash
./venv/bin/python scripts/build_synthetic_corpus.py \
  --out-dir tests/fixtures/fundamentals_tracks \
  --manifest tests/fixtures/fundamentals_eval_manifest.synthetic.json \
  --check
```

The committed manifests live one directory up. When a listed file is absent,
`scripts/evaluate_fundamentals.py` reports a skip; pass `--fail-on-skip` to make
missing audio fail the gate instead of producing a vacuous green run.

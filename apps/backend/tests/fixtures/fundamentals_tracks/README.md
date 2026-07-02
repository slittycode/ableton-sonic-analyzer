# Fundamentals Benchmark Audio

Put owned, licensed, or locally rendered reference audio here to activate
`scripts/evaluate_fundamentals.py`.

The manifest is committed at `../fundamentals_eval_manifest.json`; audio files
in this directory are gitignored. When a listed file is absent, the harness
reports a skip. When it is present, the declared tempo, beat, meter, key,
chord, percussion, and transcription gates must pass.

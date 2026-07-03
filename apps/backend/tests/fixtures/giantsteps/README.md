# GiantSteps Key + Tempo corpora (operator-fetched, never committed)

Real-audio ground truth for ASA's key and tempo measurements: ~600 annotated
Beatport preview clips per subset, i.e. actual electronic music across the
EDM genre surface. This is the accuracy program's real-world check for the
key/tempo domains — synthetic-corpus wins must reproduce here before any
backend promotion (see `audits/accuracy-baseline-2026-07-03.md`).

## Layout

```
giantsteps/
  key/
    annotations/<beatport_id>.LOFI.key    # e.g. "D minor"
    audio/<beatport_id>.LOFI.mp3          # gitignored
  tempo/
    annotations/<beatport_id>.LOFI.bpm    # single BPM float
    audio/<beatport_id>.LOFI.mp3          # gitignored
  _repos/                                 # gitignored upstream clones
```

## Fetch (run locally — cloud proxies usually block the audio hosts)

```bash
cd apps/backend
./venv/bin/python scripts/fetch_giantsteps.py            # both subsets
./venv/bin/python scripts/fetch_giantsteps.py --verify-only
```

The fetcher clones the upstream annotation repos, stages annotations,
downloads previews from the Beatport sample host with the JKU mirror as
fallback, and verifies the repos' MD5 checksums. Preview URLs rot (2015-era
datasets); if both mirrors fail, `mirdata` (`pip install mirdata`, datasets
`giantsteps_key` / `giantsteps_tempo` — install into a scratch venv, not the
product venv) is the alternate acquisition path; keep the same layout.

## Evaluate

```bash
./venv/bin/python scripts/evaluate_giantsteps.py --subset key
./venv/bin/python scripts/evaluate_giantsteps.py --subset tempo --max-clips 100
```

Reports land in `.runtime/reports/giantsteps_<subset>.json` with MIREX
weighted key score / exact / exact-or-relative rates, and tempo Acc1/Acc2.
Zero evaluable clips exits 1 (`status: underpowered`) — never vacuous green.

## Licence

The annotation repositories are MIT-licensed and redistributable; the audio
previews are Beatport's content served for preview purposes. **Never commit
audio.** Everything under `key/audio/`, `tempo/audio/`, and `_repos/` is
gitignored; only this README is committed.

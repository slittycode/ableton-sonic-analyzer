# Owner actions — Phase 1 accuracy program

Operator tasks the accuracy program needs that require your machine (the
cloud sessions sit behind a proxy that blocks the dataset hosts). Everything
here is one-time setup; each item unblocks a specific gate. Code side is
done — see `audits/accuracy-baseline-2026-07-03.md` for what's already
measured without you.

## 1. Fetch GiantSteps Key + Tempo (~30 min, mostly download time)

Unblocks: real-audio key/tempo accuracy numbers (the synthetic baseline's
reality check), and the key-ensemble gate (PR-B3).

```bash
cd apps/backend
./venv/bin/python scripts/fetch_giantsteps.py           # both subsets
./venv/bin/python scripts/evaluate_giantsteps.py --subset key
./venv/bin/python scripts/evaluate_giantsteps.py --subset tempo
```

If the 2015-era preview mirrors have rotted, the fallback is `mirdata`
(scratch venv, datasets `giantsteps_key` / `giantsteps_tempo`) — keep the
layout in `apps/backend/tests/fixtures/giantsteps/README.md`.

## 2. Fetch GTZAN + GTZAN-Rhythm and build venv-eval (~45 min)

Unblocks: the frozen, pre-registered beat_this ship/no-ship decision
(`incorporations/beat-this-measurement-gate-2026-05-20.md`).

- GTZAN audio + the GTZAN-Rhythm annotations (mirror:
  `github.com/TempoBeatDownbeat/gtzan_tempo_beat`), laid out per
  `apps/backend/tests/fixtures/beat_tracks/README.md`.
- `python3.11 -m venv apps/backend/venv-eval && venv-eval/bin/pip install -r apps/backend/requirements-eval.txt`
  (beat_this + mir_eval — never into the product venv).
- `./venv/bin/python scripts/build_beat_manifest.py --root tests/fixtures/beat_tracks --out tests/fixtures/beat_eval_manifest.gtzan.json`

## 3. Hand-annotate the ASA electronic slice (~1–2 h — the ONE manual labeling task)

Unblocks: the beat gate's `MIN_CLIPS_ASA=15` requirement (without it the
gate reports `underpowered` and must not be finalized).

- Pick 15–20 GiantSteps previews (from action 1) spanning house/techno/dnb/garage.
- Annotate beat times + bar-1 downbeats (Audacity label track or Sonic
  Visualiser; export as `.beats` — one time per line, GTZAN-Rhythm format).
- Place under `apps/backend/tests/fixtures/beat_tracks/asa/{audio,annotations}/`.
- `./venv/bin/python scripts/build_beat_manifest.py --asa-slice --root tests/fixtures/beat_tracks --out tests/fixtures/beat_eval_manifest_asa.json`

GiantSteps previews are contamination-safe for beat_this (the dataset has no
upstream beat annotations, so it was never in the model's training data).

## 4. (Later, optional) Calibration corpus tracks

Unblocks: PR-D3 confidence-threshold calibration. Place ~10 tracks (synthetic
renders + GiantSteps previews are fine — your personal library is NOT
required) under `tests/ground_truth/tracks/` and fill `labels.json` with
verified values. The fake cache stubs were deleted 2026-07-03.

## Sequencing

Action 1 is independent and highest-value-per-minute. Actions 2+3 together
unblock the beat gate run (PR-C2) — the program's biggest expected accuracy
jump (meter → downbeats is the measured weak layer).

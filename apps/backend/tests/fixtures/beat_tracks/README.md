# Local beat-tracking evaluation corpus (NOT committed)

This directory holds audio + annotations for the beat/downbeat measurement gate
(`apps/backend/beat_evaluation.py`). **Nothing here is committed to git** — the
whole `beat_tracks/` path is gitignored, matching the `tests/ground_truth/tracks/`
convention. Audio is never redistributed in this repo.

## Why GTZAN

beat_this's shipped `final*`/`small*` checkpoints were trained on **all data except
GTZAN**, so GTZAN is the one public set that gives an *honest* (contamination-free)
measurement of beat_this. GTZAN-Rhythm (Marchand, Fresnel & Peeters, ISMIR 2015)
adds **beat + downbeat** annotations to GTZAN's 1000 clips — exactly what this gate
scores against.

## Layout

```
beat_tracks/
  gtzan/
    audio/<genre>/<genre>.000NN.wav       # GTZAN audio (obtain separately)
    annotations/<genre>.000NN.beats       # GTZAN-Rhythm: "<time_seconds> <beat_position>", pos 1 = downbeat
```

## How to obtain

- GTZAN audio: the GTZAN genre collection (10 genres × 100 clips, ~30 s each).
- GTZAN-Rhythm annotations: Marchand/Fresnel/Peeters 2015; a convenient mirror is
  `github.com/TempoBeatDownbeat/gtzan_tempo_beat`.
- Place them in the layout above, then build the manifest:
  `./venv/bin/python scripts/build_beat_manifest.py --root tests/fixtures/beat_tracks --out tests/fixtures/beat_eval_manifest.gtzan.json`

## Caveats

- **GTZAN label noise** (Sturm 2013): some duplicate/mislabeled/corrupt files. The
  harness reports per-genre metrics so outliers are visible; consider excluding the
  documented corrupt files.
- **Genre skew**: GTZAN is mixed-genre. The pass bar is judged on the
  `asaRelevant` subset (disco, hiphop, pop — the electronic-adjacent genres). A
  modern ASA electronic slice (`beat_eval_manifest_asa.json`) is the representativeness
  fast-follow; use only **user-owned / unreleased** tracks so the slice stays
  contamination-free for beat_this.

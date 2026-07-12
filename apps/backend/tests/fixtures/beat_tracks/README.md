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
  `asaRelevant` subset (disco, hiphop, pop — the electronic-adjacent genres). The
  modern ASA electronic slice (`beat_eval_manifest_asa.json`, built with
  `build_beat_manifest.py --asa-slice` from `<root>/asa/{audio,annotations}/`)
  is the representativeness requirement — the frozen gate needs >= 15 clips
  (`MIN_CLIPS_ASA`) or it reports `underpowered`. Contamination-safe sources:
  **user-owned / unreleased** tracks, or **hand-annotated GiantSteps Beatport
  previews** (fetched by `scripts/fetch_giantsteps.py`; GiantSteps carries no
  beat annotations upstream, so it is outside beat_this's training data —
  annotate bar-1 downbeats by hand, ~1-2 h for 15-20 clips, the one manual
  labeling task in the accuracy program).

## ASA electronic slice — annotation runbook

The GTZAN half of the gate is measured (see
`incorporations/beat-this-measurement-gate-2026-05-20.md`); this slice is the
remaining condition. `scripts/stage_asa_beat_slice.py` stages a deterministic
18-clip selection of GiantSteps previews (requires the fetched GiantSteps
corpus): 5 house-family, 5 techno-family, 4 drum-and-bass, 4 breaks/dubstep.
Beatport's 2015 taxonomy has **no "garage" genre**, so breaks + dubstep stand
in for the plan's garage slot. `asa/SELECTION.tsv` records clip -> family ->
Beatport genre.

1. Open `asa/audio/<id>.LOFI.mp3` in Audacity (or Sonic Visualiser).
2. Tap a **point label on every beat** (Cmd+B while playing, or click-then-B).
   Type the beat position as the label text **at least on every downbeat**
   (`1`); blank labels auto-continue counting (2, 3, 4, wrap) when converted.
   An explicit label always wins, so meter changes are expressible. The FIRST
   label must be explicit — bar 1 is anchored by a human, never inferred.
3. File → Export Labels → `<id>.LOFI.txt`, then convert:

   ```bash
   ./venv/bin/python scripts/convert_audacity_beats.py <id>.LOFI.txt \
       --out tests/fixtures/beat_tracks/asa/annotations/<id>.LOFI.beats
   ```

4. After >= 15 clips are annotated, build the slice manifest and finalize:

   ```bash
   ./venv/bin/python scripts/build_beat_manifest.py --asa-slice \
       --root tests/fixtures/beat_tracks --out tests/fixtures/beat_eval_manifest_asa.json
   ./venv-eval/bin/python scripts/evaluate_beats.py \
       --manifest tests/fixtures/beat_eval_manifest_asa.json --html
   ```

   The gate finalizes only if the >= 0.10 downbeat gain reproduces here
   (`asaSliceConfirms`); record the outcome in the pre-registration doc.

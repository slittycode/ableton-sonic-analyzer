# Real-Track Accuracy Bench

This directory holds copyrighted reference tracks used to audit ASA's Phase 1 measurement accuracy. The audio files are **never** committed — they live in your local copy only.

## What goes here

10–15 reference tracks (full MP3/WAV/FLAC files you own) covering the audit categories from the depth plan:

1. 3 four-on-the-floor electronic at varied tempos (e.g., 108 / 124 / 145 BPM) — the easy case
2. 2 half-time / double-time ambiguous tracks — tests the `bpmDoubletime` correction
3. 2 modal / non-tonal tracks — tests honest key-confidence failure
4. 2 mix-test tracks — one extremely wide, one mono — for stereo width
5. 2 sidechained tracks — one obvious, one subtle — for `sidechainDetail`
6. 1 polyrhythmic / odd-meter (e.g., 7/8) — exposes the 4/4 assumption
7. 1 vocally-led — for vocal detector and monophonic vocal key detection
8. 2–3 spare slots for edges discovered during audit

Total disk: roughly 150 MB.

## Registering a track

Add an entry to `../phase1_eval_manifest.json` under the `realTracks` array. The minimal shape is:

```json
{
  "id": "house_125_example",
  "audioPath": "house_125_example.mp3",
  "category": "four_on_floor",
  "description": "Standard four-on-the-floor at 125 BPM",
  "thresholds": {
    "bpm": { "target": 125.0, "tolerance": 2.0 },
    "key": { "equals": "F Minor" },
    "lufsIntegrated": { "target": -9.5, "tolerance": 0.5 }
  }
}
```

The `audioPath` is relative to this `bench_tracks/` directory.

### Ground-truth methodology

Per the audit plan:

- **BPM** — three-way agreement (Logic Pro BPM + Mixed In Key + tap-along). Disagreement = mark as "BPM ambiguous" rather than fail.
- **Key** — Mixed In Key + Logic detection + playing along. Modal/atonal → ground truth is "modal" with low `keyConfidence` target.
- **LUFS integrated** — Youlean (free EBU R128) or MeldaProduction MLoudnessAnalyzer. Tolerance ±0.5 LU.
- **Stereo width/correlation** — MeldaProduction MStereoAnalyzer or Voxengo Correlometer.
- **Spectral balance per band** — Voxengo SPAN integrated mode, 1/12-octave smoothing, same 7-band cutpoints as ASA. Tolerance ±1.5 dB.
- **Detectors** — listener writes one-line "is there acid? yes/no/maybe". Confidence below 0.4 on the wrong answer is **not** a failure — it's the system being honest.

## Running the bench

```bash
# Default — synthetic-only gate, always runnable, runs in CI
./venv/bin/python scripts/evaluate_phase1.py

# Local opt-in — runs real tracks when files exist, skips with notice when absent
./venv/bin/python scripts/evaluate_phase1.py --include-real

# Specify a custom directory for real tracks
./venv/bin/python scripts/evaluate_phase1.py --include-real --real-tracks-dir /path/to/tracks
```

When `--include-real` is passed but no audio files match the manifest entries, each missing track is reported as skipped (not failed) with a clear notice. The overall run still passes if all synthetic-fixture checks and any present real-track checks pass.

## Adding the real-track gate to your workflow

- Run `--include-real` locally during development of any change that affects high-stakes measurements (BPM, key, LUFS, spectralBalance, detectors).
- Run the milestone full-bench audit after Phase 1.A completes, after Phase 1.B completes, and before/after each Phase 1.C analyzer ships.
- CI continues to run the default synthetic gate only — real tracks never go through GitHub Actions.

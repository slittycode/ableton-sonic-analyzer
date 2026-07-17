# Ground Truth Dataset

## Purpose

This directory holds the ground truth dataset used by `scripts/calibrate_confidence.py` to calibrate confidence thresholds for `pitchConfidence`, `chordStrength`, and `pumpingConfidence`.

## Current state

**Status: awaiting real audio.** `labels.json` contains placeholder entries
documenting the expected schema; `tracks/` does not exist yet. The fake
`cache/` stubs that previously lived here were deleted (2026-07-03) — they
did not represent real analyzer output and would have silently corrupted any
calibration report. Running `scripts/calibrate_confidence.py` against this
directory as-is aborts with exit code `1` until audio is added.

**Corpus strategy (accuracy program):** the calibration corpus is built from
the synthetic fundamentals corpus (`apps/backend/scripts/build_synthetic_corpus.py`)
plus public EDM previews (GiantSteps intake — `apps/backend/scripts/fetch_giantsteps.py`).
The owner's personal library is NOT required. Update `labels.json` with
human-verified values for whichever tracks are placed in `tracks/`.

## How to populate

1. Choose 10 tracks from your personal library that match the genre criteria in `apps/backend/scripts/genre_corpus.md`. These must be files you own or otherwise have the right to use for local development analysis.
2. Create `tests/ground_truth/tracks/` and copy the tracks into it, named to match the track IDs in `labels.json`: `track_01_techno.mp3`, `track_02_house.mp3`, `track_03_dnb.mp3`, `track_04_ambient.mp3`, `track_05_electro.mp3`, `track_06_breaks.mp3`, `track_07_psy.mp3`, `track_08_dub.mp3`, `track_09_idm.mp3`, and `track_10_industrial.mp3`. Supported extensions are `.mp3`, `.wav`, `.flac`, `.aif`, and `.aiff`.
3. Open `tests/ground_truth/labels.json` and replace the placeholder values with human-verified labels for each track:
   - `genre` — your own description, not a generic category
   - `bpm` — from your DAW project or a reliable tap-tempo tool
   - `key` — verified by ear or a chromatic tuner
   - `has_sidechain` — `true` or `false`, verified by ear
   - `melody_accuracy` — `"high"` or `"low"`, based on your judgment of how well the DSP melody extraction performs on this track
   - `chord_accuracy` — `"high"` or `"low"`, based on your judgment of how well the DSP chord extraction performs on this track
4. Delete or replace the stubs in `tests/ground_truth/cache/`. They were hand-crafted and will produce misleading results if they are left alongside real audio.
5. Run the calibration script. It will analyze each track, cache the result in `tests/ground_truth/cache/`, and write a new report to `docs/confidence_calibration_results.md`.

```bash
python3 scripts/calibrate_confidence.py \
  --venv-python apps/backend/venv/bin/python
```

## Schema reference

| Field | Type | Description |
| --- | --- | --- |
| `genre` | `string` | Human-assigned genre label |
| `bpm` | `number` | Verified BPM |
| `key` | `string` | Verified key (for example, `"A minor"`) |
| `has_sidechain` | `boolean` | True if sidechain compression is audible |
| `melody_accuracy` | `string` | `"high"` or `"low"` |
| `chord_accuracy` | `string` | `"high"` or `"low"` |

## Related files

- `scripts/calibrate_confidence.py` — the calibration runner (writes to `docs/confidence_calibration_results.md` by default; create that file fresh on the next real-audio run)
- `docs/history/archive/confidence-calibration-results-stubs.md` — invalidated historical run against stub data (archived 2026-07 trust diet; restore via `git checkout archive/pre-trust-diet-2026-07 -- docs/history`)
- `apps/backend/scripts/genre_corpus.md` — genre selection criteria

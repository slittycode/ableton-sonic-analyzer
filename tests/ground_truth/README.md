# Ground Truth Dataset

## Purpose

This directory holds the ground truth dataset used by `scripts/calibrate_confidence.py` to calibrate confidence thresholds for `pitchConfidence`, `chordStrength`, and `pumpingConfidence`.

## Current state

**Warning: this dataset is not ready for real calibration yet.** `labels.json` currently contains placeholder entries, `cache/` currently contains hand-crafted stubs that do not represent real analyzer output, and `tracks/` does not exist yet, so no audio files have been added. If you run the calibration script against this directory as-is, it aborts with exit code `1` after reporting that all tracks are being served from cache with no audio files, that the cache stubs may not represent real analysis output, and that calibration has been aborted.

`ARTIFACT_CLEANUP_MAX` is a separate cleanup safeguard elsewhere in the backend. It is not the error message currently emitted by `scripts/calibrate_confidence.py` for this missing-audio ground truth directory.

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

- `scripts/calibrate_confidence.py` — the calibration runner
- `docs/confidence_calibration_results.md` — the output report, currently invalidated
- `apps/backend/scripts/genre_corpus.md` — genre selection criteria

# Polyphonic Full-Track Research Spike

**Status:** Research only. Not a production backend.  
**Updated:** March 23, 2026

## What This Is

ASA does not currently ship full-track polyphonic audio-to-MIDI as a product feature.

In plain English: on dense mixed producer tracks, current public models can generate note data, but they do not reliably generate note data that a producer can trust without heavy cleanup. That makes this a research question, not a product toggle.

The repo now includes a separate offline harness for comparing polyphonic candidates on a fixed corpus:

- module: `apps/backend/polyphonic_evaluation.py`
- CLI entry point: `apps/backend/scripts/evaluate_polyphonic.py`

This harness is intentionally **not** wired into:

- `apps/backend/analyze.py`
- `apps/backend/server.py`
- the public API
- the UI

## Current Candidates

- `basic-pitch`
  - lightweight baseline
  - used only when the `basic-pitch` executable is installed in the active backend environment
- `MT3`
  - heavier multi-instrument baseline
  - run only through an explicit `--mt3-command` template supplied by the researcher

In plain English: ASA will not try to guess how to run MT3 on your machine. You must point the harness at your own local wrapper or exported notebook script.

## What The Harness Produces

For each clip and each candidate, the harness writes:

- candidate MIDI output when available
- note-event CSV output when available
- optional Demucs stems for diagnostics only
- a JSON report with:
  - runtime
  - note count
  - pitch range
  - simple polyphony metrics
  - scorecard fields for manual review
  - candidate-level gate summary

The scorecard fields line up with the current decision gate:

- `bassRecognizable`
- `toplineRecognizable`
- `chordsNotObviouslyWrong`
- `cleanupMinutes30s`
- `notes`

## Manifest Format

The harness expects a manifest JSON with a fixed clip list. Example:

```json
{
  "currentStemAwareAverageRuntimeMs": 3200,
  "clips": [
    {
      "id": "dense_chords_01",
      "audioPath": "/absolute/path/to/dense_chords_01.wav",
      "tags": ["dense-chords", "electronic", "mastered"],
      "notes": "Pad stack plus bass and transient top line.",
      "manualReviewByCandidate": {
        "basic-pitch": {
          "bassRecognizable": null,
          "toplineRecognizable": null,
          "chordsNotObviouslyWrong": null,
          "cleanupMinutes30s": null,
          "notes": ""
        },
        "mt3": {
          "bassRecognizable": null,
          "toplineRecognizable": null,
          "chordsNotObviouslyWrong": null,
          "cleanupMinutes30s": null,
          "notes": ""
        }
      }
    }
  ]
}
```

Notes:

- `audioPath` may be absolute or relative to the manifest file.
- `currentStemAwareAverageRuntimeMs` is optional but recommended. It lets the report compare candidate runtime against the current stem-aware ASA path.
- `manualReviewByCandidate` is optional. If omitted, the harness will still create blank scorecards in the output report.

## Commands

Basic Pitch only:

```bash
cd /Users/christiansmith/code/projects/asa/apps/backend
./venv/bin/python scripts/evaluate_polyphonic.py \
  --manifest /absolute/path/to/polyphonic_manifest.json
```

Basic Pitch plus MT3:

```bash
cd /Users/christiansmith/code/projects/asa/apps/backend
./venv/bin/python scripts/evaluate_polyphonic.py \
  --manifest /absolute/path/to/polyphonic_manifest.json \
  --mt3-command "python /absolute/path/to/run_mt3.py --audio {audio_path} --midi-out {midi_path}"
```

With Demucs diagnostics:

```bash
cd /Users/christiansmith/code/projects/asa/apps/backend
./venv/bin/python scripts/evaluate_polyphonic.py \
  --manifest /absolute/path/to/polyphonic_manifest.json \
  --save-demucs-diagnostics
```

Important MT3 command note:

- the placeholders `{audio_path}`, `{output_dir}`, `{midi_path}`, and `{clip_id}` are shell-quoted by the harness
- do not wrap those placeholders in extra quotes inside your command template

## Recommended Corpus

Use 10 to 20 short clips that match ASA's actual target material:

- dense chords
- bass plus chords
- pad plus arpeggio
- vocal plus harmony
- piano-heavy material
- busy mastered mixes

Avoid treating classical proxy clips as sufficient proof for producer use.

## Decision Gates

Reopen productization only if a candidate clears all of these:

- recognizable bass notes on at least 80% of clips
- recognizable top-line melody on at least 80% of clips
- chord content not obviously wrong on at least 80% of clips
- average manual cleanup time no more than 5 minutes for a 30-second clip
- runtime no worse than 2x the current stem-aware path

Close the question if the outputs show any of these failure patterns:

- frequent note clutter
- octave junk
- missing inner voices
- unusable dense-chord output
- quality that only works on isolated or piano-like material
- heavy setup or runtime burden without a clear editability win

## Product Rule

Do not add a polyphonic backend to the product just because a model can emit MIDI.

In plain English: "possible" is not the bar. The bar is "good enough that a producer would actually choose to use it."

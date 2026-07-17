# Polyphonic Full-Track Research Spike

> **FROZEN 2026-07 (trust diet):** default-off/non-goal. Do not expand without the owner naming this subsystem. See `plans/trust-diet-2026-07.md`.

**Status:** Offline research harness. The MT3 candidate has since shipped as an **opt-in** product stage; this harness remains the comparison rig for other candidates.  
**Updated:** 2026-05-30

## What This Is

The original spike (March 2026) asked: should ASA ship full-track polyphonic audio-to-MIDI as a product feature, and which candidate? The answer landed in two parts:

- **MT3 was promoted** to an opt-in staged backend after this evaluation (`apps/backend/mt3_transcription.py`, run-level `mt3_mode='enabled'`, env var `ASA_ENABLE_MT3=1` on the legacy CLI). It is additive — measurement remains authoritative (PURPOSE.md invariant #1) — and off by default because dense-mix quality still varies.
- **The offline harness below is preserved** for comparing future candidates (or alternate MT3 wrappers, or `basic-pitch`) against a fixed corpus **without** touching the runtime. New candidates should clear this harness before any consideration of a runtime path.

In plain English: MT3 made it from spike to shipping (opt-in, additive only). Everything else still lives behind this offline harness.

The harness:

- module: `apps/backend/polyphonic_evaluation.py`
- CLI entry point: `apps/backend/scripts/evaluate_polyphonic.py`

It is intentionally **not** wired into:

- `apps/backend/analyze.py` (the `--transcribe` flag still uses torchcrepe; MT3 is a separate optional pass gated by `ASA_ENABLE_MT3`)
- the canonical product path inside `apps/backend/server.py` for new candidates
- the UI for new candidates

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
cd /path/to/asa/apps/backend
./venv/bin/python scripts/evaluate_polyphonic.py \
  --manifest /absolute/path/to/polyphonic_manifest.json
```

Basic Pitch plus MT3:

```bash
cd /path/to/asa/apps/backend
./venv/bin/python scripts/evaluate_polyphonic.py \
  --manifest /absolute/path/to/polyphonic_manifest.json \
  --mt3-command "python /absolute/path/to/run_mt3.py --audio {audio_path} --midi-out {midi_path}"
```

With Demucs diagnostics:

```bash
cd /path/to/asa/apps/backend
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

## Corpus + Scoring Workflow

The harness ships with a dedicated fixtures directory and an interactive scorecard CLI to reduce the friction of running this spike on a real corpus.

This corpus is distinct from the Layer 2 (torchcrepe) bench at `apps/backend/tests/fixtures/transcription_tracks/`. Use:

- **`tests/fixtures/polyphonic_tracks/`** — dense, mixed, mastered material for *this* research spike.
- **`tests/fixtures/transcription_tracks/`** — monophonic-friendly material for Layer 2, which **is** in the product. See `docs/LAYER2_EVALUATION.md`.

A clip that fits one corpus generally does not fit the other.

### Target material distribution

10–20 short clips, 20–40 seconds each, weighted toward producer-realistic mixes:

1. 3–4 dense electronic mixes (mastered, chord-stack-heavy)
2. 2–3 vocal-heavy with backing harmony
3. 2–3 piano-only / piano-heavy clips
4. 2–3 busy mastered full-band mixes
5. 1–2 pad + arpeggio / pad + bass slices
6. 1–2 sparse / minimal clips (negative examples for the `sparse_likely_undertranscribed` diagnostic)

### Sourcing checklist

1. Use audio you own or license. Nothing copyrighted is committed; the fixtures directory carries only a `README.md`.
2. Mono or stereo both fine.
3. Format: WAV / FLAC / MP3 / M4A all work.
4. Pick clips where you can confidently answer all five scorecard fields. Clips that leave the reviewer unsure are not useful gate material.

### Where clips live

`apps/backend/tests/fixtures/polyphonic_tracks/` (never committed). The harness itself does not assume a checked-in manifest — you supply a manifest path via `--manifest`. `audioPath` entries may be absolute or relative to the manifest file.

### Scoring CLI

After running `evaluate_polyphonic.py`, score the clips interactively:

```bash
cd apps/backend
./venv/bin/python scripts/score_polyphonic_clip.py \
  --report .runtime/polyphonic_eval/polyphonic_eval_report.json
```

The CLI walks each unscored clip × candidate pair, plays the audio (`afplay` / `paplay` / `aplay`), surfaces the diagnostic `flags` plus key metrics, and writes the scorecard back into the report JSON in place.

Flags:

- `--rescore` — re-prompt for clips that already have a complete scorecard.
- `--no-play` — skip audio playback. Required for non-interactive / headless usage.
- `--candidate <id>` — limit scoring to a single candidate, e.g. `--candidate basic-pitch`.

After the CLI exits, re-run the per-candidate gate by feeding the updated report through `summarize_candidate_gate` (the harness's main JSON report regenerates the rollups automatically on the next `evaluate_polyphonic.py` run).

### Diagnostic flags are seeding only

`summarize_midi_file` now emits a richer `flags` list that steers the reviewer's listening attention. These flags are **diagnostic seeding only** — they do not bypass the five manual usefulness gates, and a clip with no flags can still fail the gates on listen-through:

- `note_clutter` — > 15 notes / sec; likely junk
- `octave_junk` — > 30 distinct pitches with mean active polyphony < 3; suggests scattered octave errors
- `dense_chords_unusable` — max polyphony > 8 simultaneous notes; usually unrecoverable
- `sparse_likely_undertranscribed` — < 1 note / sec across a 10s+ clip; the model probably gave up
- `empty_output`, `monophonic_output`, `high_note_density` — pre-existing flags

In plain English: the flags tell you what to listen *for*. The gates tell you whether to ship.

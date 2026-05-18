# Polyphonic Research Corpus

This directory holds short polyphonic audio clips used by the **research** harness at `apps/backend/scripts/evaluate_polyphonic.py`. The audio files are **never** committed — they live in your local copy only.

This corpus is **not** the same thing as `../transcription_tracks/`. Use:

- **`polyphonic_tracks/`** (this directory) — dense, mixed, mastered material used to evaluate research candidates (`basic-pitch`, `MT3`) against the manual usefulness gates in `docs/POLYPHONIC_TRANSCRIPTION_SPIKE.md`.
- **`transcription_tracks/`** — monophonic-friendly material (vocal leads, isolated bass, simple synth leads) used to evaluate Layer 2 (torchcrepe), which **is** in the product. See `docs/LAYER2_EVALUATION.md`.

A track that fits one corpus generally does not fit the other.

## What goes here

10–20 short clips (20–40s each) drawn from material ASA's polyphonic research is supposed to handle, weighted toward producer-realistic mixes rather than toy or classical proxies:

1. 3–4 dense electronic mixes (mastered, chord-stack-heavy)
2. 2–3 vocal-heavy material with backing harmony
3. 2–3 piano-only / piano-heavy clips
4. 2–3 busy mastered full-band mixes
5. 1–2 pad + arpeggio / pad + bass slices
6. 1–2 sparse / minimal clips (the corpus needs negative examples too — see the `sparse_likely_undertranscribed` flag in `polyphonic_evaluation.summarize_midi_file`)

Clips longer than 40 s blow up scoring time; shorter than 20 s rarely give the reviewer enough material to judge fairly.

Total disk: roughly 50–150 MB depending on encoding.

## Manifest

This directory does **not** ship its own checked-in manifest — the polyphonic harness already exercises tempfile-based manifests end-to-end in `tests/test_polyphonic_evaluation.py`. To run the harness on this corpus, point it at a manifest you write locally:

```bash
cd apps/backend
./venv/bin/python scripts/evaluate_polyphonic.py \
  --manifest /path/to/local_polyphonic_manifest.json
```

The manifest format is documented in `docs/POLYPHONIC_TRANSCRIPTION_SPIKE.md`. `audioPath` may be absolute or relative to the manifest file — relative paths typically point into this directory.

## Sourcing checklist

1. Use audio you own or license. Nothing copyrighted is committed.
2. Mono or stereo both fine — the harness does not constrain channel count.
3. Format: WAV / FLAC / MP3 / M4A all work via `soundfile` / `librosa`.
4. Pick clips where you, as a reviewer, can confidently answer the five scorecard fields: `bassRecognizable`, `toplineRecognizable`, `chordsNotObviouslyWrong`, `cleanupMinutes30s`, plus optional notes. If you can't answer, the clip isn't useful for the gate.

## Scoring workflow

After running the harness:

```bash
cd apps/backend
./venv/bin/python scripts/score_polyphonic_clip.py \
  --report .runtime/polyphonic_eval/polyphonic_eval_report.json
```

The CLI walks unscored clip × candidate pairs, plays the audio (via `afplay` on macOS / `paplay` / `aplay` on Linux), surfaces the diagnostic `flags` and key metrics, and writes the scorecard back into the report JSON in place. Pass `--no-play` to skip playback, `--rescore` to revisit completed entries, `--candidate <id>` to limit to one candidate.

Diagnostic flags emitted by `summarize_midi_file` are seeding hints only — they steer your listening attention but do not bypass the manual gates:

- `note_clutter` — note density > 15 notes/sec; likely junk
- `octave_junk` — >30 distinct pitches with mean active polyphony < 3; suggests scattered octave errors
- `dense_chords_unusable` — max polyphony > 8 simultaneous notes; usually unrecoverable
- `sparse_likely_undertranscribed` — under 1 note/sec across a 10s+ clip; model probably gave up
- `empty_output`, `monophonic_output`, `high_note_density` — pre-existing flags (see `polyphonic_evaluation.py`)

# Layer 2 (Torchcrepe) Transcription Bench

This directory holds reference audio used to audit ASA's Layer 2 pitch/note translation. The audio files and their reference MIDI are **never** committed — they live in your local copy only.

This bench is the counterpart to the polyphonic research corpus at `../polyphonic_tracks/`. Use **this** directory for material that Layer 2 (torchcrepe, monophonic-friendly) is expected to handle well; use the polyphonic directory for dense mixed material that exists only to validate research candidates.

## What goes here

8–15 short reference clips (10–40s each) covering the categories Layer 2 is supposed to handle:

1. 3 monophonic vocal leads — isolated vocal stems or vocal-only renders
2. 3 isolated bass lines — DI bass, bass synth stems, or bass-only renders
3. 2 simple synth leads — saw / square / sine monophonic leads, ideally with light vibrato to exercise the pitch-jump splitter
4. 1 whistled / hummed line — single-source, near-pure-tone material
5. 1–2 acoustic instrument leads (flute, trumpet, sax) — monophonic acoustic timbres
6. 1–2 spare slots for failure modes discovered during audit (rapid runs, glissandi, voice cracks)

Explicitly **out of scope** for this directory: dense chords, polyphonic piano, full mixes — those belong in `polyphonic_tracks/` and are not Layer 2's job.

Total disk: roughly 50–100 MB.

## Registering a track

Add an entry to `../phase1_eval_manifest.json` under the `transcriptionTracks` array. The minimal shape is:

```json
{
  "id": "monophonic_synth_lead_01",
  "audioPath": "lead_01.flac",
  "category": "monophonic_lead",
  "description": "Saw lead over silence, monophonic, ~120 BPM",
  "analyzeFlags": ["--separate", "--transcribe"],
  "groundTruthNotes": [
    { "pitchMidi": 60, "onsetSeconds": 0.50, "durationSeconds": 0.25 }
  ],
  "thresholds": {
    "noteMetrics.f1":                        { "target": 0.75, "tolerance": 0.0,  "direction": "min" },
    "noteMetrics.meanPitchCentsError":       { "target": 0.0,  "tolerance": 50.0 },
    "transcriptionDetail.averageConfidence": { "target": 0.65, "tolerance": 0.0,  "direction": "min" }
  }
}
```

`audioPath` is relative to this `transcription_tracks/` directory. `groundTruthNotes` uses the same `pitchMidi`/`onsetSeconds`/`durationSeconds` shape as `transcriptionDetail.notes` emitted by analyze.py. Threshold fields under `noteMetrics.*` resolve against the per-track precision/recall/F1 computed by the harness; everything else resolves against the analyzer payload directly.

### Building ground-truth notes from MIDI

The harness ships a one-shot converter at `apps/backend/scripts/import_midi_to_ground_truth.py`. The producer workflow:

1. Export a reference MIDI file from your DAW (Logic / Ableton / Reaper / Cubase / etc.). Quantization is optional — the harness's onset tolerance is ±50 ms.
2. Run the converter:

```bash
./venv/bin/python scripts/import_midi_to_ground_truth.py reference.mid
```

3. Paste the emitted JSON array into your manifest entry's `groundTruthNotes` field.

Flags:

- `--monophonic-collapse highest` — when notes overlap, keep the highest pitch and drop the lower ones. Use for chordal MIDI that you want to flatten to a melodic line.
- `--monophonic-collapse reject` (default) — exit non-zero if any notes overlap. Use to catch accidental polyphony.
- `--offset-seconds N` — add `N` seconds to every onset. Use when your DAW reports a negative track delay or you trimmed silence from the head of the audio after exporting MIDI.

### Ground-truth methodology

- **Pitch** — DAW MIDI is authoritative. The harness compares semitone-quantized MIDI integers; a ±1 semitone tolerance is baked into the matcher.
- **Onset** — DAW MIDI is authoritative; ±50 ms tolerance.
- **F1 target** — 0.75 is a starting threshold for monophonic material. Tighten per-category once you have a baseline.
- **Confidence** — `transcriptionDetail.averageConfidence` ≥ 0.65 is a sanity check that Layer 2 is not running at the floor; not a substitute for F1.

## Running the bench

```bash
# Default — synthetic-only gate, always runnable, runs in CI
./venv/bin/python scripts/evaluate_phase1.py

# Layer 2 opt-in — runs the stepped-sine self-test plus any registered transcription tracks
./venv/bin/python scripts/evaluate_phase1.py --include-transcription

# Specify a custom directory for transcription tracks
./venv/bin/python scripts/evaluate_phase1.py --include-transcription --transcription-tracks-dir /path/to/tracks
```

The stepped-sine self-test always runs when `--include-transcription` is set, so you get at least one F1 row even before populating the corpus. Missing audio for manifest-registered tracks is reported as skipped (not failed) with a clear notice.

# Layer 2 (Torchcrepe) Evaluation

**Status:** Local opt-in. Synthetic self-test runs on demand; real corpus is user-side.
**Updated:** 2026-05-16

## What This Is

ASA's three-layer architecture (`docs/ARCHITECTURE_STRATEGY.md`) splits work into:

1. **Layer 1** — deterministic measurement (Essentia / DSP).
2. **Layer 2** — pitch/note translation (torchcrepe), on Demucs-separated stems.
3. **Layer 3** — interpretation (Gemini), grounded in Layer 1.

Layer 1 had a real-track gate (`tests/fixtures/bench_tracks/`). Layer 2 did not. This doc closes that asymmetry: a dedicated bench under `tests/fixtures/transcription_tracks/`, a harness extension to `phase1_evaluation.py`, and an interactive workflow for turning DAW MIDI into ground-truth notes.

This is **not** the same thing as `docs/POLYPHONIC_TRANSCRIPTION_SPIKE.md`. That spike covers research candidates (basic-pitch, MT3) on **polyphonic** material and is explicitly product-gated by manual usefulness gates. Layer 2 here is the **shipped** product backend (`apps/backend/analyze_transcription.py:TorchcrepeBackend`), and its target corpus is monophonic-friendly material the product is expected to handle.

## Target Material

8–15 short clips (10–40s each) across these categories:

1. Monophonic vocal leads (isolated vocal stems, vocal-only renders)
2. Isolated bass lines (DI bass, bass synth stems, bass-only renders)
3. Simple monophonic synth leads (saw / square / sine, light vibrato welcome)
4. Whistled / hummed lines
5. Acoustic monophonic instruments (flute, sax, trumpet)
6. Spare slots for failure modes discovered during audit (rapid runs, glissandi, voice cracks)

Out of scope: dense polyphony, piano stacks, full mixes. Those go in `tests/fixtures/polyphonic_tracks/` and are evaluated by the polyphonic research harness, not by Layer 2.

## Sourcing Workflow

1. Use audio you own or license. Nothing copyrighted is committed; the fixtures directory contains only a `README.md`.
2. Export a reference MIDI file from your DAW (Logic / Ableton / Reaper / Cubase / etc.). Quantization is acceptable — the harness's onset tolerance is ±50 ms.
3. Convert the MIDI into the `groundTruthNotes` JSON fragment:

```bash
cd apps/backend
./venv/bin/python scripts/import_midi_to_ground_truth.py /path/to/reference.mid
```

4. Paste the emitted JSON array into `tests/fixtures/phase1_eval_manifest.json` under your `transcriptionTracks[].groundTruthNotes` field.

Useful flags on the importer:

- `--monophonic-collapse highest` — when MIDI has overlapping notes, keep the highest pitch and drop the rest. Use to flatten chordal MIDI to a melodic line.
- `--monophonic-collapse reject` (default) — exit non-zero on any overlap. Useful to catch accidental polyphony before it lands in the bench.
- `--offset-seconds N` — add `N` seconds to every onset. Use when DAW MIDI export starts before/after the corresponding audio (e.g. negative track delay, head silence trimmed after MIDI export).

## Manifest Entry Shape

```json
{
  "id": "monophonic_synth_lead_01",
  "audioPath": "lead_01.flac",
  "category": "monophonic_lead",
  "description": "Saw lead, monophonic, ~120 BPM",
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

Fields under `noteMetrics.*` are computed by the harness (precision / recall / f1 / meanPitchCentsError / matchedCount / missedCount / falsePositiveCount) and matched against `_evaluate_threshold`. Every other dotted path resolves against the raw analyzer payload — i.e. it can target anything `analyze.py` emits.

The threshold-direction extension is new:

- `{"direction": "min"}` — pass when `actual >= target - tolerance`.
- `{"direction": "max"}` — pass when `actual <= target + tolerance`.
- No `direction` key — symmetric `|actual - target| <= tolerance` (original behavior).

## Threshold Interpretation

| Metric | Meaning | Starting target |
|---|---|---|
| `noteMetrics.f1` | Harmonic mean of precision and recall under ±50 ms onset + ±1 semitone matching | ≥ 0.75 for monophonic; tighten per-category |
| `noteMetrics.meanPitchCentsError` | Signed mean cents error across matched pairs (multiples of 100 because pitchMidi is an integer in the analyze.py contract) | within ±50 cents (i.e. within one semitone bias) |
| `transcriptionDetail.averageConfidence` | torchcrepe periodicity averaged across notes | ≥ 0.65 as a floor sanity check |

The matcher tolerances (`onset_window_s=0.05`, `pitch_tolerance_semitones=1`) are baked into `_match_notes` rather than per-track. If a clip needs different tolerances, add a per-track parameter later — for now, choose a clip that fits these constants or hand-edit ground truth to absorb the offset.

The harness writes one synthetic self-test (`stepped_sine_synthetic`) every time `--include-transcription` is set, so you get at least one F1 row even before populating the corpus. The self-test uses a 0.5 target so it does not fail on torchcrepe's onset jitter for short tones.

## Running the Bench

```bash
# Default — synthetic-fixture gate, no transcription, always runnable
./venv/bin/python scripts/evaluate_phase1.py

# Layer 2 opt-in — stepped-sine self-test + any registered transcription tracks
./venv/bin/python scripts/evaluate_phase1.py --include-transcription

# Custom transcription tracks directory
./venv/bin/python scripts/evaluate_phase1.py --include-transcription \
  --transcription-tracks-dir /path/to/tracks
```

When `--include-transcription` is set but no audio files match the manifest entries, each missing track is reported as skipped (not failed) with a clear notice. The overall run still passes if synthetic + present-real + present-transcription checks pass.

## What This Doesn't Cover

- **Polyphonic accuracy** — out of scope; that's the polyphonic spike's job.
- **Sub-semitone pitch accuracy** — `pitchMidi` is integer in the analyzer contract. If finer reporting becomes a requirement, switch the matcher to use the underlying CREPE pitch-Hz output rather than the quantized MIDI integer.
- **Stem-separation quality** — the harness assumes whatever stems Demucs produced. Stem quality regressions surface as transcription regressions but the harness does not isolate them.

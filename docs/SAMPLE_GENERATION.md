# Sample Generation (Phase 3 — Audition)

> **Status:** Shipped on `main` as an on-demand feature (`POST/GET /api/analysis-runs/{run_id}/samples`). Not part of the staged-execution queue — the UI requests it explicitly after interpretation completes.
> **Mission fit:** Improves the user's ability to *act on* Phase 2 results by producing audible reference clips they can A/B against the source track.

## Why This Exists

ASA's chain of custody — Phase 1 measurement → Phase 2 Ableton recommendation — is the product. The recommendation cites a number; the number came from DSP. But a user reading "Glue Compressor → Ratio 4:1, Attack 10ms, informed by crest factor 8.2 dB" still has to *trust* that the chain is honest before opening Ableton and dialing it in.

Audition samples close that loop: render small, heuristic audio clips derived from the same Phase 1 measurements and Phase 2 musical decisions, and let the user ear-check whether the chain reproduces the *tonal character* of the reference. If the chord progression sounds nothing like the source, that's a signal to scrutinize the key/mode detection. If the kick fundamental feels off, that's a signal to look at `kickDetail.fundamentalHz`.

Critically, **audition samples are not Ableton-accurate reconstructions**. The Phase 2 recommendation might say "Operator with Sine + Sub + Triangle, soft-clipped." We won't render that. We'll render a credible bass note in the right key with a heuristic synth voice. The user still has to follow Phase 2's advice in Ableton to get the recommended *timbre*. The samples verify the *musical foundation* — key, mode, chord progression, bass root, drum fundamental, melody contour — not the *production character*.

## Quality Invariant Alignment

Mapping to the non-negotiables in [PURPOSE.md](../PURPOSE.md):

| Invariant | How samples honor it |
|---|---|
| **#1 Measurement authority** | Samples are derived from Phase 1 measurements (key, kickDetail.fundamentalHz, melodyDetail). They never re-estimate. If a measurement is low-confidence, the corresponding sample is omitted or labeled hedged. |
| **#2 Citation chain** | Every generated artifact carries a `provenance.cites` array listing the Phase 1 fields and Phase 2 recommendations that drove it. The manifest is the audit trail. |
| **#3 Ableton specificity** | The UI must clearly frame samples as "heuristic audition, not Ableton-accurate." Phase 2 remains the authoritative blueprint; samples illustrate the foundation. |
| **#4 Honest uncertainty** | If `keyConfidence < 0.5`, tonal samples are emitted with a `lowConfidence: true` flag and a hedged label. Drum samples respect the same threshold for `kickDetail.confidence`. |
| **#5 Reconstruction completeness** | First iteration covers tonal/harmonic + drum + melody. Production-character samples (e.g. sidechain pumping, reverb tails) are out of scope — those belong in Ableton. |
| **#6 Intermediate accessibility** | The user sees a panel of labeled audio players ("Chord progression in F# minor", "Kick at 53 Hz"), not a JSON dump. |

## Scope (First Iteration)

Generated artifacts per run:

| Artifact | Driven by | Synthesis approach |
|---|---|---|
| `tonal_chord_progression.wav` | `phase1.key`, `phase1.bpm`, optional `phase2.styleProfile.authoritativeMeasurements` | PyTheory chord voicings → MIDI → FluidSynth GM piano OR sine-additive fallback |
| `tonal_bass_root.wav` | `phase1.key`, `phase1.bpm`, `phase1.bassDetail` if present | Sustained bass note on the key root, 8 bars |
| `drum_kick.wav` | `phase1.kickDetail.fundamentalHz`, `kickDetail.decayTimeMs` | NumPy: sub-sine + click transient, no PyTheory involvement |
| `drum_snare.wav` | Heuristic 200 Hz body + noise burst | NumPy noise + tone |
| `drum_hat.wav` | Heuristic filtered noise burst | NumPy noise |
| `melody_lead.wav` | `phase1.melodyDetail`, optional pitch/note translation `bars[].noteHypotheses` | Step through detected scale degrees on a triangle/saw voice |
| `samples_manifest.json` | All of the above | JSON catalog with citations and confidence |

Each WAV is ≤ 5 seconds, mono or stereo, 44.1 kHz, 16-bit PCM — small enough to stream cheaply and short enough to be auditioned at a glance.

## Out of Scope (First Iteration)

- Full-loop combined arrangement (drums + bass + chords in one track). Possible follow-up; multiplies complexity for arguably less educational value than separate stems.
- Production-character rendering (compression, sidechain, reverb tails). Those are *what Phase 2 tells the user to dial in Ableton*. Reproducing them here would muddle the message.
- A new pipeline stage row in `analysis_runtime.py`'s schema. Samples ride on the existing `run_artifacts` table with `kind` values (`sample_audio`, `sample_midi`, `sample_manifest`). Promotion to a first-class stage with progress tracking is a follow-up if the audition value pans out.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ User action: clicks "Generate audition samples" in AnalysisResults  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼  POST /api/analysis-runs/{run_id}/samples
              ┌────────────────────────────────────┐
              │   server_samples.py                │
              │   - load phase1 + phase2 from      │
              │     analysis_runs / interpretation │
              │   - reject if measurement not      │
              │     completed; phase2 is optional  │
              └────────────────┬───────────────────┘
                               │
                               ▼
              ┌────────────────────────────────────┐
              │   sample_generation.generate(...)  │
              │                                    │
              │   sample_theory.plan_clips()       │
              │     ├── PyTheory if available      │
              │     └── pure-Python fallback       │
              │                                    │
              │   sample_drums.synth_kick/snare/   │
              │     hat()  └── NumPy oscillators   │
              │                                    │
              │   sample_synthesis.render_midi()   │
              │     ├── FluidSynth if available    │
              │     └── sine-additive fallback     │
              └────────────────┬───────────────────┘
                               │
                               ▼
              ┌────────────────────────────────────┐
              │   runtime.record_artifact()        │
              │   - one row per sample in          │
              │     run_artifacts (kind=sample_*)  │
              │   - manifest as sample_manifest    │
              └────────────────┬───────────────────┘
                               │
                               ▼  GET /api/analysis-runs/{run_id}/samples
              ┌────────────────────────────────────┐
              │   Frontend: SamplePlayback.tsx     │
              │   - <audio> per artifact           │
              │   - citation chip per sample       │
              │   - "heuristic audition" framing   │
              └────────────────────────────────────┘
```

The node labels above are schematic. The actual entry points are
`sample_generation.generate_samples()` (orchestrator);
`sample_theory.plan_chord_progression()` / `plan_bass_root()` / `plan_melody_phrase()`;
`sample_drums.synth_kick()` / `synth_snare()` / `synth_hat()`;
`sample_synthesis.render_clip()` and `write_midi()`; and the
`AnalysisRuntime.record_artifact()` method in `analysis_runtime.py`.

## Module Inventory

| File | Role |
|---|---|
| `apps/backend/sample_theory.py` | Phase 1+2 → MIDI plan. PyTheory adapter with self-contained fallback. |
| `apps/backend/sample_drums.py` | NumPy kick/snare/hat one-shots driven by Phase 1 measurements. |
| `apps/backend/sample_synthesis.py` | MIDI plan + drum buffers → WAV. FluidSynth with sine-additive fallback. |
| `apps/backend/sample_generation.py` | Orchestrator. Produces manifest with citations. |
| `apps/backend/server_samples.py` | HTTP routes (POST/GET on `/api/analysis-runs/{run_id}/samples`). |
| `apps/ui/src/services/sampleGenerationClient.ts` | Typed HTTP client + polling. |
| `apps/ui/src/components/SamplePlayback.tsx` | Audio player UI with citation chips. |
| `apps/ui/src/types/samples.ts` | Type definitions shared with the backend manifest. |

## Manifest Shape

`samples_manifest.json` — the chain-of-custody record for an audition run.

```json
{
  "schemaVersion": "samples.v1",
  "runId": "…",
  "generatedAt": "2026-05-14T20:31:00Z",
  "synthesisBackend": "fluidsynth" | "sine_fallback",
  "soundfont": "FluidR3_GM.sf2" | null,
  "framing": "Heuristic audition. Verifies tonal/rhythmic foundation, not Ableton timbre.",
  "samples": [
    {
      "id": "tonal_chord_progression",
      "label": "Chord progression in F# minor",
      "category": "tonal" | "drums" | "melody",
      "filename": "tonal_chord_progression.wav",
      "mimeType": "audio/wav",
      "durationSeconds": 4.62,
      "midiFilename": "tonal_chord_progression.mid",
      "confidence": "HIGH" | "MED" | "LOW",
      "lowConfidence": false,
      "cites": {
        "phase1Fields": ["key", "keyConfidence", "bpm"],
        "phase2Recommendations": [],
        "rationale": "8-bar i–VI–III–VII voicing in detected key (F# minor, confidence 0.87)."
      }
    },
    {
      "id": "drum_kick",
      "label": "Kick at 53 Hz",
      "category": "drums",
      "filename": "drum_kick.wav",
      "mimeType": "audio/wav",
      "durationSeconds": 0.45,
      "confidence": "HIGH",
      "cites": {
        "phase1Fields": ["kickDetail.fundamentalHz", "kickDetail.decayTimeMs"],
        "phase2Recommendations": ["sonicElements.kick"],
        "rationale": "Sub-sine at measured fundamental with measured decay envelope."
      }
    }
  ]
}
```

## HTTP Contract

### `POST /api/analysis-runs/{run_id}/samples`

Generate audition samples for a run. Synchronous — small clips, small CPU budget.

**Preconditions:** run exists, `stages.measurement.status == "completed"`, ownership matches if in hosted mode.
**If interpretation is not completed:** still generate tonal+drum samples from Phase 1 (Phase 2 just enriches labels). Skip melody if `melodyDetail` is unavailable.

**Response:** 201 with the manifest body (camelCase JSON). 409 if a manifest already exists and `?force=true` was not passed.

### `GET /api/analysis-runs/{run_id}/samples`

Return the manifest if one has been generated, 404 otherwise.

### Streaming individual samples

There is no dedicated `/samples/{sample_id}` route. The manifest includes an `artifactId` on each sample (and `midiArtifactId` where a MIDI was rendered); clients stream the underlying file through the existing artifact route:

```
GET /api/analysis-runs/{run_id}/artifacts/{artifact_id}
```

This keeps audition WAV/MIDI access on the same code path as every other run-scoped artifact (spectrograms, stems, source audio).

### Snapshot integration

Sample generation is **not** a stage on `AnalysisRunSnapshot.stages` — the snapshot still tracks the three queued stages only (`measurement`, `pitchNoteTranslation`, `interpretation`). Audition samples ride on the existing `run_artifacts` table with `kind` values `sample_audio`, `sample_midi`, and `sample_manifest`, and the manifest itself is fetched directly via `GET /api/analysis-runs/{run_id}/samples` (404 when not yet generated).

The synthesis backend used and the generated-at timestamp are recorded on the manifest body, not on the snapshot. Promotion to a first-class stage with `publicStatus` tracking is a follow-up if audition value pans out.

## Dependencies

| Package | Required? | Fallback if absent |
|---|---|---|
| `pytheory>=0.42` | Optional | Pure-Python `sample_theory.py` covers note names, scales, common chord voicings. |
| `pyfluidsynth>=1.3` | Optional | NumPy sine-additive synthesis (raw but audible, in-tune). |
| `libfluidsynth` (system) | Optional | Same as above. |
| Soundfont (GM `.sf2`) | Optional | Same as above. |

Both Python deps are added to `requirements.txt` because they install cleanly via pip. The system `libfluidsynth` library and a soundfont file are *not* required for the feature to function — the sine fallback is exercised in tests so the code path is real, not a placeholder.

**Bootstrap implication:** `apps/backend/scripts/bootstrap.sh` does not install `libfluidsynth`. Operators who want high-quality renders should install it via their system package manager and drop an `.sf2` at `apps/backend/assets/soundfonts/default.sf2` (path documented in the module).

## Test Strategy

- **`tests/test_sample_theory.py`** — exercises both PyTheory and fallback paths for known keys, asserts MIDI note numbers are correct. Must pass without `pytheory` importable.
- **`tests/test_sample_drums.py`** — generates a kick at 80 Hz, asserts the FFT peak lands within ±20 Hz of fundamental. The wide tolerance is intentional: the pitch envelope starts an octave above the requested fundamental and decays, so steady-state energy can sit a little above the target.
- **`tests/test_sample_synthesis.py`** — renders a known MIDI plan through the sine fallback, asserts the WAV is well-formed and contains audio energy at expected frequencies.
- **`tests/test_sample_generation.py`** — end-to-end with synthetic phase1+phase2 input. Asserts manifest contains every promised sample, each cites at least one phase1 field, low-confidence keys produce hedged labels.
- **`tests/test_server_samples.py`** — contract test for the new endpoints using FastAPI TestClient.
- **`apps/ui/tests/services/sampleGenerationClient.test.ts`** — Vitest unit test for the typed client + manifest parsing.

## Rollout

1. Land prototype behind no feature flag (the endpoint is opt-in by virtue of requiring an explicit POST).
2. Frontend shows the trigger after Phase 2 (interpretation) finishes and renders the results once the manifest is available (a `200` from `GET /api/analysis-runs/{run_id}/samples`; `404` until generated). Sample generation is *not* a snapshot stage — see "Snapshot integration" above — so there is no `stages.sampleGeneration.status` to gate on.
3. Iterate on synthesis quality based on real-track auditioning. Specifically: tune the chord-voicing rules, evaluate whether the kick model is convincing enough that the user trusts the `fundamentalHz` measurement.
4. If audition proves valuable, promote to a proper stage with its own attempts table and auto-enqueue. If not, remove cleanly — nothing else in the codebase depends on it.

## Non-Goals (To Avoid Drift)

- **Do not** let sample synthesis values feed back into Phase 1 or Phase 2. Samples are downstream consumers, not upstream estimators. Invariant #1 is bidirectional: Phase 1 isn't only ground truth for Phase 2; it's ground truth for *everything*.
- **Do not** advertise samples as "what the track sounds like in Ableton." They're a verification aid for the measurement layer.
- **Do not** add filler samples just to populate the panel. If the underlying measurement is low-confidence or missing, the sample is omitted, not faked.

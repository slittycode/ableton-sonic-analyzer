# ASA Architecture Strategy

**Last updated:** March 2026  
**Status:** Living document — update when experiments produce results or the AI capability landscape shifts materially.  
**Sources:** ChatGPT o3 deep research (March 2026), Codex architecture hardening audit, Perplexity ecosystem research (Demucs/separation alternatives), session analysis with Claude Sonnet, `deep-research-report.md`, `deep-research-report (1).md`, `deep-research-report (2).md`, and `docs/STAGE3_REALITY_AUDIT.md`.

This document is not a specification. It is a record of *why* the architecture is shaped the way it is, so that future development decisions — by agents or humans — can be made with the reasoning visible rather than just the conclusions.

---

## The core thesis

ASA's hybrid architecture (deterministic local DSP → AI interpretation) is not a transitional design waiting to be replaced by end-to-end AI. As of early 2026, multiple music-focused AI benchmarks confirm that frontier audio-language models including Gemini degrade on measurement tasks: BPM estimation drifts toward genre-assumed values, keys are sometimes omitted, and meter accuracy falls on complex material. The internal audio downsampling Gemini applies (merged to mono) is a structural ceiling on sub-bass nuance regardless of prompt quality.

This means the split is correct and should be maintained: **measure locally, translate pitch/notes where honest, interpret with AI grounded in measurements**.

---

## The three-layer model

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1 — MEASUREMENT (Essentia)                           │
│  Deterministic and repeatable. Authoritative for system     │
│  measurements. Safer foundation than AI for numeric tasks.  │
│  BPM, LUFS, key, spectral balance, sidechain, groove,       │
│  segment boundaries, stereo, dynamics                       │
│  Output: structured JSON — the system's measurement record  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2 — PITCH/NOTE TRANSLATION (torchcrepe)                 │
│  Best-effort. Honest about uncertainty.                     │
│  Monophonic pitch contour → note segmentation               │
│  Runs on Demucs-separated stems only (bass + other)         │
│  Output: MIDI notes + periodicity confidence per note       │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3 — INTERPRETATION (Gemini)                          │
│  Contextual. Editorial. Musically literate.                 │
│  Grounded by Layer 1 JSON — told not to re-estimate         │
│  measurements it already has                                │
│  Output: arrangement advice, device mappings,               │
│          musical descriptions, stem summaries               │
└─────────────────────────────────────────────────────────────┘
```

---

## Dependency health and decisions

| Dependency | Status | Decision |
|---|---|---|
| Essentia 2.1b6.dev1389 | ✅ Healthy — MTG-maintained, July 2025 wheels, Python 3.9–3.13 | Stay. Irreplaceable for measurement. |
| Demucs 4.0.1 | 🟡 Frozen — Meta archived Jan 1 2025, adefossez fork is bug-fix only | Stay. Models are excellent and stable. No better alternative at comparable quality. Monitor adefossez fork for compatibility drift. |
| torchcrepe 0.0.24 | ✅ Active — default transcription backend, installed and tested | Stay as the `auto` default. Current local benchmark evidence still favors it. |
| PENN 1.0.0 | ❌ Evaluated and rejected for now | March 2026 stem-aware benchmarks showed no useful quality win over torchcrepe, while adding latency, setup weight, and first-run model-download cost. Do not ship it in ASA unless a future corpus proves a clear advantage. |
| librosa 0.11.0 | ✅ Active — spectrogram + time-series visualization via spectral_viz.py | Stay. Visualization layer only; not authoritative for measurements. |
| matplotlib 3.10.8 | ✅ Active — rendering backend for librosa spectrogram PNGs | Stay. Used via Agg backend (thread-safe, non-interactive). |
| PyTorch 2.10, FastAPI, Pydantic | ✅ Healthy | Stay. |

---

## The Session Musician feature — honest assessment

The Session Musician piano roll was built assuming polyphonic transcription of electronic music was achievable at producer-grade quality. It is not, as of early 2026. The 2025 AMT Challenge explicitly noted "remaining difficulties in handling polyphony and timbre variation" and its benchmarks used synthesised classical recordings — not electronic music. This is a field-level gap, not an engineering gap fixable by swapping libraries.

**What is achievable:**
- Monophonic pitch tracking on Demucs-separated stems (bass stem, melody/other stem) with careful post-processing. Viterbi decoding (torchcrepe) materially reduces octave-jump instability by penalising implausible pitch jumps between frames — it does not universally eliminate them, particularly on complex electronic timbres. CREPE Notes-style segmentation (median-based, amplitude-trimmed, short-note-pruned) converts pitch contours to usable note events.
- Gemini musical description of isolated stems: bar-level note hypotheses, rhythmic pattern descriptions, scale degree summaries. Not MIDI — but potentially more useful to a producer trying to understand what a track is doing.

**What is not achievable right now:**
- Polyphonic synth transcription. Not a 12-18 month horizon problem. Don't build infrastructure for it.
- Productized full-track polyphonic audio-to-MIDI for dense mixed producer songs. If this is explored at all, keep it inside the offline research harness documented in `docs/POLYPHONIC_TRANSCRIPTION_SPIKE.md`, not inside the live backend or UI.

**The two-path design:**

```
SESSION MUSICIAN

[CREPE NOTES — bass/other stem]    [GEMINI SUMMARY — bass/other stem]
Viterbi-decoded pitch contour      Bar-level musical description
→ downloadable .mid                → readable, musical language
Confidence: per-note               Uncertainty: flagged in output
"Import and clean up"              "Understand what's happening"
```

Both outputs are honest about what they are. Neither pretends to be Ableton's audio-to-MIDI. The producer chooses which is useful for their workflow. Over time, if one is consistently better, it gets more UI real estate.

---

## Gemini integration — what the research changed

**Phase 2 grounding rule:** Inject Layer 1 deterministic measurements (tempo, time signature, key, section boundaries) into every Gemini call. Instruct Gemini explicitly not to re-estimate those values. Benchmarks show numeric drift and omission occur when models aren't anchored — grounding Gemini with the measurements substantially reduces that failure mode but does not guarantee it.

**Inline size limit — confirmed January 12 2026.** Google officially increased the Gemini API inline limit from 20MB to 100MB, and `server.py` already uses `INLINE_SIZE_LIMIT = 104_857_600`. ASA now sends raw audio files at or below 100 MiB inline and uses the Gemini Files API above that threshold. Note: the Firebase AI Logic SDK still enforces 20MB at its own layer, but the direct google-genai SDK used in `server.py` gets the full 100MB. Base64 encoding still adds ~33% within the inline path, but the current code contract is the raw-file threshold implemented in `server.py`.

**Structured Outputs for stem listening:** Use a minimal JSON schema (bar grid, inferred scale degrees, rhythmic pattern class, uncertainty flags). Structured Outputs constrain the response to what's parseable. This is the right interface for the Gemini stem-listening experiment.

**Audio token budget:** ~32 tokens/second. 30-120s stems are modest. Sub-bass nuance degrades due to internal mono downsampling — factor this into quality expectations for bass stem analysis.

---

## Librosa visualization layer

Librosa generates spectrogram images and per-frame spectral time-series data for frontend visualization. It does not replace Essentia for measurement — Essentia remains the sole authoritative source for scalar spectral metrics.

**Boundary:** `spectralDetail` (Essentia, authoritative scalars) vs spectrogram/time-series artifacts (librosa, for display). If a librosa time-series disagrees with an Essentia mean, the Essentia value is the measurement.

**What librosa produces:**
- Mel spectrogram PNG (128 mels, magma colormap)
- Chroma-over-time PNG (12 pitch classes, CQT-based)
- Spectral evolution JSON (centroid, rolloff, bandwidth, flatness per frame, downsampled to ~500 points)

**Where it runs:** `spectral_viz.py` is called after successful measurement in the same background thread. Artifacts are stored via `AnalysisRuntime.record_artifact()` and served through the artifact download API. Failures are logged but do not fail the measurement run.

**Why not Essentia for spectrograms?** Essentia computes frame-by-frame spectral data (bark bands, MFCC, HPCP) but does not provide the perceptually-weighted spectrogram representations (mel, CQT) that producers expect as a "look at your audio" visualization. Librosa fills exactly that gap.

---

## Architecture hardening — relationship to this strategy

The Codex architecture hardening plan (SQLite + job queue + async Phase 2) is the correct next major infrastructure work. It addresses:
- The in-memory temp-file cache fragility (server restart loses Phase 1 → Phase 2 handoff)
- Client-supplied `phase1_json` trust gap (client can tamper with measurements Gemini interprets)
- Blocking request model unsuitability for Demucs + transcription runtimes

**Ordering constraint (resolved):** Basic Pitch was removed and Layer 2 currently standardizes on `torchcrepe-viterbi`. PENN was benchmarked and then removed after failing to justify its operational cost. The hardening infrastructure does not carry any legacy pitch/note translation dependencies.

**Ordering constraint (resolved):** Experiment B (Gemini stem listening) is now implemented. Stem files persist as run artifacts during pitch/note work. The `stem_summary` interpretation profile sends separated bass and other stems to Gemini with Structured Outputs, producing bar-aligned musical descriptions. The frontend auto-queues `stem_summary` after pitch/note completes and renders per-stem summaries alongside Session Musician draft notes.

---

## The 6-month arc

| Timeframe | Work | Why |
|---|---|---|
| Done | basic-pitch removed, transcription protocol hardened, PENN benchmarked and rejected | Clean foundation before quality comparison |
| Done | Architecture hardening (SQLite + jobs + async Phase 2) | Restart-safe and trust-correct |
| Done | Experiment B — Gemini stem listening with Structured Outputs | Stem artifacts persist, `stem_summary` profile runs against separated stems |
| Done | Backport genreProfiles, abletonDevices, 8 detection services from sonic-architect-app | Grounds Phase 2 Gemini in spectral targets |
| Now | Experiment A — gather a broader real producer corpus for torchcrepe validation | Quality work on real target material |
| Now | Legacy endpoint removal (`/api/analyze`, `/api/phase2`) | Reduce maintenance surface |
| Next | Polyphonic full-track research spike stays offline-only | Compare `basic-pitch` and optional `MT3` through `apps/backend/scripts/evaluate_polyphonic.py`; do not expose a product backend unless the corpus clears the manual usefulness gates |
| +3 months | Ship Session Musician v2 — whichever path(s) produced usable output, honestly labelled | Product decision based on experiment results |
| +6 months | Re-evaluate polyphonic transcription landscape | The field is moving, but new candidates should first go through the offline research harness instead of going straight into the product path. |

---

## What this document is not

- It is not a specification. Implementation details live in AGENTS.md, JSON_SCHEMA.md, and ARCHITECTURE.md.
- It is not gospel. If experiments produce results that contradict it, update it.
- It is not a commitment to any particular library or model. The TranscriptionBackend Protocol exists specifically so that Layer 2 is swappable without rewriting callers.

When updating this document, record the date, what changed, and why. The reasoning trail is the value.

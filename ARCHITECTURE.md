# Architecture (`analyze.py`)

## Purpose

`analyze.py` is a local DSP analysis pipeline designed to extract production-relevant metrics from a mixed audio file for Ableton Live 12 reconstruction workflows.

The script is deliberately monolithic (single entrypoint) but internally segmented by self-contained analysis functions. Each function follows an error-safe pattern and returns a dictionary fragment merged into the final JSON.

---

## High-Level Flow

1. Parse CLI flags (`audio_path`, `--separate`, `--fast`).
2. Load mono and stereo audio buffers.
3. Optionally run Demucs source separation (`--separate`).
4. Run `extract_rhythm()` once (shared resource).
5. Execute all analysis functions, each returning a partial dictionary.
6. Assemble final output object in fixed key order.
7. Print JSON to `stdout`; status/warnings to `stderr`.
8. Clean up temporary stem files if separation was used.

---

## Main Analysis Functions

## Tempo, Key, Timing
- `extract_rhythm(mono)`
  - Shared `RhythmExtractor2013` call.
  - Provides `bpm`, beat ticks, confidence and auxiliary tempo data.
- `analyze_bpm(rhythm_data, mono, sample_rate)`
  - Uses shared rhythm BPM.
  - Adds secondary `PercivalBpmEstimator` cross-check.
- `analyze_key(mono)`
  - Global key via `KeyExtractor(profileType="temperley")`.
- `analyze_time_signature(rhythm_data)`
  - Currently returns `"4/4"` when rhythm exists.
- `analyze_duration_and_sr(mono, sample_rate)`
  - Derives duration and sample rate metadata.

## Loudness and Dynamics
- `analyze_loudness(stereo)`
  - `LoudnessEBUR128` integrated loudness and loudness range.
- `analyze_true_peak(stereo)`
  - True peak across channels.
- `analyze_dynamics(mono, sample_rate)`
  - Crest factor and broad-band dynamic spread.
- `analyze_dynamic_character(mono, sample_rate)`
  - `DynamicComplexity`, frame flatness, and attack-time descriptors.

## Spectral and Timbre
- `analyze_spectral_balance(mono, sample_rate)`
  - 6-band long-term spectral dB profile.
- `analyze_spectral_detail(mono, sample_rate)`
  - Global centroid/rolloff, MFCC, chroma, Bark, ERB, spectral contrast/valley.
- `analyze_perceptual(mono, sample_rate)`
  - Sharpness proxy and roughness proxy.
- `analyze_essentia_features(mono)`
  - Zero-crossing rate, HFC, spectral complexity, dissonance.
- `analyze_synthesis_character(mono, sample_rate)`
  - Inharmonicity and odd/even harmonic ratio.

## Stereo
- `analyze_stereo(stereo, sample_rate)`
  - Global `stereoDetail`:
    - `stereoWidth`
    - `stereoCorrelation`
    - `subBassCorrelation`
    - `subBassMono`
  - Sub-bass isolation uses `BandPass` when available; falls back to `LowPass(80 Hz)`.

## Rhythm and Groove
- `analyze_rhythm_detail(rhythm_data)`
  - Beat-position and groove descriptors from shared rhythm data.
- `analyze_groove(mono, sample_rate, rhythm_data, beat_data)`
  - Beat-synchronous low/high accent and swing metrics.
- `analyze_sidechain_detail(mono, sample_rate, rhythm_data, beat_data)`
  - Pumping strength/regularity/rate and confidence score.

## Melody and Harmony
- `analyze_melody(audio_path, sample_rate, rhythm_data, stems)`
  - `EqloudLoader` + `PredominantPitchMelodia` + `PitchContourSegmentation`.
  - Optional source-separated melody extraction.
  - Optional MIDI export via `mido`.
- `analyze_chords(mono, sample_rate)`
  - High-pass filtered chord extraction over HPCP and `ChordsDetection`.

## Structure and Segment-Level Analyses
- `analyze_structure(mono, sample_rate)`
  - SBic segmentation (with fallback path).
- `analyze_segment_loudness(structure_data, stereo, sample_rate)`
  - Per-segment LUFS/LRA.
- `analyze_segment_stereo(structure_data, stereo, sample_rate)`
  - Per-segment stereo width/correlation.
- `analyze_segment_spectral(structure_data, mono, segment_stereo_data, sample_rate)`
  - Per-segment Bark bands, centroid/rolloff, stereo metrics.
- `analyze_segment_key(structure_data, mono, sample_rate)`
  - Per-segment key and confidence.

## Danceability
- `analyze_danceability(mono, sample_rate)`
  - Danceability score and DFA.

---

## Shared Helpers and Why They Exist

- `_slice_segments(structure_data, total_samples, sample_rate)`
  - Single canonical segment slicing implementation.
  - Prevents drift and mismatch between segment analyzers.
  - Mandatory common source for segment boundaries in:
    - `analyze_segment_spectral`
    - `analyze_segment_key`
    - `analyze_segment_stereo`
    - (also reused by `analyze_segment_loudness`)

- `_compute_stereo_metrics(left, right)`
  - Centralises stereo width/correlation maths.
  - Ensures global and per-segment stereo values use identical formulae.

- `_extract_beat_loudness_data(mono, sample_rate, rhythm_data)`
  - Shared beat-band loudness extraction for:
    - `analyze_groove`
    - `analyze_sidechain_detail`
  - Avoids duplicate BeatLoudness logic and keeps beat-domain alignment consistent.

Additional utility helpers:
- `_safe_db(...)` and `_compute_bark_db(...)` standardise robust dB conversion/Bark averaging.

---

## CLI Flags

- `--separate`
  - Enables Demucs source separation before melody extraction.
  - Uses `other` stem for melody when available.
  - Adds noticeable runtime on CPU (commonly 30-60 seconds).

- `--fast`
  - Parser stub only.
  - No current behaviour change (intent is future hop-size optimisation path).

---

## Error-Safe Pattern Convention

Every analysis function follows this pattern:

1. Wrap algorithm logic in `try/except`.
2. On recoverable internal errors, continue with fallback/default values.
3. On function-level failure, return container key with `None`:
   - e.g. `{"sidechainDetail": None}`
4. Never raise unhandled exceptions that crash the whole script.
5. Emit warning messages to `stderr`, never `stdout`.

This allows partial JSON output even when some algorithms are unavailable in a given Essentia build or fail on edge-case audio.

---

## Known Limitations

1. Pitch detection confidence is low on heavily processed electronic masters.
- Typical `pitchConfidence` observed range: `0.04-0.09`.

2. Chord detection is approximate on full-mix masters.
- Typical `chordStrength` observed range: `0.65-0.70`.

3. Sidechain detection is less reliable when kick and sub occupy similar frequency content.
- `pumpingConfidence` should be used as the reliability gate.

4. Source separation (`--separate`) usually improves melody extraction but adds CPU processing time.
- Common overhead: ~30-60 seconds.

5. Key detection uses the Temperley profile.
- It may return a relative major/minor rather than the musical key a producer would label by ear.

---

## Practical Integration Notes

- JSON is emitted to `stdout` for pipeline compatibility.
- Runtime logs and warnings go to `stderr`.
- For reproducible automation, capture output with shell redirection and store raw JSON per source file.


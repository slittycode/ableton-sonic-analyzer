# Changelog

All notable changes to `sonic-analyzer` are documented here in reverse chronological order.

## v0.5 (current)

- Per-segment key detection
- Per-segment stereo width
- Sub-bass mono check
- Sidechain pumping detection with `pumpingConfidence`
- `stereoDetail` schema (breaking change from top-level stereo fields)
- Shared helpers:
  - `_slice_segments`
  - `_compute_stereo_metrics`
  - `_extract_beat_loudness_data`

## v0.4

- `DynamicComplexity`, `Flatness`, `LogAttackTime`
- `BarkBands` (24), `ERBBands` (40), `SpectralContrast`
- Per-segment loudness (`segmentLoudness`)
- Per-segment spectral Bark bands (`segmentSpectral`)
- `--fast` CLI stub

## v0.3

- Source separation via Demucs (`--separate` flag)
- `PitchContourSegmentation` replacing PredominantPitchMelodia-only melody output
- MIDI file export
- Chord detection with HPF pre-processing
- BPM cross-check via `PercivalBpmEstimator`
- Danceability and DFA

## v0.2

- `BeatLoudness` groove analysis (`kickSwing`, `hihatSwing`)
- Synthesis character (`inharmonicity`, `oddToEvenRatio`)
- Structure segmentation (`SBic`)
- Onset rate and beat positions

## v0.1

- Initial DSP engine
- BPM (`RhythmExtractor2013`), Key (`KeyExtractor/Temperley`), LUFS (`LoudnessEBUR128`)
- True peak, stereo width/correlation
- Spectral balance (6 bands)
- MFCC, chroma, spectral centroid/rolloff


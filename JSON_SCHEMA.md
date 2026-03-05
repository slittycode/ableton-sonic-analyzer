# JSON Output Schema (`analyze.py`)

This document defines every field currently emitted by `analyze.py`.

Conventions:
- All feature functions are error-safe. On failure they return `null` (JSON `null`) for their container or field set.
- Numeric values are rounded in code; do not assume infinite precision.
- Arrays may be truncated to keep payload size manageable.

---

## Root Object

Top-level keys:

`bpm`, `bpmConfidence`, `bpmPercival`, `bpmAgreement`, `key`, `keyConfidence`, `timeSignature`, `durationSeconds`, `sampleRate`, `lufsIntegrated`, `lufsRange`, `truePeak`, `crestFactor`, `dynamicSpread`, `dynamicCharacter`, `stereoDetail`, `spectralBalance`, `spectralDetail`, `rhythmDetail`, `melodyDetail`, `grooveDetail`, `sidechainDetail`, `effectsDetail`, `synthesisCharacter`, `danceability`, `structure`, `arrangementDetail`, `segmentLoudness`, `segmentSpectral`, `segmentStereo`, `segmentKey`, `chordDetail`, `perceptual`, `essentiaFeatures`.

---

## Core Metrics

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `bpm` | `float \| null` | Primary tempo estimate from `RhythmExtractor2013`. | beats per minute | Main tempo anchor for Ableton project tempo and clip warp assumptions. |
| `bpmConfidence` | `float \| null` | Confidence output from `RhythmExtractor2013` for primary BPM. | unbounded float (RhythmExtractor2013-specific; observed values typically 1.0-4.0 on real material) | Not normalised to 0-1. Higher values indicate stronger rhythmic periodicity. Values above 2.0 generally indicate reliable tempo detection. Low values (below 1.0) suggest ambiguous pulse or half/double-time content. |
| `key` | `string \| null` | Global key label from `KeyExtractor` (`Temperley` profile), e.g. `"A Minor"`. | categorical | Starting point for harmonic reconstruction; validate by ear against bass/chord roots. |
| `keyConfidence` | `float \| null` | Confidence/strength of global key estimate. | 0-1 (approx) | Low values indicate ambiguous tonality or modal/atonal content. |
| `timeSignature` | `string \| null` | Time signature estimate (currently defaults to `"4/4"` when rhythm exists). | string | Treat as prior; verify manually on odd-metre material. |
| `durationSeconds` | `float \| null` | Track duration from sample count. | seconds | Useful for arrangement section planning and timeline mapping. |
| `sampleRate` | `int \| null` | Effective analysis sample rate. | Hz | Ensures downstream feature interpretation uses correct temporal/frequency scaling. |

---

## BPM Cross-Check

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `bpmPercival` | `float \| null` | Secondary BPM estimate via `PercivalBpmEstimator`. | beats per minute | Cross-check for tempo stability; disagreement suggests ambiguous pulse or half/double-time confusion. |
| `bpmAgreement` | `bool \| null` | `true` when `abs(bpm - bpmPercival) < 2.0`. | boolean | Fast confidence signal for tempo reliability before committing global project BPM. |

---

## Loudness & Dynamics

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `lufsIntegrated` | `float \| null` | Integrated loudness via `LoudnessEBUR128`. | LUFS | Global loudness target reference for gain staging and master chain matching. |
| `lufsRange` | `float \| null` | Loudness range via `LoudnessEBUR128`. | LU | Indicates macro-dynamic movement across sections. |
| `truePeak` | `float \| null` | Max true peak across stereo channels. | linear amplitude proxy (rounded) | Helps detect clipping risk and required headroom when rebuilding. |
| `crestFactor` | `float \| null` | Peak-to-RMS ratio over mono signal. | dB | Higher crest means stronger transients/less compression; lower crest suggests denser limiting/compression. |
| `dynamicSpread` | `float \| null` | Ratio of broad-band energy means (sub/mid/high approximation). | unitless ratio | Quick indicator of how unevenly energy is distributed across broad frequency regions. |

### `dynamicCharacter`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `dynamicCharacter.dynamicComplexity` | `float` | From `DynamicComplexity`; measures short-term loudness variation complexity. | unitless | Higher values often indicate denser envelope modulation, pumping, or articulated transients. |
| `dynamicCharacter.loudnessVariation` | `float` | Secondary output from `DynamicComplexity`. | dB-like scale | Tracks overall variation depth; can be lower on heavily flattened masters. |
| `dynamicCharacter.spectralFlatness` | `float` | Mean frame spectral flatness. | 0-1 (tonal->noisy) | Near 0 = tonal/sinusoidal; higher values suggest noise/saturation texture. |
| `dynamicCharacter.logAttackTime` | `float` | Mean log attack time (fallback-first strategy). | log10(seconds) style | More negative implies faster attacks/transients; less negative implies slower envelope rise. |
| `dynamicCharacter.attackTimeStdDev` | `float` | Std dev of linearised attack times. | seconds (derived) | Higher spread suggests mixed transient behaviours across events. |

---

## Stereo

### `stereoDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `stereoDetail.stereoWidth` | `float \| null` | Side/mid energy ratio proxy. | unitless ratio | Higher values imply wider image; near 0 implies mostly mono. |
| `stereoDetail.stereoCorrelation` | `float \| null` | Pearson correlation of full-band L/R channels. | -1.0 to 1.0 | Near 1 = mono-compatible; near 0 = wide/decorrelated; negative may collapse poorly to mono. |
| `stereoDetail.subBassCorrelation` | `float \| null` | L/R correlation after sub-band isolation (20-80 Hz target; low-pass fallback). | -1.0 to 1.0 | Sub mono-compatibility signal; low values suggest risky stereo low-end for club playback. |
| `stereoDetail.subBassMono` | `bool \| null` | `true` when `subBassCorrelation > 0.85`. | boolean | `true` means sub region is effectively mono-compatible; standard for most dance/club mixes. |

Example interpretation:
- `subBassMono: true` -> "Sub bass is mono-compatible. Standard for club music. Advise keeping bass synthesis below ~150 Hz mono in Ableton."

---

## Spectral Balance

### `spectralBalance`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `spectralBalance.subBass` | `float` | Mean energy in 20-60 Hz band. | dB (relative) | Indicates weight of true sub fundamentals. |
| `spectralBalance.lowBass` | `float` | Mean energy in 60-200 Hz band. | dB (relative) | Covers kick thump and bass body. |
| `spectralBalance.mids` | `float` | Mean energy in 200-2000 Hz band. | dB (relative) | Core musical body and intelligibility region. |
| `spectralBalance.upperMids` | `float` | Mean energy in 2-6 kHz band. | dB (relative) | Presence/attack region; affects perceived forwardness. |
| `spectralBalance.highs` | `float` | Mean energy in 6-12 kHz band. | dB (relative) | Brightness and air onset content. |
| `spectralBalance.brilliance` | `float` | Mean energy in 12-20 kHz band. | dB (relative) | Extreme top-end "air"; often reduced on lossy or dark masters. |

### `spectralDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `spectralDetail.spectralCentroid` | `float` | Global mean centroid. | Hz | Higher centroid generally means brighter spectral tilt. |
| `spectralDetail.spectralRolloff` | `float` | Global mean rolloff frequency. | Hz | Indicates where most spectral energy accumulates below. |
| `spectralDetail.mfcc` | `float[13]` | Mean MFCC coefficients. | coefficient vector | Compact timbre fingerprint; compare tracks by vector similarity. |
| `spectralDetail.chroma` | `float[12]` | Mean HPCP/chroma profile. | 12 pitch classes | Pitch-class energy distribution; useful for harmonic centre hints. |
| `spectralDetail.barkBands` | `float[24]` | Mean Bark band energies. | dB per Bark band | Psychoacoustic distribution across critical bands. |
| `spectralDetail.erbBands` | `float[40]` | Mean ERB band energies. | dB per ERB band | Finer perceptual frequency profile for timbre/vocal presence estimation. |
| `spectralDetail.spectralContrast` | `float[]` | Mean spectral contrast per sub-band. | contrast magnitude | Higher values imply stronger peak-vs-valley separation (clear layered content). |
| `spectralDetail.spectralValley` | `float[]` | Mean valley levels per sub-band. | valley magnitude | Context for contrast: high valleys suggest denser, filled spectra. |

---

## Rhythm

### `rhythmDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `rhythmDetail.onsetRate` | `float` | Approximate onset density from beat ticks. | events/sec (approx) | Higher values imply busier transient content or denser rhythmic events. |
| `rhythmDetail.beatPositions` | `float[]` | First up-to-16 beat timestamps. | seconds | Use to align section/clip markers in DAW. |
| `rhythmDetail.grooveAmount` | `float` | Normalised beat interval variability. | unitless | Higher values imply more timing looseness/swing. |

### `grooveDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `grooveDetail.kickSwing` | `float` | Swing proxy from low-band accented beat spacing. | unitless | Captures low-end timing push/pull. |
| `grooveDetail.hihatSwing` | `float` | Swing proxy from high-band accented beat spacing. | unitless | Captures high-frequency rhythmic looseness. |
| `grooveDetail.kickAccent` | `float[]` | Up-to-16 sampled low-band beat loudness values. | linear loudness proxy | Shape of kick emphasis over time. |
| `grooveDetail.hihatAccent` | `float[]` | Up-to-16 sampled high-band beat loudness values. | linear loudness proxy | Shape of high-percussion emphasis over time. |

### `sidechainDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `sidechainDetail.pumpingStrength` | `float` | Depth/alignment score for loudness dips vs kick activity. | 0.0-1.0 | Higher values suggest stronger audible sidechain-style ducking. |
| `sidechainDetail.pumpingRegularity` | `float` | Period consistency of detected pumping intervals. | 0.0-1.0 | High values indicate clock-like pumping, useful for genre-consistent groove reconstruction. |
| `sidechainDetail.pumpingRate` | `"quarter" \| "eighth" \| "sixteenth" \| null` | Best-matching pumping grid rate. | categorical | Suggests compressor trigger rhythm for Ableton sidechain setup. |
| `sidechainDetail.pumpingConfidence` | `float` | Reliability score (kick clarity + dip correlation + timing stability penalties). | 0.0-1.0 | Low confidence means avoid overcommitting to sidechain recreation without ear-checking. |

### `effectsDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `effectsDetail.gatingDetected` | `bool` | True when repeated silence-end events form a regular BPM-aligned gating pattern. | boolean | Quick indicator for vocal-chop/stutter style processing being present. |
| `effectsDetail.gatingRate` | `"16th" \| "8th" \| "quarter" \| null` | Best matching rhythmic grid for detected gating intervals. | categorical | Suggests note-division for Ableton gate/volume automation recreation. |
| `effectsDetail.gatingRegularity` | `float` | Interval stability score from silence-end event spacing. | 0.0-1.0 | Higher values imply machine-like rhythmic gating rather than irregular edits/noise. |
| `effectsDetail.gatingEventCount` | `int` | Number of detected gate onset events in track-level pass. | count | Higher counts indicate more sustained gating activity across arrangement. |

---

## Melody

### `melodyDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `melodyDetail.noteCount` | `int` | Number of segmented melody notes detected. | count | Rough complexity estimate for topline/arpeggio extraction workload. |
| `melodyDetail.notes` | `array<object>` | Up to 64 sampled note events. | list of note objects | Timing-aware melodic sketch for MIDI guide generation. |
| `melodyDetail.notes[].midi` | `int` | MIDI note number. | 0-127 | Directly usable in DAW piano roll. |
| `melodyDetail.notes[].onset` | `float` | Note onset time. | seconds | Place MIDI note start in arrangement timeline. |
| `melodyDetail.notes[].duration` | `float` | Note duration. | seconds | Approximate gate length for note programming. |
| `melodyDetail.dominantNotes` | `int[]` | Top 5 most frequent MIDI notes. | MIDI note numbers | Tonal centre cues for bass/chord writing. |
| `melodyDetail.pitchRange` | `object` | Aggregate min/max MIDI range for detected notes. | object | Fast register summary for instrument and octave planning. |
| `melodyDetail.pitchRange.min` | `int \| null` | Lowest detected MIDI note. | MIDI note number | Lower register bound for synth or instrument selection. |
| `melodyDetail.pitchRange.max` | `int \| null` | Highest detected MIDI note. | MIDI note number | Upper register bound for lead/timbre planning. |
| `melodyDetail.pitchConfidence` | `float` | Mean confidence from pitch extractor. | 0-1 (approx) | Low values on dense masters imply melody extraction should be treated as draft only. |
| `melodyDetail.midiFile` | `string \| null` | Path to exported melody MIDI file. | filesystem path | Ready-to-import melody scaffold for Ableton reconstruction. |
| `melodyDetail.sourceSeparated` | `bool` | Whether melody extraction ran on Demucs `other` stem. | boolean | `true` usually improves contour clarity but costs additional processing time. |
| `melodyDetail.vibratoPresent` | `bool` | True when mean detected vibrato extent exceeds threshold. | boolean | Indicates audible pitch modulation likely intentional (vibrato-style movement). |
| `melodyDetail.vibratoExtent` | `float` | Mean positive vibrato extent from contour analysis. | cents | Higher values suggest deeper pitch wobble; near zero is expected on many electronic leads/vocals. |
| `melodyDetail.vibratoRate` | `float` | Mean detected vibrato modulation rate. | Hz | Useful for mapping to LFO/pitch-mod rates in synth recreation. |
| `melodyDetail.vibratoConfidence` | `float` | Proportion of analysed contour frames with detected vibrato. | 0.0-1.0 | Low values imply sparse/weak modulation; treat as subtle or absent vibrato. |

---

## Harmony

### `chordDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `chordDetail.chordSequence` | `string[]` | Up-to-32 sampled chord labels over time. | chord labels | Coarse harmonic timeline for section-level chord mapping. |
| `chordDetail.chordStrength` | `float` | Mean chord detection strength. | 0-1 (approx) | Low/medium values indicate probable ambiguity on full-master chord detection. |
| `chordDetail.progression` | `string[]` | Consecutive-duplicate-removed progression, capped at 16. | chord labels | Compact harmonic change path for arrangement planning. |
| `chordDetail.dominantChords` | `string[]` | Top 4 most frequent chord labels. | chord labels | Candidate tonic/relative function anchors. |

### `segmentKey`

Type: `array<object> \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `segmentKey[].segmentIndex` | `int` | Segment index aligned with `structure.segments`. | integer index | Use for joining harmonic data to arrangement segments. |
| `segmentKey[].key` | `string \| null` | Per-segment key label (`Temperley`). | categorical | Detects section-level key drift or modal pivots. |
| `segmentKey[].keyConfidence` | `float \| null` | Per-segment key confidence. | 0-1 (approx) | Low confidence means treat segment key as tentative. |

---

## Synthesis Character

### `synthesisCharacter`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `synthesisCharacter.inharmonicity` | `float` | Mean inharmonicity from spectral peaks. | unitless | Higher values can indicate FM/noisy/metallic timbres. |
| `synthesisCharacter.oddToEvenRatio` | `float` | Mean odd/even harmonic energy ratio. | unitless ratio | Helps infer wave-shape bias (e.g., saw/square-like emphasis). |

### `perceptual`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `perceptual.sharpness` | `float` | High-frequency weighted spectral measure. | unitless proxy | Higher values imply brighter/more piercing tonality. |
| `perceptual.roughness` | `float` | Dissonance-based roughness proxy. | unitless | Higher values suggest more beating/inharmonic interaction. |

### `essentiaFeatures`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `essentiaFeatures.zeroCrossingRate` | `float` | Mean frame zero-crossing rate. | crossings/sample (normalised) | Higher values correlate with noisier or brighter material. |
| `essentiaFeatures.hfc` | `float` | Mean high-frequency content metric. | arbitrary feature units | Good transient/brightness activity indicator. |
| `essentiaFeatures.spectralComplexity` | `float` | Mean count/proxy of spectral peaks. | feature units | Higher complexity suggests denser/layered spectral content. |
| `essentiaFeatures.dissonance` | `float` | Mean dissonance from spectral peaks. | feature units | Elevated values imply more interval roughness/tension. |

---

## Structure

### `structure`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `structure.segmentCount` | `int` | Number of detected segments (capped to 20). | count | Section count estimate for arrangement blocks. |
| `structure.segments` | `array<object>` | Segment boundary list. | list | Canonical time partitions used by all segment-level analyses. |
| `structure.segments[].start` | `float` | Segment start time. | seconds | DAW locator start. |
| `structure.segments[].end` | `float` | Segment end time. | seconds | DAW locator end. |
| `structure.segments[].index` | `int` | Segment index. | integer index | Join key across segment outputs. |

### `arrangementDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `arrangementDetail.noveltyCurve` | `float[]` | Downsampled novelty timeline (max 64 points) from Bark-band change detection. | relative novelty units | Highlights where timbral/energy surprises occur (risers, transitions, filter moves). |
| `arrangementDetail.noveltyPeaks` | `array<object>` | Top novelty events with spacing constraint (max 8). | list of events | Candidate transition markers for arrangement mapping beyond SBic segmentation. |
| `arrangementDetail.noveltyPeaks[].time` | `float` | Time of a novelty peak. | seconds | Place transition/automation markers in arrangement timeline. |
| `arrangementDetail.noveltyPeaks[].strength` | `float` | Relative strength at novelty peak. | novelty magnitude | Higher values indicate more pronounced spectral/energy change. |
| `arrangementDetail.noveltyMean` | `float` | Mean novelty over full track. | novelty magnitude | Baseline level of frame-to-frame change across arrangement. |
| `arrangementDetail.noveltyStdDev` | `float` | Standard deviation of novelty. | novelty magnitude | Higher spread indicates stronger contrast between stable and transition-heavy sections. |

### `segmentLoudness`

Type: `array<object> \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `segmentLoudness[].segmentIndex` | `int` | Segment index. | integer index | Aligns loudness evolution with structure sections. |
| `segmentLoudness[].start` | `float` | Segment start time. | seconds | Section timing context. |
| `segmentLoudness[].end` | `float` | Segment end time. | seconds | Section timing context. |
| `segmentLoudness[].lufs` | `float \| null` | Segment integrated loudness. | LUFS | Shows which sections are intentionally quieter/louder. |
| `segmentLoudness[].lra` | `float \| null` | Segment loudness range. | LU | Identifies dynamic movement inside each section. |

### `segmentSpectral`

Type: `array<object> \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `segmentSpectral[].segmentIndex` | `int` | Segment index. | integer index | Join key to structure. |
| `segmentSpectral[].barkBands` | `float[24]` | Segment mean Bark band energies. | dB per band | Frequency-content fingerprint per arrangement section. |
| `segmentSpectral[].spectralCentroid` | `float \| null` | Segment mean centroid. | Hz | Tracks brightness movement between sections (e.g., build-ups). |
| `segmentSpectral[].spectralRolloff` | `float \| null` | Segment mean rolloff. | Hz | Tracks top-end extension changes by section. |
| `segmentSpectral[].stereoWidth` | `float \| null` | Segment width proxy. | unitless ratio | Reveals widening/narrowing automation across arrangement. |
| `segmentSpectral[].stereoCorrelation` | `float \| null` | Segment L/R correlation. | -1.0 to 1.0 | Flags section-specific mono-compatibility issues. |

### `segmentStereo`

Type: `array<object> \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `segmentStereo[].segmentIndex` | `int` | Segment index aligned with `structure.segments`. | integer index | Join point for section-wise stereo diagnostics across other segment outputs. |
| `segmentStereo[].stereoWidth` | `float \| null` | Per-segment side/mid energy ratio proxy. | unitless ratio | Detects width automation by section; high changes often indicate transitions or drops. |
| `segmentStereo[].stereoCorrelation` | `float \| null` | Per-segment L/R Pearson correlation. | -1.0 to 1.0 | Flags mono-compatibility risk per arrangement block instead of only full-track average. |

---

## Danceability

### `danceability`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `danceability.danceability` | `float` | Danceability score from Essentia. | algorithmic score | Relative groove suitability indicator; compare between tracks more than absolute targets. |
| `danceability.dfa` | `float` | DFA exponent returned by danceability algo. | exponent | Rhythmic complexity/structure indicator; useful for groove simplification decisions. |

---

## Additional Notes for LLM Consumers

1. Treat low-confidence outputs as hints, not truth:
- low `melodyDetail.pitchConfidence`
- low `chordDetail.chordStrength`
- low `sidechainDetail.pumpingConfidence`

2. Use cross-field consistency checks:
- tempo: `bpm` vs `bpmPercival` and `bpmAgreement`
- harmony: `key` vs `segmentKey` vs `chordDetail.dominantChords`
- arrangement: `structure` + `segmentLoudness` + `segmentSpectral`

3. Rebuilding in Ableton Live 12 should generally start with:
- project tempo (`bpm`)
- global key (`key`) with manual confirmation
- arrangement locators (`structure.segments`)
- low-end/stereo safety (`stereoDetail`, especially sub-bass fields)

# JSON Output Schema (`analyze.py`)

This document defines every field currently emitted by `analyze.py`.

`server.py` does not return this raw object directly. The HTTP API wraps a normalized subset of it inside `phase1`. The raw CLI schema and the HTTP wrapper are intentionally different, so this document calls out both where that mapping matters.

Conventions:
- All feature functions are error-safe. On failure they return `null` (JSON `null`) for their container or field set.
- Numeric values are rounded in code; do not assume infinite precision.
- Arrays may be truncated to keep payload size manageable.

---

## Root Object

Top-level keys:

`bpm`, `bpmConfidence`, `bpmPercival`, `bpmAgreement`, `bpmDoubletime`, `bpmSource`, `bpmRawOriginal`, `key`, `keyConfidence`, `keyProfile`, `tuningFrequency`, `tuningCents`, `timeSignature`, `durationSeconds`, `sampleRate`, `lufsIntegrated`, `lufsRange`, `lufsMomentaryMax`, `lufsShortTermMax`, `truePeak`, `crestFactor`, `dynamicSpread`, `dynamicCharacter`, `stereoDetail`, `spectralBalance`, `spectralDetail`, `rhythmDetail`, `melodyDetail`, `transcriptionDetail`, `pitchDetail`, `grooveDetail`, `beatsLoudness`, `sidechainDetail`, `effectsDetail`, `synthesisCharacter`, `danceability`, `structure`, `arrangementDetail`, `segmentLoudness`, `segmentSpectral`, `segmentStereo`, `segmentKey`, `chordDetail`, `perceptual`, `essentiaFeatures`.

## Relationship To `POST /api/analyze`

The HTTP success envelope is:

```json
{
  "requestId": "uuid",
  "phase1": {
    "bpm": 128.0,
    "bpmConfidence": 0.92
  },
  "diagnostics": {
    "requestId": "uuid",
    "backendDurationMs": 31842.14,
    "engineVersion": "analyze.py",
    "timings": {
      "totalMs": 32010.41,
      "analysisMs": 31842.14,
      "serverOverheadMs": 168.27,
      "flagsUsed": ["--separate", "--transcribe"],
      "fileSizeBytes": 12039487,
      "fileDurationSeconds": 214.6,
      "msPerSecondOfAudio": 148.38
    }
  }
}
```

The wrapped HTTP diagnostics also include:

- `estimatedLowMs`
- `estimatedHighMs`
- `timeoutSeconds`

Compatibility note:

- `backendDurationMs` remains the subprocess wall time for backward compatibility and matches `diagnostics.timings.analysisMs`.
- `diagnostics.timings.fileDurationSeconds` and `diagnostics.timings.msPerSecondOfAudio` are `null` on timeout or malformed/invalid analyzer output.

`phase1` includes normalized scalar fields:

- `bpm`
- `bpmConfidence`
- `key`
- `keyConfidence`
- `timeSignature`
- `durationSeconds`
- `lufsIntegrated`
- `lufsRange`
- `truePeak`
- `crestFactor`
- `stereoWidth`
- `stereoCorrelation`
- `spectralBalance`

`phase1` also forwards these raw analyzer sections unchanged:

- `stereoDetail`
- `spectralDetail`
- `rhythmDetail`
- `melodyDetail`
- `transcriptionDetail`
- `pitchDetail`
- `grooveDetail`
- `beatsLoudness`
- `sidechainDetail`
- `effectsDetail`
- `synthesisCharacter`
- `danceability`
- `structure`
- `arrangementDetail`
- `segmentLoudness`
- `segmentSpectral`
- `segmentStereo`
- `segmentKey`
- `chordDetail`
- `perceptual`
- `essentiaFeatures`
- `dynamicCharacter`
- `acidDetail`
- `reverbDetail`
- `vocalDetail`
- `supersawDetail`
- `bassDetail`
- `kickDetail`
- `genreDetail`

`phase1` also includes these scalar fields forwarded from the raw analyzer:

- `bpmPercival`
- `bpmAgreement`
- `keyProfile`
- `tuningFrequency`
- `tuningCents`
- `sampleRate`
- `lufsMomentaryMax`
- `lufsShortTermMax`
- `dynamicSpread`
- `bpmDoubletime`
- `bpmSource`
- `bpmRawOriginal`

All raw `analyze.py` fields are now forwarded through the server `phase1` wrapper, including fields previously excluded: `bpmPercival`, `bpmAgreement`, `sampleRate`, `dynamicSpread`, `dynamicCharacter`, `segmentStereo`, `essentiaFeatures`.

Two server-only convenience fields are derived from `stereoDetail`:

- `phase1.stereoWidth`
- `phase1.stereoCorrelation`

Current server behavior that affects schema expectations:

- `transcriptionDetail` is only populated when `analyze.py` runs with `--transcribe`
- `pitchDetail` is only populated when `--separate` is used; requires torchcrepe and separated stems
- `danceability` is forwarded as the raw object shown below, not as a scalar
- `dsp_json_override` is accepted by the server but does not alter the analyzer payload

---

## Core Metrics

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `bpm` | `float \| null` | Primary tempo estimate from `RhythmExtractor2013`. | beats per minute | Main tempo anchor for Ableton project tempo and clip warp assumptions. |
| `bpmConfidence` | `float \| null` | Confidence output from `RhythmExtractor2013` for primary BPM. | unbounded float (RhythmExtractor2013-specific; observed values typically 1.0-4.0 on real material) | Not normalised to 0-1. Higher values indicate stronger rhythmic periodicity. Values above 2.0 generally indicate reliable tempo detection. Low values (below 1.0) suggest ambiguous pulse or half/double-time content. |
| `key` | `string \| null` | Global key label from `KeyExtractor` (`edma` profile), e.g. `"A Minor"`. | categorical | Starting point for harmonic reconstruction; validate by ear against bass/chord roots. |
| `keyConfidence` | `float \| null` | Confidence/strength of global key estimate. | 0-1 (approx) | Low values indicate ambiguous tonality or modal/atonal content. |
| `timeSignature` | `string \| null` | Time signature estimate (currently defaults to `"4/4"` when rhythm exists). | string | Treat as prior; verify manually on odd-metre material. |
| `durationSeconds` | `float \| null` | Track duration from sample count. | seconds | Useful for arrangement section planning and timeline mapping. |
| `sampleRate` | `int \| null` | Effective analysis sample rate. | Hz | Ensures downstream feature interpretation uses correct temporal/frequency scaling. |
| `keyProfile` | `string \| null` | Key profile used by `KeyExtractor` (e.g. `"edma"`). | categorical | Indicates which pitch template corpus was used for key detection. |
| `tuningFrequency` | `float \| null` | Estimated tuning reference frequency from spectral peak analysis. | Hz | Deviation from 440 Hz helps detect detuned material or concert-pitch variants. |
| `tuningCents` | `float \| null` | Tuning offset from A440 in cents. | cents | Positive = sharp of A440, negative = flat. Useful for pitch-correcting reconstructions. |

---

## BPM Cross-Check

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `bpmPercival` | `float \| null` | Secondary BPM estimate via `PercivalBpmEstimator`. | beats per minute | Cross-check for tempo stability; disagreement suggests ambiguous pulse or half/double-time confusion. |
| `bpmAgreement` | `bool \| null` | `true` when `abs(bpm - bpmPercival) < 2.0`. | boolean | Fast confidence signal for tempo reliability before committing global project BPM. |
| `bpmDoubletime` | `bool` | `true` when the BPM value was corrected from a half-time or fractional-time reading via ratio matching against the Percival estimator. | boolean | When `true`, the kick pattern sits at the half-tempo pulse even though harmonic/hi-hat content moves at the corrected BPM. |
| `bpmSource` | `string \| null` | One of: `"percival_ratio_corrected"` (ratio match fired, Percival wins), `"rhythm_extractor_confirmed"` (both estimators agree within 2 BPM), `"rhythm_extractor"` (default, no correction applied). | categorical | Indicates confidence level of the BPM measurement. `percival_ratio_corrected` means a harmonic relationship was detected and corrected. |
| `bpmRawOriginal` | `float \| null` | The raw RhythmExtractor2013 tempo before any correction. Always populated when RhythmExtractor succeeds, even without correction (in which case `bpm == bpmRawOriginal`). | beats per minute | Compare with `bpm` to see if correction was applied. Useful for verifying the correction logic against audio perception. |

---

## Loudness & Dynamics

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `lufsIntegrated` | `float \| null` | Integrated loudness via `LoudnessEBUR128`. | LUFS | Global loudness target reference for gain staging and master chain matching. |
| `lufsRange` | `float \| null` | Loudness range via `LoudnessEBUR128`. | LU | Indicates macro-dynamic movement across sections. |
| `truePeak` | `float \| null` | Max true peak across stereo channels. | linear amplitude proxy (rounded) | Helps detect clipping risk and required headroom when rebuilding. |
| `crestFactor` | `float \| null` | Peak-to-RMS ratio over mono signal. | dB | Higher crest means stronger transients/less compression; lower crest suggests denser limiting/compression. |
| `lufsMomentaryMax` | `float \| null` | Maximum momentary loudness (400 ms window) via `LoudnessEBUR128`. | LUFS | Peak short-burst loudness; useful for detecting loud transient moments. |
| `lufsShortTermMax` | `float \| null` | Maximum short-term loudness (3 s window) via `LoudnessEBUR128`. | LUFS | Peak sustained loudness; gap between this and integrated LUFS indicates dynamic range use. |
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
| `spectralDetail.spectralCentroid` | `float` | Global mean centroid. | Hz | Higher centroid generally means brighter spectral tilt. Normalized to `spectralCentroidMean` in HTTP response. |
| `spectralDetail.spectralRolloff` | `float` | Global mean rolloff frequency. | Hz | Indicates where most spectral energy accumulates below. Normalized to `spectralRolloffMean` in HTTP response. |
| `spectralDetail.spectralBandwidth` | `float` | Global mean spectral bandwidth (weighted std dev around centroid). | Hz | Wider bandwidth → richer harmonic content. Normalized to `spectralBandwidthMean` in HTTP response. |
| `spectralDetail.spectralFlatness` | `float` | Global mean spectral flatness. | 0–1 ratio | 0 = pure tone, 1 = white noise. Indicates noise-like vs tonal character. Normalized to `spectralFlatnessMean` in HTTP response. |
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
| `rhythmDetail.beatGrid` | `float[]` | Full-track beat timestamps from the detected beat grid (uncapped). | seconds | Use to align arrangement/clip markers across the full timeline. |
| `rhythmDetail.downbeats` | `float[]` | Beat-1 timestamp for each detected 4-beat bar. | seconds | Useful for bar-aligned locators and section anchoring. |
| `rhythmDetail.beatPositions` | `int[]` | Bar position for each beat in `beatGrid` (`1`, `2`, `3`, `4`). | beat index within bar | Aligns directly with `beatGrid` for bar-aware rhythm reconstruction. |
| `rhythmDetail.grooveAmount` | `float` | Normalised beat interval variability. | unitless | Higher values imply more timing looseness/swing. |
| `rhythmDetail.tempoStability` | `float \| null` | Tempo stability score: `1.0 - grooveAmount`, clipped to 0-1. | 0-1 | Higher values indicate more clock-like tempo; lower values suggest human or intentional drift. |
| `rhythmDetail.phraseGrid` | `object \| null` | Phrase structure derived from downbeat grouping. | object | Provides 4/8/16-bar phrase boundaries for arrangement-level grid alignment. |
| `rhythmDetail.phraseGrid.phrases4Bar` | `float[]` | Start times of 4-bar phrases. | seconds | Use for fine phrase alignment. |
| `rhythmDetail.phraseGrid.phrases8Bar` | `float[]` | Start times of 8-bar phrases. | seconds | Common electronic music phrase length. |
| `rhythmDetail.phraseGrid.phrases16Bar` | `float[]` | Start times of 16-bar phrases. | seconds | Section-level phrase boundaries. |
| `rhythmDetail.phraseGrid.totalBars` | `int` | Total number of detected bars. | count | Track length in bars for arrangement planning. |
| `rhythmDetail.phraseGrid.totalPhrases8Bar` | `int` | Total number of 8-bar phrases. | count | Quick structural count for electronic arrangement estimation. |

Note: `rhythmDetail.beatPositions` previously referred to a truncated beat-timestamp alias. That timestamp array is now exposed as `rhythmDetail.beatGrid` for the full track.

### `grooveDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `grooveDetail.kickSwing` | `float` | Swing proxy from low-band accented beat spacing. | unitless | Captures low-end timing push/pull. |
| `grooveDetail.hihatSwing` | `float` | Swing proxy from high-band accented beat spacing. | unitless | Captures high-frequency rhythmic looseness. |
| `grooveDetail.kickAccent` | `float[]` | Up-to-16 sampled low-band beat loudness values. | linear loudness proxy | Shape of kick emphasis over time. |
| `grooveDetail.hihatAccent` | `float[]` | Up-to-16 sampled high-band beat loudness values. | linear loudness proxy | Shape of high-percussion emphasis over time. |

### `beatsLoudness`

Type: `object \| null`

Beat-synchronous loudness analysis via Essentia `BeatsLoudness`. Summary statistics are always present in the HTTP response; the raw per-beat loudness matrix is only included when `ASA_DEBUG_BEATS_LOUDNESS=1` is set.

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `beatsLoudness.kickDominantRatio` | `float` | Fraction of beats where the kick (low) band is loudest. | 0-1 | High values indicate kick-driven groove; low values suggest mid/high-frequency rhythmic emphasis. |
| `beatsLoudness.midDominantRatio` | `float` | Fraction of beats where the mid band is loudest. | 0-1 | Elevated values suggest chord-stab or synth-driven rhythmic energy. |
| `beatsLoudness.highDominantRatio` | `float` | Fraction of beats where the high band is loudest. | 0-1 | Elevated values suggest hi-hat or cymbal-driven groove. |
| `beatsLoudness.accentPattern` | `float[4]` | Normalized beat accent across bar positions (4 values for 4/4). | 0-1 per position | Shows accent weight per beat within the bar; useful for groove template reconstruction. |
| `beatsLoudness.meanBeatLoudness` | `float` | Mean loudness across all detected beats. | linear loudness | Overall rhythmic energy level baseline. |
| `beatsLoudness.beatLoudnessVariation` | `float` | Coefficient of variation of beat loudness. | unitless ratio | Higher values indicate more dynamic variation across beats (less compressed). |
| `beatsLoudness.beatCount` | `int` | Number of beats analysed. | count | Context for statistical reliability of the beat loudness summary. |

### `sidechainDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `sidechainDetail.pumpingStrength` | `float` | Depth/alignment score for loudness dips vs kick activity. | 0.0-1.0 | Higher values suggest stronger audible sidechain-style ducking. |
| `sidechainDetail.pumpingRegularity` | `float` | Period consistency of detected pumping intervals. | 0.0-1.0 | High values indicate clock-like pumping, useful for genre-consistent groove reconstruction. |
| `sidechainDetail.pumpingRate` | `"quarter" \| "eighth" \| "sixteenth" \| null` | Best-matching pumping grid rate. | categorical | Suggests compressor trigger rhythm for Ableton sidechain setup. |
| `sidechainDetail.pumpingConfidence` | `float` | Reliability score (kick clarity + dip correlation + timing stability penalties). | 0.0-1.0 | Low confidence means avoid overcommitting to sidechain recreation without ear-checking. |
| `sidechainDetail.envelopeShape` | `float[16] \| null` | Normalized median RMS envelope across bars at 16th-note resolution. | 0-1 per step | Rhythmic amplitude shape useful for sidechain curve recreation; peak at step 0 typically indicates kick position. |

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

### `transcriptionDetail`

Type: `object \| null`

Implementation notes:

- `transcriptionDetail` is tuned for bass + hook extraction, not broad pitch sketching.
- The backend applies a noise-only confidence floor of `0.05` before merge so obviously bad detections never reach the UI.
- The Session Musician confidence slider remains the primary user-facing quality dial with range `0.0-1.0` and default `0.2`.
- Notes are deduplicated after merge, then capped:
  - stem-aware runs keep at most `500` notes
  - `full_mix` fallback runs keep at most `200` notes
- `noteCount`, `averageConfidence`, `dominantPitches`, and `pitchRange` all describe the retained post-dedup, post-cap note set.

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `transcriptionDetail.transcriptionMethod` | `string` | Name of the transcription backend used. Current backend reports `'torchcrepe-viterbi'`. | categorical | Identifies the transcription engine. |
| `transcriptionDetail.noteCount` | `int` | Total number of retained note events after merge, deduplication, and capping. | count | Higher counts imply denser retained musical content rather than raw backend event volume. |
| `transcriptionDetail.averageConfidence` | `float` | Mean confidence across the retained merged note events. | 0.0-1.0 | Lower values indicate noisier or more ambiguous pitch tracking even after backend noise filtering. |
| `transcriptionDetail.dominantPitches` | `array<object>` | Top 5 most frequent detected pitches. | list of pitch summary objects | Quick tonal summary for bassline and hook reconstruction. |
| `transcriptionDetail.dominantPitches[].pitchMidi` | `int` | MIDI pitch number for the dominant pitch entry. | 0-127 | Directly usable for DAW note entry or tonal analysis. |
| `transcriptionDetail.dominantPitches[].pitchName` | `string` | Note name for the dominant pitch entry. | note label | Human-readable pitch label for prompts and reports. |
| `transcriptionDetail.dominantPitches[].count` | `int` | Number of note events using that pitch. | count | Helps distinguish tonic-like repetition from incidental notes. |
| `transcriptionDetail.pitchRange` | `object` | Aggregate min/max pitch across merged note events. | object | Fast register summary for the transcribed sources. |
| `transcriptionDetail.pitchRange.minMidi` | `int \| null` | Lowest detected MIDI pitch. | MIDI note number | Lower register bound of the combined transcription. |
| `transcriptionDetail.pitchRange.maxMidi` | `int \| null` | Highest detected MIDI pitch. | MIDI note number | Upper register bound of the combined transcription. |
| `transcriptionDetail.pitchRange.minName` | `string \| null` | Note name of the lowest detected pitch. | note label | Human-readable lower pitch bound. |
| `transcriptionDetail.pitchRange.maxName` | `string \| null` | Note name of the highest detected pitch. | note label | Human-readable upper pitch bound. |
| `transcriptionDetail.stemSeparationUsed` | `bool` | Whether transcription ran on separated Demucs stems instead of the full mix. | boolean | `true` means the merged result came from one or more stems such as `bass` and `other`. |
| `transcriptionDetail.fullMixFallback` | `bool` | `true` when the transcription ran on the full mix because usable stems were unavailable. | boolean | Treat `true` as a quality warning on dense material; downstream UX should inform rather than block. |
| `transcriptionDetail.stemsTranscribed` | `string[]` | Ordered list of audio sources transcribed for this result. | source labels | Use to distinguish full-mix fallback from stem-based transcription. |
| `transcriptionDetail.notes` | `array<object>` | Retained note events sorted by onset time after merge, deduplication, and capping. | list of note objects | Combined note timeline from stem-based or full-mix transcription, bounded for UI and export use. |
| `transcriptionDetail.notes[].pitchMidi` | `int` | MIDI note number for the event. | 0-127 | Directly usable in piano-roll or MIDI regeneration workflows. |
| `transcriptionDetail.notes[].pitchName` | `string` | Note name for the event. | note label | Human-readable pitch name for summaries and prompts. |
| `transcriptionDetail.notes[].onsetSeconds` | `float` | Note onset time. | seconds | Place note start accurately in arrangement timeline. |
| `transcriptionDetail.notes[].durationSeconds` | `float` | Note duration. | seconds | Approximate note gate length for MIDI reconstruction. |
| `transcriptionDetail.notes[].confidence` | `float` | Confidence score for the event. | 0.0-1.0 | Use as a weighting signal when filtering or trusting note detections. |
| `transcriptionDetail.notes[].stemSource` | `"bass" \| "other" \| "full_mix"` | Source audio used to detect that note event. | categorical | Lets downstream tooling separate bass-derived notes from residual or fallback detections. |

---

## Pitch Detail (torchcrepe)

### `pitchDetail`

Type: `object | null`

Continuous pitch tracking via torchcrepe on separated stems. Only populated when `--separate` is used; `null` otherwise.

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `pitchDetail.method` | `string` | Pitch extraction backend identifier. Currently `"torchcrepe"`. | categorical | Future backends may use different methods; check before assuming output shape. |
| `pitchDetail.stems` | `object` | Per-stem pitch results keyed by stem name (`"vocals"`, `"other"`). | object map | Not all stems may be present; check key existence. |
| `pitchDetail.stems[name].medianPitchHz` | `float \| null` | Median pitch of voiced frames. | Hz | Core tonal centre of the stem; `null` when no voiced frames detected. |
| `pitchDetail.stems[name].pitchRangeLowHz` | `float \| null` | 5th percentile pitch of voiced frames. | Hz | Lower register bound for instrument/voice range estimation. |
| `pitchDetail.stems[name].pitchRangeHighHz` | `float \| null` | 95th percentile pitch of voiced frames. | Hz | Upper register bound for instrument/voice range estimation. |
| `pitchDetail.stems[name].meanPeriodicity` | `float` | Mean periodicity/confidence across all frames. | 0-1 | Lower values indicate noisier/less tonal content; higher values indicate cleaner pitch tracking. |
| `pitchDetail.stems[name].voicedFramePercent` | `float` | Percentage of frames with periodicity > 0.5. | 0-100 | Indicates how much of the stem contains tonal/pitched content. Low values on vocals may indicate sparse vocal phrases or arp-style hits. |
| `pitchDetail.stems[name].hopLength` | `int` | Hop length used for frame analysis. | samples | 512 at 44100 Hz ≈ 11.6 ms per frame. |
| `pitchDetail.stems[name].sampleRate` | `int` | Sample rate of the analysed stem. | Hz | Matches the Demucs output rate (typically 44100). |
| `pitchDetail.stems[name].model` | `string` | torchcrepe model variant used (`"tiny"` or `"full"`). | categorical | `tiny` is faster but less accurate; `full` is more precise but CPU-heavy. |

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
| `segmentKey[].key` | `string \| null` | Per-segment key label (`edma` profile). | categorical | Detects section-level key drift or modal pivots. |
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

Future note: per-segment structural labels such as `"verse"`, `"chorus"`, and `"bridge"` are planned additions to `structure.segments`, but are not emitted yet.

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

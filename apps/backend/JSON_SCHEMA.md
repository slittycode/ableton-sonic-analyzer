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

`phase1Version`, `bpm`, `bpmConfidence`, `bpmPercival`, `bpmAgreement`, `bpmDoubletime`, `bpmSource`, `bpmRawOriginal`, `key`, `keyConfidence`, `keyProfile`, `tuningFrequency`, `tuningCents`, `timeSignature`, `timeSignatureSource`, `timeSignatureConfidence`, `durationSeconds`, `sampleRate`, `lufsIntegrated`, `lufsRange`, `lufsMomentaryMax`, `lufsShortTermMax`, `lufsCurve`, `truePeak`, `crestFactor`, `dynamicSpread`, `monoCompatible`, `plr`, `dynamicCharacter`, `textureCharacter`, `stereoDetail`, `spectralBalance`, `spectralBalanceTimeSeries`, `spectralDetail`, `stemAnalysis`, `transientDensityDetail`, `saturationDetail`, `snareDetail`, `hihatDetail`, `rhythmDetail`, `melodyDetail`, `transcriptionDetail`, `pitchDetail`, `grooveDetail`, `beatsLoudness`, `rhythmTimeline`, `sidechainDetail`, `reverbDetail`, `vocalDetail`, `acidDetail`, `supersawDetail`, `bassDetail`, `kickDetail`, `genreDetail`, `effectsDetail`, `synthesisCharacter`, `danceability`, `structure`, `arrangementDetail`, `segmentLoudness`, `segmentSpectral`, `segmentStereo`, `segmentKey`, `chordDetail`, `perceptual`, `essentiaFeatures`.

**Shared (fast + full) vs full-only.** Fast-mode output is asserted byte-for-byte against the `EXPECTED_TOP_LEVEL_KEYS` set in [`tests/test_analyze.py`](tests/test_analyze.py). Full mode emits those keys *plus* a handful of detail-only fields that are deliberately absent from the shared snapshot: `keyProfile`, `tuningFrequency`, `tuningCents`, `lufsMomentaryMax`, `lufsShortTermMax`, and `pitchDetail`. When changing the schema, update both this list and `EXPECTED_TOP_LEVEL_KEYS`; full-only fields stay out of that set on purpose. See CLAUDE.md tripwire #4. Schema changes are also cross-checked executably against the frontend fixture and parser by `apps/ui/tests/services/phase1ContractParity.test.ts`, driven by the golden snapshot's `topLevelKeys`/`keyTree` — regenerating the golden (`UPDATE_PHASE1_GOLDEN=1`) is what arms the nested half of that gate.

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
- `textureCharacter`
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
- `timeSignatureSource`
- `timeSignatureConfidence`
- `sampleRate`
- `lufsMomentaryMax`
- `lufsShortTermMax`
- `dynamicSpread`
- `bpmDoubletime`
- `bpmSource`
- `bpmRawOriginal`

All raw `analyze.py` fields are now forwarded through the server `phase1` wrapper, including fields previously excluded: `bpmPercival`, `bpmAgreement`, `timeSignatureSource`, `timeSignatureConfidence`, `sampleRate`, `dynamicSpread`, `dynamicCharacter`, `textureCharacter`, `segmentStereo`, `essentiaFeatures`.

Two server-only convenience fields are derived from `stereoDetail`:

- `phase1.stereoWidth`
- `phase1.stereoCorrelation`

Current server behavior that affects schema expectations:

- `transcriptionDetail` is only populated when `analyze.py` runs with `--transcribe`
- `pitchDetail` is only populated when `--separate` is used; requires torchcrepe and separated stems
- `danceability` is forwarded as the raw object shown below, not as a scalar
- `dsp_json_override` is accepted by the server but does not alter the analyzer payload
- `transcription` (the optional MT3 namespace) is *absent* — not `null` — unless the
  env var `ASA_ENABLE_MT3=1` is set AND the MT3 extra is installed AND the call
  succeeds. The key is intentionally NOT in `EXPECTED_TOP_LEVEL_KEYS` (the
  shared full/fast contract); presence-or-absence is the contract. See the
  "Optional MT3 Namespace" section below.

---

## Core Metrics

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `phase1Version` | `string` | Phase 1 JSON schema version, e.g. `"phase1.v2"`. | identifier | Lets consumers detect the schema generation. v2 changed `truePeak` (now dBTP) and `bpmConfidence` (now 0-1) units vs v1. |
| `bpm` | `float \| null` | Primary tempo estimate from `RhythmExtractor2013`. | beats per minute | Main tempo anchor for Ableton project tempo and clip warp assumptions. |
| `bpmConfidence` | `float \| null` | Tempo confidence from `RhythmExtractor2013`, normalized to 0-1. | 0-1 (Phase 1 v2: raw Essentia confidence ~0-5.32 divided by 5.0 and clamped) | Higher = stronger rhythmic periodicity. Below 0.4 (raw < 2.0) suggests an ambiguous pulse or half/double-time content; hedge tempo claims there. |
| `key` | `string \| null` | Global key label from `KeyExtractor` (`edma` profile), e.g. `"A Minor"`. | categorical | Starting point for harmonic reconstruction; validate by ear against bass/chord roots. |
| `keyConfidence` | `float \| null` | Confidence/strength of global key estimate. | 0-1 (approx) | Low values indicate ambiguous tonality or modal/atonal content. |
| `timeSignature` | `string \| null` | Time signature estimate (currently defaults to `"4/4"` when rhythm exists). | string | Treat as prior; verify manually on odd-metre material. |
| `timeSignatureSource` | `string \| null` | Provenance marker for the raw `timeSignature` value. Current analyzer emits `"assumed_four_four"` when rhythm data exists. | categorical | Forwarded through HTTP `phase1`; use it to distinguish measured vs assumed meter. |
| `timeSignatureConfidence` | `float \| null` | Confidence attached to the raw `timeSignature` value. Current analyzer emits `0.0` for the assumed 4/4 fallback. | 0-1 | Forwarded through HTTP `phase1`; use low values to avoid overstating meter certainty. |
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
| `truePeak` | `float \| null` | Max true peak across stereo channels. | dBTP (Phase 1 v2: was a linear amplitude proxy in v1) | 0.0 dBTP == full scale; > 0.0 == inter-sample over; `null` for digital silence (no defined dBTP). Helps detect clipping risk and required headroom when rebuilding. |
| `crestFactor` | `float \| null` | Peak-to-RMS ratio over mono signal. | dB | Higher crest means stronger transients/less compression; lower crest suggests denser limiting/compression. |
| `lufsMomentaryMax` | `float \| null` | Maximum momentary loudness (400 ms window) via `LoudnessEBUR128`. | LUFS | Peak short-burst loudness; useful for detecting loud transient moments. |
| `lufsShortTermMax` | `float \| null` | Maximum short-term loudness (3 s window) via `LoudnessEBUR128`. | LUFS | Peak sustained loudness; gap between this and integrated LUFS indicates dynamic range use. |
| `dynamicSpread` | `float \| null` | Ratio of broad-band energy means (sub/mid/high approximation). | unitless ratio | Quick indicator of how unevenly energy is distributed across broad frequency regions. |

### `lufsCurve`

Type: `object \| null`

Per-frame EBU R128 loudness over time. Each curve is downsampled to ~200 points on a 2-minute track; points sit at bin-center timestamps relative to track start.

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `lufsCurve.shortTerm` | `Array<{t: float, lufs: float}>` | Short-term (3 s window) loudness curve. | seconds / LUFS | Phase 2 cites this to explain breakdown-vs-drop loudness contrast and section-relative dynamics. |
| `lufsCurve.momentary` | `Array<{t: float, lufs: float}>` | Momentary (400 ms window) loudness curve. | seconds / LUFS | Finer-grained than `shortTerm`; useful for spotting punch and transient swells. |

### `dynamicCharacter`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `dynamicCharacter.dynamicComplexity` | `float` | From `DynamicComplexity`; measures short-term loudness variation complexity. | unitless | Higher values often indicate denser envelope modulation, pumping, or articulated transients. |
| `dynamicCharacter.loudnessDb` | `float` | Secondary output from `DynamicComplexity`; an estimated loudness value. | dB | Use as a loudness anchor for the dynamics block, not as a variation metric. |
| `dynamicCharacter.loudnessVariation` | `float` | Deprecated alias of `loudnessDb`, kept for compatibility. | dB | Treat this as the same loudness estimate as `loudnessDb`. |
| `dynamicCharacter.spectralFlatness` | `float` | Mean full-spectrum frame spectral flatness. | 0-1 (tonal->noisy) | Legacy global texture proxy; useful but can understate band-limited abrasive/noise-heavy material. |
| `dynamicCharacter.logAttackTime` | `float` | Mean log attack time (fallback-first strategy). | log10(seconds) style | More negative implies faster attacks/transients; less negative implies slower envelope rise. |
| `dynamicCharacter.attackTimeStdDev` | `float` | Std dev of linearised attack times. | seconds (derived) | Higher spread suggests mixed transient behaviours across events. |

### `textureCharacter`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `textureCharacter.textureScore` | `float` | Weighted summary of band flatness plus optional inharmonicity. | 0-1 | Deterministic texture/noisiness summary for abrasive, distorted, or industrial material. |
| `textureCharacter.lowBandFlatness` | `float` | Mean flatness over 20-250 Hz. | 0-1 | Captures how noise-like or broadband the low-end is. |
| `textureCharacter.midBandFlatness` | `float` | Mean flatness over 250-2000 Hz. | 0-1 | Useful for gritty body, distortion, and abrasive midrange texture. |
| `textureCharacter.highBandFlatness` | `float` | Mean flatness over 2000-12000 Hz. | 0-1 | Useful for hiss, hash, harshness, and noisy top-end texture. |
| `textureCharacter.inharmonicity` | `float \| null` | Copied through from synthesis analysis when available. | unitless | Higher values reinforce a metallic/noisy reading but are not required for the score to exist. |

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
| `stereoDetail.correlationCurve` | `Array<{t: float, full: float \| null, sub: float \| null}> \| null` | 1-second windowed L/R correlation, full-band and sub-band side-by-side. | seconds / Pearson r in [-1, 1] | Surfaces stereo automation (Utility width sweeps, mono-collapsing the drop) that the global scalars conflate into one number. `sub` may be null in windows where the sub band is silent. |
| `stereoDetail.bandCorrelations` | `object \| null` | Per-frequency-band L/R Pearson correlation, keyed by the same 7 bands as `spectralBalance` (subBass / lowBass / lowMids / mids / upperMids / highs / brilliance). | dict of Pearson r in [-1, 1] or null | Phase 2 cites these to recommend Utility-tool width per band ("bass is mono at 0.98 but mids are wide at 0.45 — add width on the synth bus only"). Per-band null means that band carries no usable energy on this track. |

Example interpretation:
- `subBassMono: true` -> "Sub bass is mono-compatible. Standard for club music. Advise keeping bass synthesis below ~150 Hz mono in Ableton."
- A `correlationCurve` row at `t=48.0` showing `full: 0.42` while the integrated `stereoCorrelation` is `0.78` indicates a deliberate width-opening automation around that section.

---

## Spectral Balance

### `spectralBalance`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `spectralBalance.subBass` | `float` | Mean energy in 20-80 Hz band. | dB (relative) | Indicates weight of true sub fundamentals. |
| `spectralBalance.lowBass` | `float` | Mean energy in 80-250 Hz band. | dB (relative) | Covers kick thump and bass body. |
| `spectralBalance.lowMids` | `float` | Mean energy in 250-500 Hz band. | dB (relative) | Lower midrange — body of low instruments, room boom. Field exists in code but was previously absent from this doc; mind the asymmetry until older readers update. |
| `spectralBalance.mids` | `float` | Mean energy in 500-2000 Hz band. | dB (relative) | Core musical body and intelligibility region. |
| `spectralBalance.upperMids` | `float` | Mean energy in 2-5 kHz band. | dB (relative) | Presence/attack region; affects perceived forwardness. |
| `spectralBalance.highs` | `float` | Mean energy in 5-10 kHz band. | dB (relative) | Brightness and air onset content. |
| `spectralBalance.brilliance` | `float` | Mean energy in 10-20 kHz band. | dB (relative) | Extreme top-end "air"; often reduced on lossy or dark masters. |

### `spectralBalanceTimeSeries`

Type: `Array<{t: float, subBass: float, lowBass: float, lowMids: float, mids: float, upperMids: float, highs: float, brilliance: float}> \| null`

Sibling time-series partner for `spectralBalance`. Each row carries all seven bands at a given timestamp (bin-center, seconds). Downsampled to ~200 rows on a 2-minute track. Phase 2 cites entries like `spectralBalanceTimeSeries` plus a time index ("the high-end opens up at 1:23") rather than only static averages. Lives as a sibling rather than nested inside `spectralBalance` because that field's exact 7-key shape is asserted by the backend test contract.

### `stemAnalysis`

Type: `object \| null`

Phase 1.B per-stem analytical surface — populated only when stem separation ran successfully (`--separate`). Null when separation wasn't requested or failed. Phase 2 cites individual stems for element-specific recommendations.

The separation backend is **selectable** (`ASA_SEPARATION_BACKEND`, default `demucs`; `msst` drives a stronger MSST/BS-RoFormer model — see `separation_backend.py`), but this schema is **backend-agnostic**: stems are always the canonical `drums`/`bass`/`other`/`vocals` at 44.1 kHz, so `stemAnalysis` is unchanged regardless of which backend produced them.

For each available stem (`drums` / `bass` / `other` / `vocals`), the same high-value full-mix analyzers run on the stem's audio:

| Field per stem | Type | Description |
|---|---|---|
| `stemAnalysis.{stem}.spectralBalance` | `object` | Same 7-band shape as the top-level `spectralBalance`. Per-element EQ target. |
| `stemAnalysis.{stem}.spectralBalanceTimeSeries` | `array` | Per-stem 7-band time series, downsampled to ~200 frames. |
| `stemAnalysis.{stem}.spectralDetail` | `object` | Per-stem centroid/rolloff/MFCC/Bark/ERB/chroma. Same shape as top-level. |
| `stemAnalysis.{stem}.lufsIntegrated` | `float` | Per-stem integrated EBU R128 loudness. |
| `stemAnalysis.{stem}.lufsRange` / `.lufsMomentaryMax` / `.lufsShortTermMax` | `float` | Per-stem loudness statistics. |
| `stemAnalysis.{stem}.lufsCurve` | `object` | Per-stem `{shortTerm, momentary}` curves. |
| `stemAnalysis.{stem}.stereoDetail` | `object` | Per-stem stereo width/correlation/subBassMono/correlationCurve. |
| `stemAnalysis.{stem}.truePeak` | `float` | Per-stem true peak across L/R. |
| `stemAnalysis.{stem}.crestFactor` / `.dynamicSpread` | `float` | Per-stem dynamics scalars. |
| `stemAnalysis.{stem}.dynamicCharacter` | `object` | Per-stem dynamic-complexity / attack profile. |
| `stemAnalysis.{stem}.reverbDetail` | `object` | Phase 1.D #5 — per-stem reverb estimation. Same shape as the top-level `reverbDetail` (rt60 / isWet / tailEnergyRatio / measured / perBandRt60 / preDelayMs). Drums stem is typically the cleanest signal; long RT60 on bass/other/vocals often reflects sustained tonal decay rather than reverb. When `measured: false` the slope-fit didn't have enough transients on that stem — treat as fallback. |

**Intentionally not per-stem:** BPM, key, time signature, structure novelty, sidechain pumping, danceability, chord progression. These are song-level properties — splitting them per-stem would produce noise.

### `transientDensityDetail`

Type: `object \| null`

Phase 1.C #1 — per-frequency-band onset density across the 7 `SPECTRAL_BALANCE_BANDS`. For each band (`subBass`, `lowBass`, `lowMids`, `mids`, `upperMids`, `highs`, `brilliance`):

| Field per band | Type | Description |
|---|---|---|
| `transientDensityDetail.{band}.onsetRatePerSecond` | `float` | Detected onset events per second within this band. |
| `transientDensityDetail.{band}.meanOnsetStrength` | `float` | Mean librosa onset-envelope value at detected peaks. |
| `transientDensityDetail.{band}.peakOnsetStrength` | `float` | Max onset-envelope value across the track. |
| `transientDensityDetail.{band}.eventCount` | `int` | Number of detected onsets. |

**LLM interpretation notes:**
- Cite `transientDensityDetail.lowBass.onsetRatePerSecond` for kick-density / drum-bus claims.
- Cite `transientDensityDetail.highs.eventCount` for hi-hat density / shaker activity.
- Use cross-band comparisons to anchor "drums-heavy in upper mids, bass smooth in subs" advice.
- High onset density + low mean strength suggests sustained content (synth pad); high mean strength + low density suggests sparse hits.

### `saturationDetail`

Type: `object \| null`

Phase 1.C #5 — saturation / clipping / over-compression telltales. Hint-level signals — Phase 2 must hedge per the citation contract's low-confidence rules until the audit bench confirms.

| Field | Type | Description |
|---|---|---|
| `saturationDetail.clippedSampleCount` | `int` | Stereo samples with `|x| >= 0.9999`. |
| `saturationDetail.clippedSamplePercent` | `float` | Percentage of total samples that crossed the clip threshold. |
| `saturationDetail.nearClippedSampleCount` | `int` | Samples with `|x| >= 0.95`. |
| `saturationDetail.nearClippedSamplePercent` | `float` | Percentage near mastering-loud territory. |
| `saturationDetail.peakRatio95to50` | `float \| null` | Ratio of 95th-percentile `|x|` to 50th-percentile. Higher = more dynamic. |
| `saturationDetail.rmsToPeakRatioDb` | `float \| null` | Peak-vs-RMS in dB on the mono buffer. Inverse-shape of crest factor. |
| `saturationDetail.saturationLikely` | `bool` | Heuristic: any clipping, sustained near-clipping, or low peak ratio + low RMS-to-peak. NOT definitive — Phase 2 should hedge. |

**LLM interpretation notes:**
- A non-zero `clippedSampleCount` is a strong signal — recommend Saturator or Limiter ceiling at -0.3 dB.
- `peakRatio95to50` below ~1.7 with low `rmsToPeakRatioDb` (< 7 dB) suggests heavy limiting / brickwall mastering.
- `saturationLikely=true` alone is a hint, not a verdict — combine with crest factor and `dynamicCharacter.dynamicComplexity` for confidence.

### `snareDetail` / `hihatDetail`

Both types: `object \| null`. Same shape (BandDrumDetail), different bands.

Phase 1.C #4 — band-limited drum character. Mirrors the `analyze_kick_detail` pattern in the 120-2000 Hz band (snare body + snap) and 2000-12000 Hz band (hi-hat brightness / openness). Uses the drums stem when available, otherwise falls back to spectrum-bin selection on the full mix.

| Field | Type | Description |
|---|---|---|
| `{snare\|hihat}Detail.hitCount` | `int` | Detected onsets in band. |
| `{snare\|hihat}Detail.hitsPerSecond` | `float` | Hits per second. Useful for groove density. |
| `{snare\|hihat}Detail.meanAttackSharpness` | `float` | Mean envelope rise across 2 frames before each peak — a transient sharpness proxy. |
| `{snare\|hihat}Detail.meanBodyEnergyRatio` | `float \| null` | Fraction of per-hit spectral energy in the lower half of the band. For snare: body region (~120-755 Hz). For hi-hat: lower half (~2-6 kHz). |
| `{snare\|hihat}Detail.meanSnapEnergyRatio` | `float \| null` | Fraction in the upper half of the band. Higher snare value = more snap; higher hi-hat value = more sizzle. |
| `{snare\|hihat}Detail.meanCentroidHz` | `float \| null` | Mean spectral centroid weighted by magnitude across the per-hit spectra. |
| `{snare\|hihat}Detail.meanDecayFrames` | `float` | Mean frames between peak and envelope falling below 30% of peak. |
| `{snare\|hihat}Detail.meanDecaySeconds` | `float` | Same as above in seconds. For hi-hat, a rough open-vs-closed proxy (closed ~30-60 ms, open >150 ms). |
| `{snare\|hihat}Detail.bandHz` | `[float, float]` | Inclusive band edges actually used. |

**LLM interpretation notes:**
- Snare body vs snap balance: `meanBodyEnergyRatio > 0.6` = thick / round snare; `meanSnapEnergyRatio > 0.55` = snappy / clappy. Recommends Saturator drive or EQ Eight body/snap shaping accordingly.
- Hi-hat decay: `meanDecaySeconds < 0.06` = closed/tight hats; `> 0.15` = open / shaker / cymbal-ish content. Drives reverb send choice and Auto Filter tone.
- `hitsPerSecond` on hi-hat: 4-8 = 8th notes at house tempos, 8-16 = 16th notes / trap-style, >16 = rolls / shaker textures.
- Detail is null when no source provides ≥2 detected hits in band (fallback returns null gracefully).

**LLM interpretation notes:**
- Cite per-stem paths to justify element-specific recommendations ("Glue Compress the kick at -8 dB threshold because `stemAnalysis.drums.crestFactor = 11.2 dB`" rather than the full-mix crest).
- Compare values across stems for masking / EQ-balance claims (e.g. `stemAnalysis.bass.spectralBalance.subBass` vs `stemAnalysis.drums.spectralBalance.subBass` for sub-bass overlap).
- If a stem is missing from the dict, treat that stem as "not separated" — don't infer it's silent.

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
| `rhythmDetail.downbeats` | `float[]` | Bar-1 (downbeat) timestamps. Bar-1 phase is resolved from the kick-accent pattern within the detected meter (no longer a fixed `beatGrid[::4]` stride); falls back to that stride when per-beat low-band data is unavailable. | seconds | Useful for bar-aligned locators and section anchoring. Hedge per `downbeatConfidence`. |
| `rhythmDetail.beatPositions` | `int[]` | Bar position for each beat in `beatGrid` (`1`..`meter`), phase-aligned so position `1` lands on the resolved downbeat. | beat index within bar | Aligns directly with `beatGrid` for bar-aware rhythm reconstruction. |
| `rhythmDetail.downbeatSource` | `"kick_accent" \| "stride"` | How the bar-1 phase was resolved: `kick_accent` (kick-heaviest beat position within the meter) or `stride` (legacy 4/4 fallback when per-beat low-band data is missing). | categorical | `stride` means the phase is unverified; treat downbeats as approximate. |
| `rhythmDetail.downbeatConfidence` | `float` | How distinctly the chosen bar-1 position dominates the other beat positions in kick energy. Collapses toward `0` for four-on-the-floor (a kick on every beat carries no phase information). | 0-1 | Low values are honest hedging, not failure — soften bar-aligned recommendations accordingly. |
| `rhythmDetail.grooveAmount` | `float` | Normalised beat interval variability. | unitless | Higher values imply more timing looseness/swing. |
| `rhythmDetail.tempoStability` | `float \| null` | Tempo stability score: `1.0 - grooveAmount`, clipped to 0-1. | 0-1 | Higher values indicate more clock-like tempo; lower values suggest human or intentional drift. |
| `rhythmDetail.phraseGrid` | `object \| null` | Phrase structure derived from downbeat grouping. | object | Provides 4/8/16-bar phrase boundaries for arrangement-level grid alignment. |
| `rhythmDetail.phraseGrid.phrases4Bar` | `float[]` | Start times of 4-bar phrases. | seconds | Use for fine phrase alignment. |
| `rhythmDetail.phraseGrid.phrases8Bar` | `float[]` | Start times of 8-bar phrases. | seconds | Common electronic music phrase length. |
| `rhythmDetail.phraseGrid.phrases16Bar` | `float[]` | Start times of 16-bar phrases. | seconds | Section-level phrase boundaries. |
| `rhythmDetail.phraseGrid.totalBars` | `int` | Total number of detected bars. | count | Track length in bars for arrangement planning. |
| `rhythmDetail.phraseGrid.totalPhrases8Bar` | `int` | Total number of 8-bar phrases. | count | Quick structural count for electronic arrangement estimation. |
| `rhythmDetail.tempoCurve` | `Array<{t: float, bpm: float}> \| null` | Instantaneous-BPM curve from beat ticks, smoothed with a 4-beat rolling median, downsampled to ~200 points. | seconds / BPM | Surfaces deliberate ritardando/accelerando and DJ-tool tempo blends that the single mean `bpm` scalar conflates away. Phase 2 cites this to explain tempo-modulated sections. |

Note: `rhythmDetail.beatPositions` previously referred to a truncated beat-timestamp alias. That timestamp array is now exposed as `rhythmDetail.beatGrid` for the full track.

### `grooveDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `grooveDetail.kickSwing` | `float` | Swing proxy from low-band accented beat spacing. | unitless | Captures low-end timing push/pull. |
| `grooveDetail.hihatSwing` | `float` | Swing proxy from high-band accented beat spacing. | unitless | Captures high-frequency rhythmic looseness. |
| `grooveDetail.kickAccent` | `float[]` | Up-to-16 sampled low-band beat loudness values. | linear loudness proxy | Shape of kick emphasis over time. |
| `grooveDetail.hihatAccent` | `float[]` | Up-to-16 sampled high-band beat loudness values. | linear loudness proxy | Shape of high-percussion emphasis over time. |
| `grooveDetail.perDrumSwing.kick` | `float` | Phase 1.C #3 — same kickSwing value, exposed as part of the per-drum-swing object so Phase 2 can cite all three groups uniformly. | 0-1 tanh-compressed | Cite alongside `perDrumSwing.snare` and `perDrumSwing.hihat` for groove-aware MIDI quantization recommendations. |
| `grooveDetail.perDrumSwing.snare` | `float` | Phase 1.C #3 — swing computed from the snare-band (200-4000 Hz) beat-loudness signal. | 0-1 tanh-compressed | New in this pass. Compare with `perDrumSwing.kick`: if snareSwing >> kickSwing, the snare is being human-pushed/pulled against a quantized kick (classic hip-hop / R&B layered feel). |
| `grooveDetail.perDrumSwing.hihat` | `float` | Phase 1.C #3 — same hihatSwing value, exposed inside the perDrumSwing object. | 0-1 tanh-compressed | Cite for shuffle / dilla / triplet-hat-feel recommendations. |

### `beatsLoudness`

Type: `object \| null`

Beat-synchronous loudness analysis via Essentia `BeatsLoudness`. Summary statistics are always present in the HTTP response; the raw per-beat loudness matrix is only included when `ASA_DEBUG_BEATS_LOUDNESS=1` is set.

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `beatsLoudness.kickDominantRatio` | `float` | Fraction of beats where the kick (low) band is loudest. | 0-1 | High values indicate kick-driven groove; low values suggest mid/high-frequency rhythmic emphasis. |
| `beatsLoudness.midDominantRatio` | `float` | Fraction of beats where the mid band is loudest. | 0-1 | Elevated values suggest chord-stab or synth-driven rhythmic energy. |
| `beatsLoudness.highDominantRatio` | `float` | Fraction of beats where the high band is loudest. | 0-1 | Elevated values suggest hi-hat or cymbal-driven groove. |
| `beatsLoudness.patternBeatsPerBar` | `int` | Beat positions represented by the bar-pattern arrays. | count | Currently `4` because meter is assumed 4/4 unless a future detector provides a better value. |
| `beatsLoudness.lowBandAccentPattern` | `float[]` | Normalized low-band accent by bar position. | 0-1 per position | Kick-weighted proxy used for bar-position groove sketches. |
| `beatsLoudness.midBandAccentPattern` | `float[]` | Normalized mid-band accent by bar position. | 0-1 per position | Clap/snare-weighted proxy used for bar-position groove sketches. |
| `beatsLoudness.highBandAccentPattern` | `float[]` | Normalized high-band accent by bar position. | 0-1 per position | Hi-hat/shaker-weighted proxy used for bar-position groove sketches. |
| `beatsLoudness.overallAccentPattern` | `float[]` | Normalized total beat accent by bar position. | 0-1 per position | Primary “accent” row for the rhythm grid UI. |
| `beatsLoudness.accentPattern` | `float[4]` | Normalized beat accent across bar positions (4 values for 4/4). | 0-1 per position | Shows accent weight per beat within the bar; useful for groove template reconstruction. |
| `beatsLoudness.meanBeatLoudness` | `float` | Mean loudness across all detected beats. | linear loudness | Overall rhythmic energy level baseline. |
| `beatsLoudness.beatLoudnessVariation` | `float` | Coefficient of variation of beat loudness. | unitless ratio | Higher values indicate more dynamic variation across beats (less compressed). |
| `beatsLoudness.beatCount` | `int` | Number of beats analysed. | count | Context for statistical reliability of the beat loudness summary. |

### `rhythmTimeline`

Type: `object | null`

Representative multi-bar sequencer window derived from DSP beat timing plus band-energy measurements at 16th-note resolution. This is intended for UI playback-style rhythm views. It is a frequency-band timeline, not isolated-instrument detection.

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `rhythmTimeline.beatsPerBar` | `int` | Beat count assumed for each bar in the sequencer timeline. | count | Currently `4` because meter detection still defaults to 4/4. |
| `rhythmTimeline.stepsPerBeat` | `int` | Step subdivision per beat. | count | Currently `4`, yielding 16th-note sequencing. |
| `rhythmTimeline.availableBars` | `int` | Total complete bars available to choose from. | count | Useful for deciding whether an 8-bar or 16-bar view is truthful. |
| `rhythmTimeline.selectionMethod` | `"representative_dsp_window"` | Window-selection strategy for the returned clip(s). | categorical | Means the chosen view is based on measured energy plus consistency, not arrangement semantics or AI interpretation. |
| `rhythmTimeline.windows[].bars` | `int` | Number of bars in this emitted clip window. | count | Usually `8`; `16` is only present when enough bars exist. |
| `rhythmTimeline.windows[].startBar` | `int` | Inclusive 1-based bar number where this clip window starts. | count | UI bar labels should mirror this directly. |
| `rhythmTimeline.windows[].endBar` | `int` | Inclusive 1-based bar number where this clip window ends. | count | UI bar labels should mirror this directly. |
| `rhythmTimeline.windows[].lowBandSteps` | `float[]` | Normalized low-band energy across the emitted steps. | 0-1 per step | Kick-weighted proxy lane. |
| `rhythmTimeline.windows[].midBandSteps` | `float[]` | Normalized mid-band energy across the emitted steps. | 0-1 per step | Snare/clap-range proxy lane. |
| `rhythmTimeline.windows[].highBandSteps` | `float[]` | Normalized high-band energy across the emitted steps. | 0-1 per step | Hat/shaker-range proxy lane. |
| `rhythmTimeline.windows[].overallSteps` | `float[]` | Normalized summed band energy across the emitted steps. | 0-1 per step | Truthful overall accent lane for the sequencer UI. |

### `sidechainDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `sidechainDetail.pumpingStrength` | `float` | Depth/alignment score for loudness dips vs kick activity. | 0.0-1.0 | Higher values suggest stronger audible sidechain-style ducking. |
| `sidechainDetail.pumpingRegularity` | `float` | Period consistency of detected pumping intervals. | 0.0-1.0 | High values indicate clock-like pumping, useful for genre-consistent groove reconstruction. |
| `sidechainDetail.pumpingRate` | `"quarter" \| "eighth" \| "sixteenth" \| "thirty_second" \| null` | Best-matching pumping grid rate. | categorical | Suggests compressor trigger rhythm for Ableton sidechain setup. `thirty_second` added in Phase 1.C #6 (32nd-note grid). |
| `sidechainDetail.pumpingConfidence` | `float` | Reliability score (kick clarity + dip correlation + timing stability penalties). | 0.0-1.0 | Low confidence means avoid overcommitting to sidechain recreation without ear-checking. |
| `sidechainDetail.envelopeShape` | `float[16] \| null` | Normalized median RMS envelope across bars at 16th-note resolution (downsampled from the internal 32nd-note grid via max-pairing). | 0-1 per step | Rhythmic amplitude shape useful for sidechain curve recreation; peak at step 0 typically indicates kick position. |
| `sidechainDetail.envelopeShape32` | `float[32] \| null` | Normalized median RMS envelope across bars at 32nd-note resolution (added Phase 1.C #6). | 0-1 per step | Higher-resolution view of the same sidechain ducking pattern — exposes attack/release within the 16th-note slot. Prefer this over `envelopeShape` for Auto Filter/Auto Pan rate inference. |

### `reverbDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `reverbDetail.rt60` | `float \| null` | Mean RT60 estimate (-60 dB decay time) across detected transients. | seconds, capped at 3.0 | Quick "wet/dry" proxy at the bus level. `null` when fewer than 4 transients (no decay slopes to fit). |
| `reverbDetail.isWet` | `bool` | True when mean RT60 > 0.5 s. | boolean | Categorical "this material has measurable reverb" flag. Use to gate Reverb/Convolution recommendations vs dry-source advice. |
| `reverbDetail.tailEnergyRatio` | `float \| null` | Mean fraction of total post-transient energy that lives in the tail vs direct portion. | 0-1 | Higher = wetter; useful for deciding wet/dry mix percentage when recreating the reverb. |
| `reverbDetail.measured` | `bool` | Whether enough transients were detected to actually fit RT60 slopes. | boolean | If `measured` is False, all other fields are fallbacks — don't cite RT60 numbers in this case. |
| `reverbDetail.perBandRt60` | `{low?, lowMids?, highMids?, highs?} \| null` | Phase 1.D #5 — RT60 estimated separately in 4 octave bands (low ≈ 20-250 Hz, lowMids ≈ 250-2000 Hz, highMids ≈ 2000-8000 Hz, highs ≈ 8000-16000 Hz). Each band measures the same transient stream. | seconds | Long lows / short highs is a typical room signature; long highs / short lows suggests plate or bright chamber. Use to choose Reverb device type (Hall vs Plate vs Room) and damping. |
| `reverbDetail.preDelayMs` | `float \| null` | Phase 1.D #5 — median time between direct peak and first envelope minimum within the next 100 ms, across all detected transients. | milliseconds | A proxy for reverb pre-delay; close to zero on dry sources. Cite for Reverb device PreDelay parameter recommendations. |

### `vocalDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `vocalDetail.hasVocals` | `bool` | Categorical decision: true when composite confidence > 0.55. | boolean | Use to gate vocal-bus recommendations vs instrumental ones. |
| `vocalDetail.confidence` | `float` | Composite 35/35/30 weighting of energy / formant / MFCC scores, scaled by stemEnergyRatio when a vocals stem is present. | 0.0-1.0 | Hedge any vocal claim when confidence < 0.7. |
| `vocalDetail.vocalEnergyRatio` | `float` | Fraction of spectral energy in 150-1500 Hz vocal fundamental band. | 0.0-1.0 | Higher = more energy in the vocal range. Common on vocal-led tracks (0.25-0.45). |
| `vocalDetail.formantStrength` | `float` | Coherent-formant-frames fraction × temporal-stability multiplier. Penalizes sustained synth leads with static "formants". | 0.0-1.0 | Real vocals usually 0.4-0.8; sustained synth leads should land at 0.2 due to the static-formant penalty. |
| `vocalDetail.mfccLikelihood` | `float` | How closely the MFCC distribution matches a 40/35/25 low/mid/high voice-like profile. | 0.0-1.0 | Hint-only. Can score high on sustained tonal content; don't rely on this alone. |
| `vocalDetail.stemEnergyRatio` | `float \| null` | Phase 1.D follow-up: vocals-stem RMS / full-mix RMS. Null when no vocals stem was used (full-mix path). | 0.0-2.0 typical, capped at 2.0 | Below ~0.05 indicates Demucs ghost-stem leakage on an instrumental track; analyzer scales confidence down accordingly. Phase 2 should hedge vocal claims when this value is low. |
| `vocalDetail.stemOtherCorrelation` | `float \| null` | Phase 1.D follow-up: Pearson correlation between vocals stem and "other" stem at 200 Hz envelope rate. Null when no vocals stem was used. | -1.0 to 1.0 | Above ~0.55 indicates Demucs split a single melodic source across both stems (misclassified lead); analyzer scales confidence down. Below ~0.30 indicates independent stems — no penalty. Phase 2 should hedge vocal-bus claims when this is high. |

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
| `transcriptionDetail.perStemAverageConfidence` | `object` | Mean confidence per stem source, computed over the retained post-dedup, post-cap notes whose `stemSource` matches each key. Empty (`{}`) when `fullMixFallback` is `true`; otherwise contains one entry per stem with at least one surviving note (e.g. `{"bass": 0.85, "other": 0.32}`). | mapping of stem name to 0.0-1.0 confidence | Lets the UI show a separate confidence band when the producer toggles the stem filter — a Solid bass stem shouldn't be hidden behind a Rough lead stem (or vice versa). |
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
| `chordDetail.chordTimeline` | `array<{startSec, endSec, label, labelLong, confidence}> \| null` | Phase 1.D #2 — chord segments with start/end times (seconds), short-form `label` (`"Cm"`, `"Eb"`, `"N"` no-chord), long-form `labelLong` (`"C minor"`, `"Eb major"`, `"N"`), and per-segment confidence. State path decoded by Viterbi over the L1 mass-overlap of `librosa.feature.chroma_cqt` against a 25-state vocabulary (12 major + 12 minor triads + 1 no-chord). Confidence is mean L2 cosine similarity between the chroma and the winning state's template across the segment's frames — bounded [0, 1], where 0.5 is the noise floor and 0.7+ indicates a clean chord match. Segments shorter than 250 ms are dropped; low-confidence "N" segments (<0.4) are also dropped as transition artifacts. Capped at 64 segments. | seconds; 0-1 confidence | Use for arrangement-aware harmonic recommendations ("the bridge sits on Cm for 8 bars, then drops to Eb for 4 — recommend a chord-stab MIDI sequence that matches the timeline"). When `confidence < 0.5` on a segment, hedge — chord detection on full-mix electronic material is noisy. |
| `chordDetail.chordTimelineSource` | `string` | Phase 1.D #2 — identifier of the engine that produced `chordTimeline`. Currently always `"librosa_viterbi"`. Future-proofs swapping engines. | categorical | Phase 2 should hedge if this is anything other than the engine the prompt is calibrated against. |
| `chordDetail.chordTimelineAgreement` | `boolean \| null` | Phase 1.D #2 — `true` when the most-frequent non-"N" Viterbi label in `chordTimeline` matches Essentia's `dominantChords[0]` after enharmonic normalization (`D# ↔ Eb`, `F# ↔ Gb`, etc.). `null` when either source has no usable label. | boolean | Strong hedging signal. When `false`, the two chord engines disagree — describe the harmonic content as uncertain and cite both readings. When `true`, you can commit to the timeline reading. |
| `chordDetail.chordTimeline[].labelLong` | `string` | Long-form chord label paired with the short-form `label`: `"C major"`, `"F# minor"`, `"N"`. | chord labels | Use when a recommendation reads better with human-readable harmonic citations. |
| `chordDetail.chordChangeCount` | `int` | Phase 1.D #2 — count of unique chord-to-chord transitions in the Viterbi-decoded timeline. Flat 1-chord tracks score 0; harmonically active tracks score 16+. | count | A proxy for "how harmonically active" the track is. Cite for arrangement-density and harmonic-rhythm recommendations. |

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
| `arrangementDetail.noveltyCurve` | `float[]` | Downsampled novelty timeline (max 256 points as of Phase 1.A.5; was 64 previously) from Bark-band change detection. | relative novelty units | Highlights where timbral/energy surprises occur (risers, transitions, filter moves). Higher resolution lets Phase 2 cite "novelty ramps for 8 bars before the drop" rather than just naming peaks. |
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

## Detection analyzers (additional sections — added in JSON_SCHEMA.md reconciliation pass)

### `acidDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `acidDetail.isAcid` | `bool` | Categorical "this track sounds like acid-style synthesis" flag. | boolean | When True, recommend resonant filter modulation (Auto Filter with high resonance + LFO automation) on the bass-like element. |
| `acidDetail.confidence` | `float` | Composite confidence in the acid-detection decision. | 0.0-1.0 | Hedge when confidence < 0.5; cite the resonanceLevel + centroidOscillationHz scalars in the recommendation reason. |
| `acidDetail.resonanceLevel` | `float` | Mean spectral-centroid oscillation amplitude proxy. | 0.0-1.0 | High values indicate strong filter sweep; cite for Auto Filter Q recommendations. |
| `acidDetail.centroidOscillationHz` | `float` | Dominant frequency of centroid modulation. | Hz | Cite for LFO rate recommendations on the filter cutoff (e.g. "the centroid oscillates at 97 Hz → set Auto Filter LFO rate to match"). |
| `acidDetail.bassRhythmDensity` | `float` | Onset events per second in the bass-energy band. | events/s | Cross-reference with `kickDetail.kickCount / durationSeconds` — high bassRhythmDensity + low kickCount = acid line driving the rhythm. |

### `bassDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `bassDetail.fundamentalHz` | `int \| null` | Estimated bass fundamental via ZCR on the 150 Hz lowpassed signal. **Approximation: ZCR/2 equals f₀ only for pure sinusoids. Harmonic-rich basses (e.g. a 35 Hz sub with strong 70 Hz second-harmonic energy) bias upward — prefer `pitchDetail` when stems are available.** | Hz, clamped to 30-120 | Cite for Operator/Wavetable Coarse tuning; cross-reference with `key` to determine the bass note. Avoid driving a narrow filter Q within ±15 Hz of this value without corroborating evidence from `pitchDetail`. |
| `bassDetail.averageDecayMs` | `int \| null` | Mean decay time per detected bass transient (peak-anchored envelope decay to -6 dB). | milliseconds | Drives bass-type categorization. Cite for Glue Compressor release-time. <100 ms = punchy; 100-300 = medium; 300-600 = rolling; 600+ = sustained. |
| `bassDetail.type` | `"punchy" \| "medium" \| "rolling" \| "sustained"` | Categorical bass character derived from `averageDecayMs`. | categorical | Drives device-choice direction: punchy → kick-bus-style compression; sustained → Glue Compressor with longer release. |
| `bassDetail.transientCount` | `int` | Number of detected bass onsets. | count | A bass density proxy. |
| `bassDetail.transientRatio` | `float` | Ratio of transient-window energy to total bass-band energy. | 0.0-1.0 | High values = punchy/staccato; low values = sustained pad-like bass. |
| `bassDetail.swingPercent` | `int` | Swing inferred from bass onset-interval alternation (lag-1 autocorr). | 0-50 | Cite for Ableton Groove pool swing % when adding humanization to a re-built MIDI bass. |
| `bassDetail.grooveType` | `"straight" \| "slight-swing" \| "heavy-swing" \| "shuffle"` | Categorical groove derived from `swingPercent`. | categorical | Drives MIDI-quantize humanize amount. |

### `kickDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `kickDetail.fundamentalHz` | `int \| null` | Estimated kick fundamental from sub-bass spectral peak detection. | Hz, typically 30-120 | Cite for Operator/Wavetable kick-tone selection. <60 Hz = deep sub kick; 60-90 Hz = standard 909-ish; 90+ Hz = high-tuned kick. |
| `kickDetail.kickCount` | `int` | Count of detected kick events (preferentially on the drums stem when stems are available). | count | Cross-check density vs BPM. On full mix this can over-count due to bass/transient bleed; on `drums` stem the count is more reliable. |
| `kickDetail.thd` | `float \| null` | Total harmonic distortion proxy for the kick hits. | 0.0-1.0+ | Cite for Saturator drive recommendations. >0.2 indicates audible saturation. |
| `kickDetail.harmonicRatio` | `float \| null` | Harmonic-to-noise ratio across detected kicks. | 0.0-1.0 | High values (>0.9) indicate clean/sub-heavy kicks; low values indicate noisy/punchy kicks with snap content. |
| `kickDetail.isDistorted` | `bool` | True when THD exceeds a threshold + harmonic spread is broad. | boolean | Hint-only; cite for "the kick is already saturated — don't add more Saturator." |

### `supersawDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `supersawDetail.isSupersaw` | `bool` | Categorical "stacked-detuned-saws" presence. | boolean | When True, recommend Wavetable in Supersaw / Sawtooth mode with the measured voiceCount + detuneCents. |
| `supersawDetail.confidence` | `float` | Composite confidence. | 0.0-1.0 | Hedge when below 0.5. |
| `supersawDetail.voiceCount` | `int` | Estimated unison voice count via near-unison peak grouping. | count | Cite directly for Wavetable Voice Stack value (typically 5-7). |
| `supersawDetail.avgDetuneCents` | `float` | Mean detune spread of detected unison voices. | cents | Cite for Wavetable Detune amount in cents. |
| `supersawDetail.spectralComplexity` | `float` | Per-frame peak-count proxy for harmonic richness. | unitless | High values support the supersaw classification; cite alongside `voiceCount`. |

### `genreDetail`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `genreDetail.genre` | `string` | Predicted primary genre from heuristic signature matching. | label | Treat as context only — Phase 2 invariant says genre is short context, not the main blueprint. |
| `genreDetail.confidence` | `float` | Match-score against the predicted genre signature. | 0.0-1.0 | Genre detection on electronic music is noisy; hedge when below 0.7. |
| `genreDetail.secondaryGenre` | `string` | Second-best signature match. | label | Use to triangulate when primary is borderline — e.g. "psytrance + acid-techno" both indicates Goa-style content. |
| `genreDetail.genreFamily` | `string` | Coarse parent family (`trance`, `house`, `hip-hop`, etc.). | label | More stable than the specific genre; safer to anchor recommendations against the family. |
| `genreDetail.topScores` | `array<{genre, score}>` | Top-5 candidate scores. | (label, 0.0-1.0) | Surface as alternates when primary confidence is below 0.7. |

## Danceability

### `danceability`

Type: `object \| null`

| Field | Type | Description | Units / Scale | LLM interpretation note |
|---|---|---|---|---|
| `danceability.danceability` | `float` | Danceability score from Essentia. | algorithmic score | Relative groove suitability indicator; compare between tracks more than absolute targets. |
| `danceability.dfa` | `float` | DFA exponent returned by danceability algo. | exponent | Rhythmic complexity/structure indicator; useful for groove simplification decisions. |

---

## Optional MT3 Namespace

`transcription.mt3` is an *additive*, opt-in polyphonic-transcription
namespace, produced by Magenta's MT3 (Multi-Task Multitrack Music
Transcription) checkpoint via [`mt3_transcription.py`](./mt3_transcription.py).
It is **purely additive to Phase 1** — it does NOT override or refine
Essentia chord/key/beat/melody outputs (PURPOSE.md invariant #1, "Phase 1
measurements are ground truth"). Phase 2 may *read* it for richer note
context, but Phase 1's authoritative measurements remain the ground truth.

### Two emission paths

MT3 reaches clients through one of two paths:

1. **Staged runtime** (production path). MT3 runs as its own stage in
   [`analysis_runtime.py`](./analysis_runtime.py), peer to
   `pitch_note_translation`. Opt in via the `mt3_mode=enabled` form
   field on `POST /api/analysis-runs`, or enqueue after-the-fact via
   `POST /api/analysis-runs/{run_id}/mt3-transcriptions`. The stage
   result lives on `snapshot.stages.mt3.result`. MIDI bytes are
   persisted as per-stem artifacts; the result carries `midiArtifactId`
   + `midiSizeBytes` per track (see "Schema" below).

2. **Direct CLI** (legacy / one-off). Running
   `./venv/bin/python analyze.py <file>` with `ASA_ENABLE_MT3=1` set
   inlines MT3 results under a top-level `transcription` key in stdout
   JSON. In this path each track carries an inline `midiB64` base64
   blob rather than an artifact ref — the CLI has no artifact store.
   **Not used by the staged runtime** (which never exports the env var
   to the subprocess); `analysis_runtime.complete_measurement()` defensively
   pops `transcription` from the measurement-stage result so an operator
   who exports the env var globally cannot leak it into the
   `stages.measurement` payload.

Presence contract (load-bearing):

- For the **staged runtime path**, `snapshot.stages.mt3` is always
  present with a status field; it sits at `not_requested` when
  `mt3_mode='off'` (the default).
- For the **direct CLI path**, the entire `transcription` key is
  **absent from the JSON output** unless `ASA_ENABLE_MT3=1` AND the MT3
  extra is installed AND the call succeeds.
- The key is NOT in `EXPECTED_TOP_LEVEL_KEYS` (the shared full/fast
  schema test) by design — adding it there would force the field to
  always appear in CLI output, breaking the "absent when off" contract.
- Fast mode (`--fast`) never emits the key (the fast pipeline builds
  its own output dict separately, bypassing the MT3 hook entirely).
- The `--pitch-note-only` subprocess mode exits before reaching the
  MT3 hook, so the staged pitch/note translation request path is
  unaffected.

### One-time host setup (not run in CI)

```bash
./apps/backend/venv/bin/pip install -r apps/backend/requirements-mt3.txt
mkdir -p apps/backend/models/mt3
gsutil -m cp -r gs://mt3/checkpoints/mt3 apps/backend/models/mt3/

# Staged runtime usage (per-run opt-in via the HTTP route):
curl -X POST http://127.0.0.1:8100/api/analysis-runs \
  -F track=@<audio.flac> -F mt3_mode=enabled

# Direct CLI usage (legacy):
export ASA_ENABLE_MT3=1
./venv/bin/python analyze.py <audio.flac> --yes
```

### Schema (staged runtime — `snapshot.stages.mt3.result`)

| Field | Type | Description |
|---|---|---|
| `version` | `string` | Pinned identifier — format `"mt3-py-<module-version>+<checkpoint-id>"`, e.g. `"mt3-py-0.1.0+magenta-mt3-base"`. Phase 2 reads this verbatim to know what produced the notes. |
| `stemsUsed` | `string[]` | Stems MT3 actually transcribed. Values are Demucs canonical names (`"bass"`, `"other"`, `"vocals"`) or `["full_mix"]` when no stems were provided. |
| `tracks` | `Mt3Track[]` | One track per stem MT3 successfully processed. May be shorter than `stemsUsed` if a per-stem failure was caught and logged. |
| `tracks[*].instrument` | `string` | Stem name (matches one entry in `stemsUsed`). |
| `tracks[*].midiArtifactId` | `string \| null` | Artifact ID for the per-stem MIDI bytes. Fetch via `GET /api/analysis-runs/{run_id}/artifacts/{midiArtifactId}` (mime `audio/midi`). Null only when the track had no MIDI body (defensive — should not happen in practice). |
| `tracks[*].midiSizeBytes` | `int` | Size of the MIDI artifact in bytes. |
| `tracks[*].noteCount` | `int` | Number of notes in the decoded MIDI. |
| `tracks[*].pitchRange` | `[int, int]` | `[minMidi, maxMidi]` across all notes in this track. `[0, 0]` when empty. |

### Direct CLI shape difference

When the legacy `ASA_ENABLE_MT3=1` env-var path runs, each track carries
an inline `midiB64: string` (base64-encoded MIDI bytes) instead of the
artifact-ref pair. The staged-runtime executor in
[`server.py::_execute_mt3_attempt`](./server.py) reads that `midiB64`,
writes the bytes as a `mt3_track_<instrument>` artifact, and rewrites
the track with `midiArtifactId` + `midiSizeBytes` before persisting.
This is the intentional cross-layer mapping — Python and TS describe
the same per-stem concept at different layers.

LLM interpretation note: MT3 is a multi-instrument AMT system trained
on polyphonic material. Treat MIDI output as a *transcription hint*
layered on top of Phase 1, not a substitute for the deterministic
measurements. Do not "vote" between MT3 notes and Phase 1's chord/key
estimates — Phase 1 wins by invariant.

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

# Plan: Phase 1 Hardening

Pass all measurements through the pipeline, add DSP extensions, expose everything in the UI.

The DSP engine (analyze.py) computes ~41 feature functions via Essentia, producing a comprehensive JSON blob. server.py's `_build_phase1()` function drops 6 fields before sending to the frontend. The UI then only renders about half of what arrives. This plan fixes both leaks and adds 7 DSP extensions that are achievable with the existing Essentia/NumPy stack.

Read PURPOSE.md before starting. Every change must serve the mission: helping an intermediate Ableton producer answer "how do I make something that sounds like this?"

## Scope
- In: server.py pass-through fix, analyze.py DSP extensions, types.ts strong typing, 8-section grouped UI, JSON_SCHEMA.md updates
- Out: Phase 2 prompt updates, UI polish/design, AnalysisStatusPanel copy cleanup, new ML dependencies

## Decisions (resolved with project owner)
- Key profile: `edma` as primary (electronic music corpus-derived, from Essentia's Key algorithm)
- Beat-synchronous loudness: backend computes summary stats (kick-dominant ratio, bass-dominant ratio per beat) and exposes full raw per-beat-per-band matrix behind a debug/dev flag
- Phrase grid: works on downbeats regardless of time signature — grouping downbeats is just arithmetic on timestamps, not a time-signature-dependent operation
- Ableton recommendations: all for Live 12 Standard edition (Roar, Meld, Granulator III are Suite-only extras)

---

## Task 1: Unblock server.py — pass all 6 dropped fields

**File:** `apps/backend/server.py`, function `_build_phase1()` (line 434)

**What:** The function explicitly constructs a dict of fields to return. 6 fields that analyze.py produces are absent from this dict. Add them.

**Add these 6 lines** to the return dict in `_build_phase1()`:

```python
"bpmPercival": _coerce_nullable_number(payload.get("bpmPercival")),
"bpmAgreement": payload.get("bpmAgreement"),  # bool | None
"sampleRate": payload.get("sampleRate"),  # int | None
"dynamicSpread": _coerce_nullable_number(payload.get("dynamicSpread")),
"segmentStereo": payload.get("segmentStereo"),  # array | None
"essentiaFeatures": payload.get("essentiaFeatures"),  # object | None
```

Place them logically: `bpmPercival`/`bpmAgreement` after `bpmConfidence`, `sampleRate` after `durationSeconds`, `dynamicSpread` after `crestFactor`, `segmentStereo` near `segmentSpectral`, `essentiaFeatures` after `perceptual`.

**Also update** `apps/backend/ARCHITECTURE.md` and the `CLAUDE.md` section that says "these raw analyzer fields are present in CLI output but not exposed over HTTP" — remove those 6 fields from the exclusion list and note they are now exposed.

**Test:** `./venv/bin/python -m unittest tests.test_server` — existing server contract tests must still pass, and any tests that assert the exact shape of phase1 response need updating to include the new fields.

---

## Task 2: Extend analyze.py — EDM key profile + tuning frequency

**File:** `apps/backend/analyze.py`, function `analyze_key()` (line 611)

**Current code:**
```python
def analyze_key(mono: np.ndarray) -> dict:
    try:
        extractor = es.KeyExtractor(profileType="temperley")
        key, scale, strength = extractor(mono)
        key_str = f"{key} {scale.capitalize()}"
        return {"key": key_str, "keyConfidence": round(float(strength), 2)}
```

**Change to:**
```python
def analyze_key(mono: np.ndarray) -> dict:
    try:
        extractor = es.KeyExtractor(profileType="edma")
        key, scale, strength = extractor(mono)
        key_str = f"{key} {scale.capitalize()}"

        # Tuning frequency estimation
        tuning_freq = None
        try:
            equal_loudness = es.EqualLoudness()
            el_audio = equal_loudness(mono)
            tuning_algo = es.TuningFrequency()
            tuning_freq_val, tuning_cents = tuning_algo(
                es.SpectralPeaks()(es.Spectrum()(es.Windowing(type="hann")(el_audio[:min(len(el_audio), 44100 * 10)])))
            )
            tuning_freq = round(float(tuning_freq_val), 2)
        except Exception as e:
            print(f"[warn] Tuning frequency estimation failed: {e}", file=sys.stderr)

        return {
            "key": key_str,
            "keyConfidence": round(float(strength), 2),
            "keyProfile": "edma",
            "tuningFrequency": tuning_freq,
        }
    except Exception as e:
        print(f"[warn] Key extraction failed: {e}", file=sys.stderr)
        return {"key": None, "keyConfidence": None, "keyProfile": "edma", "tuningFrequency": None}
```

**IMPORTANT:** The tuning frequency extraction above is a sketch. Essentia's `TuningFrequency` expects spectral peaks (frequencies + magnitudes). The correct approach is:

1. Compute spectrum frames using FrameGenerator
2. Extract SpectralPeaks per frame
3. Feed to TuningFrequency
4. Average across frames

Look at how `analyze_spectral_detail()` (line 898) already does frame-by-frame spectral analysis for the correct pattern. Or simpler: Essentia's `KeyExtractor` with `tuningFrequency=0` will auto-estimate tuning internally — check if there's a way to read the estimated tuning back from the algorithm. If not, compute it separately using the frame-by-frame pattern from analyze_spectral_detail.

**New output fields:** `keyProfile` (string, always "edma"), `tuningFrequency` (float | null, Hz, expected ~440.0 for standard tuning)

---

## Task 3: Extend analyze.py — LUFS momentary + short-term max

**File:** `apps/backend/analyze.py`, function `analyze_loudness()` (line 623)

**Current code:**
```python
def analyze_loudness(stereo: np.ndarray) -> dict:
    try:
        loudness = es.LoudnessEBUR128()
        momentary, short_term, integrated, loudness_range = loudness(stereo)
        return {
            "lufsIntegrated": round(float(integrated), 1),
            "lufsRange": round(float(loudness_range), 1),
        }
```

The `momentary` and `short_term` variables are **arrays** of per-frame loudness values. They are already computed on line 627 but immediately discarded. Extract the max of each.

**Change to:**
```python
def analyze_loudness(stereo: np.ndarray) -> dict:
    try:
        loudness = es.LoudnessEBUR128()
        momentary, short_term, integrated, loudness_range = loudness(stereo)

        # Max momentary (400ms window) and max short-term (3s window)
        momentary_arr = np.asarray(momentary, dtype=np.float64)
        short_term_arr = np.asarray(short_term, dtype=np.float64)
        lufs_momentary_max = round(float(np.max(momentary_arr)), 1) if momentary_arr.size > 0 else None
        lufs_short_term_max = round(float(np.max(short_term_arr)), 1) if short_term_arr.size > 0 else None

        return {
            "lufsIntegrated": round(float(integrated), 1),
            "lufsRange": round(float(loudness_range), 1),
            "lufsMomentaryMax": lufs_momentary_max,
            "lufsShortTermMax": lufs_short_term_max,
        }
    except Exception as e:
        print(f"[warn] LUFS extraction failed: {e}", file=sys.stderr)
        return {"lufsIntegrated": None, "lufsRange": None, "lufsMomentaryMax": None, "lufsShortTermMax": None}
```

**New output fields:** `lufsMomentaryMax` (float | null, LUFS), `lufsShortTermMax` (float | null, LUFS)

**Add to `_build_phase1()` in server.py:**
```python
"lufsMomentaryMax": _coerce_nullable_number(payload.get("lufsMomentaryMax")),
"lufsShortTermMax": _coerce_nullable_number(payload.get("lufsShortTermMax")),
```

---

## Task 4: Extend analyze.py — tempo stability, phrase grid, beat-synchronous loudness

**File:** `apps/backend/analyze.py`, function `analyze_rhythm_detail()` (line 1170)

### 4a: Tempo stability

The function already computes `groove` as `std(intervals) / mean(intervals)`. Add an explicit `tempoStability` metric — the inverse concept: how stable is the tempo. Use the same interval data.

**Add to the return dict of `analyze_rhythm_detail()`:**
```python
"tempoStability": round(float(np.clip(1.0 - groove, 0.0, 1.0)), 4),
```

This is just `1.0 - grooveAmount`, so when groove is low (tight grid), stability is high. Simple, but now it's an explicit field Phase 2 can reference.

### 4b: Phrase grid

**Add after the downbeats computation** (line 1193):
```python
# Phrase grid: group downbeats into 4-bar, 8-bar, 16-bar phrases
phrase_grid = None
if len(downbeats) >= 2:
    phrases_4bar = []
    phrases_8bar = []
    phrases_16bar = []
    for i in range(0, len(downbeats), 4):
        end_idx = min(i + 4, len(downbeats) - 1)
        if i < len(downbeats):
            phrases_4bar.append(round(float(downbeats[i]), 3))
    for i in range(0, len(downbeats), 8):
        if i < len(downbeats):
            phrases_8bar.append(round(float(downbeats[i]), 3))
    for i in range(0, len(downbeats), 16):
        if i < len(downbeats):
            phrases_16bar.append(round(float(downbeats[i]), 3))
    phrase_grid = {
        "phrases4Bar": phrases_4bar,
        "phrases8Bar": phrases_8bar,
        "phrases16Bar": phrases_16bar,
        "totalBars": len(downbeats),
        "totalPhrases8Bar": len(phrases_8bar),
    }
```

Add `"phraseGrid": phrase_grid` to the return dict.

### 4c: Beat-synchronous loudness summaries

This is the most involved addition. The `_extract_beat_loudness_data()` helper (line 475) already computes per-beat, per-band loudness using Essentia's `BeatsLoudness`. It's called by `analyze_groove()` and `analyze_sidechain_detail()`. We need to expose its output as a first-class measurement.

**Create a new function** after `analyze_rhythm_detail()`:

```python
def analyze_beats_loudness(
    mono: np.ndarray,
    sample_rate: int = 44100,
    rhythm_data: dict | None = None,
    beat_data: dict | None = None,
) -> dict:
    """Beat-synchronous loudness summaries and optional raw matrix."""
    try:
        if beat_data is None:
            beat_data = _extract_beat_loudness_data(mono, sample_rate, rhythm_data)
        if beat_data is None:
            return {"beatsLoudness": None}

        beat_loudness = np.asarray(beat_data.get("beatLoudness", []), dtype=np.float64)
        low_band = np.asarray(beat_data.get("lowBand", []), dtype=np.float64)
        high_band = np.asarray(beat_data.get("highBand", []), dtype=np.float64)
        if beat_loudness.size < 2:
            return {"beatsLoudness": None}

        mean_total = float(np.mean(beat_loudness))
        mean_low = float(np.mean(low_band)) if low_band.size > 0 else 0.0
        mean_high = float(np.mean(high_band)) if high_band.size > 0 else 0.0

        kick_dominant_ratio = mean_low / (mean_total + 1e-9) if mean_total > 0 else 0.0
        high_dominant_ratio = mean_high / (mean_total + 1e-9) if mean_total > 0 else 0.0

        result = {
            "beatsLoudness": {
                "meanBeatLoudness": round(mean_total, 4),
                "meanLowBandLoudness": round(mean_low, 4),
                "meanHighBandLoudness": round(mean_high, 4),
                "kickDominantRatio": round(float(np.clip(kick_dominant_ratio, 0.0, 1.0)), 4),
                "highDominantRatio": round(float(np.clip(high_dominant_ratio, 0.0, 1.0)), 4),
                "beatCount": int(beat_loudness.size),
            }
        }

        # Raw matrix behind dev flag (check env var or CLI flag)
        if os.environ.get("ASA_DEBUG_BEATS_LOUDNESS") == "1":
            result["beatsLoudness"]["rawBeatLoudness"] = [round(float(v), 4) for v in beat_loudness]
            result["beatsLoudness"]["rawLowBand"] = [round(float(v), 4) for v in low_band]
            result["beatsLoudness"]["rawHighBand"] = [round(float(v), 4) for v in high_band]

        return result
    except Exception as e:
        print(f"[warn] Beats loudness analysis failed: {e}", file=sys.stderr)
        return {"beatsLoudness": None}
```

**Add the call** in the main orchestration section (around line 4388, after `beat_data` is computed):
```python
result.update(analyze_beats_loudness(mono, sample_rate, rhythm_data, beat_data))
```

**Add to `_build_phase1()` in server.py:**
```python
"beatsLoudness": payload.get("beatsLoudness"),
```

**New output fields:** `rhythmDetail.tempoStability`, `rhythmDetail.phraseGrid`, `beatsLoudness` (object with summaries)

---

## Task 5: Extend analyze.py — sidechain envelope shape

**File:** `apps/backend/analyze.py`, function `analyze_sidechain_detail()` (line 1656)

The function already computes per-sixteenth-note RMS values (`rms_values` array, line 1726) aligned to beat positions. The envelope shape is there — it's just not returned.

**Add to the return dict** (inside the existing `sidechainDetail` object, around line 1847):

```python
# Beat-synchronous gain envelope: sample one bar's worth of RMS as a normalized shape
envelope_shape = None
if rms_values.size >= 16:
    # Take median shape across bars (each bar = 16 sixteenths)
    n_bars = rms_values.size // 16
    if n_bars >= 1:
        bars_matrix = rms_values[:n_bars * 16].reshape(n_bars, 16)
        median_bar = np.median(bars_matrix, axis=0)
        bar_max = float(np.max(median_bar))
        if bar_max > 0:
            normalized = median_bar / bar_max
            envelope_shape = [round(float(v), 3) for v in normalized]
```

Then add `"envelopeShape": envelope_shape` to the `sidechainDetail` dict that gets returned.

**New output field:** `sidechainDetail.envelopeShape` (float[16] | null — normalized 0-1 gain shape across one bar at sixteenth-note resolution)

---

## Task 6: Strongly type types.ts

**File:** `apps/ui/src/types.ts`, `Phase1Result` interface (line 100)

Replace all `Record<string, unknown>` and `unknown[]` with proper interfaces. Here's what each should become, based on the actual JSON shapes from analyze.py:

```typescript
// Add these interfaces BEFORE Phase1Result

export interface RhythmDetail {
  onsetRate: number;
  beatGrid: number[];
  downbeats: number[];
  beatPositions: number[];
  grooveAmount: number;
  tempoStability: number;  // NEW
  phraseGrid: {             // NEW
    phrases4Bar: number[];
    phrases8Bar: number[];
    phrases16Bar: number[];
    totalBars: number;
    totalPhrases8Bar: number;
  } | null;
}

export interface GrooveDetail {
  kickSwing: number;
  hihatSwing: number;
  kickAccent: number[];
  hihatAccent: number[];
}

export interface EffectsDetail {
  gatingDetected: boolean;
  gatingRate: '16th' | '8th' | 'quarter' | null;
  gatingRegularity: number;
  gatingEventCount: number;
}

export interface StructureSegment {
  start: number;
  end: number;
  index: number;
}

export interface Structure {
  segmentCount: number;
  segments: StructureSegment[];
}

export interface ArrangementDetail {
  noveltyCurve: number[];
  noveltyPeaks: { time: number; strength: number }[];
  noveltyMean: number;
  noveltyStdDev: number;
}

export interface SegmentLoudnessEntry {
  segmentIndex: number;
  start: number;
  end: number;
  lufs: number | null;
  lra: number | null;
}

export interface SegmentStereoEntry {
  segmentIndex: number;
  stereoWidth: number | null;
  stereoCorrelation: number | null;
}

export interface SegmentKeyEntry {
  segmentIndex: number;
  key: string | null;
  keyConfidence: number | null;
}

export interface StereoDetail {
  stereoWidth: number | null;
  stereoCorrelation: number | null;
  subBassCorrelation: number | null;
  subBassMono: boolean | null;
}

export interface PerceptualDetail {
  sharpness: number;
  roughness: number;
}

export interface EssentiaFeatures {
  zeroCrossingRate: number;
  hfc: number;
  spectralComplexity: number;
  dissonance: number;
}

export interface BeatsLoudness {
  meanBeatLoudness: number;
  meanLowBandLoudness: number;
  meanHighBandLoudness: number;
  kickDominantRatio: number;
  highDominantRatio: number;
  beatCount: number;
  rawBeatLoudness?: number[];   // debug only
  rawLowBand?: number[];        // debug only
  rawHighBand?: number[];       // debug only
}
```

**Then update Phase1Result** to use these types + add the new fields:

```typescript
export interface Phase1Result {
  // Core metrics
  bpm: number;
  bpmConfidence: number;
  bpmPercival: number | null;          // UNBLOCKED
  bpmAgreement: boolean | null;        // UNBLOCKED
  key: string | null;
  keyConfidence: number;
  keyProfile: string;                  // NEW
  tuningFrequency: number | null;      // NEW
  timeSignature: string;
  durationSeconds: number;
  sampleRate: number | null;           // UNBLOCKED

  // Loudness & dynamics
  lufsIntegrated: number;
  lufsRange?: number | null;
  lufsMomentaryMax: number | null;     // NEW
  lufsShortTermMax: number | null;     // NEW
  truePeak: number;
  crestFactor?: number | null;
  dynamicSpread: number | null;        // UNBLOCKED
  dynamicCharacter?: { ... } | null;   // keep existing shape

  // Stereo
  stereoWidth: number;
  stereoCorrelation: number;
  stereoDetail?: StereoDetail | null;

  // Spectral
  spectralBalance: { ... };            // keep existing shape
  spectralDetail?: SpectralDetail | null;

  // Rhythm & groove
  rhythmDetail?: RhythmDetail | null;
  grooveDetail?: GrooveDetail | null;
  beatsLoudness?: BeatsLoudness | null;  // NEW
  sidechainDetail?: SidechainDetail | null;  // update to include envelopeShape
  effectsDetail?: EffectsDetail | null;

  // Melody & transcription
  melodyDetail?: MelodyDetail;
  transcriptionDetail?: TranscriptionDetail | null;

  // Harmony
  chordDetail?: ChordDetail | null;
  segmentKey?: SegmentKeyEntry[] | null;

  // Structure & arrangement
  structure?: Structure | null;
  arrangementDetail?: ArrangementDetail | null;
  segmentLoudness?: SegmentLoudnessEntry[] | null;
  segmentSpectral?: SegmentSpectralEntry[] | null;
  segmentStereo?: SegmentStereoEntry[] | null;  // UNBLOCKED

  // Synthesis & timbre
  synthesisCharacter?: SynthesisCharacter | null;
  perceptual?: PerceptualDetail | null;
  essentiaFeatures?: EssentiaFeatures | null;  // UNBLOCKED
  danceability?: DanceabilityResult | null;

  // Detectors (keep existing shapes)
  acidDetail?: { ... } | null;
  reverbDetail?: { ... } | null;
  vocalDetail?: { ... } | null;
  supersawDetail?: { ... } | null;
  bassDetail?: { ... } | null;
  kickDetail?: { ... } | null;
  genreDetail?: { ... } | null;
}
```

Also update `SidechainDetail` to include:
```typescript
export interface SidechainDetail {
  pumpingStrength: number;
  pumpingRegularity: number;
  pumpingRate: 'quarter' | 'eighth' | 'sixteenth' | null;
  pumpingConfidence: number;
  envelopeShape: number[] | null;  // NEW: 16 floats normalized 0-1
}
```

---

## Task 7: Build 8-section grouped UI

**File:** `apps/ui/src/components/AnalysisResults.tsx`

The current UI has: top 4-card grid, spectral balance, optional chord panel, optional detector grid, optional chroma, session musician panel, and Phase 2 sections.

Replace the Phase 1 portion with 8 clearly grouped sections. Each section renders ALL its fields. Start with raw numbers — polish later. The groupings:

### Section 1: Core Metrics
Fields: `bpm`, `bpmConfidence`, `bpmPercival`, `bpmAgreement`, `key`, `keyConfidence`, `keyProfile`, `tuningFrequency`, `timeSignature`, `durationSeconds`, `sampleRate`

### Section 2: Loudness & Dynamics
Fields: `lufsIntegrated`, `lufsRange`, `lufsMomentaryMax`, `lufsShortTermMax`, `truePeak`, `crestFactor`, `dynamicSpread`, `dynamicCharacter` (all 5 sub-fields)

### Section 3: Spectral
Fields: `spectralBalance` (all 6 bands), `spectralDetail` (centroid, rolloff, MFCC, chroma, barkBands, erbBands, spectralContrast, spectralValley). Keep existing SpectralBalanceCurve visualization. Add raw numbers for spectral detail fields not currently shown.

### Section 4: Stereo Field
Fields: `stereoWidth`, `stereoCorrelation`, `stereoDetail` (subBassCorrelation, subBassMono), `segmentStereo` (per-segment width + correlation)

### Section 5: Rhythm & Groove
Fields: `rhythmDetail` (onsetRate, grooveAmount, tempoStability, phraseGrid, beatGrid length, downbeat count), `grooveDetail` (kickSwing, hihatSwing, kickAccent, hihatAccent), `beatsLoudness` (all summary fields), `sidechainDetail` (all fields including envelopeShape), `effectsDetail` (all fields), `danceability` (danceability score, dfa)

### Section 6: Harmony
Fields: `chordDetail` (chordSequence, progression, dominantChords, chordStrength), `segmentKey` (per-segment key + confidence)

### Section 7: Structure & Arrangement
Fields: `structure` (segmentCount, segments), `arrangementDetail` (noveltyCurve, noveltyPeaks, noveltyMean, noveltyStdDev), `segmentLoudness` (per-segment LUFS + LRA)

### Section 8: Synthesis & Timbre
Fields: `synthesisCharacter`, `perceptual`, `essentiaFeatures`, all detector objects (acid, reverb, vocal, supersaw, bass, kick, genre)

**Implementation approach:** Create a new component per section (e.g., `Phase1CoreMetrics.tsx`, `Phase1Loudness.tsx`, etc.) or inline sections. Each section is a titled card with a grid of labeled values. For arrays, show count + first few values. For objects, show all sub-fields as labeled rows. Keep existing visualizations (SpectralBalanceCurve, chroma wheel, piano roll) in their sections but ADD the raw numbers alongside.

Don't remove Phase 2 sections — they stay where they are, after all 8 Phase 1 sections.

---

## Task 8: Update JSON_SCHEMA.md

**File:** `apps/backend/JSON_SCHEMA.md`

Add documentation for all new fields following the existing table format:

| Field | Type | Description | Units / Scale | LLM interpretation note |

New fields to document:
- `keyProfile` — string, always "edma"
- `tuningFrequency` — float | null, Hz
- `lufsMomentaryMax` — float | null, LUFS
- `lufsShortTermMax` — float | null, LUFS
- `rhythmDetail.tempoStability` — float, 0-1
- `rhythmDetail.phraseGrid` — object with phrase arrays
- `beatsLoudness` — object with summary stats
- `sidechainDetail.envelopeShape` — float[16] | null

Update the "Relationship To POST /api/analyze" section to note that `bpmPercival`, `bpmAgreement`, `sampleRate`, `dynamicSpread`, `segmentStereo`, and `essentiaFeatures` are now exposed via HTTP (remove them from the "not present in server phase1 wrapper" list).

---

## Task 9: Update CLAUDE.md

Remove the sentence in the Architecture section that says these fields are "not exposed over HTTP": `bpmPercival`, `bpmAgreement`, `sampleRate`, `dynamicSpread`, `segmentStereo`, `essentiaFeatures`. They are now exposed.

---

## Task 10: Run tests

```bash
# Backend
cd apps/backend && ./venv/bin/python -m unittest discover -s tests

# Frontend
cd apps/ui && npm run verify
```

Fix any failures. The most likely breakages:
- Server tests that assert the exact shape of the phase1 response (need new fields)
- Frontend type-check failures if types.ts changes don't match component usage
- Existing components that destructure Phase1Result may need updates if field names changed (they shouldn't — we're only adding, not renaming)

---

## Execution order

Tasks 1-5 are backend changes. Do them first, in order (1 depends on nothing; 2-5 are independent of each other but all feed into the same result dict). Task 6 (types.ts) depends on knowing the final field shapes from tasks 1-5. Task 7 (UI) depends on task 6. Tasks 8-9 (docs) can happen anytime. Task 10 runs after everything else.

Recommended parallel grouping:
- **Batch A:** Tasks 1, 2, 3, 4, 5 (all backend)
- **Batch B:** Task 6 (types.ts — needs batch A shapes finalized)
- **Batch C:** Task 7 (UI — needs batch B types)
- **Batch D:** Tasks 8, 9, 10 (docs + verification)

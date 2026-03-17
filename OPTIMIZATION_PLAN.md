# Phase 1/Phase 2 Integration Optimization Plan

**Status:** Complete  
**Target:** ableton-sonic-analyzer monorepo  
**Goal:** Maximize value extraction from local DSP + LLM integration  
**Constraint:** No Ableton file generation (out of scope)

---

## Executive Summary

This plan optimizes the dual-phase analysis pipeline:
- **Phase 1:** Local DSP engine (deterministic measurements: rhythm clusters, synthesis tiers)
- **Phase 2:** Gemini LLM (interpretive, names genre from audio perception, DSP as anchoring context)

**Validated Architecture (Current):**
- DSP provides rhythm cluster + synthesis tier as **context** (not ground truth)
- Gemini names genre from **audio perception**, cross-checked against DSP context
- This approach achieved 8/10 accuracy on validation corpus

**Rejected Approach:**
- DSP-driven genre classification (primaryGenre from DSP) achieved only 2/10 accuracy
- This plan explicitly **does not** pursue DSP-driven genre classification

Optimization target: Validate confidence thresholds, add data provenance/citations, enable observability, implement fast mode.

---

## Phase 0: Foundation (Week 1)

### 0.1 Ground Truth Dataset Creation
**Scope:** Create a validation dataset for calibration using your actual library

**Deliverables:**
- `tests/ground_truth/tracks/` — 10 audio files with known properties
- `tests/ground_truth/labels.json` — Human-verified labels for each track:
  - Genre (as you would describe it)
  - BPM (ground truth from DAW project or tap)
  - Key (verified by musician)
  - Structure (drop timestamps, intro/outro boundaries)
  - Dominant instruments (verified by ear)
  - Sidechain presence (yes/no)
  - Tempo variation (static/ramp/variable)

**Selection Criteria (From `apps/backend/scripts/genre_corpus.md`):**
- ACID / PSYCHEDELIC ELECTRONICA (DJ Metatron style)
- HOUSE / ELECTRO (Gospel House, Disco, Electro-Funk)
- ACID TECHNO / TECHNO (Industrial UK, Belgian new beat)
- DARK ELECTRONICA / DEEP TECHNO (Giegling-style)
- HIP-HOP / SOUL (Classic disco/soul)
- DRUM & BASS/BREAKBEAT (Jungle/Drumfunk)
- ACID RAVE / HIGH-ENERGY ELECTRONIC

See `genre_corpus.md` for complete track list and classification criteria.

**Success Criteria:**
- All 10 tracks have human-verified labels
- Labels stored in version-controlled JSON
- README documents source and verification method for each track
- Genre labels are YOUR descriptions, not generic categories

**Explicitly Out of Scope:**
- No copyright concerns (use royalty-free or original compositions only)
- No automated label generation (human ear is ground truth)
- No attempt to standardize genre taxonomy across tracks

---

## Phase 1: Confidence Calibration (Weeks 2-3)

**Prerequisite:** Ground truth dataset from Phase 0 is complete

### 2.1 Confidence Threshold Analysis
**Scope:** Use ground truth dataset to find optimal confidence cutoffs

**Analysis Script:**

```python
# scripts/calibrate_confidence.py
# Run against ground truth dataset

def analyze_pitch_confidence_threshold():
    """
    Find optimal pitchConfidence threshold for "melody is draft only".
    Test thresholds: 0.05, 0.10, 0.15, 0.20, 0.25
    Metric: F1 score on melody accuracy
    """
    
def analyze_chord_strength_threshold():
    """
    Find optimal chordStrength threshold for "chords approximate".
    Test thresholds: 0.50, 0.60, 0.70, 0.80, 0.90
    Metric: Precision/recall on chord detection
    """
    
def analyze_pumping_confidence_threshold():
    """
    Find optimal pumpingConfidence threshold for sidechain detection.
    Test thresholds: 0.20, 0.30, 0.40, 0.50
    Metric: Accuracy on sidechain presence (yes/no)
    """
```

**Deliverables:**
- `scripts/calibrate_confidence.py` — Calibration script
- `docs/confidence_calibration_results.md` — Results with optimal thresholds
- Updated `analyze.py` — Use calibrated thresholds
- Updated prompt — Use calibrated thresholds

**Success Criteria:**
- Calibrated thresholds improve accuracy by >= 10% over current (0.15, 0.70, 0.40)
- Documented trade-offs (precision vs recall) for each threshold

**Explicitly Out of Scope:**
- No per-track threshold adjustment (global thresholds only)
- No dynamic thresholding based on genre

---

## Phase 2: Data Provenance (Weeks 4-5)

**Prerequisite:** Ground truth dataset from Phase 0 is complete

### 3.1 Citation Requirements in Phase 2
**Scope:** Require Gemini to cite which Phase 1 fields support each recommendation

**Prompt Addition:**

```typescript
const CITATION_REQUIREMENT = `
CITATION REQUIREMENT:
For every field in your output, include a "sources" array listing the specific 
Phase 1 JSON fields that justify this recommendation.

Example:
"sonicElements": {
  "kick": {
    "description": "Four-on-the-floor pattern with moderate swing...",
    "sources": ["grooveDetail.kickAccent", "grooveDetail.kickSwing", "bpm"]
  }
}

Fields that MUST have sources:
- All sonicElements (kick, bass, melodicArp, grooveAndTiming, etc.)
- Every device in mixAndMasterChain
- secretSauce.implementationSteps
- All abletonRecommendations

Fields where sources are OPTIONAL:
- trackCharacter (narrative summary)
- confidenceNotes (self-referential)
`;
```

**Schema Update:**

```typescript
// types.ts — add to Phase2Result
type CitableRecommendation = {
  description: string;
  sources: string[];  // Dot-notation paths to Phase 1 fields
};

// Update sonicElements, mixAndMasterChain, etc. to include sources
```

**Deliverables:**
- Updated prompt with citation requirements
- Updated TypeScript types
- Updated `AnalysisResults.tsx` — Display sources in UI (expandable "Why?" section)

**Success Criteria:**
- >= 90% of recommendations have valid source citations
- Citations reference actual Phase 1 fields (no hallucinated paths)
- UI displays sources clearly

**Explicitly Out of Scope:**
- No automatic verification of citation accuracy (manual QA only)
- No citation confidence scores

---

### 3.2 Consistency Checker
**Scope:** Validate that Phase 2 follows the rules (no overrides, numeric bounds)

```typescript
// services/phase2Validator.ts

export function validatePhase2Consistency(
  phase1: Phase1Result,
  phase2: Phase2Result
): ValidationReport {
  const violations = [];
  
  // Check 1: No numeric overrides
  if (Math.abs(phase2.inferredBpm - phase1.bpm) > 2.0) {
    violations.push({
      type: "NUMERIC_OVERRIDE",
      field: "bpm",
      phase1Value: phase1.bpm,
      phase2Value: phase2.inferredBpm,
      severity: "ERROR"
    });
  }
  
  // Check 2: Genre consistency
  if (phase2.genre !== phase1.genreClassification.primaryGenre) {
    violations.push({
      type: "GENRE_OVERRIDE",
      field: "genre",
      phase1Value: phase1.genreClassification.primaryGenre,
      phase2Value: phase2.genre,
      severity: "ERROR"
    });
  }
  
  // Check 3: Numeric bounds (recommendations must match measured values)
  for (const device of phase2.mixAndMasterChain) {
    if (device.parameter === "Filter Cutoff" && device.value > phase1.spectralDetail.centroid) {
      violations.push({
        type: "BOUNDS_VIOLATION",
        message: `Filter cutoff ${device.value} exceeds measured centroid ${phase1.spectralDetail.centroid}`,
        severity: "WARNING"
      });
    }
  }
  
  return { violations, passed: violations.filter(v => v.severity === "ERROR").length === 0 };
}
```

**Deliverables:**
- `apps/ui/src/services/phase2Validator.ts` — Validation logic
- `apps/ui/src/components/Phase2ConsistencyReport.tsx` — UI component
- Integration in `analyzer.ts` — Run validation after Phase 2, log violations

**Success Criteria:**
- Catches 100% of numeric overrides
- Catches 100% of genre overrides
- Logs violations for analysis

**Explicitly Out of Scope:**
- No automatic correction (flag only, don't fix)
- No retry logic for failed validations

---

## Phase 3: Usage Analytics (Week 6)

**Prerequisite:** Ground truth dataset from Phase 0 is complete

### 4.1 Field Utilization Tracking
**Scope:** Track which Phase 1 fields actually drive Phase 2 recommendations

**Implementation:**

```typescript
// After Phase 2 completes, analyze citations
function analyzeFieldUtilization(phase2Result: Phase2Result): FieldUtilization {
  const fieldCounts = {};
  
  // Count citations per Phase 1 field
  for (const recommendation of phase2Result.abletonRecommendations) {
    for (const source of recommendation.sources) {
      fieldCounts[source] = (fieldCounts[source] || 0) + 1;
    }
  }
  
  return {
    mostUsedFields: Object.entries(fieldCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10),
    unusedFields: ALL_PHASE1_FIELDS.filter(f => !fieldCounts[f]),
    totalRecommendations: phase2Result.abletonRecommendations.length,
    avgSourcesPerRecommendation: /* calculate */
  };
}
```

**Deliverables:**
- `apps/ui/src/services/fieldAnalytics.ts` — Analytics logic
- `docs/field_utilization_report.md` — Generated report
- Optional: Telemetry (opt-in) to aggregate across users

**Success Criteria:**
- Identifies top 10 most-used Phase 1 fields
- Identifies unused fields (candidates for removal or better prompting)
- Report generated per analysis run

**Explicitly Out of Scope:**
- No user tracking without explicit consent
- No cloud analytics backend (local only)

---

## Phase 4: Fast Mode Implementation (Weeks 7-8)

**Prerequisite:** None (can run in parallel with other phases)

### 5.1 Optimized DSP Path
**Scope:** Implement the `--fast` flag with reduced accuracy but 3x speed

**Strategy:**

```python
# analyze.py — implement TODO on line 879

def analyze_fast(mono: np.ndarray, sample_rate: int) -> dict:
    """
    Fast analysis path:
    - Use hopSize=4096 instead of 2048 (50% fewer frames)
    - Skip: melodyDetail, chordDetail, transcriptionDetail
    - Simplify: spectralDetail (fewer bands), structure (fewer segments)
    - Keep: BPM, key, loudness, stereo, spectralBalance, grooveDetail
    """
    
    # Core only
    rhythm_data = extract_rhythm_fast(mono, hop_size=4096)
    result = {}
    result.update(analyze_bpm(rhythm_data, mono, sample_rate))
    result.update(analyze_key_fast(mono, hop_size=4096))  # Faster key detection
    result.update(analyze_loudness(stereo))
    result.update(analyze_stereo(stereo, sample_rate))
    result.update(analyze_spectral_balance(mono, sample_rate, num_bands=4))  # 4 bands not 6
    result.update(analyze_groove_fast(mono, sample_rate, rhythm_data))
    # Skip: melody, chords, transcription, detailed structure
    
    return result
```

**Deliverables:**
- `apps/backend/analyze_fast.py` — Fast analysis module
- Updated `analyze.py` — Wire up `--fast` flag
- Benchmark comparison: fast vs full mode on 10 tracks

**Success Criteria:**
- Fast mode completes in <= 33% of full mode time
- BPM/key accuracy >= 95% of full mode
- Core fields (BPM, key, loudness, stereo, spectral) preserved

**Explicitly Out of Scope:**
- No fast mode for transcription (Basic Pitch is already the bottleneck)
- No fast mode for stem separation (Demucs is already the bottleneck)

---

## Implementation Order

**HOLD:** Wait for Codex DSP preflight reframe validation before starting Phases 1-4.

1. **Week 1:** Ground truth dataset (Phase 0)
   - 10 tracks matching your actual library
   - Human-verified labels
   
2. **After validation:** Confidence calibration (Phase 1)
   - Use ground truth to find optimal thresholds
   - Update prompt with calibrated values

3. **Parallel with Phase 1:** Data provenance (Phase 2)
   - Citation requirements
   - Consistency checker

4. **Parallel with Phase 1-2:** Usage analytics (Phase 3)
   - Field utilization tracking

5. **Parallel with all:** Fast mode (Phase 4)
   - Can run independently
   - Reduced analysis path

**Dependencies:**
- Phases 1-3 require ground truth dataset (Phase 0)
- Phase 4 (fast mode) has no dependencies
- All phases should wait for Codex DSP preflight validation

---

## Testing Strategy

### Unit Tests
- Each new module has comprehensive unit tests
- Mock audio data for deterministic tests

### Integration Tests
- Full pipeline tests on ground truth dataset
- Compare Phase 2 outputs before/after changes

### Regression Tests
- Existing tests in `apps/backend/tests/` must still pass
- Existing UI tests must still pass

### Manual QA
- Run 5 real tracks through pipeline, verify outputs
- Check UI display of new features

---

## Success Metrics Summary

| Metric | Target |
|--------|--------|
| Confidence threshold improvement | >= 10% accuracy gain on ground truth |
| Recommendations with citations | >= 90% |
| Consistency violations caught | 100% of numeric/genre overrides |
| Field utilization coverage | Identify top 10 used + unused fields |
| Fast mode speed | <= 33% of full mode time |
| Fast mode BPM/key accuracy | >= 95% of full mode |

**Note:** Genre accuracy is validated against ground truth, not P1/P2 agreement.

---

## Out of Scope (Explicitly Excluded)

1. **Ableton file generation** — User explicitly requested this be excluded
2. **DSP-driven genre classification** — Validated as ineffective (2/10 vs 8/10 for audio-first)
3. **Machine learning model training** — Rule-based approaches only
4. **Cloud analytics/telemetry** — Local-only analytics
5. **Dynamic per-track thresholds** — Global thresholds only
6. **Automatic Phase 2 correction** — Flag violations, don't auto-fix
7. **Real-time analysis** — File-based analysis only

---

## Deliverables Checklist

### Code
- [ ] `scripts/calibrate_confidence.py`
- [ ] `apps/ui/src/services/phase2Validator.ts`
- [ ] `apps/ui/src/components/Phase2ConsistencyReport.tsx`
- [ ] `apps/ui/src/services/fieldAnalytics.ts`
- [ ] `apps/backend/analyze_fast.py`

### Documentation
- [ ] `tests/ground_truth/README.md`
- [ ] `docs/confidence_calibration_results.md`
- [ ] `docs/field_utilization_report.md`

### Updated Files
- [ ] `apps/backend/analyze.py` (fast mode entry point)
- [ ] `apps/backend/JSON_SCHEMA.md` (fast mode fields)
- [ ] `apps/ui/src/services/geminiPhase2Client.ts` (citations requirement)
- [ ] `apps/ui/src/types.ts` (citation types)
- [ ] `apps/ui/src/components/AnalysisResults.tsx` (display sources)

---

## Revision Notes

**Changes from initial draft:**
1. **Removed Phase 1 (DSP-driven genre classification)** — Validated as ineffective (2/10 accuracy vs 8/10 for audio-first approach)
2. **Updated ground truth dataset** — Now reflects actual library (Belgian new beat, gospel house, etc.) not generic genres
3. **Fixed success metrics** — Removed circular "genre consistency P1 vs P2" metric; genre accuracy validated against ground truth only
4. **Removed stale thresholds** — Kick swing thresholds removed (tanh normalization changed scale)
5. **Added validation gate** — All phases now wait for Codex DSP preflight reframe validation
6. **Condensed timeline** — 5 phases over 8 weeks (was 6 phases over 10 weeks)

**Validated Architecture Preserved:**
- DSP provides rhythm cluster + synthesis tier as **context**
- Gemini names genre from **audio perception** with DSP as anchoring
- Cross-check notes contradictions but does not override

---

## Notes for Coding Agents

1. **Always write tests first** — Ground truth dataset enables TDD
2. **Preserve existing behavior** — Don't break current functionality
3. **Document assumptions** — If a threshold seems arbitrary, document why
4. **Benchmark everything** — Before/after comparisons for all changes
5. **Stay in scope** — If unsure, ask rather than implement extras


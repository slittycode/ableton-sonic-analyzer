# Field Utilization Report

Generated: 2026-03-16 14:30:00 UTC

## Summary

- Total Recommendations: **24**
- Avg Sources per Recommendation: **2.30**
- Unused Fields: **11**

## Most Used Fields (Top 10)

| Field | Citations | Categories |
|-------|-----------|------------|
| `bpm` | 12 | SYNTHESIS, EFFECTS, MIDI |
| `key` | 10 | SYNTHESIS, MIDI |
| `lufsIntegrated` | 8 | DYNAMICS, MASTERING |
| `spectralBalance.subBass` | 7 | EQ |
| `grooveDetail.kickAccent` | 6 | DYNAMICS |
| `stereoWidth` | 5 | STEREO, MASTERING |
| `spectralBalance.lowBass` | 4 | EQ |
| `spectralDetail.centroid` | 3 | EQ, SYNTHESIS |
| `durationSeconds` | 2 | ROUTING |
| `truePeak` | 1 | MASTERING |

## Unused Fields

The following Phase 1 fields were never cited in recommendations:

- `bpmConfidence`
- `keyConfidence`
- `timeSignature`
- `lufsRange`
- `crestFactor`
- `stereoDetail.stereoCorrelation`
- `stereoDetail.subBassMono`
- `rhythmDetail.beatInterval`
- `melodyDetail.vibratoExtent`
- `transcriptionDetail.noteCount`
- `sidechainDetail.pumpingConfidence`

## Category Breakdown

### EQ

- Recommendations: **6**
- Avg Sources: **2.50**
- Top Fields: `spectralBalance.subBass`, `spectralBalance.lowBass`, `spectralDetail.centroid`

### DYNAMICS

- Recommendations: **5**
- Avg Sources: **2.20**
- Top Fields: `lufsIntegrated`, `grooveDetail.kickAccent`

### SYNTHESIS

- Recommendations: **4**
- Avg Sources: **2.80**
- Top Fields: `bpm`, `key`, `spectralDetail.centroid`

### EFFECTS

- Recommendations: **3**
- Avg Sources: **2.00**
- Top Fields: `bpm`, `key`

### MASTERING

- Recommendations: **3**
- Avg Sources: **2.30**
- Top Fields: `lufsIntegrated`, `stereoWidth`, `truePeak`

### STEREO

- Recommendations: **2**
- Avg Sources: **2.00**
- Top Fields: `stereoWidth`

### MIDI

- Recommendations: **1**
- Avg Sources: **2.00**
- Top Fields: `bpm`, `key`

## Recommendations

> **Note:** Many Phase 1 fields are unused. Consider:
> - Reviewing prompt engineering to encourage use of these fields
> - Removing unused fields from Phase 1 to reduce processing time
> - Adding field descriptions to help the model understand when to use them

## Actionable Insights

### High-Value Fields (Keep & Emphasize)

These fields drive the most recommendations:

1. **bpm** (12 citations) - Used across SYNTHESIS, EFFECTS, and MIDI categories
2. **key** (10 citations) - Critical for SYNTHESIS and MIDI recommendations
3. **lufsIntegrated** (8 citations) - Essential for DYNAMICS and MASTERING

### Underutilized Fields (Prompt Engineering Opportunities)

These fields have potential but are rarely cited:

- `spectralDetail.centroid` (3 citations) - Could drive more EQ decisions
- `durationSeconds` (2 citations) - Could inform arrangement recommendations
- `truePeak` (1 citation) - Should be used in all MASTERING recommendations

### Candidate Fields for Removal

These fields are never cited and may not be useful:

- Confidence fields (`bpmConfidence`, `keyConfidence`)
- Complex nested fields (`stereoDetail.subBassMono`, `rhythmDetail.beatInterval`)
- Niche analysis fields (`melodyDetail.vibratoExtent`)

Consider removing these from Phase 1 to reduce processing time, or improve prompting to leverage them.

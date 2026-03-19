 Phase 1 Hardening Plan

 Context

 The ASA DSP engine (analyze.py) computes ~41 feature fields but server.py drops 7 of them and the UI renders only ~50% of what arrives. This plan unblocks the full pipeline end-to-end: pass all measurements through, add 6 DSP extensions achievable with existing
 Essentia/NumPy, strongly type the TypeScript contract (eliminating all Record<string, unknown>), and build an 8-section grouped measurement dashboard.

 ---
 Step 1: DSP Extensions in analyze.py

 File: apps/backend/analyze.py

 1a. Key profile switch + tuning frequency

- analyze_key() (line 614): change profileType="temperley" to "edma"
- Add es.TuningFrequency() call on mono signal, return tuningFrequency (Hz) and tuningCents (deviation from A440)
- Also update analyze_segment_key() (line 3516) to use "edma"
- Add tuningFrequency and tuningCents to the root output dict (line 4400+)

 1b. Max momentary + short-term LUFS

- analyze_loudness() (line 627): momentary and short_term arrays are already computed then discarded
- Keep them: lufsMomentaryMax = round(float(np.max(momentary)), 1), same for lufsShortTermMax
- Add both to return dict and root output dict

 1c. Tempo stability

- analyze_rhythm_detail() (line 1196): intervals = np.diff(ticks) already computed for grooveAmount
- Add tempoStability: round(float(np.std(intervals)), 4) to the returned rhythmDetail dict
- No root output change needed (nested inside existing rhythmDetail)

 1d. Phrase grid

- Same function, line 1193: downbeats = beat_grid[::4] already computed
- Add phraseGrid: { phrases4bar: downbeats[::4], phrases8bar: downbeats[::8], phrases16bar: downbeats[::16] }
- Nested inside rhythmDetail

 1e. Beats loudness summary

- New function analyze_beats_loudness_summary() reusing_extract_beat_loudness_data() output (lines 475-542)
- Returns beatsLoudness: { meanBeatLoudness, stdBeatLoudness, meanLowBand, meanHighBand, lowHighRatio }
- New root-level field in output dict
- Call after analyze_groove(), pass the same beat_data to avoid recomputation

 1f. Gain envelope shape in sidechain

- analyze_sidechain_detail() (lines 1656-1859): already computes rms_values and centers
- Add gainEnvelope (downsampled to 64 pts) and gainEnvelopeTimes to sidechainDetail
- Nested inside existing sidechainDetail

 Test: ./venv/bin/python analyze.py <file> --yes and verify new fields in stdout JSON

 ---
 Step 2: Server pass-through fix in server.py

 File: apps/backend/server.py, function _build_phase1() (lines 434-488)

 2a. Add 7 previously-dropped fields

 ┌──────────────────┬─────────────────────────┬─────────────────┐
 │      Field       │        Coercion         │  Insert after   │
 ├──────────────────┼─────────────────────────┼─────────────────┤
 │ bpmPercival      │ _coerce_nullable_number │ bpmConfidence   │
 ├──────────────────┼─────────────────────────┼─────────────────┤
 │ bpmAgreement     │ pass-through (bool)     │ bpmPercival     │
 ├──────────────────┼─────────────────────────┼─────────────────┤
 │ sampleRate       │_coerce_nullable_number │ durationSeconds │
 ├──────────────────┼─────────────────────────┼─────────────────┤
 │ dynamicSpread    │ _coerce_nullable_number │ crestFactor     │
 ├──────────────────┼─────────────────────────┼─────────────────┤
 │ dynamicCharacter │ pass-through (dict)     │ dynamicSpread   │
 ├──────────────────┼─────────────────────────┼─────────────────┤
 │ segmentStereo    │ pass-through (array)    │ segmentSpectral │
 ├──────────────────┼─────────────────────────┼─────────────────┤
 │ essentiaFeatures │ pass-through (dict)     │ perceptual      │
 └──────────────────┴─────────────────────────┴─────────────────┘

 2b. Add 5 new DSP extension fields

 ┌──────────────────┬─────────────────────────┬──────────────────┐
 │      Field       │        Coercion         │   Insert after   │
 ├──────────────────┼─────────────────────────┼──────────────────┤
 │ tuningFrequency  │ _coerce_nullable_number │ keyConfidence    │
 ├──────────────────┼─────────────────────────┼──────────────────┤
 │ tuningCents      │_coerce_nullable_number │ tuningFrequency  │
 ├──────────────────┼─────────────────────────┼──────────────────┤
 │ lufsMomentaryMax │ _coerce_nullable_number │ lufsRange        │
 ├──────────────────┼─────────────────────────┼──────────────────┤
 │ lufsShortTermMax │_coerce_nullable_number │ lufsMomentaryMax │
 ├──────────────────┼─────────────────────────┼──────────────────┤
 │ beatsLoudness    │ pass-through (dict)     │ grooveDetail     │
 └──────────────────┴─────────────────────────┴──────────────────┘

 2c. Update backend tests

- apps/backend/tests/test_server.py: update_minimal_payload() and add test cases for new fields

 Test: ./venv/bin/python -m unittest discover -s tests from apps/backend/

 ---
 Step 3: TypeScript strong typing

 File: apps/ui/src/types.ts

 3a. Define new interfaces for all Record<string, unknown> fields

 Based on actual backend JSON shapes (verified by reading analyze.py):

- StereoDetail (stereoWidth, stereoCorrelation, subBassCorrelation, subBassMono)
- SpectralDetail (centroid, rolloff, mfcc[], chroma[], barkBands[], erbBands[], spectralContrast[], spectralValley[])
- RhythmDetail (onsetRate, beatGrid[], downbeats[], beatPositions[], grooveAmount, tempoStability, phraseGrid)
- PhraseGrid (phrases4bar[], phrases8bar[], phrases16bar[])
- GrooveDetail (kickSwing, hihatSwing, kickAccent[], hihatAccent[])
- SidechainDetail (pumpingStrength, pumpingRegularity, pumpingRate, pumpingConfidence, gainEnvelope?, gainEnvelopeTimes?)
- EffectsDetail (gatingDetected, gatingRate, gatingRegularity, gatingEventCount)
- SynthesisCharacter (inharmonicity, oddToEvenRatio)
- Structure (segments[], segmentCount)
- ArrangementDetail (noveltyCurve[], noveltyPeaks[], noveltyMean, noveltyStdDev)
- SegmentLoudness (segmentIndex, start, end, lufs, lra)
- SegmentStereo (segmentIndex, stereoWidth, stereoCorrelation)
- SegmentKey (segmentIndex, key, keyConfidence)
- ChordDetail (chordSequence[], chordStrength, progression[], dominantChords[])
- Perceptual (sharpness, roughness)
- EssentiaFeatures (zeroCrossingRate, hfc, spectralComplexity, dissonance)
- DynamicCharacter (dynamicComplexity, loudnessVariation, spectralFlatness, logAttackTime, attackTimeStdDev)
- BeatsLoudness (meanBeatLoudness, stdBeatLoudness, meanLowBand, meanHighBand, lowHighRatio)

 3b. Update Phase1Result to use new interfaces + add new fields

 All new fields are optional for backward compat with older backend versions.

 3c. Update parser in backendPhase1Client.ts

- parsePhase1Result() (~line 480): add parsing for 12 new fields
- Follow existing pattern of parseOptionalAcidDetail() for typed parsers

 3d. Update frontend tests

- apps/ui/tests/services/backendPhase1Client.test.ts: update validPayload.phase1, add cases for new fields

 Test: npm run lint (type-check) then npm test

 ---
 Step 4: 8-Section Measurement Dashboard UI

 New file: apps/ui/src/components/MeasurementDashboard.tsx

 4a. Create MeasurementDashboard component

 Receives MeasurementResult, renders 8 collapsible section groups:

 1. Core Metrics - BPM (+ Percival + agreement), key (+ tuning), time sig, duration, sample rate
 2. Loudness & Dynamics - LUFS integrated/range/momentary max/short-term max, true peak, crest factor, dynamic spread, dynamic character
 3. Spectral - Spectral balance (existing chart), spectral detail, essentia features
 4. Stereo Field - Width, correlation, stereo detail, segment stereo table
 5. Rhythm & Groove - Rhythm detail, tempo stability, phrase grid, groove detail, beats loudness, danceability
 6. Harmony - Chord detail, segment key table
 7. Structure & Arrangement - Structure segments, arrangement detail (novelty curve/peaks), segment loudness table, segment spectral table
 8. Synthesis & Timbre - Synthesis character, perceptual, detector cards (acid/reverb/vocal/supersaw/bass/kick), sidechain + gain envelope, effects detail

 4b. Refactor AnalysisResults.tsx

- Replace lines 293-491 (4-card grid + danceability + detector sections) with <MeasurementDashboard />
- Update navSections to include 8 measurement section IDs
- Keep Phase 2 sections (arrangement, sonic elements, mix chain) unchanged below

 4c. Component patterns

- Use existing Collapsible pattern for section groups
- Use existing metric card style (bg-bg-card border border-border rounded-sm p-4)
- StickyNav integration via section IDs + IntersectionObserver (already works)
- Lazy-load alongside existing AnalysisResults Suspense boundary

 Test: npm run verify (lint + test:unit + build + test:smoke)

 ---
 Step 5: Documentation

 File: apps/backend/JSON_SCHEMA.md

- Add all new root-level fields (tuningFrequency, tuningCents, lufsMomentaryMax, lufsShortTermMax, beatsLoudness)
- Add new nested fields (tempoStability, phraseGrid in rhythmDetail; gainEnvelope in sidechainDetail)
- Update "fields not present in phase1 wrapper" section to remove the 7 now-included fields
- Add the 7 previously-dropped fields to the phase1 field list

 ---
 Execution Order

 ┌──────┬─────────────────────────────────────────────────┬──────────────────────────────────────┬────────────┐
 │ Step │                      Scope                      │                 Test                 │ Depends on │
 ├──────┼─────────────────────────────────────────────────┼──────────────────────────────────────┼────────────┤
 │ 1    │ analyze.py DSP extensions                       │ python analyze.py <file> --yes       │ None       │
 ├──────┼─────────────────────────────────────────────────┼──────────────────────────────────────┼────────────┤
 │ 2    │ server.py pass-through + tests                  │ python -m unittest discover -s tests │ Step 1     │
 ├──────┼─────────────────────────────────────────────────┼──────────────────────────────────────┼────────────┤
 │ 3    │ types.ts + parser + tests                       │ npm run lint && npm test             │ Step 2     │
 ├──────┼─────────────────────────────────────────────────┼──────────────────────────────────────┼────────────┤
 │ 4    │ MeasurementDashboard + AnalysisResults refactor │ npm run verify                       │ Step 3     │
 ├──────┼─────────────────────────────────────────────────┼──────────────────────────────────────┼────────────┤
 │ 5    │ JSON_SCHEMA.md                                  │ Manual review                        │ Steps 1-4  │
 └──────┴─────────────────────────────────────────────────┴──────────────────────────────────────┴────────────┘

 Verification

 1. ./venv/bin/python analyze.py <test-file> --yes - confirm new fields in stdout JSON
 2. ./venv/bin/python -m unittest discover -s tests from apps/backend/ - all backend tests pass
 3. npm run verify from apps/ui/ - lint + unit tests + build + smoke tests pass
 4. ./scripts/dev.sh - full stack runs, upload a file, confirm all 8 sections render with data

 Key Files

- apps/backend/analyze.py - DSP extensions (6 changes)
- apps/backend/server.py - _build_phase1() pass-through (12 new fields)
- apps/backend/tests/test_server.py - backend test updates
- apps/ui/src/types.ts - 18+ new interfaces, Phase1Result expansion
- apps/ui/src/services/backendPhase1Client.ts - parser updates
- apps/ui/tests/services/backendPhase1Client.test.ts - frontend test updates
- apps/ui/src/components/MeasurementDashboard.tsx - NEW: 8-section dashboard
- apps/ui/src/components/AnalysisResults.tsx - refactor to use MeasurementDashboard
- apps/backend/JSON_SCHEMA.md - documentation updates
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌

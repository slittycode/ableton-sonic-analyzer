# Plan: Phase 1 Hardening

Pass all measurements through the pipeline, add DSP extensions, expose everything in the UI. The DSP engine computes ~41 feature functions but server.py drops 6 fields and the UI renders only half of what arrives. This plan unblocks the full pipeline, adds 7 DSP extensions achievable with existing Essentia/NumPy, strongly types the TypeScript contract, and builds an 8-section grouped measurement dashboard.

## Scope
- In: server.py pass-through fix (6 dropped fields), analyze.py DSP extensions (edma key profile, tuning frequency, LUFS momentary/short-term max, phrase grid, tempo stability, beat-synchronous loudness, sidechain envelope shape), types.ts strong typing for all `Record<string, unknown>` fields, new grouped results UI rendering all Phase 1 data, JSON_SCHEMA.md updates
- Out: Phase 2 prompt updates, UI polish/design, AnalysisStatusPanel copy fixes, detector card redesign, new ML dependencies

## Decisions (resolved)
- Key profile: `edma` as primary (electronic music corpus)
- Beat-synchronous loudness: backend computes summary stats, raw per-beat-per-band matrix available behind debug/dev flag
- Phrase grid: works on downbeats regardless of time signature, no 4/4 assumption needed

## Action items
- [ ] Unblock server.py: Add `bpmPercival`, `bpmAgreement`, `sampleRate`, `dynamicSpread`, `segmentStereo`, `essentiaFeatures` to `_build_phase1()`
- [ ] Extend analyze.py key: Switch from `profileType="temperley"` to `"edma"`, export tuning frequency from KeyExtractor
- [ ] Extend analyze.py loudness: Extract max momentary + max short-term LUFS from arrays already returned by `LoudnessEBUR128()` (line 627: `momentary, short_term` are computed then discarded)
- [ ] Extend analyze.py rhythm: Add `tempoStability` (std dev of beat intervals), `phraseGrid` (downbeats grouped into 4/8/16-bar phrases), `beatsLoudness` summaries via Essentia `BeatsLoudness` + raw matrix behind dev flag
- [ ] Extend analyze.py sidechain: Extract beat-synchronous gain envelope shape
- [ ] Strongly type types.ts: Replace `Record<string, unknown>` for `rhythmDetail`, `grooveDetail`, `effectsDetail`, `structure`, `arrangementDetail`, `segmentLoudness`, `segmentKey`, `perceptual`, `essentiaFeatures`; add types for all new + previously-dropped fields
- [ ] Build 8-section grouped UI: (1) Core Metrics, (2) Loudness & Dynamics, (3) Spectral, (4) Stereo Field, (5) Rhythm & Groove, (6) Harmony, (7) Structure & Arrangement, (8) Synthesis & Timbre
- [ ] Update JSON_SCHEMA.md for all new fields
- [ ] Run backend tests: `./venv/bin/python -m unittest discover -s tests`
- [ ] Run frontend verify: `npm run verify`

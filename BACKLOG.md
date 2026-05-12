# Backport Candidates from sonic-architect-app

Source: active/sonic-architect-app (keep in active/ as reference)

## Data (zero deps, direct port)
- `data/genreProfiles.ts` — 35 EDM genre spectral targets, LUFS/crest factor/PLR ranges
  → ASA slot: backend genre classification response; informs Phase 2 Gemini prompt context
  → Status: ✅ Backported to `apps/ui/src/data/genreProfiles.ts`
- `data/abletonDevices.ts` — 14 spectral-band → Ableton Live 12 device mappings (7 bands × 2 energy levels) + FX rule engine
  → ASA slot: Phase 2/3 reconstruction advice; currently Gemini infers these freeform
  → Status: ✅ Backported to `apps/ui/src/data/abletonDevices.ts`

## Mix Analysis (JS logic, ports cleanly to ASA's UI layer)
- `services/mixDoctor.ts` + `components/MixDoctorPanel.tsx` — compares audio features against
  genre profiles, scores spectral balance deviations
  → ASA slot: new UI panel consuming Phase 1 backend data; pairs with genreProfiles.ts
  → Status: ✅ Backported to `apps/ui/src/services/mixDoctor.ts` + `apps/ui/src/components/MixDoctorPanel.tsx`

## Detection Services (reimplemented in Python backend)
- `services/sidechainDetection.ts` — pump/ducking pattern detection from amplitude envelope
  → Status: ✅ Implemented as `analyze_effects_detail()` in `apps/backend/analyze_detection.py`
- `services/acidDetection.ts` — TB-303 resonance + filter-envelope pattern matching
  → Status: ✅ Implemented as `analyze_acid_detail()` in `apps/backend/analyze_detection.py`
- `services/reverbAnalysis.ts` — RT60 decay time estimation from impulse response tail
  → Status: ✅ Implemented as `analyze_reverb_detail()` in `apps/backend/analyze_detection.py`
- `services/vocalDetection.ts` — energy ratio in vocal frequency bands (300Hz–3kHz)
  → Status: ✅ Implemented as `analyze_vocal_detail()` in `apps/backend/analyze_detection.py`
- `services/supersawDetection.ts` — detuned sawtooth oscillator stack detection
  → Status: ✅ Implemented as `analyze_supersaw_detail()` in `apps/backend/analyze_detection.py`
- `services/bassAnalysis.ts` — sub-bass character, bass decay, swing/groove detection
  → Status: ✅ Covered by `analyze_rhythm.py` and `analyze_detection.py`
- `services/kickAnalysis.ts` — kick onset sharpness, pitch, THD (Total Harmonic Distortion)
  → Status: ✅ Covered by `analyze_core.py` and `analyze_rhythm.py`
- `services/genreClassifierEnhanced.ts` — orchestrates all 8 detectors above via Promise.all()
  → Status: ✅ Implemented as `analyze_genre_detail()` in `apps/backend/analyze_detection.py`

## Synthesis / Generation
- `services/patchSmith.ts` — generates Vital/Operator patch parameters from detected features
  → ASA slot: Phase 3 (not yet built); unique differentiator — download-ready preset output

## Visualizations (D3, UI layer only)
- `components/SpectralHeatmap.tsx` — per-band frequency energy over time (D3 heatmap)
  → ASA slot: waveform/analysis view; replaces or supplements WaveSurfer display
- `components/SpectralAreaChart.tsx` — stacked spectral energy area chart (D3)
  → ASA slot: same view; alternative representation of spectral balance data

## Contract Follow-Ups
- ✅ `timeSignatureSource` / `timeSignatureConfidence` — surfaced through HTTP `phase1` via `server.py` (verified on live raw analyzer output before passthrough wiring)
- ✅ Vibrato display follow-up — labeled `melodyDetail.vibratoExtent` in cents and render present-branch sub-1% confidence as `< 1%` to avoid the misleading `VIBRATO: PRESENT ... 0%` combination.

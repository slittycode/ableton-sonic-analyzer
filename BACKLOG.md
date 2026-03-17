# Backport Candidates from sonic-architect-app

Source: active/sonic-architect-app (keep in active/ as reference)

## Data (zero deps, direct port)
- `data/genreProfiles.ts` — 12+ EDM genre spectral targets, LUFS/crest factor/PLR ranges
  → ASA slot: backend genre classification response; informs Phase 2 Gemini prompt context
- `data/abletonDevices.ts` — 50+ spectral-characteristic → Ableton Live 12 device mappings
  → ASA slot: Phase 2/3 reconstruction advice; currently Gemini infers these freeform

## Mix Analysis (JS logic, ports cleanly to ASA's UI layer)
- `services/mixDoctor.ts` + `components/MixDoctorPanel.tsx` — compares audio features against
  genre profiles, scores spectral balance deviations
  → ASA slot: new UI panel consuming Phase 1 backend data; pairs with genreProfiles.ts

## Detection Services (JS; decision needed: port to UI layer or reimplement in Python backend)
- `services/sidechainDetection.ts` — pump/ducking pattern detection from amplitude envelope
  → ASA slot: rhythm/dynamics section of Phase 1 analysis output
- `services/acidDetection.ts` — TB-303 resonance + filter-envelope pattern matching
  → ASA slot: bass character classification in Phase 1
- `services/reverbAnalysis.ts` — RT60 decay time estimation from impulse response tail
  → ASA slot: space/FX section of Phase 1 analysis; feeds Ableton reverb device selection
- `services/vocalDetection.ts` — energy ratio in vocal frequency bands (300Hz–3kHz)
  → ASA slot: stem classification; affects instrument rack recommendations
- `services/supersawDetection.ts` — detuned sawtooth oscillator stack detection
  → ASA slot: synth characterization; feeds Wavetable/Serum device mapping
- `services/bassAnalysis.ts` — sub-bass character, bass decay, swing/groove detection
  → ASA slot: rhythm + bass section of Phase 1; swing value feeds MIDI quantization
- `services/kickAnalysis.ts` — kick onset sharpness, pitch, THD (Total Harmonic Distortion)
  → ASA slot: percussion analysis in Phase 1; feeds Ableton drum rack recommendations
- `services/genreClassifierEnhanced.ts` — orchestrates all 8 detectors above via Promise.all()
  → ASA slot: replaces/augments basic genre detection; feeds genre label used in Phase 2

## Synthesis / Generation
- `services/patchSmith.ts` — generates Vital/Operator patch parameters from detected features
  → ASA slot: Phase 3 (not yet built); unique differentiator — download-ready preset output

## Visualizations (D3, UI layer only)
- `components/SpectralHeatmap.tsx` — per-band frequency energy over time (D3 heatmap)
  → ASA slot: waveform/analysis view; replaces or supplements WaveSurfer display
- `components/SpectralAreaChart.tsx` — stacked spectral energy area chart (D3)
  → ASA slot: same view; alternative representation of spectral balance data

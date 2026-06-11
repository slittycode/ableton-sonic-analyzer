# Backport Candidates from sonic-architect-app

Source: `active/sonic-architect-app` (keep in `active/` as reference). Most of the original backlog landed during the detector port — the remaining open work is in the **Open** section at the bottom.

## Shipped — Data
- ✅ `data/genreProfiles.ts` — 35 EDM genre spectral targets, LUFS/crest factor/PLR ranges. **Landed:** [`apps/ui/src/data/genreProfiles.ts`](apps/ui/src/data/genreProfiles.ts).
- ✅ `data/abletonDevices.ts` — 14 spectral-band → Ableton Live 12 device mappings + FX rule engine. **Landed:** [`apps/ui/src/data/abletonDevices.ts`](apps/ui/src/data/abletonDevices.ts). *Ported but demoted to a research-only scoring baseline (owner decision 2026-06-11): imported by no product code, consumed only by the recommendation-eval bridge. See the NEEDS-WIRING decision in [`apps/backend/NEEDS.md`](apps/backend/NEEDS.md).*

## Shipped — Mix Analysis
- ✅ `services/mixDoctor.ts` + `components/MixDoctorPanel.tsx` — spectral-balance scoring against genre profiles. **Landed:** [`apps/ui/src/services/mixDoctor.ts`](apps/ui/src/services/mixDoctor.ts), [`apps/ui/src/components/MixDoctorPanel.tsx`](apps/ui/src/components/MixDoctorPanel.tsx).

## Shipped — Detectors (ported to Python backend instead of UI layer)
All eight detectors emit fields visible in [`apps/backend/tests/test_analyze.py`](apps/backend/tests/test_analyze.py) `EXPECTED_TOP_LEVEL_KEYS` and run inside [`apps/backend/analyze_detection.py`](apps/backend/analyze_detection.py).

- ✅ `sidechainDetection.ts` → `sidechainDetail`
- ✅ `acidDetection.ts` → `acidDetail` (historical implementation record archived at [`docs/history/archive/acid-detection-implementation.md`](docs/history/archive/acid-detection-implementation.md))
- ✅ `reverbAnalysis.ts` → `reverbDetail`
- ✅ `vocalDetection.ts` → `vocalDetail`
- ✅ `supersawDetection.ts` → `supersawDetail`
- ✅ `bassAnalysis.ts` → `bassDetail`
- ✅ `kickAnalysis.ts` → `kickDetail`
- ✅ `genreClassifierEnhanced.ts` → `genreDetail` (orchestrates the detectors above)

## Shipped — Visualizations (re-shaped, not direct ports)
- ✅ Spectral views: [`SpectrogramViewer.tsx`](apps/ui/src/components/SpectrogramViewer.tsx), [`SpectralEvolutionChart.tsx`](apps/ui/src/components/SpectralEvolutionChart.tsx), [`ChromaHeatmap.tsx`](apps/ui/src/components/ChromaHeatmap.tsx), [`MiniHeatmap.tsx`](apps/ui/src/components/MiniHeatmap.tsx). The original `SpectralHeatmap.tsx` / `SpectralAreaChart.tsx` from sonic-architect-app were not ported verbatim; the same need is covered by these components driven off backend spectrogram artifacts.

## Shipped — Contract Follow-Ups
- ✅ `timeSignatureSource` / `timeSignatureConfidence` — surfaced through HTTP `phase1` via `server.py`.
- ✅ Vibrato display follow-up — `melodyDetail.vibratoExtent` is labeled in cents and present-branch sub-1% confidence renders as `< 1%` rather than `VIBRATO: PRESENT … 0%`.

## Shipped — Phase 3 Audition
- ✅ **Audition samples.** Heuristic WAV/MIDI clips derived from Phase 1 measurements (and Phase 2 context when available) so producers can ear-check the measurement chain. PyTheory generates the musical plan, FluidSynth (with sine-additive fallback) renders audio, NumPy synthesizes drum one-shots, manifest carries citations. **Landed:** [`apps/backend/sample_generation.py`](apps/backend/sample_generation.py), [`sample_theory.py`](apps/backend/sample_theory.py), [`sample_synthesis.py`](apps/backend/sample_synthesis.py), [`sample_drums.py`](apps/backend/sample_drums.py), [`server_samples.py`](apps/backend/server_samples.py); UI [`SamplePlayback.tsx`](apps/ui/src/components/SamplePlayback.tsx) + [`sampleGenerationClient.ts`](apps/ui/src/services/sampleGenerationClient.ts). On-demand endpoints `POST/GET /api/analysis-runs/{run_id}/samples` (not part of the staged-execution queue). Design doc: [`docs/SAMPLE_GENERATION.md`](docs/SAMPLE_GENERATION.md). Adjacent to `patchSmith.ts` but solves a different problem — audition validates the measurements rather than producing a saveable preset.

## Shipped — Phase 3 Preset Generation
- ✅ `services/patchSmith.ts` — downloadable Vital (`.vital`) synth presets derived from Phase 1 synthesis measurements. Cites exact measurements per preset parameter (PURPOSE.md invariant #2); hedges or skips parameters whose evidence is weak (invariant #4). **Landed:** [`apps/ui/src/services/patchSmith.ts`](apps/ui/src/services/patchSmith.ts).

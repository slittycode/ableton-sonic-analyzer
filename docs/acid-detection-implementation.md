# Acid Detection — Implementation Record

**Date:** 2026-03-18
**Feature:** `acidDetail` — TB-303 acid bassline detection
**Source:** Backported from `active/sonic-architect-app/services/acidDetection.ts`
**Target layer:** Layer 1 (Measurement) — `analyze.py` Python backend

---

## Plan

### Goal

Port the JS `detectAcidPattern` function to the ASA Python backend as `analyze_acid_detail`, wire it into the full analysis pipeline, and propagate the new field through the HTTP contract and TypeScript types.

### Approach

1. Read reference source (`sidechainDetection.ts` was already done; move to `acidDetection.ts` as next item)
2. Implement `analyze_acid_detail()` in `analyze.py` using Essentia's `Spectrum`/`Windowing` (replaces browser FFT)
3. Wire into the normal and `--fast` output paths
4. Forward through `server.py`
5. Type in `apps/ui/src/types.ts`
6. Document in `JSON_SCHEMA.md`
7. Add unit tests covering real-signal behavior (not just shape checks)
8. Run full verification suite

---

## Implementation

### Algorithm (faithfully ported from TS)

The detector analyses the 100–800 Hz bass band frame-by-frame using a 2048-point FFT with 512-sample hops.

Three signals are computed per-frame:

| Signal | What it measures | Acid indicator |
|---|---|---|
| **Spectral centroid** (bass band) | Center-of-gravity of bass energy | Std dev (centroid oscillation) → filter sweep |
| **Band RMS** | Energy in bass band per frame | Peak-to-mean ratio → resonance squelch |
| **Onset count** | Bass-band energy increases > 150% | Density relative to expected 16th-note rate |

Composite confidence score (matches reference weights exactly):

```
confidence = centroid_score * 0.4 + resonance_level * 0.4 + rhythm_score * 0.2
isAcid = confidence > 0.45
```

Where:
- `centroid_score = min(1.0, centroid_std_dev / 100)`  — >100 Hz oscillation = acid-like
- `resonance_level = min(1.0, (max_rms - mean_rms) / mean_rms)` — peak-to-mean RMS ratio
- `rhythm_score = min(1.0, onset_rate / (expected_16th_rate * 0.5))`

### Files Changed

| File | Change |
|---|---|
| `apps/backend/analyze.py` | Added `analyze_acid_detail()` (~95 lines); wired after `analyze_sidechain_detail()`; added `acidDetail` to both normal and `--fast` output dicts |
| `apps/backend/server.py` | Added `"acidDetail": payload.get("acidDetail")` to the phase1 HTTP response builder |
| `apps/ui/src/types.ts` | Added typed `acidDetail` interface to `Phase1Result` |
| `apps/backend/JSON_SCHEMA.md` | Added `acidDetail` to root keys list, forwarded-sections list, and added schema table |
| `apps/backend/tests/test_analyze.py` | Added `acidDetail` to `EXPECTED_OUTPUT_KEYS`; added `AcidDetailTests` class (6 tests) |

### Output Shape

```json
"acidDetail": {
  "isAcid": false,
  "confidence": 0.12,
  "resonanceLevel": 0.08,
  "centroidOscillationHz": 45,
  "bassRhythmDensity": 3.2
}
```

Null when: signal is empty, BPM is None/invalid, or fewer than 10 analysis frames are available.

---

## Critical Actions

### 1. Verified backlog status before implementing

Confirmed `sidechainDetail` was already implemented in `analyze.py`. Moved to the next unimplemented item: `acidDetection.ts`. Would have wasted a full iteration reimplementing sidechain.

### 2. Replaced browser FFT with Essentia Spectrum

The reference uses `fftInPlace(real, imag)` — a custom browser FFT. Python backend uses Essentia's `Spectrum` + `Windowing(type="hann")`, which produces magnitude spectrum directly. This is the correct port; the math is equivalent on the same frequency bins.

### 3. Both output paths updated

`analyze.py` has two output code paths: the `--fast` branch and the normal analysis branch. Both needed `"acidDetail": result.get("acidDetail")`. Missing one would silently drop the field in that mode.

### 4. Contract check before writing HTTP field

Confirmed `acidDetail` is appropriate to expose via HTTP (unlike `bpmPercival`, `sampleRate`, etc. which are raw CLI-only). Checked `JSON_SCHEMA.md` forwarded-sections list before adding to `server.py`.

### 5. Typed in `types.ts` with specific interface, not `Record<string, unknown>`

`sidechainDetail` and `effectsDetail` use `Record<string, unknown>` in types.ts (typed loosely). `acidDetail` was given a proper typed interface since all five fields have known names and types. This is strictly better.

### 6. Unit tests verify real computed values, not just shape

Tests include a sweep-frequency signal (150→700 Hz) that exercises centroid oscillation and resonance level, asserting `> 0` rather than just checking field presence. Avoids the "tests pass but detect nothing" pattern.

---

## Verification Results

```
Backend:  90 tests — OK (29 analyze + 51 server + 10 runtime)
Frontend: 131 tests — OK, type-check clean
Stubs:    0 TODOs / NotImplementedError in new code
```

---

## What's Next (from BACKLOG.md)

Remaining unimplemented detection services in order:

1. `reverbAnalysis.ts` — RT60 decay estimation → `effectsDetail.reverbDetail` or new section
2. `vocalDetection.ts` — energy ratio in 300 Hz–3 kHz → stem classification
3. `supersawDetection.ts` — detuned saw stack detection → synthesis character
4. `bassAnalysis.ts` — sub-bass character, swing → rhythm + bass section
5. `kickAnalysis.ts` — onset sharpness, pitch, THD → percussion analysis
6. `genreClassifierEnhanced.ts` — orchestrates all detectors → genre label for Phase 2

# ADR 0002 — Phase 1 loudness-field units (schema v2)

**Status:** Accepted
**Date:** 2026-06-01
**Supersedes:** Partially supersedes [ADR 0001](0001-phase1-json-schema-v1.md) for two fields.
**Anchor:** [PURPOSE.md](../../PURPOSE.md) quality invariants #1 (measurement authority) and #4 (honest uncertainty).

## Context

ADR 0001 declared the Phase 1 payload "v1" and classified unit changes and range
changes as breaking (forbidden under v1). Two v1 fields carried representations that
fought the grain of nearly every consumer:

1. **`truePeak`** was emitted as a **linear amplitude proxy** (1.0 == 0 dBFS). The
   conventional meaning of "true peak" is **dBTP**, and a code audit found ~12 consumers
   already *assumed* dBTP — several were latent bugs because the field was actually linear:
   - `analysisResultsViewModel.ts` computed master ceilings as `min(-0.3, truePeak - 0.1)`,
     which always returned `-0.3` for a linear `truePeak ≈ 1.0`.
   - `MeasurementDashboard.tsx` rendered `{ value: truePeak, suffix: 'dBTP' }` (showing
     `1.00 dBTP` instead of `0.0`) and scaled the meter on a dB range.
   - `analyze_core.analyze_plr` computed `truePeak_linear - lufsIntegrated` — a linear
     amplitude minus a dB value, an incoherent number.
   Only `loudnessGuardrails.ts` correctly treated the field as linear.

2. **`bpmConfidence`** was the raw Essentia `RhythmExtractor2013` confidence (~0–5.32),
   the *only* `*Confidence` field not normalized to 0–1. Consumers that assumed 0–1
   mis-rendered it (`exportUtils.ts` multiplied by 100 → up to ~500%; the confidence-band
   ladder mis-banded it), and the validator carried a special-case threshold.

The WASM loudness package (`packages/loudness-spectro-wasm`) also emits `true_peak_dbtp`.
Keeping v1's linear/raw representations required converting at ~20 fragile consumer sites;
fixing the *source* makes the majority of consumers correct by default.

## Decision

Bump the Phase 1 measurement schema to **`phase1.v2`** and change two field units:

| Field | v1 | v2 |
|---|---|---|
| `truePeak` | linear amplitude proxy (1.0 == full scale) | **dBTP** (0.0 == full scale, > 0 == inter-sample over); `null` for silence |
| `bpmConfidence` | raw Essentia confidence (~0–5.32) | **normalized 0–1** (raw / 5.0, clamped) |

A new top-level string field **`phase1Version`** (e.g. `"phase1.v2"`) is added so consumers
can detect the generation — this is the canonical mechanism ADR 0001 anticipated for a v2 bump.

Derived/consumer effects:
- `plr` is now a direct dB-domain subtraction (`truePeak_dBTP - lufsIntegrated`); its *unit*
  (LU) is unchanged, so this is a correctness fix, not a contract change.
- `loudnessGuardrails.ts` over-detection moves from `truePeak > 1.0` (linear) to
  `truePeak > 0.0` (dBTP).
- `bpmConfidence` now shares the standard `0.4` low-confidence hedge threshold; the
  validator's BPM-specific threshold is removed.

## Compatibility

This is a **breaking change** under ADR 0001's policy (units + range). It is acceptable
because ASA is, in practice, its own only consumer (personal use), and the change makes the
payload *more* conventional, not less. External consumers can branch on `phase1Version`.
ADR 0001's compatibility table still governs all other fields.

## Enforcement / where v2 is pinned

- `EXPECTED_TOP_LEVEL_KEYS` and `FAST_MODE_POPULATED_FIELDS` in `tests/test_analyze.py`
  (now include `phase1Version`).
- The Phase 1 golden snapshot (`tests/fixtures/golden/phase1_default.json`), re-baselined
  for `truePeak: 0.0` (dBTP) and `plr: 5.6`.
- Dedicated unit tests in `tests/test_loudness_r128.py` (dBTP `analyze_true_peak`, dB-domain
  `analyze_plr`) and the fixture expectations in `tests/test_audio_fixture.py`.
- `Phase1Result` typing in `apps/ui/src/types/measurement.ts` and `JSON_SCHEMA.md`.

## Not in scope

- No other field units change. No machine-readable JSON Schema artifact (still deferred).
- The WASM package is not yet wired in; this ADR only aligns the Essentia path's *units*
  with dBTP convention (which happens to match WASM), easing a future parity comparison.

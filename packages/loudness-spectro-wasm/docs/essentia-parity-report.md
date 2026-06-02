# asa-dsp ↔ Essentia loudness parity report

_Generated 2026-06-02 by `scripts/essentia_parity.py` (WS3a checkpoint)._

**Verdict: ❌ FAIL** — primary gate is integrated LUFS within ±0.1 LU on every file.

- Worst integrated delta: **0.102 LU** (tolerance ±0.1).
- Corpus: 8 deterministic synthetic signal(s) @ 48000 Hz, 12s stereo (seed 0xA5AD5).
- Breaches: log_sweep_20_20k (Δ -0.102 LU).

## Integrated LUFS (the gate)

| file | Essentia | asa-dsp | Δ (asa−ess) | status |
|---|---:|---:|---:|---|
| sine_1k | -6.00 | -6.01 | -0.012 | ok |
| hot_sine_3k | 2.67 | 2.67 | -0.002 | ok |
| quiet_sine_1k | -30.45 | -30.45 | -0.002 | ok |
| two_tone_100_3k | -4.77 | -4.79 | -0.018 | ok |
| pink_noise | -14.71 | -14.71 | -0.001 | ok |
| white_noise | -13.46 | -13.46 | -0.000 | ok |
| stereo_decorrelated_pink | -15.07 | -15.07 | +0.001 | ok |
| log_sweep_20_20k | -2.08 | -2.18 | -0.102 | FAIL |

## Secondary metrics (reported, not gated)

| file | Short-term max LUFS | Momentary max LUFS | LRA (LU) | True peak dBTP |
|---|---:|---:|---:|---:|
| sine_1k | -6.00 / -6.01 (Δ -0.01) | -6.00 / -6.01 (Δ -0.01) | 0.00 / 0.00 (Δ -0.00) | -6.02 / -6.02 (Δ -0.00) |
| hot_sine_3k | 2.67 / 2.67 (Δ -0.00) | 2.67 / 2.67 (Δ -0.00) | 0.00 / 0.00 (Δ -0.00) | -0.39 / -0.45 (Δ -0.06) |
| quiet_sine_1k | -30.45 / -30.45 (Δ -0.00) | -30.45 / -30.45 (Δ -0.00) | 0.00 / 0.00 (Δ -0.00) | -30.46 / -30.46 (Δ -0.00) |
| two_tone_100_3k | -4.77 / -4.79 (Δ -0.02) | -4.77 / -4.79 (Δ -0.02) | 0.00 / 0.00 (Δ -0.00) | -3.10 / -3.10 (Δ +0.00) |
| pink_noise | -14.67 / -14.66 (Δ +0.00) | -14.52 / -14.52 (Δ -0.00) | 0.05 / 0.05 (Δ +0.01) | -2.89 / -2.95 (Δ -0.06) |
| white_noise | -13.42 / -13.42 (Δ -0.00) | -13.34 / -13.34 (Δ -0.00) | 0.07 / 0.06 (Δ -0.01) | -6.61 / -6.02 (Δ +0.59) |
| stereo_decorrelated_pink | -15.02 / -14.95 (Δ +0.08) | -14.94 / -14.94 (Δ +0.00) | 0.06 / 0.05 (Δ -0.00) | -2.94 / -2.91 (Δ +0.03) |
| log_sweep_20_20k | 0.24 / 0.24 (Δ -0.00) | 0.25 / 0.25 (Δ -0.00) | 6.08 / 6.05 (Δ -0.03) | -2.91 / -2.99 (Δ -0.08) |

> Cells show `Essentia / asa-dsp (Δ asa−ess)`. True peak is converted from Essentia's linear TruePeakDetector output via `20·log10` to match asa-dsp's dBTP; it is a sanity signal, not a gate.

## Method & caveats

- Both paths decode each WAV at its **native rate** with no resampling. Essentia uses `AudioLoader` → `LoudnessEBUR128` (identical to `analyze_core.analyze_loudness`); asa-dsp uses the `measure-cli` binary (source-identical to the WASM core).
- The corpus is **synthetic** (tones, sweep, white/pink noise, decorrelated stereo). Broadband noise is the most demanding case for K-weighting agreement; tones are easy. Real-program parity should be re-confirmed before flipping any default.
- This is the WS3a checkpoint. A PASS clears WS3b/WS3c to proceed *behind a default-off flag*; the loudness default only flips to asa-dsp after real-program parity is also proven.

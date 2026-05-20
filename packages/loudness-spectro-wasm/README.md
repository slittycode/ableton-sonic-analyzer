# @asa/loudness-spectro-wasm

Browser-first WebAssembly DSP for ASA: **ITU-R BS.1770-5 / EBU R128 loudness**, an
**A-weighted spectrum**, and a **spectral-reassignment spectrogram**. The DSP is lifted
from [openmeters](https://github.com/httpsworldview/openmeters) (Rust) and compiled to
WASM via `wasm-bindgen` — not reimplemented in JS.

## Status

| Capability | State |
|---|---|
| BS.1770-5 K-weighting, momentary, short-term | ✅ lifted from openmeters |
| True-peak (4× oversampled, Annex 2) | ✅ lifted from openmeters |
| **Integrated loudness + gating + LRA** | ✅ added here (openmeters is a live meter and omits these) |
| A-weighted spectrum (whole-file average) | ✅ lifted from openmeters |
| Spectral-reassignment spectrogram | ✅ lifted from openmeters |
| Streaming push API across the JS boundary | ⏳ (native streaming exists) |

## API

```ts
import init, { measureLoudness } from "@asa/loudness-spectro-wasm";
await init();

// `samples` is interleaved f32 PCM at the file's native rate ([L,R,L,R,...]).
const r = measureLoudness(samples, /* channels */ 2, /* sampleRate */ 48000);
r.integrated_lufs;     // LUFS (NaN if undefined — no block passed the gates)
r.loudness_range;      // LU
r.momentary_max_lufs;  // LUFS
r.short_term_max_lufs; // LUFS
r.true_peak_dbtp;      // dBTP
r.free();              // release the wasm-owned result
```

### Spectrogram + spectrum

```ts
import init, { reassignedSpectrogram, aWeightedSpectrum } from "@asa/loudness-spectro-wasm";
await init();

// Sparse spectral-reassignment spectrogram. Offline defaults: fftSize 2048, hop 512.
const sg = reassignedSpectrogram(samples, 48000, /*channels*/ 2,
                                 /*fftSize*/ 2048, /*hop*/ 512, /*maxPoints*/ 300000);
sg.points;       // Float32Array of [absTimeSec, freqHz, magDb] triples
sg.point_count;  // number of triples (capped to maxPoints)
sg.num_columns; sg.hop_seconds; sg.max_freq_hz;
sg.free();

// Whole-file A-weighted average spectrum.
const sp = aWeightedSpectrum(samples, 48000, /*channels*/ 2, /*fftSize*/ 4096);
sp.frequencies;              // Float32Array, Hz (length fftSize/2+1)
sp.magnitudes_db;            // A-weighted dB
sp.magnitudes_unweighted_db; // unweighted dB
sp.bin_hz;
sp.free();
```

The spectrogram runs 3 FFTs per column (Hilbert-analytic Auger–Flandrin reassignment), so
for whole-file analysis prefer a larger `hop` (≥512) and run it in a Web Worker. Output is
capped to `maxPoints` via a deterministic single-pass reservoir (no tail loss).

### ⚠ Decode without resampling

Do **not** feed audio through `AudioContext.decodeAudioData` for measurement — it
resamples to the context rate, which alters the signal and breaks ±0.1 LU EBU
conformance. Decode at the file's native rate (e.g. read WAV PCM directly, or use
`OfflineAudioContext` at the file's own sample rate).

## Build

```bash
rustup target add wasm32-unknown-unknown
cargo install wasm-bindgen-cli --version <match Cargo.lock>   # or use a prebuilt binary
npm run build          # -> pkg/   (web target)
npm run build:node     # -> pkg-node/ (for the Node smoke test)
```

`WASM_BINDGEN=/path/to/wasm-bindgen` overrides the binary; `WASM_OPT=1` runs
`wasm-opt -Oz` if binaryen is installed. Raw module is ~48 KB before `wasm-opt`/gzip.

## Validation

Three independent layers, run by `npm run test:rust` (`cargo test`):

1. **Absolute EBU Tech 3341/3342 conformance** (primary oracle,
   `crates/asa-dsp/tests/ebu_conformance.rs`). Synthesized, network-free signals
   whose correct EBU reading is known a priori: a dual-mono 1 kHz sine at peak
   −X dBFS must read −X LUFS (integrated, momentary-max, short-term-max), at both
   44.1 kHz and 48 kHz; LRA on a −23/−33 step must read ≈10 LU. Run just these
   with `npm run test:ebu`.
2. **`ebur128` cross-check** (independent BS.1770 implementation, mirrors
   openmeters' own test oracle): integrated within **0.1 LU**, short-term within
   **0.001 LU**, true-peak within **0.2 dB**, LRA within **1 LU**; streaming
   chunks match single-shot.
3. **pyloudnorm cross-check** (a third, Python implementation; dev/CI helper,
   not a committed gate). Build the native CLI with `npm run build:cli`
   (`cargo build --release -p measure-cli`), then:

   ```bash
   pip install pyloudnorm soundfile numpy
   python scripts/pyloudnorm_crosscheck.py <corpus-dir>   # asserts |Δ| < 0.5 LU
   ```

`npm run test:smoke` additionally exercises the generated WASM from Node.

### Optional: the official EBU compliance set

`scripts/fetch-ebu-testset.sh` downloads the official EBU Tech 3341/3342 signals
into `testsets/ebu/` (gitignored); the URL is supplied via `EBU_TESTSET_URL`
(not hardcoded). Then:

```bash
ASA_EBU_TESTSET_DIR=testsets/ebu cargo test --test ebu_conformance
```

runs the optional official-set path. Populate the `EXPECTED` filename→LUFS table
in `ebu_conformance.rs` from EBU Tech 3341 §2.1 first — an unmatched WAV is
reported as a skip, never a phantom pass/fail.

## Attribution / license

Portions vendored from [openmeters](https://github.com/httpsworldview/openmeters),
Copyright (C) 2026 Maika Namuo, **GPL-3.0-or-later**; this package inherits that
license. The `ebur128` crate is a test-only dependency.

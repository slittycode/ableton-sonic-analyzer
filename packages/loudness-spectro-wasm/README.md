# @asa/loudness-spectro-wasm

Browser-first WebAssembly DSP for ASA: **ITU-R BS.1770-5 / EBU R128 loudness**
today, **spectral-reassignment spectrogram** next. The DSP is lifted from
[openmeters](https://github.com/httpsworldview/openmeters) (Rust) and compiled to
WASM via `wasm-bindgen` — not reimplemented in JS.

## Status

| Capability | State |
|---|---|
| BS.1770-5 K-weighting, momentary, short-term | ✅ lifted from openmeters |
| True-peak (4× oversampled, Annex 2) | ✅ lifted from openmeters |
| **Integrated loudness + gating + LRA** | ✅ added here (openmeters is a live meter and omits these) |
| A-weighted spectrum | ⏳ Phase 2 |
| Spectral-reassignment spectrogram | ⏳ Phase 2 |
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

`npm run test:rust` cross-checks the DSP against the independent **`ebur128`**
crate (mirrors openmeters' own test oracle): integrated within **0.1 LU**,
short-term within **0.001 LU**, true-peak within **0.1 dB**, LRA within **1 LU**;
streaming chunks match single-shot. `npm run test:smoke` exercises the generated
WASM from Node.

Still to come (per the incorporation plan): the **EBU Tech 3341/3342 compliance
test set** as the primary oracle and **pyloudnorm** as a second independent
cross-check on real-world material.

## Attribution / license

Portions vendored from [openmeters](https://github.com/httpsworldview/openmeters),
Copyright (C) 2026 Maika Namuo, **GPL-3.0-or-later**; this package inherits that
license. The `ebur128` crate is a test-only dependency.

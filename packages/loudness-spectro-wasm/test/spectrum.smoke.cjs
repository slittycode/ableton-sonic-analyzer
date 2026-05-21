// Node smoke test for the generated WASM A-weighted spectrum.
// Build first:  npm run build:node   (produces ../pkg-node)
// Then run:     node test/spectrum.smoke.cjs
const path = require("node:path");
const asa = require(path.join(__dirname, "..", "pkg-node", "asa_dsp_wasm.js"));

const rate = 48000;
const ch = 2;
const fftSize = 4096;
const N = rate * 1; // 1 s
const buf = new Float32Array(N * ch);
for (let n = 0; n < N; n++) {
  const v = 0.5 * Math.sin((2 * Math.PI * 1000 * n) / rate);
  buf[2 * n] = v;
  buf[2 * n + 1] = v;
}

const r = asa.aWeightedSpectrum(buf, rate, ch, fftSize);
const freqs = r.frequencies;
const mags = r.magnitudes_unweighted_db;
const magsA = r.magnitudes_db;
const binHz = r.bin_hz;
r.free();

let ok = true;
const check = (name, cond) => {
  console.log((cond ? "  PASS " : "  FAIL ") + name);
  ok = ok && cond;
};

const bins = fftSize / 2 + 1;
let peakIdx = 0;
for (let i = 1; i < mags.length; i++) if (mags[i] > mags[peakIdx]) peakIdx = i;
const peakHz = freqs[peakIdx];
console.log(
  "aWeightedSpectrum ->",
  JSON.stringify({ bins: freqs.length, bin_hz: binHz, peak_hz: peakHz }),
);

check("array lengths == fft/2+1", freqs.length === bins && mags.length === bins && magsA.length === bins);
check("bin_hz ~ 48000/4096", Math.abs(binHz - rate / fftSize) < 1e-3);
check(`peak near 1 kHz (got ${peakHz.toFixed(1)} Hz)`, Math.abs(peakHz - 1000) < 20);
check("A-weight ~0 dB at 1 kHz", Math.abs(magsA[peakIdx] - mags[peakIdx]) < 0.5);

process.exit(ok ? 0 : 1);

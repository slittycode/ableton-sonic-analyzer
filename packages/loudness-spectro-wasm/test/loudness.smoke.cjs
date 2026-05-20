// Node smoke test for the generated WASM loudness module.
// Build first:  npm run build:node   (produces ../pkg-node)
// Then run:     node test/loudness.smoke.cjs
const path = require("node:path");
const asa = require(path.join(__dirname, "..", "pkg-node", "asa_dsp_wasm.js"));

const rate = 48000;
const secs = 5;
const freq = 1000;
const amp = 0.5; // -6.02 dBFS
const ch = 2;

const N = rate * secs;
const buf = new Float32Array(N * ch);
for (let n = 0; n < N; n++) {
  const v = amp * Math.sin((2 * Math.PI * freq * n) / rate);
  buf[2 * n] = v;
  buf[2 * n + 1] = v;
}

const r = asa.measureLoudness(buf, ch, rate);
const out = {
  integrated_lufs: r.integrated_lufs,
  loudness_range: r.loudness_range,
  momentary_max_lufs: r.momentary_max_lufs,
  short_term_max_lufs: r.short_term_max_lufs,
  true_peak_dbtp: r.true_peak_dbtp,
  channels: r.channels,
  sample_rate: r.sample_rate,
};
r.free();

console.log("measureLoudness ->", JSON.stringify(out));

let ok = true;
const check = (name, cond) => {
  console.log((cond ? "  PASS " : "  FAIL ") + name);
  ok = ok && cond;
};
// Steady stereo 1 kHz sine at amp 0.5 reads ~ -6.0 LUFS / -6.02 dBTP.
check("integrated finite", Number.isFinite(out.integrated_lufs));
check("integrated in (-8,-4)", out.integrated_lufs > -8 && out.integrated_lufs < -4);
check("true_peak ~ -6.02 dBTP", out.true_peak_dbtp > -7 && out.true_peak_dbtp < -5);
check("short_term_max finite", Number.isFinite(out.short_term_max_lufs));
check("channels==2", out.channels === 2);
check("sample_rate==48000", out.sample_rate === 48000);

process.exit(ok ? 0 : 1);

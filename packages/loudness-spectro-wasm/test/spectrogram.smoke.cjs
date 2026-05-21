// Node smoke test for the generated WASM reassignment spectrogram.
// Build first:  npm run build:node   (produces ../pkg-node)
// Then run:     node test/spectrogram.smoke.cjs
const path = require("node:path");
const asa = require(path.join(__dirname, "..", "pkg-node", "asa_dsp_wasm.js"));

const rate = 48000;
const ch = 2;
// 0.5 s silence, 0.5 s 1 kHz tone, 0.5 s silence — so the tone's reassigned
// energy MUST land near t ∈ [0.5, 1.0] s. Guards the absTime formula: an
// off-by-hop/seconds error (~86×) would place it tens of seconds out.
const seg = 0.5 * rate;
const buf = new Float32Array(seg * 3 * ch);
for (let n = 0; n < seg; n++) {
  const v = 0.5 * Math.sin((2 * Math.PI * 1000 * n) / rate);
  const i = (seg + n) * ch; // middle segment
  buf[i] = v;
  buf[i + 1] = v;
}

const r = asa.reassignedSpectrogram(buf, rate, ch, 2048, 512, 300000);
const pts = r.points;
const out = {
  point_count: r.point_count,
  num_columns: r.num_columns,
  hop_seconds: r.hop_seconds,
  max_freq_hz: r.max_freq_hz,
};
r.free();
console.log("reassignedSpectrogram ->", JSON.stringify(out));

let ok = true;
const check = (name, cond) => {
  console.log((cond ? "  PASS " : "  FAIL ") + name);
  ok = ok && cond;
};

// Collect points near 1 kHz and find the strongest.
let maxMag = -Infinity;
const near1k = [];
for (let i = 0; i < pts.length; i += 3) {
  const t = pts[i], f = pts[i + 1], m = pts[i + 2];
  if (f >= 900 && f <= 1100) {
    near1k.push({ t, m });
    if (m > maxMag) maxMag = m;
  }
}
const strong = near1k.filter((c) => c.m >= maxMag - 20);
const tMin = strong.length ? Math.min(...strong.map((c) => c.t)) : NaN;
const tMax = strong.length ? Math.max(...strong.map((c) => c.t)) : NaN;

check("produced points", out.point_count > 0 && out.num_columns > 0);
check("hop_seconds ~ 512/48000", Math.abs(out.hop_seconds - 512 / 48000) < 1e-6);
check("max_freq_hz ~ 24000", Math.abs(out.max_freq_hz - 24000) < 1);
check("tone energy present near 1 kHz", strong.length > 0);
check(
  `tone time in [0.3,1.2]s (got [${tMin.toFixed(3)},${tMax.toFixed(3)}]) — guards absTime`,
  tMin >= 0.3 && tMax <= 1.2,
);

process.exit(ok ? 0 : 1);

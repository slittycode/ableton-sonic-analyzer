const fs = require("fs");
const path = require("path");

const root = __dirname;
const slidesDir = path.join(root, "slides");
const previewsDir = path.join(root, "previews");
const pptxPath = path.join(root, "phase1_executive_deck_v2.pptx");
const viewerPath = path.join(root, "phase1_visual_story_v2.html");
const notesPath = path.join(root, "notes.md");

const PptxGenJS = require(path.join(root, "..", ".node", "node_modules", "pptxgenjs"));

const W = 1920;
const H = 1080;

const C = {
  bg: "#070B12",
  bg2: "#0E1422",
  panel: "#121A2A",
  panel2: "#0D1320",
  panel3: "#171F31",
  text: "#F4F7FB",
  soft: "#BBC6DB",
  muted: "#7E8AA4",
  line: "#27324A",
  lime: "#C9FF2F",
  limeDim: "#243A0A",
  cyan: "#6BD8FF",
  blue: "#7D97FF",
  ember: "#FFB357",
  red: "#FF6A62",
  gold: "#FFD368",
  forest: "#102513",
  wine: "#2A1517",
};

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function esc(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function attrs(map) {
  return Object.entries(map)
    .filter(([, value]) => value !== undefined && value !== null)
    .map(([key, value]) => `${key}="${esc(value)}"`)
    .join(" ");
}

function rect(x, y, w, h, options = {}) {
  return `<rect ${attrs({
    x,
    y,
    width: w,
    height: h,
    rx: options.rx || 0,
    ry: options.ry || options.rx || 0,
    fill: options.fill || "none",
    stroke: options.stroke,
    "stroke-width": options.strokeWidth,
    opacity: options.opacity,
  })} />`;
}

function line(x1, y1, x2, y2, options = {}) {
  return `<line ${attrs({
    x1,
    y1,
    x2,
    y2,
    stroke: options.stroke || C.line,
    "stroke-width": options.strokeWidth || 2,
    "stroke-dasharray": options.dash,
    opacity: options.opacity,
  })} />`;
}

function pathEl(d, options = {}) {
  return `<path ${attrs({
    d,
    fill: options.fill || "none",
    stroke: options.stroke,
    "stroke-width": options.strokeWidth,
    opacity: options.opacity,
    "stroke-linecap": options.linecap,
    "stroke-linejoin": options.linejoin,
    markerEnd: options.markerEnd,
    "stroke-dasharray": options.dash,
  })} />`;
}

function circle(cx, cy, r, options = {}) {
  return `<circle ${attrs({
    cx,
    cy,
    r,
    fill: options.fill || "none",
    stroke: options.stroke,
    "stroke-width": options.strokeWidth,
    opacity: options.opacity,
  })} />`;
}

function textBlock(x, y, lines, options = {}) {
  const fontSize = options.fontSize || 32;
  const lineHeight = options.lineHeight || fontSize * 1.22;
  const weight = options.weight || 500;
  const fill = options.fill || C.text;
  const anchor = options.anchor || "start";
  const family = options.family || "Avenir Next, Helvetica Neue, Arial, sans-serif";
  const letterSpacing = options.letterSpacing || 0;
  const opacity = options.opacity;
  const tspans = lines
    .map((lineText, index) => {
      const dy = index === 0 ? 0 : lineHeight;
      return `<tspan x="${x}" dy="${index === 0 ? 0 : dy}">${esc(lineText)}</tspan>`;
    })
    .join("");
  return `<text ${attrs({
    x,
    y,
    fill,
    "font-size": fontSize,
    "font-weight": weight,
    "font-family": family,
    "text-anchor": anchor,
    "letter-spacing": letterSpacing,
    opacity,
  })}>${tspans}</text>`;
}

function measureTextApprox(text, fontSize) {
  return text.length * fontSize * 0.54;
}

function chip(x, y, label, options = {}) {
  const fontSize = options.fontSize || 24;
  const paddingX = options.paddingX || 22;
  const width = options.width || Math.max(120, measureTextApprox(label, fontSize) + paddingX * 2);
  const height = options.height || 44;
  return `
    ${rect(x, y, width, height, {
      rx: height / 2,
      fill: options.fill || "#F1EEE6",
      stroke: options.stroke,
      strokeWidth: options.strokeWidth,
      opacity: options.opacity,
    })}
    ${textBlock(x + width / 2, y + 29, [label], {
      fontSize,
      weight: options.weight || 700,
      fill: options.text || "#10131A",
      anchor: "middle",
      letterSpacing: options.letterSpacing || 0.6,
    })}
  `;
}

function card(x, y, w, h, title, bodyLines, options = {}) {
  const fill = options.fill || C.panel;
  const stroke = options.stroke || C.line;
  const accent = options.accent || null;
  const body = Array.isArray(bodyLines) ? bodyLines : [bodyLines];
  return `
    ${rect(x, y, w, h, { rx: options.rx || 24, fill, stroke, strokeWidth: 2 })}
    ${accent ? rect(x + 18, y + 18, 180, 22, { rx: 11, fill: accent }) : ""}
    ${title ? textBlock(x + 28, y + (accent ? 88 : 56), [title], {
      fontSize: options.titleSize || 28,
      weight: 600,
      fill: options.titleColor || C.text,
    }) : ""}
    ${body.length ? textBlock(x + 28, y + (accent ? 132 : 102), body, {
      fontSize: options.bodySize || 21,
      weight: 450,
      fill: options.bodyColor || C.soft,
      lineHeight: options.lineHeight || 31,
    }) : ""}
  `;
}

function footerRefs(refs) {
  return textBlock(88, 1038, [refs], {
    fontSize: 16,
    weight: 500,
    fill: C.muted,
    letterSpacing: 0.2,
  });
}

function shell({ eyebrow, title, kicker, page, body, refs, bgGlow }) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="${C.bg}" />
      <stop offset="100%" stop-color="${C.bg2}" />
    </linearGradient>
    <linearGradient id="lineGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="${C.line}" />
      <stop offset="35%" stop-color="${C.cyan}" />
      <stop offset="70%" stop-color="${C.line}" />
      <stop offset="100%" stop-color="${C.line}" />
    </linearGradient>
    <radialGradient id="glowLime" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="${C.lime}" stop-opacity="0.24" />
      <stop offset="100%" stop-color="${C.lime}" stop-opacity="0" />
    </radialGradient>
    <radialGradient id="glowCyan" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="${C.cyan}" stop-opacity="0.2" />
      <stop offset="100%" stop-color="${C.cyan}" stop-opacity="0" />
    </radialGradient>
    <marker id="arrowHead" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">
      <path d="M0,0 L12,6 L0,12 z" fill="${C.cyan}" />
    </marker>
    <marker id="arrowHeadRed" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">
      <path d="M0,0 L12,6 L0,12 z" fill="${C.red}" />
    </marker>
  </defs>
  <rect width="${W}" height="${H}" fill="url(#bgGrad)" />
  <rect x="0" y="0" width="${W}" height="10" fill="${C.lime}" />
  <circle cx="1838" cy="66" r="6" fill="${C.blue}" />
  ${bgGlow || ""}
  <g opacity="0.11">
    ${Array.from({ length: 20 }, (_, i) => line(0, 120 + i * 48, W, 120 + i * 48, { stroke: C.line, strokeWidth: 1 })).join("")}
    ${Array.from({ length: 18 }, (_, i) => line(72 + i * 104, 0, 72 + i * 104, H, { stroke: C.line, strokeWidth: 1 })).join("")}
  </g>
  ${textBlock(92, 116, [eyebrow], { fontSize: 18, weight: 700, fill: C.muted, letterSpacing: 1.4 })}
  ${textBlock(92, 180, [title], { fontSize: 58, weight: 550, fill: C.text })}
  ${kicker ? textBlock(92, 244, [kicker], { fontSize: 25, weight: 450, fill: C.soft, lineHeight: 34 }) : ""}
  ${textBlock(1842, 120, [page], { fontSize: 22, weight: 700, fill: C.soft, anchor: "end", letterSpacing: 0.8 })}
  ${line(92, 206, 1828, 206, { stroke: "url(#lineGrad)", strokeWidth: 2 })}
  ${body}
  ${footerRefs(refs)}
</svg>`;
}

function flowBox(x, y, w, h, label, sublabel, fill, options = {}) {
  return `
    ${rect(x, y, w, h, { rx: 28, fill, stroke: options.stroke || C.line, strokeWidth: 2 })}
    ${options.chip ? chip(x + 22, y + 18, options.chip, { fill: options.chipFill || "#F1EEE6", text: options.chipText || "#11151D", fontSize: 20, height: 40 }) : ""}
    ${textBlock(x + 24, y + (options.chip ? 98 : 64), [label], { fontSize: options.labelSize || 42, weight: 600, fill: options.labelColor || C.text })}
    ${textBlock(x + 24, y + (options.chip ? 142 : 108), sublabel, { fontSize: options.bodySize || 20, weight: 450, fill: options.bodyColor || C.soft, lineHeight: options.lineHeight || 28 })}
  `;
}

function ghostPill(x, y, label) {
  return `
    ${rect(x, y, 356, 46, { rx: 12, fill: C.panel3, stroke: "#33405E", strokeWidth: 1.5, opacity: 0.96 })}
    ${textBlock(x + 20, y + 30, [label], { fontSize: 22, weight: 500, fill: "#AAB6CB" })}
  `;
}

function slide01() {
  const body = `
    ${rect(92, 292, 1736, 284, { rx: 36, fill: "#101826", stroke: "#1C2940", strokeWidth: 2 })}
    ${pathEl("M256 434 L330 434", { stroke: "#36445F", strokeWidth: 10, linecap: "round" })}
    ${pathEl("M626 434 L700 434", { stroke: C.cyan, strokeWidth: 10, linecap: "round" })}
    ${pathEl("M1030 434 L1104 434", { stroke: "#415278", strokeWidth: 10, linecap: "round" })}
    ${pathEl("M1412 434 L1486 434", { stroke: "#415278", strokeWidth: 10, linecap: "round" })}
    ${flowBox(120, 342, 210, 184, "Audio", ["Uploaded source track", "becomes a persisted", "runtime artifact."], "#1C2535", {
      chip: "INPUT",
      chipFill: "#182334",
      chipText: C.soft,
      labelSize: 40,
    })}
    ${flowBox(356, 318, 306, 232, "Measurement", ["Authoritative local DSP", "descriptors: tempo, key,", "loudness, stereo, structure."], C.lime, {
      chip: "TRUTH",
      labelColor: "#0B1405",
      bodyColor: "#18210B",
      chipFill: "#F1EEE6",
      labelSize: 50,
      bodySize: 23,
      lineHeight: 31,
    })}
    ${flowBox(694, 342, 294, 184, "Symbolic", ["Optional stem-aware note", "extraction. Useful,", "not authoritative."], C.blue, {
      chip: "OPTIONAL",
      chipFill: "#DCE3FF",
      chipText: "#18223E",
      labelSize: 42,
      bodySize: 21,
    })}
    ${flowBox(1122, 332, 292, 204, "Interpretation", ["AI advice is grounded on", "measurement. Symbolic", "only enriches it when present."], C.cyan, {
      chip: "GROUNDED",
      chipFill: "#E7FBFF",
      chipText: "#12222B",
      labelColor: "#10222A",
      bodyColor: "#19343E",
      labelSize: 42,
      bodySize: 21,
    })}
    ${flowBox(1518, 342, 252, 184, "Output", ["Measurement cards,", "musician panels,", "producer guidance."], "#1C2535", {
      chip: "PRODUCT",
      chipFill: "#182334",
      chipText: C.soft,
      labelSize: 40,
    })}
    ${card(92, 640, 538, 234, "What is solid", [
      "Canonical measurement is real, persisted, and",
      "consumed downstream. Tests prove the runtime strips",
      "leaked symbolic output before persistence."
    ], { fill: "#111A28", stroke: "#24334C", titleSize: 34, bodySize: 25, lineHeight: 34 })}
    ${card(650, 640, 580, 234, "What is constrained", [
      "Product-facing Phase 1 still mixes truth, compatibility,",
      "and optional symbolic projections into one user-visible",
      "concept. The code is cleaner than the product story."
    ], { fill: "#111A28", stroke: "#24334C", titleSize: 34, bodySize: 25, lineHeight: 34 })}
    ${card(1250, 640, 578, 234, "Best resource move", [
      "Fund contract cleanup before funding new detector work.",
      "The highest-value step is boundary repair, not capability",
      "sprawl."
    ], { fill: "#111A28", stroke: "#24334C", titleSize: 34, bodySize: 25, lineHeight: 34 })}
    ${chip(92, 928, "VERDICT: PARTIALLY REALIZED", { fill: C.red, text: "#FFFFFF", height: 56, fontSize: 24, width: 374 })}
    ${textBlock(494, 964, ["Phase 1 works; it is not yet a clean, finished phase contract."], { fontSize: 28, weight: 500, fill: C.text })}
  `;
  return shell({
    eyebrow: "EXECUTIVE READ-ONLY AUDIT",
    title: "Phase 1 has a real core. It does not yet have a clean boundary.",
    kicker: "This program measures first, interprets second. The strongest next investment is architectural cleanup, not detector sprawl.",
    page: "1 / 7",
    refs: "Grounded in analysis_runtime.py, server.py, analyze.py, analysisRunsClient.ts, and targeted backend tests.",
    bgGlow: `<circle cx="700" cy="360" r="320" fill="url(#glowLime)" /><circle cx="1240" cy="420" r="300" fill="url(#glowCyan)" />`,
    body,
  });
}

function slide02() {
  const body = `
    ${rect(92, 300, 920, 632, { rx: 32, fill: "#0F1624", stroke: C.cyan, strokeWidth: 3 })}
    ${textBlock(132, 362, ["CANONICAL PATH"], { fontSize: 22, weight: 700, fill: C.cyan, letterSpacing: 1.1 })}
    ${textBlock(132, 418, ["analysis-runs"], { fontSize: 54, weight: 550, fill: C.text })}
    ${flowBox(136, 474, 692, 132, "Measurement", ["Authoritative. Persisted after", "`transcriptionDetail` is stripped."], "#132212", {
      chip: "TRUTH",
      chipFill: C.lime,
      chipText: "#111714",
      labelSize: 44,
      bodySize: 22,
      bodyColor: "#C9D6C2",
    })}
    ${flowBox(136, 638, 692, 132, "Symbolic Extraction", ["Optional. Best-effort stage. Result lives", "separately from measurement."], "#11192C", {
      chip: "ADDITIVE",
      chipFill: C.blue,
      chipText: "#111926",
      labelSize: 42,
      bodySize: 22,
    })}
    ${flowBox(136, 802, 692, 132, "Interpretation", ["Grounded by authoritative measurement.", "Symbolic can enrich but does not become truth."], "#112632", {
      chip: "GROUNDED",
      chipFill: C.cyan,
      chipText: "#10222B",
      labelColor: C.text,
      bodySize: 22,
    })}
    ${pathEl("M836 702 L998 702", { stroke: "#40526F", strokeWidth: 14, linecap: "round", markerEnd: "url(#arrowHead)" })}
    ${textBlock(856, 664, ["UI projection"], { fontSize: 18, weight: 700, fill: C.muted, letterSpacing: 0.8 })}

    ${rect(1066, 300, 762, 632, { rx: 32, fill: "#201A12", stroke: C.ember, strokeWidth: 3 })}
    ${chip(1112, 334, "COMPATIBILITY", { fill: C.ember, text: "#16120D", height: 46, fontSize: 20, width: 210 })}
    ${textBlock(1112, 418, ["Legacy flat phase1 blob"], { fontSize: 54, weight: 550, fill: C.text })}
    ${card(1112, 468, 672, 346, "What still lives here", [
      "bpm",
      "key",
      "lufsIntegrated",
      "stereoDetail",
      "spectralBalance",
      "melodyDetail",
      "transcriptionDetail",
      "arrangementDetail",
      "segment data",
      "chord detail",
      "perceptual"
    ], { fill: "#181D2B", stroke: C.ember, titleSize: 34, bodySize: 24, lineHeight: 29 })}
    ${chip(1112, 850, "DO NOT EXPAND", { fill: C.red, text: "#FFFFFF", height: 54, fontSize: 22, width: 274 })}
    ${textBlock(1410, 885, ["Useful during migration. Wrong long-term center of gravity."], { fontSize: 24, weight: 500, fill: C.soft })}
  `;
  return shell({
    eyebrow: "ARCHITECTURE SPLIT",
    title: "Truth lives left. Compatibility lives right.",
    kicker: "The repo already has an authoritative stage model. The product still exposes a legacy flat mask alongside it.",
    page: "2 / 7",
    refs: "Observed in analysis_runtime.py:get_run, server.py:/api/analyze, and ui/services/analysisRunsClient.ts:projectPhase1FromRun.",
    bgGlow: `<circle cx="420" cy="670" r="360" fill="url(#glowCyan)" /><circle cx="1510" cy="670" r="280" fill="url(#glowLime)" />`,
    body,
  });
}

function slide03() {
  const cx = 960;
  const cy = 620;
  const body = `
    <circle cx="${cx}" cy="${cy}" r="216" fill="rgba(201,255,47,0.12)" stroke="${C.lime}" stroke-width="3" />
    <circle cx="${cx}" cy="${cy}" r="300" fill="none" stroke="${C.line}" stroke-width="2" stroke-dasharray="12 18" opacity="0.9" />
    ${rect(722, 528, 476, 212, { rx: 34, fill: "#12250F", stroke: C.lime, strokeWidth: 3 })}
    ${chip(774, 560, "AUTHORITATIVE", { fill: "#132313", text: C.lime, height: 42, fontSize: 20, width: 210 })}
    ${textBlock(774, 640, ["MEASUREMENT"], { fontSize: 68, weight: 600, fill: C.text, letterSpacing: 0.4 })}
    ${textBlock(774, 698, [
      "Deterministic local DSP and heuristic detector pass.",
      "This is the product's most solid technical core."
    ], { fontSize: 25, weight: 450, fill: "#D6E2CC", lineHeight: 34 })}

    ${card(174, 430, 420, 164, "Tempo / Meter", [
      "BPM, confidence, time signature,",
      "beat-grid signals"
    ], { fill: "#151C2B", stroke: C.cyan, titleSize: 34, bodySize: 24, lineHeight: 31 })}
    ${card(664, 326, 592, 138, "Loudness / Dynamics", [
      "LUFS, range, true peak, crest, dynamic character"
    ], { fill: "#182513", stroke: C.lime, titleSize: 34, bodySize: 23, lineHeight: 29 })}
    ${card(1350, 430, 394, 164, "Stereo / Spectral", [
      "width, correlation, spectral balance,",
      "spectral detail"
    ], { fill: "#151C2B", stroke: C.cyan, titleSize: 34, bodySize: 24, lineHeight: 31 })}
    ${card(174, 744, 442, 164, "Melody / Groove", [
      "melody detail, groove, sidechain,",
      "motion descriptors"
    ], { fill: "#17192B", stroke: C.blue, titleSize: 34, bodySize: 24, lineHeight: 31 })}
    ${card(698, 826, 520, 148, "Structure / Segments", [
      "sectioning, arrangement, segment loudness,",
      "spectral and key views"
    ], { fill: "#111B28", stroke: C.cyan, titleSize: 34, bodySize: 23, lineHeight: 30 })}
    ${card(1312, 760, 448, 172, "Type Detectors", [
      "acid, reverb, vocal, supersaw, bass,",
      "kick, genre, effects"
    ], { fill: "#221A11", stroke: C.ember, titleSize: 34, bodySize: 24, lineHeight: 31 })}

    ${pathEl("M596 514 L722 600", { stroke: "#31415D", strokeWidth: 3 })}
    ${pathEl("M960 466 L960 528", { stroke: "#42512A", strokeWidth: 3 })}
    ${pathEl("M1350 514 L1198 600", { stroke: "#31415D", strokeWidth: 3 })}
    ${pathEl("M616 808 L770 708", { stroke: "#31415D", strokeWidth: 3 })}
    ${pathEl("M960 740 L960 826", { stroke: "#42512A", strokeWidth: 3 })}
    ${pathEl("M1312 824 L1150 724", { stroke: "#31415D", strokeWidth: 3 })}
  `;
  return shell({
    eyebrow: "DESCRIPTOR ENGINE",
    title: "Measurement is a descriptor factory, not just tempo and key.",
    kicker: "Phase 1's real work is broad, local, and deterministic. That is why it remains the most defensible part of the stack.",
    page: "3 / 7",
    refs: "Observed in analyze.py detector and descriptor passes across tempo, tonal, loudness, stereo, structure, chord, perceptual, and detector families.",
    bgGlow: `<circle cx="960" cy="620" r="420" fill="url(#glowLime)" /><circle cx="420" cy="810" r="220" fill="url(#glowCyan)" />`,
    body,
  });
}

function slide04() {
  const body = `
    ${flowBox(120, 362, 308, 178, "stem_notes", ["User asks for symbolic", "extraction."], "#11192B", {
      chip: "REQUEST",
      chipFill: C.cyan,
      chipText: "#10222B",
      labelSize: 42,
      bodySize: 24,
    })}
    ${pathEl("M442 448 L598 448", { stroke: "#42506C", strokeWidth: 12, linecap: "round", markerEnd: "url(#arrowHead)" })}
    ${flowBox(630, 330, 338, 242, "analyze.py measurement", ["Loads audio", "Optional Demucs", "Detector pass", "Optional transcription"], "#1B202E", {
      chip: "MEASUREMENT",
      chipFill: "#101418",
      chipText: C.muted,
      labelSize: 40,
      bodySize: 22,
      lineHeight: 30,
      stroke: C.ember,
    })}
    ${pathEl("M986 448 L1142 448", { stroke: "#42506C", strokeWidth: 12, linecap: "round", markerEnd: "url(#arrowHead)" })}
    ${flowBox(1176, 352, 352, 198, "complete_measurement()", ["Persists canonical measurement and", "strips `transcriptionDetail` late."], "#132412", {
      chip: "PERSIST",
      chipFill: "#101418",
      chipText: C.muted,
      labelSize: 38,
      bodySize: 22,
      lineHeight: 30,
      stroke: C.lime,
    })}
    ${pathEl("M1546 448 L1700 448", { stroke: "#42506C", strokeWidth: 12, linecap: "round", markerEnd: "url(#arrowHead)" })}
    ${flowBox(1718, 344, 168, 214, "symbolic", ["worker", "can build stems", "and run", "analysis again"], "#141A2E", {
      chip: "FOLLOW-UP",
      chipFill: "#101418",
      chipText: C.muted,
      labelSize: 32,
      bodySize: 21,
      lineHeight: 28,
      stroke: C.blue,
    })}

    ${pathEl("M1710 596 C1670 700 1500 736 1420 660", { stroke: C.red, strokeWidth: 6, linecap: "round", linejoin: "round", markerEnd: "url(#arrowHeadRed)" })}
    ${textBlock(1480, 720, ["DUPLICATE COMPUTE"], { fontSize: 26, weight: 800, fill: C.red, letterSpacing: 1.0 })}
    ${textBlock(124, 748, ["YOU PAY TWICE"], { fontSize: 112, weight: 700, fill: C.red, letterSpacing: 1.4 })}
    ${card(120, 806, 540, 164, "Why this matters", [
      "Measurement is supposed to define truth.",
      "Right now it still performs symbolic-capable work",
      "and only sanitizes it at persistence time."
    ], { fill: "#191620", stroke: C.red, titleSize: 34, bodySize: 23, lineHeight: 31 })}
    ${card(690, 806, 540, 164, "Operational cost", [
      "If stems or transcription are rerun later, the system",
      "pays extra latency and compute for a boundary it is",
      "pretending is already clean."
    ], { fill: "#171B24", stroke: C.red, titleSize: 34, bodySize: 23, lineHeight: 31 })}
    ${card(1260, 806, 626, 164, "Best fix", [
      "Keep measurement measurement-only. Let symbolic own",
      "symbolic. Reuse stems instead of recomputing them."
    ], { fill: "#122312", stroke: C.lime, titleSize: 34, bodySize: 23, lineHeight: 31 })}
  `;
  return shell({
    eyebrow: "CRITICAL LEAK",
    title: "The pipeline cheats: symbolic work leaks into measurement, then runs again later.",
    kicker: "This is the most expensive fake cleanliness in Phase 1. The architecture looks cleaner than the execution path actually is.",
    page: "4 / 7",
    refs: "Observed in analysis_runtime.py:resolve_measurement_flags and complete_measurement, analyze.py optional transcription path, and server.py symbolic worker.",
    bgGlow: `<circle cx="1440" cy="350" r="280" fill="url(#glowCyan)" /><circle cx="360" cy="820" r="260" fill="url(#glowLime)" />`,
    body,
  });
}

function slide05() {
  const rows = [
    ["bpm", 12, C.lime],
    ["key", 10, C.cyan],
    ["lufsIntegrated", 8, C.blue],
    ["spectralBalance.subBass", 7, C.lime],
    ["grooveDetail.kickAccent", 6, C.cyan],
    ["stereoWidth", 5, C.blue],
  ];
  const bars = rows.map((row, index) => {
    const y = 402 + index * 92;
    const valueWidth = row[1] * 70;
    return `
      ${textBlock(138, y, [row[0]], { fontSize: 26, weight: 550, fill: C.text })}
      ${rect(542, y - 24, 878, 28, { rx: 14, fill: "#202A3D" })}
      ${rect(542, y - 24, valueWidth, 28, { rx: 14, fill: row[2] })}
      ${textBlock(1454, y, [String(row[1])], { fontSize: 28, weight: 700, fill: C.text })}
    `;
  }).join("");

  const body = `
    ${rect(92, 310, 1016, 648, { rx: 30, fill: "#0F1624", stroke: C.lime, strokeWidth: 3 })}
    ${textBlock(138, 370, ["The few fields that drive recommendations"], { fontSize: 40, weight: 600, fill: C.text })}
    ${textBlock(138, 406, ["Source: docs/field_utilization_report.md (24 recommendations, avg 2.3 sources each)"], { fontSize: 18, weight: 500, fill: C.muted })}
    ${bars}
    ${rect(134, 872, 930, 54, { rx: 16, fill: "#151C2B", stroke: "#2D3A54", strokeWidth: 2 })}
    ${textBlock(170, 907, ["A small measurement core drives most downstream value. Everything else should justify its cost."], { fontSize: 23, weight: 500, fill: C.soft })}

    ${rect(1140, 310, 688, 648, { rx: 30, fill: "#15181E", stroke: C.ember, strokeWidth: 3 })}
    ${textBlock(1188, 382, ["The bulk that looks important but is barely leveraged"], { fontSize: 40, weight: 600, fill: C.text })}
    ${[
      "bpmConfidence",
      "keyConfidence",
      "timeSignature",
      "lufsRange",
      "crestFactor",
      "stereoCorrelation",
      "transcriptionDetail.noteCount",
      "niche detector outputs"
    ].map((label, index) => ghostPill(1188, 450 + index * 64, label)).join("")}
    ${rect(1188, 892, 590, 62, { rx: 18, fill: "#201B15", stroke: C.ember, strokeWidth: 2 })}
    ${textBlock(1222, 930, ["Product implication: do not confuse descriptor volume with leverage."], { fontSize: 24, weight: 500, fill: "#F6DDB4" })}
  `;
  return shell({
    eyebrow: "SIGNAL VS PAYLOAD",
    title: "A few measurements do most of the work.",
    kicker: "The product emits a broad Phase 1 payload, but recommendation value is concentrated in a small set of fields.",
    page: "5 / 7",
    refs: "Grounded in docs/field_utilization_report.md, phase2Validator.ts, and ui/components/analysisResultsViewModel.ts.",
    bgGlow: `<circle cx="520" cy="620" r="320" fill="url(#glowLime)" /><circle cx="1510" cy="520" r="260" fill="url(#glowCyan)" />`,
    body,
  });
}

function slide06() {
  const q = (x, y, w, h, title, items, accent, fill) => `
    ${rect(x, y, w, h, { rx: 26, fill, stroke: accent, strokeWidth: 3 })}
    ${textBlock(x + 36, y + 78, [title], { fontSize: 42, weight: 650, fill: C.text })}
    ${textBlock(x + 36, y + 132, items, { fontSize: 28, weight: 500, fill: C.soft, lineHeight: 38 })}
  `;
  const body = `
    ${q(118, 332, 806, 288, "STABILIZE NOW", [
      "Clean measurement / symbolic boundary",
      "Canonical estimate flow",
      "Stem reuse"
    ], C.lime, "#12210F")}
    ${q(996, 332, 806, 288, "EXTEND NEXT", [
      "torchcrepe backend experiment",
      "Phase 1 evaluation pack",
      "Symbolic dependency policy"
    ], C.cyan, "#101A26")}
    ${q(118, 662, 806, 252, "STOP PRETENDING", [
      "More legacy wrapper surface",
      "More heuristic detector sprawl",
      "Product polish around ambiguous contracts"
    ], C.red, "#231518")}
    ${q(996, 662, 806, 252, "RESEARCH LATER", [
      "Beat / downbeat stack upgrade",
      "Deeper chord and structure work",
      "Additional symbolic backends"
    ], C.ember, "#231B11")}
    ${rect(648, 950, 626, 52, { rx: 18, fill: C.cyan })}
    ${textBlock(961, 985, ["Spending rule: stabilize the contract before buying more capability."], { fontSize: 24, weight: 600, fill: "#10222B", anchor: "middle" })}
  `;
  return shell({
    eyebrow: "RESOURCE ALLOCATION",
    title: "Where to spend resources.",
    kicker: "The next dollar should clean boundaries, establish product truth, and fund one decisive backend experiment. Not more sprawl.",
    page: "6 / 7",
    refs: "Prioritized from repo seams, field-utilization evidence, dependency health, and primary-source MIR tooling review.",
    bgGlow: `<circle cx="360" cy="430" r="240" fill="url(#glowLime)" /><circle cx="1540" cy="430" r="240" fill="url(#glowCyan)" />`,
    body,
  });
}

function slide07() {
  const lane = (x, y, w, h, label, bodyLines, fill, textColor = "#10141B") => `
    ${rect(x, y, w, h, { rx: 24, fill })}
    ${rect(x + 20, y + 18, 236, h - 36, { rx: 18, fill: "rgba(255,255,255,0.18)" })}
    ${textBlock(x + 48, y + 72, [label], { fontSize: 40, weight: 800, fill: textColor })}
    ${textBlock(x + 292, y + 52, bodyLines, { fontSize: 24, weight: 600, fill: textColor, lineHeight: 32 })}
  `;
  const body = `
    ${lane(118, 336, 1164, 124, "30 DAYS", [
      "Remove measurement-time transcription from symbolic-requested runs.",
      "Add a canonical estimate flow to analysis-runs."
    ], C.lime)}
    ${lane(118, 522, 1164, 124, "60 DAYS", [
      "Persist and reuse stems.",
      "Implement one torchcrepe backend experiment behind TranscriptionBackend."
    ], C.cyan)}
    ${lane(118, 708, 1164, 124, "90 DAYS", [
      "Tier or prune low-value Phase 1 fields.",
      "Make a go / no-go call on scaling symbolic extraction further."
    ], C.blue, "#F6FAFF")}

    ${card(1320, 360, 492, 258, "Final verdict", [
      "Phase 1 is only partially realized.",
      "",
      "The authoritative core is solid.",
      "The execution boundary is not yet clean.",
      "Spend on cleanup before expansion."
    ], { fill: "#191C27", stroke: C.red, titleSize: 42, bodySize: 28, lineHeight: 34, accent: "#F1EEE6" })}
    ${card(1320, 658, 492, 214, "What not to do", [
      "Do not redesign the whole product.",
      "Do not add more detector breadth until",
      "the Phase 1 contract is clean."
    ], { fill: "#181B23", stroke: C.ember, titleSize: 36, bodySize: 25, lineHeight: 34 })}
    ${rect(1364, 916, 396, 54, { rx: 18, fill: C.lime })}
    ${textBlock(1562, 951, ["Clean boundary. Reuse stems. Run one decisive experiment."], { fontSize: 21, weight: 700, fill: "#10141B", anchor: "middle" })}
  `;
  return shell({
    eyebrow: "EXECUTIVE CLOSE",
    title: "30 / 60 / 90 day priority path.",
    kicker: "This is a cleanup-first roadmap, not a rewrite roadmap.",
    page: "7 / 7",
    refs: "Synthesis of repo code, targeted tests, field-utilization analysis, and primary-source external tooling research.",
    bgGlow: `<circle cx="640" cy="520" r="300" fill="url(#glowLime)" /><circle cx="1580" cy="360" r="220" fill="url(#glowCyan)" />`,
    body,
  });
}

const slides = [
  { file: "slide-01-core-boundary.svg", svg: slide01() },
  { file: "slide-02-truth-vs-compatibility.svg", svg: slide02() },
  { file: "slide-03-measurement-engine.svg", svg: slide03() },
  { file: "slide-04-duplicate-work.svg", svg: slide04() },
  { file: "slide-05-value-density.svg", svg: slide05() },
  { file: "slide-06-resource-allocation.svg", svg: slide06() },
  { file: "slide-07-roadmap.svg", svg: slide07() },
];

function buildViewer() {
  const items = slides.map((slide, index) => `
    <section class="slide-shell" id="slide-${index + 1}">
      <div class="slide-meta">
        <div class="eyebrow">Phase 1 Executive Visual Story V2</div>
        <div class="title">${String(index + 1).padStart(2, "0")} / ${String(slides.length).padStart(2, "0")}</div>
      </div>
      <img src="./slides/${slide.file}" alt="Slide ${index + 1}" />
    </section>
  `).join("");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Phase 1 Executive Visual Story V2</title>
  <style>
    :root {
      --bg: #05070d;
      --text: #f4f7fb;
      --muted: #9cabc5;
      --line: #1a2235;
      --lime: #c9ff2f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Avenir Next", "Helvetica Neue", Arial, sans-serif;
      background:
        radial-gradient(circle at top, rgba(107, 216, 255, 0.08), transparent 24%),
        linear-gradient(180deg, #09101b 0%, var(--bg) 100%);
      color: var(--text);
    }
    header {
      position: sticky;
      top: 0;
      z-index: 20;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 18px 28px;
      border-bottom: 1px solid var(--line);
      background: rgba(5, 7, 13, 0.88);
      backdrop-filter: blur(18px);
    }
    header .left {
      display: flex;
      gap: 14px;
      align-items: baseline;
    }
    header .kicker {
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--muted);
    }
    header .headline {
      font-size: 18px;
      font-weight: 700;
    }
    header a {
      color: var(--lime);
      text-decoration: none;
      font-weight: 700;
    }
    main {
      padding: 32px 0 80px;
      display: grid;
      gap: 56px;
      justify-items: center;
    }
    .slide-shell {
      width: min(96vw, 1720px);
      display: grid;
      gap: 16px;
    }
    .slide-meta {
      display: flex;
      justify-content: space-between;
      align-items: center;
      color: var(--muted);
      font-size: 13px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    .slide-shell img {
      width: 100%;
      border-radius: 28px;
      border: 1px solid #1f2a41;
      box-shadow: 0 28px 80px rgba(0, 0, 0, 0.45);
      background: #0a0d14;
    }
  </style>
</head>
<body>
  <header>
    <div class="left">
      <div class="kicker">CEO Visual Story</div>
      <div class="headline">Phase 1: what the system actually does</div>
    </div>
    <a href="./phase1_executive_deck_v2.pptx">Open PPTX</a>
  </header>
  <main>${items}</main>
</body>
</html>`;
}

function buildNotes() {
  return `# Phase 1 Executive Visual Story V2

Artifacts in this folder:

- \`slides/\`: master SVG slides
- \`phase1_visual_story_v2.html\`: browser viewer for the SVG story
- \`phase1_executive_deck_v2.pptx\`: PowerPoint deck built from the SVG masters
- \`previews/\`: PNG previews rendered from the SVG masters

Design intent:

- one idea per slide
- large typography and sparse copy
- canonical measurement rendered as the stable truth layer
- legacy compatibility rendered as caution / drag
- duplicate symbolic work framed as the central money leak
- resource allocation framed explicitly for executive review
`;
}

async function buildPptx() {
  const pptx = new PptxGenJS();
  pptx.layout = "LAYOUT_WIDE";
  pptx.author = "OpenAI Codex";
  pptx.company = "ASA advisory";
  pptx.subject = "Phase 1 executive visual story";
  pptx.title = "Phase 1 Executive Visual Story V2";
  pptx.lang = "en-US";

  slides.forEach((slideSpec) => {
    const slide = pptx.addSlide();
    slide.background = { color: C.bg };
    slide.addImage({
      path: path.join(slidesDir, slideSpec.file),
      x: 0,
      y: 0,
      w: 13.333,
      h: 7.5,
    });
  });

  await pptx.writeFile({ fileName: pptxPath });
}

async function main() {
  ensureDir(slidesDir);
  ensureDir(previewsDir);

  for (const slide of slides) {
    fs.writeFileSync(path.join(slidesDir, slide.file), slide.svg, "utf8");
  }

  fs.writeFileSync(viewerPath, buildViewer(), "utf8");
  fs.writeFileSync(notesPath, buildNotes(), "utf8");
  await buildPptx();

  console.log(`Wrote ${slides.length} SVG slides to ${slidesDir}`);
  console.log(`Wrote browser viewer to ${viewerPath}`);
  console.log(`Wrote PPTX to ${pptxPath}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

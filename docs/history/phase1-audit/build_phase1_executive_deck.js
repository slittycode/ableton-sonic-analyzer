const path = require("path");
const PptxGenJS = require("./.node/node_modules/pptxgenjs");

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "OpenAI Codex";
pptx.company = "ASA advisory";
pptx.subject = "Phase 1 read-only audit executive deck";
pptx.title = "ASA Phase 1 Executive Audit";
pptx.lang = "en-US";
pptx.theme = {
  headFontFace: "Aptos Display",
  bodyFontFace: "Aptos",
  lang: "en-US",
};

const W = 13.333;
const H = 7.5;

const BG = "111318";
const PANEL = "181C24";
const PANEL_2 = "202631";
const TEXT = "F5F2E8";
const MUTED = "97A0AB";
const SLATE = "344050";
const LIME = "B6FF2B";
const CYAN = "52C8FF";
const BLUE = "6D8DFF";
const AMBER = "FFB54C";
const RED = "FF6363";
const OFFWHITE = "ECE7DD";

const TOTAL_SLIDES = 8;

function addBg(slide) {
  slide.background = { color: BG };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: W,
    h: H,
    line: { color: BG, pt: 0 },
    fill: { color: BG },
  });
}

function addHeader(slide, kicker, title, idx) {
  addBg(slide);
  slide.addText(kicker.toUpperCase(), {
    x: 0.62,
    y: 0.34,
    w: 4.6,
    h: 0.22,
    fontFace: "Aptos",
    fontSize: 9,
    bold: true,
    color: MUTED,
    charSpace: 1.4,
  });
  slide.addText(title, {
    x: 0.62,
    y: 0.56,
    w: 10.8,
    h: 0.48,
    fontFace: "Aptos Display",
    fontSize: 23,
    bold: true,
    color: TEXT,
  });
  slide.addText(`${idx}/${TOTAL_SLIDES}`, {
    x: 12.2,
    y: 0.34,
    w: 0.48,
    h: 0.2,
    align: "right",
    fontFace: "Aptos",
    fontSize: 9,
    color: MUTED,
  });
  slide.addShape(pptx.ShapeType.line, {
    x: 0.62,
    y: 1.12,
    w: 12.06,
    h: 0,
    line: { color: SLATE, pt: 1 },
  });
  slide.addText("Grounded in repo code, tests, and primary-source tool research", {
    x: 0.62,
    y: 7.08,
    w: 6.5,
    h: 0.18,
    fontFace: "Aptos",
    fontSize: 8,
    color: MUTED,
  });
}

function panel(slide, x, y, w, h, opts = {}) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: 0.08,
    fill: { color: opts.fill || PANEL, transparency: opts.transparency || 0 },
    line: { color: opts.line || SLATE, pt: opts.pt || 1.2 },
  });
}

function pill(slide, x, y, w, h, text, color, textColor = BG) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: 0.09,
    fill: { color },
    line: { color, pt: 0.5 },
  });
  slide.addText(text, {
    x,
    y: y + 0.01,
    w,
    h,
    align: "center",
    valign: "mid",
    fontFace: "Aptos",
    fontSize: 9,
    bold: true,
    color: textColor,
  });
}

function block(slide, x, y, w, h, heading, body, opts = {}) {
  panel(slide, x, y, w, h, {
    fill: opts.fill || PANEL,
    line: opts.line || (opts.fill || PANEL_2),
    pt: opts.pt || 1.2,
  });
  if (opts.label) {
    pill(slide, x + 0.14, y + 0.12, Math.min(1.55, w - 0.28), 0.28, opts.label, opts.labelColor || CYAN, BG);
  }
  slide.addText(heading, {
    x: x + 0.16,
    y: y + (opts.label ? 0.5 : 0.18),
    w: w - 0.32,
    h: 0.34,
    fontFace: "Aptos Display",
    fontSize: opts.headingSize || 15,
    bold: true,
    color: opts.headingColor || TEXT,
  });
  slide.addText(body, {
    x: x + 0.16,
    y: y + (opts.label ? 0.88 : 0.56),
    w: w - 0.32,
    h: h - (opts.label ? 1.02 : 0.72),
    fontFace: "Aptos",
    fontSize: opts.bodySize || 10.5,
    color: opts.bodyColor || OFFWHITE,
    breakLine: false,
    valign: "top",
    margin: 0,
  });
}

function arrow(slide, x, y, w, h, color = SLATE) {
  slide.addShape(pptx.ShapeType.chevron, {
    x,
    y,
    w,
    h,
    fill: { color },
    line: { color, pt: 0.5 },
  });
}

function smallNote(slide, x, y, w, text, color = MUTED, size = 8.5, align = "left") {
  slide.addText(text, {
    x,
    y,
    w,
    h: 0.28,
    fontFace: "Aptos",
    fontSize: size,
    color,
    align,
    margin: 0,
  });
}

function addFlowBlock(slide, x, y, w, h, title, subtitle, color, tag, textColor = TEXT) {
  block(slide, x, y, w, h, title, subtitle, {
    fill: color,
    line: color,
    label: tag,
    labelColor: textColor === BG ? TEXT : BG,
    headingColor: textColor,
    bodyColor: textColor,
    headingSize: 13.5,
    bodySize: 9.8,
  });
}

function bar(slide, x, y, label, value, maxValue, color) {
  slide.addText(label, {
    x,
    y,
    w: 2.2,
    h: 0.22,
    fontFace: "Aptos",
    fontSize: 10,
    color: OFFWHITE,
    margin: 0,
  });
  slide.addShape(pptx.ShapeType.roundRect, {
    x: x + 2.25,
    y: y + 0.03,
    w: 3.85,
    h: 0.18,
    rectRadius: 0.04,
    fill: { color: PANEL_2 },
    line: { color: PANEL_2, pt: 0.4 },
  });
  slide.addShape(pptx.ShapeType.roundRect, {
    x: x + 2.25,
    y: y + 0.03,
    w: (3.85 * value) / maxValue,
    h: 0.18,
    rectRadius: 0.04,
    fill: { color },
    line: { color, pt: 0.4 },
  });
  slide.addText(String(value), {
    x: x + 6.2,
    y,
    w: 0.45,
    h: 0.22,
    fontFace: "Aptos",
    fontSize: 10,
    bold: true,
    color: TEXT,
    align: "right",
    margin: 0,
  });
}

function chip(slide, x, y, w, text, fill, border = fill, textColor = BG) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h: 0.34,
    rectRadius: 0.08,
    fill: { color: fill },
    line: { color: border, pt: 0.4 },
  });
  slide.addText(text, {
    x,
    y: y + 0.01,
    w,
    h: 0.3,
    fontFace: "Aptos",
    fontSize: 8.8,
    color: textColor,
    bold: true,
    align: "center",
    margin: 0,
  });
}

function addDeckTitle(slide) {
  addHeader(slide, "Executive read-only audit", "Phase 1: What the system actually does", 1);

  const y = 2.0;
  const h = 1.38;
  const w = 2.16;
  const xs = [0.62, 3.02, 5.42, 7.82, 10.22];
  addFlowBlock(slide, xs[0], y, w, h, "Audio Input", "Uploaded source track becomes a persisted runtime artifact.", PANEL_2, "START");
  arrow(slide, 2.77, 2.43, 0.18, 0.44, SLATE);
  addFlowBlock(slide, xs[1], y, w, h, "Measurement", "Authoritative local DSP descriptors: tempo, key, loudness, stereo, structure, detectors.", LIME, "TRUTH", BG);
  arrow(slide, 5.17, 2.43, 0.18, 0.44, SLATE);
  addFlowBlock(slide, xs[2], y, w, h, "Symbolic", "Optional stem-aware note extraction. Best-effort. Not authoritative measurement.", BLUE, "OPTIONAL");
  arrow(slide, 7.57, 2.43, 0.18, 0.44, SLATE);
  addFlowBlock(slide, xs[3], y, w, h, "Interpretation", "AI prompt is grounded on measurement, with symbolic added only when available.", CYAN, "GROUNDED", BG);
  arrow(slide, 9.97, 2.43, 0.18, 0.44, SLATE);
  addFlowBlock(slide, xs[4], y, w, h, "Producer Output", "Measurement cards, musician views, and producer-facing advisory text.", PANEL_2, "UI");

  block(slide, 0.62, 4.2, 4.0, 1.35, "What is solid", "Canonical measurement is real, persisted, and downstream-consumed. Tests prove it strips leaked symbolic output before persistence.", {
    fill: PANEL,
    line: SLATE,
    label: "OBSERVED",
    labelColor: BG,
  });
  block(slide, 4.66, 4.2, 4.0, 1.35, "What is constrained", "Product-facing Phase 1 still mixes truth, compatibility, and optional symbolic projections into one user-visible concept.", {
    fill: PANEL,
    line: SLATE,
    label: "LIMIT",
    labelColor: BG,
  });
  block(slide, 8.7, 4.2, 4.01, 1.35, "Best resource move", "Clean the measurement boundary before extending capability. The highest-value work is architecture cleanup, not more detectors.", {
    fill: PANEL,
    line: SLATE,
    label: "NEXT",
    labelColor: BG,
  });

  pill(slide, 0.62, 6.04, 2.3, 0.34, "Verdict: partially realized", RED, TEXT);
  smallNote(slide, 3.05, 6.06, 5.8, "Phase 1 works; it is not yet a clean, finished phase contract.", OFFWHITE, 11);
}

function addTruthVsCompatibility(slide) {
  addHeader(slide, "Architecture split", "Where truth lives vs where compatibility lives", 2);

  panel(slide, 0.62, 1.5, 5.9, 5.1, { fill: PANEL, line: CYAN, pt: 1.4 });
  smallNote(slide, 0.92, 1.72, 2.2, "CANONICAL PATH", CYAN, 9.5);
  slide.addText("analysis-runs", {
    x: 0.92,
    y: 1.97,
    w: 2.7,
    h: 0.3,
    fontFace: "Aptos Display",
    fontSize: 18,
    bold: true,
    color: TEXT,
  });
  block(slide, 1.05, 2.45, 5.04, 0.92, "Measurement", "Authoritative. Persisted after `transcriptionDetail` is stripped.", {
    fill: "152018",
    line: LIME,
    label: "LAYER 1",
    labelColor: BG,
  });
  block(slide, 1.05, 3.58, 5.04, 0.92, "Symbolic Extraction", "Optional. Best-effort stage. Its result lives separately from measurement.", {
    fill: "171B29",
    line: BLUE,
    label: "LAYER 2",
    labelColor: BG,
  });
  block(slide, 1.05, 4.71, 5.04, 0.92, "Interpretation", "Grounded by authoritative measurement. Symbolic is additive, not promoted to truth.", {
    fill: "16222B",
    line: CYAN,
    label: "LAYER 3",
    labelColor: BG,
  });
  smallNote(slide, 1.05, 5.98, 4.8, "Evidence: analysis_runtime.py, server.py, analysisRunsClient.ts", MUTED, 8.2);

  panel(slide, 6.82, 1.5, 5.9, 5.1, { fill: PANEL, line: AMBER, pt: 1.4 });
  pill(slide, 7.12, 1.72, 1.7, 0.3, "COMPATIBILITY", AMBER, BG);
  slide.addText("Legacy flat phase1 blob", {
    x: 7.12,
    y: 1.97,
    w: 3.9,
    h: 0.3,
    fontFace: "Aptos Display",
    fontSize: 18,
    bold: true,
    color: TEXT,
  });
  block(slide, 7.12, 2.46, 5.3, 3.7, "What still lives here", "bpm\nkey\nlufsIntegrated\nstereoDetail\nspectralBalance\nmelodyDetail\ntranscriptionDetail\narrangementDetail\nsegment data\nchord detail\nperceptual", {
    fill: PANEL_2,
    line: AMBER,
    headingSize: 13.5,
    bodySize: 10.5,
  });
  pill(slide, 7.12, 5.82, 2.05, 0.3, "DO NOT EXPAND", RED, TEXT);
  smallNote(slide, 9.34, 5.84, 3.1, "Useful during migration. Wrong long-term center of gravity.", OFFWHITE, 8.8);

  slide.addShape(pptx.ShapeType.chevron, {
    x: 6.1,
    y: 3.5,
    w: 0.42,
    h: 0.62,
    fill: { color: SLATE },
    line: { color: SLATE, pt: 0.5 },
  });
  smallNote(slide, 5.42, 3.16, 1.1, "UI projection", MUTED, 8.4, "center");
}

function addMeasurementAnatomy(slide) {
  addHeader(slide, "Descriptor engine", "What measurement really computes", 3);

  const cx = 4.95;
  const cy = 2.62;
  const cw = 3.42;
  const ch = 1.48;
  block(slide, cx, cy, cw, ch, "MEASUREMENT", "Deterministic local DSP and heuristic detector pass. This is the product's most solid technical core.", {
    fill: "182613",
    line: LIME,
    label: "AUTHORITATIVE CORE",
    labelColor: BG,
    headingSize: 20,
    bodySize: 10.2,
  });

  const nodes = [
    [0.8, 1.7, "Tempo / Meter", "BPM, confidence, time signature, beat-grid signals", CYAN],
    [4.6, 1.35, "Loudness / Dynamics", "LUFS, range, true peak, crest, dynamic character", LIME],
    [8.6, 1.7, "Stereo / Spectral", "width, correlation, spectral balance, spectral detail", CYAN],
    [0.8, 4.45, "Melody / Groove", "melody detail, groove, sidechain, motion descriptors", BLUE],
    [4.6, 4.85, "Structure / Segments", "sectioning, arrangement, segment loudness, spectral and key views", CYAN],
    [8.6, 4.45, "Type Detectors", "acid, reverb, vocal, supersaw, bass, kick, genre, effects", AMBER],
  ];
  for (const [x, y, title, body, color] of nodes) {
    block(slide, x, y, 3.1, 1.05, title, body, {
      fill: PANEL,
      line: color,
      headingSize: 13,
      bodySize: 9.2,
    });
  }

  const links = [
    [3.9, 2.5, 1.05, 0.66],
    [6.95, 2.16, -0.58, 0.95],
    [3.9, 5.0, 1.08, -0.56],
    [6.95, 5.0, -0.58, -0.54],
    [6.25, 2.55, 0, -0.9],
    [6.25, 4.12, 0, 0.7],
  ];
  for (const [x, y, w, h] of links) {
    slide.addShape(pptx.ShapeType.line, {
      x,
      y,
      w,
      h,
      line: { color: SLATE, pt: 1.1 },
    });
  }

  smallNote(slide, 0.8, 6.08, 11.7, "Observed in analyze.py: tempo, tonal, loudness, stereo, structure, chord, perceptual, and detector families all run in the measurement subprocess.", MUTED, 8.4);
}

function addPipelineCheat(slide) {
  addHeader(slide, "Critical gap", "Where the pipeline cheats", 4);

  pill(slide, 0.78, 1.62, 1.45, 0.3, "REQUEST", CYAN, BG);
  block(slide, 0.78, 1.95, 2.22, 1.1, "stem_notes", "User asks for symbolic extraction.", {
    fill: PANEL,
    line: CYAN,
    headingSize: 18,
    bodySize: 10,
  });

  arrow(slide, 3.16, 2.3, 0.28, 0.42, SLATE);
  block(slide, 3.56, 1.65, 2.88, 1.74, "analyze.py measurement", "Loads audio\nOptional Demucs\nDetector pass\nOptional transcription", {
    fill: PANEL_2,
    line: AMBER,
    label: "MIXED EXECUTION",
    labelColor: BG,
    headingSize: 15,
  });

  arrow(slide, 6.6, 2.3, 0.28, 0.42, SLATE);
  block(slide, 7.0, 1.8, 2.72, 1.45, "complete_measurement()", "Persists canonical measurement and strips `transcriptionDetail` late.", {
    fill: "182613",
    line: LIME,
    label: "BOUNDARY ENFORCED HERE",
    labelColor: BG,
    headingSize: 14,
  });

  arrow(slide, 9.87, 2.3, 0.28, 0.42, SLATE);
  block(slide, 10.27, 1.65, 2.28, 1.74, "symbolic worker", "Can materialize stems and run `analyze_transcription()` again.", {
    fill: "1A1D2B",
    line: BLUE,
    label: "SECOND PASS",
    labelColor: BG,
    headingSize: 15,
  });

  slide.addShape(pptx.ShapeType.circularArrow, {
    x: 9.86,
    y: 3.72,
    w: 1.42,
    h: 1.18,
    fill: { color: "2A1111", transparency: 20 },
    line: { color: RED, pt: 1.4 },
  });
  slide.addText("Duplicate compute", {
    x: 10.02,
    y: 4.12,
    w: 1.1,
    h: 0.26,
    align: "center",
    fontFace: "Aptos",
    fontSize: 9,
    bold: true,
    color: RED,
    margin: 0,
  });

  block(slide, 0.78, 4.78, 3.88, 1.16, "Why this matters", "Measurement is supposed to define truth. Right now it still performs symbolic work upstream and sanitizes it only at persistence time.", {
    fill: PANEL,
    line: RED,
    headingSize: 14,
    bodySize: 10,
  });
  block(slide, 4.74, 4.78, 3.88, 1.16, "Operational cost", "If stems or transcription are rerun later, the system pays extra latency and compute for a contract boundary it is pretending is already clean.", {
    fill: PANEL,
    line: RED,
    headingSize: 14,
    bodySize: 10,
  });
  block(slide, 8.7, 4.78, 3.86, 1.16, "Best fix", "Keep measurement measurement-only. Let symbolic own symbolic. Reuse stems instead of recomputing them.", {
    fill: PANEL,
    line: LIME,
    headingSize: 14,
    bodySize: 10,
  });
}

function addUsefulness(slide) {
  addHeader(slide, "Signal vs payload", "What downstream actually uses", 5);

  panel(slide, 0.62, 1.52, 7.08, 4.94, { fill: PANEL, line: LIME, pt: 1.2 });
  slide.addText("Top fields cited in recommendations", {
    x: 0.9,
    y: 1.8,
    w: 3.8,
    h: 0.3,
    fontFace: "Aptos Display",
    fontSize: 17,
    bold: true,
    color: TEXT,
  });
  smallNote(slide, 0.92, 2.09, 4.7, "Source: docs/field_utilization_report.md (24 recs, avg 2.3 sources)", MUTED, 8.5);

  const bars = [
    ["bpm", 12, LIME],
    ["key", 10, CYAN],
    ["lufsIntegrated", 8, BLUE],
    ["spectralBalance.subBass", 7, LIME],
    ["grooveDetail.kickAccent", 6, CYAN],
    ["stereoWidth", 5, BLUE],
  ];
  let by = 2.55;
  for (const [label, value, color] of bars) {
    bar(slide, 0.98, by, label, value, 12, color);
    by += 0.54;
  }

  block(slide, 0.94, 5.72, 6.0, 0.5, "Read the pattern", "A small measurement core drives most real downstream value. Everything else should justify its cost.", {
    fill: PANEL_2,
    line: SLATE,
    headingSize: 11.5,
    bodySize: 9.3,
  });

  panel(slide, 7.98, 1.52, 4.7, 4.94, { fill: PANEL, line: AMBER, pt: 1.2 });
  slide.addText("Fields that look important but are barely leveraged", {
    x: 8.26,
    y: 1.8,
    w: 4.1,
    h: 0.44,
    fontFace: "Aptos Display",
    fontSize: 16,
    bold: true,
    color: TEXT,
  });
  const unused = [
    "bpmConfidence",
    "keyConfidence",
    "timeSignature",
    "lufsRange",
    "crestFactor",
    "stereoCorrelation",
    "transcriptionDetail.noteCount",
    "sidechainDetail.pumpingConfidence",
  ];
  let uy = 2.45;
  for (const item of unused) {
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 8.26,
      y: uy,
      w: 3.95,
      h: 0.35,
      rectRadius: 0.05,
      fill: { color: PANEL_2 },
      line: { color: SLATE, pt: 0.5 },
    });
    slide.addText(item, {
      x: 8.42,
      y: uy + 0.05,
      w: 3.5,
      h: 0.22,
      fontFace: "Aptos",
      fontSize: 9.4,
      color: OFFWHITE,
      margin: 0,
    });
    uy += 0.46;
  }
  block(slide, 8.26, 5.72, 3.95, 0.5, "Implication", "Do not confuse descriptor volume with product leverage.", {
    fill: PANEL_2,
    line: AMBER,
    headingSize: 11.5,
    bodySize: 9.2,
  });
}

function addBottlenecks(slide) {
  addHeader(slide, "Constraint board", "Why Phase 1 is constrained today", 6);

  const titles = [
    ["Boundary leakage", "Measurement still performs symbolic work, then strips it late.", RED],
    ["Dependency fragility", "Demucs is frozen upstream. Basic Pitch legacy is awkward on macOS arm64.", AMBER],
    ["Weak handoffs", "Interpretation can run before symbolic completes, even when symbolic was requested.", RED],
    ["Field bloat", "Many emitted fields add payload weight but not proportional downstream value.", AMBER],
    ["Contract drift", "Fast mode docs, legacy estimate flow, and multiple Phase 1 meanings create confusion.", RED],
  ];

  let x = 0.62;
  for (const [title, body, color] of titles) {
    block(slide, x, 1.72, 2.28, 4.88, title, body, {
      fill: PANEL,
      line: color,
      label: color === RED ? "HIGH" : "MEDIUM",
      labelColor: TEXT,
      headingSize: 14,
      bodySize: 10,
    });
    x += 2.53;
  }

  smallNote(slide, 0.78, 6.08, 11.4, "These are mostly architecture, handoff, and product-shape constraints. They are not evidence that local measurement itself is failing.", OFFWHITE, 9.4);
}

function addInvestmentMatrix(slide) {
  addHeader(slide, "Resource allocation", "Where to spend resources", 7);

  const q = [
    [0.72, 1.6, 5.92, 2.27, "STABILIZE NOW", "Clean measurement boundary\nCanonical estimate flow\nStem reuse", "182613", LIME],
    [6.74, 1.6, 5.88, 2.27, "EXTEND NEXT", "torchcrepe backend experiment\nPhase 1 evaluation pack\nSymbolic dependency policy", "16222B", CYAN],
    [0.72, 4.0, 5.92, 2.27, "STOP PRETENDING", "More legacy wrapper surface\nMore detector sprawl\nProduct polish around ambiguous contracts", "281818", RED],
    [6.74, 4.0, 5.88, 2.27, "RESEARCH LATER", "Beat/downbeat stack upgrade\nDeeper chord or structure work\nAdditional symbolic backends", "2A2415", AMBER],
  ];
  for (const [x, y, w, h, title, body, fill, line] of q) {
    block(slide, x, y, w, h, title, body, {
      fill,
      line,
      headingSize: 17,
      bodySize: 11,
    });
  }

  pill(slide, 4.28, 6.58, 4.75, 0.34, "Spending rule: stabilize the contract before buying more capability", CYAN, BG);
}

function addRoadmap(slide) {
  addHeader(slide, "Executive close", "30 / 60 / 90 day priority path", 8);

  const bands = [
    [1.55, "30 DAYS", "Remove measurement-time transcription from the symbolic-requested path.\nAdd a canonical estimate flow to analysis-runs.", LIME, BG],
    [3.2, "60 DAYS", "Persist and reuse stems.\nImplement one torchcrepe backend experiment behind TranscriptionBackend.", CYAN, BG],
    [4.85, "90 DAYS", "Tier or prune low-value Phase 1 fields.\nMake a go/no-go call on scaling symbolic extraction further.", BLUE, TEXT],
  ];
  for (const [y, label, body, color, textColor] of bands) {
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 0.78,
      y,
      w: 8.18,
      h: 1.18,
      rectRadius: 0.07,
      fill: { color },
      line: { color, pt: 0.8 },
    });
    slide.addText(label, {
      x: 1.06,
      y: y + 0.18,
      w: 1.36,
      h: 0.24,
      fontFace: "Aptos Display",
      fontSize: 16,
      bold: true,
      color: textColor,
      margin: 0,
    });
    slide.addText(body, {
      x: 2.55,
      y: y + 0.14,
      w: 5.98,
      h: 0.78,
      fontFace: "Aptos",
      fontSize: 11,
      color: textColor,
      margin: 0,
      valign: "mid",
    });
  }

  block(slide, 9.32, 1.78, 3.1, 2.1, "Final verdict", "Phase 1 is only partially realized.\n\nThe authoritative core is solid.\nThe execution boundary is not yet clean.\nThe next dollars should fund cleanup before expansion.", {
    fill: PANEL,
    line: RED,
    label: "VERDICT",
    labelColor: TEXT,
    headingSize: 19,
    bodySize: 12,
  });

  block(slide, 9.32, 4.15, 3.1, 1.65, "What not to do", "Do not redesign the whole product.\nDo not add more detector breadth until the Phase 1 contract is clean.", {
    fill: PANEL,
    line: AMBER,
    headingSize: 15,
    bodySize: 10.5,
  });

  pill(slide, 9.32, 6.12, 3.1, 0.34, "Clean boundary. Reuse stems. Run one decisive experiment.", LIME, BG);
}

async function main() {
  addDeckTitle(pptx.addSlide());
  addTruthVsCompatibility(pptx.addSlide());
  addMeasurementAnatomy(pptx.addSlide());
  addPipelineCheat(pptx.addSlide());
  addUsefulness(pptx.addSlide());
  addBottlenecks(pptx.addSlide());
  addInvestmentMatrix(pptx.addSlide());
  addRoadmap(pptx.addSlide());

  const outputPath = path.join(__dirname, "phase1_executive_deck.pptx");
  await pptx.writeFile({ fileName: outputPath });
  console.log(outputPath);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

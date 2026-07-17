/**
 * patchSmith — downloadable Vital (`.vital`) synth presets derived from Phase 1
 * synthesis measurements.
 *
 * FROZEN 2026-07 (trust diet): default-off/non-goal. Do not expand without the
 * owner naming this subsystem. See plans/trust-diet-2026-07.md.
 *
 * Why this exists (PURPOSE.md): ASA answers "how do I make something that sounds
 * like this?". A citable, downloadable preset turns measured synthesis character
 * into a concrete starting point the producer can load and play.
 *
 * Two invariants shape every line here:
 *   #2 (chain of custody): every parameter we set cites the exact Phase 1
 *      measurement(s) that justify it. No measurement → no bound parameter.
 *   #4 (honest uncertainty): SynthesisCharacter carries no confidence and several
 *      source fields are nullable, so a parameter whose evidence is weak or
 *      missing is either skipped or set to a conservative default *and disclosed*
 *      as a hedge. A preset is binary; the manifest is where the honesty lives.
 *
 * Format: a `.vital` file is JSON. Vital's loader (`load_save.cpp jsonToState`)
 * applies the `settings` control map and *retains init defaults* for any absent
 * `wavetables` / `modulations` / `lfos` / `sample` arrays — so an override-only
 * settings object loads cleanly on Vital's init wavetables. We therefore shape
 * the synthesis *character* via core controls (unison, filter, amp envelope, sub
 * layer) rather than embedding custom wavetables; wavetable authoring from
 * odd/even + inharmonicity is a documented v2 follow-up.
 *
 * Vital control units (from synth_parameters.cpp ValueDetails) are encoded in the
 * mapping helpers below: env times use seconds = value^4; filter cutoff is in
 * semitones where freq = 440·2^((s−69)/12).
 */

import type { Phase1Result } from "../types";

export type PatchConfidence = "HIGH" | "MED" | "LOW";

/** One Vital control we set, with its measurement provenance (invariant #2). */
export interface PatchParameterCitation {
  /** Human-readable label, e.g. "Unison voices". */
  label: string;
  /** Vital control name written to `settings`, e.g. "osc_1_unison_voices". */
  vitalParam: string;
  /** Value written to the preset, in Vital's units. */
  value: number;
  /** Musically-meaningful display of that value, e.g. "7 voices", "180 ms". */
  display: string;
  /** Dotted Phase 1 paths this value is derived from. */
  phase1Fields: string[];
  /** Why this value, citing the measurement. */
  rationale: string;
  /** Honest confidence of the derivation (invariant #4). */
  confidence: PatchConfidence;
}

export interface PatchManifest {
  presetName: string;
  /** Parameters set with measurement provenance. */
  citations: PatchParameterCitation[];
  /** Honest-uncertainty disclosures for low-confidence / defaulted derivations. */
  hedges: string[];
  /** Worst confidence across cited params; drives the overall badge. */
  overallConfidence: PatchConfidence;
}

/** The serializable `.vital` preset shape (a subset Vital fills out on load). */
export interface VitalPreset {
  synth_version: string;
  preset_name: string;
  author: string;
  comments: string;
  preset_style: string;
  macro1: string;
  macro2: string;
  macro3: string;
  macro4: string;
  settings: Record<string, number>;
}

export interface PatchSmithResult {
  manifest: PatchManifest;
  preset: VitalPreset;
}

// We declare the version Vital's loader is tolerant against; it only gates a
// soft compatibility note inside Vital, never a load failure.
const SYNTH_VERSION = "1.5.5";
const PRESET_AUTHOR = "ASA patchSmith";

/**
 * Baseline init controls. Vital resets to init before applying a preset, but we
 * write the full signal path we touch so the patch is deterministic regardless
 * of host load order. Values match Vital's documented ValueDetails defaults.
 */
const VITAL_INIT_SETTINGS: Readonly<Record<string, number>> = {
  osc_1_on: 1.0,
  osc_1_level: 0.707,
  osc_1_transpose: 0.0,
  osc_1_unison_voices: 1.0,
  osc_1_unison_detune: 4.472,
  osc_2_on: 0.0,
  osc_2_level: 0.707,
  osc_2_transpose: 0.0,
  env_1_attack: 0.15,
  env_1_decay: 1.0,
  env_1_sustain: 1.0,
  env_1_release: 0.548,
  filter_1_on: 0.0,
  filter_1_cutoff: 60.0,
  filter_1_resonance: 0.5,
  filter_1_mix: 1.0,
  volume: 5473.04,
  polyphony: 8.0,
};

// ── Unit mappers (Vital ValueDetails) ─────────────────────────────────────────

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}

function round(value: number, places = 4): number {
  const f = 10 ** places;
  return Math.round(value * f) / f;
}

/** Vital env time control: displayed seconds = value^4 (range 0…2.378 ≈ 32 s). */
export function secondsToEnvValue(seconds: number): number {
  if (!Number.isFinite(seconds) || seconds <= 0) return 0;
  return round(clamp(seconds ** 0.25, 0, 2.378));
}

/** Vital filter cutoff is a semitone value; freq = 440·2^((s−69)/12), range 8…136. */
export function hzToCutoffSemitone(hz: number): number {
  if (!Number.isFinite(hz) || hz <= 0) return 60.0;
  const semitone = 69 + 12 * Math.log2(hz / 440);
  return round(clamp(semitone, 8, 136), 2);
}

/**
 * Map a measured average detune in cents to Vital's 0…10 unison_detune control.
 * The control's calibration is non-linear (kQuadratic); this is a monotonic
 * approximation that lands typical supersaws (≈25–55 cents) in the musical 3.5–8
 * band. The cited measurement (avgDetuneCents) is the exact, honest part.
 */
export function detuneCentsToVital(cents: number): number {
  if (!Number.isFinite(cents) || cents <= 0) return 0;
  return round(clamp(cents / 7.0, 0, 10), 3);
}

/**
 * Mean of the 7 `spectralBalance` bands — the "mix average" reference.
 *
 * CRITICAL: the bands are ABSOLUTE band energy in dB (`10·log10(mean_energy)`,
 * roughly −100…0; see `apps/backend/analyze_core.py`), NOT relative to the mix
 * average. A real track reads e.g. `subBass −41`, `highs −62`. So any
 * "X dB above/below the mix average" reasoning MUST subtract this mean first —
 * comparing a raw band value against a small absolute threshold (the original
 * bug) never fires on real input.
 */
export function meanBandDb(sb: Phase1Result["spectralBalance"] | null | undefined): number | null {
  if (!sb) return null;
  const bands = [sb.subBass, sb.lowBass, sb.lowMids, sb.mids, sb.upperMids, sb.highs, sb.brilliance];
  const finite = bands.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (finite.length === 0) return null;
  return finite.reduce((sum, v) => sum + v, 0) / finite.length;
}

/**
 * dB above the mix average at which the sub band is "prominent" enough to
 * warrant a dedicated octave-down oscillator. First cut — tuned so a genuinely
 * sub-forward mix engages it while ordinary low-end does not; revisit against
 * the recommendation corpus (GOAL.md).
 */
const SUB_PROMINENCE_DB = 3.0;

// ── Mapping engine ─────────────────────────────────────────────────────────

const CONF_RANK: Record<PatchConfidence, number> = { HIGH: 2, MED: 1, LOW: 0 };

function worstConfidence(citations: PatchParameterCitation[]): PatchConfidence {
  if (citations.length === 0) return "LOW";
  return citations.reduce<PatchConfidence>(
    (worst, c) => (CONF_RANK[c.confidence] < CONF_RANK[worst] ? c.confidence : worst),
    "HIGH",
  );
}

/** Confidence band from a detector's 0–1 confidence score. */
function bandFromScore(score: number): PatchConfidence {
  if (score >= 0.7) return "HIGH";
  if (score >= 0.5) return "MED";
  return "LOW";
}

interface PatchAccumulator {
  citations: PatchParameterCitation[];
  hedges: string[];
  settings: Record<string, number>;
}

function applyCitation(acc: PatchAccumulator, citation: PatchParameterCitation): void {
  acc.settings[citation.vitalParam] = citation.value;
  acc.citations.push(citation);
}

/** Supersaw → unison voices + detune. The single most iconic synthesis mapping. */
function mapSupersaw(phase1: Phase1Result, acc: PatchAccumulator): void {
  const ss = phase1.supersawDetail;
  if (!ss || ss.voiceCount <= 1) return;

  const detected = ss.isSupersaw && ss.confidence >= 0.5;
  const confidence = detected ? bandFromScore(ss.confidence) : "LOW";
  const voices = clamp(Math.round(ss.voiceCount), 2, 16);
  const detune = detuneCentsToVital(ss.avgDetuneCents);

  applyCitation(acc, {
    label: "Unison voices",
    vitalParam: "osc_1_unison_voices",
    value: voices,
    display: `${voices} voices`,
    phase1Fields: ["supersawDetail.voiceCount", "supersawDetail.isSupersaw"],
    rationale: `Detected ${ss.voiceCount} stacked voices (supersaw confidence ${(ss.confidence * 100).toFixed(0)}%).`,
    confidence,
  });
  applyCitation(acc, {
    label: "Unison detune",
    vitalParam: "osc_1_unison_detune",
    value: detune,
    display: `${ss.avgDetuneCents.toFixed(0)}¢ spread`,
    phase1Fields: ["supersawDetail.avgDetuneCents"],
    rationale: `Average voice detune measured at ${ss.avgDetuneCents.toFixed(0)} cents.`,
    confidence,
  });

  if (!detected) {
    acc.hedges.push(
      `Unison is derived from a low-confidence supersaw reading (${(ss.confidence * 100).toFixed(0)}%): a starting point, not a guarantee. Dial voices/detune by ear.`,
    );
  }
}

/** Strong measured sub energy → a sub-octave second oscillator. */
function mapSubLayer(phase1: Phase1Result, acc: PatchAccumulator): void {
  const sb = phase1.spectralBalance;
  const subBass = sb?.subBass;
  if (typeof subBass !== "number") return;
  // The bands are absolute dB, so reduce to a prominence vs the mix average
  // before thresholding (see meanBandDb) — the old `subBass <= 1.0` guard
  // compared an absolute ~−41 dB reading against 1.0 and never fired.
  const meanDb = meanBandDb(sb);
  if (meanDb === null) return;
  const subProminenceDb = subBass - meanDb;
  if (subProminenceDb <= SUB_PROMINENCE_DB) return;

  applyCitation(acc, {
    label: "Sub oscillator",
    vitalParam: "osc_2_on",
    value: 1.0,
    display: "on",
    phase1Fields: ["spectralBalance.subBass"],
    rationale: `Sub band sits ${subProminenceDb.toFixed(1)} dB above the mix average — add an octave-down oscillator for that weight.`,
    confidence: "MED",
  });
  // The octave-down transpose and balance are what "sub layer" means; cite them
  // too so every value in the preset is traceable in the manifest (invariant #2).
  applyCitation(acc, {
    label: "Sub oscillator octave",
    vitalParam: "osc_2_transpose",
    value: -12.0,
    display: "−1 octave",
    phase1Fields: ["spectralBalance.subBass"],
    rationale: "An octave below the main oscillator carries the measured sub weight.",
    confidence: "MED",
  });
  applyCitation(acc, {
    label: "Sub oscillator level",
    vitalParam: "osc_2_level",
    value: 0.5,
    display: "50%",
    phase1Fields: ["spectralBalance.subBass"],
    rationale: "Mixed under the main oscillator so the sub supports rather than dominates.",
    confidence: "MED",
  });
}

/** Acid character → resonant filter; spectral brightness places its cutoff. */
function mapAcidFilter(phase1: Phase1Result, acc: PatchAccumulator): void {
  const acid = phase1.acidDetail;
  if (!acid || !acid.isAcid || acid.confidence < 0.5) return;

  const confidence = bandFromScore(acid.confidence);
  const resonance = clamp(acid.resonanceLevel, 0.3, 0.95);

  applyCitation(acc, {
    label: "Filter",
    vitalParam: "filter_1_on",
    value: 1.0,
    display: "on (low-pass)",
    phase1Fields: ["acidDetail.isAcid"],
    rationale: `Acid character detected (confidence ${(acid.confidence * 100).toFixed(0)}%) — the resonant low-pass is the defining move.`,
    confidence,
  });
  applyCitation(acc, {
    label: "Filter resonance",
    vitalParam: "filter_1_resonance",
    value: round(resonance, 3),
    display: `${(resonance * 100).toFixed(0)}%`,
    phase1Fields: ["acidDetail.resonanceLevel"],
    rationale: `Measured resonance level ${acid.resonanceLevel.toFixed(2)} drives the filter emphasis.`,
    confidence,
  });

  // Place the cutoff from spectral brightness *relative to the mix average*.
  // The bands are absolute dB; the 1200 Hz center assumes a relative reading,
  // so without subtracting the mean (the old bug) brightness ≈ −63 and the
  // cutoff pinned to the 200 Hz floor on every real track.
  const sb = phase1.spectralBalance;
  const meanDb = meanBandDb(sb);
  if (sb && meanDb !== null && typeof sb.highs === "number" && typeof sb.brilliance === "number") {
    const brightness = (sb.highs + sb.brilliance) / 2 - meanDb; // dB above/below mix average
    const cutoffHz = clamp(1200 * 2 ** (brightness / 6), 200, 16000);
    applyCitation(acc, {
      label: "Filter cutoff",
      vitalParam: "filter_1_cutoff",
      value: hzToCutoffSemitone(cutoffHz),
      display: `${Math.round(cutoffHz)} Hz`,
      phase1Fields: ["spectralBalance.highs", "spectralBalance.brilliance"],
      rationale: `High/brilliance balance (${brightness >= 0 ? "+" : ""}${brightness.toFixed(1)} dB vs mix average) sets the cutoff at ≈${Math.round(cutoffHz)} Hz.`,
      confidence: "MED",
    });
  }
}

/** Bass decay character → amp envelope (env 1 is hardwired to amplitude). */
function mapAmpEnvelope(phase1: Phase1Result, acc: PatchAccumulator): void {
  const bass = phase1.bassDetail;
  if (!bass || !Number.isFinite(bass.averageDecayMs)) return;

  const decaySec = bass.averageDecayMs / 1000;
  const sustainByType: Record<string, number> = {
    punchy: 0.15,
    medium: 0.45,
    rolling: 0.6,
    sustained: 0.85,
  };
  const sustain = sustainByType[bass.type] ?? 0.5;

  applyCitation(acc, {
    label: "Amp decay",
    vitalParam: "env_1_decay",
    value: secondsToEnvValue(decaySec),
    display: `${Math.round(bass.averageDecayMs)} ms`,
    phase1Fields: ["bassDetail.averageDecayMs"],
    rationale: `Bass notes decay over ≈${Math.round(bass.averageDecayMs)} ms; the amp envelope follows.`,
    confidence: "MED",
  });
  applyCitation(acc, {
    label: "Amp sustain",
    vitalParam: "env_1_sustain",
    value: round(sustain, 3),
    display: `${(sustain * 100).toFixed(0)}%`,
    phase1Fields: ["bassDetail.type"],
    rationale: `A "${bass.type}" bass envelope ${sustain < 0.3 ? "drops fast" : sustain > 0.7 ? "holds" : "settles mid"} after the transient.`,
    confidence: "MED",
  });
}

/** Build the human-facing preset name from genre + key when available. */
function buildPresetName(phase1: Phase1Result): string {
  const genre = phase1.genreDetail?.genre;
  const key = typeof phase1.key === "string" ? phase1.key : null;
  const parts = ["ASA", genre ?? "Patch", key ?? ""].filter(Boolean);
  return parts.join(" ").trim();
}

/** Build the `comments` block — measured context that didn't bind a hard param. */
function buildComments(phase1: Phase1Result): string {
  const notes: string[] = ["Generated by ASA patchSmith from Phase 1 measurements."];
  const synth = phase1.synthesisCharacter;
  if (synth) {
    const bits: string[] = [];
    if (typeof synth.oddToEvenRatio === "number")
      bits.push(`odd/even harmonic ratio ${synth.oddToEvenRatio.toFixed(2)}`);
    if (typeof synth.inharmonicity === "number")
      bits.push(`inharmonicity ${synth.inharmonicity.toFixed(3)}`);
    if (typeof synth.analogLike === "boolean")
      bits.push(synth.analogLike ? "analog-like" : "digital-like");
    if (bits.length) notes.push(`Spectral character: ${bits.join(", ")}.`);
  }
  const tex = phase1.textureCharacter;
  if (tex) {
    notes.push(
      `Texture: score ${tex.textureScore.toFixed(2)}, high-band flatness ${tex.highBandFlatness.toFixed(2)}.`,
    );
  }
  notes.push(
    "Synthesis character is approximated via core controls; wavetable shaping from odd/even + inharmonicity is a planned follow-up.",
  );
  return notes.join(" ");
}

export interface BuildPatchOptions {
  /** Override the preset name (defaults to genre + key). */
  presetName?: string;
}

/**
 * Derive a Vital preset + a fully-cited manifest from Phase 1 measurements.
 * Pure and deterministic: the same Phase 1 input always yields the same output.
 */
export function buildPatch(phase1: Phase1Result, options: BuildPatchOptions = {}): PatchSmithResult {
  const acc: PatchAccumulator = {
    citations: [],
    hedges: [],
    settings: { ...VITAL_INIT_SETTINGS },
  };

  mapSupersaw(phase1, acc);
  mapSubLayer(phase1, acc);
  mapAcidFilter(phase1, acc);
  mapAmpEnvelope(phase1, acc);

  if (acc.citations.length === 0) {
    acc.hedges.push(
      "Few strong synthesis cues were measured in this track, so this is a neutral single-oscillator starting patch rather than a reconstruction.",
    );
  }

  const presetName = options.presetName?.trim() || buildPresetName(phase1);

  const preset: VitalPreset = {
    synth_version: SYNTH_VERSION,
    preset_name: presetName,
    author: PRESET_AUTHOR,
    comments: buildComments(phase1),
    preset_style: phase1.genreDetail?.genre ?? "",
    macro1: "MACRO 1",
    macro2: "MACRO 2",
    macro3: "MACRO 3",
    macro4: "MACRO 4",
    settings: acc.settings,
  };

  const manifest: PatchManifest = {
    presetName,
    citations: acc.citations,
    hedges: acc.hedges,
    overallConfidence: worstConfidence(acc.citations),
  };

  return { manifest, preset };
}

/** Serialize a preset to `.vital` JSON text (re-parseable; Vital reads standard JSON). */
export function serializeVital(preset: VitalPreset): string {
  return JSON.stringify(preset, null, 2);
}

/** Convenience: filesystem-safe filename for the preset download. */
export function patchFileName(presetName: string): string {
  const safe = presetName.replace(/[^a-z0-9]+/gi, "_").replace(/^_+|_+$/g, "");
  return `${safe || "ASA_Patch"}.vital`;
}

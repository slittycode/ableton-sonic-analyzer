/**
 * keyCheck — turns the Phase 1 key + tuning measurements into what the Key
 * Check keyboard needs: which keys to highlight, which note is the tonic, what
 * A4 reference to tune the synth to, and how much to trust all of it.
 *
 * PURPOSE.md: ASA should report "a key that matches what the user hears when
 * they play along on a keyboard. Low-confidence keys are flagged, not hidden."
 * This module is the data side of that ear test. It only re-expresses Phase 1
 * fields; it never picks a different key. Ensemble alternates are surfaced as
 * "also plausible", exactly as Phase 1 labels them (surfacing-only).
 *
 * Pure — no Web Audio — so it runs under the Node unit suite.
 */

import type { Phase1Result } from '../types';
import { fundamentalsTrust, type FundamentalsTrust, type FundamentalsTrustLabel } from './fundamentalsTrust';

export type KeyMode = 'major' | 'minor';

export interface ParsedKey {
  /** Normalised display label, e.g. "F# minor". */
  label: string;
  /** Pitch class of the tonic, C = 0 … B = 11. */
  tonicPc: number;
  mode: KeyMode;
  /** Pitch classes of the major / natural-minor scale, tonic first. */
  scalePcs: number[];
  /** Spell accidentals as flats (Bb, Eb …) rather than sharps. */
  preferFlats: boolean;
}

const LETTER_PC: Record<string, number> = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
const MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11];
const NATURAL_MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10];
const SHARP_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const FLAT_NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];

// Natural-letter keys conventionally written with flats.
const FLAT_NATURAL_MAJORS = new Set(['F']);
const FLAT_NATURAL_MINORS = new Set(['D', 'G', 'C', 'F']);

const KEY_LABEL_RE = /^([A-Ga-g])\s*([#♯b♭]?)\s*(major|minor|maj|min|m)?$/i;

export function scalePitchClasses(tonicPc: number, mode: KeyMode): number[] {
  const steps = mode === 'major' ? MAJOR_STEPS : NATURAL_MINOR_STEPS;
  return steps.map((step) => (tonicPc + step) % 12);
}

export function pitchClassName(pc: number, preferFlats: boolean): string {
  const index = ((pc % 12) + 12) % 12;
  return (preferFlats ? FLAT_NAMES : SHARP_NAMES)[index];
}

/**
 * "A3"-style name with MIDI 60 = C4, matching the rest of ASA's note labels
 * (Session Musician, piano roll, MIDI export). Live's own piano roll calls
 * MIDI 60 "C3", so labels here read one octave higher than Live's.
 */
export function midiNoteName(midi: number, preferFlats: boolean): string {
  return `${pitchClassName(midi, preferFlats)}${Math.floor(midi / 12) - 1}`;
}

/**
 * Parse an Essentia-style key label ("A minor", "F# major", "Bb minor").
 * Also accepts short forms ("Am", "Ebmaj"). Returns null for "Unknown",
 * empty input, or anything that is not a major/minor key.
 */
export function parseKeyLabel(raw: string | null | undefined): ParsedKey | null {
  if (typeof raw !== 'string') return null;
  const match = raw.trim().match(KEY_LABEL_RE);
  if (!match) return null;

  const letter = match[1].toUpperCase();
  const accidental = match[2];
  const suffix = (match[3] ?? '').toLowerCase();
  const mode: KeyMode = suffix === 'minor' || suffix === 'min' || suffix === 'm' ? 'minor' : 'major';

  let tonicPc = LETTER_PC[letter];
  if (accidental === '#' || accidental === '♯') tonicPc += 1;
  if (accidental === 'b' || accidental === '♭') tonicPc -= 1;
  tonicPc = (tonicPc + 12) % 12;

  const preferFlats =
    accidental === 'b' ||
    accidental === '♭' ||
    (accidental === '' &&
      (mode === 'major' ? FLAT_NATURAL_MAJORS.has(letter) : FLAT_NATURAL_MINORS.has(letter)));

  return {
    label: `${pitchClassName(tonicPc, preferFlats)} ${mode}`,
    tonicPc,
    mode,
    scalePcs: scalePitchClasses(tonicPc, mode),
    preferFlats,
  };
}

/**
 * The relative major/minor: same notes, different tonic. The scale highlight
 * cannot tell these apart, which is why the panel points producers at the
 * tonic drone.
 */
export function relativeKey(key: ParsedKey): ParsedKey {
  const tonicPc = key.mode === 'minor' ? (key.tonicPc + 3) % 12 : (key.tonicPc + 9) % 12;
  const mode: KeyMode = key.mode === 'minor' ? 'major' : 'minor';
  return {
    label: `${pitchClassName(tonicPc, key.preferFlats)} ${mode}`,
    tonicPc,
    mode,
    scalePcs: scalePitchClasses(tonicPc, mode),
    preferFlats: key.preferFlats,
  };
}

export function sameKey(a: ParsedKey, b: ParsedKey): boolean {
  return a.tonicPc === b.tonicPc && a.mode === b.mode;
}

/** Equal-tempered frequency of a MIDI note against an A4 reference. */
export function midiToFrequency(midi: number, referenceA4 = 440): number {
  return referenceA4 * 2 ** ((midi - 69) / 12);
}

// ── Trust ────────────────────────────────────────────────────────────────────

export type KeyTrustLabel = FundamentalsTrustLabel;
export type KeyTrust = FundamentalsTrust;

// ── Tuning ───────────────────────────────────────────────────────────────────

/**
 * Accept a measured A4 only within about a semitone of 440 Hz. Anything
 * further out is more likely an estimator failure than a real concert-pitch
 * variant, and tuning the keyboard to it would make the ear test misleading.
 */
export const TUNING_ACCEPT_RANGE_HZ = [415, 466] as const;
export const DEFAULT_REFERENCE_A4 = 440;

export interface TuningReference {
  referenceHz: number;
  /** Offset from A440 in cents; null when not measured. */
  cents: number | null;
  /**
   * measured — tuning came from Phase 1 (full mode only);
   * not_measured — Phase 1 did not report tuning (e.g. fast mode);
   * rejected — Phase 1 reported a value outside TUNING_ACCEPT_RANGE_HZ.
   */
  source: 'measured' | 'not_measured' | 'rejected';
}

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function resolveTuning(phase1: Pick<Phase1Result, 'tuningFrequency' | 'tuningCents'>): TuningReference {
  const hz = phase1.tuningFrequency;
  if (!finite(hz)) {
    return { referenceHz: DEFAULT_REFERENCE_A4, cents: null, source: 'not_measured' };
  }
  if (hz < TUNING_ACCEPT_RANGE_HZ[0] || hz > TUNING_ACCEPT_RANGE_HZ[1]) {
    return { referenceHz: DEFAULT_REFERENCE_A4, cents: null, source: 'rejected' };
  }
  const cents = finite(phase1.tuningCents) ? phase1.tuningCents : 1200 * Math.log2(hz / DEFAULT_REFERENCE_A4);
  return { referenceHz: hz, cents, source: 'measured' };
}

// ── Model ────────────────────────────────────────────────────────────────────

/** Same threshold AnalysisResults uses to mark the headline key approximate. */
export const APPROXIMATE_KEY_CONFIDENCE = 0.6;

export interface KeyCheckModel {
  /** The shipped Phase 1 key, parsed. Null when Phase 1 has no usable key. */
  measured: ParsedKey | null;
  /** The raw label Phase 1 shipped, for display when it fails to parse. */
  rawKeyLabel: string | null;
  isApproximate: boolean;
  trust: KeyTrust;
  /** How many key profiles agree with the shipped key (full mode only). */
  ensemble: { agreeing: number; total: number } | null;
  /** Distinct ensemble alternates, strongest first, excluding the shipped key. */
  alternates: ParsedKey[];
  tuning: TuningReference;
}

export function buildKeyCheckModel(phase1: Phase1Result): KeyCheckModel {
  const measured = parseKeyLabel(phase1.key);
  const ensembleRaw = phase1.keyEnsemble ?? null;

  const alternates: ParsedKey[] = [];
  for (const alt of [...(ensembleRaw?.alternates ?? [])].sort((a, b) => b.strength - a.strength)) {
    const parsed = parseKeyLabel(alt.key);
    if (!parsed) continue;
    if (measured && sameKey(parsed, measured)) continue;
    if (alternates.some((existing) => sameKey(existing, parsed))) continue;
    alternates.push(parsed);
  }

  const total = ensembleRaw?.profiles?.length ?? 0;
  return {
    measured,
    rawKeyLabel: typeof phase1.key === 'string' && phase1.key.trim() ? phase1.key.trim() : null,
    isApproximate: !finite(phase1.keyConfidence) || phase1.keyConfidence <= APPROXIMATE_KEY_CONFIDENCE,
    trust: fundamentalsTrust(phase1, 'key'),
    ensemble: ensembleRaw && total > 0 ? { agreeing: ensembleRaw.agreement, total } : null,
    alternates,
    tuning: resolveTuning(phase1),
  };
}

// ── Keyboard helpers ─────────────────────────────────────────────────────────

/**
 * Tonic + perfect fifth around C3 (MIDI 48–59). The fifth is the same in major
 * and minor, so the drone tests "which note is home" without presupposing the
 * mode — the producer's own third settles that.
 */
export function droneMidis(key: ParsedKey, octaveBaseMidi = 48): number[] {
  const tonic = octaveBaseMidi + key.tonicPc;
  return [tonic, tonic + 7];
}

/**
 * Computer-keyboard note layout, matching Ableton Live's Computer MIDI
 * Keyboard: the A row plays white keys from C, the Q row the black keys.
 * Uses KeyboardEvent.code so it follows key position, not the typed letter.
 */
export const COMPUTER_KEY_OFFSETS: Readonly<Record<string, number>> = {
  KeyA: 0,
  KeyW: 1,
  KeyS: 2,
  KeyE: 3,
  KeyD: 4,
  KeyF: 5,
  KeyT: 6,
  KeyG: 7,
  KeyY: 8,
  KeyH: 9,
  KeyU: 10,
  KeyJ: 11,
  KeyK: 12,
  KeyO: 13,
  KeyL: 14,
  KeyP: 15,
  Semicolon: 16,
};

/** Ableton uses Z / X to shift the computer keyboard down / up an octave. */
export const OCTAVE_DOWN_CODE = 'KeyZ';
export const OCTAVE_UP_CODE = 'KeyX';

export function computerKeyToMidi(code: string, baseMidi: number): number | null {
  const offset = COMPUTER_KEY_OFFSETS[code];
  return offset === undefined ? null : baseMidi + offset;
}

/** Inverse of COMPUTER_KEY_OFFSETS for drawing letter hints on keys. */
export function computerKeyLabelFor(midi: number, baseMidi: number): string | null {
  const offset = midi - baseMidi;
  for (const [code, value] of Object.entries(COMPUTER_KEY_OFFSETS)) {
    if (value === offset) return code === 'Semicolon' ? ';' : code.replace('Key', '');
  }
  return null;
}

export function isBlackKey(midi: number): boolean {
  return [1, 3, 6, 8, 10].includes(((midi % 12) + 12) % 12);
}

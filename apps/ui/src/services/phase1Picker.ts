/**
 * Audit Finding #2 + #3: the CitationBlock primitive needs to resolve a Phase 1
 * dotted field path (e.g. `kickDetail.fundamentalHz`) to its measured value
 * and, when available, to its paired *Confidence sibling. This file is the
 * pure-function picker that does both jobs.
 *
 * No React, no UI. The CitationBlock component calls these helpers at render
 * time; the worst-confidence picker is also called from the ConfidenceBandBadge
 * computation per card.
 */
import type { Phase1Result } from '../types';
import { CONFIDENCE_PAIRS } from './phase2Validator';

/**
 * Walk a dotted path through nested object properties. Returns `undefined`
 * for any missing intermediate or leaf. Never throws.
 *
 *   pickPhase1Value(phase1, "spectralBalance.subBass") → number | undefined
 *   pickPhase1Value(phase1, "kickDetail.fundamentalHz") → number | undefined
 *   pickPhase1Value(phase1, "missing.field")            → undefined
 */
export function pickPhase1Value(
  phase1: Phase1Result | null | undefined,
  dottedPath: string,
): unknown {
  if (!phase1 || !dottedPath) return undefined;
  const segments = dottedPath.split('.');
  let cursor: unknown = phase1;
  for (const segment of segments) {
    if (cursor === null || cursor === undefined || typeof cursor !== 'object') {
      return undefined;
    }
    cursor = (cursor as Record<string, unknown>)[segment];
  }
  return cursor;
}

/**
 * Format a Phase 1 value for display in the citation block. The formatter
 * branches on path conventions (suffix / prefix patterns) rather than on the
 * value's runtime type — keeps it predictable across nulls / missing fields.
 *
 *   formatCitedValue("bpm", 156.6)                       → "157 BPM"
 *   formatCitedValue("spectralBalance.highs", 1.2)       → "+1.2 dB"
 *   formatCitedValue("kickDetail.fundamentalHz", 64.3)   → "64 Hz"
 *   formatCitedValue("reverbDetail.rt60", 2.04)          → "2.04s"
 *   formatCitedValue("bpmConfidence", 0.86)              → "86%"
 *   formatCitedValue("lufsIntegrated", -9.3)             → "-9.3 LUFS"
 *   formatCitedValue("truePeak", -0.2)                   → "-0.2 dBTP"
 *   formatCitedValue("key", "F minor")                   → "F minor"
 *   formatCitedValue("acidDetail.isAcid", true)          → "yes"
 *   formatCitedValue("anything", null | undefined)       → ""
 */
export function formatCitedValue(path: string, value: unknown): string {
  if (value === null || value === undefined) return '';

  // BPM family — integer + unit. Producers think in integer BPMs.
  if (path === 'bpm' || path === 'bpmPercival' || path === 'bpmRawOriginal') {
    return typeof value === 'number' && Number.isFinite(value)
      ? `${Math.round(value)} BPM`
      : String(value);
  }

  // Confidence / strength / regularity — 0-1 → percent.
  if (
    typeof value === 'number' &&
    /(Confidence|Strength|Regularity|Agreement|Conf)$/i.test(path)
  ) {
    return `${Math.round(value * 100)}%`;
  }

  // chordStrength is on a 0-1 scale too even without the "Confidence" suffix.
  if (path.endsWith('chordStrength') && typeof value === 'number') {
    return `${Math.round(value * 100)}%`;
  }

  // Spectral balance — signed dB.
  if (path.startsWith('spectralBalance.') && typeof value === 'number') {
    const fixed = value.toFixed(1);
    return `${value >= 0 ? '+' : ''}${fixed} dB`;
  }

  // LUFS-flavored paths.
  if (typeof value === 'number' && /lufs/i.test(path)) {
    return `${value.toFixed(1)} LUFS`;
  }

  // Hz / fundamental.
  if (typeof value === 'number' && /Hz$/.test(path)) {
    return `${Math.round(value)} Hz`;
  }

  // Seconds — decay times, RT60.
  if (
    typeof value === 'number' &&
    (/Seconds$/i.test(path) ||
      path.endsWith('rt60') ||
      path === 'durationSeconds')
  ) {
    return `${value.toFixed(2)}s`;
  }

  // True peak is dBTP (Phase 1 v2).
  if (path === 'truePeak' && typeof value === 'number') {
    return `${value.toFixed(1)} dBTP`;
  }

  // Dynamic / peak family — dB without sign-prefix rule. Match by suffix so
  // nested paths like `kickDetail.crestFactor` also pick up the dB formatter
  // rather than falling through to the bare-number rule.
  if (
    typeof value === 'number' &&
    /(^|\.)(crestFactor|dynamicSpread|plr)$/.test(path)
  ) {
    return `${value.toFixed(1)} dB`;
  }

  // Stereo correlation / width — bare decimal.
  if (typeof value === 'number' && (path === 'stereoWidth' || path === 'stereoCorrelation')) {
    return value.toFixed(2);
  }

  // Boolean detectors — yes/no reads more like English than "true/false".
  if (typeof value === 'boolean') {
    return value ? 'yes' : 'no';
  }

  // Strings ride as-is (key, genre, timeSignature, envelopeShape).
  if (typeof value === 'string') return value;

  // Numbers without a known formatting rule — 2 decimal places as a floor.
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }

  // Arrays — compact summary. Never stringify objects into "[object Object]".
  // chordDetail.chordTimeline gets a short progression preview when labels exist.
  if (Array.isArray(value)) {
    return formatCitedArray(path, value);
  }

  // Plain objects (and anything else) — safe dash fallback. Invariant: output
  // must never contain the literal "[object Object]".
  return '—';
}

function formatCitedArray(path: string, value: unknown[]): string {
  const count = value.length;
  if (count === 0) return '0 entries';

  const isChordTimeline =
    path === 'chordDetail.chordTimeline' || path.endsWith('.chordTimeline');

  if (isChordTimeline) {
    const labels = value
      .map((entry) => {
        if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return null;
        const label = (entry as { label?: unknown }).label;
        return typeof label === 'string' && label.trim() ? label.trim() : null;
      })
      .filter((label): label is string => Boolean(label));
    if (labels.length > 0) {
      const preview = labels.slice(0, 3).join(' → ');
      return `${preview} · ${count} ${count === 1 ? 'entry' : 'entries'}`;
    }
  }

  // Homogeneous primitive arrays: show a short join; object arrays: count only.
  const primitives = value.every(
    (item) => item === null || ['string', 'number', 'boolean'].includes(typeof item),
  );
  if (primitives) {
    const rendered = value.slice(0, 4).map((item) => {
      if (item === null) return 'null';
      if (typeof item === 'number' && Number.isFinite(item)) {
        return Number.isInteger(item) ? String(item) : item.toFixed(2);
      }
      return String(item);
    });
    const suffix = count > 4 ? `, … (+${count - 4})` : '';
    return `${rendered.join(', ')}${suffix}`;
  }

  return `${count} ${count === 1 ? 'entry' : 'entries'}`;
}

/**
 * Look up the paired *Confidence value for a given Phase 1 path. Mirrors the
 * validator's path-matching rule (full path first, then the prefix segment),
 * so a citation of `sidechainDetail.pumpingRate` still picks
 * `sidechainDetail.pumpingConfidence` as its confidence even when the
 * specific full-path entry isn't mapped.
 *
 * Returns `null` when no confidence sibling exists for the cited path.
 */
export function pickPhase1Confidence(
  phase1: Phase1Result | null | undefined,
  dottedPath: string,
): number | null {
  if (!phase1 || !dottedPath) return null;
  const confidencePath =
    CONFIDENCE_PAIRS[dottedPath] ?? CONFIDENCE_PAIRS[dottedPath.split('.')[0]];
  if (!confidencePath) return null;
  const raw = pickPhase1Value(phase1, confidencePath);
  if (typeof raw !== 'number' || !Number.isFinite(raw)) return null;
  return raw;
}

/**
 * Audit Finding #3 ("Compute a ConfidenceBand for each Phase 2 recommendation
 * by taking the worst confidence among its underlying measurements").
 *
 * Returns the lowest non-null confidence across the provided paths. Returns
 * `null` when none of the paths have a confidence sibling — the caller should
 * suppress the ConfidenceBandBadge in that case rather than guess a band.
 */
export function pickWorstConfidence(
  phase1: Phase1Result | null | undefined,
  paths: readonly string[],
): number | null {
  if (!phase1 || paths.length === 0) return null;
  let worst: number | null = null;
  for (const path of paths) {
    const value = pickPhase1Confidence(phase1, path);
    if (value === null) continue;
    if (worst === null || value < worst) worst = value;
  }
  return worst;
}

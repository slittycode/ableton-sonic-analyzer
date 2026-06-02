import type { Phase1Result } from '../types';

/**
 * Objective, genre-independent loudness defects.
 *
 * Unit note: as of Phase 1 schema v2, `truePeak` is dBTP (see
 * apps/backend/JSON_SCHEMA.md). 0.0 dBTP == full scale; > 0.0 dBTP ==
 * inter-sample over. Compare in dBTP. (In v1 this field was a linear amplitude
 * proxy with a 1.0 boundary; the v2 migration moved it to dBTP.)
 *
 * The robust trigger is `saturationDetail.clippedSampleCount` (stereo samples
 * with |x| >= 0.9999) — unit-independent and unambiguous. truePeak is a
 * secondary corroborating signal.
 *
 * This module deliberately does NOT encode loudness "taste" (a genre or
 * platform LUFS target). That judgement is subjective and owned by Gemini; the
 * safety net only asserts correctness — that a measured defect is addressed.
 */

/** dBTP above which `truePeak` is an inter-sample over (0.0 dBTP == full scale). */
export const TRUE_PEAK_OVER_DBTP = 0.0;

export type LoudnessDefectKind = 'CLIPPING' | 'TRUE_PEAK_OVER';

export interface LoudnessDefect {
  kind: LoudnessDefectKind;
  /** Phase 1 dotted path that evidences the defect. */
  field: string;
  value: number;
}

/**
 * Whether a Phase 2 `phase1Fields` citation counts as addressing a loudness
 * defect — i.e. it cites the true-peak / clipping (saturation) family.
 */
export function citationAddressesLoudnessDefect(citation: string): boolean {
  const c = citation.trim();
  return c === 'truePeak' || c === 'saturationDetail' || c.startsWith('saturationDetail.');
}

/**
 * Returns the objective loudness defects present in a Phase 1 result that a
 * Phase 2 mastering/dynamics recommendation should address. An empty array
 * means no objective defect was measured.
 */
export function loudnessDefectsDemandingAction(phase1: Phase1Result): LoudnessDefect[] {
  const defects: LoudnessDefect[] = [];

  const clipped = phase1.saturationDetail?.clippedSampleCount;
  if (typeof clipped === 'number' && Number.isFinite(clipped) && clipped > 0) {
    defects.push({
      kind: 'CLIPPING',
      field: 'saturationDetail.clippedSampleCount',
      value: clipped,
    });
  }

  const truePeak = phase1.truePeak;
  if (
    typeof truePeak === 'number' &&
    Number.isFinite(truePeak) &&
    truePeak > TRUE_PEAK_OVER_DBTP
  ) {
    defects.push({
      kind: 'TRUE_PEAK_OVER',
      field: 'truePeak',
      value: truePeak,
    });
  }

  return defects;
}

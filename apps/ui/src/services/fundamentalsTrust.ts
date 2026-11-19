/**
 * The local fundamentals trust label for one domain (tempo, beatGrid,
 * downbeats, meter, key, …), in the same LOCAL / CHECK / FAILED / NOT RUN
 * vocabulary the Measurement Summary pills use. Shared by the ear-test panels
 * (Key Check, Beat Check) so they never invent their own trust wording.
 */

import type { FundamentalsQualityStatus, Phase1Result } from '../types';

export type FundamentalsTrustLabel = 'LOCAL' | 'CHECK' | 'FAILED' | 'NOT RUN';

export interface FundamentalsTrust {
  status: FundamentalsQualityStatus | null;
  label: FundamentalsTrustLabel;
  tone: 'success' | 'warning' | 'error' | 'neutral';
  /** Phase 1's own plain-English trust sentence, when present. */
  plainEnglish: string | null;
}

export function fundamentalsTrust(phase1: Phase1Result, domain: string): FundamentalsTrust {
  const entry = phase1.fundamentalsQuality?.domains?.[domain];
  const status = entry?.status ?? null;
  const plainEnglish = entry?.plainEnglish?.trim() || null;
  if (status === 'authoritative') return { status, label: 'LOCAL', tone: 'success', plainEnglish };
  if (status === 'ambiguous') return { status, label: 'CHECK', tone: 'warning', plainEnglish };
  if (status === 'failed') return { status, label: 'FAILED', tone: 'error', plainEnglish };
  return { status, label: 'NOT RUN', tone: 'neutral', plainEnglish };
}

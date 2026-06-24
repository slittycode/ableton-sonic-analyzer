/**
 * recommendations.v1 → UI surfacing (ADR 0003).
 *
 * The backend attaches a frozen, schema-validated, citation-gated projection of
 * the Phase 2 device cards to `Phase2Result.recommendations`
 * (apps/backend/recommendations_contract.py). This module is the UI-side
 * consumer: it turns that envelope into (a) a per-card "on the contract" trust
 * signal and (b) flat rows for the Reconstruction Contract table.
 *
 * Pure + node-testable (no DOM). All matching keys on the RAW Phase 2
 * device/parameter strings — see `normKey`.
 */
import type { Phase1Result } from '../types';
import type {
  RecommendationsContract,
  RecommendationContractEntry,
} from '../types/interpretation';
import { humanizeFieldPath } from './userLabels';
import { formatCitedValue, pickPhase1Value } from './phase1Picker';

/** The raw-card fields the view-model builders already have in scope. */
export interface RawCitedItem {
  device: string;
  parameter: string;
  phase1Fields?: string[];
}

/**
 * Normalized `device|parameter` match key.
 *
 * CRITICAL: index and lookup MUST call this on the RAW strings. The backend keys
 * the envelope on the raw Phase 2 device/parameter (strip-only `_clean_str`); the
 * view-model builders iterate the same raw `item.device`/`item.parameter`. Do NOT
 * run `parameter` through `normalizeParameterLabel` — it rewrites labels
 * ("gain" → "Output Gain") while the backend stores "gain", so keys would never
 * match. There is no existing device+parameter normalizer to reuse.
 */
export function normKey(device: string, parameter: string): string {
  return `${device.trim().toLowerCase()}|${parameter.trim().toLowerCase()}`;
}

/** Every `device|parameter` key present in the validated envelope. */
export function buildContractValidatedKeys(
  contract: RecommendationsContract | undefined,
): Set<string> {
  const keys = new Set<string>();
  if (!contract || !Array.isArray(contract.recommendations)) return keys;
  for (const entry of contract.recommendations) {
    if (typeof entry?.device === 'string' && typeof entry?.parameter === 'string') {
      keys.add(normKey(entry.device, entry.parameter));
    }
  }
  return keys;
}

/**
 * Binary: is this UI card on the frozen, citation-gated contract?
 *
 * A card maps to one raw item (mix-chain, 1:1) or several merged by device
 * (patches). True iff ≥1 citation-eligible (phase1Fields-nonempty) contributing
 * item is in the envelope AND no eligible contributing item is missing from it;
 * else false (→ render no pill). Synthetic cards (Limiter fallback, MIDI Clip
 * Guide, stereo-width) contribute no eligible items and are therefore never
 * marked — they have no Phase 2 origin to validate against.
 */
export function isCardValidated(
  validatedKeys: Set<string>,
  rawItems: readonly RawCitedItem[],
): boolean {
  const eligible = rawItems.filter(
    (item) => Array.isArray(item.phase1Fields) && item.phase1Fields.length > 0,
  );
  if (eligible.length === 0) return false;
  return eligible.every((item) => validatedKeys.has(normKey(item.device, item.parameter)));
}

/**
 * Format an entry's value for display: numbers append `unit` and `range`
 * ("10 ms (7–13)"); non-numeric values (e.g. "Sine") pass through unchanged.
 */
export function formatContractValue(entry: RecommendationContractEntry): string {
  const { value, unit, range } = entry;
  if (typeof value !== 'number') return String(value);
  const base = unit ? `${value} ${unit}` : `${value}`;
  if (Array.isArray(range) && range.length === 2) {
    return `${base} (${range[0]}–${range[1]})`;
  }
  return base;
}

export interface ContractRow {
  device: string;
  parameter: string;
  value: string;
  /**
   * Display strings for each cited measurement: "Humanized label: value" when
   * the path resolves against this run's Phase 1, else the raw dotted path so
   * the cell is never blank (the envelope is citation-gated but the paths are
   * Phase-2-asserted and may not resolve in every run).
   */
  citations: string[];
}

/** Flatten the envelope into table rows, resolving citation paths against Phase 1. */
export function projectContractRows(
  contract: RecommendationsContract | undefined,
  phase1: Phase1Result,
): ContractRow[] {
  if (!contract || !Array.isArray(contract.recommendations)) return [];
  return contract.recommendations.map((entry) => ({
    device: entry.device,
    parameter: entry.parameter,
    value: formatContractValue(entry),
    citations: (Array.isArray(entry.cited_measurements) ? entry.cited_measurements : []).map(
      (path) => {
        const formatted = formatCitedValue(path, pickPhase1Value(phase1, path));
        return formatted ? `${humanizeFieldPath(path)}: ${formatted}` : path;
      },
    ),
  }));
}

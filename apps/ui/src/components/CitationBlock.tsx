/**
 * Audit Finding #2: the chain-of-custody promise — every Phase 2
 * recommendation must trace back to the Phase 1 measurement that justifies
 * it — was rendered as 9px monospace pills (field-path strings) on a single
 * section (Track Layout) and was invisible on the cards that matter (Mix
 * Chain, Patches, Sonic Elements). This is the visual primitive that fixes
 * that: a "GROUNDED IN" block placed ABOVE each recommendation card body
 * with human-readable label · value rows.
 *
 * Audit Finding #3 sibling: a confidence pill renders top-right when any of
 * the cited fields have a paired *Confidence sibling (via CONFIDENCE_PAIRS
 * in phase2Validator.ts). The pill reuses the four-band vocabulary from
 * ConfidenceBandBadge — Solid scaffold / Workable draft / Rough sketch /
 * Unreliable — so the same color language carries from Session Musician
 * into the recommendation cards.
 */
import React from 'react';
import type { Phase1Result } from '../types';
import { humanizeFieldPath } from '../services/userLabels';
import {
  formatCitedValue,
  pickPhase1Confidence,
  pickPhase1Value,
  pickWorstConfidence,
} from '../services/phase1Picker';
import {
  formatBandPillLabel,
  getConfidenceBand,
  type ConfidenceBand,
} from '../services/sessionMusician/confidenceBand';

interface CitationBlockProps {
  phase1: Phase1Result;
  fields: readonly string[];
  /** Cap the visible row count. Producers scan citations, not read them. */
  maxRows?: number;
  /**
   * Precomputed worst confidence (0-1). When omitted, the block computes it
   * from `fields` via the validator's CONFIDENCE_PAIRS map. Pass `null` to
   * suppress the badge even when the picker could compute one (e.g., if the
   * caller has higher-fidelity confidence information available elsewhere).
   */
  confidence?: number | null;
  /** When false, the confidence pill is hidden even if a value is available. */
  showConfidenceBadge?: boolean;
  /**
   * Synthetic rows appended after the resolved phase1Fields rows. Used by
   * callers whose citation includes non-Phase-1 evidence — e.g., Track
   * Layout's arrangement-segment indices.
   */
  extraRows?: ReadonlyArray<{ label: string; value: string }>;
  className?: string;
  testId?: string;
}

// Same 4-tone ladder as ConfidenceBandBadge (PILL_CLASSES). Duplicated here
// rather than imported because the badge file isn't re-exporting the map and
// the CitationBlock variant is a single-line compact pill (no copy paragraph).
// If a third call site needs the same ladder, lift PILL_CLASSES out.
const CONFIDENCE_PILL_CLASSES: Record<ConfidenceBand['id'], string> = {
  solid: 'border-success/30 text-success bg-success/10',
  workable: 'border-accent/40 text-accent bg-accent/10',
  rough: 'border-warning/30 text-warning bg-warning/10',
  unreliable: 'border-error/30 text-error bg-error/10',
};

export function CitationBlock({
  phase1,
  fields,
  maxRows = 4,
  confidence,
  showConfidenceBadge = true,
  extraRows,
  className,
  testId = 'citation-block',
}: CitationBlockProps) {
  // Resolve each cited path to (label, value). Drop rows whose value resolves
  // to null/undefined/empty — defensive against unmapped fields and against
  // Phase 2 emitting a citation whose target wasn't actually populated by
  // Phase 1 this run.
  const resolvedRows = fields
    .map((path) => {
      const value = pickPhase1Value(phase1, path);
      const formatted = formatCitedValue(path, value);
      return {
        path,
        label: humanizeFieldPath(path),
        value: formatted,
      };
    })
    .filter((row) => row.value !== '')
    .slice(0, maxRows);

  const syntheticRows = (extraRows ?? []).map((row, idx) => ({
    path: `__extra_${idx}`,
    label: row.label,
    value: row.value,
  }));
  const rows = [...resolvedRows, ...syntheticRows];

  if (rows.length === 0) return null;

  // Worst-confidence pill. `confidence` prop wins if explicitly passed (even
  // null — caller can suppress). Otherwise compute from the same paths.
  const resolvedConfidence =
    confidence !== undefined ? confidence : pickWorstConfidence(phase1, fields);
  const band =
    showConfidenceBadge && resolvedConfidence !== null
      ? getConfidenceBand(resolvedConfidence)
      : null;
  const pillClass = band ? CONFIDENCE_PILL_CLASSES[band.id] : null;

  return (
    <div
      data-testid={testId}
      className={`rounded-sm border border-border bg-bg-panel/60 px-3 py-2 space-y-1.5 ${className ?? ''}`}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-micro font-mono uppercase tracking-[0.18em] text-text-secondary/80">
          Grounded in
        </p>
        {band && pillClass && resolvedConfidence !== null && (
          <span
            data-testid="citation-confidence-pill"
            className={`inline-flex items-center px-1.5 py-0.5 rounded border text-micro font-mono uppercase tracking-wide ${pillClass}`}
            title={band.copy}
          >
            {formatBandPillLabel(band, resolvedConfidence)}
          </span>
        )}
      </div>
      <dl className="space-y-0.5">
        {rows.map((row) => (
          <div
            key={row.path}
            data-testid={`citation-row-${row.path}`}
            className="flex items-baseline justify-between gap-3 text-meta font-mono"
          >
            <dt className="text-text-secondary truncate" title={row.path}>
              {row.label}
            </dt>
            <dd className="text-text-primary tabular-nums whitespace-nowrap">
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/**
 * Audit Finding #3: surfaces a one-line primary citation inside the collapsed
 * card header so the chain-of-custody evidence is visible without expanding
 * the card. The audit's literal example:
 *
 *     Crest factor 8.2 dB → Glue Compressor
 *
 * Reads as `{humanized label} {formatted value} → {device h4 to the right}`.
 * The arrow at the end of the headline points into the device name that
 * follows in the card title row, making the implicit "measurement justified
 * device" statement visible at scan-time.
 *
 * Returns `null` when the cited field doesn't resolve in Phase 1 — the caller
 * is expected to guard with `phase1Fields.length > 0`, but the component is
 * defensive against unmapped paths and empty Phase 1 payloads. The expanded
 * card body still renders the full CitationBlock with up to 4 rows; this
 * primitive is the collapsed-state companion, not a replacement.
 */
interface CitationHeadlineProps {
  phase1: Phase1Result;
  /** Single primary path (typically `card.phase1Fields[0]`). */
  field: string;
  /** When false, the confidence pill is hidden even if a value is available. */
  showConfidenceBadge?: boolean;
  className?: string;
  testId?: string;
}

export function CitationHeadline({
  phase1,
  field,
  showConfidenceBadge = true,
  className,
  testId = 'citation-headline',
}: CitationHeadlineProps) {
  const raw = pickPhase1Value(phase1, field);
  const value = formatCitedValue(field, raw);
  if (value === '') return null;

  const label = humanizeFieldPath(field);
  const confidence = pickPhase1Confidence(phase1, field);
  const band =
    showConfidenceBadge && confidence !== null
      ? getConfidenceBand(confidence)
      : null;
  const pillClass = band ? CONFIDENCE_PILL_CLASSES[band.id] : null;

  return (
    <span
      data-testid={testId}
      className={`inline-flex items-baseline gap-1.5 min-w-0 ${className ?? ''}`}
    >
      <span className="text-text-secondary text-micro font-mono uppercase tracking-[0.15em] whitespace-nowrap">
        {label}
      </span>
      <span className="text-text-primary text-xs font-mono tabular-nums font-semibold whitespace-nowrap">
        {value}
      </span>
      {band && pillClass && confidence !== null && (
        <span
          data-testid={`${testId}-pill`}
          className={`inline-flex items-center px-1 py-0 rounded border text-micro font-mono uppercase tracking-wide whitespace-nowrap ${pillClass}`}
          title={band.copy}
        >
          {formatBandPillLabel(band, confidence)}
        </span>
      )}
      <span className="text-text-secondary/60 text-xs leading-none" aria-hidden="true">→</span>
    </span>
  );
}

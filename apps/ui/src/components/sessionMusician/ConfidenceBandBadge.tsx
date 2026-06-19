// Confidence band pill ("Workable draft · 72%") plus a one-sentence
// plain-language copy line beneath it. The pill and copy can be overridden
// when a render state needs custom framing (e.g. full-mix fallback, legacy
// run) — see NoteDraftBlock for the overrides.

import React from 'react';
import {
  formatBandPillLabel,
  getConfidenceBand,
  type ConfidenceBand,
} from '../../services/sessionMusician/confidenceBand';

// Four-tone traffic-light ladder so the producer can distinguish all four
// bands at a glance: green → orange → amber → red, best to worst. The
// vocabulary mirrors what `MeasurementPrimitives`, `DiagnosticLog`, and
// `FileUpload` already use for severity across the app — success = ready,
// accent = active, warning = caution, error = critical. All four CSS
// variables are defined in `apps/ui/src/index.css`; no new theme tokens
// needed. Uniform opacity (`/30` border, `/10` bg) matches the established
// BADGE_TONE_CLASSES convention; the color is what carries the distinction.
const PILL_CLASSES: Record<ConfidenceBand['id'], string> = {
  solid: 'border-success/30 text-success bg-success/10',
  workable: 'border-accent/40 text-accent bg-accent/10',
  rough: 'border-warning/30 text-warning bg-warning/10',
  unreliable: 'border-error/30 text-error bg-error/10',
};

interface ConfidenceBandBadgeProps {
  /**
   * Numeric 0-1 confidence. Optional when `band` is supplied (some callers
   * have a pre-converted band from a string enum and no original scalar).
   * When provided, drives the pill percent via `formatBandPillLabel`.
   */
  confidence?: number;
  /**
   * Pre-converted band. When supplied, skips the `getConfidenceBand` round-
   * trip and uses this for tone + copy. Required when `confidence` is absent.
   * Useful when the source vocabulary is a string enum (HIGH/MED/LOW) that's
   * been normalized via `toConfidenceBand`.
   */
  band?: ConfidenceBand;
  /**
   * Audit Finding #4: 'compact' renders just the pill (no copy paragraph)
   * for use in card corners, metric-card footers, and chip rows where the
   * full variant's paragraph would blow up the layout. 'full' is the
   * Session Musician panel default — pill plus hedging copy beneath.
   */
  variant?: 'full' | 'compact';
  /** When set, replaces the pill text entirely (used for fallback / legacy states). */
  overrideLabel?: string | null;
  /** When set, replaces the band copy entirely. */
  overrideCopy?: string | null;
  /** Optional tone override for the pill colors when overrideLabel is set. */
  overrideTone?: ConfidenceBand['id'];
  /** Optional testid for jumping to it from tests. */
  testId?: string;
}

export function ConfidenceBandBadge({
  confidence,
  band,
  variant = 'full',
  overrideLabel,
  overrideCopy,
  overrideTone,
  testId,
}: ConfidenceBandBadgeProps) {
  // Dev-time guard against the both-missing case. In production we still
  // default to the unreliable band on undefined confidence so we never crash
  // a results render — but the guard surfaces the misuse during development.
  if (confidence === undefined && band === undefined) {
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.warn(
        '[ConfidenceBandBadge] Pass `confidence` (0-1 number), `band` (pre-converted), or both.',
      );
    }
  }

  const bandToUse = band ?? getConfidenceBand(confidence ?? 0);
  const pillText =
    overrideLabel
    ?? (confidence !== undefined ? formatBandPillLabel(bandToUse, confidence) : bandToUse.label);
  const copyText = overrideCopy ?? bandToUse.copy;
  const toneId = overrideTone ?? bandToUse.id;
  const pillClass = PILL_CLASSES[toneId];

  const pill = (
    <span
      className={`inline-flex items-center px-2 py-1 rounded border text-meta font-mono uppercase tracking-wide ${pillClass}`}
    >
      {pillText}
    </span>
  );

  if (variant === 'compact') {
    // Wrap in a span so the testid hook still has a stable anchor; consumers
    // place the badge inline in card headers / footers and don't want the
    // full variant's block-level div breaking their layout.
    return (
      <span data-testid={testId} className="inline-flex">
        {pill}
      </span>
    );
  }

  return (
    <div className="space-y-2" data-testid={testId}>
      {pill}
      <p className="text-eyebrow font-mono text-text-secondary/90 leading-relaxed">
        {copyText}
      </p>
    </div>
  );
}

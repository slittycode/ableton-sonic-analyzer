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
  confidence: number;
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
  overrideLabel,
  overrideCopy,
  overrideTone,
  testId,
}: ConfidenceBandBadgeProps) {
  const band = getConfidenceBand(confidence);
  const pillText = overrideLabel ?? formatBandPillLabel(band, confidence);
  const copyText = overrideCopy ?? band.copy;
  const toneId = overrideTone ?? band.id;
  const pillClass = PILL_CLASSES[toneId];

  return (
    <div className="space-y-2" data-testid={testId}>
      <span
        className={`inline-flex items-center px-2 py-1 rounded border text-[10px] font-mono uppercase tracking-wide ${pillClass}`}
      >
        {pillText}
      </span>
      <p className="text-[11px] font-mono text-text-secondary/90 leading-relaxed">
        {copyText}
      </p>
    </div>
  );
}

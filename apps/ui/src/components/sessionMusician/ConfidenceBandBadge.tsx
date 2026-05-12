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

const PILL_CLASSES: Record<ConfidenceBand['id'], string> = {
  solid: 'border-accent/40 text-accent bg-accent/10',
  workable: 'border-accent/30 text-accent bg-accent/5',
  rough: 'border-warning/30 text-warning bg-warning/10',
  unreliable: 'border-warning/40 text-warning bg-warning/15',
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

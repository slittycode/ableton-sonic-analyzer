import type { Phase1Result } from '../../types';
import { buildReconstructionBrief } from '../../services/reconstructionBrief';
import { ConfidenceBandBadge } from '../sessionMusician/ConfidenceBandBadge';
import { PhaseSourceBadge } from '../PhaseSourceBadge';
import { Pill } from '../ui';
import { ResultsSectionHeader } from './shared';

// Always-on plain-English summary of the measured fundamentals — deterministic
// (DSP only), so it renders even when Phase 2 interpretation is disabled or
// failed. Each line carries the Phase 1 field paths it was derived from.
export function ReconstructionBriefSection({ phase1 }: { phase1: Phase1Result }) {
  const lines = buildReconstructionBrief(phase1);
  if (lines.length === 0) return null;

  return (
    <section
      data-testid="reconstruction-brief"
      className="space-y-3 rounded-sm border border-border-light bg-bg-card p-4"
    >
      <ResultsSectionHeader
        title="Reconstruction Brief"
        rightSlot={<PhaseSourceBadge source="measured" />}
      />
      <ul className="space-y-2.5">
        {lines.map((line) => (
          <li key={line.domain} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <Pill tone="neutral" size="xs">
              {line.label}
            </Pill>
            <span className="min-w-0 flex-1 text-xs text-text-primary">{line.text}</span>
            {line.confidence !== null && (
              <ConfidenceBandBadge confidence={line.confidence} variant="compact" />
            )}
            <span className="basis-full font-mono text-nano text-text-muted">
              {line.phase1Fields.join(' · ')}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

import { INTERPRETATION_LABEL } from '../../services/phaseLabels';
import { PhaseSourceBadge } from '../PhaseSourceBadge';
import { ResultsSectionHeader } from './shared';

/**
 * The advisory header for the Phase 2 surface. Deliberately borderless and
 * transparent — ui-details.spec.ts pins `interpretation-panel` as having no
 * card background — so this stays a plain `<section>`, not a Panel.
 */
export function InterpretationPanel({
  phase2StatusMessage,
  hasPhase2,
  hasRenderablePhase2Content,
}: {
  phase2StatusMessage: string | null;
  hasPhase2: boolean;
  hasRenderablePhase2Content: boolean;
}) {
  return (
    <section data-testid="interpretation-panel" className="space-y-3">
      <ResultsSectionHeader
        title={
          <>
            {INTERPRETATION_LABEL}
            <PhaseSourceBadge source="advisory" />
          </>
        }
      />
      <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">
        Interpretive guidance generated from DSP measurements. Not a ground-truth measurement.
      </p>
      {phase2StatusMessage && !hasPhase2 && (
        <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">
          {phase2StatusMessage}
        </p>
      )}
      {!hasRenderablePhase2Content && !phase2StatusMessage && (
        <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">
          Draft — AI interpretation is incomplete or unavailable.
        </p>
      )}
    </section>
  );
}

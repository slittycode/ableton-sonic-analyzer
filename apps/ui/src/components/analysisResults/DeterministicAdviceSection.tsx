import type { Phase1Result } from '../../types';
import { buildDeterministicAdvice } from '../../services/deterministicRecommendations';
import { CitationBlock } from '../CitationBlock';
import { DeviceRack, Pill } from '../ui';

// Phase-2-off fallback: clearly-labeled deterministic Live 12 advice mapped
// from the measured spectrum and dynamics. Mounted by AnalysisResults only
// when `shouldShowDeterministicFallback` says interpretation is settled and
// produced nothing displayable — never alongside real Phase 2 output.
export function DeterministicAdviceSection({ phase1 }: { phase1: Phase1Result }) {
  const cards = buildDeterministicAdvice(phase1);
  if (cards.length === 0) return null;

  return (
    <section data-testid="deterministic-advice">
      <DeviceRack
        name="Deterministic Baseline"
        subtitle="Live 12 starting points"
        action={
          <Pill tone="neutral" size="xs">
            NO AI
          </Pill>
        }
      >
        <div className="space-y-4 p-4">
          <p className="text-micro text-text-secondary">
            Deterministic mapping from measured spectrum and dynamics — not AI
            interpretation. Enable AI interpretation (Phase 2) for richer,
            track-specific advice.
          </p>
          <ul className="space-y-4">
            {cards.map((card) => (
              <li key={card.id} className="space-y-1.5 border-l-2 border-border-light pl-3">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-mono text-xs uppercase tracking-wider text-accent">
                    {card.device}
                  </span>
                  <span className="text-micro text-text-secondary">{card.title}</span>
                </div>
                <p className="text-xs leading-relaxed text-text-primary">{card.detail}</p>
                {card.hedges.map((hedge) => (
                  <p key={hedge} className="text-micro text-warning">
                    {hedge}
                  </p>
                ))}
                <CitationBlock phase1={phase1} fields={card.phase1Fields} maxRows={2} />
              </li>
            ))}
          </ul>
        </div>
      </DeviceRack>
    </section>
  );
}

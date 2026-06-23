import type { Phase2Result } from '../../types';
import { truncateAtSentenceBoundary } from '../analysisResultsViewModel';
import { Panel, Pill } from '../ui';
import { ResultsSectionHeader } from './shared';

type WarpGuide = NonNullable<Phase2Result['warpGuide']>;

export function WarpGuideSection({ warpGuide }: { warpGuide: WarpGuide }) {
  // warpTargets was derived in the AnalysisResults parent solely for this
  // section; it folds in here since it is a pure function of warpGuide.
  const warpTargets = [
    { label: 'Full Track', target: warpGuide.fullTrack },
    { label: 'Drums', target: warpGuide.drums },
    { label: 'Bass', target: warpGuide.bass },
    { label: 'Melodic', target: warpGuide.melodic },
    ...(warpGuide.vocals ? [{ label: 'Vocals', target: warpGuide.vocals }] : []),
  ];

  return (
    <section id="section-warp-guide" className="space-y-6 scroll-mt-24">
      <ResultsSectionHeader
        title="Warp Guide"
        rightSlot={
          <Pill tone="neutral" variant="outline" size="sm">
            CLIP PREP
          </Pill>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {warpTargets.map(({ label, target }) => (
          <Panel key={label} variant="surface" padding="lg" className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">{label}</p>
              <span className="text-micro font-mono uppercase px-1.5 py-0.5 rounded border border-accent/30 bg-accent/5 text-accent">
                {target.warpMode}
              </span>
            </div>
            {target.settings && (
              <p className="text-meta font-mono text-text-secondary uppercase tracking-wide">
                {target.settings}
              </p>
            )}
            <p className="text-xs font-mono text-text-secondary leading-relaxed">
              {truncateAtSentenceBoundary(target.reason, 220)}
            </p>
          </Panel>
        ))}
      </div>

      <Panel variant="surface" padding="lg">
        <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">Why These Modes</p>
        <p className="mt-2 text-xs font-mono text-text-secondary leading-relaxed">
          {truncateAtSentenceBoundary(warpGuide.rationale, 320)}
        </p>
      </Panel>
    </section>
  );
}

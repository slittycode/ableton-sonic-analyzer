import type { Phase1Result, Phase2Result } from '../../types';
import { getTextRoleClassName } from '../../utils/displayText';
import { truncateAtSentenceBoundary } from '../analysisResultsViewModel';
import { CitationBlock } from '../CitationBlock';
import { Panel, Pill } from '../ui';
import { ResultsSectionHeader, textRoleClassName } from './shared';

type TrackLayout = NonNullable<Phase2Result['trackLayout']>;

export function TrackLayoutSection({
  trackLayout,
  phase1,
}: {
  trackLayout: TrackLayout;
  phase1: Phase1Result;
}) {
  return (
    <section id="section-track-layout" className="space-y-6 scroll-mt-24">
      <ResultsSectionHeader
        title="Track Layout"
        rightSlot={
          <Pill tone="neutral" variant="outline" size="sm">
            SCAFFOLD
          </Pill>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {trackLayout.map((item) => (
          <Panel key={`${item.order}-${item.name}`} variant="surface" padding="lg" className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                <span className="w-6 h-6 rounded-sm bg-bg-app border border-border text-accent font-mono text-meta flex items-center justify-center">
                  {item.order}
                </span>
                <div className="min-w-0">
                  <h3
                    data-text-role="item-title"
                    className={textRoleClassName('item-title', 'truncate')}
                  >
                    {item.name}
                  </h3>
                  <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
                    {item.type}
                  </p>
                </div>
              </div>
            </div>
            <p data-text-role="body" className={textRoleClassName('body')}>
              {truncateAtSentenceBoundary(item.purpose, 220)}
            </p>
            {/* Audit Finding #2: replaced the legacy GroundingBadgeList
                (9px field-path pills) with the structured CitationBlock
                primitive, finishing the chain-of-custody visual treatment
                that already lands on Mix Chain / Patches / Sonic cards.
                Segment indexes (Track Layout-only) ride as a synthetic
                extra row at the bottom of the block. */}
            <CitationBlock
              phase1={phase1}
              fields={item.grounding.phase1Fields}
              extraRows={
                Array.isArray(item.grounding.segmentIndexes) &&
                item.grounding.segmentIndexes.length > 0
                  ? [
                      {
                        label: 'Active in segments',
                        value: item.grounding.segmentIndexes.join(' · '),
                      },
                    ]
                  : undefined
              }
              testId={`track-layout-citation-${item.order ?? 0}-${item.name}`}
            />
          </Panel>
        ))}
      </div>
    </section>
  );
}

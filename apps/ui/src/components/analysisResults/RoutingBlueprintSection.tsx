import type { Phase2Result } from '../../types';
import { getTextRoleClassName } from '../../utils/displayText';
import { truncateAtSentenceBoundary } from '../analysisResultsViewModel';
import { Panel, Pill } from '../ui';
import { MetaBadgeList, ResultsSectionHeader, textRoleClassName } from './shared';

type RoutingBlueprint = NonNullable<Phase2Result['routingBlueprint']>;

export function RoutingBlueprintSection({
  routingBlueprint,
}: {
  routingBlueprint: RoutingBlueprint;
}) {
  return (
    <section id="section-routing-blueprint" className="space-y-6 scroll-mt-24">
      <ResultsSectionHeader
        title="Routing Blueprint"
        rightSlot={
          <Pill tone="neutral" variant="outline" size="sm">
            SIGNAL MAP
          </Pill>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Panel variant="surface" padding="lg" className="space-y-2">
          <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>Sidechain Source</p>
          <p data-text-role="item-title" className={getTextRoleClassName('item-title')}>
            {routingBlueprint.sidechainSource ?? 'Not specified'}
          </p>
        </Panel>
        <Panel variant="surface" padding="lg" className="space-y-2 md:col-span-2">
          <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>Sidechain Targets</p>
          <div className="flex flex-wrap gap-1.5">
            {routingBlueprint.sidechainTargets.map((target) => (
              <span
                key={target}
                className="text-micro font-mono uppercase px-1.5 py-0.5 rounded border border-accent/30 bg-accent/5 text-accent"
              >
                {target}
              </span>
            ))}
          </div>
        </Panel>
      </div>

      {routingBlueprint.returns.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {routingBlueprint.returns.map((returnTrack) => (
            <Panel key={returnTrack.name} variant="surface" padding="lg" className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <h3 data-text-role="item-title" className={getTextRoleClassName('item-title')}>
                  {returnTrack.name}
                </h3>
                <span className="text-micro font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary">
                  {returnTrack.deviceFocus}
                </span>
              </div>
              <p data-text-role="body" className={textRoleClassName('body')}>
                {truncateAtSentenceBoundary(returnTrack.purpose, 220)}
              </p>
              <MetaBadgeList
                items={[
                  { label: 'Sends', value: returnTrack.sendSources.join(', ') },
                  { label: 'Level', value: returnTrack.levelGuidance },
                ]}
              />
            </Panel>
          ))}
        </div>
      )}

      {routingBlueprint.notes.length > 0 && (
        <Panel variant="surface" padding="lg" className="space-y-2">
          <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">Routing Notes</p>
          {routingBlueprint.notes.map((note, index) => (
            <p key={`${note}-${index}`} className="text-xs font-mono text-text-secondary leading-relaxed">
              {truncateAtSentenceBoundary(note, 220)}
            </p>
          ))}
        </Panel>
      )}
    </section>
  );
}

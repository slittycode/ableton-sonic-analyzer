import type { Phase2Result } from '../../types';
import { truncateAtSentenceBoundary } from '../analysisResultsViewModel';
import { MetricTile, Panel, Pill, TokenBadgeList } from '../ui';
import { ResultsSectionHeader, textRoleClassName, type StyleProfileSectionState } from './shared';

type StyleProfile = NonNullable<Phase2Result['styleProfile']>;

function stateLabel(state: StyleProfileSectionState): string {
  if (state === 'disabled') return 'DISABLED';
  if (state === 'pending') return 'PENDING';
  if (state === 'omitted') return 'NOT RETURNED';
  return 'DROPPED';
}

function stateDescription(state: StyleProfileSectionState): string {
  if (state === 'disabled') {
    return 'AI interpretation was disabled for this run, so no style profile was generated.';
  }
  if (state === 'pending') {
    return 'Style profile is not ready yet. AI interpretation is still running or did not finish with a usable result.';
  }
  if (state === 'omitted') {
    return 'AI interpretation completed, but this run did not return a structured style profile.';
  }
  return 'The model returned an invalid style profile, so ASA ignored it. See interpretation warnings above.';
}

export function StyleProfileSection({
  styleProfile,
  styleProfileSectionState,
  phase2StatusMessage,
}: {
  styleProfile: StyleProfile | null;
  styleProfileSectionState: StyleProfileSectionState;
  phase2StatusMessage: string | null;
}) {
  return (
    <section id="section-style-profile" className="space-y-6 scroll-mt-24">
      <ResultsSectionHeader
        title="Style Profile"
        rightSlot={
          styleProfileSectionState === 'ready' ? (
            <Pill tone="accent" variant="outline" size="sm">
              STRUCTURED
            </Pill>
          ) : (
            <Pill tone="neutral" variant="outline" size="sm">
              {stateLabel(styleProfileSectionState)}
            </Pill>
          )
        }
      />

      {styleProfile ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <MetricTile
              accent="accent"
              size="xl"
              label="Tempo"
              value={styleProfile.authoritativeMeasurements.bpm ?? '—'}
              unit={styleProfile.authoritativeMeasurements.bpm != null ? 'BPM' : undefined}
            />
            <MetricTile
              accent="accent"
              size="xl"
              label="Key"
              value={styleProfile.authoritativeMeasurements.key ?? '—'}
            />
            <MetricTile
              accent="accent"
              size="xl"
              label="Meter"
              value={styleProfile.authoritativeMeasurements.timeSignature ?? '—'}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Panel variant="surface" padding="lg" className="space-y-3">
              <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">
                Genre
              </p>
              <div className="flex flex-wrap gap-1.5">
                <Pill tone="accent" variant="solid" size="sm">
                  {styleProfile.genre}
                </Pill>
                {styleProfile.subGenre && (
                  <Pill tone="neutral" variant="outline" size="sm">
                    {styleProfile.subGenre}
                  </Pill>
                )}
              </div>
              {styleProfile.mood.length > 0 && (
                <div className="space-y-2">
                  <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">
                    Mood
                  </p>
                  <TokenBadgeList
                    items={styleProfile.mood.map((item) => ({ label: item, tone: 'accent' as const }))}
                  />
                </div>
              )}
            </Panel>

            <Panel variant="surface" padding="lg" className="space-y-3">
              {styleProfile.instruments.length > 0 && (
                <div className="space-y-2">
                  <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">
                    Instruments
                  </p>
                  <TokenBadgeList
                    items={styleProfile.instruments.map((item) => ({ label: item, tone: 'neutral' as const }))}
                  />
                </div>
              )}
              {styleProfile.productionTechniques.length > 0 && (
                <div className="space-y-2">
                  <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">
                    Production Techniques
                  </p>
                  <TokenBadgeList
                    items={styleProfile.productionTechniques.map((item) => ({ label: item, tone: 'neutral' as const }))}
                  />
                </div>
              )}
            </Panel>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Panel variant="surface" padding="lg" className="space-y-2">
              <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">
                Style Read
              </p>
              <p data-text-role="body" className={textRoleClassName('body')}>
                {truncateAtSentenceBoundary(styleProfile.description, 320)}
              </p>
            </Panel>
            {/* Reusable Prompt previously rendered as an accent-washed card
                (bg-accent/5). Neutralized to match its Style Read sibling — it's
                reference text, not primary signal, so accent is reserved. */}
            <Panel variant="surface" padding="lg" className="space-y-2">
              <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">
                Reusable Prompt
              </p>
              <p data-text-role="body" className={textRoleClassName('body')}>
                {truncateAtSentenceBoundary(styleProfile.generationPrompt, 320)}
              </p>
            </Panel>
          </div>
        </>
      ) : (
        <Panel variant="surface" padding="lg" className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="neutral" variant="outline" size="xs">
              {stateLabel(styleProfileSectionState)}
            </Pill>
          </div>
          <p data-text-role="body" className={textRoleClassName('body')}>
            {stateDescription(styleProfileSectionState)}
          </p>
          {styleProfileSectionState === 'disabled' && phase2StatusMessage && (
            <p className="text-meta font-mono uppercase tracking-[0.16em] text-text-secondary/80">
              {phase2StatusMessage}
            </p>
          )}
        </Panel>
      )}
    </section>
  );
}

import { ChevronDown, ChevronRight } from 'lucide-react';

import type { Phase1Result } from '../../types';
import { formatDisplayText } from '../../utils/displayText';
import {
  buildMixChainGroups,
  truncateAtSentenceBoundary,
} from '../analysisResultsViewModel';
import { CitationBlock, CitationHeadline } from '../CitationBlock';
import { DeviceRack, Pill } from '../ui';
import { RecommendationVerificationBadge } from '../RecommendationVerificationBadge';
import {
  AppliedCheckbox,
  Collapsible,
  ContractEntriesBlock,
  ContractValidatedBadge,
  groupIcon,
  MetaBadgeList,
  ResultsSectionHeader,
  textRoleClassName,
} from './shared';

type MixChainGroups = ReturnType<typeof buildMixChainGroups>;

export function MixChainSection({
  mixGroups,
  mixAppliedCount,
  mixCardCount,
  audioContentHash,
  openMix,
  onToggle,
  appliedIds,
  onToggleApplied,
  phase1,
}: {
  mixGroups: MixChainGroups;
  mixAppliedCount: number;
  mixCardCount: number;
  audioContentHash?: string | null;
  openMix: Record<string, boolean>;
  onToggle: (id: string) => void;
  appliedIds: Set<string>;
  onToggleApplied: (id: string) => void;
  phase1: Phase1Result;
}) {
  return (
    <section id="section-mix-chain" className="space-y-6 scroll-mt-24">
      <ResultsSectionHeader
        title={formatDisplayText('Mix & Master Chain', 'title')}
        titleRole="section-title"
        rightSlot={
          <div className="flex items-center gap-2">
            {/* Audit Finding #14: section-level progress glance. Only
                surfaces when the tracker is wired (audioContentHash
                available) AND at least one card has been applied —
                avoids leading with a "0 of N" on first view. */}
            {audioContentHash && mixAppliedCount > 0 && (
              <Pill
                tone="success"
                size="sm"
                data-testid="mix-chain-applied-progress"
              >
                {mixAppliedCount} of {mixCardCount} applied
              </Pill>
            )}
            <span className="text-meta font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">SIGNAL FLOW</span>
          </div>
        }
      />

      <div className="space-y-4">
        {mixGroups
          .filter((group) => group.cards.length > 0)
          .map((group) => (
          <DeviceRack
            key={group.name}
            // The DeviceRack title strip carries the group name. The
            // emoji-or-SVG from groupIcon() + uppercase group.name
            // ("DRUM PROCESSING" etc.) are preserved verbatim so
            // analysisResultsUi.test.ts:441-450 selectors (toContain
            // ('🥁 DRUM PROCESSING')) AND the BASS PROCESSING test at
            // :448 which expects a `lucide-audio-waveform` SVG class
            // nearby both pass. The name must be a React fragment —
            // template-literal coercion turns the AudioWaveform JSX
            // node into "[object Object]" and the SVG is lost.
            name={
              <>
                {groupIcon(group.name)} {group.name}
              </>
            }
            status="idle"
          >
            {/* Audit-preserved annotation paragraph kept here so
                data-text-role="body" presence assertions
                (analysisResultsUi.test.ts:474) stay green. */}
            {group.annotation && (
              <p
                data-text-role="meta"
                className={textRoleClassName('meta', 'mb-3')}
              >
                {group.annotation}
              </p>
            )}

            {/* Keep this exact className — the brittle assertion
                analysisResultsUi.test.ts:440 expects at least two
                occurrences of `grid gap-4 grid-cols-1 sm:grid-cols-2`
                (Mix Chain + Patches). */}
            <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
              {group.cards.map((card) => {
                const isOpen = !!openMix[card.id];
                const isApplied = appliedIds.has(card.id);
                return (
                  <div
                    key={card.id}
                    data-applied={isApplied || undefined}
                    className={`bg-bg-card border border-border rounded-sm overflow-hidden self-start transition-colors hover:border-accent/40 hover:bg-bg-card-hover/70 ${
                      isApplied ? 'border-l-2 border-l-success' : ''
                    }`}
                  >
                    <button
                      onClick={() => onToggle(card.id)}
                      className="w-full text-left px-4 py-3 border-b border-border bg-bg-panel/60 hover:bg-bg-panel transition-colors"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          {/* Audit quick-hit: order badges (`{card.order}`)
                            used to render as small numbered chips next to
                            each device. Because the cards are grouped by
                            processing stage AFTER ordering, the numbers
                            appeared out-of-order within each group ("1, 6,
                            8, 9 / 2, 4 / 5, 7 / 3 / 10"), which read as
                            a presentation bug. The visual sequence within
                            each group is already meaningful — the badge
                            added confusion without information. Dropped. */}
                          <div className="flex items-center gap-2">
                            <h4
                              data-text-role="item-title"
                              className={textRoleClassName('item-title', 'truncate')}
                            >
                              {card.device}
                            </h4>
                            <span className="text-micro font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary whitespace-nowrap">
                              {card.category}
                            </span>
                            <RecommendationVerificationBadge
                              trackContext={card.trackContext}
                              category={card.category}
                            />
                            <ContractValidatedBadge
                              entries={card.contractEntries}
                              testId={`mix-chain-contract-badge-${card.id}`}
                            />
                          </div>
                          {/* Audit Finding #3: primary citation visible in
                            the collapsed header so the chain-of-custody
                            evidence isn't gated behind expansion. The
                            expanded CitationBlock below still carries the
                            full multi-row list. */}
                          {card.phase1Fields.length > 0 && (
                            <div className="mt-1 flex min-w-0">
                              <CitationHeadline
                                phase1={phase1}
                                field={card.phase1Fields[0]}
                                testId={`mix-chain-headline-${card.id}`}
                              />
                            </div>
                          )}
                          <p data-text-role="body" className={textRoleClassName('body', 'mt-1 truncate')}>
                            {card.role}
                          </p>
                          <div className="mt-2">
                            <MetaBadgeList
                              items={[
                                // Audit N3/N8: drop `Family: Native` from
                                // the collapsed card. `deviceFamily` is
                                // almost always `NATIVE`; keeping it
                                // burns chip-row real estate without
                                // adding signal. Surfaces only the two
                                // chips that actually vary per card.
                                { label: 'Context', value: card.trackContext },
                                { label: 'Stage', value: card.workflowStage },
                              ]}
                            />
                          </div>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          {audioContentHash && (
                            <AppliedCheckbox
                              isApplied={isApplied}
                              onToggle={() => onToggleApplied(card.id)}
                              ariaLabel={`Mark ${card.device} as applied`}
                            />
                          )}
                          <span className="text-text-secondary">
                            {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                          </span>
                        </div>
                      </div>
                    </button>

                    <Collapsible isOpen={isOpen}>
                      <div className="p-4 space-y-3">
                        {/* Audit Finding #2 + #3: structured chain-of-custody
                            evidence at the top of the expanded card. */}
                        <CitationBlock
                          phase1={phase1}
                          fields={card.phase1Fields}
                          testId={`mix-chain-citation-${card.id}`}
                        />
                        <p data-text-role="body" className={textRoleClassName('body')}>
                          {truncateAtSentenceBoundary(card.role, 320)}
                        </p>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          {card.parameters.map((parameter, idx) => (
                            <div
                              key={`${card.id}-parameter-${idx}`}
                              className="border border-border rounded-sm px-2 py-1 bg-bg-panel/40"
                            >
                              <p className="text-meta font-mono uppercase text-text-secondary">{parameter.label}</p>
                              <p className="text-xs font-mono text-text-primary font-bold">{parameter.value}</p>
                            </div>
                          ))}
                        </div>

                        <ContractEntriesBlock
                          entries={card.contractEntries}
                          testId={`mix-chain-contract-${card.id}`}
                        />

                        <div className="border border-accent/20 bg-accent/5 rounded-sm px-2 py-2">
                          <p className="text-meta font-mono text-accent uppercase tracking-wide">PRO TIP</p>
                          <p className="text-xs font-mono text-text-secondary mt-1 leading-relaxed">
                            {truncateAtSentenceBoundary(card.proTip, 320)}
                          </p>
                        </div>
                      </div>
                    </Collapsible>
                  </div>
                );
              })}
            </div>
          </DeviceRack>
        ))}
      </div>
    </section>
  );
}

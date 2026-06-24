import { ChevronDown, ChevronRight, Settings2, Sliders } from 'lucide-react';

import type { Phase1Result } from '../../types';
import { formatDisplayText } from '../../utils/displayText';
import {
  buildPatchGroups,
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

type PatchGroups = ReturnType<typeof buildPatchGroups>;

export function PatchFrameworkSection({
  patchGroups,
  patchAppliedCount,
  patchTotalCount,
  audioContentHash,
  openPatch,
  onToggle,
  appliedIds,
  onToggleApplied,
  phase1,
}: {
  patchGroups: PatchGroups;
  patchAppliedCount: number;
  patchTotalCount: number;
  audioContentHash?: string | null;
  openPatch: Record<string, boolean>;
  onToggle: (id: string) => void;
  appliedIds: Set<string>;
  onToggleApplied: (id: string) => void;
  phase1: Phase1Result;
}) {
  return (
    <section id="section-patches" className="space-y-6 scroll-mt-24">
      <ResultsSectionHeader
        title={formatDisplayText('Patch Framework', 'title')}
        titleRole="section-title"
        rightSlot={
          <div className="flex items-center gap-2">
            {audioContentHash && patchAppliedCount > 0 && (
              <Pill
                tone="success"
                size="sm"
                data-testid="patches-applied-progress"
              >
                {patchAppliedCount} of {patchTotalCount} applied
              </Pill>
            )}
            <Sliders className="w-4 h-4 text-accent opacity-70" />
          </div>
        }
      />

      {/* Audit follow-up: cards grouped by processing stage (Drum / Bass /
          Synth / Mid / High-end / Master) using the same heuristic and
          emoji eyebrows as Mix Chain above. Producers can now jump to the
          bass patch without scanning all 8 cards. */}
      <div className="space-y-4">
        {patchGroups.map((group) => (
          <DeviceRack
            key={group.name}
            // Mirror Mix Chain's D.5b shape. JSX fragment (not template
            // literal) so groupIcon's BASS PROCESSING return value (an
            // <AudioWaveform> SVG) renders as a real React node — the
            // template-literal version stringifies it to "[object
            // Object]" and analysisResultsUi.test.ts:448 fails.
            name={
              <>
                {groupIcon(group.name)} {group.name}
              </>
            }
            status="idle"
          >
            {/* Keep the exact className — analysisResultsUi.test.ts:440
                expects ≥2 occurrences of `grid gap-4 grid-cols-1
                sm:grid-cols-2` across Mix Chain + Patches. */}
            <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
              {group.cards.map((patch) => {
                const isOpen = !!openPatch[patch.id];
                const isApplied = appliedIds.has(patch.id);
                return (
                  <div
                    key={patch.id}
                    data-applied={isApplied || undefined}
                    className={`bg-bg-card border border-border rounded-sm overflow-hidden self-start transition-colors hover:border-accent/40 hover:bg-bg-card-hover/70 ${
                      isApplied ? 'border-l-2 border-l-success' : ''
                    }`}
                  >
                    <button
                      onClick={() => onToggle(patch.id)}
                      className="w-full text-left px-4 py-3 border-b border-border bg-bg-panel/60 hover:bg-bg-panel transition-colors"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <Settings2 className="w-4 h-4 text-accent" />
                            <h4
                              data-text-role="item-title"
                              className={textRoleClassName('item-title', 'truncate')}
                            >
                              {patch.device}
                            </h4>
                            {patch.transcriptionDerived && (
                              <span className="text-micro font-mono uppercase px-1.5 py-0.5 rounded border border-accent/40 text-accent whitespace-nowrap">
                                Transcription-derived
                              </span>
                            )}
                            <span className="text-micro font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary whitespace-nowrap">
                              {patch.category}
                            </span>
                            <RecommendationVerificationBadge
                              trackContext={patch.trackContext}
                              category={patch.category}
                            />
                            <ContractValidatedBadge
                              entries={patch.contractEntries}
                              testId={`patch-contract-badge-${patch.id}`}
                            />
                          </div>
                          {/* Audit Finding #3: primary citation in the
                            collapsed header so the chain-of-custody
                            evidence is visible without expanding. */}
                          {patch.phase1Fields.length > 0 && (
                            <div className="mt-1 flex min-w-0">
                              <CitationHeadline
                                phase1={phase1}
                                field={patch.phase1Fields[0]}
                                testId={`patch-headline-${patch.id}`}
                              />
                            </div>
                          )}
                          {/* Audit Finding #1B: the per-card patchRole
                            paragraph used to render a duplicated
                            category-keyed placeholder ("Primary tone
                            generator" on every SYNTHESIS card). It has been
                            removed; the category chip above carries the
                            bucket and `whyThisWorks` (inside the expanded
                            card body) carries the actionable explanation. */}
                          <div className="mt-2">
                            <MetaBadgeList
                              items={[
                                // Same Family-chip drop as Mix Chain cards (audit N3/N8).
                                { label: 'Context', value: patch.trackContext },
                                { label: 'Stage', value: patch.workflowStage },
                              ]}
                            />
                          </div>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          {audioContentHash && (
                            <AppliedCheckbox
                              isApplied={isApplied}
                              onToggle={() => onToggleApplied(patch.id)}
                              ariaLabel={`Mark ${patch.device} patch as applied`}
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
                        {/* Audit Finding #2 + #3: chain-of-custody block
                            at the top of the expanded patch card. */}
                        <CitationBlock
                          phase1={phase1}
                          fields={patch.phase1Fields}
                          testId={`patch-citation-${patch.id}`}
                        />
                        <p data-text-role="body" className={textRoleClassName('body')}>
                          {truncateAtSentenceBoundary(patch.whyThisWorks, 600)}
                        </p>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          {patch.parameters.map((parameter, idx) => (
                            <div
                              key={`${patch.id}-parameter-${idx}`}
                              className="border border-border rounded-sm px-2 py-1 bg-bg-panel/40"
                            >
                              <p className="text-meta font-mono uppercase text-text-secondary">{parameter.label}</p>
                              <p className="text-xs font-mono text-text-primary font-bold">{parameter.value}</p>
                            </div>
                          ))}
                        </div>

                        <ContractEntriesBlock
                          entries={patch.contractEntries}
                          testId={`patch-contract-${patch.id}`}
                        />

                        <div className="border border-accent/20 bg-accent/5 rounded-sm px-2 py-2">
                          <p className="text-meta font-mono text-accent uppercase tracking-wide">PRO TIP</p>
                          <p className="text-xs font-mono text-text-secondary mt-1 leading-relaxed">
                            {truncateAtSentenceBoundary(patch.proTip, 320)}
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

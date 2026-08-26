import { ChevronDown, ChevronRight } from 'lucide-react';

import type { Phase1Result } from '../../types';
import { formatDisplayText } from '../../utils/displayText';
import { CitationBlock, CitationHeadline } from '../CitationBlock';
import {
  buildSonicElementCards,
  calculateStereoBandStyle,
} from '../analysisResultsViewModel';
import {
  Collapsible,
  lowConfidenceIndicator,
  ResultsSectionHeader,
  textRoleClassName,
} from './shared';

type SonicCard = ReturnType<typeof buildSonicElementCards>[number];

export function SonicElementsSection({
  sonicCards,
  openSonic,
  onToggle,
  phase1,
  chordsAreApproximate,
}: {
  sonicCards: SonicCard[];
  openSonic: Set<string>;
  onToggle: (id: string) => void;
  phase1: Phase1Result;
  chordsAreApproximate: boolean;
}) {
  return (
    <section id="section-sonic-elements" className="space-y-6 scroll-mt-24">
      <ResultsSectionHeader
        title={formatDisplayText('Sonic Elements & Reconstruction', 'title')}
        titleRole="section-title"
        rightSlot={
          <span className="text-meta font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">COLLAPSIBLE</span>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
        {sonicCards.map((card) => {
          const isOpen = openSonic.has(card.id);
          return (
            <div
              key={card.id}
              className="bg-bg-card border border-border rounded-sm overflow-hidden self-start flex flex-col transition-colors hover:border-accent/40 hover:bg-bg-card-hover/70"
            >
              <button
                onClick={() => onToggle(card.id)}
                className="w-full px-4 py-3 border-b border-border bg-bg-panel/60 text-left hover:bg-bg-panel transition-colors"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span data-text-role="meta" className={textRoleClassName('meta')}>{card.icon}</span>
                      <h3
                        data-text-role="item-title"
                        className={textRoleClassName('item-title', 'truncate')}
                      >
                        {card.title}
                      </h3>
                      {card.id === 'harmonicContent' && lowConfidenceIndicator(chordsAreApproximate)}
                      {card.transcriptionDerived && (
                        <span className="text-micro font-mono uppercase px-1.5 py-0.5 rounded border border-accent/40 text-accent whitespace-nowrap">
                          Transcription-derived
                        </span>
                      )}
                    </div>
                    {/* Audit Finding #3: primary citation visible in the
                      collapsed header. Mirrors the Mix Chain / Patch
                      placement so all three card types feel parallel. */}
                    {card.phase1Fields.length > 0 && (
                      <div className="mt-1 flex min-w-0">
                        <CitationHeadline
                          phase1={phase1}
                          field={card.phase1Fields[0]}
                          testId={`sonic-headline-${card.id}`}
                        />
                      </div>
                    )}
                    <p data-text-role="body" className={textRoleClassName('body', 'mt-1 truncate')}>
                      {card.summary}
                    </p>
                  </div>
                  <span className="text-text-secondary">
                    {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  </span>
                </div>
              </button>

              <Collapsible isOpen={isOpen}>
                <div className="p-4 space-y-3">
                  {/* Audit Finding #2 + #3: chain-of-custody block at the
                      TOP of the expanded card so the producer sees the
                      measurements + worst-confidence band BEFORE reading
                      the prose description. */}
                  <CitationBlock
                    phase1={phase1}
                    fields={card.phase1Fields}
                    testId={`sonic-citation-${card.id}`}
                  />

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p data-text-role="body" className={textRoleClassName('body')}>
                      {card.description}
                    </p>
                  </div>

                  <div className="space-y-2">
                    {card.measurements.map((measurement, idx) => (
                      <div
                        key={`${card.id}-measurement-${idx}`}
                        className="flex items-center justify-between text-eyebrow font-mono border border-border rounded-sm px-2 py-1 bg-bg-panel/40"
                      >
                        <span className="text-text-secondary truncate pr-2">
                          {measurement.icon} {measurement.label}
                        </span>
                        <span className="text-text-primary font-bold whitespace-nowrap">{measurement.value}</span>
                      </div>
                    ))}

                    {card.isWidthAndStereo && (
                      <div className="mt-3 border border-border rounded-sm p-2 bg-bg-panel/40">
                        <div className="flex items-center justify-between text-meta font-mono text-text-secondary mb-1">
                          <span>L</span>
                          <span>R</span>
                        </div>
                        <div className="relative h-3 rounded bg-bg-app border border-border overflow-hidden">
                          <div className="absolute inset-y-0 left-1/2 w-px bg-text-secondary/70" />
                          <div
                            className="absolute inset-y-0 bg-accent/50 border border-accent/60 rounded"
                            style={calculateStereoBandStyle(phase1.stereoWidth)}
                          />
                        </div>
                        <p className="text-meta font-mono text-text-secondary mt-1">
                          Width band: {phase1.stereoWidth.toFixed(2)} around center
                        </p>
                      </div>
                    )}
                  </div>
                  </div>
                </div>
              </Collapsible>
            </div>
          );
        })}
      </div>
    </section>
  );
}

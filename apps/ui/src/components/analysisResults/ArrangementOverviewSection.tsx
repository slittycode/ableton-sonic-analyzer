import { ChevronDown, ChevronRight } from 'lucide-react';

import {
  buildArrangementViewModel,
  truncateBySentenceCount,
} from '../analysisResultsViewModel';
import { Collapsible, ResultsSectionHeader, textRoleClassName } from './shared';

// Arrangement-exclusive helpers, moved verbatim out of the AnalysisResults
// monolith (Phase 5 split) alongside the section they serve.
const SEGMENT_ORDER_PALETTE = ['#e05c00', '#c44b8a', '#2d9cdb', '#27ae60'] as const;
const TRACK_AVERAGE_LUFS = -7.5;

function getSegmentPaletteColor(segmentIndex: number): string {
  return SEGMENT_ORDER_PALETTE[segmentIndex % SEGMENT_ORDER_PALETTE.length];
}

function withAlpha(hexColor: string, alphaHex: string): string {
  return `${hexColor}${alphaHex}`;
}

type ArrangementViewModel = NonNullable<ReturnType<typeof buildArrangementViewModel>>;

export function ArrangementOverviewSection({
  arrangement,
  openArrangement,
  onToggle,
  isPhase2V2,
}: {
  arrangement: ArrangementViewModel;
  openArrangement: Record<string, boolean>;
  onToggle: (id: string) => void;
  isPhase2V2: boolean;
}) {
  return (
    <section id="section-arrangement" className="space-y-6 scroll-mt-24">
      <ResultsSectionHeader
        title="Arrangement Overview"
        rightSlot={
          <span className="text-meta font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">TIMELINE</span>
        }
      />

      {arrangement.summary && (
        <p data-text-role="body" className={textRoleClassName('body', 'opacity-80')}>
          {arrangement.summary}
        </p>
      )}

      <div className="bg-bg-card border border-border rounded-sm p-4 space-y-4">
        <div className="relative pt-6">
          <div className="relative h-14 border border-border rounded-sm overflow-hidden bg-bg-app">
            {arrangement.segments.map((segment, segmentIndex) => (
              <div
                key={segment.id}
                className="absolute top-0 bottom-0 px-2 py-1 border-r border-bg-app/30 text-meta font-mono text-white flex items-center justify-center text-center overflow-hidden"
                style={{
                  left: `${segment.leftPercent}%`,
                  width: `${segment.widthPercent}%`,
                  backgroundColor: getSegmentPaletteColor(segmentIndex),
                }}
                title={`${segment.name} • ${segment.lufsLabel}`}
              >
                <span className="truncate">{segment.name} • {segment.lufsLabel}</span>
              </div>
            ))}

            {arrangement.noveltyMarkers.map((marker, idx) => (
              <div
                key={`marker-${idx}`}
                className="absolute top-0 bottom-0 pointer-events-none"
                style={{ left: `${marker.leftPercent}%` }}
              >
                <div className="absolute -top-5 -translate-x-1/2 bg-bg-panel border border-border rounded px-1 py-[1px] text-micro font-mono text-text-secondary whitespace-nowrap">
                  {marker.label}
                </div>
                <div className="h-full w-px bg-accent/90" />
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between mt-2 text-meta font-mono text-text-secondary">
            <span>0s</span>
            <span>{arrangement.totalDuration.toFixed(1)}s</span>
          </div>
        </div>

        {arrangement.noveltyNotes && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="h-px bg-border/60 flex-1" />
              <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">
                NOVELTY EVENTS
              </span>
              <div className="h-px bg-border/60 flex-1" />
            </div>
            <p data-text-role="body" className={textRoleClassName('body')}>
              {arrangement.noveltyNotes}
            </p>
          </div>
        )}

        <div className="space-y-2">
          {arrangement.segments.map((segment, segmentIndex) => {
            const isOpen = !!openArrangement[segment.id];
            const segmentColor = getSegmentPaletteColor(segmentIndex);
            const lufsDelta = segment.lufs !== null ? segment.lufs - TRACK_AVERAGE_LUFS : null;
            const lufsDeltaLabel =
              lufsDelta === null
                ? null
                : `${lufsDelta >= 0 ? '▲' : '▼'} ${lufsDelta >= 0 ? '+' : ''}${lufsDelta.toFixed(1)} dB`;
            const lufsDeltaClass =
              lufsDelta === null
                ? ''
                : lufsDelta > 0
                  ? 'text-success border-success/30 bg-success/10'
                  : lufsDelta < 0
                    ? 'text-error border-error/30 bg-error/10'
                    : 'text-text-secondary border-border bg-bg-panel/40';
            return (
              <div
                key={`${segment.id}-detail`}
                className="border border-border border-l-2 rounded-sm overflow-hidden bg-bg-panel/40"
                style={{ borderLeftColor: segmentColor }}
              >
                <button
                  onClick={() => onToggle(segment.id)}
                  className="w-full flex items-center justify-between gap-3 px-3 py-2 text-left hover:bg-bg-card transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span data-text-role="meta" className={textRoleClassName('meta')}>{isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}</span>
                    <span data-text-role="item-title" className={textRoleClassName('item-title', 'truncate')}>{segment.name}</span>
                    <span
                      className="text-meta font-mono px-1.5 py-0.5 rounded border whitespace-nowrap"
                      style={{
                        backgroundColor: withAlpha(segmentColor, '22'),
                        borderColor: withAlpha(segmentColor, '66'),
                        color: segmentColor,
                      }}
                    >
                      {segment.lufsLabel}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {lufsDeltaLabel && (
                      <span className={`text-micro font-mono px-1.5 py-0.5 rounded border whitespace-nowrap ${lufsDeltaClass}`}>
                        {lufsDeltaLabel}
                      </span>
                    )}
                    <span className="text-meta font-mono text-text-secondary whitespace-nowrap">
                      {segment.startTime.toFixed(1)}s - {segment.endTime.toFixed(1)}s
                    </span>
                  </div>
                </button>

                <Collapsible isOpen={isOpen}>
                  <div className="px-3 pb-3 pt-1 space-y-2 border-t border-border/60">
                    <p data-text-role="body" className={textRoleClassName('body')}>
                      {truncateBySentenceCount(segment.description, 4)}
                    </p>
                    {segment.spectralNote && (
                      <div className="border border-border/70 rounded-sm bg-bg-panel/50 px-2 py-2 space-y-1">
                        <span className="inline-flex text-micro font-mono uppercase tracking-wide px-1.5 py-0.5 rounded border border-accent/40 text-accent">
                          SPECTRAL NOTE
                        </span>
                        <p className="text-eyebrow text-text-secondary/90 font-mono leading-relaxed">
                          {segment.spectralNote}
                        </p>
                      </div>
                    )}
                    {isPhase2V2 && (segment.sceneName || segment.abletonAction || segment.automationFocus) && (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                        {segment.sceneName && (
                          <div className="border border-border/70 rounded-sm bg-bg-panel/50 px-2 py-2 space-y-1">
                            <span className="inline-flex text-micro font-mono uppercase tracking-wide px-1.5 py-0.5 rounded border border-border text-text-secondary">
                              Scene
                            </span>
                            <p className="text-eyebrow text-text-secondary/90 font-mono leading-relaxed">
                              {segment.sceneName}
                            </p>
                          </div>
                        )}
                        {segment.abletonAction && (
                          <div className="border border-border/70 rounded-sm bg-bg-panel/50 px-2 py-2 space-y-1">
                            <span className="inline-flex text-micro font-mono uppercase tracking-wide px-1.5 py-0.5 rounded border border-border text-text-secondary">
                              Ableton Action
                            </span>
                            <p className="text-eyebrow text-text-secondary/90 font-mono leading-relaxed">
                              {segment.abletonAction}
                            </p>
                          </div>
                        )}
                        {segment.automationFocus && (
                          <div className="border border-border/70 rounded-sm bg-bg-panel/50 px-2 py-2 space-y-1">
                            <span className="inline-flex text-micro font-mono uppercase tracking-wide px-1.5 py-0.5 rounded border border-border text-text-secondary">
                              Automation Focus
                            </span>
                            <p className="text-eyebrow text-text-secondary/90 font-mono leading-relaxed">
                              {segment.automationFocus}
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </Collapsible>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

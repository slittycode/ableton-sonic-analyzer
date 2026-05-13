// Plain-language read of the separated stems from Gemini.
//
// This panel lives adjacent to <SessionMusicianPanel> and stays useful even
// when the pitch/note draft above is rough or unreliable. It used to live
// inline inside AnalysisResults; extracted here so the file is auditable on
// its own and the visibility helper can be reused.
//
// Notice that the section ID `section-stem-summary` is intentionally NOT on
// this component — it's owned by the wrapper <div> in AnalysisResults so the
// StickyNav anchor stays in one place. We only carry the test ID.

import React from 'react';
import type { StemSummaryResult } from '../types';
import { truncateAtSentenceBoundary } from './analysisResultsViewModel';
import {
  formatDisplayText,
  getTextRoleClassName,
  type TextRole,
} from '../utils/displayText';
import { hasStemListeningNotesContent } from '../services/sessionMusician/stemListeningNotes';

function textRoleClassName(role: TextRole, className = ''): string {
  return [getTextRoleClassName(role), className].filter(Boolean).join(' ');
}

interface StemListeningNotesPanelProps {
  stemSummary: StemSummaryResult | null | undefined;
}

export function StemListeningNotesPanel({ stemSummary }: StemListeningNotesPanelProps) {
  if (!hasStemListeningNotesContent(stemSummary)) return null;

  // hasStemListeningNotesContent guarantees stemSummary is non-null.
  const summary = stemSummary as StemSummaryResult;
  const stems = Array.isArray(summary.stems) ? summary.stems : [];
  const uncertaintyFlags = Array.isArray(summary.uncertaintyFlags)
    ? summary.uncertaintyFlags
    : [];
  const topSummary = typeof summary.summary === 'string' ? summary.summary.trim() : '';

  return (
    <section
      data-testid="stem-listening-notes-panel"
      className="space-y-6"
    >
      <div className="flex items-center justify-between gap-3 border-b border-border pb-2">
        <h2
          data-text-role="section-title"
          className={textRoleClassName('section-title', 'flex items-center gap-2')}
        >
          <span className="w-2 h-2 bg-accent rounded-full flex-shrink-0" />
          {formatDisplayText('Stem listening notes', 'title')}
        </h2>
        <span className="text-[10px] font-mono bg-bg-panel border border-accent/30 text-accent px-2 py-1 rounded font-bold">
          BEST EFFORT
        </span>
      </div>

      <div className="rounded-sm border border-accent/20 bg-accent/5 p-4 space-y-2">
        <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-accent">
          What this is for
        </p>
        <p className="text-xs font-mono text-text-secondary leading-relaxed">
          Plain-language descriptions of the bass and lead stems from Gemini. Reading these is the path that stays useful even when the note draft above is rough.
        </p>
        {topSummary && (
          <p className="text-xs font-mono text-text-secondary leading-relaxed">
            {truncateAtSentenceBoundary(topSummary, 320)}
          </p>
        )}
      </div>

      {uncertaintyFlags.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {uncertaintyFlags.map((flag, index) => (
            <span
              key={`${flag}-${index}`}
              className="text-[10px] font-mono rounded-sm border border-warning/30 bg-warning/10 px-2 py-1 text-warning"
            >
              {flag}
            </span>
          ))}
        </div>
      )}

      {stems.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {stems.map((stem) => (
            <div
              key={stem.stem}
              className="rounded-sm border border-border bg-bg-card p-4 space-y-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3
                    data-text-role="item-title"
                    className={textRoleClassName('item-title')}
                  >
                    {stem.label}
                  </h3>
                  <p
                    data-text-role="body"
                    className={textRoleClassName('body', 'mt-2')}
                  >
                    {truncateAtSentenceBoundary(stem.summary, 220)}
                  </p>
                </div>
                <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-accent/30 bg-accent/5 text-accent">
                  {stem.stem}
                </span>
              </div>

              <div className="grid grid-cols-1 gap-3">
                {stem.bars.map((bar, index) => (
                  <div
                    key={`${stem.stem}-bar-${bar.barStart}-${index}`}
                    className="rounded-sm border border-border/80 bg-bg-panel/50 p-3 space-y-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
                        Bars {bar.barStart}-{bar.barEnd}
                      </span>
                      <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary">
                        {bar.uncertaintyLevel} certainty
                      </span>
                    </div>
                    {bar.noteHypotheses.length > 0 && (
                      <p className="text-xs font-mono text-text-secondary leading-relaxed">
                        Notes: {bar.noteHypotheses.join(', ')}
                      </p>
                    )}
                    {bar.scaleDegreeHypotheses.length > 0 && (
                      <p className="text-xs font-mono text-text-secondary leading-relaxed">
                        Scale degrees: {bar.scaleDegreeHypotheses.join(', ')}
                      </p>
                    )}
                    <p className="text-xs font-mono text-text-secondary leading-relaxed">
                      Rhythm: {truncateAtSentenceBoundary(bar.rhythmicPattern, 180)}
                    </p>
                    <p className="text-xs font-mono text-warning leading-relaxed">
                      Uncertainty: {truncateAtSentenceBoundary(bar.uncertaintyReason, 180)}
                    </p>
                  </div>
                ))}
              </div>

              <div className="space-y-2">
                <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
                  Global pattern
                </p>
                <div className="space-y-1">
                  <p className="text-xs font-mono text-text-secondary leading-relaxed">
                    Bass role: {truncateAtSentenceBoundary(stem.globalPatterns.bassRole, 180)}
                  </p>
                  <p className="text-xs font-mono text-text-secondary leading-relaxed">
                    Musical role: {truncateAtSentenceBoundary(stem.globalPatterns.melodicRole, 180)}
                  </p>
                  <p className="text-xs font-mono text-text-secondary leading-relaxed">
                    Movement: {truncateAtSentenceBoundary(stem.globalPatterns.pumpingOrModulation, 180)}
                  </p>
                  <p className="text-xs font-mono text-text-secondary leading-relaxed">
                    Synthesis: {truncateAtSentenceBoundary(stem.globalPatterns.synthesisCharacter, 180)}
                  </p>
                  <p className="text-xs font-mono text-text-secondary leading-relaxed">
                    Vocal presence: {truncateAtSentenceBoundary(stem.globalPatterns.vocalPresence, 180)}
                  </p>
                  <p className="text-xs font-mono text-text-secondary leading-relaxed">
                    Bass character: {truncateAtSentenceBoundary(stem.globalPatterns.bassCharacter, 180)}
                  </p>
                </div>
              </div>

              {stem.uncertaintyFlags.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {stem.uncertaintyFlags.map((flag, index) => (
                    <span
                      key={`${stem.stem}-flag-${index}`}
                      className="text-[10px] font-mono rounded-sm border border-warning/30 bg-warning/10 px-2 py-1 text-warning"
                    >
                      {flag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

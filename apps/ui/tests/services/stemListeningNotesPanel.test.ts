import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { StemListeningNotesPanel } from '../../src/components/StemListeningNotesPanel';
import type { StemSummaryResult, StemSummaryStem } from '../../src/types';

const stemCard = (overrides: Partial<StemSummaryStem> = {}): StemSummaryStem => ({
  stem: 'bass',
  label: 'Bass stem',
  summary: 'Walks the root and fifth across the verse.',
  bars: [
    {
      barStart: 1,
      barEnd: 4,
      startTime: 0,
      endTime: 8,
      noteHypotheses: ['A2', 'E3'],
      scaleDegreeHypotheses: ['1', '5'],
      rhythmicPattern: 'Quarter notes on the downbeats.',
      uncertaintyLevel: 'LOW',
      uncertaintyReason: 'Clean stem; root motion is unambiguous.',
    },
  ],
  globalPatterns: {
    bassRole: 'Foundational root motion.',
    melodicRole: 'Supports the lead from below.',
    pumpingOrModulation: 'Steady; no sidechain duck visible.',
    synthesisCharacter: 'Plucky, short-decay analog tone.',
    vocalPresence: 'No vocal bleed.',
    bassCharacter: 'Tight and present.',
  },
  uncertaintyFlags: [],
  ...overrides,
});

describe('StemListeningNotesPanel', () => {
  it('renders nothing when stemSummary is null', () => {
    const html = renderToStaticMarkup(
      React.createElement(StemListeningNotesPanel, { stemSummary: null }),
    );
    expect(html).toBe('');
  });

  it('renders nothing when stemSummary is undefined', () => {
    const html = renderToStaticMarkup(
      React.createElement(StemListeningNotesPanel, { stemSummary: undefined }),
    );
    expect(html).toBe('');
  });

  it('renders nothing for a fully empty envelope', () => {
    const empty: StemSummaryResult = { summary: '', stems: [], uncertaintyFlags: [] };
    const html = renderToStaticMarkup(
      React.createElement(StemListeningNotesPanel, { stemSummary: empty }),
    );
    expect(html).toBe('');
  });

  it('renders the panel when only the top-line summary string is set', () => {
    const summaryOnly: StemSummaryResult = {
      summary: 'Bass anchors the harmony; lead arpeggio outlines the chord changes.',
      stems: [],
      uncertaintyFlags: [],
    };
    const html = renderToStaticMarkup(
      React.createElement(StemListeningNotesPanel, { stemSummary: summaryOnly }),
    );
    expect(html).toContain('data-testid="stem-listening-notes-panel"');
    // formatDisplayText('Stem listening notes', 'title') renders title case.
    expect(html).toContain('Stem Listening Notes');
    expect(html).toContain('Bass anchors the harmony');
    // No per-stem cards
    expect(html).not.toContain('Global pattern');
  });

  it('renders the panel when only uncertaintyFlags are present', () => {
    const flagsOnly: StemSummaryResult = {
      summary: '',
      stems: [],
      uncertaintyFlags: ['Pitch detection low confidence', 'Dense polyphony in bars 5-8'],
    };
    const html = renderToStaticMarkup(
      React.createElement(StemListeningNotesPanel, { stemSummary: flagsOnly }),
    );
    expect(html).toContain('data-testid="stem-listening-notes-panel"');
    expect(html).toContain('Pitch detection low confidence');
    expect(html).toContain('Dense polyphony in bars 5-8');
  });

  it('renders all per-stem cards when stems are populated', () => {
    const fullEnvelope: StemSummaryResult = {
      summary: 'Track-level summary text.',
      uncertaintyFlags: ['Some global uncertainty'],
      stems: [
        stemCard(),
        stemCard({
          stem: 'other',
          label: 'Other (lead)',
          summary: 'Pad and arpeggio interlocked.',
        }),
      ],
    };
    const html = renderToStaticMarkup(
      React.createElement(StemListeningNotesPanel, { stemSummary: fullEnvelope }),
    );
    expect(html).toContain('Bass stem');
    expect(html).toContain('Other (lead)');
    expect(html).toContain('Bars 1-4');
    expect(html).toContain('Notes: A2, E3');
    expect(html).toContain('Scale degrees: 1, 5');
    expect(html).toContain('Foundational root motion');
    expect(html).toContain('Some global uncertainty');
  });

  it('does not carry the section-stem-summary anchor ID (that lives on the wrapper div)', () => {
    const fullEnvelope: StemSummaryResult = {
      summary: 'x',
      uncertaintyFlags: [],
      stems: [stemCard()],
    };
    const html = renderToStaticMarkup(
      React.createElement(StemListeningNotesPanel, { stemSummary: fullEnvelope }),
    );
    expect(html).not.toContain('id="section-stem-summary"');
  });
});

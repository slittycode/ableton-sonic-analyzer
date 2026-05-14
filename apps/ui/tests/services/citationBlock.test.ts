/**
 * Locks in the CitationBlock primitive (audit Finding #2 + #3): the
 * "GROUNDED IN" structured-evidence block that renders above every
 * Mix Chain / Patches / Sonic Element card body. Verifies path → label
 * translation, value formatting, worst-confidence pill behavior, defensive
 * empty-state suppression, and max-rows cap.
 */
import { describe, expect, it } from 'vitest';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { CitationBlock } from '../../src/components/CitationBlock';
import type { Phase1Result } from '../../src/types';

const phase1 = {
  bpm: 156.6,
  bpmConfidence: 0.86,
  key: 'F minor',
  keyConfidence: 0.62,
  timeSignature: '4/4',
  lufsIntegrated: -9.3,
  truePeak: -0.2,
  crestFactor: 11.6,
  stereoWidth: 0.42,
  stereoCorrelation: 0.84,
  spectralBalance: {
    subBass: -0.7,
    lowBass: 1.2,
    highs: 1.05,
  },
  kickDetail: {
    fundamentalHz: 64.3,
    crestFactor: 8.2,
    thd: 0.29,
  },
  sidechainDetail: {
    pumpingRate: 4,
    pumpingStrength: 0.71,
    pumpingConfidence: 0.18, // deliberately low so we exercise the "unreliable" band
  },
} as unknown as Phase1Result;

describe('CitationBlock', () => {
  it('renders a row per cited field with humanized labels + formatted values', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationBlock, {
        phase1,
        fields: ['bpm', 'kickDetail.crestFactor', 'spectralBalance.highs'],
        showConfidenceBadge: false,
      }),
    );

    expect(html).toContain('Grounded in');
    expect(html).toContain('Tempo');
    expect(html).toContain('157 BPM');
    expect(html).toContain('Kick crest factor');
    expect(html).toContain('8.2 dB');
    expect(html).toContain('Highs balance');
    expect(html).toContain('+1.1 dB');
  });

  it('suppresses rows whose values do not resolve in Phase 1', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationBlock, {
        phase1,
        fields: ['bpm', 'missing.field', 'nonexistent'],
        showConfidenceBadge: false,
      }),
    );

    expect(html).toContain('Tempo');
    expect(html).toContain('157 BPM');
    // Defensive: unknown / missing paths are filtered, not rendered as empty
    // rows or as the humanized label with a blank value.
    expect(html).not.toContain('Nonexistent');
    expect(html).not.toContain('Missing · field');
  });

  it('caps visible rows at maxRows (default 4)', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationBlock, {
        phase1,
        fields: [
          'bpm',
          'kickDetail.crestFactor',
          'spectralBalance.highs',
          'spectralBalance.subBass',
          'truePeak',
          'crestFactor', // 6th — must be dropped
        ],
        showConfidenceBadge: false,
      }),
    );

    expect(html).toContain('Tempo');
    expect(html).toContain('Kick crest factor');
    expect(html).toContain('Highs balance');
    expect(html).toContain('Sub-bass balance');
    // 5th and 6th fields ('truePeak' / 'crestFactor') must NOT render at the
    // default cap. Crest factor at the kickDetail.* path renders (row 2).
    // The bare-top-level 'crestFactor' label "Crest factor" appears only if
    // the cap was bypassed.
    expect(html).not.toContain('True peak');
    // Note: "Kick crest factor" matches "Crest factor" as a substring, so we
    // can't simply assert against the standalone label without false positives.
    // The maxRows-respect is also covered by the row count math: bpm, kick
    // crest, highs, sub-bass = 4 rows.
    const rowCount = (html.match(/data-testid="citation-row-/g) ?? []).length;
    expect(rowCount).toBe(4);
  });

  it('returns null when no fields resolve to values', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationBlock, {
        phase1,
        fields: ['missing.one', 'missing.two'],
      }),
    );
    // renderToStaticMarkup on a null component returns empty string.
    expect(html).toBe('');
  });

  it('returns null when fields list is empty', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationBlock, {
        phase1,
        fields: [],
      }),
    );
    expect(html).toBe('');
  });

  it('renders the worst-confidence pill when any cited field has a sibling', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationBlock, {
        phase1,
        fields: ['bpm', 'key', 'sidechainDetail.pumpingRate'],
      }),
    );

    expect(html).toContain('citation-confidence-pill');
    // pumpingConfidence 0.18 is the worst (< 0.25 threshold) → "Unreliable" band.
    expect(html).toContain('Unreliable');
  });

  it('omits the confidence pill when no cited field has a paired sibling', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationBlock, {
        phase1,
        fields: ['truePeak', 'spectralBalance.subBass'],
      }),
    );

    expect(html).toContain('Grounded in');
    expect(html).not.toContain('citation-confidence-pill');
  });

  it('suppresses the confidence pill when showConfidenceBadge=false', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationBlock, {
        phase1,
        fields: ['bpm'],
        showConfidenceBadge: false,
      }),
    );

    expect(html).toContain('Tempo');
    expect(html).not.toContain('citation-confidence-pill');
  });

  it('respects explicit `confidence={null}` override even when a pair exists', () => {
    // Caller may have higher-fidelity confidence info elsewhere and want to
    // suppress this auto-derivation.
    const html = renderToStaticMarkup(
      React.createElement(CitationBlock, {
        phase1,
        fields: ['bpm', 'key'],
        confidence: null,
      }),
    );

    expect(html).toContain('Tempo');
    expect(html).not.toContain('citation-confidence-pill');
  });

  it('uses explicit confidence number when provided', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationBlock, {
        phase1,
        fields: ['bpm'],
        confidence: 0.95, // overrides bpmConfidence (0.86)
      }),
    );

    expect(html).toContain('Solid scaffold');
  });

  it('appends extraRows after the resolved phase1Fields rows', () => {
    // Track Layout passes its segmentIndexes through extraRows so the
    // arrangement-segment citation lands inside the same block as the
    // measurement citations.
    const html = renderToStaticMarkup(
      React.createElement(CitationBlock, {
        phase1,
        fields: ['bpm', 'key'],
        showConfidenceBadge: false,
        extraRows: [{ label: 'Active in segments', value: '1 · 3 · 5' }],
      }),
    );

    expect(html).toContain('Tempo');
    expect(html).toContain('Key');
    expect(html).toContain('Active in segments');
    expect(html).toContain('1 · 3 · 5');
  });

  it('renders extraRows alone when phase1Fields is empty', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationBlock, {
        phase1,
        fields: [],
        extraRows: [{ label: 'Active in segments', value: '2 · 4' }],
      }),
    );

    // Block still renders because extraRows contributed content.
    expect(html).toContain('Grounded in');
    expect(html).toContain('Active in segments');
    expect(html).toContain('2 · 4');
  });
});

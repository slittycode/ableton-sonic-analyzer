/**
 * Locks in the CitationHeadline primitive (audit Finding #3): the one-line
 * "{label} {value} →" companion that mounts inside every collapsed Mix Chain
 * / Patches / Sonic Element card header so the chain-of-custody evidence is
 * visible without expanding the card. CitationBlock (the multi-row evidence
 * block) keeps rendering in the expanded body — this primitive is the
 * collapsed-state companion, not a replacement.
 *
 * Mirrors the structure of `citationBlock.test.ts` so the two primitives are
 * easy to keep in sync.
 */
import { describe, expect, it } from 'vitest';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { CitationHeadline } from '../../src/components/CitationBlock';
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
    pumpingConfidence: 0.18, // < 0.25 → Unreliable band
  },
} as unknown as Phase1Result;

describe('CitationHeadline', () => {
  it('renders label + formatted value + arrow for a resolvable field', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationHeadline, {
        phase1,
        field: 'kickDetail.crestFactor',
        showConfidenceBadge: false,
      }),
    );

    expect(html).toContain('citation-headline');
    expect(html).toContain('Kick crest factor');
    expect(html).toContain('8.2 dB');
    // Arrow points into the device h4 that follows in the card title row.
    expect(html).toContain('→');
  });

  it('returns null when the cited field does not resolve in Phase 1', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationHeadline, {
        phase1,
        field: 'missing.field.path',
        showConfidenceBadge: false,
      }),
    );

    expect(html).toBe('');
  });

  it('returns null when the cited field is an empty string', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationHeadline, {
        phase1,
        field: '',
        showConfidenceBadge: false,
      }),
    );

    expect(html).toBe('');
  });

  it('renders the confidence pill when the cited field has a paired sibling', () => {
    // bpm has a paired sibling `bpmConfidence` (0.86 → Solid band).
    const html = renderToStaticMarkup(
      React.createElement(CitationHeadline, {
        phase1,
        field: 'bpm',
      }),
    );

    expect(html).toContain('citation-headline-pill');
    expect(html).toContain('Solid scaffold');
  });

  it('omits the confidence pill when no paired sibling exists', () => {
    // truePeak has no `truePeakConfidence` sibling in CONFIDENCE_PAIRS.
    const html = renderToStaticMarkup(
      React.createElement(CitationHeadline, {
        phase1,
        field: 'truePeak',
      }),
    );

    expect(html).toContain('citation-headline');
    expect(html).not.toContain('citation-headline-pill');
  });

  it('suppresses the confidence pill when showConfidenceBadge=false', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationHeadline, {
        phase1,
        field: 'bpm',
        showConfidenceBadge: false,
      }),
    );

    expect(html).toContain('Tempo');
    expect(html).not.toContain('citation-headline-pill');
  });

  it('uses the unreliable band for confidence < 0.25 with hedging copy in the title attribute', () => {
    // sidechainDetail.pumpingRate ↔ pumpingConfidence 0.18 → Unreliable.
    const html = renderToStaticMarkup(
      React.createElement(CitationHeadline, {
        phase1,
        field: 'sidechainDetail.pumpingRate',
      }),
    );

    expect(html).toContain('citation-headline-pill');
    expect(html).toContain('Unreliable');
    // The hedging copy in the band's `.copy` field lands in the title attribute
    // — verify the pill carries it so producers see "this is shaky" on hover.
    expect(html).toMatch(/title="[^"]+"/);
  });

  it('formats the value using the same formatter as CitationBlock (spectralBalance signed dB)', () => {
    // spectralBalance.highs = 1.05 → CitationBlock renders "+1.1 dB" (signed,
    // 1 decimal). Headline must use the same formatCitedValue path.
    const html = renderToStaticMarkup(
      React.createElement(CitationHeadline, {
        phase1,
        field: 'spectralBalance.highs',
        showConfidenceBadge: false,
      }),
    );

    expect(html).toContain('Highs balance');
    expect(html).toContain('+1.1 dB');
  });

  it('humanizes the label using the FIELD_LABELS map (kickDetail.crestFactor → "Kick crest factor")', () => {
    const html = renderToStaticMarkup(
      React.createElement(CitationHeadline, {
        phase1,
        field: 'kickDetail.crestFactor',
        showConfidenceBadge: false,
      }),
    );

    expect(html).toContain('Kick crest factor');
    // Not the raw dotted path.
    expect(html).not.toContain('kickDetail.crestFactor');
  });

  it('renders compact-header class hooks (text-[9px] eyebrow, text-xs tabular-nums value)', () => {
    // Lightweight assertion on typography classes — the headline must read as
    // "small uppercase label + larger weighted value" to signal authority
    // alongside the device h4 in the card title row.
    const html = renderToStaticMarkup(
      React.createElement(CitationHeadline, {
        phase1,
        field: 'bpm',
        showConfidenceBadge: false,
      }),
    );

    expect(html).toContain('text-[9px]');
    expect(html).toContain('text-xs');
    expect(html).toContain('tabular-nums');
    expect(html).toContain('font-semibold');
  });
});

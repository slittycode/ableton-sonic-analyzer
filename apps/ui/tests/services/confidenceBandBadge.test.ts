// Verifies the four confidence bands render with distinct color tokens so
// the producer can tell Solid from Workable, and Rough from Unreliable, at
// a glance. The pure helper tests in `confidenceBand.test.ts` cover label
// and copy; this file pins the visual tone mapping in
// `ConfidenceBandBadge.tsx` and the override path used by
// full-mix-fallback / legacy render states.

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ConfidenceBandBadge } from '../../src/components/sessionMusician/ConfidenceBandBadge';
import {
  getConfidenceBand,
  toConfidenceBand,
} from '../../src/services/sessionMusician/confidenceBand';

// Confidence values that fall squarely inside each band per the thresholds
// in services/sessionMusician/confidenceBand.ts (≥0.80 solid, ≥0.50 workable,
// ≥0.25 rough, <0.25 unreliable).
const BAND_CONFIDENCE = {
  solid: 0.9,
  workable: 0.6,
  rough: 0.3,
  unreliable: 0.1,
} as const;

// Extracts the three color tokens (border, text, bg) from a rendered pill so
// tests can compare bands without pinning the exact opacity suffix. Returns
// e.g. `{ border: 'border-success/30', text: 'text-success', bg: 'bg-success/10' }`.
function extractColorTokens(html: string): { border: string; text: string; bg: string } {
  const border = html.match(/border-(success|accent|warning|error)\/\d+/)?.[0];
  const text = html.match(/text-(success|accent|warning|error)(?!-)\b/)?.[0];
  const bg = html.match(/bg-(success|accent|warning|error)\/\d+/)?.[0];
  if (!border || !text || !bg) {
    throw new Error(`Could not extract all three color tokens from markup: ${html}`);
  }
  return { border, text, bg };
}

function render(confidence: number, overrides: Partial<React.ComponentProps<typeof ConfidenceBandBadge>> = {}) {
  return renderToStaticMarkup(
    React.createElement(ConfidenceBandBadge, { confidence, ...overrides }),
  );
}

describe('ConfidenceBandBadge — per-band color tones', () => {
  it('renders the Solid scaffold band with success/green tokens', () => {
    const tokens = extractColorTokens(render(BAND_CONFIDENCE.solid));
    expect(tokens.border).toMatch(/^border-success\//);
    expect(tokens.text).toBe('text-success');
    expect(tokens.bg).toMatch(/^bg-success\//);
  });

  it('renders the Workable draft band with accent/orange tokens', () => {
    const tokens = extractColorTokens(render(BAND_CONFIDENCE.workable));
    expect(tokens.border).toMatch(/^border-accent\//);
    expect(tokens.text).toBe('text-accent');
    expect(tokens.bg).toMatch(/^bg-accent\//);
  });

  it('renders the Rough sketch band with warning/amber tokens', () => {
    const tokens = extractColorTokens(render(BAND_CONFIDENCE.rough));
    expect(tokens.border).toMatch(/^border-warning\//);
    expect(tokens.text).toBe('text-warning');
    expect(tokens.bg).toMatch(/^bg-warning\//);
  });

  it('renders the Unreliable band with error/red tokens', () => {
    const tokens = extractColorTokens(render(BAND_CONFIDENCE.unreliable));
    expect(tokens.border).toMatch(/^border-error\//);
    expect(tokens.text).toBe('text-error');
    expect(tokens.bg).toMatch(/^bg-error\//);
  });
});

describe('ConfidenceBandBadge — bands are pairwise distinct', () => {
  // The whole point of this redesign: producers must be able to tell the
  // four bands apart visually. Extract each band's text-color token and
  // assert no two bands share it. This survives future opacity tweaks.
  it('no two bands share the same text-color token', () => {
    const textTokens = (Object.keys(BAND_CONFIDENCE) as Array<keyof typeof BAND_CONFIDENCE>).map(
      (band) => extractColorTokens(render(BAND_CONFIDENCE[band])).text,
    );
    const unique = new Set(textTokens);
    expect(unique.size).toBe(4);
  });

  it('Solid and Unreliable use opposite ends of the severity ladder', () => {
    const solid = extractColorTokens(render(BAND_CONFIDENCE.solid));
    const unreliable = extractColorTokens(render(BAND_CONFIDENCE.unreliable));
    expect(solid.text).toBe('text-success');
    expect(unreliable.text).toBe('text-error');
  });

  it('Workable and Rough sit between Solid and Unreliable', () => {
    const workable = extractColorTokens(render(BAND_CONFIDENCE.workable));
    const rough = extractColorTokens(render(BAND_CONFIDENCE.rough));
    expect(workable.text).toBe('text-accent');
    expect(rough.text).toBe('text-warning');
  });
});

describe('ConfidenceBandBadge — override path used by full-mix-fallback / legacy', () => {
  // NoteDraftBlock passes `overrideTone="rough"` (with an overrideLabel like
  // "Full-mix fallback" or "Legacy run") so the band visually reads as
  // "amber caution" regardless of the underlying averageConfidence number.
  it('overrideTone="rough" produces warning/amber tokens even when confidence is solid-range', () => {
    const html = render(0.95, {
      overrideTone: 'rough',
      overrideLabel: 'Full-mix fallback',
      overrideCopy: 'Pitch tracked across the whole mix; treat as approximate.',
    });
    const tokens = extractColorTokens(html);
    expect(tokens.border).toMatch(/^border-warning\//);
    expect(tokens.text).toBe('text-warning');
    expect(tokens.bg).toMatch(/^bg-warning\//);
    // And the pill text is the override, not "Solid scaffold · 95%".
    expect(html).toContain('Full-mix fallback');
    expect(html).not.toContain('Solid scaffold');
  });

  it('overrideTone="rough" with low-confidence input still uses warning tokens (not red)', () => {
    const html = render(0.05, {
      overrideTone: 'rough',
      overrideLabel: 'Legacy run',
      overrideCopy: 'Re-analyze for current stem-aware quality.',
    });
    const tokens = extractColorTokens(html);
    expect(tokens.text).toBe('text-warning');
    expect(html).toContain('Legacy run');
    expect(html).not.toContain('Unreliable');
  });

  it('overrideCopy replaces the band copy without touching the pill class', () => {
    const html = render(BAND_CONFIDENCE.solid, {
      overrideCopy: 'Custom guidance for the producer.',
    });
    expect(html).toContain('Custom guidance for the producer.');
    // Default band copy must NOT appear when overrideCopy is set.
    expect(html).not.toContain("Notes look reliable. Expect light cleanup in Ableton's piano roll.");
  });
});

// Audit Finding #4: compact variant omits the copy paragraph so the badge
// can sit inline in card corners and metric-card footers without breaking
// the surrounding layout. The pill itself stays identical to the full
// variant — same tone, same label, same percent.
describe('ConfidenceBandBadge — compact variant', () => {
  it('compact variant omits the copy paragraph', () => {
    const html = render(BAND_CONFIDENCE.solid, { variant: 'compact' });
    expect(html).toContain('Solid scaffold');
    expect(html).toContain('90%');
    // The full variant's hedging copy must NOT render in compact mode.
    expect(html).not.toContain("Notes look reliable. Expect light cleanup in Ableton's piano roll.");
    // The full variant wraps in `<div class="space-y-2">`; compact wraps in
    // an inline-flex span so it composes cleanly inline.
    expect(html).not.toMatch(/<div[^>]*space-y-2/);
  });

  it('compact variant with explicit band prop and no confidence renders label-only (no percent)', () => {
    const band = getConfidenceBand(0.9); // solid
    const html = renderToStaticMarkup(
      React.createElement(ConfidenceBandBadge, { band, variant: 'compact' }),
    );
    expect(html).toContain('Solid scaffold');
    // No percent rendered because no confidence was passed.
    expect(html).not.toContain('%');
  });

  it('band override prop wins over confidence-derived band for tone', () => {
    // confidence=0.95 alone would yield solid (success tone). Override the
    // band to the unreliable (error tone) variant via the `band` prop.
    const unreliableBand = getConfidenceBand(0.1);
    const html = renderToStaticMarkup(
      React.createElement(ConfidenceBandBadge, {
        confidence: 0.95,
        band: unreliableBand,
        variant: 'compact',
      }),
    );
    const tokens = extractColorTokens(html);
    expect(tokens.text).toBe('text-error');
    // Label uses the override band; percent still comes from the
    // confidence prop ("Unreliable · 95%") — exotic combination but the
    // primitive needs to handle it without crashing.
    expect(html).toContain('Unreliable');
    expect(html).toContain('95%');
  });

  it('routes Gemini HIGH/MED/LOW strings through toConfidenceBand into the badge', () => {
    // The real-world wiring at the Detected Characteristics site: caller
    // converts the string enum, passes the resulting band.
    const band = toConfidenceBand('MED');
    expect(band).not.toBeNull();
    const html = renderToStaticMarkup(
      React.createElement(ConfidenceBandBadge, {
        band: band ?? undefined,
        variant: 'compact',
      }),
    );
    expect(html).toContain('Workable draft');
    const tokens = extractColorTokens(html);
    expect(tokens.text).toBe('text-accent');
  });
});

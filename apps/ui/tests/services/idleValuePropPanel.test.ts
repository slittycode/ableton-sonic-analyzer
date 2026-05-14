/**
 * Locks in the idle-state value-prop copy (audit Finding #5) so a stray
 * refactor doesn't quietly revert the panel to the old "NO SIGNAL DETECTED"
 * read. Also asserts the asset-slot marker is present and discoverable for
 * a future GIF/SVG swap.
 */
import { describe, expect, it } from 'vitest';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { IdleValuePropPanel } from '../../src/components/IdleValuePropPanel';

describe('IdleValuePropPanel', () => {
  const html = renderToStaticMarkup(React.createElement(IdleValuePropPanel));

  it('renders the producer-facing eyebrow and headline', () => {
    expect(html).toContain('Upload a track. Get specific Ableton.');
    expect(html).toContain('measurement-cited rebuild plan');
  });

  it('explains the chain-of-custody value prop in body copy', () => {
    // The product's wedge — citations on every recommendation — needs to be
    // visible in the idle state, not hidden until the user reads a card.
    expect(html).toContain('cites the Phase 1 measurement');
  });

  it('sets honest expectations about wait time', () => {
    // Audit revision discovery: real Phase 2 wait is ~5 minutes on a
    // non-silent track. Don't promise "fast"; promise honest.
    expect(html).toContain('~30 seconds');
    expect(html).toContain('4–5 minutes');
  });

  it('points to the left-side dropzone instead of duplicating the CTA', () => {
    // The action surface is the dropzone in the Input Source panel on the
    // left. The value-prop panel is informational; it shouldn't shadow the
    // existing affordance.
    expect(html).toContain('Drop audio in the panel on the left');
    expect(html).toContain('Load Demo Track');
  });

  it('marks the asset-slot so a real loop can be swapped in later', () => {
    // grep marker — a future GIF/SVG drops in by replacing the
    // VisualPlaceholder component matched by this attribute.
    expect(html).toContain('data-asset-slot="idle-flow-loop"');
  });

  it('uses the testid so App.tsx wiring can be asserted from end-to-end tests', () => {
    expect(html).toContain('data-testid="idle-value-prop"');
  });
});

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { KeyCheckPanel } from '../../src/components/keyCheck/KeyCheckPanel';
import type { Phase1Result } from '../../src/types';
import { phase1EnvelopeFixture } from '../fixtures/phase1FullPayload';

const phase1 = phase1EnvelopeFixture as unknown as Phase1Result;

describe('KeyCheckPanel', () => {
  // This render also guards the client-only boundary: if the audio engine
  // module leaked into the panel's static imports, createEngine would throw
  // EngineEnvironmentError here (Node has no AudioContext).
  it('renders the measured key readout without loading the audio engine', () => {
    const html = renderToStaticMarkup(React.createElement(KeyCheckPanel, { phase1 }));

    expect(html).toContain('Key Check');
    expect(html).toContain('A minor');
    expect(html).toContain('LOCAL');
    expect(html).toContain('of 3 agree');
    expect(html).toContain('C major');
    expect(html).toContain('440.1');
    expect(html).toContain('Open keyboard');
    expect(html).toContain('A minor and C major share every note');
    expect(html).not.toContain('key-check-instrument');
  });

  it('does not leak raw Phase 1 field paths into the copy', () => {
    const html = renderToStaticMarkup(React.createElement(KeyCheckPanel, { phase1 }));
    expect(html).not.toMatch(/keyConfidence|tuningFrequency|keyEnsemble|fundamentalsQuality/);
  });

  it('explains a missing key and missing tuning in plain language', () => {
    const html = renderToStaticMarkup(
      React.createElement(KeyCheckPanel, {
        phase1: { ...phase1, key: null, keyEnsemble: null, tuningFrequency: null, tuningCents: null },
      }),
    );
    expect(html).toContain('Not measured');
    expect(html).toContain('did not report a usable key');
    expect(html).toContain('Tuning is measured in full analysis mode');
  });
});

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { BeatCheckPanel } from '../../src/components/beatCheck/BeatCheckPanel';
import type { Phase1Result } from '../../src/types';
import { phase1EnvelopeFixture } from '../fixtures/phase1FullPayload';

const phase1 = phase1EnvelopeFixture as unknown as Phase1Result;

// Node has no File global before v20; a structural stand-in is enough for render.
const file = { name: 'track.wav', size: 1, lastModified: 0 } as unknown as File;

describe('BeatCheckPanel', () => {
  // Also the client-only guard: if the audio engine leaked into the panel's
  // static imports, createEngine would throw here (Node has no AudioContext).
  it('renders the rhythm readout and an open button without loading the audio engine', () => {
    const html = renderToStaticMarkup(React.createElement(BeatCheckPanel, { phase1, audioFile: file }));
    expect(html).toContain('Beat Check');
    expect(html).toContain('128');
    expect(html).toMatch(/>4<span[^>]*> beats<\/span>/);
    expect(html).toContain('LOCAL');
    expect(html).toContain('CHECK');
    expect(html).toContain('ASSUMED');
    expect(html).toContain('where the kick hits hardest');
    expect(html).toContain('Open Beat Check');
    expect(html).not.toContain('beat-check-player');
  });

  it('asks for the file when this session has no audio', () => {
    const html = renderToStaticMarkup(React.createElement(BeatCheckPanel, { phase1, audioFile: null }));
    expect(html).toContain('Load the track again to use it');
    expect(html).not.toContain('Open Beat Check');
  });

  it('explains a missing beat grid', () => {
    const html = renderToStaticMarkup(
      React.createElement(BeatCheckPanel, { phase1: { ...phase1, rhythmDetail: null }, audioFile: file }),
    );
    expect(html).toContain('did not report a beat grid');
  });

  it('does not leak raw Phase 1 field paths into the copy', () => {
    const html = renderToStaticMarkup(React.createElement(BeatCheckPanel, { phase1, audioFile: file }));
    expect(html).not.toMatch(/beatGrid|downbeatConfidence|rhythmDetail|beatPositions|phraseGrid/);
  });
});

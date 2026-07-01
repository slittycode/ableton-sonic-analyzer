import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { HarmonyLanes } from '../../src/components/HarmonyLanes';
import { MeasurementSummarySection } from '../../src/components/analysisResults/MeasurementSummarySection';
import type { Phase1Result } from '../../src/types';
import { phase1EnvelopeFixture } from '../fixtures/phase1FullPayload';

const phase1 = phase1EnvelopeFixture as unknown as Phase1Result;

describe('fundamentals quality UI', () => {
  it('renders local fundamentals trust labels in the measurement summary', () => {
    const html = renderToStaticMarkup(
      React.createElement(MeasurementSummarySection, {
        phase1,
        finalBpm: 128,
        finalKey: 'A minor',
        keyIsApproximate: false,
        characteristicPills: [],
      }),
    );

    expect(html).toContain('Local fundamentals');
    expect(html).toContain('Tempo LOCAL');
    expect(html).toContain('Meter CHECK');
    expect(html).toContain('Chords CHECK');
  });

  it('surfaces ambiguous chord authority in the harmony lanes', () => {
    const html = renderToStaticMarkup(
      React.createElement(HarmonyLanes, { phase1 }),
    );

    expect(html).toContain('Quality');
    expect(html).toContain('Check');
    expect(html).toContain('Chord labels are local estimates.');
  });
});

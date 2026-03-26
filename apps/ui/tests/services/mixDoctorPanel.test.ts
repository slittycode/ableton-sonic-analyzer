import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MixDoctorPanel } from '../../src/components/MixDoctorPanel';
import { generateMixDoctorReport } from '../../src/services/mixDoctor';
import type { Phase1Result } from '../../src/types';

const basePhase1: Phase1Result = {
  bpm: 128,
  bpmConfidence: 0.95,
  key: 'A minor',
  keyConfidence: 0.89,
  timeSignature: '4/4',
  durationSeconds: 184.2,
  lufsIntegrated: -8.4,
  truePeak: -0.5,
  plr: 7.9,
  crestFactor: 8.2,
  stereoWidth: 0.74,
  stereoCorrelation: 0.82,
  monoCompatible: true,
  spectralBalance: {
    subBass: -12.0,
    lowBass: -14.0,
    lowMids: -21.0,
    mids: -16.0,
    upperMids: -18.0,
    highs: -20.0,
    brilliance: -24.0,
  },
  genreDetail: {
    genre: 'tech house',
    confidence: 0.82,
    secondaryGenre: 'techno',
    genreFamily: 'house',
    topScores: [
      { genre: 'tech house', score: 0.82 },
      { genre: 'techno', score: 0.69 },
    ],
  },
};

describe('MixDoctorPanel', () => {
  it('renders the existing MixDoctor report fields', () => {
    const report = generateMixDoctorReport(basePhase1);
    const html = renderToStaticMarkup(React.createElement(MixDoctorPanel, { report }));

    expect(html).toContain('Target Genre');
    expect(html).toContain('Health Score');
    expect(html).toContain('Loudness Offset');
    expect(html).toContain(report.genreName);
    expect(html).toContain('Advisory Summary');
    expect(html).toContain('Band Diagnostics');
    expect(html).toContain('Low Mids');
  });
});

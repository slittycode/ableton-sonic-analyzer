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
    expect(html).toContain('LOW MIDS');
  });

  it('renders score, issue, and delta values as styled badges instead of plain text rows', () => {
    const html = renderToStaticMarkup(
      React.createElement(MixDoctorPanel, {
        report: {
          genreId: 'tech-house',
          genreName: 'Tech House',
          targetProfile: {
            id: 'tech-house',
            name: 'Tech House',
            family: 'house',
            aliases: [],
            spectralTargets: {
              'Sub Bass': { minDb: -12, maxDb: -8, optimalDb: -10 },
              'Low Bass': { minDb: -15, maxDb: -11, optimalDb: -13 },
              'Low Mids': { minDb: -21, maxDb: -17, optimalDb: -19 },
              Mids: { minDb: -18, maxDb: -14, optimalDb: -16 },
              'Upper Mids': { minDb: -20, maxDb: -16, optimalDb: -18 },
              Highs: { minDb: -21, maxDb: -17, optimalDb: -19 },
              Brilliance: { minDb: -24, maxDb: -20, optimalDb: -22 },
            },
            targetLufsRange: [-9, -7],
            targetPlrRange: [7, 10],
            targetCrestFactorRange: [7, 10],
          },
          advice: [
            {
              band: 'Sub Bass',
              issue: 'optimal',
              message: 'Balanced.',
              diffDb: 0.1,
              measuredDb: -10,
              normalizedDb: -10,
              targetMinDb: -12,
              targetMaxDb: -8,
              targetOptimalDb: -10,
            },
            {
              band: 'Low Mids',
              issue: 'too-quiet',
              message: 'Needs more body.',
              diffDb: -2.3,
              measuredDb: -21.3,
              normalizedDb: -21.3,
              targetMinDb: -19,
              targetMaxDb: -17,
              targetOptimalDb: -18,
            },
          ],
          loudnessOffset: -1.8,
          dynamicsAdvice: {
            issue: 'too-compressed',
            message: 'Dynamics need more punch.',
            actualCrest: 6.2,
            actualPlr: 5.8,
          },
          loudnessAdvice: {
            issue: 'too-loud',
            message: 'Streaming services will turn this down.',
            actualLufs: -6.4,
            truePeak: -0.2,
          },
          stereoAdvice: {
            correlation: 0.11,
            width: 0.78,
            monoCompatible: true,
            message: 'Stereo image is wide and needs checking in mono.',
          },
          overallScore: 86,
        },
      }),
    );

    expect(html).toContain('86/100');
    expect(html).toContain('border-success/30 bg-success/10');
    expect(html).toContain('border-warning/30 bg-warning/10');
    expect(html).toContain('border-error/30 bg-error/10');
    expect(html).toContain('-1.8');
  });

  it('uses the shared mono text roles inside band diagnostics instead of display-font table rows', () => {
    const report = generateMixDoctorReport(basePhase1);
    const html = renderToStaticMarkup(React.createElement(MixDoctorPanel, { report }));

    expect(html).toContain('data-text-role="eyebrow"');
    expect(html).toContain('>SUB BASS<');
    expect(html).toContain('>LOW BASS<');
    expect(html).toContain('data-text-role="value"');
    expect(html).not.toContain('font-display font-medium');
  });
});

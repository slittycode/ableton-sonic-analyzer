import { describe, expect, it } from 'vitest';
import { generateMixDoctorReport, resolveMixDoctorGenreId } from '../../src/services/mixDoctor';
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

describe('mixDoctor service', () => {
  it('maps phase1 genre to enhanced profile id', () => {
    expect(resolveMixDoctorGenreId(basePhase1)).toBe('tech-house');
    const report = generateMixDoctorReport(basePhase1);
    expect(report.genreId).toBe('tech-house');
    expect(report.genreName.toLowerCase()).toContain('tech house');
  });

  it('falls back to edm profile when genre cannot be resolved', () => {
    const report = generateMixDoctorReport({
      ...basePhase1,
      genreDetail: null,
    });
    expect(report.genreId).toBe('edm');
  });

  it('produces seven band diagnostics including low mids', () => {
    const report = generateMixDoctorReport(basePhase1);
    expect(report.advice).toHaveLength(7);
    expect(report.advice.some((entry) => entry.band === 'Low Mids')).toBe(true);
    expect(report.overallScore).toBeGreaterThanOrEqual(0);
    expect(report.overallScore).toBeLessThanOrEqual(100);
  });

  it('flags dynamics as too compressed when plr is below target', () => {
    const report = generateMixDoctorReport({
      ...basePhase1,
      plr: 3.5,
      crestFactor: 5.0,
    });
    expect(report.dynamicsAdvice.issue).toBe('too-compressed');
    expect(report.dynamicsAdvice.message.toLowerCase()).toContain('plr');
  });

  it('flags stereo advisory when mono compatibility fails', () => {
    const report = generateMixDoctorReport({
      ...basePhase1,
      monoCompatible: false,
      stereoCorrelation: 0.05,
    });
    expect(report.stereoAdvice.monoCompatible).toBe(false);
    expect(report.stereoAdvice.message.toLowerCase()).toContain('mono');
  });
});

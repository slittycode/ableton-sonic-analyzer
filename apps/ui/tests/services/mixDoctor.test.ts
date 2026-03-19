import { generateMixReport } from '../../src/services/mixDoctor';
import type { Phase1Result, GenreProfile } from '../../src/types';

const basePhase1: Phase1Result = {
  bpm: 128,
  bpmConfidence: 0.9,
  key: 'A minor',
  keyConfidence: 0.8,
  timeSignature: '4/4',
  durationSeconds: 300,
  lufsIntegrated: -8.0,
  truePeak: -1.0,
  crestFactor: 9.0,
  stereoWidth: 0.6,
  stereoCorrelation: 0.85,
  spectralBalance: {
    subBass: -18.0,
    lowBass: -12.0,
    mids: -8.0,
    upperMids: -10.0,
    highs: -14.0,
    brilliance: -20.0,
  },
};

const testProfile: GenreProfile = {
  id: 'test-edm',
  name: 'Test EDM',
  targetCrestFactorRange: [6, 12],
  targetPlrRange: [6, 10],
  targetLufsRange: [-10, -6],
  spectralTargets: {
    subBass: { minDb: -22, maxDb: -14, optimalDb: -18 },
    lowBass: { minDb: -16, maxDb: -8, optimalDb: -12 },
    lowMids: { minDb: -12, maxDb: -4, optimalDb: -8 },
    mids: { minDb: -12, maxDb: -4, optimalDb: -8 },
    upperMids: { minDb: -14, maxDb: -6, optimalDb: -10 },
    highs: { minDb: -18, maxDb: -10, optimalDb: -14 },
    brilliance: { minDb: -24, maxDb: -16, optimalDb: -20 },
  },
};

describe('generateMixReport', () => {
  it('deterministic scoring — same input produces same overallScore', () => {
    const r1 = generateMixReport(basePhase1, testProfile);
    const r2 = generateMixReport(basePhase1, testProfile);
    expect(r1.overallScore).toBe(r2.overallScore);
  });

  it('PLR below range penalizes — too-crushed', () => {
    // truePeak -3, lufs -8 => PLR = 5, below [6,10]
    const phase1 = { ...basePhase1, truePeak: -3.0, lufsIntegrated: -8.0 };
    const report = generateMixReport(phase1, testProfile);
    expect(report.plrAdvice).toBeDefined();
    expect(report.plrAdvice!.issue).toBe('too-crushed');
  });

  it('PLR above range penalizes — too-open', () => {
    // truePeak 0, lufs -12 => PLR = 12, above [6,10]
    const phase1 = { ...basePhase1, truePeak: 0, lufsIntegrated: -12.0 };
    const report = generateMixReport(phase1, testProfile);
    expect(report.plrAdvice).toBeDefined();
    expect(report.plrAdvice!.issue).toBe('too-open');
  });

  it('PLR in range — optimal', () => {
    // truePeak -1, lufs -8 => PLR = 7, within [6,10]
    const phase1 = { ...basePhase1, truePeak: -1.0, lufsIntegrated: -8.0 };
    const report = generateMixReport(phase1, testProfile);
    expect(report.plrAdvice).toBeDefined();
    expect(report.plrAdvice!.issue).toBe('optimal');
  });

  it('crest below range — too-compressed', () => {
    const phase1 = { ...basePhase1, crestFactor: 4.0 };
    const report = generateMixReport(phase1, testProfile);
    expect(report.dynamicsAdvice.issue).toBe('too-compressed');
  });

  it('overall score bounded 0-100', () => {
    // Extreme values
    const extremePhase1 = {
      ...basePhase1,
      crestFactor: 1.0,
      truePeak: 0,
      lufsIntegrated: -2.0,
      stereoCorrelation: 0.05,
      stereoWidth: 0.95,
      spectralBalance: {
        subBass: 10, lowBass: 10, mids: 10,
        upperMids: 10, highs: 10, brilliance: 10,
      },
    };
    const report = generateMixReport(extremePhase1, testProfile);
    expect(report.overallScore).toBeGreaterThanOrEqual(0);
    expect(report.overallScore).toBeLessThanOrEqual(100);
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Phase1Result } from '../../src/types';
import type { MixDoctorReport } from '../../src/services/mixDoctor';
import { collectNotableFindings } from '../../src/services/notableFindings';

// mixDoctor is genre-relative; mock it so these unit tests are deterministic and
// exercise the aggregation logic (mixDoctor's genre math has its own tests).
vi.mock('../../src/services/mixDoctor', () => ({ generateMixDoctorReport: vi.fn() }));
import { generateMixDoctorReport } from '../../src/services/mixDoctor';

const OPTIMAL_REPORT = {
  advice: [],
  loudnessAdvice: { issue: 'optimal', message: '' },
  dynamicsAdvice: { issue: 'optimal', message: '' },
  stereoAdvice: { monoCompatible: true, message: '' },
} as unknown as MixDoctorReport;

// Minimal valid Phase1Result (mirrors the factory in phase2Validator.test.ts).
const makePhase1 = (overrides: Partial<Phase1Result> = {}): Phase1Result => ({
  bpm: 126, bpmConfidence: 0.91, key: 'F minor', keyConfidence: 0.87,
  timeSignature: '4/4', durationSeconds: 210.6,
  lufsIntegrated: -9.0, lufsRange: 6.0, truePeak: -1.0, crestFactor: 11.0,
  stereoWidth: 0.6, stereoCorrelation: 0.6,
  spectralBalance: { subBass: 0, lowBass: 0, lowMids: 0, mids: 0, upperMids: 0, highs: 0, brilliance: 0 },
  spectralDetail: { spectralCentroidMean: 3000 },
  rhythmDetail: { kickSwing: 0.05 },
  synthesisCharacter: { inharmonicity: 0.1, oddToEvenRatio: 1.1 },
  ...overrides,
});

const dom = (status: string, plainEnglish: string) =>
  ({ status, plainEnglish, source: null, confidence: null, evidence: {} });

const fq = (domains: Record<string, unknown>) =>
  ({
    schemaVersion: 'fundamentals-quality.v1', targetProfile: 'electronic_ableton_v1',
    analysisMode: 'full', localOnly: true, llmExcluded: true, overallStatus: 'ambiguous', domains,
  } as unknown as NonNullable<Phase1Result['fundamentalsQuality']>);

beforeEach(() => {
  vi.mocked(generateMixDoctorReport).mockReset();
  vi.mocked(generateMixDoctorReport).mockReturnValue(OPTIMAL_REPORT);
});

describe('collectNotableFindings', () => {
  it('returns [] for a clean, unremarkable track', () => {
    expect(collectNotableFindings(makePhase1())).toEqual([]);
  });

  it('flags digital clipping as a critical Loudness finding', () => {
    const findings = collectNotableFindings(makePhase1({ saturationDetail: { clippedSampleCount: 42 } as never }));
    const clip = findings.find((f) => f.id === 'loudness.clipping');
    expect(clip?.severity).toBe('critical');
    expect(clip?.phase1Field).toBe('saturationDetail.clippedSampleCount');
    expect(clip?.detail).toContain('42');
  });

  it('flags an inter-sample true-peak over as critical', () => {
    const findings = collectNotableFindings(makePhase1({ truePeak: 0.6 }));
    expect(findings.find((f) => f.id === 'loudness.truePeakOver')?.severity).toBe('critical');
  });

  it('flags an ambiguous fundamentals domain as a warning', () => {
    const findings = collectNotableFindings(makePhase1({ fundamentalsQuality: fq({ tempo: dom('ambiguous', 'Tempo cross-check weak.') }) }));
    const tempo = findings.find((f) => f.id === 'fundamentals.tempo.ambiguous');
    expect(tempo?.severity).toBe('warning');
    expect(tempo?.detail).toBe('Tempo cross-check weak.');
    expect(tempo?.phase1Field).toBe('bpm');
  });

  it('does NOT flag the routine assumed-4/4 meter (ambiguous meter is the default)', () => {
    const findings = collectNotableFindings(makePhase1({ fundamentalsQuality: fq({ meter: dom('ambiguous', 'Meter is a working assumption.') }) }));
    expect(findings.some((f) => f.domain === 'Meter')).toBe(false);
  });

  it('orders critical before warning', () => {
    const findings = collectNotableFindings(makePhase1({ truePeak: 0.6, fundamentalsQuality: fq({ key: dom('ambiguous', 'Key uncertain.') }) }));
    const sev = findings.map((f) => f.severity);
    expect(sev.indexOf('critical')).toBeLessThan(sev.indexOf('warning'));
  });

  it('flags a genre-relative too-loud master as a warning', () => {
    vi.mocked(generateMixDoctorReport).mockReturnValue({ ...OPTIMAL_REPORT, loudnessAdvice: { issue: 'too-loud', message: 'Hot master.' } } as unknown as MixDoctorReport);
    const loud = collectNotableFindings(makePhase1()).find((f) => f.id === 'mix.loudness');
    expect(loud?.severity).toBe('warning');
    expect(loud?.phase1Field).toBe('lufsIntegrated');
  });

  it('flags a sub-bass mono issue, citing the field mixDoctor used', () => {
    vi.mocked(generateMixDoctorReport).mockReturnValue({ ...OPTIMAL_REPORT, stereoAdvice: { monoCompatible: false, message: 'Collapse sub bass.' } } as unknown as MixDoctorReport);
    const mono = collectNotableFindings(makePhase1({ monoCompatible: false })).find((f) => f.id === 'mix.stereo.mono');
    expect(mono?.severity).toBe('warning');
    expect(mono?.phase1Field).toBe('monoCompatible');
  });

  it('maps an off-target band to an info Balance finding', () => {
    vi.mocked(generateMixDoctorReport).mockReturnValue({ ...OPTIMAL_REPORT, advice: [{ band: 'Highs', issue: 'too-loud', message: 'Harsh highs.' }] } as unknown as MixDoctorReport);
    const band = collectNotableFindings(makePhase1()).find((f) => f.id === 'mix.band.highs');
    expect(band?.severity).toBe('info');
    expect(band?.phase1Field).toBe('spectralBalance.highs');
  });

  it('dedups: objective clipping supersedes the genre-relative too-loud warning', () => {
    vi.mocked(generateMixDoctorReport).mockReturnValue({ ...OPTIMAL_REPORT, loudnessAdvice: { issue: 'too-loud', message: 'Hot.' } } as unknown as MixDoctorReport);
    const findings = collectNotableFindings(makePhase1({ saturationDetail: { clippedSampleCount: 10 } as never }));
    expect(findings.some((f) => f.id === 'loudness.clipping')).toBe(true);
    expect(findings.some((f) => f.id === 'mix.loudness')).toBe(false);
  });

  it('skips mixDoctor (no crash) when spectralBalance is absent (fast mode)', () => {
    const p = makePhase1({ spectralBalance: null as never });
    expect(() => collectNotableFindings(p)).not.toThrow();
    expect(generateMixDoctorReport).not.toHaveBeenCalled();
  });
});

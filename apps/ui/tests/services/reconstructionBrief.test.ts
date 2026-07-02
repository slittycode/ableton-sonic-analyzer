import { describe, it, expect } from 'vitest';
import type { Phase1Result } from '../../src/types';
import { buildReconstructionBrief } from '../../src/services/reconstructionBrief';

// Minimal valid Phase1Result (mirrors the factory in notableFindings.test.ts).
const makePhase1 = (overrides: Partial<Phase1Result> = {}): Phase1Result => ({
  bpm: 126, bpmConfidence: 0.91, key: 'F minor', keyConfidence: 0.87,
  timeSignature: '4/4', timeSignatureSource: 'assumed_four_four', durationSeconds: 210.6,
  lufsIntegrated: -9.0, lufsRange: 6.0, truePeak: -1.0, crestFactor: 11.0, plr: 7.9,
  stereoWidth: 0.6, stereoCorrelation: 0.6,
  stereoDetail: { stereoWidth: 0.6, stereoCorrelation: 0.6, subBassMono: true },
  spectralBalance: { subBass: 0, lowBass: 0, lowMids: 0, mids: 0, upperMids: 0, highs: 0, brilliance: 0 },
  rhythmDetail: {
    onsetRate: 4.2, beatGrid: [0, 0.5], downbeats: [0], beatPositions: [0, 0.5], grooveAmount: 0.4,
  },
  grooveDetail: { kickSwing: 0.12, hihatSwing: 0.31, kickAccent: [], hihatAccent: [] },
  sidechainDetail: {
    pumpingStrength: 0.65, pumpingRegularity: 0.8, pumpingRate: 'quarter', pumpingConfidence: 0.31,
  },
  ...overrides,
});

const dom = (status: string, plainEnglish: string, confidence: number | null = null) =>
  ({ status, plainEnglish, source: null, confidence, evidence: {} });

const fq = (domains: Record<string, unknown>) =>
  ({
    schemaVersion: 'fundamentals-quality.v1', targetProfile: 'electronic_ableton_v1',
    analysisMode: 'full', localOnly: true, llmExcluded: true, overallStatus: 'ambiguous', domains,
  } as unknown as NonNullable<Phase1Result['fundamentalsQuality']>);

describe('buildReconstructionBrief', () => {
  it('produces all 8 lines from a full payload, each with at least one citation', () => {
    const lines = buildReconstructionBrief(makePhase1());
    expect(lines.map((l) => l.domain)).toEqual([
      'key', 'tempo', 'meter', 'groove', 'loudness', 'stereo', 'spectral', 'dynamics',
    ]);
    for (const line of lines) {
      expect(line.phase1Fields.length).toBeGreaterThanOrEqual(1);
      expect(line.text.length).toBeGreaterThan(0);
    }
  });

  it('omits groove/stereo/spectral/dynamics lines on a fast-mode-shaped payload', () => {
    const lines = buildReconstructionBrief(makePhase1({
      rhythmDetail: null,
      grooveDetail: null,
      sidechainDetail: null,
      spectralBalance: null as unknown as Phase1Result['spectralBalance'],
      stereoWidth: NaN,
      stereoCorrelation: NaN,
      stereoDetail: null,
      plr: null,
      crestFactor: null,
    }));
    expect(lines.map((l) => l.domain)).toEqual(['key', 'tempo', 'meter', 'loudness']);
  });

  it('omits the key line entirely when key is null instead of guessing', () => {
    const lines = buildReconstructionBrief(makePhase1({ key: null }));
    expect(lines.find((l) => l.domain === 'key')).toBeUndefined();
  });

  it('hedges the key line at the approximate threshold (keyConfidence <= 0.6)', () => {
    const hedged = buildReconstructionBrief(makePhase1({ keyConfidence: 0.6 }));
    expect(hedged.find((l) => l.domain === 'key')?.text).toContain('approximate');
    const confident = buildReconstructionBrief(makePhase1({ keyConfidence: 0.61 }));
    expect(confident.find((l) => l.domain === 'key')?.text).not.toContain('approximate');
  });

  it('reuses the fundamentals domain plainEnglish verbatim when non-authoritative', () => {
    const phase1 = makePhase1({
      fundamentalsQuality: fq({
        tempo: dom('ambiguous', 'Two tempo detectors disagree; the grid may be half-time.', 0.4),
      }),
    });
    const tempo = buildReconstructionBrief(phase1).find((l) => l.domain === 'tempo');
    expect(tempo?.text).toContain('Two tempo detectors disagree; the grid may be half-time.');
    expect(tempo?.confidence).toBe(0.4);
    expect(tempo?.band?.id).toBe('rough');
  });

  it('does not append plainEnglish for authoritative domains', () => {
    const phase1 = makePhase1({
      fundamentalsQuality: fq({ tempo: dom('authoritative', 'Tempo was measured locally.', 0.98) }),
    });
    const tempo = buildReconstructionBrief(phase1).find((l) => l.domain === 'tempo');
    expect(tempo?.text).toBe('Set your Live set to 126.0 BPM.');
    expect(tempo?.confidence).toBe(0.98);
  });

  it('marks the meter as assumed when timeSignatureSource is assumed_four_four', () => {
    const meter = buildReconstructionBrief(makePhase1()).find((l) => l.domain === 'meter');
    expect(meter?.text).toContain('assumed');
    const measured = buildReconstructionBrief(makePhase1({ timeSignatureSource: 'measured' }))
      .find((l) => l.domain === 'meter');
    expect(measured?.text).toBe('Measured meter: 4/4.');
  });

  it('describes swing qualitatively and skips low-confidence sidechain pumping', () => {
    const groove = buildReconstructionBrief(makePhase1()).find((l) => l.domain === 'groove');
    // max(kickSwing 0.12, hihatSwing 0.31) > 0.3 -> noticeably swung
    expect(groove?.text).toContain('noticeably swung');
    // pumpingConfidence 0.31 < 0.5 -> no pumping claim
    expect(groove?.text).not.toContain('pumping');

    const pumping = buildReconstructionBrief(makePhase1({
      sidechainDetail: {
        pumpingStrength: 0.65, pumpingRegularity: 0.8, pumpingRate: 'quarter', pumpingConfidence: 0.8,
      },
    })).find((l) => l.domain === 'groove');
    expect(pumping?.text).toContain('pumping');
    expect(pumping?.phase1Fields).toContain('sidechainDetail.pumpingRate');
  });

  it('cites lufsRange and truePeak only when present, and flags inter-sample overs', () => {
    const loudness = buildReconstructionBrief(makePhase1()).find((l) => l.domain === 'loudness');
    expect(loudness?.phase1Fields).toEqual(['lufsIntegrated', 'lufsRange', 'truePeak']);

    const overs = buildReconstructionBrief(makePhase1({ truePeak: 0.3 }))
      .find((l) => l.domain === 'loudness');
    expect(overs?.text).toContain('inter-sample overs');

    const bare = buildReconstructionBrief(makePhase1({ lufsRange: null, truePeak: null }))
      .find((l) => l.domain === 'loudness');
    expect(bare?.phase1Fields).toEqual(['lufsIntegrated']);
  });

  it('names ±3 dB-from-median outlier bands with per-band citations', () => {
    const lines = buildReconstructionBrief(makePhase1({
      spectralBalance: { subBass: 6, lowBass: 0, lowMids: 0, mids: 0, upperMids: 0, highs: -4, brilliance: 0 },
    }));
    const spectral = lines.find((l) => l.domain === 'spectral');
    expect(spectral?.text).toContain('sub bass');
    expect(spectral?.text).toContain('highs');
    expect(spectral?.phase1Fields).toContain('spectralBalance.subBass');
    expect(spectral?.phase1Fields).toContain('spectralBalance.highs');
  });

  it('describes an even spectrum when no band is a ±3 dB outlier', () => {
    const spectral = buildReconstructionBrief(makePhase1()).find((l) => l.domain === 'spectral');
    expect(spectral?.text).toContain('fairly even');
    expect(spectral?.phase1Fields.length).toBeGreaterThanOrEqual(1);
  });

  it('prefers PLR for dynamics and falls back to crest factor', () => {
    const plr = buildReconstructionBrief(makePhase1()).find((l) => l.domain === 'dynamics');
    expect(plr?.phase1Fields).toEqual(['plr']);
    expect(plr?.text).toContain('controlled');

    const crest = buildReconstructionBrief(makePhase1({ plr: null }))
      .find((l) => l.domain === 'dynamics');
    expect(crest?.phase1Fields).toEqual(['crestFactor']);
    expect(crest?.text).toContain('moderately compressed');
  });

  it('notes mono sub-bass with the stereoDetail citation', () => {
    const stereo = buildReconstructionBrief(makePhase1()).find((l) => l.domain === 'stereo');
    expect(stereo?.text).toContain('Sub-bass is mono');
    expect(stereo?.phase1Fields).toContain('stereoDetail.subBassMono');
  });
});

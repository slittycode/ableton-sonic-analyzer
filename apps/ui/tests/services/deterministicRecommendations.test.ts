import { describe, it, expect } from 'vitest';
import type { Phase1Result, Phase2Result } from '../../src/types';
import type { AnalysisStageStatus } from '../../src/types/backend';
import {
  buildDeterministicAdvice,
  classifySpectralBands,
  projectAudioFeatures,
  shouldShowDeterministicFallback,
} from '../../src/services/deterministicRecommendations';

const makePhase1 = (overrides: Partial<Phase1Result> = {}): Phase1Result => ({
  bpm: 126, bpmConfidence: 0.91, key: 'F minor', keyConfidence: 0.87,
  timeSignature: '4/4', durationSeconds: 210.6,
  lufsIntegrated: -9.0, lufsRange: 6.0, truePeak: -1.0, crestFactor: 11.0,
  stereoWidth: 0.6, stereoCorrelation: 0.6,
  spectralBalance: { subBass: 0, lowBass: 0, lowMids: 0, mids: 0, upperMids: 0, highs: 0, brilliance: 0 },
  spectralDetail: { spectralCentroidMean: 2000 },
  rhythmDetail: {
    onsetRate: 4.0, beatGrid: [0, 0.5], downbeats: [0], beatPositions: [0, 0.5], grooveAmount: 0.4,
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

describe('shouldShowDeterministicFallback', () => {
  const statuses: AnalysisStageStatus[] = [
    'queued', 'running', 'blocked', 'ready', 'completed', 'failed', 'interrupted', 'not_requested',
  ];
  const expectedWithoutPhase2: Record<AnalysisStageStatus, boolean> = {
    queued: false, running: false, blocked: false, ready: false,
    completed: true, failed: true, interrupted: true, not_requested: true,
  };

  it('matches the truth table when phase2 is null', () => {
    for (const status of statuses) {
      expect(shouldShowDeterministicFallback(null, status), status).toBe(expectedWithoutPhase2[status]);
    }
    expect(shouldShowDeterministicFallback(null, null)).toBe(true);
    expect(shouldShowDeterministicFallback(null, undefined)).toBe(true);
  });

  it('is always false when phase2 is present', () => {
    const phase2 = { trackCharacter: 'x' } as unknown as Phase2Result;
    for (const status of statuses) {
      expect(shouldShowDeterministicFallback(phase2, status), status).toBe(false);
    }
    expect(shouldShowDeterministicFallback(phase2, null)).toBe(false);
  });
});

describe('classifySpectralBands', () => {
  it('maps the 7 bands with JSON_SCHEMA.md ranges and median-relative dominance', () => {
    const bands = classifySpectralBands(makePhase1({
      spectralBalance: { subBass: 4, lowBass: 0, lowMids: 0, mids: 0, upperMids: 0, highs: -13, brilliance: 0 },
    }));
    expect(bands).toHaveLength(7);
    expect(bands[0]).toMatchObject({ name: 'Sub Bass', rangeHz: [20, 80], dominance: 'dominant' });
    expect(bands.find((b) => b.name === 'Highs')?.dominance).toBe('absent');
    expect(bands.find((b) => b.name === 'Mids')).toMatchObject({ rangeHz: [500, 2000], dominance: 'present' });
    expect(bands.find((b) => b.name === 'Brilliance')?.rangeHz).toEqual([10000, 20000]);
  });

  it('returns [] on a fast-mode payload with null spectralBalance', () => {
    expect(classifySpectralBands(makePhase1({
      spectralBalance: null as unknown as Phase1Result['spectralBalance'],
    }))).toEqual([]);
  });

  it('takes peakDb from spectralBalanceTimeSeries when present, else averageDb', () => {
    const noSeries = classifySpectralBands(makePhase1());
    expect(noSeries[0].peakDb).toBe(noSeries[0].averageDb);

    const withSeries = classifySpectralBands(makePhase1({
      spectralBalanceTimeSeries: [
        { t: 0, subBass: 2.5, lowBass: 0, lowMids: 0, mids: 0, upperMids: 0, highs: 0, brilliance: 0 },
        { t: 1, subBass: 5.5, lowBass: 0, lowMids: 0, mids: 0, upperMids: 0, highs: 0, brilliance: 0 },
      ],
    }));
    expect(withSeries[0].peakDb).toBe(5.5);
  });
});

describe('projectAudioFeatures', () => {
  it('splits the Phase 1 key string into root and lowercased scale', () => {
    expect(projectAudioFeatures(makePhase1({ key: 'A Minor' })).key).toEqual({ root: 'A', scale: 'minor' });
    expect(projectAudioFeatures(makePhase1({ key: null })).key).toEqual({ root: '?', scale: '' });
  });

  it('uses NaN sentinels for absent fast-mode measurements', () => {
    const features = projectAudioFeatures(makePhase1({
      crestFactor: null, rhythmDetail: null, spectralDetail: null,
    }));
    expect(Number.isNaN(features.crestFactor)).toBe(true);
    expect(Number.isNaN(features.onsetDensity)).toBe(true);
    expect(Number.isNaN(features.spectralCentroidMean)).toBe(true);
  });

  it('clamps pre-v2 raw bpmConfidence into 0-1', () => {
    expect(projectAudioFeatures(makePhase1({ bpmConfidence: 4.2 })).bpmConfidence).toBe(1);
  });
});

describe('buildDeterministicAdvice', () => {
  it('cites every card with at least one Phase 1 field', () => {
    const cards = buildDeterministicAdvice(makePhase1());
    expect(cards.length).toBeGreaterThan(0);
    for (const card of cards) {
      expect(card.phase1Fields.length, card.id).toBeGreaterThanOrEqual(1);
      expect(card.device.length, card.id).toBeGreaterThan(0);
    }
  });

  it('covers all 8 FX rules with citations (engine drift guard)', () => {
    // Drive features through every FX_RULES branch and assert each fired
    // rule produced a cited card — an unmapped artifact would be dropped.
    const scenarios: Array<{ phase1: Phase1Result; slug: string }> = [
      { phase1: makePhase1({ crestFactor: 4 }), slug: 'det.fx.crest-low' },
      { phase1: makePhase1({ crestFactor: 8 }), slug: 'det.fx.crest-moderate' },
      { phase1: makePhase1({ crestFactor: 13 }), slug: 'det.fx.crest-high' },
      {
        phase1: makePhase1({
          spectralBalance: { subBass: 5, lowBass: 0, lowMids: 0, mids: 0, upperMids: 0, highs: 0, brilliance: 0 },
        }),
        slug: 'det.fx.sub-dominant',
      },
      { phase1: makePhase1({ spectralDetail: { spectralCentroidMean: 3500 } }), slug: 'det.fx.bright' },
      { phase1: makePhase1({ spectralDetail: { spectralCentroidMean: 800 } }), slug: 'det.fx.dark' },
      {
        phase1: makePhase1({
          rhythmDetail: { onsetRate: 9, beatGrid: [], downbeats: [], beatPositions: [], grooveAmount: 0 },
        }),
        slug: 'det.fx.dense',
      },
      {
        phase1: makePhase1({
          rhythmDetail: { onsetRate: 1, beatGrid: [], downbeats: [], beatPositions: [], grooveAmount: 0 },
        }),
        slug: 'det.fx.sparse',
      },
    ];
    for (const { phase1, slug } of scenarios) {
      const cards = buildDeterministicAdvice(phase1);
      expect(cards.map((c) => c.id), slug).toContain(slug);
    }
  });

  it('covers all 5 secret-sauce tricks with citations (engine drift guard)', () => {
    const wall = buildDeterministicAdvice(makePhase1({
      crestFactor: 5,
      spectralBalance: { subBass: 5, lowBass: 5, lowMids: 5, mids: 0, upperMids: 0, highs: 0, brilliance: 0 },
    })).find((c) => c.kind === 'secretSauce');
    expect(wall?.title).toContain('Wall-of-Sound');
    expect(wall?.phase1Fields).toEqual([
      'spectralBalance.subBass', 'spectralBalance.lowBass', 'spectralBalance.lowMids', 'crestFactor',
    ]);

    const tight = buildDeterministicAdvice(makePhase1({
      rhythmDetail: { onsetRate: 7, beatGrid: [], downbeats: [], beatPositions: [], grooveAmount: 0 },
    })).find((c) => c.kind === 'secretSauce');
    expect(tight?.title).toContain('Tight Rhythmic Programming');
    expect(tight?.phase1Fields).toEqual(['rhythmDetail.onsetRate', 'bpm', 'bpmConfidence']);

    const air = buildDeterministicAdvice(makePhase1({
      spectralDetail: { spectralCentroidMean: 3000 },
      spectralBalance: { subBass: 0, lowBass: 0, lowMids: 0, mids: 0, upperMids: 0, highs: 0, brilliance: 1 },
    })).find((c) => c.kind === 'secretSauce');
    expect(air?.title).toContain('Air and Presence');
    expect(air?.phase1Fields).toContain('spectralBalance.brilliance');

    const sub = buildDeterministicAdvice(makePhase1({
      spectralBalance: { subBass: 5, lowBass: 0, lowMids: 0, mids: 0, upperMids: 0, highs: 0, brilliance: 0 },
    })).find((c) => c.kind === 'secretSauce');
    expect(sub?.title).toContain('Sub Bass Design');
    expect(sub?.phase1Fields).toEqual(['spectralBalance.subBass']);

    const balanced = buildDeterministicAdvice(makePhase1()).find((c) => c.kind === 'secretSauce');
    expect(balanced?.title).toContain('Balanced Mix Architecture');
    expect(balanced?.phase1Fields).toEqual(['bpm', 'key']);
  });

  it('hedges tempo-citing cards when the tempo fundamentals domain is ambiguous', () => {
    const cards = buildDeterministicAdvice(makePhase1({
      rhythmDetail: { onsetRate: 7, beatGrid: [], downbeats: [], beatPositions: [], grooveAmount: 0 },
      fundamentalsQuality: fq({
        tempo: dom('ambiguous', 'Two tempo detectors disagree; the grid may be half-time.', 0.4),
      }),
    }));
    const sauce = cards.find((c) => c.kind === 'secretSauce');
    expect(sauce?.hedges).toContain('Two tempo detectors disagree; the grid may be half-time.');
  });

  it('skips tempo-citing cards when the tempo fundamentals domain failed', () => {
    const cards = buildDeterministicAdvice(makePhase1({
      rhythmDetail: { onsetRate: 7, beatGrid: [], downbeats: [], beatPositions: [], grooveAmount: 0 },
      fundamentalsQuality: fq({ tempo: dom('failed', 'Tempo could not be measured.') }),
    }));
    expect(cards.find((c) => c.kind === 'secretSauce')).toBeUndefined();
  });

  it('hedges via the scalar threshold when no fundamentals layer is present', () => {
    const cards = buildDeterministicAdvice(makePhase1({
      bpmConfidence: 0.5,
      rhythmDetail: { onsetRate: 7, beatGrid: [], downbeats: [], beatPositions: [], grooveAmount: 0 },
    }));
    // bpmConfidence 0.5 fails the engine's own > 0.7 check, so the tight-
    // rhythm sauce never fires; the fallback sauce cites bpm and is hedged.
    const sauce = cards.find((c) => c.kind === 'secretSauce');
    expect(sauce?.title).toContain('Balanced Mix Architecture');
    expect(sauce?.hedges.some((h) => h.includes('Tempo confidence is low'))).toBe(true);
  });

  it('skips the key-citing fallback sauce when key is null', () => {
    const cards = buildDeterministicAdvice(makePhase1({ key: null }));
    expect(cards.find((c) => c.kind === 'secretSauce')).toBeUndefined();
  });

  it('emits instrument cards only for non-absent bands, citing the band key', () => {
    const cards = buildDeterministicAdvice(makePhase1({
      spectralBalance: { subBass: 5, lowBass: 0, lowMids: 0, mids: 0, upperMids: 0, highs: -20, brilliance: 0 },
    }));
    const subCard = cards.find((c) => c.id === 'det.band.subBass');
    expect(subCard?.device).toBe('Operator');
    expect(subCard?.phase1Fields).toEqual(['spectralBalance.subBass']);
    expect(cards.find((c) => c.id === 'det.band.highs')).toBeUndefined();
  });

  it('adds the time-series citation when peakDb came from it', () => {
    const cards = buildDeterministicAdvice(makePhase1({
      spectralBalanceTimeSeries: [
        { t: 0, subBass: 1, lowBass: 0, lowMids: 0, mids: 0, upperMids: 0, highs: 0, brilliance: 0 },
      ],
    }));
    const instrument = cards.find((c) => c.kind === 'instrument');
    expect(instrument?.phase1Fields).toContain('spectralBalanceTimeSeries');
  });

  it('produces no spectrum-driven cards on a fast-mode payload', () => {
    const cards = buildDeterministicAdvice(makePhase1({
      spectralBalance: null as unknown as Phase1Result['spectralBalance'],
      rhythmDetail: null,
      spectralDetail: null,
      crestFactor: null,
    }));
    expect(cards.filter((c) => c.kind === 'instrument')).toEqual([]);
    expect(cards.filter((c) => c.kind === 'fx')).toEqual([]);
    // The balanced-mix fallback sauce still fires from bpm + key.
    expect(cards.find((c) => c.kind === 'secretSauce')?.phase1Fields).toEqual(['bpm', 'key']);
  });
});

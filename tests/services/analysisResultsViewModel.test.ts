import {
  buildArrangementViewModel,
  buildMelodyInsights,
  buildMixChainGroups,
  buildPatchCards,
  buildSonicElementCards,
  toConfidenceBadges,
  truncateAtSentenceBoundary,
  truncateBySentenceCount,
} from '../../src/components/analysisResultsViewModel';
import { Phase2Result } from '../../src/types';

const phase1 = {
  bpm: 126,
  bpmConfidence: 0.93,
  key: 'F minor',
  keyConfidence: 0.88,
  timeSignature: '4/4',
  durationSeconds: 210.6,
  lufsIntegrated: -7.9,
  truePeak: -0.2,
  stereoWidth: 0.09,
  stereoCorrelation: 0.84,
  spectralBalance: {
    subBass: -0.7,
    lowBass: 1.2,
    mids: -0.3,
    upperMids: 0.4,
    highs: 1,
    brilliance: 0.8,
  },
  melodyDetail: {
    noteCount: 4,
    notes: [
      { midi: 60, onset: 0.2, duration: 0.3 },
      { midi: 64, onset: 0.8, duration: 0.2 },
      { midi: 67, onset: 1.2, duration: 0.4 },
      { midi: 72, onset: 1.9, duration: 0.3 },
    ],
    dominantNotes: [60, 64, 67],
    pitchRange: { min: 60, max: 72 },
    pitchConfidence: 0.72,
    midiFile: '/tmp/example.mid',
    sourceSeparated: true,
    vibratoPresent: false,
    vibratoExtent: 0,
    vibratoRate: 0,
    vibratoConfidence: 0.1,
  },
};

describe('analysisResultsViewModel helpers', () => {
  it('truncates long text at sentence boundaries', () => {
    const long = `${'A'.repeat(610)}. Final sentence should not be included.`;
    const output = truncateAtSentenceBoundary(long, 600);

    expect(output.endsWith('...')).toBe(true);
    expect(output.length).toBeLessThanOrEqual(603);
  });

  it('caps sentence count while preserving sentence boundaries', () => {
    const input = 'One sentence. Two sentence. Three sentence. Four sentence.';
    const output = truncateBySentenceCount(input, 3);

    expect(output).toBe('One sentence. Two sentence. Three sentence....');
  });

  it('normalizes confidence badges to friendly labels and levels', () => {
    const badges = toConfidenceBadges([
      { field: 'Key Signature', value: '0.62', reason: 'Measured confidence' },
      { field: 'Melody Transcription', value: 'LOW', reason: 'Weak melodic signal' },
      { field: 'True Peak', value: 'HIGH', reason: 'Stable result' },
    ]);

    expect(badges).toEqual([
      { label: 'Key', level: 'Moderate' },
      { label: 'Melody', level: 'Low' },
      { label: 'Peak', level: 'High' },
    ]);
  });

  it('builds arrangement timeline segments and novelty markers', () => {
    const arrangement = buildArrangementViewModel(phase1, {
      summary: 'Intro to drop transition.',
      segments: [
        { index: 1, startTime: 0, endTime: 32, lufs: -9.2, description: 'Intro: low energy opener' },
        { index: 2, startTime: 32, endTime: 96, lufs: -7.6, description: 'Drop: full range impact' },
      ],
      noveltyNotes: 'Events at 12.5s and 74.0s indicate transitions.',
    });

    expect(arrangement).not.toBeNull();
    expect(arrangement?.segments[0].name).toBe('INTRO');
    expect(arrangement?.segments[1].name).toBe('DROP');
    expect(arrangement?.segments[0].lufs).toBe(-9.2);
    expect(arrangement?.segments[1].lufs).toBe(-7.6);
    expect(arrangement?.noveltyNotes).toContain('12.5s');
    expect(arrangement?.noveltyMarkers.length).toBe(2);
  });

  it('caps width & stereo card content at six sentences', () => {
    const sonicCards = buildSonicElementCards(phase1, {
      kick: 'Kick sentence.',
      bass: 'Bass sentence.',
      melodicArp: 'Arp sentence.',
      grooveAndTiming: 'Groove sentence.',
      effectsAndTexture: 'Fx sentence.',
      widthAndStereo:
        'One sentence. Two sentence. Three sentence. Four sentence. Five sentence. Six sentence. Seven sentence.',
      harmonicContent: 'Harmony sentence.',
    });

    const widthCard = sonicCards.find((card) => card.id === 'widthAndStereo');
    const melodicCard = sonicCards.find((card) => card.id === 'melodicArp');
    expect(widthCard).toBeDefined();
    expect(melodicCard?.transcriptionDerived).toBe(true);
    expect(melodicCard?.measurements.some((m) => m.label === 'Transcribed Notes')).toBe(true);
    expect(widthCard?.description.includes('Seven sentence.')).toBe(false);
  });

  it('builds ordered mix groups with high-end detail stage and ensures master limiter fallback', () => {
    const groups = buildMixChainGroups(
      phase1,
      [
        {
          order: 1,
          device: 'Drum Buss',
          parameter: 'Drive',
          value: '6 dB',
          reason: 'Adds drum bite and transient character.',
        },
        {
          order: 2,
          device: 'EQ Eight',
          parameter: 'Low Cut',
          value: '30 Hz',
          reason: 'Cleans up sub energy in bass layers.',
        },
        {
          order: 3,
          device: 'Auto Filter',
          parameter: 'High Shelf',
          value: '+2.0 dB @ 10 kHz',
          reason: 'Adds sparkle to hi-hats and vocal chops in the top end.',
        },
      ],
      {
        kick: 'Kick sentence.',
        bass: 'Bass sentence.',
        melodicArp: 'Arp sentence.',
        grooveAndTiming: 'Groove sentence.',
        effectsAndTexture: 'Top end details from hi-hats and synth sweeps.',
        widthAndStereo: 'Stereo widening on high hats only.',
      },
    );

    const highEnd = groups.find((group) => group.name === 'HIGH-END DETAIL');
    const master = groups.find((group) => group.name === 'MASTER BUS');
    expect(highEnd).toBeDefined();
    expect(highEnd?.annotation).toContain('Annotated high-end focus');
    expect(master).toBeDefined();
    expect(master?.cards.some((card) => /limiter/i.test(card.device))).toBe(true);
  });

  it('builds expanded patch cards with at least three parameters', () => {
    const phase2 = {
      trackCharacter: 'Character sentence.',
      detectedCharacteristics: [{ name: 'Dynamics', confidence: 'HIGH', explanation: 'Strong profile' }],
      arrangementOverview: {
        summary: 'Summary',
        segments: [{ index: 1, startTime: 0, endTime: 20, description: 'Intro segment' }],
      },
      sonicElements: {
        kick: 'Kick',
        bass: 'Bass',
        melodicArp: 'Arp',
        grooveAndTiming: 'Groove',
        effectsAndTexture: 'FX',
      },
      mixAndMasterChain: [],
      secretSauce: { title: 'Sauce', explanation: 'Explain', implementationSteps: ['Step'] },
      confidenceNotes: [{ field: 'Key Signature', value: '0.7', reason: 'Reason' }],
      abletonRecommendations: [
        {
          device: 'Operator',
          category: 'Synth',
          parameter: 'Coarse',
          value: '1.00',
          reason: 'Matches tonal center.',
          advancedTip: 'Modulate coarse slowly.',
        },
      ],
    } as Phase2Result;

    const cards = buildPatchCards(phase1, phase2);

    expect(cards.length).toBeGreaterThan(0);
    expect(cards[0].parameters.length).toBeGreaterThanOrEqual(3);
    expect(cards[0].whyThisWorks.length).toBeGreaterThan(10);
    expect(cards.some((card) => /stereo|width/i.test(card.device))).toBe(true);
    expect(cards.some((card) => card.transcriptionDerived)).toBe(true);
  });

  it('builds melody insights from phase1 transcription payload', () => {
    const insights = buildMelodyInsights(phase1);

    expect(insights).not.toBeNull();
    expect(insights?.noteCount).toBe(4);
    expect(insights?.rangeLabel).toBe('C4 - C5');
    expect(insights?.dominantNotes).toEqual(['C4', 'E4', 'G4']);
    expect(insights?.confidenceLabel).toBe('Moderate');
    expect(insights?.isDraft).toBe(false);
  });
});

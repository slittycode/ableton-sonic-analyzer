import { generateMarkdown } from '../../src/utils/exportUtils';
import { Phase1Result, Phase2Result } from '../../src/types';

const basePhase1: Phase1Result = {
  bpm: 126,
  bpmConfidence: 0.91,
  key: 'F minor',
  keyConfidence: 0.87,
  timeSignature: '4/4',
  durationSeconds: 210.6,
  lufsIntegrated: -7.9,
  truePeak: -0.2,
  stereoWidth: 0.69,
  stereoCorrelation: 0.84,
  spectralBalance: {
    subBass: -0.7,
    lowBass: 1.2,
    mids: -0.3,
    upperMids: 0.4,
    highs: 1.0,
    brilliance: 0.8,
  },
};

const basePhase2: Phase2Result = {
  trackCharacter: 'Tight modern electronic mix.',
  detectedCharacteristics: [
    { name: 'Stereo Discipline', confidence: 'HIGH', explanation: 'Controlled width and correlation.' },
  ],
  arrangementOverview: {
    summary: 'Arrangement transitions and energy shifts.',
    segments: [
      {
        index: 1,
        startTime: 0,
        endTime: 30,
        lufs: -8.4,
        description: 'Intro: sparse opening.',
        spectralNote: 'High shelf lift around 8 kHz on hats.',
      },
      {
        index: 2,
        startTime: 30,
        endTime: 75,
        description: 'Drop: dense full-range impact.',
      },
    ],
    noveltyNotes: 'Novel shifts at 14.0s and 63.5s align with transitions.',
  },
  sonicElements: {
    kick: { description: 'Punchy kick body.' },
    bass: { description: 'Focused bass lane.' },
    melodicArp: { description: 'Simple melodic motif.' },
    grooveAndTiming: { description: 'Quantized groove.' },
    effectsAndTexture: { description: 'Light atmospherics.' },
  },
  mixAndMasterChain: [
    {
      order: 1,
      device: 'Drum Buss',
      parameter: 'Drive',
      value: '5 dB',
      reason: 'Adds punch to drums.',
    },
    {
      order: 2,
      device: 'EQ Eight',
      parameter: 'Low Cut',
      value: '30 Hz',
      reason: 'Removes rumble from bass bus.',
    },
  ],
  secretSauce: {
    title: 'Punch Layering',
    explanation: 'Layered transient enhancement.',
    implementationSteps: [{ step: 'Step 1' }, { step: 'Step 2' }],
  },
  confidenceNotes: [{ field: 'Key Signature', value: 'HIGH', reason: 'Stable detection.' }],
  abletonRecommendations: [
    {
      device: 'Operator',
      category: 'SYNTHESIS',
      parameter: 'Coarse',
      value: '1.00',
      reason: 'Matches tonal center.',
    },
  ],
};

describe('generateMarkdown', () => {
  it('renders arrangement and mix chain sections as human-readable markdown', () => {
    const markdown = generateMarkdown(basePhase1, basePhase2);

    expect(markdown).toContain('### Arrangement Overview');
    expect(markdown).toContain('Arrangement transitions and energy shifts.');
    expect(markdown).toContain('- Segment 1 (0s-30s, -8.4 LUFS): Intro: sparse opening. Spectral note: High shelf lift around 8 kHz on hats.');
    expect(markdown).toContain('- Segment 2 (30s-75s): Drop: dense full-range impact.');
    expect(markdown).toContain('Novelty Notes: Novel shifts at 14.0s and 63.5s align with transitions.');

    expect(markdown).toContain('### Mix and Master Chain');
    expect(markdown).toContain('1. Drum Buss — Drive: 5 dB. Adds punch to drums.');
    expect(markdown).toContain('2. EQ Eight — Low Cut: 30 Hz. Removes rumble from bass bus.');

    expect(markdown).toContain('### Secret Sauce: Punch Layering');
    expect(markdown).not.toContain('[object Object]');
    expect(markdown).not.toContain('[object Object],[object Object]');
  });

  it('renders width and stereo and harmonic content when present', () => {
    const markdown = generateMarkdown(basePhase1, {
      ...basePhase2,
      sonicElements: {
        ...basePhase2.sonicElements,
        widthAndStereo: 'Stereo image stays wide above the mids.',
        harmonicContent: 'Harmony stays anchored to F minor with sparse motion.',
      },
    });

    expect(markdown).toContain('- **Width and Stereo**: Stereo image stays wide above the mids.');
    expect(markdown).toContain('- **Harmonic Content**: Harmony stays anchored to F minor with sparse motion.');
  });

  it('omits optional sonic element fields when absent or undefined', () => {
    expect(() =>
      generateMarkdown(basePhase1, {
        ...basePhase2,
        sonicElements: {
          ...basePhase2.sonicElements,
          widthAndStereo: undefined,
          harmonicContent: undefined,
        },
      }),
    ).not.toThrow();

    const markdown = generateMarkdown(basePhase1, basePhase2);

    expect(markdown).not.toContain('- **Width and Stereo**:');
    expect(markdown).not.toContain('- **Harmonic Content**:');
    expect(markdown).not.toContain('undefined');
  });
});

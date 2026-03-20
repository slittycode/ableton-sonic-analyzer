import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { AnalysisResults, toggleOpenKeySet } from '../../src/components/AnalysisResults';
import { MIDI_DOWNLOAD_FILE_NAME } from '../../src/components/SessionMusicianPanel';
import { MeasurementResult, Phase2Result, TranscriptionDetail } from '../../src/types';

const baseMeasurement: MeasurementResult = {
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
        lufs: -7.0,
        description: 'Drop: dense full-range impact.',
      },
    ],
    noveltyNotes: 'Novel shifts at 14.0s and 63.5s align with transitions.',
  },
  sonicElements: {
    kick: 'Punchy kick body.',
    bass: 'Focused bass lane.',
    melodicArp: 'Simple melodic motif.',
    grooveAndTiming: 'Quantized groove.',
    effectsAndTexture: 'Light atmospherics.',
    harmonicContent: 'Approximate harmonic movement centred around the detected key.',
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
    {
      order: 3,
      device: 'Auto Filter',
      parameter: 'High Shelf',
      value: '+2.0 dB @ 10 kHz',
      reason: 'Adds sparkle to hi-hats and vocal chops in the top end.',
    },
  ],
  secretSauce: {
    title: 'Punch Layering',
    explanation: 'Layered transient enhancement.',
    implementationSteps: ['Step 1', 'Step 2'],
  },
  confidenceNotes: [{ field: 'Key Signature', value: 'HIGH', reason: 'Stable detection.' }],
  abletonRecommendations: [
    {
      device: 'Operator',
      category: 'SYNTHESIS',
      parameter: 'Coarse',
      value: '1.00',
      reason: 'Matches tonal center.',
      advancedTip: 'Modulate coarse slowly.',
    },
  ],
};

const baseSymbolic: TranscriptionDetail = {
  transcriptionMethod: 'basic-pitch-legacy',
  noteCount: 2,
  averageConfidence: 0.83,
  stemSeparationUsed: true,
  fullMixFallback: false,
  stemsTranscribed: ['bass', 'other'],
  dominantPitches: [
    { pitchMidi: 48, pitchName: 'C3', count: 4 },
    { pitchMidi: 55, pitchName: 'G3', count: 3 },
  ],
  pitchRange: {
    minMidi: 48,
    maxMidi: 67,
    minName: 'C3',
    maxName: 'G4',
  },
  notes: [
    {
      pitchMidi: 48,
      pitchName: 'C3',
      onsetSeconds: 0.1,
      durationSeconds: 0.4,
      confidence: 0.92,
      stemSource: 'bass',
    },
    {
      pitchMidi: 67,
      pitchName: 'G4',
      onsetSeconds: 0.5,
      durationSeconds: 0.2,
      confidence: 0.74,
      stemSource: 'other',
    },
  ],
};

describe('AnalysisResults UI wiring', () => {
  it('toggles only the targeted sonic card key', () => {
    const initial = new Set<string>(['kick']);

    const openBass = toggleOpenKeySet(initial, 'bass');
    expect(openBass.has('kick')).toBe(true);
    expect(openBass.has('bass')).toBe(true);

    const closeKick = toggleOpenKeySet(openBass, 'kick');
    expect(closeKick.has('kick')).toBe(false);
    expect(closeKick.has('bass')).toBe(true);

    // Ensure original set remains unchanged.
    expect(initial.has('kick')).toBe(true);
    expect(initial.has('bass')).toBe(false);
  });

  it('renders mix and patch cards using strict grid layout', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: baseMeasurement,
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect((html.match(/class=\"grid gap-4 grid-cols-1 sm:grid-cols-2\"/g) ?? []).length).toBeGreaterThanOrEqual(2);
    expect(html).toContain('🥁 DRUM PROCESSING');
    expect(html).toContain('🫧 BASS PROCESSING');
    expect(html).toContain('✨ HIGH-END DETAIL');
    expect(html).toContain('🧱 MASTER BUS');
    expect(html).not.toContain('class="flex flex-wrap gap-4"');
    expect(html).not.toContain('data-testid="mix-group-grid-');
    expect(html).not.toContain('data-testid="patch-grid"');
  });

  it('renders character pills from the first four detected characteristics with shortened names', () => {
    const phase2WithTags: Phase2Result = {
      ...basePhase2,
      detectedCharacteristics: [
        { name: 'Wide Stereo Discipline', confidence: 'HIGH', explanation: 'Controlled width and correlation.' },
        { name: 'Transient Shape', confidence: 'MED', explanation: 'Defined drum edges.' },
        { name: 'Bass Weight', confidence: 'LOW', explanation: 'Sub support is moderate.' },
        { name: 'Top End Texture', confidence: 'MODERATE', explanation: 'Fine-grain sparkle.' },
        { name: 'Ignore This Extra', confidence: 'HIGH', explanation: 'Should not show in top four pills.' },
      ],
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: baseMeasurement,
        phase2: phase2WithTags,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('>Wide Stereo</span>');
    expect(html).toContain('>Transient Shape</span>');
    expect(html).toContain('>Bass Weight</span>');
    expect(html).toContain('>Top End</span>');
    expect(html).not.toContain('>Ignore This</span>');
    expect(html).toContain('bg-success/20 text-success border-success/30');
    expect(html).toContain('bg-warning/20 text-warning border-warning/30');
    expect(html).toContain('bg-error/20 text-error border-error/30');
  });

  it('renders character scanning fallback when phase2 is unavailable', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: baseMeasurement,
        phase2: null,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('SCANNING...');
    expect(html).toContain('AI Interpretation');
    expect(html).toContain('Draft — AI interpretation is incomplete or unavailable.');
  });

  it('renders exactly two DSP badges for the current Phase 1 headings and one AI advisory badge', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: baseMeasurement,
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect((html.match(/>DSP</g) ?? []).length).toBe(2);
    expect((html.match(/>AI</g) ?? []).length).toBe(1);
    expect(html).toContain('Interpretive guidance generated from DSP measurements. Not a ground-truth measurement.');
  });

  it('shows the key low-confidence warning at the inclusive 0.60 threshold', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          keyConfidence: 0.6,
        },
        phase2: null,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('KEY SIG');
    expect(html).toContain('title="Low confidence — treat this as approximate."');
    expect(html).toContain('⚠');
  });

  it('does not show the key low-confidence warning above the threshold', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          keyConfidence: 0.61,
        },
        phase2: null,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).not.toContain('title="Low confidence — treat this as approximate."');
  });

  it('shows the chord low-confidence warning at the inclusive 0.70 threshold', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          chordDetail: {
            chordStrength: 0.7,
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('Harmonic Content');
    expect(html).toContain('title="Low confidence — treat this as approximate."');
    expect(html).toContain('⚠');
  });

  it('does not show the chord low-confidence warning above the threshold', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          chordDetail: {
            chordStrength: 0.71,
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).not.toContain('title="Low confidence — treat this as approximate."');
  });

  it('renders a danceability section when backend danceability data is present', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          danceability: {
            danceability: 1.24,
            dfa: 0.87,
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('Danceability');
    expect(html).toContain('DFA');
    expect(html).toContain('1.24');
    expect(html).toContain('0.87');
  });

  it('uses normalized midi download filename', () => {
    expect(MIDI_DOWNLOAD_FILE_NAME).toBe('track-analysis.mid');
  });

  it('renders symbolic-note unavailable state when melodyDetail is missing', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: baseMeasurement,
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('SYMBOLIC NOTES UNAVAILABLE');
    expect(html).toContain('Run with symbolic extraction enabled, or ensure melodyDetail is present in the DSP payload for a melody guide');
  });

  it('shows the symbolic toggle state by default when both sources are available', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          transcriptionDetail: baseSymbolic,
          melodyDetail: {
            noteCount: 1,
            notes: [{ midi: 72, onset: 0.1, duration: 0.2 }],
            dominantNotes: [72],
            pitchRange: { min: 72, max: 72 },
            pitchConfidence: 0.2,
            midiFile: null,
            sourceSeparated: false,
            vibratoPresent: false,
            vibratoExtent: 0,
            vibratoRate: 0,
            vibratoConfidence: 0,
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('SYMBOLIC');
    expect(html).toContain('MELODY');
    expect(html).toContain('BASIC PITCH LEGACY symbolic notes');
    expect(html).toContain('Range: C3 - G4');
    expect(html).toContain('Confidence: 83%');
    expect(html.match(/Range: C3 - G4/g)?.length ?? 0).toBe(1);
    expect(html.match(/Confidence: 83%/g)?.length ?? 0).toBe(1);
    expect(html).toContain('2 / 2 NOTES');
    expect(html).toContain('CONFIDENCE');
    expect(html).toContain('20%');
    expect(html).toContain('SOURCE: BASIC PITCH LEGACY');
    expect(html).toContain('STEM-AWARE');
    expect(html).toContain('STEMS: bass, other');
    expect(html).toContain('Adjust confidence threshold to filter noise before export.');
    expect(html).not.toContain('SYMBOLIC NOTES UNAVAILABLE');
  });

  it('shows Essentia source badges when only melodyDetail is available', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          melodyDetail: {
            noteCount: 3,
            notes: [
              { midi: 60, onset: 0.2, duration: 0.3 },
              { midi: 64, onset: 0.8, duration: 0.2 },
              { midi: 67, onset: 1.2, duration: 0.4 },
            ],
            dominantNotes: [60, 64, 67],
            pitchRange: { min: 60, max: 67 },
            pitchConfidence: 0.72,
            midiFile: null,
            sourceSeparated: true,
            vibratoPresent: false,
            vibratoExtent: 0,
            vibratoRate: 0,
            vibratoConfidence: 0.1,
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).not.toContain('SOURCE: BASIC PITCH LEGACY');
    expect(html).not.toContain('BASIC PITCH LEGACY symbolic notes');
    expect(html).toContain('SOURCE: ESSENTIA MELODY');
    expect(html).toContain('Monophonic melody guide via Essentia');
  });

  it('renders full-mix provenance when transcription did not use Demucs stems', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          transcriptionDetail: {
          transcriptionMethod: 'basic-pitch-legacy',
          noteCount: 1,
          averageConfidence: 0.61,
          stemSeparationUsed: false,
          fullMixFallback: true,
          stemsTranscribed: ['full_mix'],
          dominantPitches: [{ pitchMidi: 60, pitchName: 'C4', count: 3 }],
          pitchRange: {
            minMidi: 60,
            maxMidi: 60,
            minName: 'C4',
            maxName: 'C4',
          },
          notes: [
            {
              pitchMidi: 60,
              pitchName: 'C4',
              onsetSeconds: 0.2,
              durationSeconds: 0.5,
              confidence: 0.61,
              stemSource: 'full_mix',
            },
          ],
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('FULL MIX');
    expect(html).not.toContain('STEM-AWARE');
  });

  it('renders arrangement novelty and spectral note labels with fixed segment palette colors', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: baseMeasurement,
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('#e05c00');
    expect(html).toContain('#c44b8a');
    expect(html).toContain('NOVELTY EVENTS');
    expect(html).toContain('SPECTRAL NOTE');
    expect(html).toContain('▲ +0.5 dB');
    expect(html).toContain('▼ -0.9 dB');
  });

  it('renders a sticky device navigator with section anchors', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: baseMeasurement,
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('Device Chain');
    expect(html).toContain('href="#section-meas-spectral"');
    expect(html).toContain('href="#section-arrangement"');
    expect(html).toContain('href="#section-session"');
    expect(html).toContain('href="#section-sonic-elements"');
    expect(html).toContain('href="#section-mix-chain"');
    expect(html).toContain('href="#section-patches"');
    expect(html).toContain('id="section-meas-spectral"');
    expect(html).toContain('id="section-arrangement"');
    expect(html).toContain('id="section-session"');
    expect(html).toContain('id="section-sonic-elements"');
    expect(html).toContain('id="section-mix-chain"');
    expect(html).toContain('id="section-patches"');
  });

  it('does not render an empty chord section when chord data lacks progression content', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          chordDetail: {
            chordStrength: 0.62,
            chordSequence: [],
            progression: [],
            dominantChords: [],
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).not.toContain('id="section-chords"');
    expect(html).not.toContain('href="#section-chords"');
  });

  it('renders sidechain detector metrics inside synthesis measurement section', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          sidechainDetail: {
            pumpingStrength: 0.31,
            pumpingRegularity: 0.4,
            pumpingRate: 'eighth',
            pumpingConfidence: 0.7,
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('href="#section-meas-synthesis"');
    expect(html).toContain('id="section-meas-synthesis"');
    expect(html).toContain('Sidechain / Pumping');
    expect(html).toContain('Pumping Strength');
  });

  it('renders chroma section and nav link when 12-bin chroma data is present', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          spectralDetail: {
            spectralCentroidMean: 1800,
            spectralRolloffMean: 5400,
            mfcc: [],
            chroma: [0.95, 0.2, 0.7, 0.1, 0.3, 0.6, 0.2, 0.4, 0.1, 0.2, 0.1, 0.3],
            barkBands: Array.from({ length: 24 }, (_, i) => -22 + i * 0.3),
            erbBands: Array.from({ length: 40 }, (_, i) => -20 + i * 0.2),
            spectralContrast: [],
            spectralValley: [],
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('href="#section-meas-spectral"');
    expect(html).toContain('id="section-meas-spectral"');
    expect(html).toContain('Chroma (12 pitches)');
  });
});

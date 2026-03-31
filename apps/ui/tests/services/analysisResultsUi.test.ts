import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { AnalysisResults, toggleOpenKeySet } from '../../src/components/AnalysisResults';
import { MIDI_DOWNLOAD_FILE_NAME } from '../../src/components/SessionMusicianPanel';
import { MeasurementResult, Phase2Result, StemSummaryResult, TranscriptionDetail } from '../../src/types';

const buildStepPattern = (
  bars: number,
  primarySteps: number[],
  primaryValue: number,
  secondaryValue = 0,
): number[] =>
  Array.from({ length: bars * 16 }, (_, index) => {
    const stepInBar = index % 16;
    if (primarySteps.includes(stepInBar)) return primaryValue;
    return secondaryValue;
  });

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
    lowMids: 0.0,
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

const phase2V2: Phase2Result = {
  ...basePhase2,
  projectSetup: {
    tempoBpm: 126,
    timeSignature: '4/4',
    sampleRate: 48000,
    bitDepth: 24,
    headroomTarget: '-6 dB',
    sessionGoal: 'Rebuild the measured club energy with a tight sub lane and restrained width on the low end.',
  },
  trackLayout: [
    {
      order: 1,
      name: 'Drum Group',
      type: 'GROUP',
      purpose: 'Keep kick, clap, and hats under one timing-focused bus.',
      grounding: {
        phase1Fields: ['grooveDetail.kickSwing', 'spectralBalance.highs'],
        segmentIndexes: [1, 2],
      },
    },
    {
      order: 2,
      name: 'Bass Group',
      type: 'GROUP',
      purpose: 'Keep the sub and bass harmonics under one sidechain target.',
      grounding: {
        phase1Fields: ['spectralBalance.subBass', 'key'],
      },
    },
  ],
  routingBlueprint: {
    sidechainSource: 'Kick',
    sidechainTargets: ['Bass Group'],
    returns: [
      {
        name: 'Return A',
        purpose: 'Short top-end reverb for hats and vocal cuts.',
        sendSources: ['Drum Group'],
        deviceFocus: 'Hybrid Reverb',
        levelGuidance: '-18 dB baseline send',
      },
    ],
    notes: ['Keep the sub path dry and mono.'],
  },
  warpGuide: {
    fullTrack: {
      warpMode: 'Complex Pro',
      settings: 'Formants 100, Envelope 128',
      reason: 'Use this for the reference bounce so the full mix keeps its vocal and top-end detail.',
    },
    drums: {
      warpMode: 'Beats',
      settings: 'Preserve Transients',
      reason: 'The measured transient profile favors a transient-safe warp mode.',
    },
    bass: {
      warpMode: 'Tones',
      reason: 'Bass sustain reads more naturally with a tonal warp mode.',
    },
    melodic: {
      warpMode: 'Complex',
      reason: 'The melodic layers need harmonic stability more than transient sharpness.',
    },
    rationale: 'Assign warp modes by source type so clip prep stays predictable in Live.',
  },
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
        sceneName: 'INTRO SCENE',
        abletonAction: 'Launch the intro scene with filtered drums only.',
        automationFocus: 'Open the low-pass filter over the last 4 bars.',
      },
      {
        index: 2,
        startTime: 30,
        endTime: 75,
        lufs: -7.0,
        description: 'Drop: dense full-range impact.',
        sceneName: 'DROP SCENE',
        abletonAction: 'Trigger the bass and lead clips together.',
        automationFocus: 'Push the return send up on the transition into the drop.',
      },
    ],
    noveltyNotes: 'Novel shifts at 14.0s and 63.5s align with transitions.',
  },
  mixAndMasterChain: [
    {
      order: 1,
      device: 'Drum Buss',
      deviceFamily: 'NATIVE',
      trackContext: 'Drum Group',
      workflowStage: 'MIX',
      parameter: 'Drive',
      value: '5 dB',
      reason: 'Adds punch to drums.',
    },
    {
      order: 2,
      device: 'EQ Eight',
      deviceFamily: 'NATIVE',
      trackContext: 'Bass Group',
      workflowStage: 'MIX',
      parameter: 'Low Cut',
      value: '30 Hz',
      reason: 'Removes rumble from bass bus.',
    },
    {
      order: 3,
      device: 'Auto Filter',
      deviceFamily: 'NATIVE',
      trackContext: 'Return:Return A',
      workflowStage: 'ARRANGEMENT',
      parameter: 'High Shelf',
      value: '+2.0 dB @ 10 kHz',
      reason: 'Adds sparkle to hi-hats and vocal chops in the top end.',
    },
  ],
  secretSauce: {
    title: 'Punch Layering',
    explanation: 'Layered transient enhancement.',
    implementationSteps: ['Legacy fallback step'],
    workflowSteps: [
      {
        step: 1,
        trackContext: 'Drum Group',
        device: 'Glue Compressor',
        parameter: 'Attack',
        value: '3 ms',
        instruction: 'Set light glue before the build opens up.',
        measurementJustification: 'The measured crest factor supports a controlled transient shape.',
      },
    ],
  },
  abletonRecommendations: [
    {
      device: 'Operator',
      deviceFamily: 'NATIVE',
      trackContext: 'Bass Group',
      workflowStage: 'SOUND_DESIGN',
      category: 'SYNTHESIS',
      parameter: 'Coarse',
      value: '1.00',
      reason: 'Matches tonal center.',
      advancedTip: 'Modulate coarse slowly.',
    },
  ],
};

const baseStemSummary: StemSummaryResult = {
  summary: 'Bass stem: Bass pulses anchor the groove. Musical stem: Upper motion stays approximate.',
  stems: [
    {
      stem: 'bass',
      label: 'Bass stem',
      summary: 'Bass pulses anchor the groove.',
      bars: [
        {
          barStart: 1,
          barEnd: 2,
          startTime: 0,
          endTime: 3.75,
          noteHypotheses: ['C3 pedal'],
          scaleDegreeHypotheses: ['1'],
          rhythmicPattern: 'Short off-beat bass pulses.',
          uncertaintyLevel: 'LOW',
          uncertaintyReason: 'Pitch/note translation and measured downbeats agree.',
        },
      ],
      globalPatterns: {
        bassRole: 'Anchors the groove in the low register.',
        melodicRole: 'Leaves space for the upper material.',
        pumpingOrModulation: 'Measured pumping suggests compressor-led movement.',
      },
      uncertaintyFlags: ['Upper melodic detail is approximate.'],
    },
    {
      stem: 'other',
      label: 'Musical stem',
      summary: 'Upper motion stays approximate.',
      bars: [
        {
          barStart: 1,
          barEnd: 2,
          startTime: 0,
          endTime: 3.75,
          noteHypotheses: ['unclear lead tone'],
          scaleDegreeHypotheses: [],
          rhythmicPattern: 'Loose syncopated upper accents.',
          uncertaintyLevel: 'HIGH',
          uncertaintyReason: 'Dense harmonic overlap reduces note certainty.',
        },
      ],
      globalPatterns: {
        bassRole: 'Not a bass layer.',
        melodicRole: 'Sparse upper-register punctuation.',
        pumpingOrModulation: 'Subtle movement follows the measured pump.',
      },
      uncertaintyFlags: ['Dense harmonic overlap reduces note certainty.'],
    },
  ],
  uncertaintyFlags: ['Upper melodic detail is approximate.'],
};

const phase2V2WithAudioObservations: Phase2Result = {
  ...phase2V2,
  audioObservations: {
    soundDesignFingerprint:
      'By ear the bass feels FM-leaning and tightly enveloped, while the top layers read as filtered synthetic textures rather than open acoustic material.',
    elementCharacter: [
      {
        element: 'Kick',
        description:
          'The kick has a clipped front click and a short sub tail, so it feels designed for punch rather than long sustain.',
      },
      {
        element: 'Lead',
        description:
          'The lead sounds bright but controlled, with the movement coming from filter motion more than from a wet delay wash.',
      },
    ],
    productionSignatures: [
      'Short gated reverb feel on percussion accents.',
      'Pitched transition delays at scene changes.',
    ],
    mixContext:
      'The mix feels intentionally club-forward by ear, with the sub lane pushing first and the ambience tucked behind the groove.',
  },
};

const basePitchNote: TranscriptionDetail = {
  transcriptionMethod: 'torchcrepe-viterbi',
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

  it('renders accented top summary cards and splits measured character chips into separate badges', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          genreDetail: {
            genre: 'tech house',
            confidence: 0.86,
            secondaryGenre: 'techno',
            genreFamily: 'house',
            topScores: [
              { genre: 'tech house', score: 0.86 },
              { genre: 'techno', score: 0.74 },
            ],
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect((html.match(/border-l-2 border-accent/g) ?? []).length).toBeGreaterThanOrEqual(4);
    expect(html).toContain('>HOUSE<');
    expect(html).toContain('>TECHNO<');
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

  it('renders stem summary cards next to Session Musician with plain-language labels', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults as React.ComponentType<Record<string, unknown>>, {
        phase1: {
          ...baseMeasurement,
          transcriptionDetail: basePitchNote,
        },
        phase2: basePhase2,
        stemSummary: baseStemSummary,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('Draft notes for MIDI cleanup');
    expect(html).toContain('AI stem summary for musical understanding');
    expect(html).toContain('Bass stem');
    expect(html).toContain('Musical stem');
    expect(html).toContain('Upper melodic detail is approximate.');
  });

  it('renders v2-only Live session setup sections when interpretation.v2 is active', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults as React.ComponentType<Record<string, unknown>>, {
        phase1: baseMeasurement,
        phase2: phase2V2,
        phase2SchemaVersion: 'interpretation.v2',
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('Project Setup');
    expect(html).toContain('Track Layout');
    expect(html).toContain('Routing Blueprint');
    expect(html).toContain('Warp Guide');
    expect(html).toContain('48000 Hz');
    expect(html).toContain('Drum Group');
    expect(html).toContain('Return A');
    expect(html).toContain('Complex Pro');
  });

  it('keeps v2-only Live session setup sections hidden when interpretation.v1 is active', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults as React.ComponentType<Record<string, unknown>>, {
        phase1: baseMeasurement,
        phase2: phase2V2,
        phase2SchemaVersion: 'interpretation.v1',
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).not.toContain('Project Setup');
    expect(html).not.toContain('Track Layout');
    expect(html).not.toContain('Routing Blueprint');
    expect(html).not.toContain('Warp Guide');
  });

  it('renders interpretation validation warnings as a caution banner instead of hiding the result', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults as React.ComponentType<Record<string, unknown>>, {
        phase1: baseMeasurement,
        phase2: phase2V2,
        phase2SchemaVersion: 'interpretation.v2',
        phase2ValidationWarnings: [
          {
            code: 'UNKNOWN_PARAMETER',
            path: 'abletonRecommendations[0].parameter',
            message: 'Parameter mismatch surfaced as a caution.',
          },
        ],
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('Interpretation Caution');
    expect(html).toContain('Parameter mismatch surfaced as a caution.');
    expect(html).toContain('UNKNOWN_PARAMETER');
    expect(html).toContain('abletonRecommendations[0].parameter');
    expect(html).toContain('Track Character');
  });

  it('renders v2 arrangement actions, device workflow metadata, and prefers structured secret sauce steps', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults as React.ComponentType<Record<string, unknown>>, {
        phase1: baseMeasurement,
        phase2: phase2V2,
        phase2SchemaVersion: 'interpretation.v2',
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('Scene');
    expect(html).toContain('INTRO SCENE');
    expect(html).toContain('Ableton Action');
    expect(html).toContain('Launch the intro scene with filtered drums only.');
    expect(html).toContain('Automation Focus');
    expect(html).toContain('Open the low-pass filter over the last 4 bars.');
    expect(html).toContain('NATIVE');
    expect(html).toContain('Drum Group');
    expect(html).toContain('MIX');
    expect(html).toContain('SOUND_DESIGN');
    expect(html).toContain('Glue Compressor');
    expect(html).toContain('Attack');
    expect(html).toContain('3 ms');
    expect(html).toContain('The measured crest factor supports a controlled transient shape.');
    expect(html).not.toContain('Legacy fallback step');
  });

  it('renders the perceptual audio observations panel when present', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults as React.ComponentType<Record<string, unknown>>, {
        phase1: baseMeasurement,
        phase2: phase2V2WithAudioObservations,
        phase2SchemaVersion: 'interpretation.v2',
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('Audio Observations');
    expect(html).toContain('Perceptual / Audio-Derived');
    expect(html).toContain('FM-leaning');
    expect(html).toContain('Kick');
    expect(html).toContain('Short gated reverb feel on percussion accents.');
    expect(html).toContain('The mix feels intentionally club-forward by ear');
  });

  it('silently omits the perceptual audio observations panel when absent', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults as React.ComponentType<Record<string, unknown>>, {
        phase1: baseMeasurement,
        phase2: phase2V2,
        phase2SchemaVersion: 'interpretation.v2',
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).not.toContain('Audio Observations');
    expect(html).not.toContain('Perceptual / Audio-Derived');
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

  it('shows the chord low-confidence warning at the inclusive 0.50 threshold', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          chordDetail: {
            chordStrength: 0.5,
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
            chordStrength: 0.51,
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).not.toContain('title="Low confidence — treat this as approximate."');
  });

  it('renders danceability metrics in the rhythm section when backend danceability data is present', () => {
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

    expect(html).toContain('Rhythm &amp; Groove');
    expect(html).toContain('1.24');
    expect(html).toContain('DFA (Rhythmic Complexity)');
    expect(html).toContain('0.870');
  });

  it('renders the DSP-grounded sequencer with multi-bar numbering and no prose summary', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          timeSignatureSource: 'assumed_four_four',
          timeSignatureConfidence: 0,
          grooveDetail: {
            kickSwing: 0.47,
            hihatSwing: 0.46,
            kickAccent: [1.0, 0.2, 0.9, 0.1],
            hihatAccent: [0.2, 0.8, 0.6, 1.0],
          },
          beatsLoudness: {
            kickDominantRatio: 0.62,
            midDominantRatio: 0.18,
            highDominantRatio: 0.2,
            patternBeatsPerBar: 3,
            lowBandAccentPattern: [1.0, 0.24, 0.82],
            midBandAccentPattern: [0.22, 1.0, 0.34],
            highBandAccentPattern: [0.3, 0.88, 1.0],
            overallAccentPattern: [1.0, 0.55, 0.92],
            accentPattern: [1.0, 0.55, 0.92],
            meanBeatLoudness: 0.42,
            beatLoudnessVariation: 0.83,
            beatCount: 362,
          },
          rhythmTimeline: {
            beatsPerBar: 4,
            stepsPerBeat: 4,
            availableBars: 16,
            selectionMethod: 'representative_dsp_window',
            windows: [
              {
                bars: 8,
                startBar: 5,
                endBar: 12,
                lowBandSteps: buildStepPattern(8, [0, 8], 1.0),
                midBandSteps: buildStepPattern(8, [4, 12], 0.72),
                highBandSteps: buildStepPattern(8, [0, 2, 4, 6, 8, 10, 12, 14], 0.38, 0.14),
                overallSteps: buildStepPattern(8, [0, 4, 8, 12], 0.92, 0.2),
              },
              {
                bars: 16,
                startBar: 1,
                endBar: 16,
                lowBandSteps: buildStepPattern(16, [0, 8], 1.0),
                midBandSteps: buildStepPattern(16, [4, 12], 0.72),
                highBandSteps: buildStepPattern(16, [0, 2, 4, 6, 8, 10, 12, 14], 0.38, 0.14),
                overallSteps: buildStepPattern(16, [0, 4, 8, 12], 0.92, 0.2),
              },
            ],
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('Rhythm Grid');
    expect(html).toContain('LOW BAND');
    expect(html).toContain('MID BAND');
    expect(html).toContain('HIGH BAND');
    expect(html).toContain('OVERALL ACCENT');
    expect(html).toContain('8 BAR');
    expect(html).toContain('16 BAR');
    expect(html).toContain('DSP band-energy lanes. Frequency-band proxies, not isolated stems.');
    expect(html).toContain('>5<');
    expect(html).toContain('>12<');
    expect(html).not.toContain('Kick-led groove');
    expect(html).not.toContain('Clap / Snare');
    expect(html).not.toContain('HH / Shaker');
    expect(html).not.toContain('>grid<');
    expect(html).not.toContain('>energy<');
  });

  it('renders a mode-aware fallback when dynamics and texture metrics are unavailable for a run', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          dynamicCharacter: null,
          textureCharacter: null,
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
        measurementAvailability: {
          analysisMode: 'standard',
          hasRunContext: true,
        },
      }),
    );

    expect(html).toContain('Dynamics &amp; Texture');
    expect(html).toContain('Measurements not included in this run');
    expect(html).toContain('This standard run completed without dynamics or texture detail.');
    expect(html).toContain('older backend or partial measurement output');
    expect(html).not.toContain('Requires full analysis mode');
  });

  it('renders separated dynamics and texture metrics', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          dynamicCharacter: {
            dynamicComplexity: 3.052,
            loudnessDb: -14.9342,
            loudnessVariation: -14.9342,
            spectralFlatness: 0.0631,
            logAttackTime: -3.9299,
            attackTimeStdDev: 0.0476,
          },
          textureCharacter: {
            textureScore: 0.704,
            lowBandFlatness: 0.6515,
            midBandFlatness: 0.6987,
            highBandFlatness: 0.7131,
            inharmonicity: 0.1838,
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
        measurementAvailability: {
          analysisMode: 'full',
          hasRunContext: true,
        },
      }),
    );

    expect(html).toContain('Dynamics &amp; Texture');
    expect(html).toContain('Estimated Loudness');
    expect(html).toContain('Texture Score');
    expect(html).not.toContain('Dynamic Character');
    expect(html).not.toContain('Measurements not included in this run');
  });

  it('renders dynamics plus a texture fallback when texture metrics are missing', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          dynamicCharacter: {
            dynamicComplexity: 3.052,
            loudnessDb: -14.9342,
            loudnessVariation: -14.9342,
            spectralFlatness: 0.0631,
            logAttackTime: -3.9299,
            attackTimeStdDev: 0.0476,
          },
          textureCharacter: null,
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
        measurementAvailability: {
          analysisMode: 'full',
          hasRunContext: true,
        },
      }),
    );

    expect(html).toContain('Dynamics');
    expect(html).toContain('Estimated Loudness');
    expect(html).toContain('Texture unavailable');
    expect(html).toContain('This full run did not include texture measurements.');
    expect(html).not.toContain('Measurements not included in this run');
  });

  it('renders texture plus a dynamics fallback when dynamics metrics are missing', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          dynamicCharacter: null,
          textureCharacter: {
            textureScore: 0.704,
            lowBandFlatness: 0.6515,
            midBandFlatness: 0.6987,
            highBandFlatness: 0.7131,
            inharmonicity: 0.1838,
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
        measurementAvailability: {
          analysisMode: 'standard',
          hasRunContext: true,
        },
      }),
    );

    expect(html).toContain('Texture');
    expect(html).toContain('Texture Score');
    expect(html).toContain('Dynamics unavailable');
    expect(html).toContain('This standard run did not include dynamics measurements.');
    expect(html).not.toContain('Measurements not included in this run');
  });

  it('renders a generic fallback when no run context exists', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          dynamicCharacter: null,
          textureCharacter: null,
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
        measurementAvailability: {
          hasRunContext: false,
        },
      }),
    );

    expect(html).toContain('Measurements unavailable');
    expect(html).toContain('This payload does not include dynamics or texture detail.');
    expect(html).not.toContain('Requires full analysis mode');
  });

  it('labels stereo correlation bars from anti-phase to mono', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          stereoDetail: {
            stereoWidth: 0.69,
            stereoCorrelation: 0.84,
            subBassCorrelation: 0.92,
            subBassMono: true,
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('anti-phase');
    expect(html).toContain('mono');
  });

  it('uses normalized midi download filename', () => {
    expect(MIDI_DOWNLOAD_FILE_NAME).toBe('track-analysis.mid');
  });

  it('renders pitch/note unavailable state when melodyDetail is missing', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: baseMeasurement,
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('PITCH &amp; MELODY UNAVAILABLE');
    expect(html).toContain('Run with pitch/note translation enabled, or ensure melodyDetail is present in the DSP payload for a melody guide');
  });

  it('shows the pitch/note toggle state by default when both sources are available', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          transcriptionDetail: basePitchNote,
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

    expect(html).toContain('PITCH/NOTE');
    expect(html).toContain('MELODY');
    expect(html).toContain('TORCHCREPE pitch detection');
    expect(html).toContain('Range: C3 - G4');
    expect(html).toContain('Confidence: 83%');
    expect(html.match(/Range: C3 - G4/g)?.length ?? 0).toBe(1);
    expect(html.match(/Confidence: 83%/g)?.length ?? 0).toBe(1);
    expect(html).toContain('2 / 2 NOTES');
    expect(html).toContain('CONFIDENCE');
    expect(html).toContain('20%');
    expect(html).toContain('PITCH/NOTE: TORCHCREPE');
    expect(html).toContain('STEM-AWARE');
    expect(html).toContain('Adjust confidence threshold to filter noise before export.');
    expect(html).not.toContain('PITCH &amp; MELODY UNAVAILABLE');
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

    expect(html).not.toContain('PITCH/NOTE: TORCHCREPE');
    expect(html).not.toContain('TORCHCREPE pitch detection');
    expect(html).toContain('MELODY GUIDE: ESSENTIA');
    expect(html).toContain('Essentia melody guide.');
  });

  it('renders full-mix provenance when transcription did not use Demucs stems', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          transcriptionDetail: {
          transcriptionMethod: 'torchcrepe-viterbi',
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
    expect(html).toContain('href="#section-meas-mixdoctor"');
    expect(html).toContain('href="#section-meas-spectral"');
    expect(html).toContain('href="#section-arrangement"');
    expect(html).toContain('href="#section-session"');
    expect(html).toContain('href="#section-sonic-elements"');
    expect(html).toContain('href="#section-mix-chain"');
    expect(html).toContain('href="#section-patches"');
    expect(html).toContain('id="section-meas-mixdoctor"');
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

  it('renders an effects field panel in rhythm section when gating data is present', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          rhythmDetail: {
            onsetRate: 2.4,
            beatGrid: [],
            downbeats: [],
            beatPositions: [],
            grooveAmount: 0.22,
            tempoStability: 0.94,
            phraseGrid: {
              phrases4Bar: [0, 4, 8, 12],
              phrases8Bar: [0, 8],
              phrases16Bar: [0],
              totalBars: 16,
            },
          },
          sidechainDetail: {
            pumpingStrength: 0.61,
            pumpingRegularity: 0.78,
            pumpingRate: 'eighth',
            pumpingConfidence: 0.83,
            envelopeShape: [0.9, 0.5, 0.4, 0.6, 1, 0.55, 0.5, 0.48, 0.47, 0.44, 0.43, 0.45, 1, 0.58, 0.42, 0.62],
          },
          effectsDetail: {
            gatingDetected: true,
            gatingRate: 8,
            gatingRegularity: 0.67,
            gatingEventCount: 12,
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('Effects Field');
    expect(html).toContain('Gate Events');
    expect(html).toContain('Gate Regularity');
    expect(html).toContain('Phrase Structure');
  });

  it('renders pump matrix fallback in rhythm section when no gating effect is present', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          sidechainDetail: {
            pumpingStrength: 0.31,
            pumpingRegularity: 0.4,
            pumpingRate: 'eighth',
            pumpingConfidence: 0.7,
            envelopeShape: [0.8, 0.6, 0.55, 0.72, 0.92, 0.58, 0.54, 0.6, 0.85, 0.63, 0.52, 0.5, 0.79, 0.62, 0.58, 0.69],
          },
          effectsDetail: {
            gatingDetected: false,
          },
        },
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('Pump Matrix');
    expect(html).toContain('Pump Confidence');
    expect(html).not.toContain('Effects Field');
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

  it('surfaces track character, assumed meter state, truthful tempo score, authoritative total bars, and segment keys', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: {
          ...baseMeasurement,
          bpmConfidence: 1.88,
          bpmSource: 'rhythm_extractor_confirmed',
          timeSignatureSource: 'assumed_four_four',
          timeSignatureConfidence: 0,
          durationSeconds: 210.6,
          rhythmDetail: {
            onsetRate: 2.4,
            beatGrid: [],
            downbeats: [],
            beatPositions: [],
            grooveAmount: 0.22,
            phraseGrid: {
              phrases4Bar: [0, 4, 8, 12],
              phrases8Bar: [0, 8],
              phrases16Bar: [0],
              totalBars: 257,
              totalPhrases8Bar: 32,
            },
          },
          segmentKey: [{ segmentIndex: 0, key: 'C Major (Bridge)', keyConfidence: 0.62 }],
        },
        phase2: {
          ...basePhase2,
          trackCharacter: 'Measured summary with explicit genre and dynamic language.',
        },
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('Track Character');
    expect(html).toContain('Measured summary with explicit genre and dynamic language.');
    expect(html).toContain('ASSUMED');
    expect(html).toContain('SCORE 1.88');
    expect(html).toContain('rhythm extractor confirmed');
    expect(html).not.toContain('CONF 188%');
    expect(html).toContain('257 BARS');
    expect(html).not.toContain('110 BARS');
    expect(html).toContain('C Major (Bridge)');
    expect(html).toMatch(/<td[^>]*>0<\/td>/);
  });
});

/**
 * Canonical full Phase 1 payload fixture — the frontend's executable mirror of
 * the backend contract, shared by `tests/services/backendPhase1Client.test.ts`
 * and the cross-boundary gate in `tests/services/phase1ContractParity.test.ts`.
 *
 * Shape notes:
 * - `phase1EnvelopeFixture` is **envelope-shaped**: what the frontend parser
 *   actually receives AFTER `_build_phase1` in apps/backend/server_phase1.py
 *   normalized the raw analyze.py output (top-level stereoWidth/stereoCorrelation
 *   hoisted from stereoDetail; spectralDetail keys use the renamed `*Mean` forms).
 * - Every top-level key the backend golden snapshot records
 *   (apps/backend/tests/fixtures/golden/phase1_default.json `topLevelKeys`) must
 *   be present here with a representative NON-NULL value — the parity test's
 *   Gate A enforces this, so the no-silent-drop walk (Gate B) exercises every
 *   parser branch.
 *
 * Validity invariants (Gate B walks every non-null path through the REAL parser
 * and asserts survival, so the fixture must not trip the parser's sanitizers):
 * - all numbers finite, all strings non-empty;
 * - melody/transcription note entries valid (`duration > 0`, `onset >= 0`) and
 *   pre-sorted by onset (the parser filters and re-sorts);
 * - `dominantNotes` at most 5 unique values (parser dedupes + slices to 5);
 * - `beatsLoudness` accent arrays exactly `patternBeatsPerBar` long, `accentPattern`
 *   at most 4 (parser slices/pads to length);
 * - `rhythmTimeline` step arrays exactly `bars * beatsPerBar * stepsPerBeat` long;
 * - `chordTimeline` entries sorted by startSec with valid label + confidence.
 */

export const buildStepPattern = (
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

const transientBand = (
  onsetRatePerSecond: number,
  meanOnsetStrength: number,
  peakOnsetStrength: number,
  eventCount: number,
) => ({ onsetRatePerSecond, meanOnsetStrength, peakOnsetStrength, eventCount });

export const phase1EnvelopeFixture = {
  phase1Version: 'phase1.v2',
  fundamentalsQuality: {
    schemaVersion: 'fundamentals-quality.v1',
    targetProfile: 'electronic_ableton_v1',
    analysisMode: 'full',
    localOnly: true,
    llmExcluded: true,
    overallStatus: 'ambiguous',
    domains: {
      tempo: {
        status: 'authoritative',
        plainEnglish: 'Tempo was measured locally.',
        source: 'rhythm_extractor_confirmed',
        confidence: 0.98,
        evidence: {
          bpm: 128,
          bpmPercival: 127.5,
          bpmAgreement: true,
          bpmDoubletime: false,
          bpmRawOriginal: 128,
        },
      },
      beatGrid: {
        status: 'authoritative',
        plainEnglish: 'Beat grid was derived locally from the measured tempo and beat tracker.',
        source: 'rhythm_extractor',
        confidence: 0.98,
        evidence: { beatCount: 256, firstBeatSec: 0, lastBeatSec: 183.75 },
      },
      downbeats: {
        status: 'ambiguous',
        plainEnglish: 'The beat grid is usable, but exact bar starts are uncertain.',
        source: 'kick_accent',
        confidence: 0.36,
        evidence: { downbeatCount: 64 },
      },
      meter: {
        status: 'ambiguous',
        plainEnglish: 'Meter is a local working assumption, not a confirmed reading.',
        source: 'assumed_four_four',
        confidence: 0,
        evidence: { timeSignature: '4/4' },
      },
      key: {
        status: 'authoritative',
        plainEnglish: 'Key was measured locally.',
        source: 'edma',
        confidence: 0.91,
        evidence: { key: 'A minor', tuningFrequency: 440.12, tuningCents: 0.05 },
      },
      chords: {
        status: 'ambiguous',
        plainEnglish: 'Chord labels are local estimates.',
        source: 'librosa_viterbi',
        confidence: 0.54,
        evidence: {
          chordStrength: 0.54,
          chordTimelineAgreement: false,
          chordChangeCount: 3,
          dominantChords: ['Am', 'F', 'G'],
        },
      },
      percussion: {
        status: 'authoritative',
        plainEnglish: 'Percussion events were measured locally.',
        source: 'local_band_and_stem_detectors',
        confidence: 0.7,
        evidence: {
          kickCount: 256,
          kickFundamentalHz: 55,
          snareHitCount: 64,
          hihatHitCount: 128,
        },
      },
      transcription: {
        status: 'authoritative',
        plainEnglish: 'Monophonic notes were translated locally from stem-aware pitch tracking.',
        source: 'torchcrepe-viterbi',
        confidence: 0.83,
        evidence: {
          noteCount: 2,
          fullMixFallback: false,
          perStemAverageConfidence: { bass: 0.92, other: 0.74 },
        },
      },
    },
  },
  bpm: 128,
  bpmConfidence: 0.98,
  bpmPercival: 127.5,
  bpmAgreement: true,
  key: 'A minor',
  keyConfidence: 0.91,
  keyProfile: 'edma',
  tuningFrequency: 440.12,
  tuningCents: 0.05,
  timeSignature: '4/4',
  timeSignatureSource: 'assumed_four_four',
  timeSignatureConfidence: 0,
  durationSeconds: 184.2,
  sampleRate: 44100,
  lufsIntegrated: -8.4,
  lufsRange: 3.1,
  lufsMomentaryMax: -3.2,
  lufsShortTermMax: -4.8,
  lufsCurve: {
    shortTerm: [
      { t: 0.0, lufs: -12.4 },
      { t: 3.0, lufs: -9.1 },
      { t: 6.0, lufs: -8.2 },
    ],
    momentary: [
      { t: 0.0, lufs: -11.8 },
      { t: 0.4, lufs: -9.6 },
      { t: 0.8, lufs: -7.9 },
    ],
  },
  truePeak: -0.5,
  plr: 7.9,
  crestFactor: 8.6,
  dynamicSpread: 0.42,
  dynamicCharacter: {
    dynamicComplexity: 0.5,
    loudnessDb: -14.2,
    loudnessVariation: -14.2,
    spectralFlatness: 0.2,
    logAttackTime: -0.8,
    attackTimeStdDev: 0.15,
  },
  textureCharacter: {
    textureScore: 0.68,
    lowBandFlatness: 0.51,
    midBandFlatness: 0.72,
    highBandFlatness: 0.83,
    inharmonicity: 0.19,
  },
  stereoWidth: 0.75,
  stereoCorrelation: 0.82,
  stereoDetail: {
    stereoWidth: 0.75,
    stereoCorrelation: 0.82,
    subBassCorrelation: 0.97,
    subBassMono: true,
    correlationCurve: [
      { t: 0.0, full: 0.81, sub: 0.98 },
      { t: 1.0, full: 0.74, sub: 0.96 },
    ],
    bandCorrelations: {
      subBass: 0.98,
      lowBass: 0.91,
      lowMids: 0.72,
      mids: 0.61,
      upperMids: 0.55,
      highs: 0.49,
      brilliance: 0.4,
    },
  },
  monoCompatible: true,
  spectralBalance: {
    subBass: -1.2,
    lowBass: 0.8,
    lowMids: 0.0,
    mids: -0.4,
    upperMids: 0.2,
    highs: 1.1,
    brilliance: 0.5,
  },
  spectralBalanceTimeSeries: [
    { t: 0.0, subBass: -2.1, lowBass: 0.4, lowMids: -0.2, mids: -0.6, upperMids: 0.1, highs: 0.9, brilliance: 0.2 },
    { t: 1.0, subBass: -1.4, lowBass: 0.7, lowMids: 0.1, mids: -0.3, upperMids: 0.3, highs: 1.2, brilliance: 0.6 },
  ],
  spectralDetail: {
    spectralCentroidMean: 1820.5,
    spectralRolloffMean: 6450.2,
    spectralBandwidthMean: 2310.8,
    spectralFlatnessMean: 0.21,
    mfcc: [-512.4, 110.2, -14.7, 22.1],
    chroma: [0.42, 0.11, 0.08, 0.31],
    barkBands: [-32.1, -18.4, -12.9, -20.5],
    erbBands: [-30.6, -17.2, -11.8, -19.9],
    spectralContrast: [18.2, 14.6, 12.1],
    spectralValley: [-44.5, -38.2, -35.7],
  },
  stemAnalysis: {
    bass: {
      spectralBalance: {
        subBass: 2.4,
        lowBass: 4.1,
        lowMids: -6.2,
        mids: -18.4,
        upperMids: -32.7,
        highs: -48.1,
        brilliance: -60.3,
      },
      spectralBalanceTimeSeries: [
        { t: 0.0, subBass: 2.0, lowBass: 3.8, lowMids: -6.6, mids: -19.0, upperMids: -33.1, highs: -48.8, brilliance: -61.0 },
      ],
      spectralDetail: {
        spectralCentroidMean: 240.7,
        spectralRolloffMean: 820.4,
        spectralBandwidthMean: 310.2,
        spectralFlatnessMean: 0.08,
        mfcc: [-480.1, 92.4, -8.2],
      },
      lufsIntegrated: -14.6,
      lufsRange: 2.2,
      lufsMomentaryMax: -10.4,
      lufsShortTermMax: -11.8,
      lufsCurve: {
        shortTerm: [{ t: 0.0, lufs: -15.2 }],
        momentary: [{ t: 0.0, lufs: -14.1 }],
      },
      stereoDetail: {
        stereoWidth: 0.05,
        stereoCorrelation: 0.99,
        subBassMono: true,
      },
      truePeak: -6.2,
      crestFactor: 6.1,
      dynamicSpread: 0.31,
      dynamicCharacter: {
        dynamicComplexity: 0.4,
        loudnessDb: -16.8,
        loudnessVariation: -16.8,
        spectralFlatness: 0.1,
        logAttackTime: -1.1,
        attackTimeStdDev: 0.09,
      },
      reverbDetail: {
        rt60: 0.6,
        isWet: false,
        tailEnergyRatio: 0.12,
        measured: true,
        perBandRt60: { low: 0.7, lowMids: 0.5, highMids: 0.3, highs: 0.2 },
        preDelayMs: 8.0,
      },
    },
    drums: {
      spectralBalance: {
        subBass: -4.8,
        lowBass: -1.2,
        lowMids: -3.4,
        mids: -6.8,
        upperMids: -4.1,
        highs: -2.6,
        brilliance: -8.9,
      },
      lufsIntegrated: -12.1,
      stereoDetail: {
        stereoWidth: 0.42,
        stereoCorrelation: 0.71,
        subBassMono: true,
      },
      reverbDetail: {
        rt60: 1.1,
        isWet: true,
        tailEnergyRatio: 0.28,
        measured: true,
        perBandRt60: { low: 1.3, lowMids: 1.0, highMids: 0.7, highs: 0.4 },
        preDelayMs: 18.5,
      },
    },
  },
  transientDensityDetail: {
    subBass: transientBand(2.1, 0.62, 1.4, 384),
    lowBass: transientBand(2.3, 0.58, 1.3, 421),
    lowMids: transientBand(3.8, 0.41, 1.1, 696),
    mids: transientBand(4.6, 0.38, 0.9, 842),
    upperMids: transientBand(5.2, 0.35, 0.8, 951),
    highs: transientBand(7.4, 0.44, 1.2, 1355),
    brilliance: transientBand(6.1, 0.29, 0.7, 1117),
  },
  saturationDetail: {
    clippedSampleCount: 0,
    clippedSamplePercent: 0.0,
    nearClippedSampleCount: 1240,
    nearClippedSamplePercent: 0.008,
    peakRatio95to50: 3.4,
    rmsToPeakRatioDb: -11.2,
    saturationLikely: false,
  },
  snareDetail: {
    hitCount: 184,
    hitsPerSecond: 1.0,
    meanAttackSharpness: 0.34,
    meanBodyEnergyRatio: 0.61,
    meanSnapEnergyRatio: 0.39,
    meanCentroidHz: 980.4,
    meanDecayFrames: 14.2,
    meanDecaySeconds: 0.165,
    bandHz: [120, 2000],
  },
  hihatDetail: {
    hitCount: 736,
    hitsPerSecond: 4.0,
    meanAttackSharpness: 0.52,
    meanBodyEnergyRatio: 0.22,
    meanSnapEnergyRatio: 0.78,
    meanCentroidHz: 6840.7,
    meanDecayFrames: 6.8,
    meanDecaySeconds: 0.079,
    bandHz: [2000, 12000],
  },
  rhythmDetail: {
    onsetRate: 4.2,
    beatGrid: [0.47, 0.94, 1.41, 1.88],
    downbeats: [0.47, 2.35],
    beatPositions: [1, 2, 3, 4],
    downbeatSource: 'kick_accent',
    downbeatConfidence: 0.36,
    grooveAmount: 0.42,
    tempoStability: 0.58,
    phraseGrid: {
      phrases4Bar: [0.47, 7.97],
      phrases8Bar: [0.47, 15.47],
      phrases16Bar: [0.47],
      totalBars: 96,
      totalPhrases8Bar: 12,
    },
    tempoCurve: [
      { t: 0.0, bpm: 128.1 },
      { t: 2.0, bpm: 127.9 },
    ],
  },
  melodyDetail: {
    noteCount: 3,
    notes: [
      { midi: 60, onset: 0.1, duration: 0.25 },
      { midi: 64, onset: 0.4, duration: 0.3 },
      { midi: 67, onset: 0.8, duration: 0.2 },
    ],
    dominantNotes: [60, 64, 67],
    pitchRange: { min: 60, max: 67 },
    pitchConfidence: 0.71,
    midiFile: '/tmp/example.mid',
    sourceSeparated: true,
    vibratoPresent: false,
    vibratoExtent: 0.0,
    vibratoRate: 0.0,
    vibratoConfidence: 0.05,
  },
  transcriptionDetail: {
    transcriptionMethod: 'torchcrepe-viterbi',
    noteCount: 2,
    averageConfidence: 0.83,
    stemSeparationUsed: true,
    fullMixFallback: false,
    stemsTranscribed: ['bass', 'other'],
    perStemAverageConfidence: { bass: 0.92, other: 0.74 },
    dominantPitches: [
      { pitchMidi: 48, pitchName: 'C3', count: 5 },
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
  },
  pitchDetail: {
    method: 'torchcrepe',
    stems: {
      vocals: {
        medianPitchHz: 220.4,
        pitchRangeLowHz: 164.8,
        pitchRangeHighHz: 392.1,
        meanPeriodicity: 0.72,
        voicedFramePercent: 41.6,
        hopLength: 512,
        sampleRate: 44100,
        model: 'tiny',
      },
      other: {
        medianPitchHz: 440.2,
        pitchRangeLowHz: 261.6,
        pitchRangeHighHz: 880.5,
        meanPeriodicity: 0.64,
        voicedFramePercent: 38.2,
        hopLength: 512,
        sampleRate: 44100,
        model: 'tiny',
      },
    },
  },
  grooveDetail: {
    kickSwing: 0.12,
    hihatSwing: 0.31,
    kickAccent: [1.0, 0.4, 0.9, 0.5],
    hihatAccent: [0.2, 0.8, 0.3, 0.7],
    perDrumSwing: {
      kick: 0.12,
      snare: 0.24,
      hihat: 0.31,
    },
  },
  beatsLoudness: {
    kickDominantRatio: 0.45,
    midDominantRatio: 0.35,
    highDominantRatio: 0.20,
    patternBeatsPerBar: 4,
    lowBandAccentPattern: [1.0, 0.3, 0.8, 0.2],
    midBandAccentPattern: [0.2, 1.0, 0.4, 0.3],
    highBandAccentPattern: [0.1, 0.2, 0.6, 1.0],
    overallAccentPattern: [1.0, 0.6, 0.8, 0.5],
    accentPattern: [1.0, 0.6, 0.8, 0.5],
    meanBeatLoudness: 0.32,
    beatLoudnessVariation: 0.18,
    beatCount: 256,
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
  sidechainDetail: {
    pumpingStrength: 0.65,
    pumpingConfidence: 0.31,
    pumpingRegularity: 0.82,
    pumpingRate: 'quarter',
    envelopeShape: [1.0, 0.9, 0.7, 0.5, 0.3, 0.2, 0.15, 0.1, 0.08, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01, 0.005],
    envelopeShape32: Array.from({ length: 32 }, (_, index) => Math.max(0.005, 1.0 - index * 0.032)),
  },
  effectsDetail: {
    gatingDetected: true,
    gatingRate: '16th',
    gatingRegularity: 0.74,
    gatingEventCount: 96,
  },
  synthesisCharacter: {
    inharmonicity: 0.14,
    oddToEvenRatio: 1.62,
    analogLike: true,
  },
  danceability: {
    danceability: 1.24,
    dfa: 0.87,
  },
  structure: {
    segments: [
      { start: 0.0, end: 32.4, index: 0 },
      { start: 32.4, end: 96.8, index: 1 },
    ],
    segmentCount: 2,
    sections: 5,
  },
  arrangementDetail: {
    noveltyCurve: [0.12, 0.18, 0.64, 0.22],
    noveltyPeaks: [
      { time: 32.4, strength: 0.64 },
      { time: 96.8, strength: 0.51 },
    ],
    noveltyMean: 0.21,
    noveltyStdDev: 0.14,
    sectionCount: 5,
  },
  segmentLoudness: [{ segmentIndex: 0, start: 0, end: 32.4, lufs: -8.2, lra: 1.4 }],
  segmentSpectral: [
    {
      segmentIndex: 0,
      barkBands: [-32.1, -18.4, -12.9],
      spectralCentroid: 1820.5,
      spectralRolloff: 6450.2,
      stereoWidth: 0.8,
      stereoCorrelation: 0.9,
    },
  ],
  segmentStereo: [{ segmentIndex: 0, stereoWidth: 0.8, stereoCorrelation: 0.9 }],
  segmentKey: [{ segmentIndex: 0, key: 'A minor', keyConfidence: 0.85 }],
  essentiaFeatures: {
    zeroCrossingRate: 0.12,
    hfc: 0.45,
    spectralComplexity: 0.33,
    dissonance: 0.21,
  },
  chordDetail: {
    chordSequence: ['Am', 'F', 'C', 'G'],
    chordStrength: 0.72,
    progression: ['Am', 'G'],
    dominantChords: ['Am', 'G', 'F', 'C'],
    chordTimeline: [
      { startSec: 0.0, endSec: 4.0, label: 'Am', labelLong: 'A minor', confidence: 0.81 },
      { startSec: 4.0, endSec: 8.0, label: 'F', labelLong: 'F major', confidence: 0.65 },
    ],
    chordChangeCount: 1,
    chordTimelineSource: 'librosa_viterbi',
    chordTimelineAgreement: true,
  },
  perceptual: {
    sharpness: 1.42,
    roughness: 0.087,
  },

  // BPM correction metadata
  bpmDoubletime: false,
  bpmSource: 'rhythm_extractor_confirmed',
  bpmRawOriginal: 128.0,

  // Detectors
  acidDetail: {
    isAcid: false,
    confidence: 0.12,
    resonanceLevel: 0.08,
    centroidOscillationHz: 120.5,
    bassRhythmDensity: 0.45,
  },
  reverbDetail: {
    rt60: 1.2,
    isWet: true,
    tailEnergyRatio: 0.35,
    measured: true,
    perBandRt60: { low: 1.4, lowMids: 1.1, highMids: 0.8, highs: 0.5 },
    preDelayMs: 22.5,
  },
  vocalDetail: {
    hasVocals: false,
    confidence: 0.85,
    vocalEnergyRatio: 0.02,
    formantStrength: 0.05,
    mfccLikelihood: 0.1,
    stemEnergyRatio: 0.12,
    stemOtherCorrelation: 0.41,
  },
  supersawDetail: {
    isSupersaw: false,
    confidence: 0.08,
    voiceCount: 1,
    avgDetuneCents: 2.5,
    spectralComplexity: 0.15,
  },
  bassDetail: {
    averageDecayMs: 45,
    type: 'punchy',
    transientRatio: 0.72,
    fundamentalHz: 55.0,
    transientCount: 128,
    swingPercent: 3.2,
    grooveType: 'straight',
  },
  kickDetail: {
    isDistorted: false,
    thd: 0.08,
    harmonicRatio: 0.35,
    fundamentalHz: 52.0,
    kickCount: 256,
  },
  genreDetail: {
    genre: 'techno',
    confidence: 0.82,
    secondaryGenre: 'tech house',
    genreFamily: 'techno',
    topScores: [
      { genre: 'techno', score: 0.82 },
      { genre: 'tech house', score: 0.65 },
    ],
  },
};

export const validBackendAnalyzeResponse = {
  requestId: 'req_123',
  phase1: phase1EnvelopeFixture,
  diagnostics: {
    backendDurationMs: 1420,
    engineVersion: '0.4.0',
    timings: {
      totalMs: 1560,
      analysisMs: 1420,
      serverOverheadMs: 140,
      flagsUsed: ['--transcribe'],
      fileSizeBytes: 543210,
      fileDurationSeconds: 184.2,
      msPerSecondOfAudio: 7.71,
    },
  },
};

export interface MelodyNote {
  midi: number;
  onset: number;
  duration: number;
}

export interface MelodyPitchRange {
  min: number | null;
  max: number | null;
}

export interface MelodyDetail {
  noteCount: number;
  notes: MelodyNote[];
  dominantNotes: number[];
  pitchRange: MelodyPitchRange;
  pitchConfidence: number;
  midiFile: string | null;
  sourceSeparated: boolean;
  vibratoPresent: boolean;
  vibratoExtent: number;
  vibratoRate: number;
  vibratoConfidence: number;
}

export interface TranscriptionNote {
  pitchMidi: number;
  pitchName: string;
  onsetSeconds: number;
  durationSeconds: number;
  confidence: number;
  stemSource: "bass" | "other" | "full_mix";
}

export interface TranscriptionDetail {
  transcriptionMethod: string;
  noteCount: number;
  averageConfidence: number;
  stemSeparationUsed: boolean;
  fullMixFallback: boolean;
  stemsTranscribed: string[];
  /**
   * Mean confidence per stem source, computed over the post-dedup, post-cap notes.
   * Empty `{}` when `fullMixFallback` is true; otherwise contains one entry per
   * stem with at least one surviving note (e.g. `{"bass": 0.85, "other": 0.32}`).
   * Optional because legacy snapshots and the empty-notes path may omit it.
   */
  perStemAverageConfidence?: Record<string, number>;
  dominantPitches: Array<{
    pitchMidi: number;
    pitchName: string;
    count: number;
  }>;
  pitchRange: {
    minMidi: number | null;
    maxMidi: number | null;
    minName: string | null;
    maxName: string | null;
  };
  notes: TranscriptionNote[];
}

export interface DanceabilityResult {
  danceability: number;
  dfa: number;
}

export interface StereoDetail {
  stereoWidth: number | null;
  stereoCorrelation: number | null;
  subBassCorrelation?: number | null;
  subBassMono?: boolean | null;
}

export interface SpectralDetail {
  spectralCentroidMean?: number | null;
  spectralRolloffMean?: number | null;
  spectralBandwidthMean?: number | null;
  spectralFlatnessMean?: number | null;
  mfcc?: number[] | null;
  chroma?: number[] | null;
  barkBands?: number[] | null;
  erbBands?: number[] | null;
  spectralContrast?: number[] | null;
  spectralValley?: number[] | null;
}

export interface PhraseGrid {
  phrases4Bar: number[];
  phrases8Bar: number[];
  phrases16Bar: number[];
  totalBars: number;
  totalPhrases8Bar: number;
}

export interface RhythmDetail {
  onsetRate: number;
  beatGrid: number[];
  downbeats: number[];
  beatPositions: number[];
  grooveAmount: number;
  tempoStability?: number | null;
  phraseGrid?: PhraseGrid | null;
}

export interface GrooveDetail {
  kickSwing: number;
  hihatSwing: number;
  kickAccent: number[];
  hihatAccent: number[];
}

export interface SidechainDetail {
  pumpingStrength: number;
  pumpingRegularity: number;
  pumpingRate: string | null;
  pumpingConfidence: number;
  envelopeShape?: number[] | null;
}

export interface EffectsDetail {
  gatingDetected?: boolean | null;
  gatingRate?: number | null;
  gatingRegularity?: number | null;
  gatingEventCount?: number | null;
}

export interface SynthesisCharacter {
  inharmonicity?: number | null;
  oddToEvenRatio?: number | null;
  analogLike?: boolean | null;
}

export interface StructureData {
  segments?: unknown[] | null;
  segmentCount?: number | null;
  sections?: number | null;
}

export interface ArrangementDetail {
  noveltyCurve?: number[] | null;
  noveltyPeaks?: number[] | null;
  noveltyMean?: number | null;
  noveltyStdDev?: number | null;
  sectionCount?: number | null;
}

export interface SegmentLoudnessEntry {
  segmentIndex?: number;
  start?: number;
  end?: number;
  lufs?: number | null;
  lra?: number | null;
  value?: number | null;
}

export interface SegmentSpectralEntry {
  segmentIndex: number;
  barkBands?: number[] | null;
  spectralCentroid?: number | null;
  spectralRolloff?: number | null;
  stereoWidth?: number | null;
  stereoCorrelation?: number | null;
}

export interface SegmentStereoEntry {
  segmentIndex: number;
  stereoWidth?: number | null;
  stereoCorrelation?: number | null;
}

export interface SegmentKeyEntry {
  segmentIndex: number;
  key: string | null;
  keyConfidence?: number | null;
}

export interface ChordDetail {
  chordSequence?: string[] | null;
  chordStrength?: number | null;
  progression?: string[] | null;
  dominantChords?: string[] | null;
}

export interface PerceptualDetail {
  sharpness: number;
  roughness: number;
}

export interface EssentiaFeatures {
  zeroCrossingRate?: number | null;
  hfc?: number | null;
  spectralComplexity?: number | null;
  dissonance?: number | null;
}

export interface DynamicCharacter {
  dynamicComplexity: number;
  loudnessDb: number;
  loudnessVariation?: number | null;
  spectralFlatness: number;
  logAttackTime: number;
  attackTimeStdDev: number;
}

export interface TextureCharacter {
  textureScore: number;
  lowBandFlatness: number;
  midBandFlatness: number;
  highBandFlatness: number;
  inharmonicity?: number | null;
}

export interface BeatsLoudness {
  kickDominantRatio: number;
  midDominantRatio: number;
  highDominantRatio: number;
  patternBeatsPerBar: number;
  lowBandAccentPattern: number[];
  midBandAccentPattern: number[];
  highBandAccentPattern: number[];
  overallAccentPattern: number[];
  accentPattern: number[];
  meanBeatLoudness: number;
  beatLoudnessVariation: number;
  beatCount: number;
}

export interface RhythmTimelineWindow {
  bars: number;
  startBar: number;
  endBar: number;
  lowBandSteps: number[];
  midBandSteps: number[];
  highBandSteps: number[];
  overallSteps: number[];
}

export interface RhythmTimeline {
  beatsPerBar: number;
  stepsPerBeat: number;
  availableBars: number;
  selectionMethod: "representative_dsp_window";
  windows: RhythmTimelineWindow[];
}

export interface PitchStemResult {
  medianPitchHz: number | null;
  pitchRangeLowHz: number | null;
  pitchRangeHighHz: number | null;
  meanPeriodicity: number;
  voicedFramePercent: number;
  hopLength: number;
  sampleRate: number;
  model: string;
}

export interface PitchDetail {
  method: string;
  stems: Record<string, PitchStemResult>;
}

export interface AcidDetail {
  isAcid: boolean;
  confidence: number;
  resonanceLevel: number;
  centroidOscillationHz: number;
  bassRhythmDensity: number;
}

export interface ReverbDetail {
  rt60: number | null;
  isWet: boolean;
  tailEnergyRatio: number | null;
  measured: boolean;
}

export interface VocalDetail {
  hasVocals: boolean;
  confidence: number;
  vocalEnergyRatio: number;
  formantStrength: number;
  mfccLikelihood: number;
}

export interface SupersawDetail {
  isSupersaw: boolean;
  confidence: number;
  voiceCount: number;
  avgDetuneCents: number;
  spectralComplexity: number;
}

export interface BassDetail {
  averageDecayMs: number;
  type: "punchy" | "medium" | "rolling" | "sustained";
  transientRatio: number;
  fundamentalHz: number | null;
  transientCount: number;
  swingPercent: number;
  grooveType: string;
}

export interface KickDetail {
  isDistorted: boolean;
  thd: number;
  harmonicRatio: number;
  fundamentalHz: number | null;
  kickCount: number;
}

export interface GenreDetail {
  genre: string;
  confidence: number;
  secondaryGenre: string | null;
  genreFamily: "house" | "techno" | "dnb" | "ambient" | "trance" | "dubstep" | "breaks" | "other";
  topScores: Array<{ genre: string; score: number }>;
}

export interface Phase1Result {
  bpm: number;
  bpmConfidence: number;
  bpmPercival?: number | null;
  bpmAgreement?: boolean | null;
  bpmDoubletime?: boolean | null;
  bpmSource?: string | null;
  bpmRawOriginal?: number | null;
  key: string | null;
  keyConfidence: number;
  keyProfile?: string | null;
  tuningFrequency?: number | null;
  tuningCents?: number | null;
  timeSignature: string;
  timeSignatureSource?: string | null;
  timeSignatureConfidence?: number | null;
  durationSeconds: number;
  sampleRate?: number | null;
  lufsIntegrated: number;
  lufsRange?: number | null;
  lufsMomentaryMax?: number | null;
  lufsShortTermMax?: number | null;
  truePeak: number;
  plr?: number | null;
  crestFactor?: number | null;
  dynamicSpread?: number | null;
  dynamicCharacter?: DynamicCharacter | null;
  textureCharacter?: TextureCharacter | null;
  stereoWidth: number;
  stereoCorrelation: number;
  stereoDetail?: StereoDetail | null;
  monoCompatible?: boolean | null;
  spectralBalance: {
    subBass: number;
    lowBass: number;
    lowMids: number;
    mids: number;
    upperMids: number;
    highs: number;
    brilliance: number;
  };
  spectralDetail?: SpectralDetail | null;
  rhythmDetail?: RhythmDetail | null;
  melodyDetail?: MelodyDetail;
  transcriptionDetail?: TranscriptionDetail | null;
  pitchDetail?: PitchDetail | null;
  grooveDetail?: GrooveDetail | null;
  beatsLoudness?: BeatsLoudness | null;
  rhythmTimeline?: RhythmTimeline | null;
  sidechainDetail?: SidechainDetail | null;
  effectsDetail?: EffectsDetail | null;
  synthesisCharacter?: SynthesisCharacter | null;
  danceability?: DanceabilityResult | null;
  structure?: StructureData | null;
  arrangementDetail?: ArrangementDetail | null;
  segmentLoudness?: SegmentLoudnessEntry[] | null;
  segmentSpectral?: SegmentSpectralEntry[] | null;
  segmentStereo?: SegmentStereoEntry[] | null;
  segmentKey?: SegmentKeyEntry[] | null;
  chordDetail?: ChordDetail | null;
  perceptual?: PerceptualDetail | null;
  essentiaFeatures?: EssentiaFeatures | null;
  acidDetail?: AcidDetail | null;
  reverbDetail?: ReverbDetail | null;
  vocalDetail?: VocalDetail | null;
  supersawDetail?: SupersawDetail | null;
  bassDetail?: BassDetail | null;
  kickDetail?: KickDetail | null;
  genreDetail?: GenreDetail | null;
}

export type MeasurementResult = Omit<Phase1Result, 'transcriptionDetail'>;

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

export type RecommendationCategory =
  | "SYNTHESIS"
  | "DYNAMICS"
  | "EQ"
  | "EFFECTS"
  | "STEREO"
  | "MASTERING"
  | "MIDI"
  | "ROUTING";

export type DeviceFamily = "NATIVE" | "MAX_FOR_LIVE";

export type WorkflowStage =
  | "PROJECT_SETUP"
  | "SOUND_DESIGN"
  | "ARRANGEMENT"
  | "MIX"
  | "MASTER";

export type WarpMode =
  | "Beats"
  | "Tones"
  | "Texture"
  | "Re-Pitch"
  | "Complex"
  | "Complex Pro";

export interface Phase2Grounding {
  phase1Fields: string[];
  segmentIndexes?: number[];
}

export interface Phase2ProjectSetup {
  tempoBpm: number;
  timeSignature: string;
  sampleRate: number;
  bitDepth: number;
  headroomTarget: string;
  sessionGoal: string;
}

export interface Phase2TrackLayoutItem {
  order: number;
  name: string;
  type: string;
  purpose: string;
  grounding: Phase2Grounding;
}

export interface RoutingBlueprintReturn {
  name: string;
  purpose: string;
  sendSources: string[];
  deviceFocus: string;
  levelGuidance: string;
}

export interface RoutingBlueprint {
  sidechainSource?: string | null;
  sidechainTargets: string[];
  returns: RoutingBlueprintReturn[];
  notes: string[];
}

export interface WarpGuideTarget {
  warpMode: WarpMode;
  settings?: string;
  reason: string;
}

export interface Phase2WarpGuide {
  fullTrack: WarpGuideTarget;
  drums: WarpGuideTarget;
  bass: WarpGuideTarget;
  melodic: WarpGuideTarget;
  vocals?: WarpGuideTarget;
  rationale: string;
}

export interface SecretSauceWorkflowStep {
  step: number;
  trackContext: string;
  device: string;
  parameter: string;
  value: string;
  instruction: string;
  measurementJustification: string;
}

export interface AbletonRecommendation {
  device: string;
  deviceFamily?: DeviceFamily;
  trackContext?: string;
  workflowStage?: WorkflowStage;
  category: RecommendationCategory;
  parameter: string;
  value: string;
  reason: string;
  advancedTip?: string;
}

export interface AudioObservationElement {
  element: string;
  description: string;
}

export interface AudioObservations {
  soundDesignFingerprint: string;
  elementCharacter: AudioObservationElement[];
  productionSignatures: string[];
  mixContext: string;
}

export interface Phase2Result {
  trackCharacter: string;
  projectSetup?: Phase2ProjectSetup;
  trackLayout?: Phase2TrackLayoutItem[];
  routingBlueprint?: RoutingBlueprint;
  warpGuide?: Phase2WarpGuide;
  audioObservations?: AudioObservations;
  detectedCharacteristics: {
    name: string;
    confidence: "HIGH" | "MED" | "LOW";
    explanation: string;
  }[];
  arrangementOverview: {
    summary: string;
    segments: Array<{
      index: number;
      startTime: number;
      endTime: number;
      lufs?: number;
      description: string;
      spectralNote?: string;
      sceneName?: string;
      abletonAction?: string;
      automationFocus?: string;
    }>;
    noveltyNotes?: string;
  };
  sonicElements: {
    kick: string;
    bass: string;
    melodicArp: string;
    grooveAndTiming: string;
    effectsAndTexture: string;
    widthAndStereo?: string;
    harmonicContent?: string;
  };
  mixAndMasterChain: Array<{
    order: number;
    device: string;
    deviceFamily?: DeviceFamily;
    trackContext?: string;
    workflowStage?: WorkflowStage;
    parameter: string;
    value: string;
    reason: string;
  }>;
  secretSauce: {
    title: string;
    icon?: string;
    explanation: string;
    implementationSteps: string[];
    workflowSteps?: SecretSauceWorkflowStep[];
  };
  confidenceNotes: {
    field: string;
    value: string;
    reason: string;
  }[];
  abletonRecommendations: AbletonRecommendation[];
}

export interface StemSummaryBar {
  barStart: number;
  barEnd: number;
  startTime: number;
  endTime: number;
  noteHypotheses: string[];
  scaleDegreeHypotheses: string[];
  rhythmicPattern: string;
  uncertaintyLevel: "LOW" | "MED" | "HIGH";
  uncertaintyReason: string;
}

export interface StemSummaryStem {
  stem: 'bass' | 'other';
  label: string;
  summary: string;
  bars: StemSummaryBar[];
  globalPatterns: {
    bassRole: string;
    melodicRole: string;
    pumpingOrModulation: string;
  };
  uncertaintyFlags: string[];
}

export interface StemSummaryResult {
  summary: string;
  stems: StemSummaryStem[];
  uncertaintyFlags: string[];
}

export type InterpretationResult = Phase2Result | StemSummaryResult;

export type InterpretationSchemaVersion = "interpretation.v1" | "interpretation.v2";

export interface InterpretationValidationWarning {
  code?: string;
  path?: string;
  message: string;
  originalValue?: string;
  coercedValue?: string;
  dropReason?: string;
}

export interface BackendTimingDiagnostics {
  totalMs: number;
  analysisMs: number;
  serverOverheadMs: number;
  flagsUsed: string[];
  fileSizeBytes: number;
  fileDurationSeconds: number | null;
  msPerSecondOfAudio: number | null;
}

export interface BackendDiagnostics {
  backendDurationMs: number;
  engineVersion?: string;
  estimatedLowMs?: number;
  estimatedHighMs?: number;
  timeoutSeconds?: number;
  stdoutSnippet?: string;
  stderrSnippet?: string;
  timings?: BackendTimingDiagnostics;
}

export interface BackendAnalyzeResponse {
  requestId: string;
  // COMPAT: non-canonical, do not use in primary flow.
  analysisRunId?: string;
  phase1: Phase1Result;
  diagnostics?: BackendDiagnostics;
}

export type AnalysisStageStatus =
  | 'queued'
  | 'running'
  | 'blocked'
  | 'ready'
  | 'completed'
  | 'failed'
  | 'interrupted'
  | 'not_requested';

export interface AnalysisStageError {
  code: string;
  message: string;
  retryable?: boolean;
  phase?: string;
}

export interface AnalysisRunArtifact {
  artifactId: string;
  filename: string;
  mimeType: string;
  sizeBytes: number;
  contentSha256: string;
}

export interface SpectralArtifactRef {
  artifactId: string;
  kind:
    | 'spectrogram_mel'
    | 'spectrogram_chroma'
    | 'spectrogram_cqt'
    | 'spectrogram_harmonic'
    | 'spectrogram_percussive'
    | 'spectrogram_onset';
  filename: string;
  mimeType: string;
  sizeBytes: number;
}

export interface SpectralArtifacts {
  spectrograms: SpectralArtifactRef[];
  timeSeries: SpectralArtifactRef | null;
  onsetStrength: SpectralArtifactRef | null;
  chromaInteractive: SpectralArtifactRef | null;
}

export interface OnsetStrengthData {
  timePoints: number[];
  onsetStrength: number[];
  sampleRate: number;
  hopLength: number;
  originalFrameCount: number;
  downsampledTo: number;
}

export interface ChromaInteractiveData {
  timePoints: number[];
  pitchClasses: string[];
  chroma: number[][];
  sampleRate: number;
  hopLength: number;
  originalFrameCount: number;
  downsampledTo: number;
}

export interface SpectralTimeSeriesData {
  timePoints: number[];
  spectralCentroid: number[];
  spectralRolloff: number[];
  spectralBandwidth: number[];
  spectralFlatness: number[];
  sampleRate: number;
  hopLength: number;
  originalFrameCount: number;
  downsampledTo: number;
}

export interface AnalysisRunRequestedStages {
  analysisMode: 'full' | 'standard';
  pitchNoteMode: string;
  pitchNoteBackend: string;
  symbolicMode: string;
  symbolicBackend: string;
  interpretationMode: string;
  interpretationProfile: string;
  interpretationModel: string | null;
}

export interface MeasurementAvailabilityContext {
  analysisMode?: 'full' | 'standard';
  hasRunContext: boolean;
}

export interface MeasurementStageSnapshot {
  status: AnalysisStageStatus;
  authoritative: true;
  result: MeasurementResult | null;
  provenance: Record<string, unknown> | null;
  diagnostics: Record<string, unknown> | null;
  error: AnalysisStageError | null;
}

export interface PitchNoteTranslationAttemptSummary {
  attemptId: string;
  backendId: string;
  mode: string;
  status: AnalysisStageStatus;
}

export interface InterpretationAttemptSummary {
  attemptId: string;
  profileId: string;
  modelName: string | null;
  status: AnalysisStageStatus;
}

export interface PitchNoteTranslationStageSnapshot {
  status: AnalysisStageStatus;
  authoritative: false;
  preferredAttemptId: string | null;
  attemptsSummary: PitchNoteTranslationAttemptSummary[];
  result: TranscriptionDetail | null;
  provenance: Record<string, unknown> | null;
  diagnostics: Record<string, unknown> | null;
  error: AnalysisStageError | null;
}

export interface InterpretationStageSnapshot {
  status: AnalysisStageStatus;
  authoritative: false;
  preferredAttemptId: string | null;
  attemptsSummary: InterpretationAttemptSummary[];
  result: InterpretationResult | null;
  provenance: Record<string, unknown> | null;
  diagnostics: Record<string, unknown> | null;
  error: AnalysisStageError | null;
  profiles?: Record<string, {
    attemptId: string;
    status: AnalysisStageStatus;
    modelName: string | null;
    result: InterpretationResult | null;
    provenance: Record<string, unknown> | null;
    diagnostics: Record<string, unknown> | null;
    error: AnalysisStageError | null;
  }>;
}

export interface AnalysisRunSnapshot {
  runId: string;
  requestedStages: AnalysisRunRequestedStages;
  artifacts: {
    sourceAudio: AnalysisRunArtifact;
    stems?: AnalysisRunArtifact[];
    spectral?: SpectralArtifacts;
  };
  stages: {
    measurement: MeasurementStageSnapshot;
    pitchNoteTranslation: PitchNoteTranslationStageSnapshot;
    interpretation: InterpretationStageSnapshot;
  };
}

export interface BackendEstimateStage {
  key: string;
  label: string;
  lowMs: number;
  highMs: number;
}

export interface BackendAnalysisEstimate {
  durationSeconds: number;
  totalLowMs: number;
  totalHighMs: number;
  stages: BackendEstimateStage[];
}

export interface BackendEstimateResponse {
  requestId: string;
  estimate: BackendAnalysisEstimate;
}

export interface BackendErrorPayload {
  code: string;
  message: string;
  phase: string;
  retryable: boolean;
}

export interface BackendErrorResponse {
  requestId: string;
  error: BackendErrorPayload;
  diagnostics?: BackendDiagnostics;
}

export type DiagnosticLogStatus = "running" | "success" | "error" | "skipped";

export interface DiagnosticLogEntry {
  model: string;
  phase: string;
  stageKey?: 'measurement' | 'pitchNoteTranslation' | 'interpretation' | 'system';
  promptLength: number;
  responseLength: number;
  durationMs: number;
  audioMetadata: {
    name: string;
    size: number;
    type: string;
  };
  timestamp: string;
  requestId?: string;
  source?: "backend" | "gemini" | "system";
  status?: DiagnosticLogStatus;
  message?: string;
  errorCode?: string;
  estimateLowMs?: number;
  estimateHighMs?: number;
  timings?: BackendTimingDiagnostics;
  validationReport?: import('./services/phase2Validator').ValidationReport;
}

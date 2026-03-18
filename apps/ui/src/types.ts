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

export interface Phase1Result {
  bpm: number;
  bpmConfidence: number;
  key: string | null;
  keyConfidence: number;
  timeSignature: string;
  durationSeconds: number;
  lufsIntegrated: number;
  lufsRange?: number | null;
  truePeak: number;
  crestFactor?: number | null;
  stereoWidth: number;
  stereoCorrelation: number;
  stereoDetail?: Record<string, unknown> | null;
  spectralBalance: {
    subBass: number;
    lowBass: number;
    mids: number;
    upperMids: number;
    highs: number;
    brilliance: number;
  };
  spectralDetail?: Record<string, unknown> | null;
  rhythmDetail?: Record<string, unknown> | null;
  melodyDetail?: MelodyDetail;
  transcriptionDetail?: TranscriptionDetail | null;
  grooveDetail?: Record<string, unknown> | null;
  sidechainDetail?: Record<string, unknown> | null;
  acidDetail?: {
    isAcid: boolean;
    confidence: number;
    resonanceLevel: number;
    centroidOscillationHz: number;
    bassRhythmDensity: number;
  } | null;
  reverbDetail?: {
    rt60: number | null;
    isWet: boolean;
    tailEnergyRatio: number | null;
    measured: boolean;
  } | null;
  vocalDetail?: {
    hasVocals: boolean;
    confidence: number;
    vocalEnergyRatio: number;
    formantStrength: number;
    mfccLikelihood: number;
  } | null;
  supersawDetail?: {
    isSupersaw: boolean;
    confidence: number;
    voiceCount: number;
    avgDetuneCents: number;
    spectralComplexity: number;
  } | null;
  bassDetail?: {
    averageDecayMs: number;
    type: 'punchy' | 'medium' | 'rolling' | 'sustained';
    transientRatio: number;
    fundamentalHz: number;
    transientCount: number;
    swingPercent: number;
    grooveType: 'straight' | 'slight-swing' | 'heavy-swing' | 'shuffle';
  } | null;
  kickDetail?: {
    isDistorted: boolean;
    thd: number;
    harmonicRatio: number;
    fundamentalHz: number;
    kickCount: number;
  } | null;
  genreDetail?: {
    genre: string;
    confidence: number;
    secondaryGenre: string | null;
    genreFamily: 'house' | 'techno' | 'dnb' | 'ambient' | 'trance' | 'dubstep' | 'breaks' | 'other';
    topScores: { genre: string; score: number }[];
  } | null;
  effectsDetail?: Record<string, unknown> | null;
  synthesisCharacter?: Record<string, unknown> | null;
  danceability?: DanceabilityResult | null;
  structure?: Record<string, unknown> | null;
  arrangementDetail?: Record<string, unknown> | null;
  segmentLoudness?: unknown[] | null;
  segmentSpectral?: unknown[] | null;
  segmentKey?: unknown[] | null;
  chordDetail?: Record<string, unknown> | null;
  perceptual?: Record<string, unknown> | null;
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

export interface AbletonRecommendation {
  device: string;
  category: RecommendationCategory;
  parameter: string;
  value: string;
  reason: string;
  advancedTip?: string;
}

export interface Phase2Result {
  trackCharacter: string;
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
    parameter: string;
    value: string;
    reason: string;
  }>;
  secretSauce: {
    title: string;
    icon?: string;
    explanation: string;
    implementationSteps: string[];
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

export interface StemSummaryResult {
  summary: string;
  bars: StemSummaryBar[];
  globalPatterns: {
    bassRole: string;
    melodicRole: string;
    pumpingOrModulation: string;
  };
  uncertaintyFlags: string[];
}

export type InterpretationResult = Phase2Result | StemSummaryResult;

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
  path: string;
}

export interface AnalysisRunRequestedStages {
  symbolicMode: string;
  symbolicBackend: string;
  interpretationMode: string;
  interpretationProfile: string;
  interpretationModel: string | null;
}

export interface MeasurementStageSnapshot {
  status: AnalysisStageStatus;
  authoritative: true;
  result: MeasurementResult | null;
  provenance: Record<string, unknown> | null;
  diagnostics: Record<string, unknown> | null;
  error: AnalysisStageError | null;
}

export interface SymbolicExtractionAttemptSummary {
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

export interface SymbolicExtractionStageSnapshot {
  status: AnalysisStageStatus;
  authoritative: false;
  preferredAttemptId: string | null;
  attemptsSummary: SymbolicExtractionAttemptSummary[];
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
}

export interface AnalysisRunSnapshot {
  runId: string;
  requestedStages: AnalysisRunRequestedStages;
  artifacts: {
    sourceAudio: AnalysisRunArtifact;
  };
  stages: {
    measurement: MeasurementStageSnapshot;
    symbolicExtraction: SymbolicExtractionStageSnapshot;
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
  stageKey?: 'measurement' | 'symbolicExtraction' | 'interpretation' | 'system';
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

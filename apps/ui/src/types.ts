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
  phase1: Phase1Result;
  diagnostics?: BackendDiagnostics;
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

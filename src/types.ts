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

export interface Phase1Result {
  bpm: number;
  bpmConfidence: number;
  key: string | null;
  keyConfidence: number;
  timeSignature: string;
  durationSeconds: number;
  lufsIntegrated: number;
  truePeak: number;
  stereoWidth: number;
  stereoCorrelation: number;
  spectralBalance: {
    subBass: number;
    lowBass: number;
    mids: number;
    upperMids: number;
    highs: number;
    brilliance: number;
  };
  melodyDetail?: MelodyDetail;
}

export type RecommendationCategory =
  | "Dynamics"
  | "EQ"
  | "Saturation"
  | "Space"
  | "Modulation"
  | "Utility"
  | "Synth"
  | "Sampler"
  | "Other";

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
  arrangementOverview?: {
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
  mixAndMasterChain?: Array<{
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
  abletonRecommendations?: AbletonRecommendation[];
}

export interface BackendDiagnostics {
  backendDurationMs: number;
  engineVersion: string;
}

export interface BackendAnalyzeResponse {
  requestId: string;
  phase1: Phase1Result;
  diagnostics?: BackendDiagnostics;
}

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
}

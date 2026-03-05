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
}

export interface Phase2Result {
  trackCharacter: string;
  detectedCharacteristics: {
    name: string;
    confidence: "HIGH" | "MED" | "LOW";
    explanation: string;
  }[];
  arrangementOverview: string;
  sonicElements: {
    kick: string;
    bass: string;
    melodicArp: string;
    grooveAndTiming: string;
    effectsAndTexture: string;
  };
  mixAndMasterChain: string;
  secretSauce: {
    title: string;
    explanation: string;
    implementationSteps: string[];
  };
  confidenceNotes: {
    field: string;
    value: string;
    reason: string;
  }[];
  abletonRecommendations?: {
    device: string;
    category: "Dynamics" | "EQ" | "Saturation" | "Space" | "Modulation" | "Utility" | "Synth" | "Sampler" | "Other";
    parameter: string;
    value: string;
    reason: string;
    advancedTip?: string;
  }[];
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
}

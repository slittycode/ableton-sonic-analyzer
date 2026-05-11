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

export interface StyleProfileAuthoritativeMeasurements {
  bpm: number | null;
  key: string | null;
  timeSignature: string | null;
}

export interface StyleProfile {
  genre: string;
  subGenre?: string;
  mood: string[];
  instruments: string[];
  productionTechniques: string[];
  description: string;
  generationPrompt: string;
  authoritativeMeasurements: StyleProfileAuthoritativeMeasurements;
}

export interface Phase2Result {
  trackCharacter: string;
  projectSetup?: Phase2ProjectSetup;
  trackLayout?: Phase2TrackLayoutItem[];
  routingBlueprint?: RoutingBlueprint;
  warpGuide?: Phase2WarpGuide;
  audioObservations?: AudioObservations;
  styleProfile?: StyleProfile;
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
    synthesisCharacter: string;
    vocalPresence: string;
    bassCharacter: string;
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

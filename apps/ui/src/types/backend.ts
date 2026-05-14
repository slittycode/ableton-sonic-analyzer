import type { MeasurementResult, Phase1Result, TranscriptionDetail } from './measurement';
import type { InterpretationResult } from './interpretation';

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

/**
 * The 5-value collapse of {@link AnalysisStageStatus} that the response
 * boundary attaches as `publicStatus` on every stage.
 *
 * Mapping (from `apps/backend/stage_status.py`):
 * - queued | blocked | ready  → `'queued'`
 * - running                   → `'running'`
 * - completed                 → `'completed'`
 * - failed                    → `'failed'`
 * - interrupted               → `'interrupted'`
 * - not_requested             → `null` (stage exists but not in pipeline)
 *
 * Additive over `status` — the original 8-state field is preserved on
 * every stage. New code that doesn't need to distinguish blocked-vs-
 * queued or ready-vs-queued can read `publicStatus` and ignore the
 * internal vocabulary.
 */
export type PublicStageStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'interrupted';

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
  path?: string;
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
  /** Additive 5-value collapse of `status`. `null` when status is `not_requested`. */
  publicStatus: PublicStageStatus | null;
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
  /** Additive 5-value collapse of `status`. `null` when status is `not_requested`. */
  publicStatus: PublicStageStatus | null;
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
  /** Additive 5-value collapse of `status`. `null` when status is `not_requested`. */
  publicStatus: PublicStageStatus | null;
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
  validationReport?: import('../services/phase2Validator').ValidationReport;
}

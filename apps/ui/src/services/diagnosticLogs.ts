import {
  AnalysisRunSnapshot,
  AnalysisStageStatus,
  BackendTimingDiagnostics,
  DiagnosticLogEntry,
} from '../types';

type StageKey = 'measurement' | 'pitchNoteTranslation' | 'interpretation';

interface BuildDisplayDiagnosticLogsOptions {
  logs: DiagnosticLogEntry[];
  analysisRun: AnalysisRunSnapshot | null;
  audioMetadata?: DiagnosticLogEntry['audioMetadata'] | null;
  interpretationModel?: string | null;
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function parseTimings(value: unknown): BackendTimingDiagnostics | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return undefined;
  }

  const record = value as Record<string, unknown>;
  const totalMs = asNumber(record.totalMs);
  const analysisMs = asNumber(record.analysisMs);
  const serverOverheadMs = asNumber(record.serverOverheadMs);
  const fileSizeBytes = asNumber(record.fileSizeBytes);
  const flagsUsed = Array.isArray(record.flagsUsed)
    ? record.flagsUsed.filter((item): item is string => typeof item === 'string')
    : [];

  if (
    totalMs === null ||
    analysisMs === null ||
    serverOverheadMs === null ||
    fileSizeBytes === null
  ) {
    return undefined;
  }

  return {
    totalMs,
    analysisMs,
    serverOverheadMs,
    flagsUsed,
    fileSizeBytes,
    fileDurationSeconds: asNumber(record.fileDurationSeconds),
    msPerSecondOfAudio: asNumber(record.msPerSecondOfAudio),
  };
}

function toLogStatus(status: AnalysisStageStatus): DiagnosticLogEntry['status'] {
  if (status === 'completed') return 'success';
  if (status === 'failed' || status === 'interrupted') return 'error';
  if (status === 'not_requested') return 'skipped';
  return 'running';
}

function stageDisplayLabel(stageKey: StageKey): string {
  switch (stageKey) {
    case 'measurement':
      return 'Measurement';
    case 'pitchNoteTranslation':
      return 'Pitch/Note Translation';
    case 'interpretation':
      return 'AI Interpretation';
  }
}

function stageMessage(stageKey: StageKey, status: AnalysisStageStatus, errorMessage?: string): string {
  if ((status === 'failed' || status === 'interrupted') && errorMessage) {
    return errorMessage;
  }

  if (status === 'completed') {
    if (stageKey === 'measurement') return 'Measurement complete.';
    if (stageKey === 'pitchNoteTranslation') return 'Pitch/Note Translation complete.';
    return 'AI interpretation complete.';
  }

  if (status === 'not_requested') {
    return stageKey === 'interpretation'
      ? 'AI interpretation skipped.'
      : 'Pitch/Note Translation was not requested.';
  }

  if (status === 'queued') return `${stageDisplayLabel(stageKey)} queued.`;
  if (status === 'blocked') return `${stageDisplayLabel(stageKey)} waiting on measurement.`;
  if (status === 'ready') return `${stageDisplayLabel(stageKey)} ready to run.`;
  return `${stageDisplayLabel(stageKey)} in progress.`;
}

function resolveAudioMetadata(
  analysisRun: AnalysisRunSnapshot,
  explicitAudioMetadata?: DiagnosticLogEntry['audioMetadata'] | null,
): DiagnosticLogEntry['audioMetadata'] {
  if (explicitAudioMetadata) {
    return explicitAudioMetadata;
  }

  return {
    name: analysisRun.artifacts.sourceAudio.filename,
    size: analysisRun.artifacts.sourceAudio.sizeBytes,
    type: analysisRun.artifacts.sourceAudio.mimeType,
  };
}

function resolveStageModel(
  stageKey: StageKey,
  analysisRun: AnalysisRunSnapshot,
  interpretationModel?: string | null,
): string {
  if (stageKey === 'measurement') {
    return 'local-dsp-engine';
  }

  if (stageKey === 'pitchNoteTranslation') {
    return (
      analysisRun.stages.pitchNoteTranslation.attemptsSummary[0]?.backendId ??
      asString((analysisRun.stages.pitchNoteTranslation.provenance as Record<string, unknown> | null)?.backendId) ??
      'pitch-note-translation'
    );
  }

  return (
    interpretationModel ??
    analysisRun.stages.interpretation.attemptsSummary[0]?.modelName ??
    'ai-interpretation'
  );
}

function buildFallbackStageLog(
  stageKey: StageKey,
  analysisRun: AnalysisRunSnapshot,
  audioMetadata: DiagnosticLogEntry['audioMetadata'],
  interpretationModel?: string | null,
): DiagnosticLogEntry | null {
  const stage =
    stageKey === 'measurement'
      ? analysisRun.stages.measurement
      : stageKey === 'pitchNoteTranslation'
        ? analysisRun.stages.pitchNoteTranslation
        : analysisRun.stages.interpretation;

  if (!stage.diagnostics && !stage.error) {
    return null;
  }

  const diagnosticsRecord =
    stage.diagnostics && typeof stage.diagnostics === 'object' && !Array.isArray(stage.diagnostics)
      ? stage.diagnostics as Record<string, unknown>
      : {};
  const backendDurationMs = asNumber(diagnosticsRecord.backendDurationMs);
  const requestId = asString(diagnosticsRecord.requestId) ?? analysisRun.runId;

  return {
    model: resolveStageModel(stageKey, analysisRun, interpretationModel),
    phase: stageDisplayLabel(stageKey),
    stageKey,
    promptLength: 0,
    responseLength: 0,
    durationMs: backendDurationMs === null ? 0 : Math.round(backendDurationMs),
    audioMetadata,
    timestamp: new Date().toISOString(),
    requestId,
    source: 'backend',
    status: toLogStatus(stage.status),
    message: stageMessage(stageKey, stage.status, stage.error?.message),
    errorCode: stage.error?.code,
    timings: parseTimings(diagnosticsRecord.timings),
  };
}

export function buildDisplayDiagnosticLogs({
  logs,
  analysisRun,
  audioMetadata,
  interpretationModel,
}: BuildDisplayDiagnosticLogsOptions): DiagnosticLogEntry[] {
  if (logs.length > 0 || !analysisRun) {
    return logs;
  }

  const resolvedAudioMetadata = resolveAudioMetadata(analysisRun, audioMetadata);
  const fallbackLogs = (['measurement', 'pitchNoteTranslation', 'interpretation'] as const)
    .map((stageKey) => buildFallbackStageLog(stageKey, analysisRun, resolvedAudioMetadata, interpretationModel))
    .filter((entry): entry is DiagnosticLogEntry => entry !== null);

  return fallbackLogs.length > 0 ? fallbackLogs : logs;
}

import {
  AnalysisRunArtifact,
  AnalysisRunRequestedStages,
  AnalysisRunSnapshot,
  AnalysisStageError,
  AnalysisStageStatus,
  InterpretationAttemptSummary,
  InterpretationResult,
  InterpretationStageSnapshot,
  MeasurementResult,
  Phase1Result,
  Phase2Result,
  StemSummaryResult,
  SymbolicExtractionAttemptSummary,
  SymbolicExtractionStageSnapshot,
} from '../types';
import { BackendClientError, createUserCancelledError, parsePhase1Result } from './backendPhase1Client';

interface AnalysisRunsClientOptions {
  apiBaseUrl: string;
  signal?: AbortSignal;
}

interface CreateAnalysisRunOptions extends AnalysisRunsClientOptions {
  symbolicMode: string;
  symbolicBackend: string;
  interpretationMode: string;
  interpretationProfile: string;
  interpretationModel?: string | null;
}

interface CreateSymbolicAttemptOptions extends AnalysisRunsClientOptions {
  symbolicMode: string;
  symbolicBackend: string;
}

interface CreateInterpretationAttemptOptions extends AnalysisRunsClientOptions {
  interpretationProfile: string;
  interpretationModel: string;
}

const ANALYSIS_RUN_STATUSES = new Set<AnalysisStageStatus>([
  'queued',
  'running',
  'blocked',
  'ready',
  'completed',
  'failed',
  'interrupted',
  'not_requested',
]);

export async function createAnalysisRun(
  file: File,
  options: CreateAnalysisRunOptions,
): Promise<AnalysisRunSnapshot> {
  const body = new FormData();
  body.append('track', file);
  body.append('symbolic_mode', options.symbolicMode);
  body.append('symbolic_backend', options.symbolicBackend);
  body.append('interpretation_mode', options.interpretationMode);
  body.append('interpretation_profile', options.interpretationProfile);
  if (options.interpretationModel) {
    body.append('interpretation_model', options.interpretationModel);
  }

  const response = await fetchJson(
    `${options.apiBaseUrl}/api/analysis-runs`,
    {
      method: 'POST',
      body,
      signal: options.signal,
    },
  );

  return parseAnalysisRunSnapshot(response);
}

export async function getAnalysisRun(
  runId: string,
  options: AnalysisRunsClientOptions,
): Promise<AnalysisRunSnapshot> {
  const response = await fetchJson(
    `${options.apiBaseUrl}/api/analysis-runs/${runId}`,
    {
      method: 'GET',
      signal: options.signal,
    },
  );

  return parseAnalysisRunSnapshot(response);
}

export async function createSymbolicExtractionAttempt(
  runId: string,
  options: CreateSymbolicAttemptOptions,
): Promise<AnalysisRunSnapshot> {
  const body = new FormData();
  body.append('symbolic_mode', options.symbolicMode);
  body.append('symbolic_backend', options.symbolicBackend);

  const response = await fetchJson(
    `${options.apiBaseUrl}/api/analysis-runs/${runId}/symbolic-extractions`,
    {
      method: 'POST',
      body,
      signal: options.signal,
    },
  );

  return parseAnalysisRunSnapshot(response);
}

export async function createInterpretationAttempt(
  runId: string,
  options: CreateInterpretationAttemptOptions,
): Promise<AnalysisRunSnapshot> {
  const body = new FormData();
  body.append('interpretation_profile', options.interpretationProfile);
  body.append('interpretation_model', options.interpretationModel);

  const response = await fetchJson(
    `${options.apiBaseUrl}/api/analysis-runs/${runId}/interpretations`,
    {
      method: 'POST',
      body,
      signal: options.signal,
    },
  );

  return parseAnalysisRunSnapshot(response);
}

export function projectPhase1FromRun(snapshot: AnalysisRunSnapshot): Phase1Result | null {
  if (snapshot.stages.measurement.result == null) {
    return null;
  }

  const measurement: MeasurementResult = snapshot.stages.measurement.result;
  const symbolic = snapshot.stages.symbolicExtraction.result;
  if (!symbolic) {
    return measurement;
  }

  return {
    ...measurement,
    transcriptionDetail: symbolic,
  };
}

export function projectPhase2FromRun(snapshot: AnalysisRunSnapshot): Phase2Result | null {
  const preferredProfileId = getPreferredInterpretationProfileId(snapshot.stages.interpretation);
  if (preferredProfileId !== 'producer_summary') {
    return null;
  }
  return snapshot.stages.interpretation.result as Phase2Result | null;
}

export function projectStemSummaryFromRun(snapshot: AnalysisRunSnapshot): StemSummaryResult | null {
  const preferredProfileId = getPreferredInterpretationProfileId(snapshot.stages.interpretation);
  if (preferredProfileId !== 'stem_summary') {
    return null;
  }
  return snapshot.stages.interpretation.result as StemSummaryResult | null;
}

async function fetchJson(url: string, init: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    if (init.signal?.aborted) {
      throw createUserCancelledError();
    }
    if (error instanceof TypeError) {
      throw new BackendClientError(
        'NETWORK_UNREACHABLE',
        'Cannot reach the local DSP backend. Confirm it is running and the API base URL is correct.',
        { cause: error },
      );
    }
    throw error instanceof Error ? error : new Error(String(error));
  }

  let payload: Record<string, unknown>;
  try {
    payload = (await response.json()) as Record<string, unknown>;
  } catch (error) {
    throw new BackendClientError(
      'BACKEND_BAD_RESPONSE',
      'Analysis run endpoint returned a non-JSON response.',
      {
        status: response.status,
        statusText: response.statusText,
        cause: error,
      },
    );
  }

  if (!response.ok) {
    const errorPayload = parseNullableRecord(payload.error);
    throw new BackendClientError(
      'BACKEND_HTTP_ERROR',
      asString(errorPayload?.message) ?? 'Analysis run request failed.',
      {
        status: response.status,
        statusText: response.statusText,
        serverCode: asString(errorPayload?.code) ?? undefined,
        retryable: typeof errorPayload?.retryable === 'boolean' ? errorPayload.retryable : undefined,
      },
    );
  }

  return payload;
}

function parseAnalysisRunSnapshot(value: unknown): AnalysisRunSnapshot {
  const root = expectRecord(value, 'analysis run');
  const stages = expectRecord(root.stages, 'analysis run stages');
  const measurement = expectRecord(stages.measurement, 'measurement stage');
  const symbolicExtraction = expectRecord(stages.symbolicExtraction, 'symbolic extraction stage');
  const interpretation = expectRecord(stages.interpretation, 'interpretation stage');

  return {
    runId: expectString(root.runId, 'runId'),
    requestedStages: parseRequestedStages(root.requestedStages),
    artifacts: {
      sourceAudio: parseArtifact(expectRecord(expectRecord(root.artifacts, 'artifacts').sourceAudio, 'sourceAudio')),
    },
    stages: {
      measurement: {
        status: expectStageStatus(measurement.status),
        authoritative: true,
        result: measurement.result == null ? null : parseCanonicalMeasurementResult(measurement.result),
        provenance: parseNullableRecord(measurement.provenance),
        diagnostics: parseNullableRecord(measurement.diagnostics),
        error: parseNullableError(measurement.error),
      },
      symbolicExtraction: parseSymbolicStage(symbolicExtraction),
      interpretation: parseInterpretationStage(interpretation),
    },
  };
}

function parseCanonicalMeasurementResult(value: unknown): MeasurementResult {
  const { transcriptionDetail: _transcriptionDetail, ...measurement } = parsePhase1Result(value);
  return measurement;
}

function parseRequestedStages(value: unknown): AnalysisRunRequestedStages {
  const requested = expectRecord(value, 'requestedStages');
  return {
    symbolicMode: expectString(requested.symbolicMode, 'requestedStages.symbolicMode'),
    symbolicBackend: expectString(requested.symbolicBackend, 'requestedStages.symbolicBackend'),
    interpretationMode: expectString(requested.interpretationMode, 'requestedStages.interpretationMode'),
    interpretationProfile: expectString(requested.interpretationProfile, 'requestedStages.interpretationProfile'),
    interpretationModel: asString(requested.interpretationModel),
  };
}

function parseArtifact(value: Record<string, unknown>): AnalysisRunArtifact {
  return {
    artifactId: expectString(value.artifactId, 'artifactId'),
    filename: expectString(value.filename, 'filename'),
    mimeType: expectString(value.mimeType, 'mimeType'),
    sizeBytes: expectNumber(value.sizeBytes, 'sizeBytes'),
    contentSha256: expectString(value.contentSha256, 'contentSha256'),
    path: expectString(value.path, 'path'),
  };
}

function parseSymbolicStage(value: Record<string, unknown>): SymbolicExtractionStageSnapshot {
  return {
    status: expectStageStatus(value.status),
    authoritative: false,
    preferredAttemptId: asString(value.preferredAttemptId),
    attemptsSummary: Array.isArray(value.attemptsSummary)
      ? value.attemptsSummary.map(parseSymbolicAttemptSummary)
      : [],
    result: value.result == null ? null : parseSymbolicResult(value.result),
    provenance: parseNullableRecord(value.provenance),
    diagnostics: parseNullableRecord(value.diagnostics),
    error: parseNullableError(value.error),
  };
}

function parseInterpretationStage(value: Record<string, unknown>): InterpretationStageSnapshot {
  const attemptsSummary = Array.isArray(value.attemptsSummary)
    ? value.attemptsSummary.map(parseInterpretationAttemptSummary)
    : [];
  const preferredProfileId = getPreferredInterpretationProfileId({
    preferredAttemptId: asString(value.preferredAttemptId),
    attemptsSummary,
  });
  return {
    status: expectStageStatus(value.status),
    authoritative: false,
    preferredAttemptId: asString(value.preferredAttemptId),
    attemptsSummary,
    result: value.result == null ? null : parseInterpretationResult(value.result, preferredProfileId),
    provenance: parseNullableRecord(value.provenance),
    diagnostics: parseNullableRecord(value.diagnostics),
    error: parseNullableError(value.error),
  };
}

function parseSymbolicAttemptSummary(value: unknown): SymbolicExtractionAttemptSummary {
  const attempt = expectRecord(value, 'symbolic attempt');
  return {
    attemptId: expectString(attempt.attemptId, 'symbolic attemptId'),
    backendId: expectString(attempt.backendId, 'symbolic backendId'),
    mode: expectString(attempt.mode, 'symbolic mode'),
    status: expectStageStatus(attempt.status),
  };
}

function parseInterpretationAttemptSummary(value: unknown): InterpretationAttemptSummary {
  const attempt = expectRecord(value, 'interpretation attempt');
  return {
    attemptId: expectString(attempt.attemptId, 'interpretation attemptId'),
    profileId: expectString(attempt.profileId, 'interpretation profileId'),
    modelName: asString(attempt.modelName),
    status: expectStageStatus(attempt.status),
  };
}

function parseInterpretationResult(
  value: unknown,
  profileId: string | null,
): InterpretationResult {
  if (profileId === 'stem_summary') {
    return parseStemSummaryResult(value);
  }
  return expectRecord(value, 'interpretation result') as unknown as Phase2Result;
}

function parseStemSummaryResult(value: unknown): StemSummaryResult {
  const result = expectRecord(value, 'stem summary result');
  return {
    summary: expectString(result.summary, 'stem summary summary'),
    bars: Array.isArray(result.bars)
      ? result.bars.map((entry) => {
          const bar = expectRecord(entry, 'stem summary bar');
          return {
            barStart: expectNumber(bar.barStart, 'stem summary barStart'),
            barEnd: expectNumber(bar.barEnd, 'stem summary barEnd'),
            startTime: expectNumber(bar.startTime, 'stem summary startTime'),
            endTime: expectNumber(bar.endTime, 'stem summary endTime'),
            noteHypotheses: Array.isArray(bar.noteHypotheses) ? bar.noteHypotheses.map((item) => String(item)) : [],
            scaleDegreeHypotheses: Array.isArray(bar.scaleDegreeHypotheses)
              ? bar.scaleDegreeHypotheses.map((item) => String(item))
              : [],
            rhythmicPattern: expectString(bar.rhythmicPattern, 'stem summary rhythmicPattern'),
            uncertaintyLevel: expectString(bar.uncertaintyLevel, 'stem summary uncertaintyLevel') as StemSummaryResult['bars'][number]['uncertaintyLevel'],
            uncertaintyReason: expectString(bar.uncertaintyReason, 'stem summary uncertaintyReason'),
          };
        })
      : [],
    globalPatterns: {
      bassRole: expectString(expectRecord(result.globalPatterns, 'stem summary globalPatterns').bassRole, 'stem summary bassRole'),
      melodicRole: expectString(expectRecord(result.globalPatterns, 'stem summary globalPatterns').melodicRole, 'stem summary melodicRole'),
      pumpingOrModulation: expectString(
        expectRecord(result.globalPatterns, 'stem summary globalPatterns').pumpingOrModulation,
        'stem summary pumpingOrModulation',
      ),
    },
    uncertaintyFlags: Array.isArray(result.uncertaintyFlags)
      ? result.uncertaintyFlags.map((item) => String(item))
      : [],
  };
}

function parseSymbolicResult(value: unknown): SymbolicExtractionStageSnapshot['result'] {
  const result = expectRecord(value, 'symbolic result');
  return {
    transcriptionMethod: asString(result.transcriptionMethod) ?? 'unknown',
    noteCount: expectNumber(result.noteCount, 'symbolic noteCount'),
    averageConfidence: expectNumber(result.averageConfidence, 'symbolic averageConfidence'),
    stemSeparationUsed: Boolean(result.stemSeparationUsed),
    fullMixFallback: Boolean(result.fullMixFallback),
    stemsTranscribed: Array.isArray(result.stemsTranscribed)
      ? result.stemsTranscribed.map((entry) => String(entry))
      : [],
    dominantPitches: Array.isArray(result.dominantPitches)
      ? result.dominantPitches.map((entry) => expectRecord(entry, 'dominant pitch') as SymbolicExtractionStageSnapshot['result']['dominantPitches'][number])
      : [],
    pitchRange: expectRecord(result.pitchRange, 'symbolic pitchRange') as SymbolicExtractionStageSnapshot['result']['pitchRange'],
    notes: Array.isArray(result.notes)
      ? result.notes.map((entry) => expectRecord(entry, 'symbolic note') as unknown as SymbolicExtractionStageSnapshot['result']['notes'][number])
      : [],
  };
}

function parseNullableRecord(value: unknown): Record<string, unknown> | null {
  if (value == null) {
    return null;
  }
  return expectRecord(value, 'record');
}

function parseNullableError(value: unknown): AnalysisStageError | null {
  if (value == null) {
    return null;
  }
  const error = expectRecord(value, 'stage error');
  return {
    code: expectString(error.code, 'stage error code'),
    message: expectString(error.message, 'stage error message'),
    retryable: typeof error.retryable === 'boolean' ? error.retryable : undefined,
    phase: asString(error.phase) ?? undefined,
  };
}

function expectRecord(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== 'object' || value == null || Array.isArray(value)) {
    throw new Error(`Expected ${label} to be an object.`);
  }
  return value as Record<string, unknown>;
}

function expectString(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Expected ${label} to be a non-empty string.`);
  }
  return value;
}

function expectNumber(value: unknown, label: string): number {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    throw new Error(`Expected ${label} to be a number.`);
  }
  return value;
}

function expectStageStatus(value: unknown): AnalysisStageStatus {
  if (typeof value !== 'string' || !ANALYSIS_RUN_STATUSES.has(value as AnalysisStageStatus)) {
    throw new Error(`Expected stage status to be one of ${Array.from(ANALYSIS_RUN_STATUSES).join(', ')}.`);
  }
  return value as AnalysisStageStatus;
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null;
}

function getPreferredInterpretationProfileId(
  stage: Pick<InterpretationStageSnapshot, 'preferredAttemptId' | 'attemptsSummary'>,
): string | null {
  const preferredAttempt = stage.attemptsSummary.find((attempt) => attempt.attemptId === stage.preferredAttemptId);
  return preferredAttempt?.profileId ?? stage.attemptsSummary[0]?.profileId ?? null;
}

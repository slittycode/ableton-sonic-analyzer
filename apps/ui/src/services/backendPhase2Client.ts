import { DiagnosticLogEntry, Phase1Result, Phase2Result } from '../types';
import { PHASE2_LABEL, PHASE2_SKIPPED_LABEL } from './phaseLabels';
import { BackendClientError, createUserCancelledError } from './backendPhase1Client';

export interface AnalyzePhase2BackendResult {
  result: Phase2Result | null;
  log: DiagnosticLogEntry;
}

export async function analyzePhase2WithBackend(
  file: File,
  phase1Result: Phase1Result,
  modelName: string,
  options: { apiBaseUrl: string; signal?: AbortSignal },
): Promise<AnalyzePhase2BackendResult> {
  const { apiBaseUrl, signal } = options;

  const body = new FormData();
  body.append('track', file);
  body.append('phase1_json', JSON.stringify(phase1Result));
  body.append('model_name', modelName);

  const audioMetadata: DiagnosticLogEntry['audioMetadata'] = {
    name: file.name,
    size: file.size,
    type: file.type || 'audio/mpeg',
  };

  const startTime = Date.now();
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/api/phase2`, {
      method: 'POST',
      body,
      signal,
    });
  } catch (err) {
    if (signal?.aborted) throw createUserCancelledError();
    throw err;
  }

  const durationMs = Date.now() - startTime;

  let json: Record<string, unknown>;
  try {
    json = (await response.json()) as Record<string, unknown>;
  } catch {
    throw new BackendClientError('BACKEND_BAD_RESPONSE', 'Phase 2 backend returned a non-JSON response.', {
      status: response.status,
      statusText: response.statusText,
    });
  }

  if (!response.ok) {
    const errorPayload = json.error as Record<string, unknown> | undefined;
    const serverCode = (errorPayload?.code as string | undefined) ?? 'GEMINI_FAILED';
    const errorMessage =
      (errorPayload?.message as string | undefined) ?? 'Phase 2 backend request failed.';
    const retryable = (errorPayload?.retryable as boolean | undefined) ?? false;
    throw new BackendClientError('BACKEND_HTTP_ERROR', errorMessage, {
      status: response.status,
      statusText: response.statusText,
      serverCode,
      retryable,
      requestId: json.requestId as string | undefined,
    });
  }

  const phase2Data = json.phase2 as Phase2Result | null | undefined;
  const message = (json.message as string | undefined) ?? '';

  if (phase2Data == null) {
    return {
      result: null,
      log: {
        model: modelName,
        phase: PHASE2_SKIPPED_LABEL,
        promptLength: 0,
        responseLength: 0,
        durationMs,
        audioMetadata,
        timestamp: new Date().toISOString(),
        source: 'backend',
        status: 'skipped',
        message: message || 'Phase 2 advisory skipped.',
      },
    };
  }

  return {
    result: phase2Data,
    log: {
      model: modelName,
      phase: PHASE2_LABEL,
      promptLength: 0,
      responseLength: JSON.stringify(phase2Data).length,
      durationMs,
      audioMetadata,
      timestamp: new Date().toISOString(),
      source: 'backend',
      status: 'success',
      message: message || 'Phase 2 advisory complete.',
    },
  };
}

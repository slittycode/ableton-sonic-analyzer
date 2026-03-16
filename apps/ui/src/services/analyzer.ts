import { appConfig, canRunGeminiPhase2, isGeminiPhase2ConfigEnabled } from '../config';
import { getAudioMimeTypeOrDefault } from './audioFile';
import { analyzePhase1WithBackend, createUserCancelledError, mapBackendError } from './backendPhase1Client';
import { PHASE1_LABEL, PHASE2_SKIPPED_LABEL } from './phaseLabels';
import { validatePhase2Consistency } from './phase2Validator';
import { DiagnosticLogEntry, Phase1Result, Phase2Result } from '../types';

interface AnalyzeAudioOptions {
  transcribe?: boolean;
  separate?: boolean;
  timeoutMs?: number;
  signal?: AbortSignal;
  phase2Requested?: boolean;
  phase2ConfigEnabled?: boolean;
}

function throwIfUserCancelled(signal?: AbortSignal) {
  if (signal?.aborted) {
    throw createUserCancelledError();
  }
}

async function raceWithCancellation<T>(operation: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (!signal) {
    return operation;
  }

  throwIfUserCancelled(signal);

  let abortHandler: (() => void) | null = null;
  const cancellation = new Promise<never>((_, reject) => {
    abortHandler = () => reject(createUserCancelledError());
    signal.addEventListener('abort', abortHandler, { once: true });
  });

  try {
    return await Promise.race([operation, cancellation]);
  } finally {
    if (abortHandler) {
      signal.removeEventListener('abort', abortHandler);
    }
  }
}

function buildPhase2SkippedLog(
  audioMetadata: DiagnosticLogEntry['audioMetadata'],
  requestId: string | undefined,
  message: string,
): DiagnosticLogEntry {
  return {
    model: 'disabled',
    phase: PHASE2_SKIPPED_LABEL,
    promptLength: 0,
    responseLength: 0,
    durationMs: 0,
    audioMetadata,
    timestamp: new Date().toISOString(),
    requestId,
    source: 'system',
    status: 'skipped',
    message,
  };
}

export async function analyzeAudio(
  file: File,
  modelName: string,
  dspJson: string | null,
  onPhase1Complete: (result: Phase1Result, log: DiagnosticLogEntry) => void,
  onPhase2Complete: (result: Phase2Result | null, log: DiagnosticLogEntry) => void,
  onError: (error: Error) => void,
  analysisOptions?: AnalyzeAudioOptions,
) {
  let phase1Completed = false;
  const phase2Requested = analysisOptions?.phase2Requested ?? true;
  const phase2ConfigEnabled = analysisOptions?.phase2ConfigEnabled ?? isGeminiPhase2ConfigEnabled(appConfig);
  const audioMetadata: DiagnosticLogEntry['audioMetadata'] = {
    name: file.name,
    size: file.size,
    type: getAudioMimeTypeOrDefault(file),
  };

  try {
    const phase1Start = Date.now();
    const backendResult = await analyzePhase1WithBackend(file, dspJson, {
      apiBaseUrl: appConfig.apiBaseUrl,
      timeoutMs: analysisOptions?.timeoutMs,
      transcribe: analysisOptions?.transcribe ?? false,
      separate: analysisOptions?.separate ?? false,
      signal: analysisOptions?.signal,
    });
    const phase1End = Date.now();

    const phase1Log: DiagnosticLogEntry = {
      model: 'local-dsp-engine',
      phase: PHASE1_LABEL,
      promptLength: dspJson?.length ?? 0,
      responseLength: JSON.stringify(backendResult.phase1).length,
      durationMs: phase1End - phase1Start,
      audioMetadata,
      timestamp: new Date().toISOString(),
      requestId: backendResult.requestId,
      source: 'backend',
      status: 'success',
      message: 'Local DSP analysis complete.',
      estimateLowMs: backendResult.diagnostics?.estimatedLowMs,
      estimateHighMs: backendResult.diagnostics?.estimatedHighMs,
      timings: backendResult.diagnostics?.timings,
    };

    onPhase1Complete(backendResult.phase1, phase1Log);
    phase1Completed = true;
    throwIfUserCancelled(analysisOptions?.signal);

    if (!phase2Requested) {
      onPhase2Complete(
        null,
        buildPhase2SkippedLog(
          audioMetadata,
          backendResult.requestId,
          'Phase 2 advisory skipped because it was disabled in the UI.',
        ),
      );
      return;
    }

    if (!phase2ConfigEnabled) {
      onPhase2Complete(
        null,
        buildPhase2SkippedLog(
          audioMetadata,
          backendResult.requestId,
          'Phase 2 advisory skipped because it was disabled by configuration.',
        ),
      );
      return;
    }

    if (!canRunGeminiPhase2()) {
      onPhase2Complete(
        null,
        buildPhase2SkippedLog(
          audioMetadata,
          backendResult.requestId,
          'Phase 2 advisory skipped because Gemini is enabled but no API key is configured.',
        ),
      );
      return;
    }

    const { analyzePhase2WithGemini } = await import('./geminiPhase2Client');
    const phase2 = await raceWithCancellation(
      analyzePhase2WithGemini({
        file,
        modelName,
        phase1Result: backendResult.phase1,
        audioMetadata,
        signal: analysisOptions?.signal,
      }),
      analysisOptions?.signal,
    );
    throwIfUserCancelled(analysisOptions?.signal);

    let validationReport: DiagnosticLogEntry['validationReport'];
    if (phase2.result) {
      try {
        validationReport = validatePhase2Consistency(backendResult.phase1, phase2.result);
      } catch {
        validationReport = undefined;
      }
    }

    onPhase2Complete(phase2.result, {
      ...phase2.log,
      requestId: backendResult.requestId,
      validationReport,
    });
  } catch (error) {
    if (!phase1Completed) {
      onError(mapBackendError(error));
      return;
    }
    onError(error instanceof Error ? error : new Error(String(error)));
  }
}

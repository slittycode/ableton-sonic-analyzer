import { appConfig, isGeminiPhase2ConfigEnabled } from '../config';
import { AnalysisRunSnapshot, DiagnosticLogEntry, Phase1Result, Phase2Result } from '../types';
import { getAudioMimeTypeOrDefault } from './audioFile';
import {
  createAnalysisRun,
  getAnalysisRun,
  projectPhase1FromRun,
  projectPhase2FromRun,
} from './analysisRunsClient';
import { createUserCancelledError, mapBackendError } from './backendPhase1Client';
import { MEASUREMENT_LABEL, INTERPRETATION_LABEL, INTERPRETATION_SKIPPED_LABEL } from './phaseLabels';
import { validatePhase2Consistency } from './phase2Validator';

const DEFAULT_POLL_INTERVAL_MS = 1_000;

export interface AnalyzeAudioUpdate {
  runId: string;
  snapshot: AnalysisRunSnapshot;
  displayPhase1: Phase1Result | null;
  displayPhase2: Phase2Result | null;
}

export interface AnalyzeAudioOptions {
  analysisMode?: 'full' | 'standard';
  pitchNoteRequested?: boolean;
  interpretationRequested?: boolean;
  interpretationConfigEnabled?: boolean;
  timeoutMs?: number;
  signal?: AbortSignal;
  onRunUpdate?: (update: AnalyzeAudioUpdate) => void;
  pollIntervalMs?: number;
  transcribe?: boolean;
  phase2Requested?: boolean;
  phase2ConfigEnabled?: boolean;
}

function throwIfUserCancelled(signal?: AbortSignal) {
  if (signal?.aborted) {
    throw createUserCancelledError();
  }
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  if (ms <= 0) {
    return Promise.resolve();
  }

  return new Promise((resolve, reject) => {
    const timeoutId = globalThis.setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);

    const onAbort = () => {
      globalThis.clearTimeout(timeoutId);
      signal?.removeEventListener('abort', onAbort);
      reject(createUserCancelledError());
    };

    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function buildPhase2SkippedLog(
  audioMetadata: DiagnosticLogEntry['audioMetadata'],
  requestId: string | undefined,
  message: string,
): DiagnosticLogEntry {
  return {
    model: 'disabled',
    phase: INTERPRETATION_SKIPPED_LABEL,
    stageKey: 'interpretation',
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

function buildMeasurementLog(
  runId: string,
  phase1: Phase1Result,
  audioMetadata: DiagnosticLogEntry['audioMetadata'],
  snapshot: AnalysisRunSnapshot,
): DiagnosticLogEntry {
  return {
    model: 'local-dsp-engine',
    phase: MEASUREMENT_LABEL,
    stageKey: 'measurement',
    promptLength: 0,
    responseLength: JSON.stringify(phase1).length,
    durationMs: 0,
    audioMetadata,
    timestamp: new Date().toISOString(),
    requestId: runId,
    source: 'backend',
    status: 'success',
    message: 'Measurement complete.',
    timings: snapshot.stages.measurement.diagnostics?.timings as DiagnosticLogEntry['timings'],
  };
}

function buildInterpretationLog(
  runId: string,
  phase2: Phase2Result,
  audioMetadata: DiagnosticLogEntry['audioMetadata'],
  validationReport: DiagnosticLogEntry['validationReport'],
): DiagnosticLogEntry {
  return {
    model: 'ai-interpretation',
    phase: INTERPRETATION_LABEL,
    stageKey: 'interpretation',
    promptLength: 0,
    responseLength: JSON.stringify(phase2).length,
    durationMs: 0,
    audioMetadata,
    timestamp: new Date().toISOString(),
    requestId: runId,
    source: 'backend',
    status: 'success',
    message: 'AI interpretation complete.',
    validationReport,
  };
}

function isMeasurementTerminal(snapshot: AnalysisRunSnapshot): boolean {
  return snapshot.stages.measurement.status === 'completed' || snapshot.stages.measurement.status === 'failed';
}

function isRunTerminal(snapshot: AnalysisRunSnapshot): boolean {
  if (!isMeasurementTerminal(snapshot)) {
    return false;
  }

  const pitchNoteDone = ['completed', 'failed', 'interrupted', 'not_requested'].includes(
    snapshot.stages.pitchNoteTranslation.status,
  );
  const interpretationDone = ['completed', 'failed', 'interrupted', 'not_requested'].includes(
    snapshot.stages.interpretation.status,
  );

  return pitchNoteDone && interpretationDone;
}

export async function analyzeAudio(
  file: File,
  modelName: string,
  _dspJson: string | null,
  onPhase1Complete: (result: Phase1Result, log: DiagnosticLogEntry) => void,
  onPhase2Complete: (result: Phase2Result | null, log: DiagnosticLogEntry) => void,
  onError: (error: Error) => void,
  analysisOptions?: AnalyzeAudioOptions,
) {
  try {
    throwIfUserCancelled(analysisOptions?.signal);

    const initialRun = await createAnalysisRun(file, {
      apiBaseUrl: appConfig.apiBaseUrl,
      signal: analysisOptions?.signal,
      analysisMode: analysisOptions?.analysisMode ?? 'full',
      pitchNoteMode: resolvePitchNoteRequested(analysisOptions) ? 'stem_notes' : 'off',
      pitchNoteBackend: 'auto',
      symbolicMode: resolvePitchNoteRequested(analysisOptions) ? 'stem_notes' : 'off',
      symbolicBackend: 'auto',
      interpretationMode: resolveInterpretationMode(analysisOptions),
      interpretationProfile: 'producer_summary',
      interpretationModel: resolveInterpretationMode(analysisOptions) === 'off' ? null : modelName,
    });

    analysisOptions?.onRunUpdate?.({
      runId: initialRun.runId,
      snapshot: initialRun,
      displayPhase1: projectPhase1FromRun(initialRun),
      displayPhase2: projectPhase2FromRun(initialRun),
    });

    await monitorAnalysisRun(
      initialRun.runId,
      file,
      modelName,
      onPhase1Complete,
      onPhase2Complete,
      onError,
      analysisOptions,
    );
  } catch (error) {
    onError(mapBackendError(error));
  }
}

export async function monitorAnalysisRun(
  runId: string,
  file: File,
  modelName: string,
  onPhase1Complete: (result: Phase1Result, log: DiagnosticLogEntry) => void,
  onPhase2Complete: (result: Phase2Result | null, log: DiagnosticLogEntry) => void,
  onError: (error: Error) => void,
  analysisOptions?: AnalyzeAudioOptions,
) {
  const audioMetadata: DiagnosticLogEntry['audioMetadata'] = {
    name: file.name,
    size: file.size,
    type: getAudioMimeTypeOrDefault(file),
  };
  const interpretationRequested = resolveInterpretationRequested(analysisOptions);

  let measurementReported = false;
  let interpretationReported = false;

  try {
    while (true) {
      throwIfUserCancelled(analysisOptions?.signal);
      const snapshot = await getAnalysisRun(runId, {
        apiBaseUrl: appConfig.apiBaseUrl,
        signal: analysisOptions?.signal,
      });
      throwIfUserCancelled(analysisOptions?.signal);

      const displayPhase1 = projectPhase1FromRun(snapshot);
      const displayPhase2 = projectPhase2FromRun(snapshot);
      analysisOptions?.onRunUpdate?.({
        runId,
        snapshot,
        displayPhase1,
        displayPhase2,
      });

      if (!measurementReported && displayPhase1 && snapshot.stages.measurement.status === 'completed') {
        onPhase1Complete(displayPhase1, buildMeasurementLog(runId, displayPhase1, audioMetadata, snapshot));
        measurementReported = true;
      }

      if (!interpretationReported) {
        if (displayPhase2) {
          let validationReport: DiagnosticLogEntry['validationReport'];
          try {
            if (displayPhase1) {
              validationReport = validatePhase2Consistency(displayPhase1, displayPhase2);
            }
          } catch {
            validationReport = undefined;
          }

          onPhase2Complete(
            displayPhase2,
            buildInterpretationLog(runId, displayPhase2, audioMetadata, validationReport),
          );
          interpretationReported = true;
        } else if (snapshot.stages.interpretation.status === 'not_requested') {
          const message = interpretationRequested
            ? 'AI interpretation skipped because it was disabled by configuration.'
            : 'AI interpretation skipped because it was disabled in the UI.';
          onPhase2Complete(null, buildPhase2SkippedLog(audioMetadata, runId, message));
          interpretationReported = true;
        }
      }

      if (isRunTerminal(snapshot)) {
        return;
      }

      await delay(analysisOptions?.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS, analysisOptions?.signal);
    }
  } catch (error) {
    onError(mapBackendError(error));
  }
}

function resolvePitchNoteRequested(options?: AnalyzeAudioOptions): boolean {
  return options?.pitchNoteRequested ?? options?.transcribe ?? false;
}

function resolveInterpretationRequested(options?: AnalyzeAudioOptions): boolean {
  return options?.interpretationRequested ?? options?.phase2Requested ?? true;
}

function resolveInterpretationMode(options?: AnalyzeAudioOptions): 'off' | 'async' {
  const interpretationRequested = resolveInterpretationRequested(options);
  const interpretationConfigEnabled =
    options?.interpretationConfigEnabled ??
    options?.phase2ConfigEnabled ??
    isGeminiPhase2ConfigEnabled(appConfig);

  return interpretationRequested && interpretationConfigEnabled ? 'async' : 'off';
}

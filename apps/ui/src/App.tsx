import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import { AudioWaveform, Sparkles, X } from 'lucide-react';

import { AnalysisStatusPanel } from './components/AnalysisStatusPanel';
import { DiagnosticLog } from './components/DiagnosticLog';
import { FileUpload } from './components/FileUpload';
import { WaveformPlayer } from './components/WaveformPlayer';
import { IdleSignalMonitor } from './components/IdleSignalMonitor';
import { useCpuMeter } from './hooks/useCpuMeter';
import { useGlobalDrag } from './hooks/useGlobalDrag';
import {
  appConfig,
  isGeminiPhase2ConfigEnabled,
} from './config';
import { getAudioMimeTypeOrDefault, isSupportedAudioFile } from './services/audioFile';
import { analyzeAudio, monitorAnalysisRun } from './services/analyzer';
import { createInterpretationAttempt, createSymbolicExtractionAttempt } from './services/analysisRunsClient';
import {
  BackendClientError,
  deriveAnalyzeTimeoutMs,
  estimatePhase1WithBackend,
  mapBackendError,
} from './services/backendPhase1Client';
import { MEASUREMENT_LABEL, INTERPRETATION_LABEL } from './services/phaseLabels';
import {
  AnalysisRunSnapshot,
  AnalysisStageStatus,
  BackendAnalysisEstimate,
  DiagnosticLogEntry,
  MeasurementResult,
  Phase1Result,
  Phase2Result,
  TranscriptionDetail,
} from './types';
import type { AnalysisResultsProps } from './components/AnalysisResults';
import {
  loadPhase2RequestedPreference,
  savePhase2RequestedPreference,
} from './utils/phase2Preference';
import { startRenderBenchmarkCycle } from './utils/renderBenchmark';

const MODELS = [
  { id: 'gemini-3.1-pro-preview', name: 'Gemini 3.1 Pro Preview (Recommended)' },
  { id: 'gemini-3.1-flash-preview', name: 'Gemini 3.1 Flash Preview' },
  { id: 'gemini-3-pro-preview', name: 'Gemini 3.0 Pro Preview' },
  { id: 'gemini-3-flash-preview', name: 'Gemini 3.0 Flash Preview' },
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro' },
  { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash' },
];

const AnalysisResults = lazy<React.ComponentType<AnalysisResultsProps>>(() =>
  import('./components/AnalysisResults').then((module) => ({
    default: module.AnalysisResults,
  })),
);

function buildAudioMetadata(file: File): DiagnosticLogEntry['audioMetadata'] {
  return {
    name: file.name,
    size: file.size,
    type: getAudioMimeTypeOrDefault(file),
  };
}

type StageKey = NonNullable<DiagnosticLogEntry['stageKey']>;

function replaceRunningLog(
  logs: DiagnosticLogEntry[],
  stageKey: StageKey,
  nextLog: DiagnosticLogEntry,
): DiagnosticLogEntry[] {
  return [...logs.filter((entry) => !(entry.stageKey === stageKey && entry.status === 'running')), nextLog];
}

function formatEstimateRange(estimate: BackendAnalysisEstimate): string {
  return `${Math.round(estimate.totalLowMs / 1000)}s-${Math.round(estimate.totalHighMs / 1000)}s`;
}

function getInterpretationStatusBadge(
  phase2ConfigEnabled: boolean,
  phase2Requested: boolean,
): string | null {
  if (!phase2ConfigEnabled) return 'INTERPRETATION CONFIG OFF';
  if (!phase2Requested) return 'INTERPRETATION USER OFF';
  return null;
}

function getInterpretationHelperCopy(
  phase2ConfigEnabled: boolean,
  phase2Requested: boolean,
): string {
  if (!phase2ConfigEnabled) {
    return 'Developer kill-switch is off. AI interpretation is unavailable in this build.';
  }

  if (!phase2Requested) {
    return 'Measurement still runs. Turn this on when you want an AI-grounded interpretation after local analysis completes.';
  }

  return 'Runs after measurement succeeds and uses the selected model for grounded musical interpretation.';
}

function isTerminalStageStatus(status: AnalysisStageStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'interrupted' || status === 'not_requested';
}

function stageDisplayLabel(stageKey: StageKey): string {
  switch (stageKey) {
    case 'measurement':
      return 'Measurement';
    case 'symbolicExtraction':
      return 'Symbolic Extraction';
    case 'interpretation':
      return 'AI Interpretation';
    default:
      return 'System';
  }
}

function buildStageLogMessage(stageKey: StageKey, status: AnalysisStageStatus, run: AnalysisRunSnapshot): string {
  const stage =
    stageKey === 'measurement'
      ? run.stages.measurement
      : stageKey === 'symbolicExtraction'
        ? run.stages.symbolicExtraction
        : run.stages.interpretation;
  const error = stage.error;

  if (status === 'failed' || status === 'interrupted') {
    return error?.message ?? `${stageDisplayLabel(stageKey)} ${status}.`;
  }

  if (status === 'completed') {
    switch (stageKey) {
      case 'measurement':
        return 'Measurement complete.';
      case 'symbolicExtraction':
        return 'Symbolic extraction complete.';
      case 'interpretation':
        return 'AI interpretation complete.';
      default:
        return 'Stage complete.';
    }
  }

  if (status === 'not_requested') {
    return stageKey === 'interpretation'
      ? 'AI interpretation skipped.'
      : 'Symbolic extraction was not requested.';
  }

  if (status === 'queued') {
    return `${stageDisplayLabel(stageKey)} queued.`;
  }

  if (status === 'running') {
    return `${stageDisplayLabel(stageKey)} in progress.`;
  }

  if (status === 'blocked') {
    return `${stageDisplayLabel(stageKey)} waiting on measurement.`;
  }

  return `${stageDisplayLabel(stageKey)} ready to run.`;
}

function createStageLogEntry(
  stageKey: StageKey,
  status: DiagnosticLogEntry['status'],
  message: string,
  audioMetadata: DiagnosticLogEntry['audioMetadata'],
  model: string,
  requestId?: string,
  errorCode?: string,
): DiagnosticLogEntry {
  return {
    model,
    phase: stageDisplayLabel(stageKey),
    stageKey,
    promptLength: 0,
    responseLength: 0,
    durationMs: 0,
    audioMetadata,
    timestamp: new Date().toISOString(),
    requestId,
    source: stageKey === 'interpretation' ? 'backend' : 'backend',
    status,
    message,
    errorCode,
  };
}

function getValidationSummaryLine(
  validationReport: DiagnosticLogEntry['validationReport'],
): string | null {
  if (!validationReport || validationReport.violations.length === 0) {
    return null;
  }

  return `Validation: ${validationReport.summary.errorCount} error(s), ${validationReport.summary.warningCount} warning(s)`;
}

export default function App() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorRetryable, setErrorRetryable] = useState(false);
  const [selectedModel, setSelectedModel] = useState(MODELS[0].id);
  const [interpretationRequested, setInterpretationRequested] = useState(() => loadPhase2RequestedPreference());

  const [measurementResult, setMeasurementResult] = useState<MeasurementResult | null>(null);
  const [symbolicResult, setSymbolicResult] = useState<TranscriptionDetail | null>(null);
  const [phase2Result, setPhase2Result] = useState<Phase2Result | null>(null);
  const [phase2StatusMessage, setPhase2StatusMessage] = useState<string | null>(null);
  const [logs, setLogs] = useState<DiagnosticLogEntry[]>([]);
  const [analysisRun, setAnalysisRun] = useState<AnalysisRunSnapshot | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isDemoLoading, setIsDemoLoading] = useState(false);

  const [analysisEstimate, setAnalysisEstimate] = useState<BackendAnalysisEstimate | null>(null);
  const [isEstimateLoading, setIsEstimateLoading] = useState(false);
  const [estimateError, setEstimateError] = useState<string | null>(null);
  const [estimateWrongService, setEstimateWrongService] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [symbolicExtractionRequested, setSymbolicExtractionRequested] = useState(true);

  const analysisStartedAtRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const phase2ConfigEnabled = isGeminiPhase2ConfigEnabled();
  const interpretationWillRun = interpretationRequested && phase2ConfigEnabled;
  const phase2StatusBadge = getInterpretationStatusBadge(phase2ConfigEnabled, interpretationRequested);
  const phase2HelperCopy = getInterpretationHelperCopy(phase2ConfigEnabled, interpretationRequested);
  const phase2ModelSelectorDisabled = isAnalyzing || !phase2ConfigEnabled || !interpretationRequested;
  const cpuMeterPercent = useCpuMeter(isAnalyzing);
  const audioElementRef = useRef<HTMLAudioElement | null>(null);
  const previousRunRef = useRef<AnalysisRunSnapshot | null>(null);
  const completionRef = useRef<{ measurement: boolean; interpretation: boolean }>({
    measurement: false,
    interpretation: false,
  });

  useEffect(() => {
    savePhase2RequestedPreference(interpretationRequested);
  }, [interpretationRequested]);

  useEffect(() => {
    if (!audioFile) {
      setAnalysisEstimate(null);
      setIsEstimateLoading(false);
      setEstimateError(null);
      setEstimateWrongService(false);
      return;
    }

    let isCancelled = false;
    setAnalysisEstimate(null);
    setEstimateError(null);
    setEstimateWrongService(false);
    setIsEstimateLoading(true);

    // Legacy estimate route — retained pending canonicalization into analysis-runs API.
    estimatePhase1WithBackend(audioFile, {
      apiBaseUrl: appConfig.apiBaseUrl,
      transcribe: symbolicExtractionRequested,
      separate: symbolicExtractionRequested,
    })
      .then((result) => {
        if (isCancelled) return;
        setAnalysisEstimate(result.estimate);
      })
      .catch((rawError) => {
        if (isCancelled) return;
        const mapped = mapBackendError(rawError);
        setEstimateError(mapped.message);
        setEstimateWrongService(mapped.code === 'BACKEND_WRONG_SERVICE');
      })
      .finally(() => {
        if (!isCancelled) {
          setIsEstimateLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [audioFile, symbolicExtractionRequested]);

  useEffect(() => {
    if (!isAnalyzing || analysisStartedAtRef.current === null) {
      setElapsedMs(0);
      return;
    }

    const updateElapsed = () => {
      if (analysisStartedAtRef.current === null) return;
      setElapsedMs(Date.now() - analysisStartedAtRef.current);
    };

    updateElapsed();
    const intervalId = window.setInterval(updateElapsed, 250);
    return () => window.clearInterval(intervalId);
  }, [isAnalyzing]);

  const handleFileSelect = useCallback((file: File) => {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioFile(file);
    setAudioUrl(URL.createObjectURL(file));
    setMeasurementResult(null);
    setSymbolicResult(null);
    setPhase2Result(null);
    setPhase2StatusMessage(null);
    setLogs([]);
    setAnalysisRun(null);
    setActiveRunId(null);
    setError(null);
    previousRunRef.current = null;
    completionRef.current = { measurement: false, interpretation: false };
    analysisStartedAtRef.current = null;
    setElapsedMs(0);
    setEstimateWrongService(false);
    setIsDemoLoading(false);
  }, [audioUrl]);

  const handleFileClear = useCallback(() => {
    setAudioFile(null);
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioUrl(null);
    setMeasurementResult(null);
    setSymbolicResult(null);
    setPhase2Result(null);
    setPhase2StatusMessage(null);
    setLogs([]);
    setAnalysisRun(null);
    setActiveRunId(null);
    setError(null);
    setAnalysisEstimate(null);
    setEstimateError(null);
    setIsEstimateLoading(false);
    setEstimateWrongService(false);
    previousRunRef.current = null;
    completionRef.current = { measurement: false, interpretation: false };
    analysisStartedAtRef.current = null;
    setElapsedMs(0);
    setIsDemoLoading(false);
  }, [audioUrl]);

  const handleGlobalFilesDrop = useCallback(
    (files: File[]) => {
      if (isAnalyzing) return;

      const nextFile = files.find((file) => isSupportedAudioFile(file));
      if (!nextFile) {
        setError('File type not supported. Please upload MP3, WAV, FLAC, or AIFF.');
        setErrorRetryable(false);
        return;
      }

      handleFileSelect(nextFile);
    },
    [handleFileSelect, isAnalyzing],
  );

  const { isDraggingFile } = useGlobalDrag({
    disabled: isAnalyzing,
    onFilesDrop: handleGlobalFilesDrop,
  });

  const handleLoadDemoTrack = useCallback(async () => {
    if (isAnalyzing || isDemoLoading) return;

    setIsDemoLoading(true);
    setError(null);
    setErrorRetryable(false);

    try {
      const response = await fetch('/demo.mp3');
      if (!response.ok) {
        throw new Error('Failed to load demo track.');
      }

      const blob = await response.blob();
      const file = new File([blob], 'demo.mp3', { type: blob.type || 'audio/mpeg' });
      handleFileSelect(file);
    } catch (rawError) {
      const err = rawError instanceof Error ? rawError : new Error(String(rawError));
      setError(err.message);
      setErrorRetryable(false);
      setIsDemoLoading(false);
    }
  }, [handleFileSelect, isAnalyzing, isDemoLoading]);

  const handleInterpretationRequestedChange = (requested: boolean) => {
    setInterpretationRequested(requested);
  };

  const syncStageLog = useCallback((
    currentLogs: DiagnosticLogEntry[],
    stageKey: StageKey,
    nextStatus: AnalysisStageStatus,
    run: AnalysisRunSnapshot,
    audioMetadata: DiagnosticLogEntry['audioMetadata'],
    activeModel: string,
    activeEstimate: BackendAnalysisEstimate | null,
  ) => {
    const model = stageKey === 'interpretation' ? activeModel : 'local-dsp-engine';
    const stageError =
      stageKey === 'measurement'
        ? run.stages.measurement.error
        : stageKey === 'symbolicExtraction'
          ? run.stages.symbolicExtraction.error
          : run.stages.interpretation.error;

    if (nextStatus === 'queued' || nextStatus === 'running') {
      return replaceRunningLog(currentLogs, stageKey, {
        ...createStageLogEntry(
          stageKey,
          'running',
          buildStageLogMessage(stageKey, nextStatus, run),
          audioMetadata,
          model,
          run.runId,
        ),
        estimateLowMs: stageKey === 'measurement' ? activeEstimate?.totalLowMs : undefined,
        estimateHighMs: stageKey === 'measurement' ? activeEstimate?.totalHighMs : undefined,
      });
    }

    if (nextStatus === 'completed' && stageKey === 'symbolicExtraction') {
      return replaceRunningLog(
        currentLogs,
        stageKey,
        createStageLogEntry(
          stageKey,
          'success',
          buildStageLogMessage(stageKey, nextStatus, run),
          audioMetadata,
          model,
          run.runId,
        ),
      );
    }

    if (nextStatus === 'failed' || nextStatus === 'interrupted') {
      return replaceRunningLog(
        currentLogs,
        stageKey,
        createStageLogEntry(
          stageKey,
          'error',
          buildStageLogMessage(stageKey, nextStatus, run),
          audioMetadata,
          model,
          run.runId,
          stageError?.code,
        ),
      );
    }

    return currentLogs;
  }, []);

  const handleStartAnalysis = async () => {
    if (!audioFile) return;

    const activeFile = audioFile;
    const activeModel = selectedModel;
    const activeEstimate = analysisEstimate;
    const activeTimeoutMs = deriveAnalyzeTimeoutMs(activeEstimate?.totalHighMs);
    const audioMetadata = buildAudioMetadata(activeFile);

    startRenderBenchmarkCycle(window);

    const ac = new AbortController();
    abortControllerRef.current = ac;

    setIsAnalyzing(true);
    setError(null);
    setErrorRetryable(false);
    setPhase2StatusMessage(null);
    setAnalysisRun(null);
    setActiveRunId(null);
    previousRunRef.current = null;
    completionRef.current = { measurement: false, interpretation: false };
    analysisStartedAtRef.current = Date.now();

    setLogs([
      {
        model: 'local-dsp-engine',
        phase: MEASUREMENT_LABEL,
        stageKey: 'measurement',
        promptLength: 0,
        responseLength: 0,
        durationMs: 0,
        audioMetadata,
        timestamp: new Date().toISOString(),
        source: 'backend',
        status: 'running',
        message: 'Request in flight',
        estimateLowMs: activeEstimate?.totalLowMs,
        estimateHighMs: activeEstimate?.totalHighMs,
      },
    ]);

    try {
      await analyzeAudio(
        activeFile,
        activeModel,
        null,
        (result, log) => {
          setLogs((prev) => {
            const nextLogs = replaceRunningLog(prev, 'measurement', {
              ...log,
              status: 'success',
              message: log.message ?? 'Measurement complete.',
              estimateLowMs: activeEstimate?.totalLowMs,
              estimateHighMs: activeEstimate?.totalHighMs,
            });

            if (!interpretationWillRun) {
              return nextLogs;
            }

            return [
              ...nextLogs,
              {
                model: activeModel,
                phase: INTERPRETATION_LABEL,
                stageKey: 'interpretation',
                promptLength: 0,
                responseLength: 0,
                durationMs: 0,
                audioMetadata,
                timestamp: new Date().toISOString(),
                source: 'backend',
                status: 'running',
                message: 'AI interpretation in progress.',
              },
            ];
          });
          completionRef.current.measurement = true;
          if (result) {
            const { transcriptionDetail, ...measurement } = result;
            setMeasurementResult(measurement);
            setSymbolicResult(transcriptionDetail ?? null);
          } else {
            setMeasurementResult(null);
            setSymbolicResult(null);
          }
        },
        (result, log) => {
          setPhase2Result(result);
          setPhase2StatusMessage(log.message ?? null);
          setLogs((prev) => {
            const baseMessage =
              log.message ?? (result ? 'AI interpretation complete.' : 'AI interpretation skipped.');
            const validationSummaryLine = getValidationSummaryLine(log.validationReport);
            const logMessage = validationSummaryLine
              ? `${baseMessage}\n${validationSummaryLine}`
              : baseMessage;

            if (interpretationWillRun) {
              return replaceRunningLog(prev, 'interpretation', {
                ...log,
                status: log.status ?? (result ? 'success' : 'skipped'),
                message: logMessage,
              });
            }
            return [
              ...prev,
              {
                ...log,
                message: logMessage,
              },
            ];
          });
          completionRef.current.interpretation = true;
        },
        (rawError) => {
          const err = rawError instanceof Error ? rawError : new Error(String(rawError));
          const backendError = err instanceof BackendClientError ? err : null;
          const isCancelled = backendError?.code === 'USER_CANCELLED';

          setLogs((prev) => [
            ...prev.filter(
              (entry) =>
                !(
                  entry.status === 'running' &&
                  (entry.stageKey === 'measurement' || entry.stageKey === 'interpretation')
                ),
            ),
            {
              model: 'system',
              phase: 'Monitoring',
              stageKey: 'system',
              promptLength: 0,
              responseLength: 0,
              durationMs: elapsedMs,
              audioMetadata,
              timestamp: new Date().toISOString(),
              requestId: backendError?.details?.requestId,
              source: 'system',
              status: isCancelled ? 'skipped' : 'error',
              message: isCancelled ? 'Monitoring stopped.' : err.message,
              errorCode: isCancelled ? undefined : backendError?.details?.serverCode ?? backendError?.code,
              estimateLowMs: activeEstimate?.totalLowMs,
              estimateHighMs: activeEstimate?.totalHighMs,
              timings: backendError?.details?.diagnostics?.timings,
            },
          ]);

          if (!isCancelled) {
            setError(err.message);
            setErrorRetryable(backendError?.details?.retryable === true);
          }
        },
        {
          symbolicRequested: symbolicExtractionRequested,
          timeoutMs: activeTimeoutMs,
          signal: ac.signal,
          interpretationRequested,
          interpretationConfigEnabled: phase2ConfigEnabled,
          onRunUpdate: (update) => {
            setActiveRunId(update.runId);
            setAnalysisRun(update.snapshot);
            const p1 = update.displayPhase1;
            if (p1) {
              const { transcriptionDetail, ...measurement } = p1;
              setMeasurementResult(measurement);
              setSymbolicResult(transcriptionDetail ?? null);
            } else {
              setMeasurementResult(null);
              setSymbolicResult(null);
            }
            setPhase2Result(update.displayPhase2);
            if (!update.displayPhase2 && isTerminalStageStatus(update.snapshot.stages.interpretation.status)) {
              setPhase2StatusMessage(
                update.snapshot.stages.interpretation.error?.message ??
                  (update.snapshot.stages.interpretation.status === 'not_requested'
                    ? interpretationRequested
                      ? 'AI interpretation skipped because it was disabled by configuration.'
                      : 'AI interpretation skipped because it was disabled in the UI.'
                    : null),
              );
            }

            const previous = previousRunRef.current;
            setLogs((prev) => {
              let nextLogs = prev;
              const measurementStatus = update.snapshot.stages.measurement.status;
              const symbolicStatus = update.snapshot.stages.symbolicExtraction.status;
              const interpretationStatus = update.snapshot.stages.interpretation.status;

              if (!previous || previous.stages.measurement.status !== measurementStatus) {
                nextLogs = syncStageLog(
                  nextLogs,
                  'measurement',
                  measurementStatus,
                  update.snapshot,
                  audioMetadata,
                  activeModel,
                  activeEstimate,
                );
              }

              if (!previous || previous.stages.symbolicExtraction.status !== symbolicStatus) {
                nextLogs = syncStageLog(
                  nextLogs,
                  'symbolicExtraction',
                  symbolicStatus,
                  update.snapshot,
                  audioMetadata,
                  activeModel,
                  activeEstimate,
                );
              }

              if (!previous || previous.stages.interpretation.status !== interpretationStatus) {
                nextLogs = syncStageLog(
                  nextLogs,
                  'interpretation',
                  interpretationStatus,
                  update.snapshot,
                  audioMetadata,
                  activeModel,
                  activeEstimate,
                );
              }

              return nextLogs;
            });
            previousRunRef.current = update.snapshot;
          },
        },
      );
    } catch (rawError) {
      const err = rawError instanceof Error ? rawError : new Error(String(rawError));
      setError(err.message);
      setErrorRetryable(err instanceof BackendClientError && err.details?.retryable === true);
    } finally {
      setIsAnalyzing(false);
      abortControllerRef.current = null;
      analysisStartedAtRef.current = null;
      setElapsedMs(0);
    }
  };

  const handleStopMonitoring = () => {
    abortControllerRef.current?.abort();
  };

  const handleRetrySymbolicExtraction = useCallback(async () => {
    if (!audioFile || !activeRunId) return;

    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsAnalyzing(true);
    setError(null);
    setErrorRetryable(false);
    analysisStartedAtRef.current = Date.now();

    try {
      await createSymbolicExtractionAttempt(activeRunId, {
        apiBaseUrl: appConfig.apiBaseUrl,
        symbolicMode: 'stem_notes',
        symbolicBackend: 'auto',
        signal: controller.signal,
      });
      await monitorAnalysisRun(
        activeRunId,
        audioFile,
        selectedModel,
        (result, log) => {
          completionRef.current.measurement = true;
          if (result) {
            const { transcriptionDetail, ...measurement } = result;
            setMeasurementResult(measurement);
            setSymbolicResult(transcriptionDetail ?? null);
          } else {
            setMeasurementResult(null);
            setSymbolicResult(null);
          }
          setLogs((prev) => replaceRunningLog(prev, 'measurement', { ...log, status: 'success' }));
        },
        (result, log) => {
          setPhase2Result(result);
          setPhase2StatusMessage(log.message ?? null);
          setLogs((prev) => replaceRunningLog(prev, 'interpretation', { ...log, status: log.status ?? 'success' }));
        },
        (rawError) => {
          const err = rawError instanceof Error ? rawError : new Error(String(rawError));
          if (!(err instanceof BackendClientError && err.code === 'USER_CANCELLED')) {
            setError(err.message);
          }
        },
        {
          symbolicRequested: symbolicExtractionRequested,
          interpretationRequested,
          interpretationConfigEnabled: phase2ConfigEnabled,
          signal: controller.signal,
          onRunUpdate: (update) => {
            setActiveRunId(update.runId);
            setAnalysisRun(update.snapshot);
            const p1 = update.displayPhase1;
            if (p1) {
              const { transcriptionDetail, ...measurement } = p1;
              setMeasurementResult(measurement);
              setSymbolicResult(transcriptionDetail ?? null);
            } else {
              setMeasurementResult(null);
              setSymbolicResult(null);
            }
            setPhase2Result(update.displayPhase2);
            previousRunRef.current = update.snapshot;
          },
        },
      );
    } finally {
      setIsAnalyzing(false);
      abortControllerRef.current = null;
      analysisStartedAtRef.current = null;
      setElapsedMs(0);
    }
  }, [activeRunId, audioFile, interpretationRequested, phase2ConfigEnabled, selectedModel, symbolicExtractionRequested]);

  const handleRetryInterpretation = useCallback(async () => {
    if (!audioFile || !activeRunId) return;

    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsAnalyzing(true);
    setError(null);
    setErrorRetryable(false);
    setPhase2StatusMessage(null);
    analysisStartedAtRef.current = Date.now();

    try {
      await createInterpretationAttempt(activeRunId, {
        apiBaseUrl: appConfig.apiBaseUrl,
        interpretationProfile: 'producer_summary',
        interpretationModel: selectedModel,
        signal: controller.signal,
      });
      await monitorAnalysisRun(
        activeRunId,
        audioFile,
        selectedModel,
        (result, log) => {
          completionRef.current.measurement = true;
          if (result) {
            const { transcriptionDetail, ...measurement } = result;
            setMeasurementResult(measurement);
            setSymbolicResult(transcriptionDetail ?? null);
          } else {
            setMeasurementResult(null);
            setSymbolicResult(null);
          }
          setLogs((prev) => replaceRunningLog(prev, 'measurement', { ...log, status: 'success' }));
        },
        (result, log) => {
          setPhase2Result(result);
          setPhase2StatusMessage(log.message ?? null);
          setLogs((prev) => replaceRunningLog(prev, 'interpretation', { ...log, status: log.status ?? 'success' }));
        },
        (rawError) => {
          const err = rawError instanceof Error ? rawError : new Error(String(rawError));
          if (!(err instanceof BackendClientError && err.code === 'USER_CANCELLED')) {
            setError(err.message);
          }
        },
        {
          symbolicRequested: symbolicExtractionRequested,
          interpretationRequested,
          interpretationConfigEnabled: phase2ConfigEnabled,
          signal: controller.signal,
          onRunUpdate: (update) => {
            setActiveRunId(update.runId);
            setAnalysisRun(update.snapshot);
            const p1 = update.displayPhase1;
            if (p1) {
              const { transcriptionDetail, ...measurement } = p1;
              setMeasurementResult(measurement);
              setSymbolicResult(transcriptionDetail ?? null);
            } else {
              setMeasurementResult(null);
              setSymbolicResult(null);
            }
            setPhase2Result(update.displayPhase2);
            previousRunRef.current = update.snapshot;
          },
        },
      );
    } finally {
      setIsAnalyzing(false);
      abortControllerRef.current = null;
      analysisStartedAtRef.current = null;
      setElapsedMs(0);
    }
  }, [activeRunId, audioFile, interpretationRequested, phase2ConfigEnabled, selectedModel, symbolicExtractionRequested]);

  const handleAudioElement = useCallback((el: HTMLAudioElement) => {
    audioElementRef.current = el;
  }, []);

  const handleSpectrogramSeek = useCallback((timeSeconds: number) => {
    if (audioElementRef.current) {
      audioElementRef.current.currentTime = timeSeconds;
    }
  }, []);

  const isAnalyzeDisabled = isAnalyzing || estimateWrongService;
  const hasRetryableRunStage = Boolean(
    analysisRun &&
      (
        ['failed', 'interrupted'].includes(analysisRun.stages.measurement.status) ||
        ['failed', 'interrupted'].includes(analysisRun.stages.symbolicExtraction.status) ||
        ['failed', 'interrupted'].includes(analysisRun.stages.interpretation.status)
      ),
  );
  const shouldShowStatusPanel = Boolean(audioUrl && audioFile && analysisRun && (isAnalyzing || hasRetryableRunStage));
  const phase1ForRender: Phase1Result | null = measurementResult
    ? {
        ...measurementResult,
        transcriptionDetail: symbolicResult ?? null,
      }
    : null;

  return (
    <div className="min-h-screen bg-bg-app px-3 py-3 md:px-6 md:py-5 font-sans flex items-center justify-center">
      <div
        data-testid="app-shell"
        className="ableton-shell w-full max-w-6xl rounded-sm overflow-hidden flex flex-col"
      >
        <div
          data-testid="app-toolbar"
          className="ableton-toolbar h-10 border-b border-border flex items-center justify-between px-4"
        >
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <AudioWaveform className="w-4 h-4 text-accent" />
              <span className="text-xs font-bold text-text-primary tracking-wide">SonicAnalyzer</span>
            </div>
            <div className="h-4 w-px bg-border"></div>
            <span className="text-[10px] font-mono text-text-secondary uppercase">Local DSP Engine</span>
          </div>

          <div className="hidden sm:flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <label className="text-[10px] font-mono text-text-secondary uppercase">Interpretation Model</label>
              <select
                data-testid="phase2-model-desktop"
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                disabled={phase2ModelSelectorDisabled}
                className="appearance-none bg-bg-card border border-border text-text-primary text-[10px] font-mono py-1 pl-2 pr-6 rounded-sm focus:outline-none focus:border-accent cursor-pointer disabled:opacity-50"
              >
                {MODELS.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name}
                  </option>
                ))}
              </select>
            </div>
            {phase2StatusBadge && (
              <span
                data-testid="phase2-status-badge"
                className="text-[10px] font-mono text-text-secondary uppercase"
              >
                {phase2StatusBadge}
              </span>
            )}
            <div className="h-4 w-px bg-border"></div>
            <div className="flex items-center space-x-1">
              <span className="text-[10px] font-mono text-text-secondary uppercase">CPU</span>
              <div className="w-16 h-3 bg-bg-card border border-border rounded-sm overflow-hidden flex items-end p-[1px]">
                <div
                  data-testid="cpu-meter-fill"
                  className={`w-full bg-accent transition-[height] duration-200 ${isAnalyzing ? 'animate-pulse' : ''}`}
                  style={{ height: `${cpuMeterPercent}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        <div className="bg-bg-panel p-3 md:p-5 space-y-5 flex-grow">
          <main className="space-y-5">
            <section className="grid grid-cols-1 lg:grid-cols-12 gap-3 md:gap-4">
              <div className="lg:col-span-4 flex flex-col gap-4">
                <div className="flex flex-col">
                  <div className="bg-bg-surface-dark border border-border border-b-0 rounded-t-sm px-3 py-1.5 flex items-center">
                    <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
                    <h3 className="text-[10px] font-mono text-text-secondary uppercase tracking-wider">Input Source</h3>
                  </div>
                  <div
                    data-testid="input-panel"
                    className="bg-bg-card border border-border rounded-b-sm p-4 flex flex-col min-h-[220px]"
                  >
                    <FileUpload
                      onFileSelect={handleFileSelect}
                      onFileClear={handleFileClear}
                      onLoadDemoTrack={handleLoadDemoTrack}
                      isLoading={isAnalyzing}
                      isDemoLoading={isDemoLoading}
                      selectedFile={audioFile}
                    />
                    <label
                      className={`mt-4 rounded-sm border px-3 py-3 transition-colors cursor-pointer ${
                        symbolicExtractionRequested
                          ? 'border-accent bg-accent/10 text-accent'
                          : 'border-border bg-bg-panel text-text-secondary'
                      } ${isAnalyzing ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={symbolicExtractionRequested}
                          onChange={(e) => setSymbolicExtractionRequested(e.target.checked)}
                          disabled={isAnalyzing}
                          aria-label="SYMBOLIC EXTRACTION"
                          className="mt-0.5 h-4 w-4 accent-accent"
                        />
                        <div className="space-y-1">
                          <p className="text-[10px] font-mono uppercase tracking-wider">SYMBOLIC EXTRACTION</p>
                          <p className="text-[10px] font-mono uppercase tracking-wide opacity-80">
                            Best-effort local note extraction from separated stems
                          </p>
                        </div>
                      </div>
                    </label>
                    <label
                      className={`mt-3 rounded-sm border px-3 py-3 transition-colors cursor-pointer ${
                        interpretationRequested && phase2ConfigEnabled
                          ? 'border-accent bg-accent/10 text-accent'
                          : 'border-border bg-bg-panel text-text-secondary'
                      } ${isAnalyzing || !phase2ConfigEnabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={interpretationRequested}
                          onChange={(e) => handleInterpretationRequestedChange(e.target.checked)}
                          disabled={isAnalyzing || !phase2ConfigEnabled}
                          aria-label="AI INTERPRETATION"
                          className="mt-0.5 h-4 w-4 accent-accent"
                        />
                        <div className="space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-[10px] font-mono uppercase tracking-wider">AI INTERPRETATION</p>
                            {phase2StatusBadge && (
                              <span
                                data-testid="phase2-status-inline"
                                className="text-[10px] font-mono uppercase tracking-wider opacity-80"
                              >
                                {phase2StatusBadge}
                              </span>
                            )}
                          </div>
                          <p className="text-[10px] font-mono uppercase tracking-wide opacity-80">
                            {phase2HelperCopy}
                          </p>
                        </div>
                      </div>
                    </label>
                    <div className="mt-3 rounded-sm border border-border bg-bg-panel p-3 sm:hidden">
                      <div className="flex items-center justify-between gap-3">
                        <label
                          htmlFor="phase2-model-mobile"
                          className="text-[10px] font-mono uppercase tracking-wider text-text-secondary"
                        >
                          Interpretation Model
                        </label>
                        <select
                          id="phase2-model-mobile"
                          data-testid="phase2-model-mobile"
                          value={selectedModel}
                          onChange={(e) => setSelectedModel(e.target.value)}
                          disabled={phase2ModelSelectorDisabled}
                          className="min-w-0 flex-1 appearance-none bg-bg-card border border-border text-text-primary text-[10px] font-mono py-1 pl-2 pr-6 rounded-sm focus:outline-none focus:border-accent cursor-pointer disabled:opacity-50"
                        >
                          {MODELS.map((model) => (
                            <option key={model.id} value={model.id}>
                              {model.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                    {!measurementResult && audioFile && (
                      <>
                        <div className="mt-3 rounded-sm border border-border bg-bg-panel p-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <p className="text-[10px] font-mono text-text-secondary uppercase tracking-wider">Estimated local analysis</p>
                            <p className="text-xs font-mono font-bold tracking-wider text-text-primary">
                              {isEstimateLoading
                                ? 'Calculating...'
                                : analysisEstimate
                                  ? formatEstimateRange(analysisEstimate)
                                  : 'Unavailable'}
                            </p>
                          </div>
                          {estimateError && (
                            <p
                              className={`text-[10px] font-mono text-warning ${
                                estimateWrongService ? 'leading-relaxed' : 'uppercase tracking-wider'
                              }`}
                            >
                              {estimateWrongService ? estimateError : `Estimate unavailable: ${estimateError}`}
                            </p>
                          )}
                        </div>
                        <div className="mt-4 flex justify-end">
                          <button
                            onClick={handleStartAnalysis}
                            disabled={isAnalyzeDisabled}
                            className="bg-accent hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed text-bg-app font-bold py-2 px-6 rounded-sm flex items-center transition-colors uppercase tracking-wider font-mono text-xs"
                            title={estimateWrongService ? 'Point the UI at the Sonic Analyzer backend to enable analysis.' : undefined}
                          >
                            <Sparkles className="w-3 h-3 mr-2" />
                            Initiate Analysis
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </div>

              <div className="lg:col-span-8 flex flex-col">
                <div className="bg-bg-surface-dark border border-border border-b-0 rounded-t-sm px-3 py-1.5 flex items-center justify-between">
                  <div className="flex items-center">
                    <span className={`w-2 h-2 rounded-full mr-2 ${audioUrl ? 'bg-success' : 'bg-border'}`}></span>
                    <h3 className="text-[10px] font-mono text-text-secondary uppercase tracking-wider">Signal Monitor</h3>
                  </div>
                </div>

                <div
                  data-testid="signal-panel"
                  className="flex-grow bg-bg-card border border-border rounded-b-sm p-4 relative flex flex-col"
                >
                  {audioUrl && audioFile ? (
                    <div className="flex flex-col relative z-10 gap-4">
                      <WaveformPlayer audioUrl={audioUrl} audioFile={audioFile} onAudioElement={handleAudioElement} />

                      {shouldShowStatusPanel && (
                        <AnalysisStatusPanel
                          run={analysisRun}
                          elapsedMs={elapsedMs}
                          estimate={analysisEstimate}
                          isActive={isAnalyzing}
                          onStopMonitoring={handleStopMonitoring}
                          onRetryMeasurement={audioFile ? handleStartAnalysis : undefined}
                          onRetrySymbolic={analysisRun && ['failed', 'interrupted'].includes(analysisRun.stages.symbolicExtraction.status) ? handleRetrySymbolicExtraction : undefined}
                          onRetryInterpretation={analysisRun && ['failed', 'interrupted'].includes(analysisRun.stages.interpretation.status) ? handleRetryInterpretation : undefined}
                        />
                      )}
                    </div>
                  ) : (
                    <IdleSignalMonitor />
                  )}
                </div>
              </div>
            </section>

            {error && (
              <div className="p-3 bg-error/10 border border-error/30 rounded-sm text-error text-xs font-mono flex items-center justify-between gap-3">
                <div className="flex items-center min-w-0">
                  <div className="w-2 h-2 bg-error rounded-full mr-2 shrink-0"></div>
                  <span className="truncate">ERROR: {error}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {errorRetryable && audioFile && (
                    <button
                      onClick={handleStartAnalysis}
                      disabled={isAnalyzing}
                      className="px-2 py-1 bg-accent/20 text-accent border border-accent/30 rounded-sm hover:bg-accent/30 transition-colors uppercase tracking-wider text-[10px] disabled:opacity-50"
                    >
                      Retry
                    </button>
                  )}
                  <button
                    onClick={() => {
                      setError(null);
                      setErrorRetryable(false);
                    }}
                    className="p-1 hover:bg-error/20 rounded-sm transition-colors"
                    title="Dismiss error"
                    aria-label="Dismiss error"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}

            {phase1ForRender ? (
              <Suspense
                fallback={
                  <div className="space-y-6">
                    <div className="h-8 w-48 bg-bg-card rounded-sm animate-pulse" />
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      {Array.from({ length: 4 }).map((_, i) => (
                        <div key={i} className="bg-bg-panel border border-border rounded-sm p-4 min-h-[170px] animate-pulse" />
                      ))}
                    </div>
                    <div className="h-40 bg-bg-panel border border-border rounded-sm animate-pulse" />
                  </div>
                }
              >
                <AnalysisResults
                  phase1={phase1ForRender}
                  phase2={phase2Result}
                  phase2StatusMessage={phase2StatusMessage}
                  sourceFileName={audioFile?.name ?? null}
                />
              </Suspense>
            ) : null}
            <DiagnosticLog logs={logs} defaultExpanded={isAnalyzing} />
          </main>
        </div>
      </div>
      {isDraggingFile && (
        <div className="pointer-events-none fixed inset-0 z-50">
          <div className="absolute inset-0 bg-bg-app/85 backdrop-blur-sm" />
          <div className="relative flex h-full items-center justify-center p-6">
            <div className="w-full max-w-2xl rounded-sm border border-accent/40 bg-bg-panel/90 px-8 py-10 text-center shadow-[0_0_30px_rgba(255,136,0,0.18)]">
              <p className="text-[11px] font-mono uppercase tracking-[0.3em] text-text-secondary">
                Global Input
              </p>
              <p className="mt-4 text-3xl font-display font-bold uppercase tracking-[0.12em] text-accent">
                Drop Audio Here
              </p>
              <p className="mt-3 text-[11px] font-mono uppercase tracking-[0.18em] text-text-secondary">
                Release to replace the current track
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

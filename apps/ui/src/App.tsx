import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { AudioWaveform, Play, X } from 'lucide-react';

import { AnalysisStatusPanel } from './components/AnalysisStatusPanel';
import { DiagnosticLog } from './components/DiagnosticLog';
import { FileUpload } from './components/FileUpload';
import { InputSettingsForm } from './components/InputSettingsForm';
import { WaveformPlayer } from './components/WaveformPlayer';
import { Button, DeviceRack } from './components/ui';
// Audit Finding #5: IdleValuePropPanel now occupies the Signal Monitor area
// when no file is selected. It tells the producer what ASA does and what to
// expect in 30s / 5min.
import { IdleValuePropPanel } from './components/IdleValuePropPanel';
import { useGlobalDrag } from './hooks/useGlobalDrag';
import {
  appConfig,
  isGeminiPhase2ConfigEnabled,
  isMt3ConfigEnabled,
} from './config';
import { getAudioMimeTypeOrDefault, isSupportedAudioFile } from './services/audioFile';
import { analyzeAudio, monitorAnalysisRun } from './services/analyzer';
import {
  createInterpretationAttempt,
  createPitchNoteTranslationAttempt,
  estimateAnalysisRun,
  getPhase2SchemaVersionFromRun,
  interruptAnalysisRun,
  projectPhase1FromRun,
  projectPhase2FromRun,
  projectPhase2ValidationWarningsFromRun,
  projectStemSummaryFromRun,
} from './services/analysisRunsClient';
import { buildDisplayDiagnosticLogs } from './services/diagnosticLogs';
import {
  BackendClientError,
  deriveAnalyzeTimeoutMs,
  mapBackendError,
} from './services/backendPhase1Client';
import { MEASUREMENT_LABEL, INTERPRETATION_LABEL } from './services/phaseLabels';
import { validatePhase2Consistency } from './services/phase2Validator';
import {
  AnalysisRunSnapshot,
  AnalysisStageStatus,
  BackendAnalysisEstimate,
  DiagnosticLogEntry,
  Phase1Result,
} from './types';
import type { AnalysisResultsProps } from './components/AnalysisResults';
import { ErrorBoundary } from './components/ErrorBoundary';
import {
  loadPhase2RequestedPreference,
  savePhase2RequestedPreference,
} from './utils/phase2Preference';
// Audit quick-hit: `getAppViewHref` import retired — its only consumer
// was the Dense DAW Lab header link, which was removed in this PR. The
// helper is still exported for any future re-introduction (e.g. behind a
// settings menu) and from `main.tsx` for the active-view router.
import { startRenderBenchmarkCycle } from './utils/renderBenchmark';

// Vertex Gemini 3.x / 3.5 require location=global (us-central1 404s them).
// gemini-3.5-flash is the current default recommended model for this project.
// gemini-3.1-flash-preview stays omitted from the picker (historical 404s on
// AI Studio); backend ALLOWED_GEMINI_MODELS still lists it if needed.
const MODELS = [
  { id: 'gemini-3.5-flash', name: 'Gemini 3.5 Flash (Recommended)' },
  { id: 'gemini-3.1-pro-preview', name: 'Gemini 3.1 Pro Preview' },
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

// Audit N9: M:SS duration for the collapsed Input Source summary card. Returns
// null for missing/invalid values so callers can skip the chip without juggling
// conditionals around a placeholder string.
export function formatTrackDuration(seconds: number | null | undefined): string | null {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return null;
  // Round to whole seconds first so 59.5s never produces "0:60" — the modulo
  // would carry past the seconds boundary without bumping the minutes.
  const total = Math.round(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function getInterpretationStatusBadge(
  phase2ConfigEnabled: boolean,
  phase2Requested: boolean,
): string | null {
  if (!phase2ConfigEnabled) return 'NOT CONFIGURED';
  if (!phase2Requested) return 'OFF';
  return null;
}

function getInterpretationHelperCopy(
  phase2ConfigEnabled: boolean,
  phase2Requested: boolean,
): string {
  if (!phase2ConfigEnabled) {
    // Audit #12: drop developer-flavored copy. Give the user a concrete next step
    // instead of a config-state assertion. On hosted deployments, an operator
    // configures GEMINI_API_KEY on the backend; on local setups the user does it themselves.
    return 'AI interpretation isn’t configured. Configure Gemini (Vertex AI or GEMINI_API_KEY) on the backend to enable Ableton recommendations.';
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
    case 'pitchNoteTranslation':
      return 'Pitch/Note Translation';
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
      : stageKey === 'pitchNoteTranslation'
        ? run.stages.pitchNoteTranslation
        : run.stages.interpretation;
  const error = stage.error;

  if (status === 'failed' || status === 'interrupted') {
    return error?.message ?? `${stageDisplayLabel(stageKey)} ${status}.`;
  }

  if (status === 'completed') {
    switch (stageKey) {
      case 'measurement':
        return 'Measurement complete.';
      case 'pitchNoteTranslation':
        return 'Pitch/Note Translation complete.';
      case 'interpretation':
        return 'AI interpretation complete.';
      default:
        return 'Stage complete.';
    }
  }

  if (status === 'not_requested') {
    return stageKey === 'interpretation'
      ? 'AI interpretation skipped.'
      : 'Pitch/Note Translation was not requested.';
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

  const [phase2StatusMessage, setPhase2StatusMessage] = useState<string | null>(null);
  const [logs, setLogs] = useState<DiagnosticLogEntry[]>([]);
  const [analysisRun, setAnalysisRun] = useState<AnalysisRunSnapshot | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isDemoLoading, setIsDemoLoading] = useState(false);
  // Audit N9: after analysis completes the Input Source panel collapses into a
  // compact summary so the results below get the full top-of-page real estate.
  // The user can re-open it via "Adjust settings"; the override resets at the
  // start of each new analysis (useEffect below) so subsequent completions also
  // collapse — that's the predictable behavior.
  const [inputManuallyExpanded, setInputManuallyExpanded] = useState(false);

  const [analysisEstimate, setAnalysisEstimate] = useState<BackendAnalysisEstimate | null>(null);
  const [isEstimateLoading, setIsEstimateLoading] = useState(false);
  const [estimateError, setEstimateError] = useState<string | null>(null);
  const [estimateWrongService, setEstimateWrongService] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [analysisMode, setAnalysisMode] = useState<'full' | 'standard'>('full');
  const [pitchNoteTranslationRequested, setPitchNoteTranslationRequested] = useState(true);
  const [mt3Requested, setMt3Requested] = useState(false);

  const analysisStartedAtRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const currentRunIdRef = useRef<string | null>(null);
  const ignoredRunIdsRef = useRef<Set<string>>(new Set());
  // Set when the user stops monitoring; consulted by the run's onError to
  // suppress any error banner for the stopped run. The per-run id guard
  // (shouldIgnoreRun) can't cover this alone — clearActiveRunState nulls
  // currentRunIdRef, so a late rejection would read shouldIgnoreRun(null).
  const userStoppedRef = useRef(false);
  const phase2ConfigEnabled = isGeminiPhase2ConfigEnabled();
  const mt3ConfigEnabled = isMt3ConfigEnabled();
  const interpretationWillRun = interpretationRequested && phase2ConfigEnabled;
  const phase2StatusBadge = getInterpretationStatusBadge(phase2ConfigEnabled, interpretationRequested);
  const phase2HelperCopy = getInterpretationHelperCopy(phase2ConfigEnabled, interpretationRequested);
  const phase2ModelSelectorDisabled = isAnalyzing || !phase2ConfigEnabled || !interpretationRequested;
  const audioElementRef = useRef<HTMLAudioElement | null>(null);

  // Audit N9: reset the manual-expand override whenever a new analysis kicks
  // off, so every completion re-collapses (predictable). Without this, a user
  // who clicked "Adjust settings" once would have the panel stay open forever.
  useEffect(() => {
    if (isAnalyzing) setInputManuallyExpanded(false);
  }, [isAnalyzing]);
  const previousRunRef = useRef<AnalysisRunSnapshot | null>(null);
  const completionRef = useRef<{ measurement: boolean; interpretation: boolean }>({
    measurement: false,
    interpretation: false,
  });

  const clearActiveRunState = useCallback(() => {
    setPhase2StatusMessage(null);
    setLogs([]);
    setAnalysisRun(null);
    setActiveRunId(null);
    previousRunRef.current = null;
    completionRef.current = { measurement: false, interpretation: false };
    analysisStartedAtRef.current = null;
    abortControllerRef.current = null;
    currentRunIdRef.current = null;
    setElapsedMs(0);
  }, []);

  const shouldIgnoreRun = useCallback((runId: string | null | undefined) => {
    return Boolean(runId && ignoredRunIdsRef.current.has(runId));
  }, []);

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

    estimateAnalysisRun(audioFile, {
      apiBaseUrl: appConfig.apiBaseUrl,
      analysisMode,
      pitchNoteMode: pitchNoteTranslationRequested ? 'stem_notes' : 'off',
      pitchNoteBackend: 'auto',
      interpretationMode: interpretationWillRun ? 'async' : 'off',
      interpretationProfile: 'producer_summary',
      interpretationModel: interpretationWillRun ? selectedModel : undefined,
      mt3Mode: mt3Requested && mt3ConfigEnabled ? 'enabled' : 'off',
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
  }, [analysisMode, audioFile, interpretationWillRun, mt3Requested, mt3ConfigEnabled, pitchNoteTranslationRequested, selectedModel]);

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
    ignoredRunIdsRef.current.clear();
    setAudioFile(file);
    setAudioUrl(URL.createObjectURL(file));
    clearActiveRunState();
    setError(null);
    setEstimateWrongService(false);
    setIsDemoLoading(false);
  }, [audioUrl, clearActiveRunState]);

  const handleFileClear = useCallback(() => {
    ignoredRunIdsRef.current.clear();
    setAudioFile(null);
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioUrl(null);
    clearActiveRunState();
    setError(null);
    setAnalysisEstimate(null);
    setEstimateError(null);
    setIsEstimateLoading(false);
    setEstimateWrongService(false);
    setIsDemoLoading(false);
  }, [audioUrl, clearActiveRunState]);

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
        : stageKey === 'pitchNoteTranslation'
          ? run.stages.pitchNoteTranslation.error
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

    if (nextStatus === 'completed' && stageKey === 'pitchNoteTranslation') {
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

  // Overrides let the Session Musician panel re-trigger analysis for a legacy
  // (non-torchcrepe) snapshot with the stem-aware pipeline forced on, without
  // waiting for the React state of the toggle to flush before kicking off
  // the run. The current toggle is also updated so the UI stays consistent.
  type StartAnalysisOverrides = {
    pitchNoteRequested?: boolean;
  };

  const handleStartAnalysis = async (overrides: StartAnalysisOverrides = {}) => {
    if (!audioFile) return;

    const activeFile = audioFile;
    const activeModel = selectedModel;
    const activeEstimate = analysisEstimate;
    const activeTimeoutMs = deriveAnalyzeTimeoutMs(activeEstimate?.totalHighMs);
    const audioMetadata = buildAudioMetadata(activeFile);
    const activePitchNoteRequested =
      overrides.pitchNoteRequested ?? pitchNoteTranslationRequested;
    if (
      overrides.pitchNoteRequested !== undefined &&
      overrides.pitchNoteRequested !== pitchNoteTranslationRequested
    ) {
      setPitchNoteTranslationRequested(overrides.pitchNoteRequested);
    }

    startRenderBenchmarkCycle(window);
    ignoredRunIdsRef.current.clear();
    userStoppedRef.current = false;

    const ac = new AbortController();
    abortControllerRef.current = ac;
    currentRunIdRef.current = null;

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
          if (shouldIgnoreRun(currentRunIdRef.current)) {
            return;
          }
          setLogs((prev) => {
            const nextLogs = replaceRunningLog(prev, 'measurement', {
              ...log,
              status: 'success',
              message: log.message ?? 'Measurement complete.',
              estimateLowMs: activeEstimate?.totalLowMs,
              estimateHighMs: activeEstimate?.totalHighMs,
            });
            return nextLogs;
          });
          completionRef.current.measurement = true;
        },
        (result, log) => {
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

          // The user stopped this run: suppress any error it emits, including a
          // non-cancelled rejection that loses the race with the stop handler.
          if (userStoppedRef.current) {
            return;
          }

          if (shouldIgnoreRun(currentRunIdRef.current)) {
            return;
          }

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
          analysisMode,
          pitchNoteRequested: activePitchNoteRequested,
          mt3Requested,
          timeoutMs: activeTimeoutMs,
          signal: ac.signal,
          interpretationRequested,
          interpretationConfigEnabled: phase2ConfigEnabled,
          onRunUpdate: (update) => {
            if (shouldIgnoreRun(update.runId)) {
              return;
            }
            currentRunIdRef.current = update.runId;
            setActiveRunId(update.runId);
            setAnalysisRun(update.snapshot);
            if (update.displayPhase2) {
              setPhase2StatusMessage(null);
            } else if (isTerminalStageStatus(update.snapshot.stages.interpretation.status)) {
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
              const pitchNoteStatus = update.snapshot.stages.pitchNoteTranslation.status;
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

              if (!previous || previous.stages.pitchNoteTranslation.status !== pitchNoteStatus) {
                nextLogs = syncStageLog(
                  nextLogs,
                  'pitchNoteTranslation',
                  pitchNoteStatus,
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

  const handleStopAnalysis = useCallback(async () => {
    userStoppedRef.current = true;
    const runId = currentRunIdRef.current ?? activeRunId;
    if (runId) {
      ignoredRunIdsRef.current.add(runId);
      try {
        await interruptAnalysisRun(runId, {
          apiBaseUrl: appConfig.apiBaseUrl,
        });
      } catch {
        // Intentionally suppress interrupt failures; the UI clears the cancelled run immediately.
      }
    }

    abortControllerRef.current?.abort();
    clearActiveRunState();
    setIsAnalyzing(false);
    setError(null);
    setErrorRetryable(false);
  }, [activeRunId, clearActiveRunState]);

  const handleRetryPitchNoteExtraction = useCallback(async () => {
    if (!audioFile || !activeRunId) return;

    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsAnalyzing(true);
    setError(null);
    setErrorRetryable(false);
    analysisStartedAtRef.current = Date.now();

    try {
      await createPitchNoteTranslationAttempt(activeRunId, {
        apiBaseUrl: appConfig.apiBaseUrl,
        pitchNoteMode: 'stem_notes',
        pitchNoteBackend: 'auto',
        signal: controller.signal,
      });
      await monitorAnalysisRun(
        activeRunId,
        audioFile,
        selectedModel,
        (result, log) => {
          if (shouldIgnoreRun(currentRunIdRef.current)) {
            return;
          }
          completionRef.current.measurement = true;
          setLogs((prev) => replaceRunningLog(prev, 'measurement', { ...log, status: 'success' }));
        },
        (result, log) => {
          setPhase2StatusMessage(log.message ?? null);
          setLogs((prev) => replaceRunningLog(prev, 'interpretation', { ...log, status: log.status ?? 'success' }));
        },
        (rawError) => {
          const err = rawError instanceof Error ? rawError : new Error(String(rawError));
          if (shouldIgnoreRun(currentRunIdRef.current)) {
            return;
          }
          if (!(err instanceof BackendClientError && err.code === 'USER_CANCELLED')) {
            setError(err.message);
          }
        },
        {
          pitchNoteRequested: pitchNoteTranslationRequested,
          interpretationRequested,
          interpretationConfigEnabled: phase2ConfigEnabled,
          signal: controller.signal,
          onRunUpdate: (update) => {
            if (shouldIgnoreRun(update.runId)) {
              return;
            }
            currentRunIdRef.current = update.runId;
            setActiveRunId(update.runId);
            setAnalysisRun(update.snapshot);
            if (update.displayPhase2) {
              setPhase2StatusMessage(null);
            }
            previousRunRef.current = update.snapshot;
          },
        },
      );
    } catch (rawError) {
      // The monitor's onError handles errors surfaced through polling; this
      // catch covers the awaited create*Attempt POST that runs before the
      // monitor (backend down / 4xx). Mirror onError's shouldIgnoreRun guard so
      // an ignored/cancelled run isn't re-surfaced here.
      if (shouldIgnoreRun(currentRunIdRef.current)) return;
      const err = rawError instanceof Error ? rawError : new Error(String(rawError));
      if (!(err instanceof BackendClientError && err.code === 'USER_CANCELLED')) {
        setError(err.message);
        setErrorRetryable(err instanceof BackendClientError && err.details?.retryable === true);
      }
    } finally {
      setIsAnalyzing(false);
      abortControllerRef.current = null;
      analysisStartedAtRef.current = null;
      setElapsedMs(0);
    }
  }, [activeRunId, audioFile, interpretationRequested, phase2ConfigEnabled, selectedModel, pitchNoteTranslationRequested, shouldIgnoreRun]);

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
          if (shouldIgnoreRun(currentRunIdRef.current)) {
            return;
          }
          completionRef.current.measurement = true;
          setLogs((prev) => replaceRunningLog(prev, 'measurement', { ...log, status: 'success' }));
        },
        (result, log) => {
          setPhase2StatusMessage(log.message ?? null);
          setLogs((prev) => replaceRunningLog(prev, 'interpretation', { ...log, status: log.status ?? 'success' }));
        },
        (rawError) => {
          const err = rawError instanceof Error ? rawError : new Error(String(rawError));
          if (shouldIgnoreRun(currentRunIdRef.current)) {
            return;
          }
          if (!(err instanceof BackendClientError && err.code === 'USER_CANCELLED')) {
            setError(err.message);
          }
        },
        {
          pitchNoteRequested: pitchNoteTranslationRequested,
          interpretationRequested,
          interpretationConfigEnabled: phase2ConfigEnabled,
          signal: controller.signal,
          onRunUpdate: (update) => {
            if (shouldIgnoreRun(update.runId)) {
              return;
            }
            currentRunIdRef.current = update.runId;
            setActiveRunId(update.runId);
            setAnalysisRun(update.snapshot);
            if (update.displayPhase2) {
              setPhase2StatusMessage(null);
            }
            previousRunRef.current = update.snapshot;
          },
        },
      );
    } catch (rawError) {
      // The monitor's onError handles errors surfaced through polling; this
      // catch covers the awaited create*Attempt POST that runs before the
      // monitor (backend down / 4xx). Mirror onError's shouldIgnoreRun guard so
      // an ignored/cancelled run isn't re-surfaced here.
      if (shouldIgnoreRun(currentRunIdRef.current)) return;
      const err = rawError instanceof Error ? rawError : new Error(String(rawError));
      if (!(err instanceof BackendClientError && err.code === 'USER_CANCELLED')) {
        setError(err.message);
        setErrorRetryable(err instanceof BackendClientError && err.details?.retryable === true);
      }
    } finally {
      setIsAnalyzing(false);
      abortControllerRef.current = null;
      analysisStartedAtRef.current = null;
      setElapsedMs(0);
    }
  }, [activeRunId, audioFile, interpretationRequested, phase2ConfigEnabled, selectedModel, pitchNoteTranslationRequested, shouldIgnoreRun]);

  const handleAudioElement = useCallback((el: HTMLAudioElement) => {
    audioElementRef.current = el;
  }, []);

  const diagnosticLogs = React.useMemo(
    () =>
      buildDisplayDiagnosticLogs({
        logs,
        analysisRun,
        audioMetadata: audioFile ? buildAudioMetadata(audioFile) : null,
        interpretationModel: selectedModel,
      }),
    [analysisRun, audioFile, logs, selectedModel],
  );

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
        ['failed', 'interrupted'].includes(analysisRun.stages.pitchNoteTranslation.status) ||
        ['failed', 'interrupted'].includes(analysisRun.stages.interpretation.status)
      ),
  );
  const shouldShowStatusPanel = Boolean(audioUrl && audioFile && analysisRun && (isAnalyzing || hasRetryableRunStage));
  const phase1ForRender: Phase1Result | null = analysisRun ? projectPhase1FromRun(analysisRun) : null;
  // Audit N9: collapse the Input Source panel when results are visible and we
  // aren't actively analyzing. A failed run keeps the panel open so the user
  // can change settings before retry.
  const showInputCollapsed = Boolean(phase1ForRender) && !isAnalyzing && !hasRetryableRunStage && !inputManuallyExpanded;
  const phase2ForRender = analysisRun ? projectPhase2FromRun(analysisRun) : null;
  const stemSummaryForRender = analysisRun ? projectStemSummaryFromRun(analysisRun) : null;
  const phase2SchemaVersion = analysisRun ? getPhase2SchemaVersionFromRun(analysisRun) : null;
  const phase2ValidationWarnings = analysisRun ? projectPhase2ValidationWarningsFromRun(analysisRun) : [];
  // Recompute the chain-of-custody report where the results render so producers
  // see drift / citation / hedging violations on the results surface, not only
  // inside the Diagnostic Log. Same validator the interpretation log entry uses.
  const phase2ConsistencyReport = React.useMemo(() => {
    if (!phase1ForRender || !phase2ForRender) {
      return null;
    }
    // Non-fatal, matching the analyzer's guarded call (see analyzer.ts): the
    // validator is pure logic, but a throw here is on the render path with no
    // error boundary above <App>, so it would blank the entire UI. Degrade to
    // "no report" instead of crashing the results surface.
    try {
      return validatePhase2Consistency(phase1ForRender, phase2ForRender);
    } catch (error) {
      console.error('[App] phase2 consistency validation threw', error);
      return null;
    }
  }, [phase1ForRender, phase2ForRender]);

  return (
    // Wave 1 / W1-01: top-anchor the workbench like Live (not a centered
    // marketing card). Wider max width so INPUT | SIGNAL MONITOR can breathe
    // at desktop the way design/reference/01 + 06 do.
    <div className="min-h-screen bg-bg-app px-3 py-3 md:px-5 md:py-4 font-sans flex items-start justify-center">
      <div
        data-testid="app-shell"
        className="ableton-shell w-full max-w-7xl rounded-sm overflow-hidden flex flex-col"
      >
        <div
          data-testid="app-toolbar"
          className="ableton-toolbar h-10 border-b border-border flex items-center justify-between px-4"
        >
          {/* Audit #7+#9: dropped "Local DSP Engine v1.6.0" eyebrow. Version was
              header noise and wrapped to 3 lines at 375px. The brand mark alone
              is enough at-a-glance; version lives on the about/help surface. */}
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <AudioWaveform className="w-4 h-4 text-accent" />
              <span className="text-xs font-bold text-text-primary tracking-wide">SonicAnalyzer</span>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-4">
            {/* Audit quick-hit: removed the Dense DAW Lab link from the
              header. A prior pass had already demoted it to muted text, but
              the audit re-flagged it for sitting in the primary flow's
              header without context for what it is. The route stays
              accessible via direct URL (?view=daw-concept) — see
              `getAppViewHref('daw-concept')` and `main.tsx`. */}
            <div className="hidden sm:flex items-center space-x-4">
              {/* Audit quick-hit: dropped the "Interpretation Model" label
                and shrank the select to a discreet text-secondary dropdown.
                The audit flagged the prior styling as foregrounding an
                AI-model choice an intermediate producer has no basis to
                make. Selector stays accessible (smoke spec requires it
                visible at desktop viewport) but now reads as background
                metadata, not a primary control. Title attribute carries
                the long-form context. */}
              <select
                data-testid="phase2-model-desktop"
                aria-label="Interpretation model"
                title="AI model used for Phase 2 interpretation (advanced)"
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                disabled={phase2ModelSelectorDisabled}
                className="appearance-none bg-transparent border-none text-text-secondary/70 hover:text-text-primary text-meta font-mono py-0 pl-0 pr-4 rounded-sm focus:outline-none focus:text-text-primary cursor-pointer disabled:opacity-50 transition-colors"
              >
                {MODELS.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name}
                  </option>
                ))}
              </select>
              {phase2StatusBadge && (
                <span
                  data-testid="phase2-status-badge"
                  className="text-meta font-mono text-text-secondary uppercase"
                >
                  {phase2StatusBadge}
                </span>
              )}
              {/* Audit #11: dropped the CPU meter. Analysis happens in the
                  backend subprocess — the browser tab's CPU has no useful
                  relationship to "how hard the analysis is working." The pulsing
                  bar implied effort the page wasn't actually doing. */}
            </div>
          </div>
        </div>

        <div className="bg-bg-panel p-3 md:p-4 space-y-4 flex-grow">
          <main className="space-y-4">
            {/* W1-01 dual-rack: 4|8 grid kept for responsive-layout smoke
                (.lg:col-span-4 / .lg:col-span-8). items-stretch + h-full make
                both DeviceRacks share one instrument row height like Live. */}
            <section
              data-testid="dual-rack"
              className="grid grid-cols-1 lg:grid-cols-12 gap-3 md:gap-3 items-stretch"
            >
              <div className="lg:col-span-4 flex flex-col min-h-0">
                <DeviceRack
                  name="Input Source"
                  status={audioFile ? (isAnalyzing ? 'active' : 'success') : 'idle'}
                  signalOut={audioFile ? (isAnalyzing ? 'active' : 'success') : 'idle'}
                  className="h-full flex flex-col"
                >
                  {/* bg-bg-card on the inner div: locked by
                      tests/smoke/theme-shell.spec.ts:41 which asserts the
                      input-panel computed background is rgb(68, 68, 68)
                      (#444444 = --color-bg-card). The DeviceRack's body is
                      transparent by default so the rack's gradient face
                      would show through; we explicitly flatten the body
                      here to preserve the palette contract. */}
                  <div
                    data-testid="input-panel"
                    className="bg-bg-card flex flex-col flex-1 min-h-[280px] lg:min-h-[420px] p-4"
                  >
                    {showInputCollapsed && audioFile ? (
                      // Audit N9: compact post-analysis summary. Replaces the
                      // FileUpload dropzone + 3 toggles + estimate + run button
                      // with one-line context + two actions. The user can swap
                      // files or re-open the full panel from here.
                      <div
                        data-testid="input-panel-collapsed"
                        className="space-y-3"
                      >
                        <div className="rounded-sm border border-border bg-bg-panel px-3 py-3 space-y-2">
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-meta font-mono uppercase tracking-wider text-text-secondary">Analyzed</p>
                            {(() => {
                              const formatted = formatTrackDuration(phase1ForRender?.durationSeconds);
                              return formatted ? (
                                <span className="text-meta font-mono text-text-secondary uppercase tracking-wider shrink-0">
                                  {formatted}
                                </span>
                              ) : null;
                            })()}
                          </div>
                          <p
                            className="text-xs font-mono text-text-primary truncate"
                            title={audioFile.name}
                          >
                            {audioFile.name}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="secondary"
                            size="md"
                            onClick={handleFileClear}
                            className="flex-1"
                          >
                            ↺ Analyze new file
                          </Button>
                          <Button
                            variant="secondary"
                            size="md"
                            onClick={() => setInputManuallyExpanded(true)}
                          >
                            Adjust settings
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <>
                        {phase1ForRender && inputManuallyExpanded && !isAnalyzing && (
                          // Audit N9: re-expanded post-results — give the user a way back
                          // to the compact view without having to clear the file.
                          <div className="mb-3 flex items-center justify-between gap-3">
                            <p className="text-meta font-mono uppercase tracking-wider text-text-secondary">
                              Editing analysis settings
                            </p>
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => setInputManuallyExpanded(false)}
                            >
                              Hide
                            </Button>
                          </div>
                        )}
                    <FileUpload
                      onFileSelect={handleFileSelect}
                      onFileClear={handleFileClear}
                      onLoadDemoTrack={handleLoadDemoTrack}
                      isLoading={isAnalyzing}
                      isDemoLoading={isDemoLoading}
                      selectedFile={audioFile}
                    />
                    <InputSettingsForm
                      isAnalyzing={isAnalyzing}
                      analysisMode={analysisMode}
                      onAnalysisModeChange={setAnalysisMode}
                      pitchNoteTranslationRequested={pitchNoteTranslationRequested}
                      onPitchNoteTranslationRequestedChange={setPitchNoteTranslationRequested}
                      mt3ConfigEnabled={mt3ConfigEnabled}
                      mt3Requested={mt3Requested}
                      onMt3RequestedChange={setMt3Requested}
                      interpretationRequested={interpretationRequested}
                      phase2ConfigEnabled={phase2ConfigEnabled}
                      onInterpretationRequestedChange={handleInterpretationRequestedChange}
                      phase2StatusBadge={phase2StatusBadge}
                      phase2HelperCopy={phase2HelperCopy}
                    />
                    <div className="mt-3 rounded-sm border border-border bg-bg-panel p-3 sm:hidden">
                      <div className="flex items-center justify-between gap-3">
                        <label
                          htmlFor="phase2-model-mobile"
                          className="text-meta font-mono uppercase tracking-wider text-text-secondary"
                        >
                          Interpretation Model
                        </label>
                        <select
                          id="phase2-model-mobile"
                          data-testid="phase2-model-mobile"
                          value={selectedModel}
                          onChange={(e) => setSelectedModel(e.target.value)}
                          disabled={phase2ModelSelectorDisabled}
                          className="min-w-0 flex-1 appearance-none bg-bg-card border border-border text-text-primary text-meta font-mono py-1 pl-2 pr-6 rounded-sm focus:outline-none focus:border-accent cursor-pointer disabled:opacity-50"
                        >
                          {MODELS.map((model) => (
                            <option key={model.id} value={model.id}>
                              {model.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                    {!phase1ForRender && audioFile && (
                      <>
                        <motion.div
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.35, ease: 'easeOut' }}
                          className="mt-3 rounded-sm border border-border hover:border-accent/30 bg-bg-panel p-3 space-y-2 transition-colors"
                        >
                          <div className="flex items-center justify-between">
                            <p className="text-meta font-mono text-text-secondary uppercase tracking-wider">Estimated local analysis</p>
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
                              className={`text-meta font-mono text-warning ${
                                estimateWrongService ? 'leading-relaxed' : 'uppercase tracking-wider'
                              }`}
                            >
                              {estimateWrongService ? estimateError : `Estimate unavailable: ${estimateError}`}
                            </p>
                          )}
                        </motion.div>
                        <motion.div
                          initial={{ opacity: 0, y: 6 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.3, ease: 'easeOut', delay: 0.1 }}
                          className="mt-auto pt-4"
                        >
                          {/* W1-02: full-width Live-style primary — ref 06 RUN ANALYSIS */}
                          <Button
                            variant="primary"
                            size="lg"
                            ledIndicator
                            leadingIcon={<Play className="w-3 h-3 fill-current" />}
                            onClick={() => handleStartAnalysis()}
                            disabled={isAnalyzeDisabled}
                            title={estimateWrongService ? 'Point the UI at the Sonic Analyzer backend to enable analysis.' : undefined}
                            className="w-full"
                          >
                            Run Analysis
                          </Button>
                        </motion.div>
                      </>
                    )}
                      </>
                    )}
                  </div>
                </DeviceRack>
              </div>

              <div className="lg:col-span-8 flex flex-col min-h-0">
                {/* data-testid="signal-panel" lifted onto the DeviceRack so
                    the testid wraps the title strip (containing the
                    visible "Signal Monitor" text the
                    tests/smoke/error-states.spec.ts:524 selector
                    `signalPanel.getByText('Signal Monitor')` looks for).
                    The inner bg-bg-card div preserves the palette
                    contract the theme-shell smoke locks. */}
                <DeviceRack
                  data-testid="signal-panel"
                  name="Signal Monitor"
                  status={isAnalyzing ? 'active' : audioUrl ? 'success' : 'idle'}
                  signalIn={audioFile ? (isAnalyzing ? 'active' : 'success') : 'idle'}
                  className="h-full flex flex-col"
                >
                  <div
                    className="flex-1 bg-bg-card p-4 relative flex flex-col min-h-[280px] lg:min-h-[420px]"
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
                          onStopAnalysis={handleStopAnalysis}
                          onRetryMeasurement={audioFile ? handleStartAnalysis : undefined}
                          onRetryPitchNote={analysisRun && ['failed', 'interrupted'].includes(analysisRun.stages.pitchNoteTranslation.status) ? handleRetryPitchNoteExtraction : undefined}
                          onRetryInterpretation={analysisRun && ['failed', 'interrupted'].includes(analysisRun.stages.interpretation.status) ? handleRetryInterpretation : undefined}
                        />
                      )}
                    </div>
                  ) : (
                    <IdleValuePropPanel />
                  )}
                </div>
                </DeviceRack>
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
                      onClick={() => handleStartAnalysis()}
                      disabled={isAnalyzing}
                      className="px-2 py-1 bg-accent/20 text-accent border border-accent/30 rounded-sm hover:bg-accent/30 transition-colors uppercase tracking-wider text-meta disabled:opacity-50"
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
              <ErrorBoundary title="The analysis results view failed to render">
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
                  phase2={phase2ForRender}
                  stemSummary={stemSummaryForRender}
                  phase2SchemaVersion={phase2SchemaVersion}
                  phase2ValidationWarnings={phase2ValidationWarnings}
                  phase2ConsistencyReport={phase2ConsistencyReport}
                  phase2StatusMessage={phase2StatusMessage}
                  sourceFileName={audioFile?.name ?? null}
                  audioFile={audioFile}
                  spectralArtifacts={analysisRun?.artifacts?.spectral ?? null}
                  measurementAvailability={{
                    analysisMode: analysisRun?.requestedStages.analysisMode,
                    hasRunContext: Boolean(analysisRun),
                  }}
                  apiBaseUrl={appConfig.apiBaseUrl}
                  runId={activeRunId ?? undefined}
                  pitchNoteMode={(analysisRun?.requestedStages.pitchNoteMode ?? null) as 'stem_notes' | 'off' | null}
                  interpretationStatus={analysisRun?.stages.interpretation.status ?? null}
                  // Audit Finding #14 + #15: hash from the backend's source-audio
                  // artifact keys the per-file applied-recommendations tracker
                  // in localStorage. When absent (e.g., legacy run snapshot),
                  // AnalysisResults skips the checkbox affordance.
                  audioContentHash={analysisRun?.artifacts?.sourceAudio?.contentSha256 ?? null}
                  sourceSizeBytes={analysisRun?.artifacts?.sourceAudio?.sizeBytes ?? null}
                  onReanalyzeWithStemAware={
                    audioFile && !isAnalyzing
                      ? () => handleStartAnalysis({ pitchNoteRequested: true })
                      : undefined
                  }
                />
              </Suspense>
              </ErrorBoundary>
            ) : null}
            <DiagnosticLog logs={diagnosticLogs} defaultExpanded={isAnalyzing} />
          </main>
        </div>
      </div>
      {isDraggingFile && (
        <div className="pointer-events-none fixed inset-0 z-50">
          <div className="absolute inset-0 bg-bg-app/85 backdrop-blur-sm" />
          <div className="relative flex h-full items-center justify-center p-6">
            <div className="w-full max-w-2xl rounded-sm border border-accent/40 bg-bg-panel/90 px-8 py-10 text-center shadow-[0_0_30px_rgba(255,136,0,0.18)]">
              <p className="text-eyebrow font-mono uppercase tracking-[0.3em] text-text-secondary">
                Global Input
              </p>
              <p className="mt-4 text-3xl font-display font-bold uppercase tracking-[0.12em] text-accent">
                Drop Audio Here
              </p>
              <p className="mt-3 text-eyebrow font-mono uppercase tracking-[0.18em] text-text-secondary">
                Release to replace the current track
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

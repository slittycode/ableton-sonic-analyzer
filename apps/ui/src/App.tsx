import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import { Activity, AudioWaveform, Sparkles, X } from 'lucide-react';

import { AnalysisStatusPanel } from './components/AnalysisStatusPanel';
import { DiagnosticLog } from './components/DiagnosticLog';
import { FileUpload } from './components/FileUpload';
import { WaveformPlayer } from './components/WaveformPlayer';
import { useCpuMeter } from './hooks/useCpuMeter';
import { useGlobalDrag } from './hooks/useGlobalDrag';
import {
  appConfig,
  isGeminiPhase2ConfigEnabled,
} from './config';
import { getAudioMimeTypeOrDefault, isSupportedAudioFile } from './services/audioFile';
import { analyzeAudio } from './services/analyzer';
import {
  BackendClientError,
  deriveAnalyzeTimeoutMs,
  estimatePhase1WithBackend,
  mapBackendError,
} from './services/backendPhase1Client';
import { PHASE1_LABEL, PHASE2_LABEL } from './services/phaseLabels';
import {
  BackendAnalysisEstimate,
  DiagnosticLogEntry,
  Phase1Result,
  Phase2Result,
} from './types';
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

const AnalysisResults = lazy(() =>
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

function replaceRunningLog(
  logs: DiagnosticLogEntry[],
  source: DiagnosticLogEntry['source'],
  nextLog: DiagnosticLogEntry,
): DiagnosticLogEntry[] {
  return [...logs.filter((entry) => !(entry.source === source && entry.status === 'running')), nextLog];
}

function formatEstimateRange(estimate: BackendAnalysisEstimate): string {
  return `${Math.round(estimate.totalLowMs / 1000)}s-${Math.round(estimate.totalHighMs / 1000)}s`;
}

function getPhase2StatusBadge(
  phase2ConfigEnabled: boolean,
  phase2Requested: boolean,
): string | null {
  if (!phase2ConfigEnabled) return 'PHASE 2 CONFIG OFF';
  if (!phase2Requested) return 'PHASE 2 USER OFF';
  return null;
}

function getPhase2HelperCopy(
  phase2ConfigEnabled: boolean,
  phase2Requested: boolean,
): string {
  if (!phase2ConfigEnabled) {
    return 'Developer kill-switch is off. Gemini advisory is unavailable in this build.';
  }

  if (!phase2Requested) {
    return 'Phase 1 will still run. Turn this on when you want the Gemini advisory pass after local DSP completes.';
  }

  return 'Runs after Phase 1 succeeds and uses the selected Gemini model for advisory reconstruction output.';
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
  const [currentPhase, setCurrentPhase] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [errorRetryable, setErrorRetryable] = useState(false);
  const [selectedModel, setSelectedModel] = useState(MODELS[0].id);
  const [phase2Requested, setPhase2Requested] = useState(() => loadPhase2RequestedPreference());

  const [phase1Result, setPhase1Result] = useState<Phase1Result | null>(null);
  const [phase2Result, setPhase2Result] = useState<Phase2Result | null>(null);
  const [phase2StatusMessage, setPhase2StatusMessage] = useState<string | null>(null);
  const [logs, setLogs] = useState<DiagnosticLogEntry[]>([]);

  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isDemoLoading, setIsDemoLoading] = useState(false);

  const [analysisEstimate, setAnalysisEstimate] = useState<BackendAnalysisEstimate | null>(null);
  const [isEstimateLoading, setIsEstimateLoading] = useState(false);
  const [estimateError, setEstimateError] = useState<string | null>(null);
  const [estimateWrongService, setEstimateWrongService] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [transcribeEnabled, setTranscribeEnabled] = useState(true);
  const [stemSeparationEnabled, setStemSeparationEnabled] = useState(false);

  const phase1CompletedRef = useRef(false);
  const analysisStartedAtRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const phase2ConfigEnabled = isGeminiPhase2ConfigEnabled();
  const phase2WillRun = phase2Requested && phase2ConfigEnabled;
  const phase2StatusBadge = getPhase2StatusBadge(phase2ConfigEnabled, phase2Requested);
  const phase2HelperCopy = getPhase2HelperCopy(phase2ConfigEnabled, phase2Requested);
  const phase2ModelSelectorDisabled = isAnalyzing || !phase2ConfigEnabled || !phase2Requested;
  const cpuMeterPercent = useCpuMeter(isAnalyzing);

  useEffect(() => {
    savePhase2RequestedPreference(phase2Requested);
  }, [phase2Requested]);

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

    estimatePhase1WithBackend(audioFile, {
      apiBaseUrl: appConfig.apiBaseUrl,
      transcribe: transcribeEnabled,
      separate: stemSeparationEnabled,
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
  }, [audioFile, stemSeparationEnabled, transcribeEnabled]);

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
    setPhase1Result(null);
    setPhase2Result(null);
    setPhase2StatusMessage(null);
    setLogs([]);
    setError(null);
    setCurrentPhase(0);
    phase1CompletedRef.current = false;
    analysisStartedAtRef.current = null;
    setElapsedMs(0);
    setEstimateWrongService(false);
    setIsDemoLoading(false);
  }, [audioUrl]);

  const handleFileClear = useCallback(() => {
    setAudioFile(null);
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioUrl(null);
    setPhase1Result(null);
    setPhase2Result(null);
    setPhase2StatusMessage(null);
    setLogs([]);
    setError(null);
    setCurrentPhase(0);
    setAnalysisEstimate(null);
    setEstimateError(null);
    setIsEstimateLoading(false);
    setEstimateWrongService(false);
    phase1CompletedRef.current = false;
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

  const handlePhase2RequestedChange = (requested: boolean) => {
    setPhase2Requested(requested);
  };

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
    setCurrentPhase(1);
    setError(null);
    setErrorRetryable(false);
    setPhase2StatusMessage(null);
    phase1CompletedRef.current = false;
    analysisStartedAtRef.current = Date.now();

    setLogs([
      {
        model: 'local-dsp-engine',
        phase: PHASE1_LABEL,
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
          phase1CompletedRef.current = true;
          setPhase1Result(result);
          setLogs((prev) => {
            const nextLogs = replaceRunningLog(prev, 'backend', {
              ...log,
              status: 'success',
              message: log.message ?? 'Local DSP analysis complete.',
              estimateLowMs: activeEstimate?.totalLowMs,
              estimateHighMs: activeEstimate?.totalHighMs,
            });

            if (!phase2WillRun) {
              return nextLogs;
            }

            return [
              ...nextLogs,
              {
                model: activeModel,
                phase: PHASE2_LABEL,
                promptLength: 0,
                responseLength: 0,
                durationMs: 0,
                audioMetadata,
                timestamp: new Date().toISOString(),
                source: 'gemini',
                status: 'running',
                message: 'Generating advisory output',
              },
            ];
          });
          setCurrentPhase(phase2WillRun ? 2 : 1);
        },
        (result, log) => {
          setPhase2Result(result);
          setPhase2StatusMessage(log.message ?? null);
          setLogs((prev) => {
            const baseMessage =
              log.message ?? (result ? 'Phase 2 advisory complete.' : 'Phase 2 advisory skipped.');
            const validationSummaryLine = getValidationSummaryLine(log.validationReport);
            const logMessage = validationSummaryLine
              ? `${baseMessage}\n${validationSummaryLine}`
              : baseMessage;

            if (phase2WillRun) {
              return replaceRunningLog(prev, 'gemini', {
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
          setCurrentPhase(0);
          setIsAnalyzing(false);
          abortControllerRef.current = null;
          analysisStartedAtRef.current = null;
          setElapsedMs(0);
        },
        (rawError) => {
          const err = rawError instanceof Error ? rawError : new Error(String(rawError));
          const isPhase1Failure = !phase1CompletedRef.current;
          const backendError = err instanceof BackendClientError ? err : null;
          const isCancelled = backendError?.code === 'USER_CANCELLED';

          setLogs((prev) => [
            ...prev.filter(
              (entry) => !(entry.status === 'running' && entry.source === (isPhase1Failure ? 'backend' : 'gemini')),
            ),
            {
              model: isPhase1Failure ? 'local-dsp-engine' : activeModel,
              phase: isPhase1Failure ? PHASE1_LABEL : PHASE2_LABEL,
              promptLength: 0,
              responseLength: 0,
              durationMs: elapsedMs,
              audioMetadata,
              timestamp: new Date().toISOString(),
              requestId: backendError?.details?.requestId,
              source: isPhase1Failure ? 'backend' : 'gemini',
              status: isCancelled ? 'skipped' : 'error',
              message: isCancelled ? 'Analysis cancelled by user.' : err.message,
              errorCode: isCancelled ? undefined : backendError?.details?.serverCode ?? backendError?.code,
              estimateLowMs: isPhase1Failure ? activeEstimate?.totalLowMs : undefined,
              estimateHighMs: isPhase1Failure ? activeEstimate?.totalHighMs : undefined,
              timings: isPhase1Failure ? backendError?.details?.diagnostics?.timings : undefined,
            },
          ]);

          if (!isCancelled) {
            setError(err.message);
            setErrorRetryable(backendError?.details?.retryable === true);
          }
          setIsAnalyzing(false);
          setCurrentPhase(0);
          abortControllerRef.current = null;
          analysisStartedAtRef.current = null;
          setElapsedMs(0);
        },
        {
          transcribe: transcribeEnabled,
          separate: stemSeparationEnabled,
          timeoutMs: activeTimeoutMs,
          signal: ac.signal,
          phase2Requested,
          phase2ConfigEnabled,
        },
      );
    } catch (rawError) {
      const err = rawError instanceof Error ? rawError : new Error(String(rawError));
      setError(err.message);
      setErrorRetryable(err instanceof BackendClientError && err.details?.retryable === true);
      setIsAnalyzing(false);
      setCurrentPhase(0);
      abortControllerRef.current = null;
      analysisStartedAtRef.current = null;
      setElapsedMs(0);
    }
  };

  const handleCancel = () => {
    abortControllerRef.current?.abort();
  };

  const isAnalyzeDisabled = isAnalyzing || estimateWrongService;

  const statusTitle = currentPhase === 2 ? PHASE2_LABEL : PHASE1_LABEL;
  const statusSummary =
    currentPhase === 2
      ? 'Generating the advisory pass from completed local DSP measurements.'
      : 'Running the local DSP engine against the uploaded track.';
  const statusDetail =
    currentPhase === 2
      ? 'Phase 1 is complete. Phase 2 is optional and UI-owned.'
      : 'Measuring tempo, key, loudness, stereo, rhythm, melody, and spectral balance.';
  const statusRequestState = currentPhase === 2 ? 'Generating advisory output' : 'Request in flight';

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
              <label className="text-[10px] font-mono text-text-secondary uppercase">Phase 2 Model</label>
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
                        transcribeEnabled
                          ? 'border-accent bg-accent/10 text-accent'
                          : 'border-border bg-bg-panel text-text-secondary'
                      } ${isAnalyzing ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={transcribeEnabled}
                          onChange={(e) => setTranscribeEnabled(e.target.checked)}
                          disabled={isAnalyzing}
                          aria-label="MIDI TRANSCRIPTION"
                          className="mt-0.5 h-4 w-4 accent-accent"
                        />
                        <div className="space-y-1">
                          <p className="text-[10px] font-mono uppercase tracking-wider">MIDI TRANSCRIPTION</p>
                          <p className="text-[10px] font-mono uppercase tracking-wide opacity-80">
                            Basic Pitch polyphonic analysis (+30-60s)
                          </p>
                        </div>
                      </div>
                    </label>
                    <label
                      className={`mt-3 rounded-sm border px-3 py-3 transition-colors cursor-pointer ${
                        phase2Requested && phase2ConfigEnabled
                          ? 'border-accent bg-accent/10 text-accent'
                          : 'border-border bg-bg-panel text-text-secondary'
                      } ${isAnalyzing || !phase2ConfigEnabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={phase2Requested}
                          onChange={(e) => handlePhase2RequestedChange(e.target.checked)}
                          disabled={isAnalyzing || !phase2ConfigEnabled}
                          aria-label="PHASE 2 ADVISORY"
                          className="mt-0.5 h-4 w-4 accent-accent"
                        />
                        <div className="space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-[10px] font-mono uppercase tracking-wider">PHASE 2 ADVISORY</p>
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
                          Phase 2 Model
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
                    <label
                      className={`mt-3 rounded-sm border px-3 py-3 transition-colors cursor-pointer ${
                        stemSeparationEnabled
                          ? 'border-accent bg-accent/10 text-accent'
                          : 'border-border bg-bg-panel text-text-secondary'
                      } ${isAnalyzing ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={stemSeparationEnabled}
                          onChange={(e) => setStemSeparationEnabled(e.target.checked)}
                          disabled={isAnalyzing}
                          aria-label="STEM SEPARATION"
                          className="mt-0.5 h-4 w-4 accent-accent"
                        />
                        <div className="space-y-1">
                          <p className="text-[10px] font-mono uppercase tracking-wider">STEM SEPARATION</p>
                          <p className="text-[10px] font-mono uppercase tracking-wide opacity-80">
                            Demucs pre-processing for better accuracy (+60-120s)
                          </p>
                        </div>
                      </div>
                    </label>
                    {!phase1Result && audioFile && (
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
                    )}
                  </div>
                </div>
              </div>

              <div className="lg:col-span-8 flex flex-col h-full">
                <div className="bg-bg-surface-dark border border-border border-b-0 rounded-t-sm px-3 py-1.5 flex items-center justify-between">
                  <div className="flex items-center">
                    <span className={`w-2 h-2 rounded-full mr-2 ${audioUrl ? 'bg-success' : 'bg-border'}`}></span>
                    <h3 className="text-[10px] font-mono text-text-secondary uppercase tracking-wider">
                      {isAnalyzing ? 'Local DSP Status' : 'Signal Monitor'}
                    </h3>
                  </div>
                </div>

                <div
                  data-testid="signal-panel"
                  className="flex-grow bg-bg-card border border-border rounded-b-sm p-4 relative flex flex-col"
                >
                  {audioUrl && audioFile ? (
                    isAnalyzing ? (
                      <AnalysisStatusPanel
                        title={statusTitle}
                        summary={statusSummary}
                        detail={statusDetail}
                        requestState={statusRequestState}
                        elapsedMs={elapsedMs}
                        estimate={analysisEstimate}
                        onCancel={handleCancel}
                      />
                    ) : (
                      <div className="h-full flex flex-col justify-between relative z-10 gap-4">
                        <WaveformPlayer audioUrl={audioUrl} audioFile={audioFile} />

                        {!phase1Result && (
                          <div className="rounded-sm border border-border bg-bg-panel p-4 space-y-3">
                            <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
                              <div>
                                <p className="text-[10px] font-mono text-text-secondary uppercase tracking-wider">Local DSP first</p>
                                <p className="mt-2 text-sm font-bold uppercase tracking-wide text-text-primary">Estimated local analysis</p>
                                <p className="mt-1 text-xs font-mono tracking-wider text-text-secondary">
                                  {isEstimateLoading
                                    ? 'Calculating estimate...'
                                    : analysisEstimate
                                      ? formatEstimateRange(analysisEstimate)
                                      : 'Unavailable'}
                                </p>
                              </div>
                              <div className="max-w-xs text-[10px] font-mono uppercase tracking-wider text-text-secondary leading-relaxed">
                                Phase 1 runs on the local DSP backend. Phase 2 advisory only starts after Phase 1 succeeds.
                              </div>
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
                        )}
                      </div>
                    )
                  ) : (
                    <div className="h-full flex flex-col items-center justify-center text-text-secondary opacity-50 font-mono text-xs border border-dashed border-border rounded-sm m-2 min-h-[150px] bg-bg-app">
                      <Activity className="w-8 h-8 mb-2" />
                      NO SIGNAL DETECTED
                    </div>
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

            {phase1Result ? (
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
                  phase1={phase1Result}
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

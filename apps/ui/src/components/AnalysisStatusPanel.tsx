import React from 'react';
import { Activity, Clock3, Radio, TimerReset, RotateCcw, XCircle } from 'lucide-react';

import { AnalysisRunSnapshot, AnalysisStageStatus, BackendAnalysisEstimate } from '../types';

interface AnalysisStatusPanelProps {
  run: AnalysisRunSnapshot | null;
  elapsedMs: number;
  estimate?: BackendAnalysisEstimate | null;
  isActive: boolean;
  onStopMonitoring?: () => void;
  onRetryMeasurement?: () => void;
  onRetrySymbolic?: () => void;
  onRetryInterpretation?: () => void;
}

function formatSecondsLabel(seconds: number): string {
  const totalSeconds = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(totalSeconds / 60);
  const remaining = totalSeconds % 60;
  if (minutes > 0) {
    return `${minutes}m ${remaining}s`;
  }
  return `${remaining}s`;
}

function formatElapsedLabel(elapsedMs: number): string {
  return formatSecondsLabel(elapsedMs / 1000);
}

function formatEstimateRange(estimate: BackendAnalysisEstimate): string {
  return `${formatSecondsLabel(estimate.totalLowMs / 1000)}-${formatSecondsLabel(estimate.totalHighMs / 1000)}`;
}

function computeProgress(elapsedMs: number, estimate?: BackendAnalysisEstimate | null): { percent: number; indeterminate: boolean } {
  if (!estimate) return { percent: 0, indeterminate: true };
  const midpointMs = (estimate.totalLowMs + estimate.totalHighMs) / 2;
  if (midpointMs <= 0) return { percent: 0, indeterminate: true };
  return {
    percent: Math.min((elapsedMs / midpointMs) * 100, 95),
    indeterminate: false,
  };
}

function stageDisplayName(stageKey: 'measurement' | 'symbolicExtraction' | 'interpretation'): string {
  switch (stageKey) {
    case 'measurement':
      return 'Measurement';
    case 'symbolicExtraction':
      return 'Symbolic Extraction';
    case 'interpretation':
      return 'AI Interpretation';
    default:
      return stageKey;
  }
}

function stageStatusLabel(status: AnalysisStageStatus): string {
  return status.replace(/_/g, ' ');
}

function statusClass(status: AnalysisStageStatus): string {
  switch (status) {
    case 'running':
    case 'queued':
      return 'text-accent border-accent/30 bg-accent/10';
    case 'completed':
      return 'text-success border-success/30 bg-success/10';
    case 'failed':
    case 'interrupted':
      return 'text-error border-error/30 bg-error/10';
    case 'not_requested':
      return 'text-warning border-warning/30 bg-warning/10';
    default:
      return 'text-text-secondary border-border bg-bg-panel';
  }
}

type StageKey = 'measurement' | 'symbolicExtraction' | 'interpretation';

interface StageSummaryDescriptor {
  message: string;
  typewriterSeed: string | null;
}

const ESTIMATE_STAGE_PIPELINE_PROGRESS_KEYS: Record<string, string> = {
  demucs_separation: 'separation',
  transcription_stems: 'transcription_stems',
  transcription_full_mix: 'transcription_full_mix',
};

function getStageSnapshot(
  run: AnalysisRunSnapshot,
  stageKey: StageKey,
) {
  return stageKey === 'measurement'
    ? run.stages.measurement
    : stageKey === 'symbolicExtraction'
      ? run.stages.symbolicExtraction
      : run.stages.interpretation;
}

function getRunningProgressMessage(stage: ReturnType<typeof getStageSnapshot>): string | null {
  const progress = stage.diagnostics?.progress;
  if (!progress || typeof progress.message !== 'string') {
    return null;
  }
  const message = progress.message.trim();
  return message.length > 0 ? message : null;
}

export function resolveStageSummary(
  run: AnalysisRunSnapshot | null,
  stageKey: StageKey,
): StageSummaryDescriptor {
  if (!run) {
    return { message: 'Awaiting run state.', typewriterSeed: null };
  }

  const stage = getStageSnapshot(run, stageKey);

  if (stage.error?.message) {
    return { message: stage.error.message, typewriterSeed: null };
  }

  switch (stage.status) {
    case 'queued':
      return { message: 'Queued locally.', typewriterSeed: null };
    case 'running': {
      const progressMessage = getRunningProgressMessage(stage);
      if (progressMessage) {
        return {
          message: progressMessage,
          typewriterSeed: progressMessage,
        };
      }
      return { message: 'Currently processing.', typewriterSeed: null };
    }
    case 'blocked':
      return { message: 'Waiting for measurement to finish.', typewriterSeed: null };
    case 'ready':
      return { message: 'Ready for retry.', typewriterSeed: null };
    case 'completed':
      return {
        message: stageKey === 'measurement'
          ? 'Authoritative local measurement complete.'
          : stageKey === 'symbolicExtraction'
            ? 'Best-effort symbolic output available.'
            : 'Grounded musical interpretation available.',
        typewriterSeed: null,
      };
    case 'failed':
      return { message: 'Stage failed.', typewriterSeed: null };
    case 'interrupted':
      return { message: 'Stage was interrupted and can be retried.', typewriterSeed: null };
    case 'not_requested':
      return { message: 'Not requested for this run.', typewriterSeed: null };
    default:
      return { message: 'Awaiting stage state.', typewriterSeed: null };
  }
}

export function resolveEstimateStageSummary(
  run: AnalysisRunSnapshot | null,
  estimateStageKey: string,
): StageSummaryDescriptor | null {
  if (!run) {
    return null;
  }
  const pipelineKey = ESTIMATE_STAGE_PIPELINE_PROGRESS_KEYS[estimateStageKey];
  if (!pipelineKey) {
    return null;
  }
  const pipelineProgress = run.stages.measurement.diagnostics?.pipelineProgress?.[pipelineKey];
  if (!pipelineProgress || typeof pipelineProgress.message !== 'string') {
    return null;
  }
  const message = pipelineProgress.message.trim();
  if (message.length === 0) {
    return null;
  }
  return {
    message,
    typewriterSeed: pipelineProgress.status === 'running' ? message : null,
  };
}

function TypewriterLine({ text }: { text: string }) {
  const [visibleText, setVisibleText] = React.useState(text);

  React.useEffect(() => {
    if (typeof window === 'undefined') {
      setVisibleText(text);
      return;
    }
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setVisibleText(text);
      return;
    }

    setVisibleText('');
    let cursor = 0;
    const intervalId = window.setInterval(() => {
      cursor += 1;
      setVisibleText(text.slice(0, cursor));
      if (cursor >= text.length) {
        window.clearInterval(intervalId);
      }
    }, 14);

    return () => window.clearInterval(intervalId);
  }, [text]);

  return <span>{visibleText}</span>;
}

export function AnalysisStatusPanel({
  run,
  elapsedMs,
  estimate,
  isActive,
  onStopMonitoring,
  onRetryMeasurement,
  onRetrySymbolic,
  onRetryInterpretation,
}: AnalysisStatusPanelProps) {
  const progress = computeProgress(elapsedMs, estimate);

  const stageCards = [
    {
      key: 'measurement' as const,
      status: run?.stages.measurement.status ?? 'queued',
      onRetry: onRetryMeasurement,
    },
    {
      key: 'symbolicExtraction' as const,
      status: run?.stages.symbolicExtraction.status ?? 'blocked',
      onRetry: onRetrySymbolic,
    },
    {
      key: 'interpretation' as const,
      status: run?.stages.interpretation.status ?? 'blocked',
      onRetry: onRetryInterpretation,
    },
  ];

  return (
    <div className="h-full rounded-sm border border-border bg-bg-panel p-6 flex flex-col justify-between gap-6">
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-mono text-text-secondary uppercase tracking-[0.24em]">Analysis Run</p>
            <h3 className="mt-2 text-lg font-bold uppercase tracking-wide text-text-primary">Canonical Stage Monitor</h3>
            <p className="mt-2 text-sm text-text-primary/90">
              Measurement is authoritative. Symbolic extraction and AI interpretation are tracked independently.
            </p>
            <p className="mt-2 text-xs font-mono text-text-secondary uppercase tracking-wider">
              {run ? `RUN ${run.runId}` : 'Awaiting run id'}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <div className={`flex items-center gap-2 rounded-sm border px-3 py-2 ${isActive ? 'border-accent/30 bg-accent/10 text-accent' : 'border-success/30 bg-success/10 text-success'}`}>
              <Activity className="w-4 h-4" />
              <span className="text-[10px] font-mono uppercase tracking-[0.24em]">{isActive ? 'Monitoring' : 'Idle'}</span>
            </div>
            {onStopMonitoring && isActive && (
              <button
                onClick={onStopMonitoring}
                className="flex items-center gap-1.5 rounded-sm border border-error/30 bg-error/10 px-3 py-2 text-error hover:bg-error/20 transition-colors"
                title="Stop monitoring"
                aria-label="Stop monitoring"
              >
                <XCircle className="w-4 h-4" />
                <span className="text-[10px] font-mono uppercase tracking-[0.24em]">Stop</span>
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="rounded-sm border border-border bg-bg-card p-3">
            <div className="flex items-center gap-2 text-text-secondary">
              <Radio className="w-4 h-4 text-accent" />
              <span className="text-[10px] font-mono uppercase tracking-wider">Request State</span>
            </div>
            <p className="mt-3 text-sm font-bold uppercase tracking-wide text-text-primary">
              {isActive ? 'Polling canonical run' : 'Awaiting next action'}
            </p>
          </div>

          <div className="rounded-sm border border-border bg-bg-card p-3">
            <div className="flex items-center gap-2 text-text-secondary">
              <Clock3 className="w-4 h-4 text-accent" />
              <span className="text-[10px] font-mono uppercase tracking-wider">Elapsed</span>
            </div>
            <p className="mt-3 text-sm font-bold tracking-wide text-text-primary">{formatElapsedLabel(elapsedMs)}</p>
          </div>

          <div className="rounded-sm border border-border bg-bg-card p-3">
            <div className="flex items-center gap-2 text-text-secondary">
              <TimerReset className="w-4 h-4 text-accent" />
              <span className="text-[10px] font-mono uppercase tracking-wider">Estimated local pipeline</span>
            </div>
            <p className="mt-3 text-sm font-bold tracking-wide text-text-primary">
              {estimate ? formatEstimateRange(estimate) : 'Unavailable'}
            </p>
          </div>
        </div>

        <div className="rounded-sm border border-border bg-bg-card p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono uppercase tracking-wider text-text-secondary">Progress</span>
            <span className="text-[10px] font-mono tracking-wider text-text-primary">
              {progress.indeterminate ? 'Estimating...' : `${Math.round(progress.percent)}%`}
            </span>
          </div>
          <div className="w-full h-2 bg-bg-app border border-border/30 rounded-sm overflow-hidden">
            {progress.indeterminate ? (
              <div className="h-full w-1/3 bg-accent/70 rounded-sm animate-pulse" />
            ) : (
              <div
                className={`h-full bg-accent rounded-sm transition-all duration-500 ease-out ${progress.percent >= 95 ? 'animate-pulse' : ''}`}
                style={{ width: `${progress.percent}%` }}
              />
            )}
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {stageCards.map((card) => (
          <div key={card.key} className="rounded-sm border border-border bg-bg-card p-3 space-y-3">
            <div className="flex items-center justify-between gap-4">
              <span className="text-[10px] font-mono uppercase tracking-wider text-text-secondary">{stageDisplayName(card.key)}</span>
              <span className={`px-2 py-1 rounded-sm border text-[10px] font-mono uppercase tracking-wider ${statusClass(card.status)}`}>
                {stageStatusLabel(card.status)}
              </span>
            </div>
            {(() => {
              const summary = resolveStageSummary(run, card.key);
              if (summary.typewriterSeed) {
                return (
                  <p className="text-xs text-text-primary/90">
                    <TypewriterLine text={summary.message} />
                  </p>
                );
              }
              return <p className="text-xs text-text-primary/90">{summary.message}</p>;
            })()}
            {card.onRetry && (card.status === 'failed' || card.status === 'interrupted' || card.status === 'ready') && (
              <button
                onClick={card.onRetry}
                className="inline-flex items-center gap-1.5 rounded-sm border border-accent/30 bg-accent/10 px-3 py-2 text-accent hover:bg-accent/20 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span className="text-[10px] font-mono uppercase tracking-[0.2em]">Retry {stageDisplayName(card.key)}</span>
              </button>
            )}
          </div>
        ))}

        {estimate?.stages?.length ? (
          estimate.stages.map((stage) => (
            <div key={stage.key} className="rounded-sm border border-border bg-bg-card p-3">
              <div className="flex items-center justify-between gap-4">
                <span className="text-[10px] font-mono uppercase tracking-wider text-text-secondary">{stage.label}</span>
                <span className="text-[10px] font-mono tracking-wider text-text-primary">
                  {formatSecondsLabel(stage.lowMs / 1000)}-{formatSecondsLabel(stage.highMs / 1000)}
                </span>
              </div>
              {(() => {
                const summary = resolveEstimateStageSummary(run, stage.key);
                if (!summary) {
                  return null;
                }
                if (summary.typewriterSeed) {
                  return (
                    <p className="mt-2 text-xs text-text-primary/90">
                      <TypewriterLine text={summary.message} />
                    </p>
                  );
                }
                return <p className="mt-2 text-xs text-text-primary/90">{summary.message}</p>;
              })()}
            </div>
          ))
        ) : (
          <div className="rounded-sm border border-dashed border-border p-3 text-[10px] font-mono uppercase tracking-wider text-text-secondary">
            Backend estimate unavailable for this request.
          </div>
        )}
      </div>
    </div>
  );
}

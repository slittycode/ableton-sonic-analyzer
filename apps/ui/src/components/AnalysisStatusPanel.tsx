import React from 'react';
import { Activity, Clock3, Radio, TimerReset, RotateCcw, XCircle } from 'lucide-react';

import { AnalysisRunSnapshot, AnalysisStageStatus, BackendAnalysisEstimate } from '../types';

interface AnalysisStatusPanelProps {
  run: AnalysisRunSnapshot | null;
  elapsedMs: number;
  estimate?: BackendAnalysisEstimate | null;
  isActive: boolean;
  onStopAnalysis?: () => void;
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

function computeEstimateProgress(
  elapsedMs: number,
  estimate?: BackendAnalysisEstimate | null,
): { percent: number; indeterminate: boolean; message: string } {
  if (!estimate) return { percent: 0, indeterminate: true, message: 'Estimating progress...' };
  const midpointMs = (estimate.totalLowMs + estimate.totalHighMs) / 2;
  if (midpointMs <= 0) return { percent: 0, indeterminate: true, message: 'Estimating progress...' };
  return {
    percent: Math.min((elapsedMs / midpointMs) * 100, 95),
    indeterminate: false,
    message: 'Estimating progress from elapsed time.',
  };
}

type StageKey = 'measurement' | 'symbolicExtraction' | 'interpretation';

function getStageSnapshot(run: AnalysisRunSnapshot, stageKey: StageKey) {
  switch (stageKey) {
    case 'measurement':
      return run.stages.measurement;
    case 'symbolicExtraction':
      return run.stages.symbolicExtraction;
    case 'interpretation':
      return run.stages.interpretation;
    default:
      return run.stages.measurement;
  }
}

function getStageProgressDetails(run: AnalysisRunSnapshot | null, stageKey: StageKey): { fraction: number | null; message: string | null } {
  if (!run) {
    return { fraction: null, message: null };
  }

  const diagnostics = getStageSnapshot(run, stageKey).diagnostics;
  const progress = diagnostics && typeof diagnostics === 'object' && diagnostics !== null && 'progress' in diagnostics
    ? diagnostics.progress
    : null;

  if (!progress || typeof progress !== 'object') {
    return { fraction: null, message: null };
  }

  const fraction = typeof progress.fraction === 'number' ? progress.fraction : null;
  const message = typeof progress.message === 'string' ? progress.message : null;
  return { fraction, message };
}

function getTrackedStageKeys(run: AnalysisRunSnapshot | null): StageKey[] {
  if (!run) {
    return ['measurement'];
  }

  const tracked: StageKey[] = ['measurement'];
  if (run.requestedStages.symbolicMode !== 'off') {
    tracked.push('symbolicExtraction');
  }
  if (run.requestedStages.interpretationMode !== 'off') {
    tracked.push('interpretation');
  }
  return tracked;
}

function isStageTerminal(status: AnalysisStageStatus): boolean {
  return ['completed', 'failed', 'interrupted', 'not_requested'].includes(status);
}

function computeLiveProgress(
  run: AnalysisRunSnapshot | null,
): { percent: number; indeterminate: boolean; message: string } | null {
  if (!run) {
    return null;
  }

  const trackedStageKeys = getTrackedStageKeys(run);
  const activeStageKey = trackedStageKeys.find((stageKey) => !isStageTerminal(getStageSnapshot(run, stageKey).status));
  const totalStages = Math.max(trackedStageKeys.length, 1);

  if (!activeStageKey) {
    return { percent: 100, indeterminate: false, message: 'Analysis complete.' };
  }

  const activeStage = getStageSnapshot(run, activeStageKey);
  const progressDetails = getStageProgressDetails(run, activeStageKey);
  const completedBeforeActive = trackedStageKeys.indexOf(activeStageKey);
  const stageFraction = progressDetails.fraction ?? 0;
  const percent = Math.min(((completedBeforeActive + stageFraction) / totalStages) * 100, 100);
  const message = progressDetails.message ?? stageSummary(run, activeStageKey);

  return {
    percent,
    indeterminate: activeStage.status === 'running' && progressDetails.fraction == null,
    message,
  };
}

function stageDisplayName(stageKey: StageKey): string {
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

function stageSummary(run: AnalysisRunSnapshot | null, stageKey: StageKey): string {
  if (!run) {
    return 'Awaiting run state.';
  }

  const stage = getStageSnapshot(run, stageKey);
  const progressDetails = getStageProgressDetails(run, stageKey);

  if (stage.error?.message) {
    return stage.error.message;
  }

  switch (stage.status) {
    case 'queued':
      return 'Queued locally.';
    case 'running':
      return progressDetails.message ?? 'Currently processing.';
    case 'blocked':
      return 'Waiting for measurement to finish.';
    case 'ready':
      return 'Ready for retry.';
    case 'completed':
      return stageKey === 'measurement'
        ? 'Authoritative local measurement complete.'
        : stageKey === 'symbolicExtraction'
          ? 'Best-effort symbolic output available.'
          : 'Grounded musical interpretation available.';
    case 'failed':
      return 'Stage failed.';
    case 'interrupted':
      return 'Stage was interrupted and can be retried.';
    case 'not_requested':
      return 'Not requested for this run.';
    default:
      return 'Awaiting stage state.';
  }
}

export function AnalysisStatusPanel({
  run,
  elapsedMs,
  estimate,
  isActive,
  onStopAnalysis,
  onRetryMeasurement,
  onRetrySymbolic,
  onRetryInterpretation,
}: AnalysisStatusPanelProps) {
  const progress = computeLiveProgress(run) ?? computeEstimateProgress(elapsedMs, estimate);

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
            {onStopAnalysis && isActive && (
              <button
                onClick={onStopAnalysis}
                className="flex items-center gap-1.5 rounded-sm border border-error/30 bg-error/10 px-3 py-2 text-error hover:bg-error/20 transition-colors"
                title="Stop analysis"
                aria-label="Stop analysis"
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
              {progress.indeterminate ? 'Live update...' : `${Math.round(progress.percent)}%`}
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
          <p className="text-[10px] font-mono uppercase tracking-wider text-text-secondary">
            {progress.message}
          </p>
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
            <p className="text-xs text-text-primary/90">{stageSummary(run, card.key)}</p>
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

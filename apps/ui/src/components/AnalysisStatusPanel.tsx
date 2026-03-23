import React from 'react';
import { RotateCcw, Square } from 'lucide-react';

import { AnalysisRunSnapshot, AnalysisStageStatus, BackendAnalysisEstimate } from '../types';

interface AnalysisStatusPanelProps {
  run: AnalysisRunSnapshot | null;
  elapsedMs: number;
  estimate?: BackendAnalysisEstimate | null;
  isActive: boolean;
  onStopMonitoring?: () => void;
  onRetryMeasurement?: () => void;
  onRetryPitchNote?: () => void;
  onRetryInterpretation?: () => void;
}

function formatElapsed(ms: number): string {
  const totalSeconds = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const remaining = totalSeconds % 60;
  return minutes > 0
    ? `${minutes}:${remaining.toString().padStart(2, '0')}`
    : `0:${remaining.toString().padStart(2, '0')}`;
}

function formatEstimateRange(estimate: BackendAnalysisEstimate): string {
  const lo = Math.round(estimate.totalLowMs / 1000);
  const hi = Math.round(estimate.totalHighMs / 1000);
  return `${lo}s-${hi}s`;
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

type StageKey = 'measurement' | 'pitchNoteTranslation' | 'interpretation';

const STAGE_LABELS: Record<StageKey, string> = {
  measurement: 'MEASURE',
  pitchNoteTranslation: 'PITCH/NOTE',
  interpretation: 'INTERPRET',
};

function statusDotClass(status: AnalysisStageStatus): string {
  switch (status) {
    case 'running':
    case 'queued':
      return 'bg-accent animate-pulse';
    case 'completed':
      return 'bg-success';
    case 'failed':
    case 'interrupted':
      return 'bg-error';
    case 'not_requested':
      return 'bg-text-secondary/30';
    default:
      return 'bg-border';
  }
}

function statusTextClass(status: AnalysisStageStatus): string {
  switch (status) {
    case 'running':
    case 'queued':
      return 'text-accent';
    case 'completed':
      return 'text-success';
    case 'failed':
    case 'interrupted':
      return 'text-error';
    case 'not_requested':
      return 'text-text-secondary/50';
    default:
      return 'text-text-secondary';
  }
}

function statusLabel(status: AnalysisStageStatus): string {
  switch (status) {
    case 'running': return 'RUNNING';
    case 'queued': return 'QUEUED';
    case 'completed': return 'DONE';
    case 'failed': return 'FAILED';
    case 'interrupted': return 'STOPPED';
    case 'not_requested': return 'SKIP';
    case 'blocked': return 'WAIT';
    case 'ready': return 'READY';
    default: return String(status).toUpperCase();
  }
}

export function AnalysisStatusPanel({
  run,
  elapsedMs,
  estimate,
  isActive,
  onStopMonitoring,
  onRetryMeasurement,
  onRetryPitchNote,
  onRetryInterpretation,
}: AnalysisStatusPanelProps) {
  const progress = computeProgress(elapsedMs, estimate);

  const stages: { key: StageKey; status: AnalysisStageStatus; onRetry?: () => void }[] = [
    { key: 'measurement', status: run?.stages.measurement.status ?? 'queued', onRetry: onRetryMeasurement },
    { key: 'pitchNoteTranslation', status: run?.stages.pitchNoteTranslation.status ?? 'blocked', onRetry: onRetryPitchNote },
    { key: 'interpretation', status: run?.stages.interpretation.status ?? 'blocked', onRetry: onRetryInterpretation },
  ];

  return (
    <div className="rounded-sm border border-border bg-bg-panel p-3 space-y-3">
      {/* Header row */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-[11px] font-mono text-text-secondary uppercase tracking-[0.2em]">Analysis Run</span>
          {run && (
            <span className="text-[9px] font-mono text-text-secondary/50 uppercase tracking-wider truncate">
              {run.runId}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <div className="flex items-center gap-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-accent animate-pulse' : 'bg-success'}`} />
            <span className="text-[10px] font-mono text-text-primary tabular-nums">{formatElapsed(elapsedMs)}</span>
          </div>
          {estimate && (
            <span className="text-[9px] font-mono text-text-secondary/60 uppercase">
              est {formatEstimateRange(estimate)}
            </span>
          )}
          {onStopMonitoring && isActive && (
            <button
              onClick={onStopMonitoring}
              className="flex items-center gap-1 rounded-sm border border-error/30 bg-error/10 px-2 py-1 text-error hover:bg-error/20 transition-colors"
              title="Stop monitoring"
              aria-label="Stop monitoring"
            >
              <Square className="w-3 h-3 fill-current" />
              <span className="text-[9px] font-mono uppercase tracking-wider">Stop</span>
            </button>
          )}
        </div>
      </div>

      {/* Stage pipeline */}
      <div className="flex items-stretch gap-1">
        {stages.map((stage, i) => {
          const isRetryable = stage.onRetry && (stage.status === 'failed' || stage.status === 'interrupted' || stage.status === 'ready');
          return (
            <div
              key={stage.key}
              className={`flex-1 rounded-sm border p-2 ${
                stage.status === 'running' || stage.status === 'queued'
                  ? 'border-accent/30 bg-accent/5'
                  : stage.status === 'completed'
                    ? 'border-success/20 bg-success/5'
                    : stage.status === 'failed' || stage.status === 'interrupted'
                      ? 'border-error/20 bg-error/5'
                      : 'border-border bg-bg-card'
              }`}
            >
              <div className="flex items-center justify-between gap-1.5 mb-1">
                <span className="text-[9px] font-mono text-text-secondary uppercase tracking-wider">
                  {STAGE_LABELS[stage.key]}
                </span>
                <div className={`w-2 h-2 rounded-full shrink-0 ${statusDotClass(stage.status)}`} />
              </div>
              <div className="flex items-center justify-between gap-1">
                <span className={`text-[10px] font-mono font-bold uppercase tracking-wider ${statusTextClass(stage.status)}`}>
                  {statusLabel(stage.status)}
                </span>
                {isRetryable && (
                  <button
                    onClick={stage.onRetry}
                    className="flex items-center gap-0.5 text-accent hover:text-accent/80 transition-colors"
                    title={`Retry ${STAGE_LABELS[stage.key]}`}
                  >
                    <RotateCcw className="w-3 h-3" />
                    <span className="text-[8px] font-mono uppercase tracking-wider">Retry</span>
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="w-full h-1 bg-bg-app border border-border/20 rounded-sm overflow-hidden">
          {progress.indeterminate ? (
            <div className="h-full w-1/3 bg-accent/60 rounded-sm animate-pulse" />
          ) : (
            <div
              className={`h-full bg-accent rounded-sm transition-all duration-500 ease-out ${progress.percent >= 95 ? 'animate-pulse' : ''}`}
              style={{ width: `${progress.percent}%` }}
            />
          )}
        </div>
        <div className="flex items-center justify-end">
          <span className="text-[9px] font-mono text-text-secondary/50 tabular-nums">
            {progress.indeterminate ? 'estimating' : `${Math.round(progress.percent)}%`}
          </span>
        </div>
      </div>
    </div>
  );
}

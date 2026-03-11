import React from 'react';
import { Activity, Clock3, Radio, TimerReset, XCircle } from 'lucide-react';

import { BackendAnalysisEstimate } from '../types';

interface AnalysisStatusPanelProps {
  title: string;
  summary: string;
  detail: string;
  requestState: string;
  elapsedMs: number;
  estimate?: BackendAnalysisEstimate | null;
  onCancel?: () => void;
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
  const raw = (elapsedMs / midpointMs) * 100;
  // Cap at 95% — once we exceed the estimate, pulse at 95% rather than showing >100%
  const percent = Math.min(raw, 95);
  return { percent, indeterminate: false };
}

export function AnalysisStatusPanel({
  title,
  summary,
  detail,
  requestState,
  elapsedMs,
  estimate,
  onCancel,
}: AnalysisStatusPanelProps) {
  const progress = computeProgress(elapsedMs, estimate);

  return (
    <div className="h-full rounded-sm border border-border bg-bg-panel p-6 flex flex-col justify-between gap-6">
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-mono text-text-secondary uppercase tracking-[0.24em]">Analysis Status</p>
            <h3 className="mt-2 text-lg font-bold uppercase tracking-wide text-text-primary">{title}</h3>
            <p className="mt-2 text-sm text-text-primary/90">{summary}</p>
            <p className="mt-2 text-xs font-mono text-text-secondary uppercase tracking-wider">{detail}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <div className="flex items-center gap-2 rounded-sm border border-accent/30 bg-accent/10 px-3 py-2 text-accent">
              <Activity className="w-4 h-4" />
              <span className="text-[10px] font-mono uppercase tracking-[0.24em]">Active</span>
            </div>
            {onCancel && (
              <button
                onClick={onCancel}
                className="flex items-center gap-1.5 rounded-sm border border-error/30 bg-error/10 px-3 py-2 text-error hover:bg-error/20 transition-colors"
                title="Cancel analysis"
                aria-label="Cancel analysis"
              >
                <XCircle className="w-4 h-4" />
                <span className="text-[10px] font-mono uppercase tracking-[0.24em]">Cancel</span>
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
            <p className="mt-3 text-sm font-bold uppercase tracking-wide text-text-primary">{requestState}</p>
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
              <span className="text-[10px] font-mono uppercase tracking-wider">Estimated local analysis</span>
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

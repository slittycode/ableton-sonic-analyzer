import React from 'react';
import { RotateCcw, Square } from 'lucide-react';

import { AnalysisRunSnapshot, AnalysisStageError, AnalysisStageStatus, BackendAnalysisEstimate } from '../types';

interface AnalysisStatusPanelProps {
  run: AnalysisRunSnapshot | null;
  elapsedMs: number;
  estimate?: BackendAnalysisEstimate | null;
  isActive: boolean;
  onStopAnalysis?: () => void;
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

export type ProgressTone = 'running' | 'success' | 'failed';

export interface ProgressState {
  percent: number;
  indeterminate: boolean;
  message: string;
  tone: ProgressTone;
  /**
   * Audit Finding #6: which stage is producing this message. Lets the panel
   * label the readout ("MEASURE · Measuring tempo, key, loudness…") so the
   * user has the substance + context in one glance instead of having to
   * cross-reference the stage chips. `null` for terminal/estimate states
   * where no single stage is active.
   */
  activeStageKey: StageKey | null;
}

function computeEstimateProgress(
  elapsedMs: number,
  estimate?: BackendAnalysisEstimate | null,
): ProgressState {
  if (!estimate) return { percent: 0, indeterminate: true, message: 'Estimating progress...', tone: 'running', activeStageKey: null };
  const midpointMs = (estimate.totalLowMs + estimate.totalHighMs) / 2;
  if (midpointMs <= 0) return { percent: 0, indeterminate: true, message: 'Estimating progress...', tone: 'running', activeStageKey: null };
  return {
    percent: Math.min((elapsedMs / midpointMs) * 100, 95),
    indeterminate: false,
    message: 'Estimating progress from elapsed time.',
    tone: 'running',
    activeStageKey: null,
  };
}

type StageKey = 'measurement' | 'pitchNoteTranslation' | 'interpretation';

const STAGE_LABELS: Record<StageKey, string> = {
  measurement: 'MEASURE',
  pitchNoteTranslation: 'PITCH/NOTE',
  interpretation: 'INTERPRET',
};

/**
 * Maps progress tone to the Tailwind background-color class for the progress
 * bar fill. Used to surface failed/successful end-states visually, instead of
 * leaving the bar accent-orange even when a stage has FAILED. Indeterminate
 * fills use a lower-opacity variant so the pulsing partial bar reads as
 * activity rather than solid colour. Audit N1 sibling.
 */
function progressFillClass(tone: ProgressTone, indeterminate: boolean): string {
  if (tone === 'failed') return indeterminate ? 'bg-error/60' : 'bg-error';
  if (tone === 'success') return indeterminate ? 'bg-success/60' : 'bg-success';
  return indeterminate ? 'bg-accent/60' : 'bg-accent';
}

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

function getStageSnapshot(run: AnalysisRunSnapshot, stageKey: StageKey) {
  switch (stageKey) {
    case 'measurement':
      return run.stages.measurement;
    case 'pitchNoteTranslation':
      return run.stages.pitchNoteTranslation;
    case 'interpretation':
      return run.stages.interpretation;
    default:
      return run.stages.measurement;
  }
}

function getStageProgressDetails(
  run: AnalysisRunSnapshot | null,
  stageKey: StageKey,
): { fraction: number | null; message: string | null } {
  if (!run) {
    return { fraction: null, message: null };
  }

  const diagnostics = getStageSnapshot(run, stageKey).diagnostics;
  const progress =
    diagnostics && typeof diagnostics === 'object' && diagnostics !== null && 'progress' in diagnostics
      ? diagnostics.progress
      : null;

  if (!progress || typeof progress !== 'object') {
    return { fraction: null, message: null };
  }

  const progressRecord = progress as Record<string, unknown>;

  return {
    fraction: typeof progressRecord.fraction === 'number' ? progressRecord.fraction : null,
    message: typeof progressRecord.message === 'string' ? progressRecord.message : null,
  };
}

function getTrackedStageKeys(run: AnalysisRunSnapshot | null): StageKey[] {
  if (!run) {
    return ['measurement'];
  }

  const tracked: StageKey[] = ['measurement'];
  if (run.requestedStages.pitchNoteMode !== 'off') {
    tracked.push('pitchNoteTranslation');
  }
  if (run.requestedStages.interpretationMode !== 'off') {
    tracked.push('interpretation');
  }
  return tracked;
}

function isStageTerminal(status: AnalysisStageStatus): boolean {
  return ['completed', 'failed', 'interrupted', 'not_requested'].includes(status);
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
        : stageKey === 'pitchNoteTranslation'
          ? 'Best-effort pitch/note output available.'
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

export function computeLiveProgress(
  run: AnalysisRunSnapshot | null,
): ProgressState | null {
  if (!run) {
    return null;
  }

  const trackedStageKeys = getTrackedStageKeys(run);
  const activeStageKey = trackedStageKeys.find(
    (stageKey) => !isStageTerminal(getStageSnapshot(run, stageKey).status),
  );
  const totalStages = Math.max(trackedStageKeys.length, 1);

  if (!activeStageKey) {
    // All stages reached a terminal state — but distinguish honest success
    // from a failure or interruption. Previously this branch unconditionally
    // returned "Analysis complete." even when a stage had failed, so the
    // progress card lied alongside a red FAILED stage badge. (Audit N1.)
    const failedKey = trackedStageKeys.find((key) => {
      const status = getStageSnapshot(run, key).status;
      return status === 'failed' || status === 'interrupted';
    });
    if (failedKey) {
      const failedStatus = getStageSnapshot(run, failedKey).status;
      const verb = failedStatus === 'failed' ? 'failed' : 'stopped';
      return {
        percent: 100,
        indeterminate: false,
        message: `${STAGE_LABELS[failedKey]} ${verb}.`,
        tone: 'failed',
        activeStageKey: failedKey,
      };
    }
    return { percent: 100, indeterminate: false, message: 'Analysis complete.', tone: 'success', activeStageKey: null };
  }

  const activeStage = getStageSnapshot(run, activeStageKey);
  const progressDetails = getStageProgressDetails(run, activeStageKey);
  const completedBeforeActive = trackedStageKeys.indexOf(activeStageKey);
  const stageFraction = progressDetails.fraction ?? 0;

  return {
    percent: Math.min(((completedBeforeActive + stageFraction) / totalStages) * 100, 100),
    indeterminate: activeStage.status === 'running' && progressDetails.fraction == null,
    message: progressDetails.message ?? stageSummary(run, activeStageKey),
    tone: 'running',
    activeStageKey,
  };
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
  onStopAnalysis,
  onRetryMeasurement,
  onRetryPitchNote,
  onRetryInterpretation,
}: AnalysisStatusPanelProps) {
  const progress = computeLiveProgress(run) ?? computeEstimateProgress(elapsedMs, estimate);

  const stages: {
    key: StageKey;
    status: AnalysisStageStatus;
    error: AnalysisStageError | null;
    onRetry?: () => void;
  }[] = [
    {
      key: 'measurement',
      status: run?.stages.measurement.status ?? 'queued',
      error: run?.stages.measurement.error ?? null,
      onRetry: onRetryMeasurement,
    },
    {
      key: 'pitchNoteTranslation',
      status: run?.stages.pitchNoteTranslation.status ?? 'blocked',
      error: run?.stages.pitchNoteTranslation.error ?? null,
      onRetry: onRetryPitchNote,
    },
    {
      key: 'interpretation',
      status: run?.stages.interpretation.status ?? 'blocked',
      error: run?.stages.interpretation.error ?? null,
      onRetry: onRetryInterpretation,
    },
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
          {onStopAnalysis && isActive && (
            <button
              onClick={onStopAnalysis}
              className="flex items-center gap-1 rounded-sm border border-error/30 bg-error/10 px-2 py-1 text-error hover:bg-error/20 transition-colors"
              title="Stop analysis"
              aria-label="Stop analysis"
            >
              <Square className="w-3 h-3 fill-current" />
              <span className="text-[9px] font-mono uppercase tracking-wider">Stop</span>
            </button>
          )}
        </div>
      </div>

      {/* Audit Finding #6: primary readout. The stage diagnostic message used
          to render at `text-[9px] text-secondary/50` below the percent — sized
          as background fluff. During a 4–5 minute Phase 2 wait the producer
          would tab away and miss any actual signal about what's happening.
          Now it sits between the header and the stage chips as the visual
          focus, with the active stage label as a mono eyebrow above it. The
          chips below become the secondary "which stage is which" landmark. */}
      <div
        data-testid="status-panel-primary-readout"
        className="rounded-sm border border-border/40 bg-bg-card/40 px-3 py-2.5"
      >
        {progress.activeStageKey && (
          <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary/80 mb-1">
            {STAGE_LABELS[progress.activeStageKey]}
            {progress.tone === 'failed' ? ' · failure' : null}
          </p>
        )}
        <p
          className={`text-sm font-sans leading-snug ${
            progress.tone === 'failed' ? 'text-error' : 'text-text-primary'
          }`}
        >
          {progress.message}
        </p>
      </div>

      {/* Stage pipeline */}
      <div className="flex items-stretch gap-1">
        {stages.map((stage, i) => {
          // A retry button only makes sense when (a) the parent provided a
          // handler, (b) the stage is in a retryable state, and (c) the
          // backend hasn't explicitly marked the error as non-retryable
          // (e.g. GEMINI_NOT_CONFIGURED: clicking RETRY won't fix a missing
          // env var). Audit N1 sibling: previously the button rendered for
          // every failed stage regardless of error.retryable.
          const errorMarkedNonRetryable = stage.error?.retryable === false;
          const isRetryable =
            stage.onRetry &&
            (stage.status === 'failed' || stage.status === 'interrupted' || stage.status === 'ready') &&
            !errorMarkedNonRetryable;
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
                {isRetryable ? (
                  <button
                    onClick={stage.onRetry}
                    className="flex items-center gap-0.5 text-accent hover:text-accent/80 transition-colors"
                    title={`Retry ${STAGE_LABELS[stage.key]}`}
                  >
                    <RotateCcw className="w-3 h-3" />
                    <span className="text-[8px] font-mono uppercase tracking-wider">Retry</span>
                  </button>
                ) : errorMarkedNonRetryable && stage.error?.code ? (
                  // Audit N1 sibling: a non-retryable failure (e.g.
                  // GEMINI_NOT_CONFIGURED) used to render FAILED with no
                  // actionable feedback. Surface the error code so the user
                  // knows where to look; full message goes in the tooltip.
                  <span
                    className="text-[8px] font-mono uppercase tracking-wider text-error/70 truncate max-w-[8rem]"
                    title={stage.error?.message ?? stage.error.code}
                  >
                    {stage.error.code}
                  </span>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="w-full h-1 bg-bg-app border border-border/20 rounded-sm overflow-hidden">
          {progress.indeterminate ? (
            <div className={`h-full w-1/3 rounded-sm animate-pulse ${progressFillClass(progress.tone, true)}`} />
          ) : (
            <div
              className={`h-full rounded-sm transition-all duration-500 ease-out ${progressFillClass(progress.tone, false)} ${
                progress.percent >= 95 && progress.tone === 'running' ? 'animate-pulse' : ''
              }`}
              style={{ width: `${progress.percent}%` }}
            />
          )}
        </div>
        <div className="flex items-center justify-end">
          <span className="text-[9px] font-mono text-text-secondary/50 tabular-nums">
            {progress.indeterminate ? 'estimating' : `${Math.round(progress.percent)}%`}
          </span>
        </div>
        {/* Audit Finding #6: the duplicate small `progress.message` that used
            to render here was removed — the primary readout above is the
            single source for "what's happening". Keeping it here would have
            been visual noise repeating the same sentence twice. */}
      </div>
    </div>
  );
}

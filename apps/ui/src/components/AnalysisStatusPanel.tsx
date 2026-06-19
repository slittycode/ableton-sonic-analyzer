import React from 'react';
import { RotateCcw, Square } from 'lucide-react';

import {
  AnalysisRunSnapshot,
  AnalysisStageError,
  AnalysisStageStatus,
  BackendAnalysisEstimate,
} from '../types';
import { assertNever } from '../utils/assertNever';
import {
  Button,
  DeviceRack,
  Panel,
  SignalChain,
  type SignalStage,
  type SignalStageStatus,
  type SignalTone,
} from './ui';

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
  return `${lo}s–${hi}s`;
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

function getStageSnapshot(run: AnalysisRunSnapshot, stageKey: StageKey) {
  switch (stageKey) {
    case 'measurement':
      return run.stages.measurement;
    case 'pitchNoteTranslation':
      return run.stages.pitchNoteTranslation;
    case 'interpretation':
      return run.stages.interpretation;
    default:
      return assertNever(stageKey);
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
      return assertNever(stage.status);
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

/**
 * Map a stage's internal status onto the visual SignalChain status. The
 * SignalChain primitive owns the device-rack chrome for each stage, so we
 * collapse the wider AnalysisStageStatus enum onto its smaller vocabulary.
 *
 * - `running`        → active   (LED pulses, cable animates)
 * - `queued`         → queued   (waiting in line behind earlier stages)
 * - `blocked`        → queued   (waiting on measurement to finish; same
 *                                visual semantic as queued)
 * - `ready`          → idle     (failed stage was reset and is now waiting
 *                                for the user to click Retry — the Retry
 *                                button in the action slot owns this state's
 *                                CTA, so the device tile reads as idle
 *                                rather than queued-for-auto-execution)
 * - `completed`      → success
 * - `failed`/`interrupted` → error
 * - `not_requested`  → idle     (stage was not requested for this run)
 */
export function toSignalStatus(status: AnalysisStageStatus): SignalStageStatus {
  switch (status) {
    case 'running':
      return 'active';
    case 'queued':
    case 'blocked':
      return 'queued';
    case 'completed':
      return 'success';
    case 'failed':
    case 'interrupted':
      return 'error';
    case 'ready':
    case 'not_requested':
      return 'idle';
    default:
      return 'idle';
  }
}

export function statusLabel(status: AnalysisStageStatus): string {
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

/**
 * Map the live ProgressState + isActive onto a DeviceRack status tone for
 * the outer ANALYSIS RUN rack. Failure dominates (error tone) regardless of
 * isActive; an explicit success tone overrides isActive; otherwise the rack
 * lights up active while running and falls to idle when no stage is active.
 */
export function rackStatusFromProgress(
  progress: ProgressState,
  isActive: boolean,
): 'idle' | 'active' | 'success' | 'error' {
  if (progress.tone === 'failed') return 'error';
  if (progress.tone === 'success') return 'success';
  return isActive ? 'active' : 'idle';
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

  const signalStages: SignalStage[] = stages.map((stage) => {
    const errorMarkedNonRetryable = stage.error?.retryable === false;
    const isRetryable =
      stage.onRetry &&
      (stage.status === 'failed' || stage.status === 'interrupted' || stage.status === 'ready') &&
      !errorMarkedNonRetryable;
    // Audit N1: non-retryable failures (e.g. GEMINI_NOT_CONFIGURED) used to
    // render FAILED with no actionable feedback. Surface the error code in
    // the action slot so the user knows where to look; the full message
    // lives in the title attribute.
    const nonRetryableHint =
      errorMarkedNonRetryable && stage.error?.code ? (
        <span
          className="font-mono text-micro uppercase tracking-wider text-error/70 truncate max-w-[8rem]"
          title={stage.error?.message ?? stage.error.code}
        >
          {stage.error.code}
        </span>
      ) : null;

    const action = isRetryable ? (
      <Button
        variant="ghost"
        size="sm"
        leadingIcon={<RotateCcw className="w-3 h-3" />}
        onClick={stage.onRetry}
        title={`Retry ${STAGE_LABELS[stage.key]}`}
      >
        Retry
      </Button>
    ) : (
      nonRetryableHint
    );

    return {
      key: stage.key,
      name: STAGE_LABELS[stage.key],
      status: toSignalStatus(stage.status),
      statusLabel: statusLabel(stage.status),
      action,
    };
  });

  const rackStatus = rackStatusFromProgress(progress, isActive);
  const subtitle = run ? `· ${run.runId.slice(-8)}` : undefined;
  const railTone: SignalTone =
    progress.tone === 'success' ? 'success' : progress.tone === 'failed' ? 'idle' : 'active';

  const railProgressLabel = progress.indeterminate
    ? 'estimating'
    : `${Math.round(progress.percent)}%`;

  return (
    <DeviceRack
      name="ANALYSIS RUN"
      subtitle={subtitle}
      status={rackStatus}
      action={
        onStopAnalysis && isActive ? (
          <Button
            variant="danger"
            size="sm"
            leadingIcon={<Square className="w-3 h-3 fill-current" />}
            onClick={onStopAnalysis}
            title="Stop analysis"
            aria-label="Stop analysis"
          >
            Stop
          </Button>
        ) : undefined
      }
      signalIn={railTone}
      signalOut={progress.tone === 'success' ? 'success' : 'idle'}
      railContent={
        <span className="flex items-center gap-3">
          <span className="tabular-mono text-text-secondary">
            {formatElapsed(elapsedMs)}
          </span>
          {estimate && (
            <span className="text-text-muted">est {formatEstimateRange(estimate)}</span>
          )}
          <span className="tabular-mono text-text-secondary">{railProgressLabel}</span>
        </span>
      }
    >
      <div className="space-y-3">
        {/* Audit Finding #6: primary readout. The stage diagnostic message
            used to render at `text-micro text-secondary/50` below the percent
            — sized as background fluff. During a 4–5 minute Phase 2 wait the
            producer would tab away and miss any actual signal about what's
            happening. Now it sits at the top of the device body as the visual
            focus, with the active stage label as a mono eyebrow above it. The
            SignalChain below becomes the secondary "which stage is which"
            landmark. */}
        <Panel
          variant="inset"
          padding="sm"
          data-testid="status-panel-primary-readout"
        >
          {progress.activeStageKey && (
            <p className="font-mono text-meta uppercase tracking-[0.18em] text-text-secondary/80 mb-1">
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
        </Panel>

        <SignalChain
          stages={signalStages}
          orientation="horizontal"
          animated={isActive && progress.tone === 'running'}
        />
      </div>
    </DeviceRack>
  );
}

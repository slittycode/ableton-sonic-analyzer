/**
 * Locks in the progress-card message logic so the card never returns to
 * saying "Analysis complete." 100% while a stage is FAILED or STOPPED.
 *
 * Audit N1 sibling: previously `computeLiveProgress` returned
 *   { percent: 100, message: 'Analysis complete.' }
 * whenever NO stage was still active — but `isStageTerminal` includes
 * 'failed' and 'interrupted', so a failed-Phase-2 run landed in the
 * success branch and the progress card lied alongside a red FAILED
 * stage badge.
 */
import { describe, expect, it } from 'vitest';
import { computeLiveProgress } from '../../src/components/AnalysisStatusPanel';
import type { AnalysisRunSnapshot, AnalysisStageStatus } from '../../src/types';

function makeStage(status: AnalysisStageStatus) {
  return {
    status,
    authoritative: status === 'completed',
    preferredAttemptId: null,
    attemptsSummary: [],
    result: null,
    provenance: null,
    diagnostics: null,
    error:
      status === 'failed'
        ? { code: 'TEST_FAILURE', message: 'test', retryable: true }
        : null,
  };
}

function makeRun(opts: {
  measurement: AnalysisStageStatus;
  pitchNote: AnalysisStageStatus;
  interpretation: AnalysisStageStatus;
  pitchNoteMode?: string;
  interpretationMode?: string;
}): AnalysisRunSnapshot {
  return {
    runId: 'test-run',
    status: 'completed',
    requestedStages: {
      pitchNoteMode: opts.pitchNoteMode ?? 'stem_notes',
      interpretationMode: opts.interpretationMode ?? 'producer_summary',
      analysisMode: 'full',
      pitchNoteBackend: 'auto',
    },
    stages: {
      measurement: makeStage(opts.measurement),
      pitchNoteTranslation: makeStage(opts.pitchNote),
      interpretation: makeStage(opts.interpretation),
    },
  } as unknown as AnalysisRunSnapshot;
}

describe('computeLiveProgress', () => {
  it('returns null when there is no run', () => {
    expect(computeLiveProgress(null)).toBeNull();
  });

  it('returns "Analysis complete." only when every tracked stage completed', () => {
    const run = makeRun({
      measurement: 'completed',
      pitchNote: 'completed',
      interpretation: 'completed',
    });
    const progress = computeLiveProgress(run);
    expect(progress).not.toBeNull();
    expect(progress!.percent).toBe(100);
    expect(progress!.message).toBe('Analysis complete.');
    expect(progress!.tone).toBe('success');
  });

  it('does NOT claim "Analysis complete." when interpretation failed', () => {
    const run = makeRun({
      measurement: 'completed',
      pitchNote: 'completed',
      interpretation: 'failed',
    });
    const progress = computeLiveProgress(run);
    expect(progress).not.toBeNull();
    expect(progress!.message).not.toMatch(/Analysis complete/i);
    expect(progress!.message).toBe('INTERPRET failed.');
    expect(progress!.tone).toBe('failed');
  });

  it('surfaces a stopped stage with "stopped" verb', () => {
    // All stages terminal, one of them interrupted: branch should fire.
    const run = makeRun({
      measurement: 'completed',
      pitchNote: 'interrupted',
      interpretation: 'not_requested',
      interpretationMode: 'off',
    });
    const progress = computeLiveProgress(run);
    expect(progress).not.toBeNull();
    expect(progress!.message).toBe('PITCH/NOTE stopped.');
  });

  it('reports the first non-terminal stage while measurement is running', () => {
    const run = makeRun({
      measurement: 'running',
      pitchNote: 'blocked',
      interpretation: 'blocked',
    });
    const progress = computeLiveProgress(run);
    expect(progress).not.toBeNull();
    expect(progress!.message).not.toMatch(/Analysis complete/i);
    expect(progress!.tone).toBe('running');
  });

  it('treats not_requested + completed as success', () => {
    const run = makeRun({
      measurement: 'completed',
      pitchNote: 'not_requested',
      interpretation: 'completed',
      pitchNoteMode: 'off',
    });
    const progress = computeLiveProgress(run);
    expect(progress!.message).toBe('Analysis complete.');
  });

  // ─────────────────────────────────────────────────────────────────────
  // Audit Finding #6: streaming-reveal companion. `activeStageKey` lets the
  // status panel render "MEASURE · …" / "INTERPRET · …" as a primary readout
  // instead of just a tiny diagnostic message. Verify the key threads through
  // every branch.
  // ─────────────────────────────────────────────────────────────────────
  it('exposes activeStageKey for the currently-running stage', () => {
    const run = makeRun({
      measurement: 'running',
      pitchNote: 'blocked',
      interpretation: 'blocked',
    });
    const progress = computeLiveProgress(run);
    expect(progress!.activeStageKey).toBe('measurement');
  });

  it('exposes activeStageKey for an interpretation that is still working', () => {
    // Mid-run streaming-reveal state: measurement completed, Phase 1 has
    // already streamed into the UI, INTERPRET is still going. The primary
    // readout should label "INTERPRET" so the user knows what they're waiting on.
    const run = makeRun({
      measurement: 'completed',
      pitchNote: 'completed',
      interpretation: 'running',
    });
    const progress = computeLiveProgress(run);
    expect(progress!.activeStageKey).toBe('interpretation');
    expect(progress!.tone).toBe('running');
  });

  it('points activeStageKey at the failed stage on a failure terminal', () => {
    const run = makeRun({
      measurement: 'completed',
      pitchNote: 'completed',
      interpretation: 'failed',
    });
    const progress = computeLiveProgress(run);
    expect(progress!.activeStageKey).toBe('interpretation');
  });

  it('returns null activeStageKey when all stages completed cleanly', () => {
    const run = makeRun({
      measurement: 'completed',
      pitchNote: 'completed',
      interpretation: 'completed',
    });
    const progress = computeLiveProgress(run);
    expect(progress!.activeStageKey).toBeNull();
  });
});

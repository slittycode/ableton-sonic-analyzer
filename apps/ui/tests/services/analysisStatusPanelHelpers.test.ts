import { describe, expect, it } from 'vitest';

import {
  rackStatusFromProgress,
  statusLabel,
  toSignalStatus,
  type ProgressState,
} from '../../src/components/AnalysisStatusPanel';
import type { AnalysisStageStatus } from '../../src/types';

describe('toSignalStatus', () => {
  it.each<[AnalysisStageStatus, string]>([
    ['running', 'active'],
    ['queued', 'queued'],
    ['blocked', 'queued'],
    ['completed', 'success'],
    ['failed', 'error'],
    ['interrupted', 'error'],
    ['ready', 'idle'],
    ['not_requested', 'idle'],
  ])('maps %s → %s', (input, expected) => {
    expect(toSignalStatus(input)).toBe(expected);
  });

  it('maps unknown statuses to idle', () => {
    // Cast to bypass the AnalysisStageStatus union — exercising the default branch.
    expect(toSignalStatus('mystery' as AnalysisStageStatus)).toBe('idle');
  });

  it('treats ready as idle (not queued) so the Retry CTA owns the action', () => {
    // ready means "failed stage was reset; user must click Retry". The action
    // slot already carries the Retry button; the tile must read as idle so
    // the chain doesn't look like it will auto-resume.
    expect(toSignalStatus('ready')).toBe('idle');
    expect(toSignalStatus('ready')).not.toBe('queued');
  });
});

describe('statusLabel', () => {
  it.each<[AnalysisStageStatus, string]>([
    ['running', 'RUNNING'],
    ['queued', 'QUEUED'],
    ['completed', 'DONE'],
    ['failed', 'FAILED'],
    ['interrupted', 'STOPPED'],
    ['not_requested', 'SKIP'],
    ['blocked', 'WAIT'],
    ['ready', 'READY'],
  ])('maps %s → %s', (input, expected) => {
    expect(statusLabel(input)).toBe(expected);
  });

  it('uppercases unknown statuses', () => {
    expect(statusLabel('weird-state' as AnalysisStageStatus)).toBe('WEIRD-STATE');
  });
});

describe('rackStatusFromProgress', () => {
  function progress(
    tone: ProgressState['tone'],
    overrides: Partial<ProgressState> = {},
  ): ProgressState {
    return {
      percent: 50,
      indeterminate: false,
      message: '',
      tone,
      activeStageKey: null,
      ...overrides,
    };
  }

  it('failure tone always wins over isActive', () => {
    expect(rackStatusFromProgress(progress('failed'), true)).toBe('error');
    expect(rackStatusFromProgress(progress('failed'), false)).toBe('error');
  });

  it('success tone always wins over isActive', () => {
    expect(rackStatusFromProgress(progress('success'), true)).toBe('success');
    expect(rackStatusFromProgress(progress('success'), false)).toBe('success');
  });

  it('running + active → active', () => {
    expect(rackStatusFromProgress(progress('running'), true)).toBe('active');
  });

  it('running + not active → idle', () => {
    // Edge case: progress tone says running but isActive=false. The rack
    // should fall back to idle rather than lying about activity.
    expect(rackStatusFromProgress(progress('running'), false)).toBe('idle');
  });
});

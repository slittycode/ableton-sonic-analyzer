/**
 * Locks in the StickyNav-pill disabled-reason mapping (audit Finding #6
 * streaming-reveal). The reason used to be hardcoded "Recommendations not
 * produced this run" which read as a lie during the 4–5 minute mid-run
 * window where Phase 1 streamed in but Phase 2 was still working.
 */
import { describe, expect, it } from 'vitest';
import { getPhase2NavDisabledReason } from '../../src/components/AnalysisResults';
import type { AnalysisStageStatus } from '../../src/types';

describe('getPhase2NavDisabledReason', () => {
  it.each<[AnalysisStageStatus | null | undefined, RegExp]>([
    ['running', /in progress/i],
    ['queued', /pending — waiting/i],
    ['ready', /pending — waiting/i],
    ['blocked', /pending — waiting/i],
    ['not_requested', /off for this run/i],
    ['failed', /failed — retry/i],
    ['interrupted', /stopped/i],
    ['completed', /not produced this run/i],
    [null, /not produced this run/i],
    [undefined, /not produced this run/i],
  ])('maps %s to a reason matching %s', (status, pattern) => {
    expect(getPhase2NavDisabledReason(status)).toMatch(pattern);
  });

  it('never returns the legacy "not produced this run" while interpretation is running', () => {
    // Regression guard for the audit's mid-run lie. The streaming-reveal
    // experience hinges on these states being honest.
    const inProgressStates: AnalysisStageStatus[] = ['running', 'queued', 'ready', 'blocked'];
    for (const status of inProgressStates) {
      expect(getPhase2NavDisabledReason(status)).not.toMatch(/not produced this run/i);
    }
  });
});

/**
 * Locks in the mapping between interpretation stage status and the
 * results-header subtitle, so the header never reverts to a hardcoded
 * "PHASE COMPLETE" that lies about Phase 2's actual state (see audit
 * finding N1: header was previously decoupled from stage status and read
 * "// PHASE COMPLETE" whether Phase 2 was running, failed, or completed).
 */
import { describe, expect, it } from 'vitest';
import { getInterpretationSubtitle } from '../../src/components/AnalysisResults';
import type { AnalysisStageStatus } from '../../src/types';

describe('getInterpretationSubtitle', () => {
  it('returns null for nullish status', () => {
    expect(getInterpretationSubtitle(null)).toBeNull();
    expect(getInterpretationSubtitle(undefined)).toBeNull();
  });

  it.each<[AnalysisStageStatus, string]>([
    ['completed', 'Recommendations ready'],
    ['running', 'AI interpretation in progress…'],
    ['queued', 'AI interpretation pending'],
    ['ready', 'AI interpretation pending'],
    ['blocked', 'AI interpretation pending'],
    ['failed', 'AI interpretation failed — retry from progress panel'],
    ['interrupted', 'AI interpretation stopped'],
    ['not_requested', 'Measurements only'],
  ])('maps status %s to %s', (status, expected) => {
    expect(getInterpretationSubtitle(status)).toBe(expected);
  });

  it('never returns the legacy "PHASE COMPLETE" string for any known status', () => {
    const statuses: AnalysisStageStatus[] = [
      'queued',
      'running',
      'blocked',
      'ready',
      'completed',
      'failed',
      'interrupted',
      'not_requested',
    ];
    for (const status of statuses) {
      const subtitle = getInterpretationSubtitle(status);
      expect(subtitle).not.toMatch(/PHASE COMPLETE/i);
    }
  });
});

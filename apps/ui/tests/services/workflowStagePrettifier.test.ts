/**
 * Locks in the UPPER_SNAKE_CASE → Sentence case transformation for the
 * Phase 2 workflowStage label. Audit findings N3/N8: previously the raw
 * `SOUND_DESIGN` value rendered verbatim in the Stage chip on every
 * Mix Chain and Patch card.
 */
import { describe, expect, it } from 'vitest';
import { prettifyWorkflowStage } from '../../src/components/analysisResultsViewModel';

describe('prettifyWorkflowStage', () => {
  it('returns undefined for nullish input', () => {
    expect(prettifyWorkflowStage(undefined)).toBeUndefined();
    expect(prettifyWorkflowStage(null)).toBeUndefined();
    expect(prettifyWorkflowStage('')).toBeUndefined();
  });

  it.each<[string, string]>([
    ['PROJECT_SETUP', 'Project setup'],
    ['SOUND_DESIGN', 'Sound design'],
    ['ARRANGEMENT', 'Arrangement'],
    ['MIX', 'Mix'],
    ['MASTER', 'Master'],
  ])('transforms %s to %s', (input, expected) => {
    expect(prettifyWorkflowStage(input)).toBe(expected);
  });

  it('handles multi-underscore values', () => {
    expect(prettifyWorkflowStage('VERY_LONG_PHASE_NAME')).toBe('Very long phase name');
  });

  it('leaves already-pretty values lowercased except first letter', () => {
    // Defensive: idempotency-ish, in case backend later emits human strings.
    expect(prettifyWorkflowStage('Mix')).toBe('Mix');
  });
});

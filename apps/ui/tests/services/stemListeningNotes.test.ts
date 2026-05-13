import { describe, expect, it } from 'vitest';

import { hasStemListeningNotesContent } from '../../src/services/sessionMusician/stemListeningNotes';
import type { StemSummaryResult } from '../../src/types';

const emptyEnvelope: StemSummaryResult = {
  summary: '',
  stems: [],
  uncertaintyFlags: [],
};

describe('hasStemListeningNotesContent', () => {
  it('returns false for null', () => {
    expect(hasStemListeningNotesContent(null)).toBe(false);
  });

  it('returns false for undefined', () => {
    expect(hasStemListeningNotesContent(undefined)).toBe(false);
  });

  it('returns false for a fully empty envelope', () => {
    expect(hasStemListeningNotesContent(emptyEnvelope)).toBe(false);
  });

  it('returns false when the summary string is only whitespace', () => {
    expect(
      hasStemListeningNotesContent({ ...emptyEnvelope, summary: '   ' }),
    ).toBe(false);
  });

  it('returns true when the summary string has real content', () => {
    expect(
      hasStemListeningNotesContent({ ...emptyEnvelope, summary: 'Bass plays root notes.' }),
    ).toBe(true);
  });

  it('returns true when any stems are present', () => {
    const envelope: StemSummaryResult = {
      summary: '',
      uncertaintyFlags: [],
      stems: [
        {
          stem: 'bass',
          label: 'Bass',
          summary: 'Bass walks through scale degrees.',
          bars: [],
          globalPatterns: {
            bassRole: '',
            melodicRole: '',
            pumpingOrModulation: '',
            synthesisCharacter: '',
            vocalPresence: '',
            bassCharacter: '',
          },
          uncertaintyFlags: [],
        },
      ],
    };
    expect(hasStemListeningNotesContent(envelope)).toBe(true);
  });

  it('returns true when only uncertainty flags are present', () => {
    expect(
      hasStemListeningNotesContent({
        ...emptyEnvelope,
        uncertaintyFlags: ['Pitch detection low confidence'],
      }),
    ).toBe(true);
  });
});

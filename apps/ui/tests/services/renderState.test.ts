import { describe, expect, it } from 'vitest';

import {
  deriveNoteDraftRenderState,
  isLegacyTranscriptionMethod,
} from '../../src/services/sessionMusician/renderState';
import type { TranscriptionDetail, TranscriptionNote } from '../../src/types';

const baseNote: TranscriptionNote = {
  pitchMidi: 60,
  pitchName: 'C4',
  onsetSeconds: 0,
  durationSeconds: 0.4,
  confidence: 0.7,
  stemSource: 'bass',
};

const torchcrepe = (overrides: Partial<TranscriptionDetail> = {}): TranscriptionDetail => ({
  transcriptionMethod: 'torchcrepe-viterbi',
  noteCount: 1,
  averageConfidence: 0.7,
  stemSeparationUsed: true,
  fullMixFallback: false,
  stemsTranscribed: ['bass'],
  dominantPitches: [],
  pitchRange: { minMidi: 60, maxMidi: 60, minName: 'C4', maxName: 'C4' },
  notes: [baseNote],
  ...overrides,
});

describe('isLegacyTranscriptionMethod', () => {
  it('returns false for torchcrepe-viterbi', () => {
    expect(isLegacyTranscriptionMethod('torchcrepe-viterbi')).toBe(false);
  });

  it('returns false for the bare torchcrepe alias', () => {
    expect(isLegacyTranscriptionMethod('torchcrepe')).toBe(false);
  });

  it('is case-insensitive', () => {
    expect(isLegacyTranscriptionMethod('Torchcrepe-Viterbi')).toBe(false);
  });

  it('returns true for basic-pitch', () => {
    expect(isLegacyTranscriptionMethod('basic-pitch')).toBe(true);
  });

  it('returns true for basic-pitch-legacy', () => {
    expect(isLegacyTranscriptionMethod('basic-pitch-legacy')).toBe(true);
  });

  it('returns true for arbitrary unknown methods', () => {
    expect(isLegacyTranscriptionMethod('penn')).toBe(true);
  });

  it('returns false for null / undefined / empty', () => {
    expect(isLegacyTranscriptionMethod(null)).toBe(false);
    expect(isLegacyTranscriptionMethod(undefined)).toBe(false);
    expect(isLegacyTranscriptionMethod('')).toBe(false);
    expect(isLegacyTranscriptionMethod('   ')).toBe(false);
  });
});

describe('deriveNoteDraftRenderState — precedence', () => {
  it('returns absent when pitchNoteMode is off, even with stale notes', () => {
    expect(deriveNoteDraftRenderState(torchcrepe(), 'off')).toBe('absent');
  });

  it('returns requested-but-unavailable when stem_notes is requested but no payload arrives', () => {
    expect(deriveNoteDraftRenderState(null, 'stem_notes')).toBe('requested-but-unavailable');
    expect(deriveNoteDraftRenderState(undefined, 'stem_notes')).toBe('requested-but-unavailable');
  });

  it('returns absent when no payload and no explicit request', () => {
    expect(deriveNoteDraftRenderState(null, null)).toBe('absent');
  });

  it('returns ran-with-no-result when payload arrives with an empty notes array', () => {
    expect(
      deriveNoteDraftRenderState(torchcrepe({ notes: [] }), 'stem_notes'),
    ).toBe('ran-with-no-result');
  });

  it('returns ran-with-no-result even when noteCount is non-zero but notes is empty', () => {
    // Defensive — a backend that reports noteCount: 5 but ships notes: [] is
    // still un-renderable.
    expect(
      deriveNoteDraftRenderState(torchcrepe({ notes: [], noteCount: 5 }), 'stem_notes'),
    ).toBe('ran-with-no-result');
  });

  it('returns legacy when the method is basic-pitch even if fullMixFallback is also true', () => {
    expect(
      deriveNoteDraftRenderState(
        torchcrepe({ transcriptionMethod: 'basic-pitch', fullMixFallback: true }),
        'stem_notes',
      ),
    ).toBe('legacy');
  });

  it('returns full-mix-fallback when torchcrepe data has fullMixFallback === true', () => {
    expect(
      deriveNoteDraftRenderState(
        torchcrepe({ fullMixFallback: true }),
        'stem_notes',
      ),
    ).toBe('full-mix-fallback');
  });

  it('returns stem-aware for nominal torchcrepe data', () => {
    expect(deriveNoteDraftRenderState(torchcrepe(), 'stem_notes')).toBe('stem-aware');
  });

  it('returns stem-aware when pitchNoteMode is null but the data is valid (legacy snapshot)', () => {
    expect(deriveNoteDraftRenderState(torchcrepe(), null)).toBe('stem-aware');
  });
});

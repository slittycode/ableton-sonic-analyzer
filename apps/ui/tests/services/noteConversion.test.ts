import { describe, expect, it } from 'vitest';

import {
  melodyNotesToDisplayNotes,
  midiToNoteName,
  transcriptionNotesToDisplayNotes,
} from '../../src/services/sessionMusician/noteConversion';
import type { MelodyDetail, TranscriptionDetail } from '../../src/types';

const transcription: TranscriptionDetail = {
  transcriptionMethod: 'torchcrepe-viterbi',
  noteCount: 3,
  averageConfidence: 0.7,
  stemSeparationUsed: true,
  fullMixFallback: false,
  stemsTranscribed: ['bass', 'other'],
  dominantPitches: [],
  pitchRange: { minMidi: 40, maxMidi: 72, minName: 'E2', maxName: 'C5' },
  notes: [
    {
      pitchMidi: 40,
      pitchName: 'E2',
      onsetSeconds: 0,
      durationSeconds: 0.5,
      confidence: 0.92,
      stemSource: 'bass',
    },
    {
      pitchMidi: 60,
      pitchName: 'C4',
      onsetSeconds: 0.5,
      durationSeconds: 0.4,
      confidence: 0.55,
      stemSource: 'other',
    },
    {
      pitchMidi: 72,
      pitchName: 'C5',
      onsetSeconds: 1.0,
      durationSeconds: 0.6,
      confidence: 0.18,
      stemSource: 'other',
    },
  ],
};

describe('transcriptionNotesToDisplayNotes', () => {
  it('returns an empty array when transcriptionDetail is null', () => {
    expect(transcriptionNotesToDisplayNotes(null)).toEqual([]);
  });

  it('returns an empty array when transcriptionDetail is undefined', () => {
    expect(transcriptionNotesToDisplayNotes(undefined)).toEqual([]);
  });

  it('returns an empty array when the notes array is empty', () => {
    expect(
      transcriptionNotesToDisplayNotes({ ...transcription, notes: [] }),
    ).toEqual([]);
  });

  it('maps every note to the display shape when no filter is applied', () => {
    const display = transcriptionNotesToDisplayNotes(transcription);
    expect(display).toHaveLength(3);
    expect(display[0]).toEqual({
      midi: 40,
      name: 'E2',
      startTime: 0,
      duration: 0.5,
      velocity: 90,
      confidence: 0.92,
    });
  });

  it('filters by stem source when an active filter is passed', () => {
    const display = transcriptionNotesToDisplayNotes(transcription, 'bass');
    expect(display).toHaveLength(1);
    expect(display[0].midi).toBe(40);
  });

  it('returns an empty array when the filter matches no stem', () => {
    expect(transcriptionNotesToDisplayNotes(transcription, 'drums')).toEqual([]);
  });

  it('treats a null filter the same as no filter', () => {
    expect(transcriptionNotesToDisplayNotes(transcription, null)).toHaveLength(3);
  });
});

const melody: MelodyDetail = {
  noteCount: 2,
  notes: [
    { midi: 60, onset: 0.1, duration: 0.3 },
    { midi: 64, onset: 0.5, duration: 0.4 },
  ],
  dominantNotes: [60, 64],
  pitchRange: { min: 60, max: 64 },
  pitchConfidence: 0.42,
  midiFile: null,
  sourceSeparated: false,
  vibratoPresent: false,
  vibratoExtent: 0,
  vibratoRate: 0,
  vibratoConfidence: 0,
};

describe('melodyNotesToDisplayNotes', () => {
  it('returns an empty array when melodyDetail is null', () => {
    expect(melodyNotesToDisplayNotes(null)).toEqual([]);
  });

  it('returns an empty array when melodyDetail has no notes', () => {
    expect(melodyNotesToDisplayNotes({ ...melody, notes: [] })).toEqual([]);
  });

  it('applies the scalar pitchConfidence to every emitted note', () => {
    const display = melodyNotesToDisplayNotes(melody);
    expect(display).toHaveLength(2);
    expect(display.every((note) => note.confidence === 0.42)).toBe(true);
  });

  it('derives note names from MIDI numbers', () => {
    const display = melodyNotesToDisplayNotes(melody);
    expect(display[0].name).toBe('C4');
    expect(display[1].name).toBe('E4');
  });
});

describe('midiToNoteName', () => {
  it('handles middle C', () => {
    expect(midiToNoteName(60)).toBe('C4');
  });

  it('handles A4', () => {
    expect(midiToNoteName(69)).toBe('A4');
  });

  it('clamps below zero to C-1', () => {
    expect(midiToNoteName(-5)).toBe('C-1');
  });

  it('clamps above 127 to G9', () => {
    expect(midiToNoteName(200)).toBe('G9');
  });

  it('rounds non-integer values', () => {
    expect(midiToNoteName(60.4)).toBe('C4');
    expect(midiToNoteName(60.6)).toBe('C#4');
  });
});

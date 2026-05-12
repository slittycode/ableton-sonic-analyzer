// Pure converters from backend pitch/note shapes to the panel's display note.
//
// These were previously inlined in SessionMusicianPanel.tsx and duplicated
// per-source. Extracting them lets the two new block components share a single
// implementation and lets unit tests assert the conversion contract directly.

import type { MelodyDetail, TranscriptionDetail } from '../../types';
import type { MidiDisplayNote } from '../midi/types';

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const;

export function midiToNoteName(midi: number): string {
  const clamped = Math.max(0, Math.min(127, Math.round(midi)));
  const octave = Math.floor(clamped / 12) - 1;
  return `${NOTE_NAMES[clamped % 12]}${octave}`;
}

export function transcriptionNotesToDisplayNotes(
  transcriptionDetail: TranscriptionDetail | null | undefined,
  activeStemFilter: string | null = null,
): MidiDisplayNote[] {
  if (!transcriptionDetail?.notes?.length) return [];
  const filtered = activeStemFilter
    ? transcriptionDetail.notes.filter((note) => note.stemSource === activeStemFilter)
    : transcriptionDetail.notes;
  return filtered.map((note) => ({
    midi: note.pitchMidi,
    name: note.pitchName,
    startTime: note.onsetSeconds,
    duration: note.durationSeconds,
    velocity: 90,
    confidence: note.confidence,
  }));
}

export function melodyNotesToDisplayNotes(
  melodyDetail: MelodyDetail | null | undefined,
): MidiDisplayNote[] {
  if (!melodyDetail?.notes?.length) return [];
  // Per-note confidence isn't available from Essentia's PredominantPitchMelodia;
  // the scalar pitchConfidence applies to the whole contour, so every emitted
  // display note carries it.
  return melodyDetail.notes.map((note) => ({
    midi: note.midi,
    name: midiToNoteName(note.midi),
    startTime: note.onset,
    duration: note.duration,
    velocity: 90,
    confidence: melodyDetail.pitchConfidence,
  }));
}

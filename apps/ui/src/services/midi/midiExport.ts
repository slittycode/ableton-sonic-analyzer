import MidiWriter from 'midi-writer-js';
import { MidiDisplayNote } from './types';

const TICKS_PER_BEAT = 128;
const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const;

function midiToPitchString(midi: number): string {
  const clamped = Math.max(0, Math.min(127, Math.round(midi)));
  const octave = Math.floor(clamped / 12) - 1;
  const note = NOTE_NAMES[clamped % 12];
  return `${note}${octave}`;
}

function durationToTicks(durationSec: number, bpm: number): number {
  const beatsPerSecond = bpm / 60;
  const beats = durationSec * beatsPerSecond;
  return Math.max(1, Math.round(beats * TICKS_PER_BEAT));
}

export function createMidiFile(notes: MidiDisplayNote[], bpm = 120): Blob {
  const track = new MidiWriter.Track();
  track.setTempo(bpm);
  track.addEvent(new MidiWriter.ProgramChangeEvent({ instrument: 1 }));

  const sorted = [...notes].sort((a, b) => a.startTime - b.startTime);

  for (const note of sorted) {
    const startTick = durationToTicks(note.startTime, bpm);
    const durationTicks = durationToTicks(note.duration, bpm);
    const velocity = Math.max(1, Math.min(100, Math.round((note.velocity / 127) * 100)));

    track.addEvent(
      new MidiWriter.NoteEvent({
        pitch: [midiToPitchString(note.midi)],
        duration: `T${durationTicks}`,
        velocity,
        startTick,
      }),
    );
  }

  const writer = new MidiWriter.Writer([track]);
  const output = writer.buildFile();
  return new Blob([output.buffer as ArrayBuffer], { type: 'audio/midi' });
}

export function downloadMidiFile(
  notes: MidiDisplayNote[],
  bpm: number,
  fileName = 'session-musician.mid',
): void {
  const blob = createMidiFile(notes, bpm);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

import { MidiDisplayNote, QuantizeGrid, QuantizeOptions } from './types';

function gridToSeconds(grid: QuantizeGrid, bpm: number): number {
  const beatDuration = 60 / bpm;
  switch (grid) {
    case '1/4':
      return beatDuration;
    case '1/8':
      return beatDuration / 2;
    case '1/16':
      return beatDuration / 4;
    case '1/32':
      return beatDuration / 8;
    case 'off':
      return 0;
  }
}

function snapToGrid(time: number, gridSize: number, swing: number): number {
  if (gridSize <= 0) return time;

  const gridIndex = Math.round(time / gridSize);
  let snapped = gridIndex * gridSize;

  if (swing > 0 && gridIndex % 2 !== 0) {
    const swingOffset = (swing / 100) * gridSize * 0.5;
    snapped += swingOffset;
  }

  return Math.max(0, snapped);
}

function snapDuration(duration: number, gridSize: number): number {
  if (gridSize <= 0) return duration;
  const minDuration = gridSize / 2;
  return Math.max(minDuration, Math.round(duration / gridSize) * gridSize);
}

export function quantizeNotes(
  notes: MidiDisplayNote[],
  bpm: number,
  options: QuantizeOptions,
): MidiDisplayNote[] {
  if (options.grid === 'off') return notes;

  const gridSize = gridToSeconds(options.grid, bpm);
  return notes.map((note) => ({
    ...note,
    startTime: snapToGrid(note.startTime, gridSize, options.swing),
    duration: snapDuration(note.duration, gridSize),
  }));
}

export function gridLabel(grid: QuantizeGrid): string {
  switch (grid) {
    case '1/4':
      return '1/4 note';
    case '1/8':
      return '1/8 note';
    case '1/16':
      return '1/16 note';
    case '1/32':
      return '1/32 note';
    case 'off':
      return 'Off';
  }
}

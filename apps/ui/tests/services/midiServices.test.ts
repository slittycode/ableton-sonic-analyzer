import { createMidiFile } from '../../src/services/midi/midiExport';
import { gridLabel, quantizeNotes } from '../../src/services/midi/quantization';
import { MidiDisplayNote } from '../../src/services/midi/types';

const notes: MidiDisplayNote[] = [
  {
    midi: 60,
    name: 'C4',
    startTime: 0.13,
    duration: 0.21,
    velocity: 90,
    confidence: 0.8,
  },
  {
    midi: 64,
    name: 'E4',
    startTime: 0.41,
    duration: 0.19,
    velocity: 90,
    confidence: 0.8,
  },
];

describe('midi services', () => {
  it('quantizes note start and duration to grid', () => {
    const quantized = quantizeNotes(notes, 120, { grid: '1/16', swing: 0 });

    expect(quantized[0].startTime).toBeCloseTo(0.125, 3);
    expect(quantized[0].duration).toBeCloseTo(0.25, 3);
  });

  it('creates a midi blob', () => {
    const blob = createMidiFile(notes, 120);

    expect(blob).toBeInstanceOf(Blob);
    expect(blob.type).toBe('audio/midi');
    expect(blob.size).toBeGreaterThan(0);
  });

  it('returns architect-style quantize labels', () => {
    expect(gridLabel('off')).toBe('Off');
    expect(gridLabel('1/4')).toBe('1/4 note');
    expect(gridLabel('1/8')).toBe('1/8 note');
    expect(gridLabel('1/16')).toBe('1/16 note');
    expect(gridLabel('1/32')).toBe('1/32 note');
  });
});

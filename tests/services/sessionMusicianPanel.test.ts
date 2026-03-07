import { filterNotesByConfidence, formatFilteredNoteCount } from '../../src/components/SessionMusicianPanel';

describe('SessionMusicianPanel confidence helpers', () => {
  it('filters notes at or above the confidence threshold', () => {
    const filtered = filterNotesByConfidence(
      [
        {
          midi: 48,
          name: 'C3',
          startTime: 0.1,
          duration: 0.4,
          velocity: 90,
          confidence: 0.19,
        },
        {
          midi: 55,
          name: 'G3',
          startTime: 0.6,
          duration: 0.3,
          velocity: 90,
          confidence: 0.2,
        },
        {
          midi: 60,
          name: 'C4',
          startTime: 0.9,
          duration: 0.25,
          velocity: 90,
          confidence: 0.8,
        },
      ],
      0.2,
    );

    expect(filtered).toHaveLength(2);
    expect(filtered.map((note) => note.midi)).toEqual([55, 60]);
  });

  it('formats filtered note counts when the threshold is active', () => {
    expect(formatFilteredNoteCount(2, 3, 0.2)).toBe('2 / 3 NOTES');
  });

  it('formats note counts without the filtered prefix when threshold is zero', () => {
    expect(formatFilteredNoteCount(3, 3, 0)).toBe('3 NOTES');
  });
});

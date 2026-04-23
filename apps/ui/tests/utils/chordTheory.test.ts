import { describe, expect, it } from 'vitest';
import {
  analyzeChord,
  CHORD_FUNCTION_COLORS,
  deduplicateChords,
  getChordColor,
  getChordNumeral,
} from '../../src/utils/chordTheory';

describe('analyzeChord — diatonic major', () => {
  it('labels I in C major', () => {
    expect(analyzeChord('C', 'C major')).toMatchObject({
      numeral: 'I',
      function: 'tonic',
      degree: 0,
      root: 'C',
      bass: null,
      inversion: null,
    });
  });

  it('labels V7 in C major', () => {
    const analysis = analyzeChord('G7', 'C major');
    expect(analysis?.numeral).toBe('V7');
    expect(analysis?.function).toBe('dominant');
  });

  it('labels ii in C major', () => {
    expect(analyzeChord('Dm', 'C major')?.numeral).toBe('ii');
  });

  it('labels vii° in C major', () => {
    expect(analyzeChord('Bdim', 'C major')?.numeral).toBe('vii°');
  });
});

describe('analyzeChord — diatonic minor with raised dominant', () => {
  it('labels i and iv in A minor', () => {
    expect(analyzeChord('Am', 'A minor')?.numeral).toBe('i');
    expect(analyzeChord('Dm', 'A minor')?.numeral).toBe('iv');
  });

  it('treats V in A minor as dominant harmony', () => {
    const analysis = analyzeChord('E', 'A minor');
    expect(analysis?.numeral).toBe('V');
    expect(analysis?.function).toBe('dominant');
  });

  it('labels the raised leading-tone chord in A minor', () => {
    const analysis = analyzeChord('G#dim', 'A minor');
    expect(analysis?.numeral).toBe('vii°');
    expect(analysis?.function).toBe('dominant');
  });
});

describe('analyzeChord — slash chords', () => {
  it('formats triad inversions with figured-bass shorthand', () => {
    expect(analyzeChord('C/E', 'C major')).toMatchObject({
      numeral: 'I6',
      bass: 'E',
      inversion: 'first',
    });

    expect(analyzeChord('G/B', 'C major')).toMatchObject({
      numeral: 'V6',
      bass: 'B',
      inversion: 'first',
    });
  });

  it('formats seventh-chord inversions with 42 notation', () => {
    expect(analyzeChord('G7/F', 'C major')).toMatchObject({
      numeral: 'V42',
      bass: 'F',
      inversion: 'third',
    });
  });

  it('keeps the root reading when the slash bass is not a chord tone', () => {
    expect(analyzeChord('C/F', 'C major')).toMatchObject({
      numeral: 'I',
      bass: 'F',
      inversion: null,
    });
  });
});

describe('analyzeChord — non-diatonic fallback', () => {
  it('labels secondary dominants and applied leading tones', () => {
    expect(analyzeChord('D', 'C major')).toMatchObject({
      numeral: 'V/V',
      function: 'dominant',
    });

    expect(analyzeChord('F#dim', 'C major')).toMatchObject({
      numeral: 'vii°/V',
      function: 'dominant',
    });
  });

  it('labels borrowed and altered same-root chords without returning null', () => {
    expect(analyzeChord('Fm', 'C major')).toMatchObject({
      numeral: 'iv',
      function: 'chromatic',
    });

    expect(analyzeChord('Dm7b5', 'C major')).toMatchObject({
      numeral: 'iiø7',
      function: 'chromatic',
    });

    expect(analyzeChord('Gsus4', 'C major')).toMatchObject({
      numeral: 'V(sus4)',
      function: 'chromatic',
    });

    expect(analyzeChord('Eadd9', 'C major')).toMatchObject({
      numeral: 'III(add9)',
      function: 'chromatic',
    });
  });

  it('labels chromatic accidentals with a chromatic marker', () => {
    expect(analyzeChord('Bb', 'C major')).toMatchObject({
      numeral: 'bVII',
      function: 'chromatic',
    });

    expect(analyzeChord('Ab', 'C major')).toMatchObject({
      numeral: 'bVI',
      function: 'chromatic',
    });

    expect(analyzeChord('F#', 'C major')).toMatchObject({
      numeral: '#IV',
      function: 'chromatic',
    });
  });

  it('never returns null for well-formed chord tokens with a valid key', () => {
    for (const chord of ['C', 'C#', 'Dbm', 'F#m7', 'Bb7', 'Eadd9', 'Gsus4', 'Dm7b5']) {
      expect(analyzeChord(chord, 'C major')).not.toBeNull();
      expect(getChordNumeral(chord, 'C major')).not.toBeNull();
    }
  });
});

describe('getChordColor', () => {
  it('uses the dominant color for applied and minor-key dominant chords', () => {
    expect(getChordColor('D', 'C major')).toBe(CHORD_FUNCTION_COLORS.dominant);
    expect(getChordColor('E', 'A minor')).toBe(CHORD_FUNCTION_COLORS.dominant);
  });

  it('uses the chromatic color for borrowed and accidental chords', () => {
    expect(getChordColor('Fm', 'C major')).toBe(CHORD_FUNCTION_COLORS.chromatic);
    expect(getChordColor('Bb', 'C major')).toBe(CHORD_FUNCTION_COLORS.chromatic);
  });
});

describe('deduplicateChords', () => {
  it('deduplicates slash chords after normalizing spacing', () => {
    expect(deduplicateChords(['C/E', 'C / E', 'G'])).toEqual(['C/E', 'G']);
  });
});

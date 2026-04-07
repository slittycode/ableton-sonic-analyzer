/**
 * Chord theory utilities for deriving Roman numeral labels and function-based
 * colors from chord names relative to a detected key center.
 */

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const;

const ENHARMONIC_MAP: Record<string, string> = {
  'Db': 'C#', 'Eb': 'D#', 'Fb': 'E', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#',
  'Cb': 'B', 'E#': 'F', 'B#': 'C',
};

const MAJOR_SCALE_INTERVALS = [0, 2, 4, 5, 7, 9, 11];
const MINOR_SCALE_INTERVALS = [0, 2, 3, 5, 7, 8, 10];

const MAJOR_NUMERALS = ['I', 'ii', 'iii', 'IV', 'V', 'vi', 'vii°'];
const MINOR_NUMERALS = ['i', 'ii°', 'III', 'iv', 'v', 'VI', 'VII'];

export type ChordFunction = 'tonic' | 'supertonic' | 'mediant' | 'subdominant' | 'dominant' | 'submediant' | 'leading';

const DEGREE_TO_FUNCTION: ChordFunction[] = [
  'tonic', 'supertonic', 'mediant', 'subdominant', 'dominant', 'submediant', 'leading',
];

export const CHORD_FUNCTION_COLORS: Record<ChordFunction, string> = {
  tonic: '#ff8800',
  supertonic: '#38bdf8',
  mediant: '#8a64ff',
  subdominant: '#00c896',
  dominant: '#ffb800',
  submediant: '#8a64ff',
  leading: '#ff3333',
};

export interface ChordAnalysis {
  numeral: string;
  function: ChordFunction;
  color: string;
  degree: number;
}

function normalizeNote(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const upper = trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
  if (ENHARMONIC_MAP[upper]) return ENHARMONIC_MAP[upper];
  const idx = NOTE_NAMES.indexOf(upper as typeof NOTE_NAMES[number]);
  return idx >= 0 ? NOTE_NAMES[idx] : null;
}

function parseChordRoot(chord: string): string | null {
  const match = chord.trim().match(/^([A-Ga-g][#b]?)/);
  if (!match) return null;
  return normalizeNote(match[1]);
}

function parseKeySignature(key: string): { root: string; isMinor: boolean } | null {
  const trimmed = key.trim();
  const match = trimmed.match(/^([A-Ga-g][#b]?)\s*(major|minor|maj|min|m)?$/i);
  if (!match) return null;
  const root = normalizeNote(match[1]);
  if (!root) return null;
  const qualifier = (match[2] || '').toLowerCase();
  const isMinor = qualifier === 'minor' || qualifier === 'min' || qualifier === 'm';
  return { root, isMinor };
}

function noteIndex(note: string): number {
  return NOTE_NAMES.indexOf(note as typeof NOTE_NAMES[number]);
}

function isMinorChord(chord: string): boolean {
  const body = chord.replace(/^[A-Ga-g][#b]?/, '');
  return /^m(?!aj)/i.test(body) || /min/i.test(body);
}

export function analyzeChord(chord: string, key: string | null): ChordAnalysis | null {
  if (!key) return null;

  const parsed = parseKeySignature(key);
  if (!parsed) return null;

  const chordRoot = parseChordRoot(chord);
  if (!chordRoot) return null;

  const rootIdx = noteIndex(parsed.root);
  const chordIdx = noteIndex(chordRoot);
  if (rootIdx < 0 || chordIdx < 0) return null;

  const interval = (chordIdx - rootIdx + 12) % 12;
  const scale = parsed.isMinor ? MINOR_SCALE_INTERVALS : MAJOR_SCALE_INTERVALS;
  const numerals = parsed.isMinor ? MINOR_NUMERALS : MAJOR_NUMERALS;

  const degree = scale.indexOf(interval);
  if (degree < 0) return null;

  const fn = DEGREE_TO_FUNCTION[degree];
  return {
    numeral: numerals[degree],
    function: fn,
    color: CHORD_FUNCTION_COLORS[fn],
    degree,
  };
}

export function getChordColor(chord: string, key: string | null): string {
  const analysis = analyzeChord(chord, key);
  if (analysis) return analysis.color;

  const normalized = chord.trim().toLowerCase();
  if (/(dim|°|o)(?![a-z])/.test(normalized)) return '#ff3333';
  if (/(aug|\+)/.test(normalized)) return '#ffb800';
  if (isMinorChord(chord)) return '#8a64ff';
  return '#ff8800';
}

export function getChordNumeral(chord: string, key: string | null): string | null {
  const analysis = analyzeChord(chord, key);
  return analysis?.numeral ?? null;
}

export function deduplicateChords(chords: string[]): string[] {
  const seen = new Set<string>();
  return chords.filter((c) => {
    const key = c.trim();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

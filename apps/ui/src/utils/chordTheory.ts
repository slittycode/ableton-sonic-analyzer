/**
 * Chord theory utilities for deriving Roman numeral labels and function-based
 * colors from chord names relative to a detected key center.
 */

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const;

const ENHARMONIC_MAP: Record<string, string> = {
  Db: 'C#',
  Eb: 'D#',
  Fb: 'E',
  Gb: 'F#',
  Ab: 'G#',
  Bb: 'A#',
  Cb: 'B',
  'E#': 'F',
  'B#': 'C',
};

const MAJOR_SCALE_INTERVALS = [0, 2, 4, 5, 7, 9, 11] as const;
const MINOR_SCALE_INTERVALS = [0, 2, 3, 5, 7, 8, 10] as const;
const DEGREE_ROMANS = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII'] as const;
const MAJOR_TARGET_NUMERALS = ['I', 'ii', 'iii', 'IV', 'V', 'vi', 'vii°'] as const;
const MINOR_TARGET_NUMERALS = ['i', 'ii°', 'III', 'iv', 'v', 'VI', 'VII'] as const;
const MAJOR_TRIAD_QUALITIES = ['major', 'minor', 'minor', 'major', 'major', 'minor', 'diminished'] as const;
const MINOR_TRIAD_QUALITIES = ['minor', 'diminished', 'major', 'minor', 'minor', 'major', 'major'] as const;
const MAJOR_FUNCTION_LABELS = [
  'Tonic',
  'Predominant',
  'Tonic extension',
  'Predominant',
  'Dominant',
  'Tonic relative',
  'Leading-tone tension',
] as const;
const MINOR_FUNCTION_LABELS = [
  'Tonic',
  'Predominant',
  'Relative major',
  'Predominant',
  'Modal dominant',
  'Tonic relative',
  'Subtonic',
] as const;

export type ChordFunction =
  | 'tonic'
  | 'supertonic'
  | 'mediant'
  | 'subdominant'
  | 'dominant'
  | 'submediant'
  | 'leading'
  | 'chromatic';

type TriadQuality = 'major' | 'minor' | 'diminished' | 'augmented' | 'suspended' | 'power';
type RomanQuality = 'major' | 'minor' | 'diminished' | 'half-diminished' | 'augmented' | 'suspended' | 'power';
type SeventhKind = 'none' | 'minor7' | 'major7' | 'diminished7';
export type ChordInversion = 'root' | 'first' | 'second' | 'third';
type CaseStyle = 'upper' | 'lower';

const DEGREE_TO_FUNCTION: Array<Exclude<ChordFunction, 'chromatic'>> = [
  'tonic',
  'supertonic',
  'mediant',
  'subdominant',
  'dominant',
  'submediant',
  'leading',
];

export const CHORD_FUNCTION_COLORS: Record<ChordFunction, string> = {
  tonic: '#ff8800',
  supertonic: '#38bdf8',
  mediant: '#8a64ff',
  subdominant: '#00c896',
  dominant: '#ffb800',
  submediant: '#8a64ff',
  leading: '#ff3333',
  chromatic: '#6b7280',
};

export interface ChordAnalysis {
  numeral: string;
  function: ChordFunction;
  functionLabel: string;
  color: string;
  degree: number;
  root: string;
  bass: string | null;
  inversion: ChordInversion | null;
}

interface ParsedChordSymbol {
  root: string;
  bass: string | null;
  triadQuality: TriadQuality;
  romanQuality: RomanQuality;
  seventhKind: SeventhKind;
  displaySuffix: string;
  toneIntervals: number[];
  inversion: ChordInversion | null;
}

interface ParsedKeySignature {
  root: string;
  isMinor: boolean;
}

interface DegreeResolution {
  degree: number;
  accidentalPrefix: '' | 'b' | '#';
}

function normalizeNote(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const upper = trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
  if (ENHARMONIC_MAP[upper]) return ENHARMONIC_MAP[upper];
  const idx = NOTE_NAMES.indexOf(upper as typeof NOTE_NAMES[number]);
  return idx >= 0 ? NOTE_NAMES[idx] : null;
}

function normalizeChordText(chord: string): string {
  return chord.trim().replace(/\s*\/\s*/g, '/').replace(/\s+/g, ' ');
}

function parseKeySignature(key: string): ParsedKeySignature | null {
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
  const normalized = normalizeChordText(chord);
  const slashMatch = normalized.match(/^(.*)\/([A-Ga-g][#b]?)$/);
  const head = slashMatch ? slashMatch[1] : normalized;
  const body = head.replace(/^[A-Ga-g][#b]?/, '');
  return /^m(?!aj)/i.test(body) || /^min/i.test(body) || /^-/i.test(body);
}

function parseMinorExtension(compact: string): { suffix: string } | null {
  const match = compact.match(/^(?:m|min|-)(7|9|11|13)$/);
  if (!match) return null;
  return { suffix: match[1] };
}

function parseMinorAddedTone(compact: string): { suffix: string } | null {
  const match = compact.match(/^(?:m|min|-)(add9)$/);
  if (!match) return null;
  return { suffix: match[1] };
}

function parseMajorExtension(compact: string): { suffix: string } | null {
  const match = compact.match(/^(maj7|maj9|maj11|maj13|Δ7|Δ9|Δ11|Δ13)$/i);
  if (!match) return null;
  const raw = match[1].replace(/^Δ/i, 'maj');
  return { suffix: raw.toLowerCase() };
}

function parseChordBody(body: string): Omit<ParsedChordSymbol, 'root' | 'bass' | 'inversion'> | null {
  const compact = body.toLowerCase().replace(/\s+/g, '');
  if (!compact || compact === 'maj') {
    return {
      triadQuality: 'major',
      romanQuality: 'major',
      seventhKind: 'none',
      displaySuffix: '',
      toneIntervals: [0, 4, 7],
    };
  }

  if (/^(ø7|m7b5|min7b5|-7b5)$/.test(compact)) {
    return {
      triadQuality: 'diminished',
      romanQuality: 'half-diminished',
      seventhKind: 'minor7',
      displaySuffix: 'ø7',
      toneIntervals: [0, 3, 6, 10],
    };
  }

  if (/^(dim7|°7|o7)$/.test(compact)) {
    return {
      triadQuality: 'diminished',
      romanQuality: 'diminished',
      seventhKind: 'diminished7',
      displaySuffix: '°7',
      toneIntervals: [0, 3, 6, 9],
    };
  }

  if (/^(dim|°|o)$/.test(compact)) {
    return {
      triadQuality: 'diminished',
      romanQuality: 'diminished',
      seventhKind: 'none',
      displaySuffix: '°',
      toneIntervals: [0, 3, 6],
    };
  }

  if (/^(aug|\+)$/.test(compact)) {
    return {
      triadQuality: 'augmented',
      romanQuality: 'augmented',
      seventhKind: 'none',
      displaySuffix: '+',
      toneIntervals: [0, 4, 8],
    };
  }

  if (/^(sus|sus4)$/.test(compact)) {
    return {
      triadQuality: 'suspended',
      romanQuality: 'suspended',
      seventhKind: 'none',
      displaySuffix: '(sus4)',
      toneIntervals: [0, 5, 7],
    };
  }

  if (/^sus2$/.test(compact)) {
    return {
      triadQuality: 'suspended',
      romanQuality: 'suspended',
      seventhKind: 'none',
      displaySuffix: '(sus2)',
      toneIntervals: [0, 2, 7],
    };
  }

  if (/^5$/.test(compact)) {
    return {
      triadQuality: 'power',
      romanQuality: 'power',
      seventhKind: 'none',
      displaySuffix: '5',
      toneIntervals: [0, 7],
    };
  }

  const majorExtension = parseMajorExtension(compact);
  if (majorExtension) {
    return {
      triadQuality: 'major',
      romanQuality: 'major',
      seventhKind: 'major7',
      displaySuffix: majorExtension.suffix,
      toneIntervals: [0, 4, 7, 11],
    };
  }

  const minorExtension = parseMinorExtension(compact);
  if (minorExtension) {
    return {
      triadQuality: 'minor',
      romanQuality: 'minor',
      seventhKind: 'minor7',
      displaySuffix: minorExtension.suffix,
      toneIntervals: [0, 3, 7, 10],
    };
  }

  const minorAddedTone = parseMinorAddedTone(compact);
  if (minorAddedTone) {
    return {
      triadQuality: 'minor',
      romanQuality: 'minor',
      seventhKind: 'none',
      displaySuffix: `(${minorAddedTone.suffix})`,
      toneIntervals: [0, 3, 7],
    };
  }

  if (/^(m|min|-)$/.test(compact)) {
    return {
      triadQuality: 'minor',
      romanQuality: 'minor',
      seventhKind: 'none',
      displaySuffix: '',
      toneIntervals: [0, 3, 7],
    };
  }

  if (/^(7|9|11|13)$/.test(compact)) {
    return {
      triadQuality: 'major',
      romanQuality: 'major',
      seventhKind: 'minor7',
      displaySuffix: compact,
      toneIntervals: [0, 4, 7, 10],
    };
  }

  if (/^add9$/.test(compact)) {
    return {
      triadQuality: 'major',
      romanQuality: 'major',
      seventhKind: 'none',
      displaySuffix: '(add9)',
      toneIntervals: [0, 4, 7],
    };
  }

  if (/^(6|maj6)$/.test(compact)) {
    return {
      triadQuality: 'major',
      romanQuality: 'major',
      seventhKind: 'none',
      displaySuffix: '(6)',
      toneIntervals: [0, 4, 7],
    };
  }

  if (/^(m6|min6|-6)$/.test(compact)) {
    return {
      triadQuality: 'minor',
      romanQuality: 'minor',
      seventhKind: 'none',
      displaySuffix: '(6)',
      toneIntervals: [0, 3, 7],
    };
  }

  return null;
}

function getSlashInversion(root: string, bass: string, toneIntervals: number[]): ChordInversion | null {
  const rootIdx = noteIndex(root);
  const bassIdx = noteIndex(bass);
  if (rootIdx < 0 || bassIdx < 0) return null;

  const interval = (bassIdx - rootIdx + 12) % 12;
  const uniqueIntervals = Array.from(new Set(toneIntervals));
  if (interval === 0) return 'root';
  if (uniqueIntervals[1] === interval) return 'first';
  if (uniqueIntervals[2] === interval) return 'second';
  if (uniqueIntervals[3] === interval) return 'third';
  return null;
}

function parseChordSymbol(chord: string): ParsedChordSymbol | null {
  const normalized = normalizeChordText(chord);
  if (!normalized) return null;

  const parts = normalized.split('/');
  if (parts.length > 2) return null;

  const [head, bassPart] = parts;
  const bass = bassPart ? normalizeNote(bassPart) : null;
  if (bassPart && !bass) return null;

  const match = head.match(/^([A-Ga-g][#b]?)(.*)$/);
  if (!match) return null;

  const root = normalizeNote(match[1]);
  if (!root) return null;

  const parsedBody = parseChordBody(match[2] || '');
  if (!parsedBody) return null;

  const inversion = bass ? getSlashInversion(root, bass, parsedBody.toneIntervals) : null;
  return {
    root,
    bass,
    inversion,
    ...parsedBody,
  };
}

function getExpectedTriadQualities(isMinor: boolean) {
  return isMinor ? MINOR_TRIAD_QUALITIES : MAJOR_TRIAD_QUALITIES;
}

function getFunctionLabels(isMinor: boolean) {
  return isMinor ? MINOR_FUNCTION_LABELS : MAJOR_FUNCTION_LABELS;
}

function getTargetNumerals(isMinor: boolean) {
  return isMinor ? MINOR_TARGET_NUMERALS : MAJOR_TARGET_NUMERALS;
}

function getScaleIntervals(isMinor: boolean) {
  return isMinor ? MINOR_SCALE_INTERVALS : MAJOR_SCALE_INTERVALS;
}

function getCaseStyleForChord(parsedChord: ParsedChordSymbol, fallback: CaseStyle): CaseStyle {
  switch (parsedChord.romanQuality) {
    case 'major':
    case 'augmented':
      return 'upper';
    case 'minor':
    case 'diminished':
    case 'half-diminished':
      return 'lower';
    case 'suspended':
    case 'power':
      return fallback;
  }
}

function buildRomanBase(resolution: DegreeResolution, caseStyle: CaseStyle): string {
  const base = DEGREE_ROMANS[resolution.degree];
  return resolution.accidentalPrefix + (caseStyle === 'upper' ? base : base.toLowerCase());
}

function getInversionSuffix(parsedChord: ParsedChordSymbol): string {
  const inversion = parsedChord.inversion;
  if (!inversion || inversion === 'root') {
    return parsedChord.displaySuffix;
  }

  if (parsedChord.seventhKind !== 'none') {
    const figure = inversion === 'first' ? '65' : inversion === 'second' ? '43' : inversion === 'third' ? '42' : '';
    if (!figure) return parsedChord.displaySuffix;
    if (parsedChord.romanQuality === 'half-diminished') return `ø${figure}`;
    if (parsedChord.romanQuality === 'diminished' && parsedChord.seventhKind === 'diminished7') return `°${figure}`;
    return figure;
  }

  const figure = inversion === 'first' ? '6' : inversion === 'second' ? '64' : '';
  if (!figure) return parsedChord.displaySuffix;
  if (parsedChord.romanQuality === 'diminished') return `°${figure}`;
  if (parsedChord.romanQuality === 'augmented') return `+${figure}`;
  if (parsedChord.romanQuality === 'suspended' || parsedChord.romanQuality === 'power') {
    return `${figure}${parsedChord.displaySuffix}`;
  }
  return figure;
}

function buildResolvedNumeral(
  resolution: DegreeResolution,
  parsedChord: ParsedChordSymbol,
  fallbackCase: CaseStyle,
): string {
  const caseStyle = getCaseStyleForChord(parsedChord, fallbackCase);
  const base = buildRomanBase(resolution, caseStyle);
  return `${base}${getInversionSuffix(parsedChord)}`;
}

function formatFunctionLabel(baseLabel: string, inversion: ChordInversion | null): string {
  if (!inversion || inversion === 'root') return baseLabel;
  if (inversion === 'first') return `${baseLabel} (1st inversion)`;
  if (inversion === 'second') return `${baseLabel} (2nd inversion)`;
  return `${baseLabel} (3rd inversion)`;
}

function buildAnalysis(
  numeral: string,
  fn: ChordFunction,
  functionLabel: string,
  degree: number,
  parsedChord: ParsedChordSymbol,
): ChordAnalysis {
  return {
    numeral,
    function: fn,
    functionLabel,
    color: CHORD_FUNCTION_COLORS[fn],
    degree,
    root: parsedChord.root,
    bass: parsedChord.bass,
    inversion: parsedChord.inversion,
  };
}

function isDiatonicExactMatch(parsedChord: ParsedChordSymbol, expectedTriad: TriadQuality): boolean {
  if (parsedChord.romanQuality === 'suspended' || parsedChord.romanQuality === 'power' || parsedChord.romanQuality === 'augmented') {
    return false;
  }

  if (expectedTriad === 'diminished') {
    if (parsedChord.romanQuality === 'half-diminished') return true;
    return parsedChord.triadQuality === 'diminished' && parsedChord.seventhKind !== 'diminished7';
  }

  return parsedChord.triadQuality === expectedTriad;
}

function resolveChromaticDegree(interval: number, isMinor: boolean): DegreeResolution | null {
  if (interval === 6) {
    return { degree: 3, accidentalPrefix: '#' };
  }

  const scale = getScaleIntervals(isMinor);
  for (let degree = 0; degree < scale.length; degree += 1) {
    if (degree === 0) continue;
    if ((scale[degree] + 11) % 12 === interval) {
      return { degree, accidentalPrefix: 'b' };
    }
  }

  for (let degree = 0; degree < scale.length; degree += 1) {
    if ((scale[degree] + 1) % 12 === interval) {
      return { degree, accidentalPrefix: '#' };
    }
  }

  return null;
}

function resolveAppliedChord(
  interval: number,
  parsedChord: ParsedChordSymbol,
  isMinor: boolean,
): ChordAnalysis | null {
  const scale = getScaleIntervals(isMinor);
  const targetNumerals = getTargetNumerals(isMinor);

  const isAppliedDominantCandidate =
    parsedChord.romanQuality === 'major' &&
    (parsedChord.displaySuffix === '' || /^(7|9|11|13)$/.test(parsedChord.displaySuffix));

  const isAppliedLeadingToneCandidate =
    parsedChord.romanQuality === 'diminished' || parsedChord.romanQuality === 'half-diminished';

  for (let degree = 0; degree < scale.length - 1; degree += 1) {
    const targetInterval = scale[degree];
    const targetNumeral = targetNumerals[degree];

    if (isAppliedDominantCandidate && ((targetInterval + 7) % 12) === interval) {
      const head = parsedChord.displaySuffix === '' ? 'V' : `V${parsedChord.displaySuffix}`;
      return buildAnalysis(
        `${head}/${targetNumeral}`,
        'dominant',
        `Applied dominant of ${targetNumeral}`,
        degree,
        parsedChord,
      );
    }

    if (isAppliedLeadingToneCandidate && ((targetInterval + 11) % 12) === interval) {
      const head =
        parsedChord.romanQuality === 'half-diminished'
          ? 'viiø7'
          : parsedChord.seventhKind === 'diminished7'
            ? 'vii°7'
            : 'vii°';
      return buildAnalysis(
        `${head}/${targetNumeral}`,
        'dominant',
        `Applied leading-tone of ${targetNumeral}`,
        degree,
        parsedChord,
      );
    }
  }

  return null;
}

function resolveMinorKeyDominantException(
  interval: number,
  parsedChord: ParsedChordSymbol,
  isMinor: boolean,
): ChordAnalysis | null {
  if (!isMinor) return null;

  if (
    interval === 7 &&
    parsedChord.romanQuality === 'major' &&
    (parsedChord.displaySuffix === '' || /^(7|9|11|13)$/.test(parsedChord.displaySuffix))
  ) {
    return buildAnalysis(
      buildResolvedNumeral({ degree: 4, accidentalPrefix: '' }, parsedChord, 'upper'),
      'dominant',
      formatFunctionLabel('Dominant', parsedChord.inversion),
      4,
      parsedChord,
    );
  }

  if ((parsedChord.romanQuality === 'diminished' || parsedChord.romanQuality === 'half-diminished') && interval === 11) {
    return buildAnalysis(
      buildResolvedNumeral({ degree: 6, accidentalPrefix: '' }, parsedChord, 'lower'),
      'dominant',
      formatFunctionLabel('Leading-tone dominant', parsedChord.inversion),
      6,
      parsedChord,
    );
  }

  return null;
}

export function analyzeChord(chord: string, key: string | null): ChordAnalysis | null {
  if (!key) return null;

  const parsedKey = parseKeySignature(key);
  if (!parsedKey) return null;

  const parsedChord = parseChordSymbol(chord);
  if (!parsedChord) return null;

  const keyRootIdx = noteIndex(parsedKey.root);
  const chordRootIdx = noteIndex(parsedChord.root);
  if (keyRootIdx < 0 || chordRootIdx < 0) return null;

  const interval = (chordRootIdx - keyRootIdx + 12) % 12;
  const scale = getScaleIntervals(parsedKey.isMinor);
  const expectedTriads = getExpectedTriadQualities(parsedKey.isMinor);
  const degree = (scale as readonly number[]).indexOf(interval);

  if (degree >= 0 && isDiatonicExactMatch(parsedChord, expectedTriads[degree])) {
    const functionLabels = getFunctionLabels(parsedKey.isMinor);
    const fn = DEGREE_TO_FUNCTION[degree];
    return buildAnalysis(
      buildResolvedNumeral(
        { degree, accidentalPrefix: '' },
        parsedChord,
        expectedTriads[degree] === 'minor' || expectedTriads[degree] === 'diminished' ? 'lower' : 'upper',
      ),
      fn,
      formatFunctionLabel(functionLabels[degree], parsedChord.inversion),
      degree,
      parsedChord,
    );
  }

  const minorDominantException = resolveMinorKeyDominantException(interval, parsedChord, parsedKey.isMinor);
  if (minorDominantException) {
    return minorDominantException;
  }

  const appliedChord = resolveAppliedChord(interval, parsedChord, parsedKey.isMinor);
  if (appliedChord) {
    return appliedChord;
  }

  if (degree >= 0) {
    return buildAnalysis(
      buildResolvedNumeral(
        { degree, accidentalPrefix: '' },
        parsedChord,
        expectedTriads[degree] === 'minor' || expectedTriads[degree] === 'diminished' ? 'lower' : 'upper',
      ),
      'chromatic',
      formatFunctionLabel(`Chromatic ${buildResolvedNumeral({ degree, accidentalPrefix: '' }, parsedChord, 'upper')}`, parsedChord.inversion),
      degree,
      parsedChord,
    );
  }

  const chromaticResolution = resolveChromaticDegree(interval, parsedKey.isMinor);
  if (!chromaticResolution) return null;

  const numeral = buildResolvedNumeral(chromaticResolution, parsedChord, 'upper');
  return buildAnalysis(
    numeral,
    'chromatic',
    formatFunctionLabel(`Chromatic ${numeral}`, parsedChord.inversion),
    chromaticResolution.degree,
    parsedChord,
  );
}

export function getChordColor(chord: string, key: string | null): string {
  const analysis = analyzeChord(chord, key);
  if (analysis) return analysis.color;

  const parsedChord = parseChordSymbol(chord);
  if (!key || !parsedChord) {
    const normalized = normalizeChordText(chord).toLowerCase();
    if (/(dim|°|o)(?![a-z])/.test(normalized)) return '#ff3333';
    if (/(aug|\+)/.test(normalized)) return '#ffb800';
    if (isMinorChord(chord)) return '#8a64ff';
    return '#ff8800';
  }

  return CHORD_FUNCTION_COLORS.chromatic;
}

export function getChordNumeral(chord: string, key: string | null): string | null {
  const analysis = analyzeChord(chord, key);
  return analysis?.numeral ?? null;
}

export function deduplicateChords(chords: string[]): string[] {
  const seen = new Set<string>();
  return chords.filter((chord) => {
    const normalized = normalizeChordText(chord);
    if (!normalized || seen.has(normalized)) return false;
    seen.add(normalized);
    return true;
  });
}

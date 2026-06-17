/**
 * Cross-boundary citation contract: every citable Phase 1 field the backend
 * emits must survive the frontend parser.
 *
 * WHY THIS EXISTS. The Phase 1 contract lives in three hand-maintained
 * representations — `analyze.py` output, `apps/backend/JSON_SCHEMA.md`, and
 * `Phase1Result` in `src/types/measurement.ts` — with no generated source of
 * truth between them (CLAUDE.md tripwire #3). Most of `parsePhase1Result`
 * passes detail blocks through verbatim (`isRecord(x) ? x : null`), so nested
 * fields survive by construction. But ~12 `parseOptional*` reconstructors in
 * `backendPhase1Client.ts` rebuild their block field-by-field — and a field the
 * backend emits (and the Phase 2 prompt invites a citation to) that the
 * reconstructor forgets to forward is *silently dropped*. When that happens the
 * field's path is absent from `collectPhase1FieldPaths`, so a correct Gemini
 * citation to it fails the existence check and the chain of custody breaks on a
 * good recommendation. This is not hypothetical: `reverbDetail.preDelayMs`,
 * `reverbDetail.perBandRt60.*`, `vocalDetail.stemEnergyRatio`, and
 * `vocalDetail.stemOtherCorrelation` were each dropped exactly this way.
 *
 * WHAT IT GUARDS. The test feeds a comprehensive payload through the *real*
 * `parsePhase1Result`, runs the *real* citation walker `collectPhase1FieldPaths`
 * on the result, and asserts every path in `CITABLE_DETAIL_PATHS` survives. The
 * payload populates each field with a concrete non-null value, so a path is
 * present in the surviving set only if the reconstructor actually carried it
 * through — drop a field in any `parseOptional*` and its assertion fails by name.
 *
 * MAINTENANCE. When you add a citable field to a `parseOptional*` reconstructor
 * (or the Phase 2 prompt starts inviting a new citation), add it to BOTH
 * `COMPREHENSIVE_PHASE1` and `CITABLE_DETAIL_PATHS` below. This is the executable
 * mirror of JSON_SCHEMA.md's citable surface — the half tripwire #3 could not
 * defend, now made loud.
 */
import { describe, it, expect } from 'vitest';
import { parsePhase1Result } from '../../src/services/backendPhase1Client';
import { collectPhase1FieldPaths } from '../../src/services/phase2Validator';

/**
 * A maximal backend `phase1` payload: the required scalars `parsePhase1Result`
 * insists on, plus every field-by-field-reconstructed detail block fully
 * populated with non-null values. Pass-through blocks (spectralDetail,
 * grooveDetail, …) survive verbatim and are not the drop-risk surface, so they
 * are exercised elsewhere; the reshaping blocks (melodyDetail,
 * transcriptionDetail, rhythmTimeline, chordTimeline) have their own coverage in
 * backendPhase1Client.test.ts.
 */
const COMPREHENSIVE_PHASE1 = {
  // --- required scalars (parsePhase1Result throws without these) ---
  bpm: 128,
  bpmConfidence: 0.98,
  key: 'A minor',
  keyConfidence: 0.91,
  timeSignature: '4/4',
  durationSeconds: 184.2,
  lufsIntegrated: -8.4,
  truePeak: -0.5,
  stereoWidth: 0.75,
  stereoCorrelation: 0.82,
  spectralBalance: {
    subBass: -1.2,
    lowBass: 0.8,
    lowMids: 0.0,
    mids: -0.4,
    upperMids: 0.2,
    highs: 1.1,
    brilliance: 0.5,
  },

  // --- field-by-field reconstructed detail blocks (the drop-risk surface) ---
  reverbDetail: {
    rt60: 1.2,
    isWet: true,
    tailEnergyRatio: 0.31,
    measured: true,
    perBandRt60: { low: 1.4, lowMids: 1.2, highMids: 0.9, highs: 0.6 },
    preDelayMs: 22.5,
  },
  vocalDetail: {
    hasVocals: true,
    confidence: 0.77,
    vocalEnergyRatio: 0.41,
    formantStrength: 0.55,
    mfccLikelihood: 0.63,
    stemEnergyRatio: 0.12,
    stemOtherCorrelation: 0.34,
  },
  supersawDetail: {
    isSupersaw: true,
    confidence: 0.82,
    voiceCount: 7,
    avgDetuneCents: 18.5,
    spectralComplexity: 0.66,
  },
  bassDetail: {
    averageDecayMs: 180.0,
    type: 'rolling',
    transientRatio: 0.44,
    fundamentalHz: 55.0,
    transientCount: 96,
    swingPercent: 12.5,
    grooveType: 'slight-swing',
  },
  kickDetail: {
    isDistorted: true,
    thd: 0.28,
    harmonicRatio: 0.62,
    fundamentalHz: 48.0,
    kickCount: 128,
  },
  genreDetail: {
    genre: 'tech house',
    confidence: 0.74,
    secondaryGenre: 'techno',
    genreFamily: 'house',
    topScores: [
      { genre: 'tech house', score: 0.74 },
      { genre: 'techno', score: 0.51 },
    ],
  },
  acidDetail: {
    isAcid: true,
    confidence: 0.69,
    resonanceLevel: 0.58,
    centroidOscillationHz: 4.2,
    bassRhythmDensity: 0.47,
  },
  danceability: {
    danceability: 1.32,
    dfa: 0.88,
  },
  dynamicCharacter: {
    dynamicComplexity: 0.5,
    loudnessDb: -14.2,
    loudnessVariation: -14.2,
    spectralFlatness: 0.2,
    logAttackTime: -0.8,
    attackTimeStdDev: 0.15,
  },
  textureCharacter: {
    textureScore: 0.68,
    lowBandFlatness: 0.51,
    midBandFlatness: 0.72,
    highBandFlatness: 0.83,
    inharmonicity: 0.19,
  },
  beatsLoudness: {
    kickDominantRatio: 0.61,
    midDominantRatio: 0.22,
    highDominantRatio: 0.17,
    meanBeatLoudness: -9.4,
    beatLoudnessVariation: 0.12,
    beatCount: 128,
    accentPattern: [1, 0.4, 0.7, 0.4],
    patternBeatsPerBar: 4,
  },
  chordDetail: {
    chordSequence: ['Am', 'F', 'C', 'G'],
    chordStrength: 0.72,
    progression: ['i', 'VI', 'III', 'VII'],
    dominantChords: ['Am', 'F'],
    chordChangeCount: 4,
    chordTimelineSource: 'viterbi',
    chordTimelineAgreement: true,
  },
} as const;

/**
 * The citable nested field paths Phase 2 may reference and the parser must
 * therefore preserve. Grouped by reconstructed block; scalar fields only
 * (booleans like `isWet`/`hasVocals` are citable too but the scalars are the
 * drop-prone ones that motivated this test).
 */
const CITABLE_DETAIL_PATHS: readonly string[] = [
  // reverbDetail — the original silent-drop bug lived here
  'reverbDetail.rt60',
  'reverbDetail.tailEnergyRatio',
  'reverbDetail.preDelayMs',
  'reverbDetail.perBandRt60.low',
  'reverbDetail.perBandRt60.lowMids',
  'reverbDetail.perBandRt60.highMids',
  'reverbDetail.perBandRt60.highs',
  // vocalDetail — stemEnergyRatio / stemOtherCorrelation were dropped here
  'vocalDetail.confidence',
  'vocalDetail.vocalEnergyRatio',
  'vocalDetail.formantStrength',
  'vocalDetail.mfccLikelihood',
  'vocalDetail.stemEnergyRatio',
  'vocalDetail.stemOtherCorrelation',
  // supersawDetail
  'supersawDetail.confidence',
  'supersawDetail.voiceCount',
  'supersawDetail.avgDetuneCents',
  'supersawDetail.spectralComplexity',
  // bassDetail
  'bassDetail.averageDecayMs',
  'bassDetail.transientRatio',
  'bassDetail.fundamentalHz',
  'bassDetail.transientCount',
  'bassDetail.swingPercent',
  'bassDetail.grooveType',
  'bassDetail.type',
  // kickDetail
  'kickDetail.thd',
  'kickDetail.harmonicRatio',
  'kickDetail.fundamentalHz',
  'kickDetail.kickCount',
  // genreDetail
  'genreDetail.genre',
  'genreDetail.confidence',
  'genreDetail.secondaryGenre',
  'genreDetail.genreFamily',
  'genreDetail.topScores.score',
  // acidDetail
  'acidDetail.confidence',
  'acidDetail.resonanceLevel',
  'acidDetail.centroidOscillationHz',
  'acidDetail.bassRhythmDensity',
  // danceability
  'danceability.danceability',
  'danceability.dfa',
  // dynamicCharacter (note: loudnessVariation/loudnessDb are both preserved)
  'dynamicCharacter.dynamicComplexity',
  'dynamicCharacter.loudnessDb',
  'dynamicCharacter.loudnessVariation',
  'dynamicCharacter.spectralFlatness',
  'dynamicCharacter.logAttackTime',
  'dynamicCharacter.attackTimeStdDev',
  // textureCharacter
  'textureCharacter.textureScore',
  'textureCharacter.lowBandFlatness',
  'textureCharacter.midBandFlatness',
  'textureCharacter.highBandFlatness',
  'textureCharacter.inharmonicity',
  // beatsLoudness
  'beatsLoudness.kickDominantRatio',
  'beatsLoudness.midDominantRatio',
  'beatsLoudness.highDominantRatio',
  'beatsLoudness.meanBeatLoudness',
  'beatsLoudness.beatLoudnessVariation',
  'beatsLoudness.beatCount',
  // chordDetail
  'chordDetail.chordStrength',
  'chordDetail.chordChangeCount',
];

/**
 * The reconstructed blocks the comprehensive payload must populate. The
 * meta-guard below asserts each is non-null after parsing, so the contract can
 * never be satisfied vacuously by an emptied fixture.
 */
const RECONSTRUCTED_BLOCKS: readonly (keyof ReturnType<typeof parsePhase1Result>)[] = [
  'reverbDetail',
  'vocalDetail',
  'supersawDetail',
  'bassDetail',
  'kickDetail',
  'genreDetail',
  'acidDetail',
  'danceability',
  'dynamicCharacter',
  'textureCharacter',
  'beatsLoudness',
  'chordDetail',
];

describe('Phase 1 citation contract (cross-boundary field survival)', () => {
  const parsed = parsePhase1Result(COMPREHENSIVE_PHASE1);
  const survivingPaths = collectPhase1FieldPaths(parsed);

  it.each(CITABLE_DETAIL_PATHS)(
    'preserves citable path "%s" through parsePhase1Result',
    (path) => {
      expect(survivingPaths.has(path)).toBe(true);
    },
  );

  it('populates every reconstructed block (fixture is not vacuous)', () => {
    for (const block of RECONSTRUCTED_BLOCKS) {
      expect(parsed[block], `${block} should parse to a non-null block`).not.toBeNull();
    }
  });
});

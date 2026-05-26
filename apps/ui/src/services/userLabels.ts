/**
 * Audit Finding #2 + N3/N4/N8: every user-facing rendering of a Phase 1 field
 * path (e.g., `spectralBalance.highs`, `kickDetail.fundamentalHz`) currently
 * reads as raw JSON. Producers can't decode those.
 *
 * This file is the single translation layer from internal field paths to
 * producer-readable labels. Keep entries terse — they render in tight
 * "GROUNDED IN" rows where space is at a premium. When a path isn't in the
 * map, `humanizeFieldPath` falls back to a deterministic word-splitting rule
 * so unknown fields never expose raw camelCase to the user.
 *
 * Add entries here, not at the render site. If multiple paths need the same
 * label, that's a hint they should probably collapse into one citation, not
 * be duplicated in the map.
 */

/**
 * Curated field-path → producer label map. Roughly ordered by frequency in
 * Phase 2 output. Extend as new field paths show up in real citations.
 */
export const FIELD_LABELS: Record<string, string> = {
  // Tempo / key / meter
  bpm: 'Tempo',
  bpmConfidence: 'Tempo confidence',
  bpmPercival: 'Tempo (Percival cross-check)',
  bpmAgreement: 'Tempo cross-check',
  bpmRawOriginal: 'Tempo (raw, pre-correction)',
  bpmSource: 'Tempo source',
  key: 'Key',
  keyConfidence: 'Key confidence',
  keyProfile: 'Key profile',
  timeSignature: 'Meter',
  timeSignatureConfidence: 'Meter confidence',
  durationSeconds: 'Duration',

  // Loudness / dynamics
  lufsIntegrated: 'Integrated loudness',
  lufsRange: 'Loudness range',
  lufsMomentaryMax: 'Momentary loudness peak',
  lufsShortTermMax: 'Short-term loudness peak',
  truePeak: 'True peak',
  plr: 'Peak-to-loudness ratio',
  crestFactor: 'Crest factor',
  dynamicSpread: 'Dynamic spread',

  // Spectral balance (signed-dB deviations from a reference curve)
  'spectralBalance.subBass': 'Sub-bass balance',
  'spectralBalance.lowBass': 'Low-bass balance',
  'spectralBalance.lowMids': 'Low-mids balance',
  'spectralBalance.mids': 'Mids balance',
  'spectralBalance.upperMids': 'Upper-mids balance',
  'spectralBalance.highs': 'Highs balance',
  'spectralBalance.brilliance': 'Brilliance balance',

  // Stereo
  stereoWidth: 'Stereo width',
  stereoCorrelation: 'Stereo correlation',

  // Kick / drum detail
  'kickDetail.fundamentalHz': 'Kick fundamental frequency',
  'kickDetail.crestFactor': 'Kick crest factor',
  'kickDetail.thd': 'Kick harmonic distortion (THD)',
  'kickDetail.meanDecaySeconds': 'Kick mean decay',
  'hihatDetail.meanDecaySeconds': 'Hi-hat mean decay',

  // Sidechain / pumping
  'sidechainDetail.pumpingRate': 'Pumping rate',
  'sidechainDetail.pumpingStrength': 'Pumping strength',
  'sidechainDetail.pumpingRegularity': 'Pumping regularity',
  'sidechainDetail.pumpingConfidence': 'Pumping confidence',
  'sidechainDetail.envelopeShape': 'Pumping envelope shape',

  // Reverb / acid / vocals / supersaw detectors
  'reverbDetail.rt60': 'Reverb tail (RT60)',
  'reverbDetail.measured': 'Reverb measured',
  'reverbDetail.confidence': 'Reverb detection confidence',
  'acidDetail.isAcid': 'Acid bass detected',
  'acidDetail.confidence': 'Acid detection confidence',
  'vocalDetail.hasVocals': 'Vocals detected',
  'vocalDetail.confidence': 'Vocal detection confidence',
  'supersawDetail.isSupersaw': 'Supersaw detected',
  'supersawDetail.confidence': 'Supersaw detection confidence',

  // Genre / style
  'genreDetail.genre': 'Genre',
  'genreDetail.confidence': 'Genre confidence',

  // Melody / transcription / chords
  'melodyDetail.pitchConfidence': 'Melody pitch confidence',
  'melodyDetail.vibratoRate': 'Vibrato rate',
  'melodyDetail.vibratoExtent': 'Vibrato extent',
  'melodyDetail.vibratoConfidence': 'Vibrato confidence',
  'transcriptionDetail.averageConfidence': 'Note transcription confidence',
  'chordDetail.chordStrength': 'Chord progression confidence',
  'chordDetail.chordTimeline': 'Chord timeline',

  // Audio metadata
  sampleRate: 'Sample rate',
};

/**
 * Fallback humanizer for any path not in `FIELD_LABELS`. Splits on dots and
 * camelCase boundaries, lowercases, then capitalizes the first letter.
 *
 *   "kickDetail.fundamentalHz"  → "Kick detail · fundamental hz"
 *   "spectralBalance.highs"     → "Spectral balance · highs"
 *   "bpmConfidence"             → "Bpm confidence"   (lookup hits first)
 *
 * Deliberately gentle — don't try to be clever. The curated map is the place
 * for nuance; this fallback is just a "don't expose raw camelCase" floor.
 */
export function humanizeFieldPath(path: string): string {
  const mapped = FIELD_LABELS[path];
  if (mapped) return mapped;

  const segments = path.split('.').map((segment) =>
    segment
      // Insert a space before each uppercase letter that follows a lowercase
      // letter or digit — splits camelCase into words.
      .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
      // Same for the X-Y case "URLPath" -> "URL path".
      .replace(/([A-Z])([A-Z][a-z])/g, '$1 $2')
      .toLowerCase(),
  );

  const joined = segments.join(' · ');
  return joined.charAt(0).toUpperCase() + joined.slice(1);
}

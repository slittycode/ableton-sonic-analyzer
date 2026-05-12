import { Phase1Result, Phase2Result, AbletonRecommendation } from '../types';

export type ValidationViolationType =
  | 'NUMERIC_OVERRIDE'
  | 'GENRE_IGNORES_DSP'
  | 'BOUNDS_VIOLATION'
  | 'MISSING_CITATION'
  | 'TRIVIAL_CITATIONS'
  | 'NEW_FIELD_UNCITED'
  | 'LOW_CONFIDENCE_NOT_HEDGED'
  | 'RECOMMENDATION_SALVAGED';

export interface ValidationViolation {
  type: ValidationViolationType;
  field: string;
  phase1Value?: any;
  phase2Value?: any;
  severity: 'ERROR' | 'WARNING';
  message: string;
}

export interface ValidationReport {
  violations: ValidationViolation[];
  passed: boolean;
  summary: {
    errorCount: number;
    warningCount: number;
    checkedFields: number;
  };
}

// Constants for validation thresholds
const BPM_TOLERANCE = 2.0;
const LUFS_TOLERANCE = 5.0; // LUFS difference threshold for warnings

/**
 * Threshold above which an identical phase1Fields citation array, repeated
 * across recommendations, counts as "trivial" — Gemini gaming the contract by
 * citing the same anchor on every card instead of grounding each in a distinct
 * measurement.
 */
const TRIVIAL_CITATION_DOMINANCE_THRESHOLD = 0.6;

/**
 * Confidence below which paired recommendation text must use hedged language.
 * Mirrors the PURPOSE.md invariant: low-confidence measurements must propagate
 * to hedged recommendations, not confident-sounding guesses.
 */
const LOW_CONFIDENCE_THRESHOLD = 0.4;

/**
 * Phase 1 fields whose presence-but-zero-citations should warn. The list now
 * spans Phase 1.A (cheap-wins) through Phase 1.D #5 (RT60 per stem). If Gemini
 * ignores them after they land in the payload, the depth gain isn't reaching
 * the user. Add new paths here as later phases land.
 *
 * The path matcher is bidirectional with wildcard support — see
 * `pathCoversTracked` for the precise semantics:
 *   - "exact match"           — citation === tracked
 *   - "parent covers child"   — citation is a path-prefix of tracked
 *   - "child covers parent"   — tracked is a path-prefix of citation
 *   - "wildcard match"        — segment-wise equality, with `*` in either
 *                               position matching any single segment
 *
 * Wildcards (`*`) are the way stem-scoped paths are tracked without binding
 * to a specific stem name. e.g. `stemAnalysis.*.reverbDetail` is "covered"
 * by a citation against `stemAnalysis.bass.reverbDetail.preDelayMs`.
 */
export const PHASE1_NEW_FIELD_PATHS = [
  // Phase 1.A — cheap-win additions
  'lufsCurve',
  'lufsCurve.shortTerm',
  'lufsCurve.momentary',
  'spectralBalanceTimeSeries',
  'rhythmDetail.tempoCurve',
  'stereoDetail.correlationCurve',
  'arrangementDetail.noveltyCurve',
  // Phase 1.C — mid-investment new analyzers
  'transientDensityDetail',          // #1: per-band onset density
  'stereoDetail.bandCorrelations',   // #2: per-band L/R correlation
  'grooveDetail.perDrumSwing',       // #3: per-drum-group swing (kick / snare / hihat)
  'snareDetail',                     // #4: snare character (BandDrumDetail)
  'hihatDetail',                     // #4: hi-hat character (BandDrumDetail)
  'saturationDetail',                // #5: saturation / clipping signals
  'saturationDetail.peakRatio95to50',
  'saturationDetail.clippedSamplePercent',
  'sidechainDetail.envelopeShape32', // #6: 32nd-note sidechain envelope
  // Phase 1.D — bigger lifts
  'reverbDetail.perBandRt60',        // #5: RT60 per octave band
  'reverbDetail.preDelayMs',         // #5: median pre-delay
  'stemAnalysis.*.reverbDetail',     // #5: per-stem reverb (any of drums/bass/other/vocals)
] as const;

/**
 * Convenience subset used for "phase-aware" reporting (e.g. the live
 * comparator's split metrics). The full list above is the matcher's source
 * of truth; these helpers expose the structure.
 */
export const PHASE1A_FIELD_PATHS = PHASE1_NEW_FIELD_PATHS.slice(0, 7);
export const PHASE1_CD_FIELD_PATHS = PHASE1_NEW_FIELD_PATHS.slice(7);

/**
 * Backward-compat alias for any external consumer that referenced the old
 * name. Prefer `PHASE1_NEW_FIELD_PATHS` going forward.
 */
const PHASE1A_NEW_FIELD_PATHS = PHASE1_NEW_FIELD_PATHS;

/**
 * Maps a Phase 1 measurement path to its paired *Confidence path. When a
 * recommendation cites the left side, the validator looks up the right side
 * to decide whether the recommendation text must be hedged.
 *
 * Keep these conservative — only fields where the analyzer emits a confidence
 * sibling and where misuse would harm the user. Add detector confidences as
 * the audit surfaces patterns of over-confident recommendations.
 */
const CONFIDENCE_PAIRS: Record<string, string> = {
  'bpm': 'bpmConfidence',
  'key': 'keyConfidence',
  'timeSignature': 'timeSignatureConfidence',
  'acidDetail': 'acidDetail.confidence',
  'acidDetail.isAcid': 'acidDetail.confidence',
  'reverbDetail': 'reverbDetail.confidence',
  'vocalDetail': 'vocalDetail.confidence',
  'vocalDetail.hasVocals': 'vocalDetail.confidence',
  'supersawDetail': 'supersawDetail.confidence',
  'supersawDetail.isSupersaw': 'supersawDetail.confidence',
  'sidechainDetail': 'sidechainDetail.pumpingConfidence',
  'sidechainDetail.pumpingRate': 'sidechainDetail.pumpingConfidence',
  'sidechainDetail.pumpingStrength': 'sidechainDetail.pumpingConfidence',
  'sidechainDetail.pumpingRegularity': 'sidechainDetail.pumpingConfidence',
  'sidechainDetail.envelopeShape': 'sidechainDetail.pumpingConfidence',
  'melodyDetail': 'melodyDetail.pitchConfidence',
  'transcriptionDetail': 'transcriptionDetail.averageConfidence',
  'genreDetail': 'genreDetail.confidence',
  'chordDetail': 'chordDetail.chordStrength',
};

/**
 * Word lists used by the hedging check. Matched with word-boundary regexes —
 * "may" matches "may " but not "many", "must" matches "must " but not
 * "mustard". Keep these short and surgical; broader lists produce noise.
 */
const HEDGE_WORDS = [
  'possible', 'possibly', 'subtle', 'subtly', 'maybe', 'consider',
  'may', 'might', 'can', 'could', 'often', 'sometimes', 'lightly',
  'gently', 'tentative', 'try', 'experiment', 'optional', 'low-confidence',
  'low confidence', 'if needed', 'if present', 'where appropriate',
];

const IMPERATIVE_WORDS = [
  'mandatory', 'must', 'required', 'always', 'never', 'absolutely',
  'critical', 'essential', 'crucial', 'definitely', 'strictly',
  'prohibited', 'forbidden',
];

/**
 * Backend warning codes the validator should surface as RECOMMENDATION_SALVAGED.
 * Mirrors every code `_build_phase2_validation_warning()` can emit in
 * apps/backend/server_phase2.py — broader than the backend's own narrower
 * `_PHASE2_SALVAGE_WARNING_CODES` set because the decision gate cares about
 * any "Gemini emitted something invalid, server intervened" signal, not just
 * the items that were salvaged or dropped after a bounded salvage pass.
 */
const SALVAGE_WARNING_CODES = new Set([
  'DROPPED_INVALID_ARRAY_ITEM',
  'DROPPED_INVALID_STYLE_PROFILE',
  'COERCED_ENUM_VALUE',
  'COERCED_TRACK_CONTEXT',
  'BACKFILLED_FIELD',
  'AUTHORITATIVE_MEASUREMENT_OVERRIDDEN',
  'DEVICE_FAMILY_MISMATCH',
  'UNKNOWN_DEVICE',
  'UNKNOWN_PARAMETER',
  'UNKNOWN_TRACK_CONTEXT',
]);

/**
 * Optional diagnostics shape the validator accepts. Mirrors what the backend
 * envelope exposes under ``diagnostics.warnings`` after a Phase 2 run. The
 * validator surfaces any salvage codes here as RECOMMENDATION_SALVAGED
 * violations so the decision gate can fail when Gemini output is being
 * silently fixed up.
 */
export interface ValidationDiagnostics {
  warnings?: Array<{ code?: string; path?: string; message?: string }>;
}

/**
 * Validates that Phase 2 output is consistent with Phase 1 measurements.
 * Checks for numeric overrides, genre/DSP consistency, and physical bounds.
 */
export function validatePhase2Consistency(
  phase1: Phase1Result,
  phase2: Phase2Result,
  diagnostics?: ValidationDiagnostics,
): ValidationReport {
  const violations: ValidationViolation[] = [];
  let checkedFields = 0;

  // 1. Numeric override validations
  violations.push(...validateBPMConsistency(phase1, phase2));
  checkedFields++;

  violations.push(...validateKeyConsistency(phase1, phase2));
  checkedFields++;

  violations.push(...validateLUFSConsistency(phase1, phase2));
  checkedFields++;

  // 2. Genre/DSP context validation
  violations.push(...validateGenreDSPConsistency(phase1, phase2));
  checkedFields++;

  // 3. Numeric bounds validation
  violations.push(...validateNumericBounds(phase1, phase2));
  checkedFields++;

  // 4. Citation contract — only run on new-shape responses where at least one
  // recommendation already exposes phase1Fields. Legacy stored runs (predating
  // the citation contract) skip this check silently.
  if (isNewShapePhase2(phase2)) {
    violations.push(...validatePhase1FieldCitations(phase1, phase2));
    checkedFields++;

    // 5. Citation diversity — non-trivial spread across recommendations.
    violations.push(...validateCitationDiversity(phase2));
    checkedFields++;

    // 6. New-field coverage — Phase 1.A fields present in payload should be
    // cited at least once.
    violations.push(...validateNewFieldCoverage(phase1, phase2));
    checkedFields++;

    // 7. Low-confidence hedging — recommendation text grounded in a
    // low-confidence measurement must be hedged, not imperative.
    violations.push(...validateLowConfidenceHedging(phase1, phase2));
    checkedFields++;
  }

  // 8. Salvage warnings — only when diagnostics are passed in. Surfaces the
  // case where Gemini returned data the backend repaired or dropped.
  if (diagnostics) {
    violations.push(...validateSalvagedRecommendations(diagnostics));
    checkedFields++;
  }

  // Calculate summary statistics
  const errorCount = violations.filter(v => v.severity === 'ERROR').length;
  const warningCount = violations.filter(v => v.severity === 'WARNING').length;

  return {
    violations,
    passed: errorCount === 0,
    summary: {
      errorCount,
      warningCount,
      checkedFields,
    },
  };
}

/**
 * Returns true if at least one recommendation across mixAndMasterChain,
 * abletonRecommendations, or secretSauce.workflowSteps exposes a phase1Fields
 * array. Used to gate the citation contract check so legacy stored Phase 2
 * results from before the contract landed do not produce spurious errors.
 */
function isNewShapePhase2(phase2: Phase2Result): boolean {
  const buckets: Array<Array<{ phase1Fields?: string[] }>> = [
    phase2.mixAndMasterChain ?? [],
    phase2.abletonRecommendations ?? [],
    phase2.secretSauce?.workflowSteps ?? [],
  ];
  for (const bucket of buckets) {
    for (const rec of bucket) {
      if (Array.isArray(rec.phase1Fields)) {
        return true;
      }
    }
  }
  return false;
}

/**
 * Recursively collect every dotted path that resolves to a non-null value in
 * the Phase 1 result. Both intermediate keys and leaf scalars are included so
 * that citations like "kickDetail" and "kickDetail.fundamentalHz" both match.
 *
 * For arrays of objects, we also surface `path.field` shapes (e.g.
 * "arrangementDetail.noveltyPeaks.time") so Gemini can cite the field name
 * of array items without indexing into them.
 *
 * Exported for tests; consumed by validatePhase1FieldCitations.
 */
export function collectPhase1FieldPaths(phase1: Phase1Result): Set<string> {
  const paths = new Set<string>();
  walkForPaths(phase1, '', paths);
  return paths;
}

function walkForPaths(value: unknown, prefix: string, paths: Set<string>): void {
  if (value === null || value === undefined) {
    return;
  }
  if (Array.isArray(value)) {
    if (prefix.length > 0) {
      paths.add(prefix);
    }
    // For arrays of objects, register `prefix.field` paths so citations to a
    // field name on array items (e.g. "noveltyPeaks.time") are valid.
    for (const item of value) {
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        for (const key of Object.keys(item as Record<string, unknown>)) {
          const subPath = prefix ? `${prefix}.${key}` : key;
          walkForPaths((item as Record<string, unknown>)[key], subPath, paths);
        }
      }
    }
    return;
  }
  if (typeof value !== 'object') {
    if (prefix.length > 0) {
      paths.add(prefix);
    }
    return;
  }
  if (prefix.length > 0) {
    paths.add(prefix);
  }
  for (const key of Object.keys(value as Record<string, unknown>)) {
    const subPath = prefix ? `${prefix}.${key}` : key;
    walkForPaths((value as Record<string, unknown>)[key], subPath, paths);
  }
}

interface CitationBearing {
  phase1Fields?: string[];
}

interface CitationBucket {
  pathPrefix: string;
  recs: CitationBearing[];
}

/**
 * Citation contract validation. Each recommendation must:
 *   1. expose a phase1Fields array,
 *   2. include at least one entry,
 *   3. only reference paths that exist in the Phase 1 payload.
 *
 * Caller gates this via isNewShapePhase2() so legacy stored runs do not
 * generate spurious MISSING_CITATION errors.
 */
function validatePhase1FieldCitations(
  phase1: Phase1Result,
  phase2: Phase2Result,
): ValidationViolation[] {
  const violations: ValidationViolation[] = [];
  const allowed = collectPhase1FieldPaths(phase1);

  const buckets: CitationBucket[] = [
    { pathPrefix: 'mixAndMasterChain', recs: phase2.mixAndMasterChain ?? [] },
    { pathPrefix: 'abletonRecommendations', recs: phase2.abletonRecommendations ?? [] },
    {
      pathPrefix: 'secretSauce.workflowSteps',
      recs: phase2.secretSauce?.workflowSteps ?? [],
    },
  ];

  for (const bucket of buckets) {
    bucket.recs.forEach((rec, index) => {
      const fieldPath = `${bucket.pathPrefix}[${index}].phase1Fields`;
      const phase1Fields = rec.phase1Fields;

      if (!Array.isArray(phase1Fields)) {
        violations.push({
          type: 'MISSING_CITATION',
          field: fieldPath,
          severity: 'ERROR',
          message:
            `Recommendation at ${bucket.pathPrefix}[${index}] is missing the required ` +
            'phase1Fields citation array. Per the Citation Contract every recommendation ' +
            'must list the Phase 1 measurement paths that justify it.',
        });
        return;
      }

      if (phase1Fields.length === 0) {
        violations.push({
          type: 'MISSING_CITATION',
          field: fieldPath,
          severity: 'ERROR',
          message:
            `Recommendation at ${bucket.pathPrefix}[${index}] has an empty phase1Fields array. ` +
            'At least one Phase 1 measurement path must be cited.',
        });
        return;
      }

      phase1Fields.forEach((cited, entryIndex) => {
        if (typeof cited !== 'string' || cited.trim().length === 0) {
          violations.push({
            type: 'MISSING_CITATION',
            field: `${fieldPath}[${entryIndex}]`,
            severity: 'ERROR',
            message:
              `phase1Fields entry ${entryIndex} on ${bucket.pathPrefix}[${index}] is not a ` +
              'non-empty string. Each citation must be a dotted measurement path.',
            phase2Value: cited,
          });
          return;
        }
        const normalized = cited.trim();
        if (!allowed.has(normalized)) {
          violations.push({
            type: 'MISSING_CITATION',
            field: `${fieldPath}[${entryIndex}]`,
            severity: 'ERROR',
            message:
              `phase1Fields entry "${normalized}" on ${bucket.pathPrefix}[${index}] does not ` +
              'match any path present in the Phase 1 payload. Do not invent field paths; ' +
              'only cite measurements that exist in AUTHORITATIVE_MEASUREMENT_RESULT_JSON.',
            phase2Value: normalized,
          });
        }
      });
    });
  }

  return violations;
}

/**
 * Validates BPM consistency between Phase 1 and Phase 2.
 * Phase 2 should not contradict Phase 1 BPM by more than 2.0 BPM.
 */
function validateBPMConsistency(phase1: Phase1Result, phase2: Phase2Result): ValidationViolation[] {
  const violations: ValidationViolation[] = [];
  const phase1BPM = phase1.bpm;

  // Extract BPM mentions from Phase 2 text fields
  const bpmMentions = extractBPMFromPhase2(phase2);

  for (const mention of bpmMentions) {
    const diff = Math.abs(mention.value - phase1BPM);
    if (diff > BPM_TOLERANCE) {
      violations.push({
        type: 'NUMERIC_OVERRIDE',
        field: 'bpm',
        phase1Value: phase1BPM,
        phase2Value: mention.value,
        severity: 'ERROR',
        message: `Phase 2 ${mention.location} mentions BPM ${mention.value}, which differs from Phase 1 BPM ${phase1BPM} by ${diff.toFixed(1)} (tolerance: ${BPM_TOLERANCE})`,
      });
    }
  }

  return violations;
}

/**
 * Extracts BPM values mentioned in Phase 2 text fields.
 */
function extractBPMFromPhase2(phase2: Phase2Result): Array<{ value: number; location: string }> {
  const mentions: Array<{ value: number; location: string }> = [];

  // Check trackCharacter
  if (phase2.trackCharacter) {
    const bpm = extractBPMFromText(phase2.trackCharacter);
    if (bpm !== null) {
      mentions.push({ value: bpm, location: 'trackCharacter' });
    }
  }

  // Check sonicElements - they are strings
  if (phase2.sonicElements) {
    const kickDesc = phase2.sonicElements.kick;
    if (kickDesc) {
      const bpm = extractBPMFromText(kickDesc);
      if (bpm !== null) {
        mentions.push({ value: bpm, location: 'sonicElements.kick' });
      }
    }
    const grooveDesc = phase2.sonicElements.grooveAndTiming;
    if (grooveDesc) {
      const bpm = extractBPMFromText(grooveDesc);
      if (bpm !== null) {
        mentions.push({ value: bpm, location: 'sonicElements.grooveAndTiming' });
      }
    }
  }

  if (phase2.styleProfile) {
    const description = phase2.styleProfile.description;
    if (description) {
      const bpm = extractBPMFromText(description);
      if (bpm !== null) {
        mentions.push({ value: bpm, location: 'styleProfile.description' });
      }
    }
    const generationPrompt = phase2.styleProfile.generationPrompt;
    if (generationPrompt) {
      const bpm = extractBPMFromText(generationPrompt);
      if (bpm !== null) {
        mentions.push({ value: bpm, location: 'styleProfile.generationPrompt' });
      }
    }
  }

  return mentions;
}

/**
 * Extracts a BPM value from text using regex.
 * Matches patterns like "126 BPM", "at 130 bpm", etc.
 */
function extractBPMFromText(text: string): number | null {
  // Match patterns like "126 BPM", "130bpm", "at 128 bpm", etc.
  const bpmRegex = /(\d+(?:\.\d+)?)\s*BPM\b/gi;
  const matches = [...text.matchAll(bpmRegex)];

  if (matches.length > 0) {
    // Return the first BPM found
    return parseFloat(matches[0][1]);
  }

  return null;
}

/**
 * Validates key consistency between Phase 1 and Phase 2.
 * Phase 2 should not contradict Phase 1 key (exact match required when Phase 1 key is present).
 */
function validateKeyConsistency(phase1: Phase1Result, phase2: Phase2Result): ValidationViolation[] {
  const violations: ValidationViolation[] = [];

  // If Phase 1 has no key, skip validation (Phase 2 can infer)
  if (phase1.key === null || phase1.key === undefined) {
    return violations;
  }

  // Extract key mentions from Phase 2
  const keyMentions = extractKeyFromPhase2(phase2);

  for (const mention of keyMentions) {
    // Normalize keys for comparison
    const normalizedPhase1Key = normalizeKey(phase1.key!);
    const normalizedMentionKey = normalizeKey(mention.value);

    // Check for contradiction (not exact match and not relative major/minor)
    if (normalizedMentionKey !== normalizedPhase1Key) {
      // Check if it's a relative major/minor (which is still a contradiction per rules)
      violations.push({
        type: 'NUMERIC_OVERRIDE',
        field: 'key',
        phase1Value: phase1.key,
        phase2Value: mention.value,
        severity: 'ERROR',
        message: `Phase 2 ${mention.location} mentions key "${mention.value}", which contradicts Phase 1 key "${phase1.key}". Do not reinterpret as relative major/minor.`,
      });
    }
  }

  return violations;
}

/**
 * Extracts key mentions from Phase 2 text fields.
 */
function extractKeyFromPhase2(phase2: Phase2Result): Array<{ value: string; location: string }> {
  const mentions: Array<{ value: string; location: string }> = [];

  // Common key patterns
  const keyPattern = /\b([A-G][#b]?\s*(?:major|minor|maj|min| Major| Minor|Maj|Min))\b/gi;

  // Check trackCharacter
  if (phase2.trackCharacter) {
    const matches = [...phase2.trackCharacter.matchAll(keyPattern)];
    for (const match of matches) {
      mentions.push({ value: match[1].trim(), location: 'trackCharacter' });
    }
  }

  // Check sonicElements.harmonicContent (string)
  const harmonicDesc = phase2.sonicElements?.harmonicContent;
  if (harmonicDesc) {
    const matches = [...harmonicDesc.matchAll(keyPattern)];
    for (const match of matches) {
      mentions.push({ value: match[1].trim(), location: 'sonicElements.harmonicContent' });
    }
  }

  if (phase2.styleProfile) {
    const description = phase2.styleProfile.description;
    if (description) {
      const matches = [...description.matchAll(keyPattern)];
      for (const match of matches) {
        mentions.push({ value: match[1].trim(), location: 'styleProfile.description' });
      }
    }
    const generationPrompt = phase2.styleProfile.generationPrompt;
    if (generationPrompt) {
      const matches = [...generationPrompt.matchAll(keyPattern)];
      for (const match of matches) {
        mentions.push({ value: match[1].trim(), location: 'styleProfile.generationPrompt' });
      }
    }
  }

  return mentions;
}

/**
 * Normalizes a key string for comparison.
 */
function normalizeKey(key: string): string {
  return key
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .replace(/major/g, 'major')
    .replace(/minor/g, 'minor')
    .replace(/maj/g, 'major')
    .replace(/min(?!or)/g, 'minor')
    .trim();
}

/**
 * Validates LUFS consistency between Phase 1 and Phase 2.
 */
function validateLUFSConsistency(phase1: Phase1Result, phase2: Phase2Result): ValidationViolation[] {
  const violations: ValidationViolation[] = [];

  // Check segment LUFS values against integrated LUFS
  if (phase2.arrangementOverview?.segments && phase1.lufsIntegrated !== undefined) {
    for (const segment of phase2.arrangementOverview.segments) {
      if (segment.lufs !== undefined) {
        const diff = Math.abs(segment.lufs - phase1.lufsIntegrated);
        if (diff > LUFS_TOLERANCE) {
          violations.push({
            type: 'BOUNDS_VIOLATION',
            field: 'segmentLufs',
            phase1Value: phase1.lufsIntegrated,
            phase2Value: segment.lufs,
            severity: 'WARNING',
            message: `Segment ${segment.index} LUFS (${segment.lufs}) differs significantly from integrated LUFS (${phase1.lufsIntegrated}) by ${diff.toFixed(1)} dB`,
          });
        }
      }
    }
  }

  return violations;
}

/**
 * Validates that Phase 2 genre analysis acknowledges Phase 1 DSP context.
 * Checks that confidenceNotes reference rhythm cluster and synthesis tier.
 */
function validateGenreDSPConsistency(phase1: Phase1Result, phase2: Phase2Result): ValidationViolation[] {
  const violations: ValidationViolation[] = [];

  // Check if we have DSP data to validate against
  const hasRhythmData = phase1.grooveDetail && (
    phase1.grooveDetail.kickSwing !== undefined ||
    phase1.grooveDetail.kickAccent !== undefined
  );
  const hasSynthesisData = phase1.synthesisCharacter && (
    phase1.synthesisCharacter.inharmonicity !== undefined ||
    phase1.synthesisCharacter.oddToEvenRatio !== undefined
  );

  if (!hasRhythmData && !hasSynthesisData) {
    return violations;
  }

  // Check confidenceNotes for DSP context references
  const confidenceNotes = phase2.confidenceNotes || [];
  const hasRhythmReference = confidenceNotes.some(note =>
    note.field.toLowerCase().includes('rhythm') ||
    note.field.toLowerCase().includes('kick') ||
    note.field.toLowerCase().includes('swing'),
  );
  const hasSynthesisReference = confidenceNotes.some(note =>
    note.field.toLowerCase().includes('synthesis') ||
    note.field.toLowerCase().includes('inharmonicity') ||
    note.field.toLowerCase().includes('timbre'),
  );

  // Warn if DSP context is completely ignored
  if (hasRhythmData && !hasRhythmReference) {
    violations.push({
      type: 'GENRE_IGNORES_DSP',
      field: 'rhythmCluster',
      severity: 'WARNING',
      message: 'Phase 2 confidenceNotes do not reference rhythm cluster analysis from Phase 1 DSP measurements (kickSwing, kickAccent). Genre inference should acknowledge rhythm context.',
    });
  }

  if (hasSynthesisData && !hasSynthesisReference) {
    violations.push({
      type: 'GENRE_IGNORES_DSP',
      field: 'synthesisTier',
      severity: 'WARNING',
      message: 'Phase 2 confidenceNotes do not reference synthesis tier analysis from Phase 1 DSP measurements (inharmonicity, oddToEvenRatio). Genre inference should acknowledge synthesis context.',
    });
  }

  return violations;
}

/**
 * Validates numeric bounds - recommendations should be physically possible.
 */
function validateNumericBounds(phase1: Phase1Result, phase2: Phase2Result): ValidationViolation[] {
  const violations: ValidationViolation[] = [];

  const spectralCentroid = phase1.spectralDetail?.spectralCentroidMean as number | undefined;

  if (!spectralCentroid) {
    return violations;
  }

  // Check EQ recommendations
  const recommendations = phase2.abletonRecommendations || [];
  for (const rec of recommendations) {
    violations.push(...validateRecommendationBounds(rec, spectralCentroid));
  }

  // Check mix chain recommendations
  const mixChain = phase2.mixAndMasterChain || [];
  for (const rec of mixChain) {
    // Convert to AbletonRecommendation format
    const convertedRec: AbletonRecommendation = {
      device: rec.device,
      category: 'EQ', // Default category for mix chain
      parameter: rec.parameter,
      value: rec.value,
      reason: rec.reason,
    };
    violations.push(...validateRecommendationBounds(convertedRec, spectralCentroid));
  }

  return violations;
}

/**
 * Validates a single recommendation against spectral bounds.
 */
function validateRecommendationBounds(
  rec: AbletonRecommendation,
  spectralCentroid: number,
): ValidationViolation[] {
  const violations: ValidationViolation[] = [];

  // Check EQ cutoffs
  if (rec.category === 'EQ' && rec.device.includes('EQ')) {
    // Extract frequency values from parameters
    const freqValue = extractFrequencyValue(rec.value);

    if (freqValue !== null) {
      // High cut above spectral centroid is suspicious
      if (rec.parameter.toLowerCase().includes('high') ||
          rec.parameter.toLowerCase().includes('cutoff') ||
          rec.parameter.toLowerCase().includes('frequency')) {
        if (freqValue > spectralCentroid * 2) {
          violations.push({
            type: 'BOUNDS_VIOLATION',
            field: 'eqHighCut',
            phase1Value: spectralCentroid,
            phase2Value: freqValue,
            severity: 'WARNING',
            message: `EQ ${rec.parameter} at ${freqValue} Hz exceeds measured spectral centroid (${spectralCentroid} Hz). Filter cutoff may be inaudible or ineffective.`,
          });
        }
      }
    }
  }

  return violations;
}

/**
 * Extracts a frequency value in Hz from a string.
 * Handles formats like "8000 Hz", "8kHz", "8000", etc.
 */
function extractFrequencyValue(value: string): number | null {
  // Match patterns like "8000 Hz", "8 kHz", "8000"
  const match = value.match(/(\d+(?:\.\d+)?)\s*(k?)Hz?/i);
  if (match) {
    const num = parseFloat(match[1]);
    const multiplier = match[2].toLowerCase() === 'k' ? 1000 : 1;
    return num * multiplier;
  }
  return null;
}

// ───────────────────────────────────────────────────────────────────────────
// Contract Slice step 9 extensions — added after the first live Gemini run
// surfaced over-confident text, single-anchor citation patterns, and
// salvaged-but-not-surfaced recommendation drops.
// ───────────────────────────────────────────────────────────────────────────

interface CitationRec {
  bucket: string;
  index: number;
  phase1Fields: string[];
  reasonText: string;
}

function collectCitationRecs(phase2: Phase2Result): CitationRec[] {
  const recs: CitationRec[] = [];
  const buckets: Array<{ name: string; items: any[] }> = [
    { name: 'mixAndMasterChain', items: phase2.mixAndMasterChain ?? [] },
    { name: 'abletonRecommendations', items: phase2.abletonRecommendations ?? [] },
    { name: 'secretSauce.workflowSteps', items: phase2.secretSauce?.workflowSteps ?? [] },
  ];
  for (const bucket of buckets) {
    bucket.items.forEach((rec: any, index) => {
      const fields = Array.isArray(rec?.phase1Fields)
        ? rec.phase1Fields.map((s: unknown) => (typeof s === 'string' ? s.trim() : '')).filter(Boolean)
        : [];
      const reasonText = [rec?.reason, rec?.advancedTip, rec?.measurementJustification, rec?.instruction]
        .filter((s: unknown): s is string => typeof s === 'string' && s.length > 0)
        .join(' \n ');
      recs.push({ bucket: bucket.name, index, phase1Fields: fields, reasonText });
    });
  }
  return recs;
}

/**
 * Returns a normalized key for a phase1Fields array — sorted, lowercased,
 * joined. Two recs with the same anchors in different orders collapse to the
 * same key so the dominance heuristic catches "always cite bpm + key" gaming.
 */
function citationKey(phase1Fields: string[]): string {
  return phase1Fields.map((s) => s.toLowerCase().trim()).filter(Boolean).sort().join('|');
}

function validateCitationDiversity(phase2: Phase2Result): ValidationViolation[] {
  const recs = collectCitationRecs(phase2);
  // Only consider recs that actually have citations — recs missing phase1Fields
  // are already surfaced by MISSING_CITATION. Counting them here would
  // double-penalize and could mask real dominance among the citing recs.
  const cited = recs.filter((r) => r.phase1Fields.length > 0);
  if (cited.length < 4) {
    return []; // Not enough recs to meaningfully measure dominance.
  }

  const keyCounts = new Map<string, number>();
  for (const rec of cited) {
    const key = citationKey(rec.phase1Fields);
    keyCounts.set(key, (keyCounts.get(key) ?? 0) + 1);
  }

  let dominantKey = '';
  let dominantCount = 0;
  for (const [key, count] of keyCounts.entries()) {
    if (count > dominantCount) {
      dominantKey = key;
      dominantCount = count;
    }
  }
  const dominance = dominantCount / cited.length;
  if (dominance < TRIVIAL_CITATION_DOMINANCE_THRESHOLD) {
    return [];
  }

  return [
    {
      type: 'TRIVIAL_CITATIONS',
      field: 'phase1Fields.dominantPattern',
      phase2Value: dominantKey || '(empty)',
      severity: 'WARNING',
      message:
        `${Math.round(dominance * 100)}% of cited recommendations share the same ` +
        `phase1Fields anchor (${dominantKey || '(empty)'}). Citations should be diverse — different ` +
        `cards should cite different measurements unless they genuinely depend on the same anchor.`,
    },
  ];
}

/**
 * Bidirectional + wildcard match between a citation path and a tracked path.
 * Accepts:
 *   1. exact string equality
 *   2. citation is a path-prefix of tracked  (parent-citation covers child-tracked)
 *   3. tracked is a path-prefix of citation  (child-citation satisfies parent-tracked)
 *   4. segment-wise equality with `*` wildcard token matching any single segment
 *      on either side (used for stem-scoped paths like
 *      `stemAnalysis.*.reverbDetail`)
 *
 * Wildcards only match a single segment — `stemAnalysis.*` won't match
 * `stemAnalysis.drums.spectralBalance`. To cover nested paths under a
 * wildcard, combine with the prefix rules: tracked `stemAnalysis.*.reverbDetail`
 * matches citation `stemAnalysis.bass.reverbDetail.preDelayMs` because the
 * tracked path is a wildcard-prefix of the citation.
 */
export function pathCoversTracked(citation: string, tracked: string): boolean {
  if (citation === tracked) return true;
  if (citation.startsWith(`${tracked}.`)) return true; // child citation satisfies parent tracked
  if (tracked.startsWith(`${citation}.`)) return true; // parent citation covers child tracked
  if (!citation.includes('*') && !tracked.includes('*')) return false;

  const cs = citation.split('.');
  const ts = tracked.split('.');
  // Wildcard prefix: tracked has fewer or equal segments and each tracked
  // segment matches the corresponding citation segment (with `*` wild).
  if (ts.length <= cs.length) {
    let ok = true;
    for (let i = 0; i < ts.length; i++) {
      if (ts[i] !== cs[i] && ts[i] !== '*' && cs[i] !== '*') {
        ok = false;
        break;
      }
    }
    if (ok) return true;
  }
  // Symmetric: citation prefix matches a leaf-extended tracked path. Rare but
  // keeps the function symmetric across direction so callers can pass either
  // argument as the "more specific" path.
  if (cs.length <= ts.length) {
    let ok = true;
    for (let i = 0; i < cs.length; i++) {
      if (cs[i] !== ts[i] && cs[i] !== '*' && ts[i] !== '*') {
        ok = false;
        break;
      }
    }
    if (ok) return true;
  }
  return false;
}

function validateNewFieldCoverage(
  phase1: Phase1Result,
  phase2: Phase2Result,
): ValidationViolation[] {
  const recs = collectCitationRecs(phase2);
  const citedPaths = new Set<string>();
  for (const rec of recs) {
    for (const f of rec.phase1Fields) citedPaths.add(f);
  }
  const citedList = Array.from(citedPaths);

  const violations: ValidationViolation[] = [];
  for (const path of PHASE1A_NEW_FIELD_PATHS) {
    if (!isPathPresentAndUseful(phase1, path)) continue;
    // A tracked path is "covered" iff some citation matches under the
    // bidirectional + wildcard rules. This lets either a parent or a more
    // specific child satisfy a tracked anchor — important because Gemini
    // tends to cite leaves (e.g. `grooveDetail.perDrumSwing.snare`) where
    // the tracked path is the parent (`grooveDetail.perDrumSwing`).
    if (citedList.some((c) => pathCoversTracked(c, path))) continue;
    violations.push({
      type: 'NEW_FIELD_UNCITED',
      field: path,
      severity: 'WARNING',
      message:
        `Phase 1 field "${path}" is present in the measurement payload but no Phase 2 ` +
        `recommendation cites it. If the field is relevant to this track, Gemini should ` +
        `use it as a citation anchor; if it is not relevant, this warning is benign.`,
    });
  }
  return violations;
}

/**
 * Minimum useful density for a curve/array to be worth citing. Curves with
 * fewer points carry no narrative — e.g. a 1-point tempoCurve has no "drift"
 * to describe, a 1-point lufsCurve has no envelope. We treat shorter than
 * this as "field present but not yet meaningful for this track" and skip
 * the NEW_FIELD_UNCITED warning rather than fault Gemini for not citing it.
 */
const MIN_USEFUL_CURVE_POINTS = 5;

function isPathPresentAndUseful(phase1: Phase1Result, path: string): boolean {
  // Wildcard support: a tracked path like `stemAnalysis.*.reverbDetail` is
  // present when ANY key at the `*` position has the remaining sub-path
  // populated. We recurse on each candidate and short-circuit on the first
  // useful match. This keeps the gate from warning about per-stem paths when
  // at least one stem actually carries the field.
  if (path.includes('*')) {
    const parts = path.split('.');
    const starIndex = parts.indexOf('*');
    // Resolve the prefix up to the first wildcard segment.
    let cursor: any = phase1;
    for (let i = 0; i < starIndex; i++) {
      if (cursor === null || cursor === undefined) return false;
      if (typeof cursor !== 'object') return false;
      const part = parts[i];
      if (!(part in cursor)) return false;
      cursor = cursor[part];
    }
    if (cursor === null || cursor === undefined || typeof cursor !== 'object') return false;
    const remainder = parts.slice(starIndex + 1).join('.');
    if (remainder.length === 0) {
      // `foo.*` is "present" if foo has any non-empty child.
      return Object.values(cursor).some(
        (v) => v !== null && v !== undefined && (typeof v !== 'object' || Object.keys(v as object).length > 0),
      );
    }
    return Object.values(cursor).some((child) =>
      child && typeof child === 'object'
        ? isPathPresentAndUseful(child as Phase1Result, remainder)
        : false,
    );
  }

  let cursor: any = phase1;
  for (const part of path.split('.')) {
    if (cursor === null || cursor === undefined) return false;
    if (typeof cursor !== 'object') return false;
    if (!(part in cursor)) return false;
    cursor = cursor[part];
  }
  if (cursor === null || cursor === undefined) return false;
  if (Array.isArray(cursor)) {
    if (cursor.length < MIN_USEFUL_CURVE_POINTS) return false;
    // Reject curves where every cell is null (e.g. correlationCurve on silence).
    const hasAnyFinite = cursor.some((row: any) => {
      if (row === null || row === undefined) return false;
      if (typeof row === 'number') return Number.isFinite(row);
      if (typeof row === 'object') {
        for (const v of Object.values(row)) {
          if (typeof v === 'number' && Number.isFinite(v)) return true;
        }
        return false;
      }
      return false;
    });
    return hasAnyFinite;
  }
  if (typeof cursor === 'object') {
    if (Object.keys(cursor).length === 0) return false;
    // Container objects like lufsCurve = {shortTerm, momentary} count as
    // useful when at least one child curve passes the threshold.
    for (const value of Object.values(cursor)) {
      if (Array.isArray(value) && value.length >= MIN_USEFUL_CURVE_POINTS) return true;
      if (value !== null && value !== undefined && typeof value !== 'object') return true;
    }
    return false;
  }
  return true;
}

const WORD_BOUNDARY_REGEX_CACHE = new Map<string, RegExp>();

function wordBoundaryRegex(phrase: string): RegExp {
  let cached = WORD_BOUNDARY_REGEX_CACHE.get(phrase);
  if (cached) return cached;
  // Allow multi-word phrases (e.g. "low confidence") but anchor each side to a
  // word boundary or whitespace boundary. Escape regex specials defensively.
  const escaped = phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  cached = new RegExp(`(?:^|\\b|\\s)${escaped}(?=\\b|\\s|$|[\\.,;:!?])`, 'i');
  WORD_BOUNDARY_REGEX_CACHE.set(phrase, cached);
  return cached;
}

function containsAny(text: string, words: string[]): { matched: string | null } {
  for (const w of words) {
    if (wordBoundaryRegex(w).test(text)) return { matched: w };
  }
  return { matched: null };
}

function validateLowConfidenceHedging(
  phase1: Phase1Result,
  phase2: Phase2Result,
): ValidationViolation[] {
  const recs = collectCitationRecs(phase2);
  const violations: ValidationViolation[] = [];

  for (const rec of recs) {
    if (rec.phase1Fields.length === 0) continue;
    if (rec.reasonText.length === 0) continue;

    // Find the most-cited field that has a paired confidence; use the lowest
    // confidence value among the rec's cited fields as the gate. (If the rec
    // cites multiple fields and any one has low confidence, the text needs
    // hedging.)
    let lowestConfidence: number | null = null;
    let triggeringField: string | null = null;
    let triggeringConfidenceField: string | null = null;
    for (const cited of rec.phase1Fields) {
      const confidencePath =
        CONFIDENCE_PAIRS[cited] ?? CONFIDENCE_PAIRS[cited.split('.')[0]];
      if (!confidencePath) continue;
      const value = readNumberAtPath(phase1, confidencePath);
      if (value === null) continue;
      if (value >= LOW_CONFIDENCE_THRESHOLD) continue;
      if (lowestConfidence === null || value < lowestConfidence) {
        lowestConfidence = value;
        triggeringField = cited;
        triggeringConfidenceField = confidencePath;
      }
    }
    if (lowestConfidence === null) continue;

    const imperative = containsAny(rec.reasonText, IMPERATIVE_WORDS);
    const hedge = containsAny(rec.reasonText, HEDGE_WORDS);
    if (imperative.matched && !hedge.matched) {
      violations.push({
        type: 'LOW_CONFIDENCE_NOT_HEDGED',
        field: `${rec.bucket}[${rec.index}]`,
        phase1Value: { confidenceField: triggeringConfidenceField, value: lowestConfidence },
        phase2Value: imperative.matched,
        severity: 'ERROR',
        message:
          `Recommendation at ${rec.bucket}[${rec.index}] cites "${triggeringField}" whose paired ` +
          `confidence ${triggeringConfidenceField}=${lowestConfidence} is below the ` +
          `${LOW_CONFIDENCE_THRESHOLD} threshold, but the text uses the imperative word ` +
          `"${imperative.matched}" without any hedging language. Low-confidence ` +
          `measurements must propagate to hedged recommendations (PURPOSE.md invariant #4).`,
      });
    }
  }
  return violations;
}

function readNumberAtPath(payload: unknown, path: string): number | null {
  let cursor: any = payload;
  for (const part of path.split('.')) {
    if (cursor === null || cursor === undefined) return null;
    if (typeof cursor !== 'object') return null;
    cursor = (cursor as Record<string, unknown>)[part];
  }
  if (typeof cursor === 'number' && Number.isFinite(cursor)) return cursor;
  return null;
}

function validateSalvagedRecommendations(
  diagnostics: ValidationDiagnostics,
): ValidationViolation[] {
  const warnings = Array.isArray(diagnostics.warnings) ? diagnostics.warnings : [];
  const violations: ValidationViolation[] = [];
  for (const warning of warnings) {
    const code = typeof warning?.code === 'string' ? warning.code : '';
    if (!SALVAGE_WARNING_CODES.has(code)) continue;
    const path = typeof warning?.path === 'string' ? warning.path : '(unknown path)';
    const message = typeof warning?.message === 'string' ? warning.message : '';
    violations.push({
      type: 'RECOMMENDATION_SALVAGED',
      field: path,
      phase2Value: code,
      severity: 'ERROR',
      message:
        `Backend salvage code ${code} at ${path}: the Phase 2 response had to be repaired ` +
        `or had an item dropped before reaching the user (${message || 'no detail provided'}). ` +
        `Silent loss of recommendations means the prompt or schema is letting Gemini produce ` +
        `invalid items.`,
    });
  }
  return violations;
}

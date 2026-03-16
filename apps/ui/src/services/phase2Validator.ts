import { Phase1Result, Phase2Result, AbletonRecommendation } from '../types';

export interface ValidationViolation {
  type: 'NUMERIC_OVERRIDE' | 'GENRE_IGNORES_DSP' | 'BOUNDS_VIOLATION' | 'MISSING_CITATION';
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
 * Validates that Phase 2 output is consistent with Phase 1 measurements.
 * Checks for numeric overrides, genre/DSP consistency, and physical bounds.
 */
export function validatePhase2Consistency(
  phase1: Phase1Result,
  phase2: Phase2Result,
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
  const hasRhythmData = phase1.rhythmDetail && (
    phase1.rhythmDetail.kickSwing !== undefined ||
    phase1.rhythmDetail.kickAccent !== undefined
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

  const spectralCentroid = phase1.spectralDetail?.spectralCentroid as number | undefined;

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

/**
 * Field Utilization Analytics Service
 *
 * Tracks which Phase 1 fields drive Phase 2 recommendations.
 * Analyzes citation patterns to identify:
 * - Most used fields (top 10)
 * - Unused fields (candidates for removal or better prompting)
 * - Field usage by recommendation category
 */

import { Phase2Result, AbletonRecommendation } from '../types';

/**
 * Extended recommendation type that includes sources field
 * (for forward compatibility with future Phase 2 results)
 */
interface RecommendationWithSources extends AbletonRecommendation {
  sources?: string[];
}

/**
 * Extended Phase2Result with sourced recommendations
 */
interface Phase2ResultWithSources extends Omit<Phase2Result, 'abletonRecommendations'> {
  abletonRecommendations: RecommendationWithSources[];
}

/**
 * Represents utilization data for a single Phase 1 field
 */
export interface FieldUtilization {
  /** Dot-notation path like "grooveDetail.kickAccent" */
  field: string;
  /** Number of times this field was cited across all recommendations */
  citationCount: number;
  /** Which recommendation categories use this field */
  categories: string[];
}

/**
 * Complete utilization report for a Phase 2 analysis
 */
export interface UtilizationReport {
  /** Top 10 most cited fields */
  mostUsedFields: FieldUtilization[];
  /** Phase 1 fields that were never cited */
  unusedFields: string[];
  /** Total number of recommendations analyzed */
  totalRecommendations: number;
  /** Average number of source citations per recommendation */
  avgSourcesPerRecommendation: number;
  /** Breakdown of field usage by recommendation category */
  categoryBreakdown: Record<
    string,
    {
      recommendationCount: number;
      avgSources: number;
      topFields: string[];
    }
  >;
}

/**
 * Complete list of all Phase 1 fields that can be cited.
 * Used to identify unused fields.
 */
const ALL_PHASE1_FIELDS: string[] = [
  // Basic metadata
  'bpm',
  'bpmConfidence',
  'key',
  'keyConfidence',
  'timeSignature',
  'durationSeconds',
  // Loudness
  'lufsIntegrated',
  'lufsRange',
  'truePeak',
  'crestFactor',
  // Stereo
  'stereoWidth',
  'stereoCorrelation',
  'stereoDetail.stereoWidth',
  'stereoDetail.stereoCorrelation',
  'stereoDetail.subBassMono',
  // Spectral
  'spectralBalance.subBass',
  'spectralBalance.lowBass',
  'spectralBalance.mids',
  'spectralBalance.upperMids',
  'spectralBalance.highs',
  'spectralBalance.brilliance',
  'spectralDetail.centroid',
  'spectralDetail.flatness',
  'spectralDetail.rolloff',
  'spectralDetail.flux',
  'spectralDetail.complexity',
  // Rhythm
  'rhythmDetail.beatInterval',
  'rhythmDetail.beatPositions',
  // Groove
  'grooveDetail.kickSwing',
  'grooveDetail.hihatSwing',
  'grooveDetail.kickAccent',
  // Melody
  'melodyDetail.noteCount',
  'melodyDetail.dominantNotes',
  'melodyDetail.pitchConfidence',
  'melodyDetail.pitchRange',
  // Transcription
  'transcriptionDetail.noteCount',
  'transcriptionDetail.dominantPitches',
  'transcriptionDetail.averageConfidence',
  'transcriptionDetail.pitchRange',
  // Sidechain
  'sidechainDetail.pumpingStrength',
  'sidechainDetail.pumpingConfidence',
  // Synthesis
  'synthesisCharacter.inharmonicity',
  'synthesisCharacter.oddToEvenRatio',
  'synthesisCharacter.timbreBrightness',
  // Structure
  'structure.segments',
  'segmentLoudness',
  'segmentSpectral',
  'segmentKey',
  // Chords
  'chordDetail.dominantChords',
  'chordDetail.chordStrength',
  'chordDetail.chordProgression',
  // Danceability
  'danceability.danceability',
  'danceability.dfa',
  // Perceptual
  'perceptual.perceivedLoudness',
  'perceptual.spectralBrightness',
];

/**
 * Extracts all path levels from a dot-notation field path.
 * For example, "grooveDetail.kickAccent" returns:
 * ["grooveDetail", "grooveDetail.kickAccent"]
 *
 * This allows counting citations for both parent objects and specific fields.
 */
function extractPathLevels(fieldPath: string): string[] {
  const parts = fieldPath.split('.');
  const levels: string[] = [];

  for (let i = 1; i <= parts.length; i++) {
    levels.push(parts.slice(0, i).join('.'));
  }

  return levels;
}

/**
 * Analyzes Phase 2 result citations and produces utilization statistics.
 *
 * @param phase2Result - The Phase 2 analysis result containing recommendations with sources
 * @returns Complete utilization report
 */
export function analyzeFieldUtilization(
  phase2Result: Phase2Result | Phase2ResultWithSources
): UtilizationReport {
  const result = phase2Result as Phase2ResultWithSources;
  const recommendations = result.abletonRecommendations || [];

  // Track field usage statistics
  const fieldStats = new Map<
    string,
    {
      citationCount: number;
      categories: Set<string>;
    }
  >();

  // Track category-level statistics
  const categoryStats = new Map<
    string,
    {
      recommendationCount: number;
      totalSources: number;
      fieldCounts: Map<string, number>;
    }
  >();

  let totalSources = 0;

  // Process each recommendation
  for (const rec of recommendations) {
    const category = rec.category || 'UNKNOWN';

    // Initialize category stats if needed
    if (!categoryStats.has(category)) {
      categoryStats.set(category, {
        recommendationCount: 0,
        totalSources: 0,
        fieldCounts: new Map(),
      });
    }

    const catStats = categoryStats.get(category)!;
    catStats.recommendationCount++;

    // Process sources if they exist
    const sources = rec.sources || [];
    totalSources += sources.length;
    catStats.totalSources += sources.length;

    for (const source of sources) {
      // Extract all path levels for this citation
      const pathLevels = extractPathLevels(source);

      for (const field of pathLevels) {
        // Update global field stats
        if (!fieldStats.has(field)) {
          fieldStats.set(field, {
            citationCount: 0,
            categories: new Set(),
          });
        }

        const stats = fieldStats.get(field)!;
        stats.citationCount++;
        stats.categories.add(category);

        // Update category-specific field stats
        catStats.fieldCounts.set(field, (catStats.fieldCounts.get(field) || 0) + 1);
      }
    }
  }

  // Build most used fields list (top 10)
  const sortedFields = Array.from(fieldStats.entries())
    .sort((a, b) => b[1].citationCount - a[1].citationCount)
    .slice(0, 10)
    .map(
      ([field, stats]): FieldUtilization => ({
        field,
        citationCount: stats.citationCount,
        categories: Array.from(stats.categories),
      })
    );

  // Identify unused fields
  const usedFields = new Set(fieldStats.keys());
  const unusedFields = ALL_PHASE1_FIELDS.filter((field) => !usedFields.has(field));

  // Build category breakdown
  const categoryBreakdown: UtilizationReport['categoryBreakdown'] = {};

  for (const [category, stats] of categoryStats.entries()) {
    // Get top 5 fields for this category
    const topFields = Array.from(stats.fieldCounts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([field]) => field);

    categoryBreakdown[category] = {
      recommendationCount: stats.recommendationCount,
      avgSources:
        stats.recommendationCount > 0
          ? stats.totalSources / stats.recommendationCount
          : 0,
      topFields,
    };
  }

  return {
    mostUsedFields: sortedFields,
    unusedFields,
    totalRecommendations: recommendations.length,
    avgSourcesPerRecommendation:
      recommendations.length > 0 ? totalSources / recommendations.length : 0,
    categoryBreakdown,
  };
}

/**
 * Generates a human-readable markdown report from utilization data.
 *
 * @param report - The utilization report to format
 * @returns Markdown-formatted report string
 */
export function generateUtilizationMarkdown(report: UtilizationReport): string {
  const lines: string[] = [];

  // Header
  lines.push('# Field Utilization Report');
  lines.push('');
  lines.push(
    `Generated: ${new Date().toISOString().replace('T', ' ').slice(0, 19)} UTC`
  );
  lines.push('');

  // Summary section
  lines.push('## Summary');
  lines.push('');
  lines.push(`- Total Recommendations: **${report.totalRecommendations}**`);
  lines.push(
    `- Avg Sources per Recommendation: **${report.avgSourcesPerRecommendation.toFixed(2)}**`
  );
  lines.push(`- Unused Fields: **${report.unusedFields.length}**`);
  lines.push('');

  // Most used fields section
  lines.push('## Most Used Fields (Top 10)');
  lines.push('');
  lines.push('| Field | Citations | Categories |');
  lines.push('|-------|-----------|------------|');

  if (report.mostUsedFields.length === 0) {
    lines.push('| *No citations found* | - | - |');
  } else {
    for (const field of report.mostUsedFields) {
      const categories = field.categories.join(', ') || 'None';
      lines.push(`| \`${field.field}\` | ${field.citationCount} | ${categories} |`);
    }
  }
  lines.push('');

  // Unused fields section
  lines.push('## Unused Fields');
  lines.push('');
  lines.push(
    'The following Phase 1 fields were never cited in recommendations:'
  );
  lines.push('');

  if (report.unusedFields.length === 0) {
    lines.push('*All fields were utilized*');
  } else {
    for (const field of report.unusedFields) {
      lines.push(`- \`${field}\``);
    }
  }
  lines.push('');

  // Category breakdown section
  lines.push('## Category Breakdown');
  lines.push('');

  const sortedCategories = Object.entries(report.categoryBreakdown).sort(
    (a, b) => b[1].recommendationCount - a[1].recommendationCount
  );

  if (sortedCategories.length === 0) {
    lines.push('*No category data available*');
  } else {
    for (const [category, stats] of sortedCategories) {
      lines.push(`### ${category}`);
      lines.push('');
      lines.push(`- Recommendations: **${stats.recommendationCount}**`);
      lines.push(`- Avg Sources: **${stats.avgSources.toFixed(2)}**`);
      lines.push(`- Top Fields: ${stats.topFields.map((f) => `\`${f}\``).join(', ')}`);
      lines.push('');
    }
  }

  // Recommendations section
  lines.push('## Recommendations');
  lines.push('');

  if (report.unusedFields.length > 10) {
    lines.push(
      '> **Note:** Many Phase 1 fields are unused. Consider:'
    );
    lines.push('> - Reviewing prompt engineering to encourage use of these fields');
    lines.push('> - Removing unused fields from Phase 1 to reduce processing time');
    lines.push('> - Adding field descriptions to help the model understand when to use them');
  } else if (report.avgSourcesPerRecommendation < 1) {
    lines.push(
      '> **Note:** Low average sources per recommendation. Consider:'
    );
    lines.push('> - Encouraging the model to cite specific Phase 1 fields');
    lines.push('> - Adding citation requirements to the prompt');
  } else {
    lines.push('> Field utilization looks healthy. Continue monitoring for trends.');
  }
  lines.push('');

  return lines.join('\n');
}

/**
 * Exports the list of all trackable Phase 1 fields.
 * Useful for documentation and validation.
 */
export function getAllPhase1Fields(): readonly string[] {
  return ALL_PHASE1_FIELDS;
}

import { describe, it, expect } from 'vitest';
import {
  analyzeFieldUtilization,
  generateUtilizationMarkdown,
  FieldUtilization,
  UtilizationReport,
} from '../../src/services/fieldAnalytics';
import { Phase2Result, AbletonRecommendation } from '../../src/types';

// Extended recommendation type with sources for testing
interface RecommendationWithSources extends AbletonRecommendation {
  sources?: string[];
}

// Extended Phase2Result with sourced recommendations
interface Phase2ResultWithSources extends Omit<Phase2Result, 'abletonRecommendations'> {
  abletonRecommendations: RecommendationWithSources[];
}

function createMockPhase2Result(
  recommendations: RecommendationWithSources[]
): Phase2ResultWithSources {
  return {
    trackCharacter: 'Test track character',
    detectedCharacteristics: [],
    arrangementOverview: {
      summary: 'Test arrangement',
      segments: [],
    },
    sonicElements: {
      kick: 'Test kick',
      bass: 'Test bass',
      melodicArp: 'Test arp',
      grooveAndTiming: 'Test groove',
      effectsAndTexture: 'Test effects',
    },
    mixAndMasterChain: [],
    secretSauce: {
      title: 'Test secret sauce',
      explanation: 'Test explanation',
      implementationSteps: [],
    },
    confidenceNotes: [],
    abletonRecommendations: recommendations,
  };
}

describe('analyzeFieldUtilization', () => {
  it('returns empty report for empty recommendations', () => {
    const result = createMockPhase2Result([]);
    const report = analyzeFieldUtilization(result as Phase2Result);

    expect(report.totalRecommendations).toBe(0);
    expect(report.avgSourcesPerRecommendation).toBe(0);
    expect(report.mostUsedFields).toEqual([]);
    expect(report.unusedFields.length).toBeGreaterThan(0);
  });

  it('counts single field citations correctly', () => {
    const result = createMockPhase2Result([
      {
        device: 'EQ Eight',
        category: 'EQ',
        parameter: 'Low Cut',
        value: '30 Hz',
        reason: 'Remove rumble',
        sources: ['spectralBalance.subBass'],
      },
      {
        device: 'Compressor',
        category: 'DYNAMICS',
        parameter: 'Threshold',
        value: '-20 dB',
        reason: 'Control dynamics',
        sources: ['lufsIntegrated'],
      },
    ]);

    const report = analyzeFieldUtilization(result as Phase2Result);

    expect(report.totalRecommendations).toBe(2);
    expect(report.avgSourcesPerRecommendation).toBe(1);
    // spectralBalance.subBass creates 2 entries (spectralBalance + spectralBalance.subBass)
    // lufsIntegrated creates 1 entry
    expect(report.mostUsedFields).toHaveLength(3);
    expect(report.mostUsedFields[0].citationCount).toBe(1);
  });

  it('counts multiple citations for same field', () => {
    const result = createMockPhase2Result([
      {
        device: 'EQ Eight',
        category: 'EQ',
        parameter: 'Low Cut',
        value: '30 Hz',
        reason: 'Remove rumble',
        sources: ['bpm'],
      },
      {
        device: 'Compressor',
        category: 'DYNAMICS',
        parameter: 'Threshold',
        value: '-20 dB',
        reason: 'Control dynamics',
        sources: ['bpm'],
      },
      {
        device: 'Delay',
        category: 'EFFECTS',
        parameter: 'Time',
        value: '1/4',
        reason: 'Sync delay',
        sources: ['bpm'],
      },
    ]);

    const report = analyzeFieldUtilization(result as Phase2Result);

    expect(report.mostUsedFields[0].field).toBe('bpm');
    expect(report.mostUsedFields[0].citationCount).toBe(3);
  });

  it('counts nested path citations for both parent and child', () => {
    const result = createMockPhase2Result([
      {
        device: 'EQ Eight',
        category: 'EQ',
        parameter: 'Low Cut',
        value: '30 Hz',
        reason: 'Remove rumble',
        sources: ['grooveDetail.kickAccent'],
      },
    ]);

    const report = analyzeFieldUtilization(result as Phase2Result);

    // Should count both 'grooveDetail' and 'grooveDetail.kickAccent'
    const grooveDetailField = report.mostUsedFields.find(
      (f) => f.field === 'grooveDetail'
    );
    const kickAccentField = report.mostUsedFields.find(
      (f) => f.field === 'grooveDetail.kickAccent'
    );

    expect(grooveDetailField).toBeDefined();
    expect(grooveDetailField?.citationCount).toBe(1);
    expect(kickAccentField).toBeDefined();
    expect(kickAccentField?.citationCount).toBe(1);
  });

  it('tracks categories per field', () => {
    const result = createMockPhase2Result([
      {
        device: 'EQ Eight',
        category: 'EQ',
        parameter: 'Low Cut',
        value: '30 Hz',
        reason: 'Remove rumble',
        sources: ['bpm'],
      },
      {
        device: 'Compressor',
        category: 'DYNAMICS',
        parameter: 'Threshold',
        value: '-20 dB',
        reason: 'Control dynamics',
        sources: ['bpm'],
      },
    ]);

    const report = analyzeFieldUtilization(result as Phase2Result);

    const bpmField = report.mostUsedFields.find((f) => f.field === 'bpm');
    expect(bpmField).toBeDefined();
    expect(bpmField?.categories).toContain('EQ');
    expect(bpmField?.categories).toContain('DYNAMICS');
    expect(bpmField?.categories).toHaveLength(2);
  });

  it('calculates category breakdown correctly', () => {
    const result = createMockPhase2Result([
      {
        device: 'EQ Eight',
        category: 'EQ',
        parameter: 'Low Cut',
        value: '30 Hz',
        reason: 'Remove rumble',
        sources: ['bpm', 'key'],
      },
      {
        device: 'EQ Eight',
        category: 'EQ',
        parameter: 'High Cut',
        value: '20 kHz',
        reason: 'Reduce harshness',
        sources: ['bpm'],
      },
      {
        device: 'Compressor',
        category: 'DYNAMICS',
        parameter: 'Threshold',
        value: '-20 dB',
        reason: 'Control dynamics',
        sources: ['lufsIntegrated'],
      },
    ]);

    const report = analyzeFieldUtilization(result as Phase2Result);

    expect(report.categoryBreakdown['EQ']).toBeDefined();
    expect(report.categoryBreakdown['EQ'].recommendationCount).toBe(2);
    expect(report.categoryBreakdown['EQ'].avgSources).toBe(1.5); // (2 + 1) / 2
    expect(report.categoryBreakdown['EQ'].topFields).toContain('bpm');

    expect(report.categoryBreakdown['DYNAMICS']).toBeDefined();
    expect(report.categoryBreakdown['DYNAMICS'].recommendationCount).toBe(1);
    expect(report.categoryBreakdown['DYNAMICS'].avgSources).toBe(1);
  });

  it('identifies unused Phase 1 fields', () => {
    const result = createMockPhase2Result([
      {
        device: 'EQ Eight',
        category: 'EQ',
        parameter: 'Low Cut',
        value: '30 Hz',
        reason: 'Remove rumble',
        sources: ['bpm'],
      },
    ]);

    const report = analyzeFieldUtilization(result as Phase2Result);

    expect(report.unusedFields).not.toContain('bpm');
    expect(report.unusedFields).toContain('key');
    expect(report.unusedFields).toContain('lufsIntegrated');
  });

  it('handles recommendations without sources gracefully', () => {
    const result = createMockPhase2Result([
      {
        device: 'EQ Eight',
        category: 'EQ',
        parameter: 'Low Cut',
        value: '30 Hz',
        reason: 'Remove rumble',
        // No sources field
      },
      {
        device: 'Compressor',
        category: 'DYNAMICS',
        parameter: 'Threshold',
        value: '-20 dB',
        reason: 'Control dynamics',
        sources: ['bpm'],
      },
    ]);

    const report = analyzeFieldUtilization(result as Phase2Result);

    expect(report.totalRecommendations).toBe(2);
    expect(report.avgSourcesPerRecommendation).toBe(0.5); // 1 source / 2 recommendations
  });

  it('handles deeply nested paths correctly', () => {
    const result = createMockPhase2Result([
      {
        device: 'EQ Eight',
        category: 'EQ',
        parameter: 'Low Cut',
        value: '30 Hz',
        reason: 'Remove rumble',
        sources: ['spectralBalance.subBass.lowEnd'],
      },
    ]);

    const report = analyzeFieldUtilization(result as Phase2Result);

    // Should create entries for each level
    expect(report.mostUsedFields.some((f) => f.field === 'spectralBalance')).toBe(true);
    expect(
      report.mostUsedFields.some((f) => f.field === 'spectralBalance.subBass')
    ).toBe(true);
    expect(
      report.mostUsedFields.some((f) => f.field === 'spectralBalance.subBass.lowEnd')
    ).toBe(true);
  });

  it('limits mostUsedFields to top 10', () => {
    const recommendations: RecommendationWithSources[] = [];

    // Create 15 different fields with different citation counts
    for (let i = 0; i < 15; i++) {
      recommendations.push({
        device: 'Device',
        category: 'EQ',
        parameter: 'Param',
        value: 'Value',
        reason: 'Reason',
        sources: [`field${i}`],
      });
    }

    const result = createMockPhase2Result(recommendations);
    const report = analyzeFieldUtilization(result as Phase2Result);

    expect(report.mostUsedFields).toHaveLength(10);
  });

  it('sorts mostUsedFields by citation count descending', () => {
    const result = createMockPhase2Result([
      {
        device: 'Device1',
        category: 'EQ',
        parameter: 'Param',
        value: 'Value',
        reason: 'Reason',
        sources: ['fieldA', 'fieldA', 'fieldA'],
      },
      {
        device: 'Device2',
        category: 'EQ',
        parameter: 'Param',
        value: 'Value',
        reason: 'Reason',
        sources: ['fieldB'],
      },
      {
        device: 'Device3',
        category: 'EQ',
        parameter: 'Param',
        value: 'Value',
        reason: 'Reason',
        sources: ['fieldA', 'fieldA'],
      },
    ]);

    const report = analyzeFieldUtilization(result as Phase2Result);

    expect(report.mostUsedFields[0].field).toBe('fieldA');
    expect(report.mostUsedFields[0].citationCount).toBe(5); // 3 + 2
    expect(report.mostUsedFields[1].field).toBe('fieldB');
    expect(report.mostUsedFields[1].citationCount).toBe(1);
  });
});

describe('generateUtilizationMarkdown', () => {
  it('generates markdown report with all sections', () => {
    const report: UtilizationReport = {
      mostUsedFields: [
        {
          field: 'bpm',
          citationCount: 5,
          categories: ['EQ', 'DYNAMICS'],
        },
        {
          field: 'key',
          citationCount: 3,
          categories: ['SYNTHESIS'],
        },
      ],
      unusedFields: ['durationSeconds', 'crestFactor'],
      totalRecommendations: 10,
      avgSourcesPerRecommendation: 1.5,
      categoryBreakdown: {
        EQ: {
          recommendationCount: 5,
          avgSources: 1.2,
          topFields: ['bpm', 'key'],
        },
        DYNAMICS: {
          recommendationCount: 3,
          avgSources: 1.0,
          topFields: ['bpm'],
        },
      },
    };

    const markdown = generateUtilizationMarkdown(report);

    expect(markdown).toContain('# Field Utilization Report');
    expect(markdown).toContain('## Summary');
    expect(markdown).toContain('Total Recommendations: **10**');
    expect(markdown).toContain('Avg Sources per Recommendation: **1.50**');
    expect(markdown).toContain('## Most Used Fields (Top 10)');
    expect(markdown).toContain('## Unused Fields');
    expect(markdown).toContain('## Category Breakdown');
  });

  it('includes field details in markdown', () => {
    const report: UtilizationReport = {
      mostUsedFields: [
        {
          field: 'bpm',
          citationCount: 5,
          categories: ['EQ', 'DYNAMICS'],
        },
      ],
      unusedFields: [],
      totalRecommendations: 5,
      avgSourcesPerRecommendation: 1,
      categoryBreakdown: {},
    };

    const markdown = generateUtilizationMarkdown(report);

    expect(markdown).toContain('bpm');
    expect(markdown).toContain('5');
    expect(markdown).toContain('EQ');
    expect(markdown).toContain('DYNAMICS');
  });

  it('handles empty report gracefully', () => {
    const report: UtilizationReport = {
      mostUsedFields: [],
      unusedFields: [],
      totalRecommendations: 0,
      avgSourcesPerRecommendation: 0,
      categoryBreakdown: {},
    };

    const markdown = generateUtilizationMarkdown(report);

    expect(markdown).toContain('# Field Utilization Report');
    expect(markdown).toContain('Total Recommendations: **0**');
  });

  it('lists unused fields as bullet points', () => {
    const report: UtilizationReport = {
      mostUsedFields: [],
      unusedFields: ['field1', 'field2', 'field3'],
      totalRecommendations: 0,
      avgSourcesPerRecommendation: 0,
      categoryBreakdown: {},
    };

    const markdown = generateUtilizationMarkdown(report);

    expect(markdown).toContain('- `field1`');
    expect(markdown).toContain('- `field2`');
    expect(markdown).toContain('- `field3`');
  });
});

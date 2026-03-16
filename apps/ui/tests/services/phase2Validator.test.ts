import { describe, it, expect } from 'vitest';
import {
  validatePhase2Consistency,
  ValidationViolation,
  ValidationReport,
} from '../../src/services/phase2Validator';
import { Phase1Result, Phase2Result } from '../../src/types';

// Helper to create a base Phase1Result
const createBasePhase1 = (overrides: Partial<Phase1Result> = {}): Phase1Result => ({
  bpm: 126,
  bpmConfidence: 0.91,
  key: 'F minor',
  keyConfidence: 0.87,
  timeSignature: '4/4',
  durationSeconds: 210.6,
  lufsIntegrated: -7.9,
  lufsRange: 2.3,
  truePeak: -0.2,
  crestFactor: 12.5,
  stereoWidth: 0.69,
  stereoCorrelation: 0.84,
  spectralBalance: {
    subBass: -0.7,
    lowBass: 1.2,
    mids: -0.3,
    upperMids: 0.4,
    highs: 1.0,
    brilliance: 0.8,
  },
  spectralDetail: {
    spectralCentroid: 3500,
  },
  rhythmDetail: {
    kickSwing: 0.08,
    kickAccent: [0.8, 0.2, 0.7, 0.3, 0.8, 0.2, 0.7, 0.3, 0.8, 0.2, 0.7, 0.3, 0.8, 0.2, 0.7, 0.3],
    hihatSwing: 0.05,
  },
  synthesisCharacter: {
    inharmonicity: 0.15,
    oddToEvenRatio: 1.2,
  },
  ...overrides,
});

// Helper to create a base Phase2Result
const createBasePhase2 = (overrides: Partial<Phase2Result> = {}): Phase2Result => ({
  trackCharacter: 'Tight modern electronic mix at 126 BPM in F minor.',
  detectedCharacteristics: [
    { name: 'Stereo Discipline', confidence: 'HIGH', explanation: 'Controlled width and correlation.' },
  ],
  arrangementOverview: {
    summary: 'Arrangement transitions and energy shifts.',
    segments: [
      { index: 1, startTime: 0, endTime: 30, lufs: -8.4, description: 'Intro', spectralNote: 'Sparse' },
    ],
  },
  sonicElements: {
    kick: 'Four-on-the-floor kick at 126 BPM.',
    bass: 'FM bass character.',
    melodicArp: 'Simple melodic motif.',
    grooveAndTiming: 'Tight quantized groove with minimal swing.',
    effectsAndTexture: 'Light atmospherics.',
  },
  mixAndMasterChain: [
    { order: 1, device: 'EQ Eight', parameter: 'Low Cut', value: '30 Hz', reason: 'Removes rumble' },
    { order: 2, device: 'Compressor', parameter: 'Ratio', value: '4:1', reason: 'Controls dynamics' },
  ],
  secretSauce: {
    title: 'Punch Layering',
    explanation: 'Layered transient enhancement.',
    implementationSteps: ['Step 1', 'Step 2', 'Step 3', 'Step 4', 'Step 5', 'Step 6'],
  },
  confidenceNotes: [
    { field: 'Key Signature', value: 'HIGH', reason: 'Stable detection.' },
    { field: 'Rhythm cluster', value: 'tight mechanical pulse', reason: 'kickSwing 0.08, low variance' },
    { field: 'Synthesis tier', value: 'FM/acid character', reason: 'inharmonicity 0.15' },
  ],
  abletonRecommendations: [
    { device: 'Operator', category: 'SYNTHESIS', parameter: 'Coarse', value: '1.00', reason: 'Matches tonal center' },
  ],
  ...overrides,
});

describe('validatePhase2Consistency', () => {
  describe('BPM validation', () => {
    it('should pass when Phase 2 BPM is within 2.0 BPM of Phase 1', () => {
      const phase1 = createBasePhase1({ bpm: 126 });
      const phase2 = createBasePhase2({
        trackCharacter: 'Track at 127.5 BPM',
        sonicElements: { ...createBasePhase2().sonicElements, kick: 'Kick at 127.5 BPM' },
      });

      const result = validatePhase2Consistency(phase1, phase2);

      expect(result.passed).toBe(true);
      expect(result.violations.filter(v => v.field === 'bpm')).toHaveLength(0);
    });

    it('should report ERROR when Phase 2 BPM differs by more than 2.0 from Phase 1', () => {
      const phase1 = createBasePhase1({ bpm: 126 });
      const phase2 = createBasePhase2({
        trackCharacter: 'Track at 130 BPM',
        sonicElements: { ...createBasePhase2().sonicElements, kick: 'Kick at 130 BPM' },
      });

      const result = validatePhase2Consistency(phase1, phase2);

      const bpmViolation = result.violations.find(v => v.field === 'bpm');
      expect(bpmViolation).toBeDefined();
      expect(bpmViolation?.type).toBe('NUMERIC_OVERRIDE');
      expect(bpmViolation?.severity).toBe('ERROR');
      expect(bpmViolation?.phase1Value).toBe(126);
      expect(result.passed).toBe(false);
    });

    it('should detect BPM in trackCharacter text', () => {
      const phase1 = createBasePhase1({ bpm: 128 });
      const phase2 = createBasePhase2({ trackCharacter: 'Driving techno track at 135 BPM with heavy bass.' });

      const result = validatePhase2Consistency(phase1, phase2);

      const bpmViolation = result.violations.find(v => v.field === 'bpm');
      expect(bpmViolation).toBeDefined();
      expect(bpmViolation?.severity).toBe('ERROR');
    });

    it('should detect BPM in sonicElements text', () => {
      const phase1 = createBasePhase1({ bpm: 124 });
      const phase2 = createBasePhase2({
        sonicElements: { ...createBasePhase2().sonicElements, kick: 'Kick pattern at 130 BPM' },
      });

      const result = validatePhase2Consistency(phase1, phase2);

      const bpmViolation = result.violations.find(v => v.field === 'bpm');
      expect(bpmViolation).toBeDefined();
    });
  });

  describe('Key validation', () => {
    it('should pass when Phase 2 key matches Phase 1 key exactly', () => {
      const phase1 = createBasePhase1({ key: 'F minor' });
      const phase2 = createBasePhase2({ trackCharacter: 'Track in F minor with dark atmosphere.' });

      const result = validatePhase2Consistency(phase1, phase2);

      const keyViolation = result.violations.find(v => v.field === 'key');
      expect(keyViolation).toBeUndefined();
    });

    it('should pass when Phase 1 key is null', () => {
      const phase1 = createBasePhase1({ key: null });
      const phase2 = createBasePhase2({ trackCharacter: 'Track in unknown key.' });

      const result = validatePhase2Consistency(phase1, phase2);

      const keyViolation = result.violations.find(v => v.field === 'key');
      expect(keyViolation).toBeUndefined();
    });

    it('should report ERROR when Phase 2 contradicts Phase 1 key', () => {
      const phase1 = createBasePhase1({ key: 'F minor' });
      const phase2 = createBasePhase2({ trackCharacter: 'Track in A major with bright vibes.' });

      const result = validatePhase2Consistency(phase1, phase2);

      const keyViolation = result.violations.find(v => v.field === 'key');
      expect(keyViolation).toBeDefined();
      expect(keyViolation?.type).toBe('NUMERIC_OVERRIDE');
      expect(keyViolation?.severity).toBe('ERROR');
      expect(keyViolation?.phase1Value).toBe('F minor');
      expect(result.passed).toBe(false);
    });
  });

  describe('LUFS validation', () => {
    it('should pass when Phase 2 LUFS values are within reasonable bounds', () => {
      const phase1 = createBasePhase1({ lufsIntegrated: -7.9 });
      const phase2 = createBasePhase2({
        arrangementOverview: {
          ...createBasePhase2().arrangementOverview,
          segments: [{ index: 1, startTime: 0, endTime: 30, lufs: -8.2, description: 'Intro' }],
        },
      });

      const result = validatePhase2Consistency(phase1, phase2);

      const lufsViolations = result.violations.filter(v => v.field.includes('lufs') || v.field.includes('LUFS'));
      expect(lufsViolations).toHaveLength(0);
    });

    it('should report WARNING when segment LUFS differs significantly from integrated', () => {
      const phase1 = createBasePhase1({ lufsIntegrated: -7.9 });
      const phase2 = createBasePhase2({
        arrangementOverview: {
          ...createBasePhase2().arrangementOverview,
          segments: [{ index: 1, startTime: 0, endTime: 30, lufs: -3.0, description: 'Very loud section' }],
        },
      });

      const result = validatePhase2Consistency(phase1, phase2);

      const lufsViolation = result.violations.find(v => v.field === 'segmentLufs');
      expect(lufsViolation).toBeDefined();
      expect(lufsViolation?.severity).toBe('WARNING');
    });
  });

  describe('Genre/DSP consistency validation', () => {
    it('should pass when confidenceNotes reference rhythm cluster and synthesis tier', () => {
      const phase1 = createBasePhase1({
        rhythmDetail: { kickSwing: 0.08, kickAccent: [0.8, 0.2], hihatSwing: 0.05 },
        synthesisCharacter: { inharmonicity: 0.15, oddToEvenRatio: 1.2 },
      });
      const phase2 = createBasePhase2({
        confidenceNotes: [
          { field: 'Rhythm cluster', value: 'tight', reason: 'kickSwing 0.08' },
          { field: 'Synthesis tier', value: 'FM', reason: 'inharmonicity 0.15' },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);

      const dspViolation = result.violations.find(v => v.type === 'GENRE_IGNORES_DSP');
      expect(dspViolation).toBeUndefined();
    });

    it('should report WARNING when confidenceNotes ignore DSP context', () => {
      const phase1 = createBasePhase1({
        rhythmDetail: { kickSwing: 0.08, kickAccent: [0.8, 0.2], hihatSwing: 0.05 },
        synthesisCharacter: { inharmonicity: 0.15, oddToEvenRatio: 1.2 },
      });
      const phase2 = createBasePhase2({
        confidenceNotes: [
          { field: 'Key Signature', value: 'HIGH', reason: 'Stable' },
          { field: 'Bass detection', value: 'MED', reason: 'Some uncertainty' },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);

      const dspViolation = result.violations.find(v => v.type === 'GENRE_IGNORES_DSP');
      expect(dspViolation).toBeDefined();
      expect(dspViolation?.severity).toBe('WARNING');
    });
  });

  describe('Numeric bounds validation', () => {
    it('should report WARNING when EQ cutoffs exceed spectral centroid', () => {
      const phase1 = createBasePhase1({ spectralDetail: { spectralCentroid: 2000 } });
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          { device: 'EQ Eight', category: 'EQ', parameter: 'High Cut', value: '8000 Hz', reason: 'Roll off highs' },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);

      const boundsViolation = result.violations.find(v => v.field === 'eqHighCut');
      expect(boundsViolation).toBeDefined();
      expect(boundsViolation?.type).toBe('BOUNDS_VIOLATION');
      expect(boundsViolation?.severity).toBe('WARNING');
    });

    it('should pass when EQ cutoffs are within spectral bounds', () => {
      const phase1 = createBasePhase1({ spectralDetail: { spectralCentroid: 5000 } });
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          { device: 'EQ Eight', category: 'EQ', parameter: 'High Cut', value: '4000 Hz', reason: 'Roll off highs' },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);

      const boundsViolation = result.violations.find(v => v.field === 'eqHighCut');
      expect(boundsViolation).toBeUndefined();
    });
  });

  describe('Summary statistics', () => {
    it('should count errors and warnings correctly', () => {
      const phase1 = createBasePhase1({ bpm: 126, key: 'F minor' });
      const phase2 = createBasePhase2({
        trackCharacter: 'Track at 130 BPM in A major.',
        confidenceNotes: [{ field: 'Key', value: 'HIGH', reason: 'Clear' }],
      });

      const result = validatePhase2Consistency(phase1, phase2);

      expect(result.summary.errorCount).toBeGreaterThan(0);
      expect(result.summary.checkedFields).toBeGreaterThan(0);
      expect(result.summary.errorCount + result.summary.warningCount).toBe(result.violations.length);
    });

    it('should set passed=false when there are errors', () => {
      const phase1 = createBasePhase1({ bpm: 126 });
      const phase2 = createBasePhase2({ trackCharacter: 'Track at 135 BPM' });

      const result = validatePhase2Consistency(phase1, phase2);

      expect(result.passed).toBe(false);
      expect(result.summary.errorCount).toBeGreaterThan(0);
    });

    it('should set passed=true when only warnings exist', () => {
      const phase1 = createBasePhase1({
        rhythmDetail: { kickSwing: 0.08, kickAccent: [0.8], hihatSwing: 0.05 },
      });
      const phase2 = createBasePhase2({
        confidenceNotes: [{ field: 'Key', value: 'HIGH', reason: 'Clear' }],
      });

      const result = validatePhase2Consistency(phase1, phase2);

      // Should have warnings but still pass
      if (result.summary.warningCount > 0) {
        expect(result.passed).toBe(true);
      }
    });
  });
});

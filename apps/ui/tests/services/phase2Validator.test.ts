import { describe, it, expect } from 'vitest';
import {
  collectPhase1FieldPaths,
  pathCoversTracked,
  PHASE1_NEW_FIELD_PATHS,
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
    lowMids: 0.0,
    mids: -0.3,
    upperMids: 0.4,
    highs: 1.0,
    brilliance: 0.8,
  },
  spectralDetail: {
    spectralCentroidMean: 3500,
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
        sonicElements: {
          ...createBasePhase2().sonicElements,
          kick: 'Kick at 127.5 BPM',
        },
      });

      const result = validatePhase2Consistency(phase1, phase2);

      expect(result.passed).toBe(true);
      expect(result.violations.filter(v => v.field === 'bpm')).toHaveLength(0);
    });

    it('should report ERROR when Phase 2 BPM differs by more than 2.0 from Phase 1', () => {
      const phase1 = createBasePhase1({ bpm: 126 });
      const phase2 = createBasePhase2({
        trackCharacter: 'Track at 130 BPM',
        sonicElements: {
          ...createBasePhase2().sonicElements,
          kick: 'Kick at 130 BPM',
        },
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
        sonicElements: {
          ...createBasePhase2().sonicElements,
          kick: 'Kick pattern at 130 BPM',
        },
      });

      const result = validatePhase2Consistency(phase1, phase2);

      const bpmViolation = result.violations.find(v => v.field === 'bpm');
      expect(bpmViolation).toBeDefined();
    });

    it('flags a BPM contradiction in styleProfile.description', () => {
      const phase1 = createBasePhase1({ bpm: 126 });
      const phase2 = createBasePhase2({
        styleProfile: {
          genre: 'Techno',
          subGenre: 'Warehouse',
          mood: ['Driving'],
          instruments: ['Kick', 'Bass'],
          productionTechniques: ['Sidechain'],
          description: 'Driving warehouse techno at 140 BPM with a hard kick.',
          generationPrompt: 'Warehouse techno groove in F minor at 126 BPM.',
          authoritativeMeasurements: { bpm: 126, key: 'F minor', timeSignature: '4/4' },
        },
      });

      const result = validatePhase2Consistency(phase1, phase2);

      const bpmViolations = result.violations.filter(v => v.field === 'bpm');
      expect(bpmViolations.length).toBeGreaterThan(0);
      expect(bpmViolations.some(v => String(v.message).includes('styleProfile.description'))).toBe(true);
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

    it('flags a key contradiction in styleProfile.generationPrompt', () => {
      const phase1 = createBasePhase1({ key: 'F minor' });
      const phase2 = createBasePhase2({
        styleProfile: {
          genre: 'Techno',
          subGenre: 'Warehouse',
          mood: ['Driving'],
          instruments: ['Kick'],
          productionTechniques: [],
          description: 'Driving techno with disciplined low end.',
          generationPrompt: 'Warehouse techno loop in C major at 126 BPM.',
          authoritativeMeasurements: { bpm: 126, key: 'F minor', timeSignature: '4/4' },
        },
      });

      const result = validatePhase2Consistency(phase1, phase2);

      const keyViolations = result.violations.filter(v => v.field === 'key');
      expect(keyViolations.length).toBeGreaterThan(0);
      expect(keyViolations.some(v => String(v.message).includes('styleProfile.generationPrompt'))).toBe(true);
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
          segments: [{ index: 1, startTime: 0, endTime: 30, lufs: -1.0, description: 'Very loud section' }],
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
      const phase1 = createBasePhase1({ spectralDetail: { spectralCentroidMean: 2000 } });
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
      const phase1 = createBasePhase1({ spectralDetail: { spectralCentroidMean: 5000 } });
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

  describe('Citation contract (phase1Fields)', () => {
    it('skips citation checks for legacy stored runs that have no phase1Fields anywhere', () => {
      // Existing fixture intentionally lacks phase1Fields on recommendations —
      // simulates a stored Phase 2 result from before the citation contract.
      const phase1 = createBasePhase1();
      const phase2 = createBasePhase2();

      const result = validatePhase2Consistency(phase1, phase2);
      const citationViolations = result.violations.filter(v => v.type === 'MISSING_CITATION');
      expect(citationViolations).toHaveLength(0);
    });

    it('runs citation checks when at least one rec exposes phase1Fields', () => {
      const phase1 = createBasePhase1();
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'Operator',
            category: 'SYNTHESIS',
            parameter: 'Coarse',
            value: '1.00',
            reason: 'Matches tonal center.',
            phase1Fields: ['bpm', 'spectralBalance.subBass'],
          },
        ],
        mixAndMasterChain: [
          {
            order: 1,
            device: 'EQ Eight',
            parameter: 'Low Cut',
            value: '30 Hz',
            reason: 'Removes rumble.',
            // Intentionally omit phase1Fields here — this rec should error.
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const missing = result.violations.filter(
        v => v.type === 'MISSING_CITATION' && v.field.startsWith('mixAndMasterChain'),
      );
      expect(missing).toHaveLength(1);
      expect(missing[0].severity).toBe('ERROR');
      expect(missing[0].message).toContain('missing the required phase1Fields');
    });

    it('rejects an empty phase1Fields array', () => {
      const phase1 = createBasePhase1();
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'Operator',
            category: 'SYNTHESIS',
            parameter: 'Coarse',
            value: '1.00',
            reason: 'Matches tonal center.',
            phase1Fields: [],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const empty = result.violations.filter(
        v => v.type === 'MISSING_CITATION' && v.message.includes('empty phase1Fields array'),
      );
      expect(empty).toHaveLength(1);
    });

    it('rejects citations to invented field paths', () => {
      const phase1 = createBasePhase1();
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'Operator',
            category: 'SYNTHESIS',
            parameter: 'Coarse',
            value: '1.00',
            reason: 'Matches tonal center.',
            phase1Fields: ['bpm', 'inventedField.thatDoesNotExist'],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const inventedViolations = result.violations.filter(
        v => v.type === 'MISSING_CITATION' && v.message.includes('does not match any path'),
      );
      expect(inventedViolations).toHaveLength(1);
      expect(inventedViolations[0].phase2Value).toBe('inventedField.thatDoesNotExist');
    });

    it('accepts citations to nested scalar paths like spectralBalance.subBass', () => {
      const phase1 = createBasePhase1();
      const phase2 = createBasePhase2({
        // Once auto-detection treats the response as new-shape, every rec
        // bucket must carry phase1Fields. This fixture exercises the happy
        // path across all three buckets.
        abletonRecommendations: [
          {
            device: 'EQ Eight',
            category: 'EQ',
            parameter: 'Low Shelf',
            value: '+1.5 dB',
            reason: 'Bring up the sub-bass region.',
            phase1Fields: ['spectralBalance.subBass', 'lufsIntegrated'],
          },
        ],
        mixAndMasterChain: [
          {
            order: 1,
            device: 'EQ Eight',
            parameter: 'Low Cut',
            value: '30 Hz',
            reason: 'Removes rumble.',
            phase1Fields: ['spectralBalance.subBass'],
          },
        ],
        secretSauce: {
          title: 'Punch Layering',
          explanation: 'Layered transient enhancement.',
          implementationSteps: ['Step 1', 'Step 2', 'Step 3', 'Step 4', 'Step 5', 'Step 6'],
          workflowSteps: [
            {
              step: 1,
              trackContext: 'Master',
              device: 'Glue Compressor',
              parameter: 'Ratio',
              value: '2:1',
              instruction: 'Glue the bus.',
              measurementJustification: 'Crest factor supports gentle glue.',
              phase1Fields: ['crestFactor'],
            },
          ],
        },
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const citationErrors = result.violations.filter(v => v.type === 'MISSING_CITATION');
      expect(citationErrors).toHaveLength(0);
    });

    it('validates phase1Fields on secretSauce.workflowSteps too', () => {
      const phase1 = createBasePhase1();
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'Operator',
            category: 'SYNTHESIS',
            parameter: 'Coarse',
            value: '1.00',
            reason: 'Matches tonal center.',
            phase1Fields: ['bpm'],
          },
        ],
        secretSauce: {
          title: 'Punch Layering',
          explanation: 'Layered transient enhancement.',
          implementationSteps: ['Step 1', 'Step 2', 'Step 3', 'Step 4', 'Step 5', 'Step 6'],
          workflowSteps: [
            {
              step: 1,
              trackContext: 'Drum Group',
              device: 'Glue Compressor',
              parameter: 'Attack',
              value: '3 ms',
              instruction: 'Set up bus glue.',
              measurementJustification: 'Crest profile supports controlled transient shape.',
              // phase1Fields intentionally missing
            },
          ],
        },
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const workflowViolations = result.violations.filter(
        v => v.type === 'MISSING_CITATION' && v.field.startsWith('secretSauce.workflowSteps'),
      );
      expect(workflowViolations).toHaveLength(1);
    });
  });

  describe('Citation diversity (TRIVIAL_CITATIONS)', () => {
    const baseRec = (phase1Fields: string[]) => ({
      device: 'Operator',
      category: 'SYNTHESIS' as const,
      parameter: 'Coarse',
      value: '1.00',
      reason: 'Matches tonal center.',
      phase1Fields,
    });

    it('warns when >60% of recommendations cite the same single anchor', () => {
      const phase1 = createBasePhase1();
      const phase2 = createBasePhase2({
        // 6 of 6 cite ["bpm"] — 100% dominance, deep into trivial.
        abletonRecommendations: Array.from({ length: 6 }, () => baseRec(['bpm'])),
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const trivial = result.violations.filter(v => v.type === 'TRIVIAL_CITATIONS');
      expect(trivial).toHaveLength(1);
      expect(trivial[0].severity).toBe('WARNING');
      expect(trivial[0].phase2Value).toBe('bpm');
    });

    it('does not warn when citations are diverse', () => {
      const phase1 = createBasePhase1();
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          baseRec(['bpm']),
          baseRec(['key']),
          baseRec(['spectralBalance.subBass']),
          baseRec(['stereoDetail.subBassCorrelation']),
          baseRec(['kickDetail.fundamentalHz']),
          baseRec(['lufsIntegrated', 'crestFactor']),
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const trivial = result.violations.filter(v => v.type === 'TRIVIAL_CITATIONS');
      expect(trivial).toHaveLength(0);
    });

    it('skips the diversity check when fewer than 4 recommendations have citations', () => {
      // 3 recs total, all identical — under the minimum threshold so no warning.
      const phase1 = createBasePhase1();
      const phase2 = createBasePhase2({
        abletonRecommendations: Array.from({ length: 3 }, () => baseRec(['bpm'])),
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const trivial = result.violations.filter(v => v.type === 'TRIVIAL_CITATIONS');
      expect(trivial).toHaveLength(0);
    });
  });

  describe('New-field coverage (NEW_FIELD_UNCITED)', () => {
    it('warns when a Phase 1.A field is populated but uncited', () => {
      const phase1 = createBasePhase1({
        // Inject the new Phase 1.A field as if the analyzer produced it.
        // Density must clear MIN_USEFUL_CURVE_POINTS (5) on at least one
        // child curve or the validator correctly treats it as "not yet
        // meaningful" and skips the warning.
        lufsCurve: {
          shortTerm: [
            { t: 0.0, lufs: -16.2 },
            { t: 3.0, lufs: -15.8 },
            { t: 6.0, lufs: -14.9 },
            { t: 9.0, lufs: -13.5 },
            { t: 12.0, lufs: -11.2 },
            { t: 15.0, lufs: -9.4 },
          ],
          momentary: [{ t: 0.0, lufs: -15.8 }],
        },
      } as Partial<Phase1Result>);
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'EQ Eight',
            category: 'EQ',
            parameter: 'Low Cut',
            value: '30 Hz',
            reason: 'Removes rumble.',
            phase1Fields: ['spectralBalance.subBass'],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const uncited = result.violations.filter(v => v.type === 'NEW_FIELD_UNCITED');
      expect(uncited.some(v => v.field === 'lufsCurve')).toBe(true);
    });

    it('does not warn when a parent path is cited (prefix tolerance)', () => {
      const phase1 = createBasePhase1({
        // Same density requirement as the prior test.
        lufsCurve: {
          shortTerm: [
            { t: 0.0, lufs: -16.2 },
            { t: 3.0, lufs: -15.8 },
            { t: 6.0, lufs: -14.9 },
            { t: 9.0, lufs: -13.5 },
            { t: 12.0, lufs: -11.2 },
            { t: 15.0, lufs: -9.4 },
          ],
          momentary: [{ t: 0.0, lufs: -15.8 }],
        },
      } as Partial<Phase1Result>);
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'Glue Compressor',
            category: 'DYNAMICS',
            parameter: 'Attack',
            value: '10 ms',
            reason: 'Preserves transients.',
            // Citing the parent path covers any child paths.
            phase1Fields: ['lufsCurve'],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const uncited = result.violations.filter(
        v => v.type === 'NEW_FIELD_UNCITED' && v.field.startsWith('lufsCurve.'),
      );
      expect(uncited).toHaveLength(0);
    });

    it('does not warn when the field is absent from Phase 1', () => {
      // Default fixture has no lufsCurve; no rec cites it; should NOT warn.
      const phase1 = createBasePhase1();
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'Operator',
            category: 'SYNTHESIS',
            parameter: 'Coarse',
            value: '1.00',
            reason: 'Matches tonal center.',
            phase1Fields: ['bpm'],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const uncited = result.violations.filter(
        v => v.type === 'NEW_FIELD_UNCITED' && v.field === 'lufsCurve',
      );
      expect(uncited).toHaveLength(0);
    });

    it('does not warn for a parent tracked path when a more-specific child is cited (bidirectional)', () => {
      // grooveDetail.perDrumSwing is the tracked parent; Gemini cites the
      // leaf perDrumSwing.snare — the gate must accept the leaf citation as
      // covering the tracked parent (the case the v2 validator missed).
      const phase1 = createBasePhase1({
        grooveDetail: {
          kickSwing: 0.9,
          hihatSwing: 0.6,
          kickAccent: [0.4, 0.6, 0.8, 0.7, 0.5],
          hihatAccent: [0.3, 0.5, 0.7, 0.6, 0.4],
          perDrumSwing: { kick: 0.9, snare: 0.51, hihat: 0.64 },
        } as any,
      } as Partial<Phase1Result>);
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'Beat Repeat',
            category: 'GROOVE',
            parameter: 'Variation',
            value: '12 %',
            reason: 'Snare is humanized while kick stays rigid.',
            phase1Fields: ['grooveDetail.perDrumSwing.snare'],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const uncited = result.violations.filter(
        v => v.type === 'NEW_FIELD_UNCITED' && v.field === 'grooveDetail.perDrumSwing',
      );
      expect(uncited).toHaveLength(0);
    });

    it('does not warn for a stem-scoped wildcard path when any stem cites it', () => {
      // stemAnalysis.*.reverbDetail tracked; one stem (bass) has the field
      // populated and Gemini cites it on that stem — the gate must treat
      // the wildcard as satisfied without enumerating per-stem paths.
      const phase1 = createBasePhase1({
        stemAnalysis: {
          bass: {
            reverbDetail: {
              rt60: 2.25,
              isWet: true,
              tailEnergyRatio: 0.88,
              measured: true,
              perBandRt60: { low: 2.06, lowMids: 2.21, highMids: 2.8, highs: 2.33 },
              preDelayMs: 80.0,
            },
          },
        } as any,
      } as Partial<Phase1Result>);
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'Reverb',
            category: 'EFFECTS',
            parameter: 'PreDelay',
            value: '80 ms',
            reason: 'Bass-bus reverb pre-delay matches measured stem value.',
            phase1Fields: ['stemAnalysis.bass.reverbDetail.preDelayMs'],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const uncited = result.violations.filter(
        v => v.type === 'NEW_FIELD_UNCITED' && v.field === 'stemAnalysis.*.reverbDetail',
      );
      expect(uncited).toHaveLength(0);
    });

    it('warns for a stem-scoped wildcard path when no stem is cited', () => {
      // stemAnalysis.*.reverbDetail tracked; field is populated on at least
      // one stem; no recommendation cites any per-stem reverb path. The gate
      // SHOULD warn (and the wildcard must not falsely auto-pass).
      const phase1 = createBasePhase1({
        stemAnalysis: {
          drums: {
            reverbDetail: {
              rt60: 0.81,
              isWet: true,
              tailEnergyRatio: 0.65,
              measured: true,
              perBandRt60: { low: 0.62, lowMids: 0.92, highMids: 1.35, highs: 1.68 },
              preDelayMs: 40.0,
            },
          },
        } as any,
      } as Partial<Phase1Result>);
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'EQ Eight',
            category: 'EQ',
            parameter: 'Low Cut',
            value: '30 Hz',
            reason: 'Removes rumble.',
            phase1Fields: ['spectralBalance.subBass'],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const uncited = result.violations.filter(
        v => v.type === 'NEW_FIELD_UNCITED' && v.field === 'stemAnalysis.*.reverbDetail',
      );
      expect(uncited).toHaveLength(1);
    });

    it('exported PHASE1_NEW_FIELD_PATHS includes the Phase 1.C/D additions', () => {
      // The live decision-gate comparator imports this constant — guard the
      // shape so that future renames or accidental removals are caught.
      expect(PHASE1_NEW_FIELD_PATHS).toContain('grooveDetail.perDrumSwing');
      expect(PHASE1_NEW_FIELD_PATHS).toContain('reverbDetail.perBandRt60');
      expect(PHASE1_NEW_FIELD_PATHS).toContain('reverbDetail.preDelayMs');
      expect(PHASE1_NEW_FIELD_PATHS).toContain('sidechainDetail.envelopeShape32');
      expect(PHASE1_NEW_FIELD_PATHS).toContain('stemAnalysis.*.reverbDetail');
      expect(PHASE1_NEW_FIELD_PATHS).toContain('transientDensityDetail');
      expect(PHASE1_NEW_FIELD_PATHS).toContain('snareDetail');
      expect(PHASE1_NEW_FIELD_PATHS).toContain('hihatDetail');
      expect(PHASE1_NEW_FIELD_PATHS).toContain('saturationDetail');
      // Phase 1.D #2 — librosa+Viterbi chord-timeline migration.
      expect(PHASE1_NEW_FIELD_PATHS).toContain('chordDetail.chordTimeline');
      expect(PHASE1_NEW_FIELD_PATHS).toContain('chordDetail.chordChangeCount');
    });

    it('warns when chordDetail.chordTimeline is populated but no recommendation cites it', () => {
      // chordTimeline needs >=5 entries to clear the MIN_USEFUL_CURVE_POINTS
      // threshold — same gate that protects lufsCurve / noveltyCurve from
      // warning on too-sparse data.
      const phase1 = createBasePhase1({
        chordDetail: {
          chordSequence: ['Cm', 'Eb', 'Bb', 'Ab', 'Fm', 'Cm'],
          chordStrength: 0.72,
          progression: ['Cm', 'Eb', 'Bb', 'Ab', 'Fm'],
          dominantChords: ['Cm', 'Eb', 'Bb', 'Ab'],
          chordTimeline: [
            { startSec: 0, endSec: 4, label: 'Cm', labelLong: 'C minor', confidence: 0.8 },
            { startSec: 4, endSec: 8, label: 'Eb', labelLong: 'Eb major', confidence: 0.65 },
            { startSec: 8, endSec: 12, label: 'Bb', labelLong: 'Bb major', confidence: 0.7 },
            { startSec: 12, endSec: 16, label: 'Ab', labelLong: 'Ab major', confidence: 0.6 },
            { startSec: 16, endSec: 20, label: 'Fm', labelLong: 'F minor', confidence: 0.55 },
          ],
          chordChangeCount: 4,
          chordTimelineSource: 'librosa_viterbi',
          chordTimelineAgreement: true,
        },
      } as Partial<Phase1Result>);
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'EQ Eight',
            category: 'EQ',
            parameter: 'Low Cut',
            value: '30 Hz',
            reason: 'Removes rumble.',
            phase1Fields: ['spectralBalance.subBass'],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const uncited = result.violations.filter(
        v => v.type === 'NEW_FIELD_UNCITED' && v.field === 'chordDetail.chordTimeline',
      );
      expect(uncited).toHaveLength(1);
    });

    it('does not warn when a chordDetail child path is cited', () => {
      const phase1 = createBasePhase1({
        chordDetail: {
          chordSequence: ['Cm', 'Eb', 'Bb', 'Ab', 'Fm', 'Cm'],
          chordStrength: 0.72,
          chordTimeline: [
            { startSec: 0, endSec: 4, label: 'Cm', labelLong: 'C minor', confidence: 0.8 },
            { startSec: 4, endSec: 8, label: 'Eb', labelLong: 'Eb major', confidence: 0.65 },
            { startSec: 8, endSec: 12, label: 'Bb', labelLong: 'Bb major', confidence: 0.7 },
            { startSec: 12, endSec: 16, label: 'Ab', labelLong: 'Ab major', confidence: 0.6 },
            { startSec: 16, endSec: 20, label: 'Fm', labelLong: 'F minor', confidence: 0.55 },
          ],
          chordChangeCount: 4,
          chordTimelineSource: 'librosa_viterbi',
          chordTimelineAgreement: true,
        },
      } as Partial<Phase1Result>);
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'MIDI Effects',
            category: 'MIDI',
            parameter: 'Chord Trigger',
            value: 'Cm',
            reason: 'The Viterbi timeline reads Cm with high confidence.',
            // Citing the path satisfies the new-field-coverage gate.
            phase1Fields: ['chordDetail.chordTimeline'],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const uncited = result.violations.filter(
        v => v.type === 'NEW_FIELD_UNCITED' && v.field === 'chordDetail.chordTimeline',
      );
      expect(uncited).toHaveLength(0);
    });

    // Audit Finding #1E: NEW_FIELD_UNCITED is a coverage signal for the
    // engine team ("warning is benign" copy in the message). Tag it
    // dev-audience so the user-facing System Diagnostics panel can filter
    // it out while tests/research keep seeing the violations.
    it('NEW_FIELD_UNCITED violations are marked audience=dev', () => {
      const phase1 = createBasePhase1({
        lufsCurve: {
          shortTerm: [
            { t: 0.0, lufs: -16.2 },
            { t: 3.0, lufs: -15.8 },
            { t: 6.0, lufs: -14.9 },
            { t: 9.0, lufs: -13.5 },
            { t: 12.0, lufs: -11.2 },
            { t: 15.0, lufs: -9.4 },
          ],
          momentary: [{ t: 0.0, lufs: -15.8 }],
        },
      } as Partial<Phase1Result>);
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'EQ Eight',
            category: 'EQ',
            parameter: 'Low Cut',
            value: '30 Hz',
            reason: 'Removes rumble.',
            phase1Fields: ['spectralBalance.subBass'],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const uncited = result.violations.filter(v => v.type === 'NEW_FIELD_UNCITED');
      expect(uncited.length).toBeGreaterThan(0);
      expect(uncited.every(v => v.audience === 'dev')).toBe(true);
    });

    it('non-NEW_FIELD_UNCITED violations default to user audience (audience undefined)', () => {
      // Mirror the existing "EQ cutoff above spectral centroid"
      // BOUNDS_VIOLATION fixture from the Numeric bounds suite so we have a
      // reliable non-coverage violation to assert against.
      const phase1 = createBasePhase1({ spectralDetail: { spectralCentroidMean: 2000 } });
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'EQ Eight',
            category: 'EQ',
            parameter: 'High Cut',
            value: '8000 Hz',
            reason: 'Roll off highs',
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const nonCoverage = result.violations.filter(v => v.type !== 'NEW_FIELD_UNCITED');
      expect(nonCoverage.length).toBeGreaterThan(0);
      expect(nonCoverage.every(v => v.audience === undefined)).toBe(true);
    });
  });

  describe('pathCoversTracked helper', () => {
    it('matches exact strings', () => {
      expect(pathCoversTracked('grooveDetail.perDrumSwing', 'grooveDetail.perDrumSwing')).toBe(true);
    });

    it('parent citation covers child tracked', () => {
      // citation `lufsCurve` covers tracked `lufsCurve.shortTerm`
      expect(pathCoversTracked('lufsCurve', 'lufsCurve.shortTerm')).toBe(true);
    });

    it('child citation covers parent tracked', () => {
      // citation `grooveDetail.perDrumSwing.snare` covers tracked `grooveDetail.perDrumSwing`
      expect(pathCoversTracked('grooveDetail.perDrumSwing.snare', 'grooveDetail.perDrumSwing')).toBe(true);
    });

    it('wildcard matches stem-scoped citation', () => {
      // tracked has `*`; citation has a concrete stem name at that segment;
      // the rest of the citation is a deeper sub-path under the tracked
      // remainder.
      expect(pathCoversTracked('stemAnalysis.drums.reverbDetail.rt60', 'stemAnalysis.*.reverbDetail')).toBe(true);
      expect(pathCoversTracked('stemAnalysis.other.reverbDetail.preDelayMs', 'stemAnalysis.*.reverbDetail')).toBe(true);
      expect(pathCoversTracked('stemAnalysis.bass.reverbDetail', 'stemAnalysis.*.reverbDetail')).toBe(true);
    });

    it('wildcard rejects unrelated path', () => {
      // Concrete segment beside the wildcard must still match; an unrelated
      // sub-path must not satisfy the tracked wildcard.
      expect(pathCoversTracked('stemAnalysis.drums.spectralBalance.subBass', 'stemAnalysis.*.reverbDetail')).toBe(false);
      expect(pathCoversTracked('rhythmDetail.tempoCurve', 'stemAnalysis.*.reverbDetail')).toBe(false);
    });

    it('non-overlapping paths return false', () => {
      expect(pathCoversTracked('spectralBalance.subBass', 'rhythmDetail.tempoCurve')).toBe(false);
    });
  });

  describe('Low-confidence hedging (LOW_CONFIDENCE_NOT_HEDGED)', () => {
    it('flags the exact PDF case: PUMPING_CONFIDENCE 0.26 + "ducking is mandatory"', () => {
      // Fixture mirrors the real Gemini output from the no-stem reference run.
      const phase1 = createBasePhase1({
        sidechainDetail: {
          pumpingStrength: 0.30,
          pumpingRegularity: 0.0,
          pumpingRate: null,
          pumpingConfidence: 0.26,
        },
      } as Partial<Phase1Result>);
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'Compressor',
            category: 'DYNAMICS',
            parameter: 'Sidechain',
            value: 'On',
            reason: 'Pumping strength is 0.29; ducking the bass is mandatory for clarity at 144.9 BPM.',
            phase1Fields: ['sidechainDetail.pumpingStrength'],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const violations = result.violations.filter(
        v => v.type === 'LOW_CONFIDENCE_NOT_HEDGED',
      );
      expect(violations).toHaveLength(1);
      expect(violations[0].severity).toBe('ERROR');
      expect(violations[0].phase2Value).toBe('mandatory');
    });

    it('does not flag hedged language at low confidence', () => {
      const phase1 = createBasePhase1({
        sidechainDetail: {
          pumpingStrength: 0.30,
          pumpingRegularity: 0.0,
          pumpingRate: null,
          pumpingConfidence: 0.26,
        },
      } as Partial<Phase1Result>);
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'Compressor',
            category: 'DYNAMICS',
            parameter: 'Sidechain',
            value: 'On',
            reason: 'Pumping strength is 0.29 with low confidence; consider subtle bass ducking — may add clarity at 144.9 BPM.',
            phase1Fields: ['sidechainDetail.pumpingStrength'],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const violations = result.violations.filter(
        v => v.type === 'LOW_CONFIDENCE_NOT_HEDGED',
      );
      expect(violations).toHaveLength(0);
    });

    it('does not flag imperative language when the cited field has high confidence', () => {
      // Same imperative text, but pumping confidence is high — gate is correctly
      // about LOW-confidence + imperative, not imperative alone.
      const phase1 = createBasePhase1({
        sidechainDetail: {
          pumpingStrength: 0.85,
          pumpingRegularity: 0.92,
          pumpingRate: 'quarter',
          pumpingConfidence: 0.91,
        },
      } as Partial<Phase1Result>);
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'Compressor',
            category: 'DYNAMICS',
            parameter: 'Sidechain',
            value: 'On',
            reason: 'Pumping strength is 0.85; ducking the bass is mandatory for clarity at 144.9 BPM.',
            phase1Fields: ['sidechainDetail.pumpingStrength'],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const violations = result.violations.filter(
        v => v.type === 'LOW_CONFIDENCE_NOT_HEDGED',
      );
      expect(violations).toHaveLength(0);
    });

    it('flags imperative chord recommendations grounded in low chordStrength', () => {
      // chordStrength below the hedging threshold (default 0.4); a card that
      // cites the Viterbi timeline must hedge ("may be", "consider") or the
      // validator will surface it as LOW_CONFIDENCE_NOT_HEDGED.
      const phase1 = createBasePhase1({
        chordDetail: {
          chordSequence: ['Cm'],
          chordStrength: 0.28,
          chordTimeline: [
            { startSec: 0, endSec: 4, label: 'Cm', labelLong: 'C minor', confidence: 0.25 },
          ],
          chordChangeCount: 0,
          chordTimelineSource: 'librosa_viterbi',
          chordTimelineAgreement: false,
        },
      } as Partial<Phase1Result>);
      const phase2 = createBasePhase2({
        abletonRecommendations: [
          {
            device: 'MIDI Effects',
            category: 'MIDI',
            parameter: 'Chord Trigger',
            value: 'Cm',
            reason: 'The timeline reads Cm — you must build the chord stab in Cm.',
            phase1Fields: ['chordDetail.chordTimeline'],
          },
        ],
      });

      const result = validatePhase2Consistency(phase1, phase2);
      const violations = result.violations.filter(
        v => v.type === 'LOW_CONFIDENCE_NOT_HEDGED',
      );
      expect(violations.length).toBeGreaterThan(0);
    });
  });

  describe('Salvage warnings (RECOMMENDATION_SALVAGED)', () => {
    it('emits an ERROR for each salvage warning code passed via diagnostics', () => {
      const phase1 = createBasePhase1();
      const phase2 = createBasePhase2({
        // Need at least one phase1Fields anywhere to make this new-shape,
        // though salvage check runs independent of the new-shape gate.
        abletonRecommendations: [
          {
            device: 'Operator',
            category: 'SYNTHESIS',
            parameter: 'Coarse',
            value: '1.00',
            reason: 'Matches tonal center.',
            phase1Fields: ['key'],
          },
        ],
      });
      const diagnostics = {
        warnings: [
          {
            code: 'DROPPED_INVALID_ARRAY_ITEM',
            path: 'abletonRecommendations[3]',
            message: 'workflowStage "EQ" is not valid',
          },
          {
            code: 'COERCED_TRACK_CONTEXT',
            path: 'mixAndMasterChain[1].trackContext',
            message: 'Return: Reverb → Return:Long Reverb',
          },
        ],
      };

      const result = validatePhase2Consistency(phase1, phase2, diagnostics);
      const salvaged = result.violations.filter(v => v.type === 'RECOMMENDATION_SALVAGED');
      expect(salvaged).toHaveLength(2);
      expect(salvaged.every(v => v.severity === 'ERROR')).toBe(true);
      expect(salvaged[0].phase2Value).toBe('DROPPED_INVALID_ARRAY_ITEM');
    });

    it('ignores unrelated warning codes', () => {
      const phase1 = createBasePhase1();
      const phase2 = createBasePhase2();
      const diagnostics = {
        warnings: [{ code: 'UNRELATED_INFO', path: 'foo', message: 'bar' }],
      };

      const result = validatePhase2Consistency(phase1, phase2, diagnostics);
      const salvaged = result.violations.filter(v => v.type === 'RECOMMENDATION_SALVAGED');
      expect(salvaged).toHaveLength(0);
    });

    it('does nothing when diagnostics is undefined', () => {
      const phase1 = createBasePhase1();
      const phase2 = createBasePhase2();
      const result = validatePhase2Consistency(phase1, phase2);
      const salvaged = result.violations.filter(v => v.type === 'RECOMMENDATION_SALVAGED');
      expect(salvaged).toHaveLength(0);
    });
  });

  describe('collectPhase1FieldPaths helper', () => {
    it('collects top-level scalar paths', () => {
      const phase1 = createBasePhase1();
      const paths = collectPhase1FieldPaths(phase1);
      expect(paths.has('bpm')).toBe(true);
      expect(paths.has('lufsIntegrated')).toBe(true);
      expect(paths.has('key')).toBe(true);
    });

    it('collects nested object scalar paths', () => {
      const phase1 = createBasePhase1();
      const paths = collectPhase1FieldPaths(phase1);
      expect(paths.has('spectralBalance')).toBe(true);
      expect(paths.has('spectralBalance.subBass')).toBe(true);
      expect(paths.has('spectralBalance.brilliance')).toBe(true);
      expect(paths.has('rhythmDetail.kickSwing')).toBe(true);
      expect(paths.has('synthesisCharacter.inharmonicity')).toBe(true);
    });

    it('omits paths whose value is null or undefined', () => {
      const phase1 = createBasePhase1({ key: null });
      const paths = collectPhase1FieldPaths(phase1);
      expect(paths.has('key')).toBe(false);
      // Adjacent non-null paths should still be present.
      expect(paths.has('bpm')).toBe(true);
    });

    it('surfaces array-of-object field names so citations like noveltyPeaks.time are valid', () => {
      const phase1 = createBasePhase1({
        arrangementDetail: {
          noveltyCurve: [0.1, 0.2, 0.3],
          noveltyPeaks: [{ time: 12.4, strength: 0.81 }],
          noveltyMean: 0.18,
          noveltyStdDev: 0.05,
        },
      } as Partial<Phase1Result>);
      const paths = collectPhase1FieldPaths(phase1);
      expect(paths.has('arrangementDetail')).toBe(true);
      expect(paths.has('arrangementDetail.noveltyCurve')).toBe(true);
      expect(paths.has('arrangementDetail.noveltyPeaks')).toBe(true);
      expect(paths.has('arrangementDetail.noveltyPeaks.time')).toBe(true);
      expect(paths.has('arrangementDetail.noveltyPeaks.strength')).toBe(true);
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

describe('Loudness action presence (objective safety net)', () => {
  // The check runs only on "new shape" Phase 2 (recommendations expose
  // phase1Fields); these helpers guarantee that shape with valid citations that
  // do NOT touch the loudness family, so the only variable under test is the
  // presence/absence of a true-peak / clipping recommendation.
  const newShapePhase2 = (overrides: Partial<Phase2Result> = {}): Phase2Result =>
    createBasePhase2({
      mixAndMasterChain: [
        {
          order: 1, device: 'EQ Eight', parameter: 'Low Cut', value: '30 Hz',
          reason: 'Removes rumble', phase1Fields: ['spectralBalance'],
        },
      ],
      abletonRecommendations: [
        {
          device: 'Operator', category: 'SYNTHESIS', parameter: 'Coarse', value: '1.00',
          reason: 'Matches tonal center', phase1Fields: ['bpm'],
        },
      ],
      ...overrides,
    });

  const clippingPhase1 = () =>
    createBasePhase1({
      truePeak: 0.9,
      saturationDetail: { clippedSampleCount: 1280, clippedSamplePercent: 0.4 } as any,
    });

  const loudnessViolations = (result: ValidationReport) =>
    result.violations.filter(v => v.type === 'MISSING_LOUDNESS_ACTION');

  it('warns when clipping is measured but no recommendation cites the loudness family', () => {
    const result = validatePhase2Consistency(clippingPhase1(), newShapePhase2());
    const loudness = loudnessViolations(result);
    expect(loudness).toHaveLength(1);
    expect(loudness[0].severity).toBe('WARNING');
    expect(loudness[0].field).toContain('saturationDetail.clippedSampleCount');
  });

  it('does not warn when a recommendation cites the clipping measurement', () => {
    const phase2 = newShapePhase2({
      mixAndMasterChain: [
        {
          order: 1, device: 'Limiter', parameter: 'Ceiling', value: '-0.3 dB',
          reason: 'Tame clipping', phase1Fields: ['saturationDetail.clippedSampleCount'],
        },
      ],
    });
    expect(loudnessViolations(validatePhase2Consistency(clippingPhase1(), phase2))).toHaveLength(0);
  });

  it('does not warn when a recommendation cites truePeak for an over', () => {
    const phase1 = createBasePhase1({ truePeak: 1.2 });
    const phase2 = newShapePhase2({
      abletonRecommendations: [
        {
          device: 'Limiter', category: 'MASTERING', parameter: 'Ceiling', value: '-0.3 dB',
          reason: 'Restore inter-sample headroom', phase1Fields: ['truePeak'],
        },
      ],
    });
    expect(loudnessViolations(validatePhase2Consistency(phase1, phase2))).toHaveLength(0);
  });

  it('warns on an unaddressed true-peak over (linear > 1.0)', () => {
    const result = validatePhase2Consistency(createBasePhase1({ truePeak: 1.1 }), newShapePhase2());
    const loudness = loudnessViolations(result);
    expect(loudness).toHaveLength(1);
    expect(loudness[0].field).toContain('truePeak');
  });

  it('does not warn for a clean master (no clipping, peak below full scale)', () => {
    const phase1 = createBasePhase1({
      truePeak: 0.8,
      saturationDetail: { clippedSampleCount: 0, clippedSamplePercent: 0 } as any,
    });
    expect(loudnessViolations(validatePhase2Consistency(phase1, newShapePhase2()))).toHaveLength(0);
  });

  it('emits a WARNING, never an ERROR — an unaddressed defect does not fail the gate alone', () => {
    const result = validatePhase2Consistency(clippingPhase1(), newShapePhase2());
    expect(loudnessViolations(result).every(v => v.severity === 'WARNING')).toBe(true);
  });

  it('skips the check for legacy-shape Phase 2 (no phase1Fields anywhere)', () => {
    // createBasePhase2() carries no phase1Fields, so isNewShapePhase2() is false.
    const result = validatePhase2Consistency(clippingPhase1(), createBasePhase2());
    expect(loudnessViolations(result)).toHaveLength(0);
  });
});

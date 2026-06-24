import { describe, it, expect } from 'vitest';
import {
  normKey,
  buildContractValidatedKeys,
  isCardValidated,
  formatContractValue,
  projectContractRows,
} from '../../src/services/recommendationsContract';
import type {
  RecommendationsContract,
  RecommendationContractEntry,
} from '../../src/types/interpretation';
import type { Phase1Result } from '../../src/types';

const entry = (
  over: Partial<RecommendationContractEntry>,
): RecommendationContractEntry => ({
  device: 'Glue Compressor',
  parameter: 'Ratio',
  value: '4:1',
  unit: null,
  range: null,
  cited_measurements: ['lufsIntegrated'],
  ...over,
});

const contract = (
  entries: RecommendationContractEntry[],
): RecommendationsContract => ({ version: 'recommendations.v1', recommendations: entries });

describe('normKey', () => {
  it('lowercases and trims both device and parameter', () => {
    expect(normKey('  Glue Compressor ', ' Ratio')).toBe('glue compressor|ratio');
    expect(normKey('OPERATOR', 'Output Gain')).toBe('operator|output gain');
  });

  it('matches across case/whitespace drift on either side', () => {
    expect(normKey('Operator', 'gain')).toBe(normKey('  operator', 'GAIN '));
  });
});

describe('buildContractValidatedKeys', () => {
  it('returns an empty set for an absent or malformed contract', () => {
    expect(buildContractValidatedKeys(undefined).size).toBe(0);
    expect(
      buildContractValidatedKeys({ version: 'recommendations.v1' } as RecommendationsContract).size,
    ).toBe(0);
  });

  it('indexes every entry by normalized device|parameter', () => {
    const keys = buildContractValidatedKeys(
      contract([entry({ device: 'Operator', parameter: 'gain' }), entry({})]),
    );
    expect(keys.has('operator|gain')).toBe(true);
    expect(keys.has('glue compressor|ratio')).toBe(true);
    expect(keys.size).toBe(2);
  });
});

describe('isCardValidated', () => {
  const keys = buildContractValidatedKeys(
    contract([entry({ device: 'Operator', parameter: 'gain' })]),
  );

  it('marks a 1:1 mix card whose cited item is on the contract', () => {
    expect(
      isCardValidated(keys, [{ device: 'Operator', parameter: 'gain', phase1Fields: ['lufsIntegrated'] }]),
    ).toBe(true);
  });

  it('does not mark a card with no citation-eligible items (synthetic / uncited)', () => {
    expect(isCardValidated(keys, [{ device: 'Operator', parameter: 'gain' }])).toBe(false);
    expect(isCardValidated(keys, [{ device: 'Operator', parameter: 'gain', phase1Fields: [] }])).toBe(false);
    expect(isCardValidated(keys, [])).toBe(false);
  });

  it('requires ALL eligible merged items to be on the contract (patch merge)', () => {
    const merged = [
      { device: 'Operator', parameter: 'gain', phase1Fields: ['lufsIntegrated'] },
      { device: 'Operator', parameter: 'detune', phase1Fields: ['key'] }, // eligible but NOT in contract
    ];
    expect(isCardValidated(keys, merged)).toBe(false);
  });

  it('ignores uncited siblings when the cited ones all match', () => {
    const merged = [
      { device: 'Operator', parameter: 'gain', phase1Fields: ['lufsIntegrated'] }, // eligible + matched
      { device: 'Operator', parameter: 'detune' }, // uncited → ignored
    ];
    expect(isCardValidated(keys, merged)).toBe(true);
  });

  // Round-2 blocker B1 regression guard: the match must key on the RAW Phase 2
  // parameter, never the normalizeParameterLabel-rewritten one. The backend
  // stores "gain"; a UI lookup built from "Output Gain" must NOT match.
  it('matches the raw parameter and NOT the normalizeParameterLabel rewrite', () => {
    expect(
      isCardValidated(keys, [{ device: 'Operator', parameter: 'gain', phase1Fields: ['lufsIntegrated'] }]),
    ).toBe(true);
    expect(
      isCardValidated(keys, [{ device: 'Operator', parameter: 'Output Gain', phase1Fields: ['lufsIntegrated'] }]),
    ).toBe(false);
  });
});

describe('formatContractValue', () => {
  it('passes non-numeric values through unchanged', () => {
    expect(formatContractValue(entry({ value: 'Sine', unit: null, range: null }))).toBe('Sine');
    expect(formatContractValue(entry({ value: '4:1', unit: null, range: null }))).toBe('4:1');
  });

  it('appends unit and range for numeric values', () => {
    expect(formatContractValue(entry({ value: 10, unit: 'ms', range: [7, 13] }))).toBe('10 ms (7–13)');
    expect(formatContractValue(entry({ value: -1.5, unit: 'dB', range: null }))).toBe('-1.5 dB');
    expect(formatContractValue(entry({ value: 4, unit: null, range: null }))).toBe('4');
  });
});

describe('projectContractRows', () => {
  const phase1 = { lufsIntegrated: -8.4 } as unknown as Phase1Result;

  it('returns [] for an absent contract', () => {
    expect(projectContractRows(undefined, phase1)).toEqual([]);
  });

  it('resolves a citation that exists in Phase 1 to a labeled value', () => {
    const [row] = projectContractRows(
      contract([entry({ device: 'Limiter', parameter: 'Ceiling', cited_measurements: ['lufsIntegrated'] })]),
      phase1,
    );
    expect(row.device).toBe('Limiter');
    expect(row.citations).toHaveLength(1);
    // Humanized "lufsIntegrated" label + resolved value, not the bare path.
    expect(row.citations[0]).not.toBe('lufsIntegrated');
    expect(row.citations[0].toLowerCase()).toContain('lufs');
  });

  it('falls back to the raw path when a citation does not resolve (cell never blank)', () => {
    const [row] = projectContractRows(
      contract([entry({ cited_measurements: ['nonexistent.deep.path'] })]),
      phase1,
    );
    expect(row.citations[0]).toBe('nonexistent.deep.path');
  });
});

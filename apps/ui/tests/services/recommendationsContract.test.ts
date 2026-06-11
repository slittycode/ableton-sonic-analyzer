import {
  buildRecommendationsContractIndex,
  findContractEntries,
  formatContractRange,
  formatContractValue,
  parseRecommendationValue,
} from '../../src/services/recommendationsContract';
import { RecommendationContractEntry, RecommendationsContract } from '../../src/types';

function entry(partial: Partial<RecommendationContractEntry>): RecommendationContractEntry {
  return {
    device: 'EQ Eight',
    parameter: 'Low Cut',
    value: 30,
    unit: 'Hz',
    range: [24, 36],
    cited_measurements: ['spectralBalance.subBass'],
    ...partial,
  };
}

function contract(entries: RecommendationContractEntry[]): RecommendationsContract {
  return { version: 'recommendations.v1', recommendations: entries };
}

describe('parseRecommendationValue', () => {
  // Mirror of apps/backend/recommendations_contract.py parse_value — the
  // case table below matches the backend's documented examples so a drift
  // in either side surfaces here.
  it('parses the backend parser case table identically', () => {
    expect(parseRecommendationValue('4 kHz')).toEqual({ number: 4000, unit: 'hz' });
    expect(parseRecommendationValue('-15 dB')).toEqual({ number: -15, unit: 'db' });
    expect(parseRecommendationValue('200 ms')).toEqual({ number: 200, unit: 'ms' });
    expect(parseRecommendationValue('3:1')).toEqual({ number: 3, unit: 'ratio' });
    expect(parseRecommendationValue('30%')).toEqual({ number: 30, unit: 'pct' });
    expect(parseRecommendationValue('0.6')).toEqual({ number: 0.6, unit: '' });
    expect(parseRecommendationValue('+12st')).toEqual({ number: 12, unit: 'st' });
    expect(parseRecommendationValue('2 semitones')).toEqual({ number: 2, unit: 'st' });
    expect(parseRecommendationValue('1.5 s')).toEqual({ number: 1.5, unit: 's' });
  });

  it('returns null for non-numeric, empty, and missing values', () => {
    expect(parseRecommendationValue('Sine')).toBeNull();
    expect(parseRecommendationValue('')).toBeNull();
    expect(parseRecommendationValue('   ')).toBeNull();
    expect(parseRecommendationValue(null)).toBeNull();
    expect(parseRecommendationValue(undefined)).toBeNull();
  });

  it('passes through finite numbers as unitless', () => {
    expect(parseRecommendationValue(0.5)).toEqual({ number: 0.5, unit: '' });
    expect(parseRecommendationValue(Number.NaN)).toBeNull();
  });
});

describe('buildRecommendationsContractIndex + findContractEntries', () => {
  it('pairs a raw card with its contract entry across the value normalization boundary', () => {
    // Raw card says "4 kHz"; the contract normalized it to {4000, "Hz"}.
    const index = buildRecommendationsContractIndex(
      contract([entry({ device: 'Auto Filter', parameter: 'Cutoff', value: 4000, unit: 'Hz', range: [3200, 4800] })]),
    );

    const matches = findContractEntries(index, {
      device: 'Auto Filter',
      parameter: 'Cutoff',
      value: '4 kHz',
    });
    expect(matches).toHaveLength(1);
    expect(matches[0].value).toBe(4000);
  });

  it('is case- and whitespace-insensitive on device and parameter', () => {
    const index = buildRecommendationsContractIndex(contract([entry({})]));

    expect(
      findContractEntries(index, { device: '  eq eight ', parameter: 'LOW CUT', value: '30 Hz' }),
    ).toHaveLength(1);
  });

  it('disambiguates duplicate device+parameter pairs by value', () => {
    // Same device+parameter twice with different values (e.g. one in
    // mixAndMasterChain, one in abletonRecommendations). Pairing must be
    // value-aware or the wrong working range would render — the
    // confidently-wrong failure mode this surface exists to prevent.
    const lowCut30 = entry({ value: 30, range: [27, 33] });
    const lowCut100 = entry({ value: 100, range: [97, 103] });
    const index = buildRecommendationsContractIndex(contract([lowCut30, lowCut100]));

    const matches = findContractEntries(index, {
      device: 'EQ Eight',
      parameter: 'Low Cut',
      value: '100 Hz',
    });
    expect(matches).toEqual([lowCut100]);
  });

  it('matches non-numeric values as strings', () => {
    const sine = entry({ device: 'Operator', parameter: 'Waveform', value: 'Sine', unit: null, range: null });
    const index = buildRecommendationsContractIndex(contract([sine]));

    expect(
      findContractEntries(index, { device: 'Operator', parameter: 'Waveform', value: 'sine' }),
    ).toEqual([sine]);
  });

  it('returns no entries for uncited cards (absent from the envelope) and for absent envelopes', () => {
    const index = buildRecommendationsContractIndex(contract([entry({})]));
    expect(
      findContractEntries(index, { device: 'Glue Compressor', parameter: 'Ratio', value: '2:1' }),
    ).toEqual([]);

    const emptyIndex = buildRecommendationsContractIndex(undefined);
    expect(
      findContractEntries(emptyIndex, { device: 'EQ Eight', parameter: 'Low Cut', value: '30 Hz' }),
    ).toEqual([]);
  });
});

describe('formatContractValue + formatContractRange', () => {
  it('formats numeric entries with their display unit', () => {
    expect(formatContractValue(entry({ value: 30, unit: 'Hz' }))).toBe('30 Hz');
    expect(formatContractValue(entry({ value: 0.6, unit: null }))).toBe('0.6');
    expect(formatContractValue(entry({ value: 'Sine', unit: null }))).toBe('Sine');
  });

  it('formats ranges and returns null when the contract published none', () => {
    expect(formatContractRange(entry({ value: 30, unit: 'Hz', range: [24, 36] }))).toBe('24–36 Hz');
    expect(formatContractRange(entry({ value: 3, unit: 'ratio', range: [2, 4] }))).toBe('2–4 ratio');
    expect(formatContractRange(entry({ value: 'Sine', unit: null, range: null }))).toBeNull();
  });

  it('strips float noise from kHz-multiplied magnitudes', () => {
    // 4.7 kHz parses to 4.7 * 1000 on both sides; display must not leak
    // IEEE754 artifacts like "4700.000000000001".
    expect(formatContractValue(entry({ value: 4.7 * 1000, unit: 'Hz' }))).toBe('4700 Hz');
  });
});

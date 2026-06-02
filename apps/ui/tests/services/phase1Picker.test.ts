/**
 * Locks in the pure-function Phase 1 picker that the CitationBlock primitive
 * (audit Finding #2) uses to resolve dotted field paths to measured values,
 * format them, and compute worst-confidence bands.
 */
import { describe, expect, it } from 'vitest';
import {
  pickPhase1Value,
  formatCitedValue,
  pickPhase1Confidence,
  pickWorstConfidence,
} from '../../src/services/phase1Picker';
import type { Phase1Result } from '../../src/types';

// Minimal Phase1 shape sufficient for picker tests. The picker walks `unknown`
// paths via property access, so the strict shape is forgiving as long as the
// nested objects exist where the paths claim to read.
const phase1 = {
  bpm: 156.6,
  bpmConfidence: 0.86,
  key: 'F minor',
  keyConfidence: 0.62,
  timeSignature: '4/4',
  durationSeconds: 126.4,
  lufsIntegrated: -9.3,
  truePeak: -0.2,
  crestFactor: 11.6,
  stereoWidth: 0.42,
  stereoCorrelation: 0.84,
  spectralBalance: {
    subBass: -0.7,
    lowBass: 1.2,
    highs: 1.05,
  },
  kickDetail: {
    fundamentalHz: 64.3,
    crestFactor: 8.2,
    thd: 0.29,
  },
  sidechainDetail: {
    pumpingRate: 4,
    pumpingStrength: 0.71,
    pumpingConfidence: 0.42,
  },
  acidDetail: {
    isAcid: true,
    confidence: 0.78,
  },
  reverbDetail: {
    rt60: 2.04,
    confidence: 0.55,
  },
} as unknown as Phase1Result;

describe('pickPhase1Value', () => {
  it('reads top-level fields', () => {
    expect(pickPhase1Value(phase1, 'bpm')).toBe(156.6);
    expect(pickPhase1Value(phase1, 'key')).toBe('F minor');
    expect(pickPhase1Value(phase1, 'truePeak')).toBe(-0.2);
  });

  it('reads nested dotted paths', () => {
    expect(pickPhase1Value(phase1, 'spectralBalance.subBass')).toBe(-0.7);
    expect(pickPhase1Value(phase1, 'kickDetail.fundamentalHz')).toBe(64.3);
    expect(pickPhase1Value(phase1, 'sidechainDetail.pumpingStrength')).toBe(0.71);
  });

  it('returns undefined for missing intermediates or leaves', () => {
    expect(pickPhase1Value(phase1, 'doesNotExist')).toBeUndefined();
    expect(pickPhase1Value(phase1, 'spectralBalance.missing')).toBeUndefined();
    expect(pickPhase1Value(phase1, 'missing.further.deeper')).toBeUndefined();
  });

  it('is defensive against null / empty inputs', () => {
    expect(pickPhase1Value(null, 'bpm')).toBeUndefined();
    expect(pickPhase1Value(undefined, 'bpm')).toBeUndefined();
    expect(pickPhase1Value(phase1, '')).toBeUndefined();
  });
});

describe('formatCitedValue', () => {
  it('rounds BPM to integer with unit', () => {
    expect(formatCitedValue('bpm', 156.6)).toBe('157 BPM');
    expect(formatCitedValue('bpm', 174)).toBe('174 BPM');
    expect(formatCitedValue('bpmPercival', 86.1)).toBe('86 BPM');
  });

  it('formats spectral balance as signed dB', () => {
    expect(formatCitedValue('spectralBalance.subBass', -0.7)).toBe('-0.7 dB');
    expect(formatCitedValue('spectralBalance.highs', 1.05)).toBe('+1.1 dB');
    expect(formatCitedValue('spectralBalance.lowBass', 0)).toBe('+0.0 dB');
  });

  it('formats confidence fields as percent', () => {
    expect(formatCitedValue('bpmConfidence', 0.86)).toBe('86%');
    expect(formatCitedValue('keyConfidence', 0.62)).toBe('62%');
    expect(formatCitedValue('sidechainDetail.pumpingConfidence', 0.42)).toBe('42%');
    expect(formatCitedValue('sidechainDetail.pumpingStrength', 0.71)).toBe('71%');
    expect(formatCitedValue('chordDetail.chordStrength', 0.62)).toBe('62%');
  });

  it('formats LUFS', () => {
    expect(formatCitedValue('lufsIntegrated', -9.3)).toBe('-9.3 LUFS');
    expect(formatCitedValue('lufsRange', 5.2)).toBe('5.2 LUFS');
  });

  it('formats Hz fields as integer + Hz', () => {
    expect(formatCitedValue('kickDetail.fundamentalHz', 64.3)).toBe('64 Hz');
  });

  it('formats seconds fields with 2 decimals', () => {
    expect(formatCitedValue('reverbDetail.rt60', 2.04)).toBe('2.04s');
    expect(formatCitedValue('kickDetail.meanDecaySeconds', 0.066)).toBe('0.07s');
    expect(formatCitedValue('durationSeconds', 126.4)).toBe('126.40s');
  });

  it('formats dB-family paths', () => {
    expect(formatCitedValue('truePeak', -0.2)).toBe('-0.2 dBTP');
    expect(formatCitedValue('crestFactor', 11.6)).toBe('11.6 dB');
  });

  it('formats stereo correlation/width as bare decimal', () => {
    expect(formatCitedValue('stereoWidth', 0.42)).toBe('0.42');
    expect(formatCitedValue('stereoCorrelation', 0.84)).toBe('0.84');
  });

  it('formats booleans as yes/no', () => {
    expect(formatCitedValue('acidDetail.isAcid', true)).toBe('yes');
    expect(formatCitedValue('vocalDetail.hasVocals', false)).toBe('no');
  });

  it('passes strings through unchanged', () => {
    expect(formatCitedValue('key', 'F minor')).toBe('F minor');
    expect(formatCitedValue('timeSignature', '4/4')).toBe('4/4');
  });

  it('returns empty string for null/undefined', () => {
    expect(formatCitedValue('bpm', null)).toBe('');
    expect(formatCitedValue('bpm', undefined)).toBe('');
  });
});

describe('pickPhase1Confidence', () => {
  it('finds the paired confidence for top-level fields', () => {
    expect(pickPhase1Confidence(phase1, 'bpm')).toBe(0.86);
    expect(pickPhase1Confidence(phase1, 'key')).toBe(0.62);
  });

  it('finds confidence via prefix-match when full path is not in the map', () => {
    // sidechainDetail.pumpingRate is mapped → sidechainDetail.pumpingConfidence
    expect(pickPhase1Confidence(phase1, 'sidechainDetail.pumpingRate')).toBe(0.42);
    // acidDetail is mapped at the prefix; isAcid leaf goes through prefix-match.
    expect(pickPhase1Confidence(phase1, 'acidDetail.isAcid')).toBe(0.78);
  });

  it('returns null when no confidence sibling exists', () => {
    expect(pickPhase1Confidence(phase1, 'spectralBalance.subBass')).toBeNull();
    expect(pickPhase1Confidence(phase1, 'truePeak')).toBeNull();
  });

  it('is defensive against null / empty', () => {
    expect(pickPhase1Confidence(null, 'bpm')).toBeNull();
    expect(pickPhase1Confidence(phase1, '')).toBeNull();
  });
});

describe('pickWorstConfidence', () => {
  it('returns the minimum confidence across paths that have siblings', () => {
    // bpm=0.86, key=0.62 → worst is 0.62.
    expect(pickWorstConfidence(phase1, ['bpm', 'key'])).toBe(0.62);
  });

  it('ignores paths without confidence siblings', () => {
    // bpm=0.86 has a sibling; truePeak doesn't.
    expect(pickWorstConfidence(phase1, ['bpm', 'truePeak'])).toBe(0.86);
  });

  it('returns null when no path has a confidence sibling', () => {
    expect(pickWorstConfidence(phase1, ['truePeak', 'spectralBalance.subBass'])).toBeNull();
  });

  it('returns null for empty paths array', () => {
    expect(pickWorstConfidence(phase1, [])).toBeNull();
  });

  it('returns null when phase1 is null', () => {
    expect(pickWorstConfidence(null, ['bpm'])).toBeNull();
  });

  it('handles a mix of nested + top-level paths', () => {
    // sidechainDetail.pumpingRate → pumpingConfidence=0.42 (worst)
    // bpm → bpmConfidence=0.86
    // key → keyConfidence=0.62
    expect(
      pickWorstConfidence(phase1, ['bpm', 'sidechainDetail.pumpingRate', 'key']),
    ).toBe(0.42);
  });
});

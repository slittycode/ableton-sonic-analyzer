import { describe, it, expect } from 'vitest';
import {
  TRUE_PEAK_OVER_DBTP,
  citationAddressesLoudnessDefect,
  loudnessDefectsDemandingAction,
} from '../../src/services/loudnessGuardrails';
import type { Phase1Result } from '../../src/types';

// Minimal Phase1Result — only the fields the predicate reads matter; the rest
// are irrelevant to loudness defect detection. Default truePeak is a normal
// mastered peak below full scale (negative dBTP).
const phase1 = (overrides: Partial<Phase1Result>): Phase1Result =>
  ({ truePeak: -1.0, ...overrides }) as Phase1Result;

describe('loudnessDefectsDemandingAction', () => {
  it('returns no defects for a clean master (no clipping, peak below full scale)', () => {
    const result = loudnessDefectsDemandingAction(
      phase1({ truePeak: -1.0, saturationDetail: { clippedSampleCount: 0 } as any }),
    );
    expect(result).toEqual([]);
  });

  it('flags CLIPPING when clippedSampleCount > 0', () => {
    const result = loudnessDefectsDemandingAction(
      phase1({ truePeak: -1.0, saturationDetail: { clippedSampleCount: 1280 } as any }),
    );
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      kind: 'CLIPPING',
      field: 'saturationDetail.clippedSampleCount',
      value: 1280,
    });
  });

  it('flags TRUE_PEAK_OVER when truePeak exceeds full scale (dBTP > 0)', () => {
    const result = loudnessDefectsDemandingAction(phase1({ truePeak: 1.1 }));
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({ kind: 'TRUE_PEAK_OVER', field: 'truePeak', value: 1.1 });
  });

  it('does not flag a true peak exactly at full scale (0.0 dBTP is the boundary, not an over)', () => {
    const result = loudnessDefectsDemandingAction(phase1({ truePeak: TRUE_PEAK_OVER_DBTP }));
    expect(result).toEqual([]);
  });

  it('flags both defects independently when clipping and an over coexist', () => {
    const result = loudnessDefectsDemandingAction(
      phase1({ truePeak: 1.2, saturationDetail: { clippedSampleCount: 5 } as any }),
    );
    expect(result.map(d => d.kind).sort()).toEqual(['CLIPPING', 'TRUE_PEAK_OVER']);
  });

  it('treats truePeak as dBTP, so a normal master below full scale (negative dBTP) is not an over', () => {
    // Guards the unit contract: truePeak is dBTP (Phase 1 v2). -0.2 dBTP is below
    // full scale, so it is not an inter-sample over.
    const result = loudnessDefectsDemandingAction(phase1({ truePeak: -0.2 }));
    expect(result).toEqual([]);
  });

  it('ignores missing / null / non-finite values without throwing', () => {
    expect(loudnessDefectsDemandingAction(phase1({ truePeak: null as any }))).toEqual([]);
    expect(
      loudnessDefectsDemandingAction(
        phase1({ truePeak: -1.0, saturationDetail: null as any }),
      ),
    ).toEqual([]);
    expect(loudnessDefectsDemandingAction(phase1({ truePeak: NaN }))).toEqual([]);
  });
});

describe('citationAddressesLoudnessDefect', () => {
  it('accepts truePeak and the saturationDetail family', () => {
    expect(citationAddressesLoudnessDefect('truePeak')).toBe(true);
    expect(citationAddressesLoudnessDefect('saturationDetail')).toBe(true);
    expect(citationAddressesLoudnessDefect('saturationDetail.clippedSampleCount')).toBe(true);
    expect(citationAddressesLoudnessDefect('saturationDetail.clippedSamplePercent')).toBe(true);
    expect(citationAddressesLoudnessDefect('  truePeak  ')).toBe(true);
  });

  it('rejects unrelated measurement paths', () => {
    expect(citationAddressesLoudnessDefect('lufsIntegrated')).toBe(false);
    expect(citationAddressesLoudnessDefect('bpm')).toBe(false);
    expect(citationAddressesLoudnessDefect('spectralBalance.subBass')).toBe(false);
    expect(citationAddressesLoudnessDefect('truePeakiness')).toBe(false);
  });
});

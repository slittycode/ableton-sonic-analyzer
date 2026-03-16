import { describe, expect, it } from 'vitest';

import { isSpectrumActive, nextPeakValue } from '../../src/components/waveformPlayerUtils';

describe('waveformPlayerUtils', () => {
  it('treats seeking as an active spectrum state even when playback is paused', () => {
    expect(isSpectrumActive(false, true)).toBe(true);
    expect(isSpectrumActive(true, false)).toBe(true);
    expect(isSpectrumActive(false, false)).toBe(false);
  });

  it('holds higher peak values and decays lower ones without going negative', () => {
    expect(nextPeakValue(80, 120, 2)).toBe(120);
    expect(nextPeakValue(80, 60, 2)).toBe(78);
    expect(nextPeakValue(1, 0, 2)).toBe(0);
  });
});

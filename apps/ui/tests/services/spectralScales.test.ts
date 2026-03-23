import { describe, expect, it } from 'vitest';
import {
  formatFrequency,
  pixelToFreqCQT,
  pixelToFreqLinear,
  pixelToFreqMel,
  pixelToTime,
} from '../../src/utils/spectralScales';

describe('pixelToFreqMel', () => {
  it('returns low frequency at bottom of image (y = imageHeight)', () => {
    const hz = pixelToFreqMel(128, 128);
    // Bottom = fmin = 0 Hz
    expect(hz).toBeCloseTo(0, 0);
  });

  it('returns high frequency at top of image (y = 0)', () => {
    const hz = pixelToFreqMel(0, 128);
    // Top = fmax = 22050 Hz
    expect(hz).toBeCloseTo(22050, -1);
  });

  it('returns mid-range frequency at y = imageHeight / 2', () => {
    const hz = pixelToFreqMel(64, 128);
    // Midpoint of mel scale should be around 3-4 kHz
    expect(hz).toBeGreaterThan(2000);
    expect(hz).toBeLessThan(6000);
  });

  it('returns 0 when imageHeight is 0', () => {
    expect(pixelToFreqMel(50, 0)).toBe(0);
  });
});

describe('pixelToFreqCQT', () => {
  it('returns fmin at bottom of image', () => {
    const hz = pixelToFreqCQT(128, 128);
    // Bottom = bin 0 = fmin = 32.703 Hz
    expect(hz).toBeCloseTo(32.703, 1);
  });

  it('returns high frequency at top of image', () => {
    const hz = pixelToFreqCQT(0, 128);
    // Top = bin 84, 7 octaves above C1 = 32.703 * 2^7 ≈ 4185.6
    expect(hz).toBeGreaterThan(4000);
    expect(hz).toBeLessThan(4500);
  });

  it('doubles frequency for each octave (12 bins)', () => {
    const nBins = 84;
    const h = 256;
    // One octave = 12 bins out of 84 total
    const fracLow = (84 - 12) / 84; // fraction from top for bin 12
    const hzLow = pixelToFreqCQT(fracLow * h, h, nBins);
    const fracHigh = (84 - 24) / 84;
    const hzHigh = pixelToFreqCQT(fracHigh * h, h, nBins);
    // One octave higher should be roughly 2x
    expect(hzHigh / hzLow).toBeCloseTo(2, 1);
  });

  it('returns 0 when imageHeight is 0', () => {
    expect(pixelToFreqCQT(50, 0)).toBe(0);
  });
});

describe('pixelToFreqLinear', () => {
  it('returns 0 Hz at bottom of image', () => {
    expect(pixelToFreqLinear(256, 256)).toBeCloseTo(0, 0);
  });

  it('returns sr/2 at top of image', () => {
    expect(pixelToFreqLinear(0, 256)).toBeCloseTo(22050, 0);
  });

  it('returns mid frequency at midpoint', () => {
    expect(pixelToFreqLinear(128, 256)).toBeCloseTo(11025, 0);
  });

  it('respects custom sample rate', () => {
    expect(pixelToFreqLinear(0, 256, 48000)).toBeCloseTo(24000, 0);
  });
});

describe('pixelToTime', () => {
  it('returns 0 at left edge', () => {
    expect(pixelToTime(0, 800, 120)).toBe(0);
  });

  it('returns duration at right edge', () => {
    expect(pixelToTime(800, 800, 120)).toBeCloseTo(120, 1);
  });

  it('returns proportional time at midpoint', () => {
    expect(pixelToTime(400, 800, 120)).toBeCloseTo(60, 1);
  });

  it('returns 0 when imageWidth is 0', () => {
    expect(pixelToTime(100, 0, 120)).toBe(0);
  });
});

describe('formatFrequency', () => {
  it('formats sub-kHz as integer Hz', () => {
    expect(formatFrequency(440)).toBe('440 Hz');
  });

  it('formats kHz with one decimal', () => {
    expect(formatFrequency(2400)).toBe('2.4 kHz');
  });

  it('formats exactly 1000 Hz as kHz', () => {
    expect(formatFrequency(1000)).toBe('1.0 kHz');
  });

  it('rounds sub-kHz values', () => {
    expect(formatFrequency(99.7)).toBe('100 Hz');
  });
});

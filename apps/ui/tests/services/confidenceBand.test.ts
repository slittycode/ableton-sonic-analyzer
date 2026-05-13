import { describe, expect, it } from 'vitest';

import {
  formatBandPillLabel,
  getConfidenceBand,
} from '../../src/services/sessionMusician/confidenceBand';

describe('getConfidenceBand', () => {
  it('returns unreliable for 0.0', () => {
    expect(getConfidenceBand(0).id).toBe('unreliable');
  });

  it('returns unreliable just below the rough threshold (0.249)', () => {
    expect(getConfidenceBand(0.249).id).toBe('unreliable');
  });

  it('returns rough at the inclusive 0.25 threshold', () => {
    expect(getConfidenceBand(0.25).id).toBe('rough');
  });

  it('returns rough just below the workable threshold (0.499)', () => {
    expect(getConfidenceBand(0.499).id).toBe('rough');
  });

  it('returns workable at the inclusive 0.50 threshold', () => {
    expect(getConfidenceBand(0.5).id).toBe('workable');
  });

  it('returns workable just below the solid threshold (0.799)', () => {
    expect(getConfidenceBand(0.799).id).toBe('workable');
  });

  it('returns solid at the inclusive 0.80 threshold', () => {
    expect(getConfidenceBand(0.8).id).toBe('solid');
  });

  it('returns solid for 1.0', () => {
    expect(getConfidenceBand(1).id).toBe('solid');
  });

  it('treats NaN as unreliable rather than throwing', () => {
    expect(getConfidenceBand(Number.NaN).id).toBe('unreliable');
  });

  it('returns the producer-facing label for the solid band', () => {
    const band = getConfidenceBand(0.9);
    expect(band.label).toBe('Solid scaffold');
    expect(band.copy).toContain('reliable');
  });

  it('returns the producer-facing label for the workable band', () => {
    const band = getConfidenceBand(0.6);
    expect(band.label).toBe('Workable draft');
    expect(band.copy).toContain('right ballpark');
  });

  it('returns the producer-facing label for the rough band', () => {
    const band = getConfidenceBand(0.3);
    expect(band.label).toBe('Rough sketch');
    expect(band.copy).toContain('rhythm grid');
  });

  it('returns the producer-facing label for the unreliable band', () => {
    const band = getConfidenceBand(0.1);
    expect(band.label).toBe('Unreliable');
    expect(band.copy).toContain('scale hints');
  });
});

describe('formatBandPillLabel', () => {
  it('joins label and integer percent with a middle dot', () => {
    const band = getConfidenceBand(0.72);
    expect(formatBandPillLabel(band, 0.72)).toBe('Workable draft · 72%');
  });

  it('rounds the percent to the nearest integer', () => {
    const band = getConfidenceBand(0.876);
    expect(formatBandPillLabel(band, 0.876)).toBe('Solid scaffold · 88%');
  });

  it('clamps confidence values above 1 to 100%', () => {
    const band = getConfidenceBand(0.9);
    expect(formatBandPillLabel(band, 1.5)).toBe('Solid scaffold · 100%');
  });

  it('clamps negative confidence values to 0%', () => {
    const band = getConfidenceBand(0);
    expect(formatBandPillLabel(band, -0.4)).toBe('Unreliable · 0%');
  });

  it('treats NaN as 0%', () => {
    const band = getConfidenceBand(0);
    expect(formatBandPillLabel(band, Number.NaN)).toBe('Unreliable · 0%');
  });
});

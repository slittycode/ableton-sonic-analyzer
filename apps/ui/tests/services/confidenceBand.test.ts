import { describe, expect, it } from 'vitest';

import {
  formatBandPillLabel,
  getConfidenceBand,
  toConfidenceBand,
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

// Audit Finding #4: `toConfidenceBand` is the normalizer that lets every
// confidence-rendering site (Detected Characteristics HIGH/MED/LOW pills,
// Confidence Notes High/Moderate/Low chips, Key/Character/Tempo CONF and
// SCORE displays) route through the same four-band ladder. It accepts
// numeric 0-1, numeric 0-100, the string enums emitted by Gemini, and
// percent strings like "62%". Returns null for unparseable input so
// callers can choose a fallback instead of rendering a misleading band.
describe('toConfidenceBand', () => {
  it('returns null for null/undefined/empty string', () => {
    expect(toConfidenceBand(null)).toBeNull();
    expect(toConfidenceBand(undefined)).toBeNull();
    expect(toConfidenceBand('')).toBeNull();
    expect(toConfidenceBand('   ')).toBeNull();
  });

  it('maps 0-1 floats via getConfidenceBand at the band boundaries', () => {
    expect(toConfidenceBand(0.25)?.id).toBe('rough');
    expect(toConfidenceBand(0.5)?.id).toBe('workable');
    expect(toConfidenceBand(0.8)?.id).toBe('solid');
    expect(toConfidenceBand(0.249)?.id).toBe('unreliable');
  });

  it('maps 0-100 integers by dividing', () => {
    expect(toConfidenceBand(95)?.id).toBe('solid');
    expect(toConfidenceBand(62)?.id).toBe('workable');
    expect(toConfidenceBand(30)?.id).toBe('rough');
    expect(toConfidenceBand(10)?.id).toBe('unreliable');
  });

  it('maps HIGH/High/high to the solid band (0.9 mid-band)', () => {
    expect(toConfidenceBand('HIGH')?.id).toBe('solid');
    expect(toConfidenceBand('High')?.id).toBe('solid');
    expect(toConfidenceBand('high')?.id).toBe('solid');
    // 0.9 → 90% — solidly inside the band so the pill reads as an honest hedge.
    const band = toConfidenceBand('HIGH');
    expect(band && formatBandPillLabel(band, 0.9)).toBe('Solid scaffold · 90%');
  });

  it('maps MED/Medium/Moderate/moderate to the workable band (0.6 mid-band)', () => {
    expect(toConfidenceBand('MED')?.id).toBe('workable');
    expect(toConfidenceBand('Medium')?.id).toBe('workable');
    expect(toConfidenceBand('Moderate')?.id).toBe('workable');
    expect(toConfidenceBand('moderate')?.id).toBe('workable');
    expect(toConfidenceBand('medium')?.id).toBe('workable');
  });

  it('maps LOW/Low/low to the rough band (0.3 mid-band)', () => {
    expect(toConfidenceBand('LOW')?.id).toBe('rough');
    expect(toConfidenceBand('Low')?.id).toBe('rough');
    expect(toConfidenceBand('low')?.id).toBe('rough');
  });

  it('parses percent strings to the matching band', () => {
    expect(toConfidenceBand('62%')?.id).toBe('workable');
    expect(toConfidenceBand('30%')?.id).toBe('rough');
    expect(toConfidenceBand('95%')?.id).toBe('solid');
    // Also accepts bare numeric strings.
    expect(toConfidenceBand('0.62')?.id).toBe('workable');
    expect(toConfidenceBand('62')?.id).toBe('workable');
  });

  it('returns null for NaN/Infinity and unparseable strings', () => {
    expect(toConfidenceBand(Number.NaN)).toBeNull();
    expect(toConfidenceBand(Number.POSITIVE_INFINITY)).toBeNull();
    expect(toConfidenceBand(Number.NEGATIVE_INFINITY)).toBeNull();
    expect(toConfidenceBand('not a confidence')).toBeNull();
    expect(toConfidenceBand('???')).toBeNull();
  });

  it('clamps negative numbers to the unreliable band', () => {
    expect(toConfidenceBand(-0.4)?.id).toBe('unreliable');
    expect(toConfidenceBand(-50)?.id).toBe('unreliable');
  });
});

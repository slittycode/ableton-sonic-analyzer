import { describe, expect, it } from 'vitest';
import { dbToColor } from '../../src/utils/colorScales';

describe('dbToColor', () => {
  it('returns a dark blue for t=0', () => {
    const color = dbToColor(0);
    // First segment: rgb(0, 0, 40) at t=0
    expect(color).toBe('rgb(0,0,40)');
  });

  it('returns a reddish color for t=1', () => {
    const color = dbToColor(1);
    // Last segment at t=1: rgb(255, 115, 0)
    expect(color).toMatch(/^rgb\(255,/);
  });

  it('returns mid-range color for t=0.5', () => {
    const color = dbToColor(0.5);
    // At boundary of segment 2 and 3
    expect(color).toMatch(/^rgb\(\d+,\d+,\d+\)$/);
  });

  it('clamps values below 0', () => {
    expect(dbToColor(-0.5)).toBe(dbToColor(0));
  });

  it('clamps values above 1', () => {
    expect(dbToColor(1.5)).toBe(dbToColor(1));
  });

  it('returns valid rgb string for all segment boundaries', () => {
    const boundaries = [0, 0.25, 0.5, 0.75, 1];
    for (const t of boundaries) {
      const color = dbToColor(t);
      expect(color).toMatch(/^rgb\(\d+,\d+,\d+\)$/);
    }
  });

  it('produces monotonically increasing red channel from 0 to 1', () => {
    const steps = [0, 0.25, 0.5, 0.75, 1];
    const reds = steps.map((t) => {
      const match = dbToColor(t).match(/^rgb\((\d+),/);
      return parseInt(match![1], 10);
    });
    for (let i = 1; i < reds.length; i++) {
      expect(reds[i]).toBeGreaterThanOrEqual(reds[i - 1]);
    }
  });
});

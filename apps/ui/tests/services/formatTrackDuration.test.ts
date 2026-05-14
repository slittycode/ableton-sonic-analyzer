/**
 * Locks in the M:SS formatter used in the collapsed Input Source panel
 * (Audit N9). The format has to be terse and stable — producers will scan it
 * alongside the filename to confirm they're looking at the right run.
 */
import { describe, expect, it } from 'vitest';
import { formatTrackDuration } from '../../src/App';

describe('formatTrackDuration', () => {
  it.each<[number, string]>([
    [0, '0:00'],
    [1, '0:01'],
    [9, '0:09'],
    [10, '0:10'],
    [59, '0:59'],
    [60, '1:00'],
    [61, '1:01'],
    [126, '2:06'],
    [3599, '59:59'],
    [3600, '60:00'],
  ])('formats %d seconds as %s', (seconds, expected) => {
    expect(formatTrackDuration(seconds)).toBe(expected);
  });

  it('rounds fractional seconds', () => {
    expect(formatTrackDuration(126.4)).toBe('2:06');
    expect(formatTrackDuration(126.6)).toBe('2:07');
  });

  it('returns null for missing / invalid values', () => {
    expect(formatTrackDuration(null)).toBeNull();
    expect(formatTrackDuration(undefined)).toBeNull();
    expect(formatTrackDuration(Number.NaN)).toBeNull();
    expect(formatTrackDuration(Number.POSITIVE_INFINITY)).toBeNull();
    expect(formatTrackDuration(-1)).toBeNull();
  });
});

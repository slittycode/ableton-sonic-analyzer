import { describe, expect, it } from 'vitest';

import {
  beatIndexAt,
  beatIndicesInRange,
  buildBeatCheckModel,
  firstBeatAtOrAfter,
  formatTrackTime,
  isAccentBeat,
  parseMeter,
  resolveBeatPositions,
} from '../../src/services/beatCheck';
import type { Phase1Result } from '../../src/types';
import { phase1EnvelopeFixture } from '../fixtures/phase1FullPayload';

const fixture = phase1EnvelopeFixture as unknown as Phase1Result;

function withRhythm(overrides: Partial<NonNullable<Phase1Result['rhythmDetail']>>, rest: Partial<Phase1Result> = {}) {
  return {
    ...fixture,
    ...rest,
    rhythmDetail: { ...fixture.rhythmDetail!, ...overrides },
  } as Phase1Result;
}

describe('parseMeter', () => {
  it('reads the numerator of a time signature', () => {
    expect(parseMeter('4/4')).toBe(4);
    expect(parseMeter('3/4')).toBe(3);
    expect(parseMeter(' 7 / 8 ')).toBe(7);
  });

  it('rejects anything else', () => {
    expect(parseMeter(null)).toBeNull();
    expect(parseMeter('four')).toBeNull();
    expect(parseMeter('0/4')).toBeNull();
  });
});

describe('isAccentBeat', () => {
  it('accents the measured bar 1 with no shift', () => {
    expect([1, 2, 3, 4].map((position) => isAccentBeat(position, 4, 0))).toEqual([true, false, false, false]);
  });

  it('moves the accent later by the shift, wrapping within the bar', () => {
    expect([1, 2, 3, 4].map((position) => isAccentBeat(position, 4, 1))).toEqual([false, true, false, false]);
    expect([1, 2, 3, 4].map((position) => isAccentBeat(position, 4, 3))).toEqual([false, false, false, true]);
    expect([1, 2, 3].map((position) => isAccentBeat(position, 3, 2))).toEqual([false, false, true]);
  });
});

describe('beat lookups', () => {
  const beats = [0.5, 1.0, 1.5, 2.0, 2.5];

  it('finds beats in a half-open range', () => {
    expect(beatIndicesInRange(beats, 1.0, 2.0)).toEqual([1, 2]);
    expect(beatIndicesInRange(beats, 0, 0.5)).toEqual([]);
    expect(beatIndicesInRange(beats, 2.4, 10)).toEqual([4]);
  });

  it('finds the first beat at or after a time', () => {
    expect(firstBeatAtOrAfter(beats, 0)).toBe(0);
    expect(firstBeatAtOrAfter(beats, 1.0)).toBe(1);
    expect(firstBeatAtOrAfter(beats, 1.01)).toBe(2);
    expect(firstBeatAtOrAfter(beats, 3)).toBe(5);
  });

  it('finds the beat currently sounding', () => {
    expect(beatIndexAt(beats, 0.2)).toBe(-1);
    expect(beatIndexAt(beats, 0.5)).toBe(0);
    expect(beatIndexAt(beats, 1.49)).toBe(1);
    expect(beatIndexAt(beats, 9)).toBe(4);
  });

  it('formats track time as m:ss.s', () => {
    expect(formatTrackTime(0)).toBe('0:00.0');
    expect(formatTrackTime(75.25)).toBe('1:15.3');
  });
});

describe('resolveBeatPositions', () => {
  const beats = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0];

  it('uses Phase 1 beat positions when they line up with the grid', () => {
    expect(resolveBeatPositions(beats, [3, 4, 1, 2, 3, 4], [1.5], 4)).toEqual({
      positions: [3, 4, 1, 2, 3, 4],
      source: 'beat_positions',
    });
  });

  it('counts from the first matching downbeat when positions are missing or misaligned', () => {
    expect(resolveBeatPositions(beats, null, [1.51], 4)).toEqual({
      positions: [3, 4, 1, 2, 3, 4],
      source: 'downbeats',
    });
    expect(resolveBeatPositions(beats, [1, 2], [0.5], 3).positions).toEqual([1, 2, 3, 1, 2, 3]);
  });

  it('gives up when nothing anchors bar 1', () => {
    expect(resolveBeatPositions(beats, null, [], 4)).toEqual({ positions: [], source: 'none' });
    expect(resolveBeatPositions(beats, null, [7.77], 4).source).toBe('none');
  });
});

describe('buildBeatCheckModel', () => {
  it('re-expresses tempo, grid, downbeat and meter measurements with their trust labels', () => {
    const model = buildBeatCheckModel(fixture);
    expect(model.bpm).toBe(128);
    expect(model.beats).toEqual([0.47, 0.94, 1.41, 1.88]);
    expect(model.positions).toEqual([1, 2, 3, 4]);
    expect(model.positionSource).toBe('beat_positions');
    expect(model.meter).toBe(4);
    expect(model.meterAssumed).toBe(true);
    expect(model.downbeatSource).toBe('kick_accent');
    expect(model.downbeatConfidence).toBe(0.36);
    expect(model.trust.tempo.label).toBe('LOCAL');
    expect(model.trust.beatGrid.label).toBe('LOCAL');
    expect(model.trust.downbeats.label).toBe('CHECK');
    expect(model.trust.meter.label).toBe('CHECK');
    expect(model.usable).toBe(true);
  });

  it('offers the whole track and each measured 8-bar phrase', () => {
    const model = buildBeatCheckModel(withRhythm({}, { durationSeconds: 30 }));
    expect(model.regions.map((region) => [region.id, region.start, region.end])).toEqual([
      ['whole', 0, 30],
      ['phrase-1', 0.47, 15.47],
      ['phrase-2', 15.47, 30],
    ]);
    expect(model.regions[1].label).toBe('Phrase 1 · 0:00.5–0:15.5');
  });

  it('falls back to every 8th downbeat when there is no phrase grid', () => {
    const downbeats = Array.from({ length: 17 }, (_, bar) => 1 + bar * 2);
    const model = buildBeatCheckModel(withRhythm({ phraseGrid: null, downbeats }, { durationSeconds: 40 }));
    expect(model.regions.slice(1).map((region) => region.start)).toEqual([1, 17, 33]);
  });

  it('sorts an unsorted grid and then derives positions from downbeats', () => {
    const model = buildBeatCheckModel(
      withRhythm({ beatGrid: [1.0, 0.5, 1.5, 2.0], beatPositions: [2, 1, 3, 4], downbeats: [1.0] }),
    );
    expect(model.beats).toEqual([0.5, 1.0, 1.5, 2.0]);
    expect(model.positions).toEqual([4, 1, 2, 3]);
    expect(model.positionSource).toBe('downbeats');
  });

  it('marks the model unusable without a beat grid', () => {
    const model = buildBeatCheckModel({ ...fixture, rhythmDetail: null });
    expect(model.usable).toBe(false);
    expect(model.beats).toEqual([]);
    expect(model.positionSource).toBe('none');
  });

  it('does not assume the meter when Phase 1 detected it', () => {
    const model = buildBeatCheckModel({ ...fixture, timeSignature: '3/4', timeSignatureSource: 'onset_accent' });
    expect(model.meter).toBe(3);
    expect(model.meterAssumed).toBe(false);
  });
});

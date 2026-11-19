import { describe, expect, it } from 'vitest';

import {
  MIN_ATTACK_S,
  MIN_RELEASE_S,
  clampAdsr,
  envelopeLevelAt,
  heldLevelAt,
  type EnvelopeState,
} from '../../src/audio/envelope';

const adsr = { attack: 0.1, decay: 0.2, sustain: 0.5, release: 0.4 };

describe('heldLevelAt', () => {
  it('ramps linearly through attack and decay, then holds sustain', () => {
    expect(heldLevelAt(-0.01, adsr, 1)).toBe(0);
    expect(heldLevelAt(0, adsr, 1)).toBe(0);
    expect(heldLevelAt(0.05, adsr, 1)).toBeCloseTo(0.5);
    expect(heldLevelAt(0.1, adsr, 1)).toBeCloseTo(1);
    expect(heldLevelAt(0.2, adsr, 1)).toBeCloseTo(0.75);
    expect(heldLevelAt(0.3, adsr, 1)).toBeCloseTo(0.5);
    expect(heldLevelAt(5, adsr, 1)).toBeCloseTo(0.5);
  });

  it('scales with peak', () => {
    expect(heldLevelAt(5, adsr, 0.2)).toBeCloseTo(0.1);
  });
});

describe('envelopeLevelAt', () => {
  const base: EnvelopeState = {
    startTime: 10,
    peak: 1,
    adsr,
    releaseAt: null,
    releaseLevel: 0,
    releaseDuration: adsr.release,
  };

  it('follows the held envelope until release', () => {
    expect(envelopeLevelAt(base, 10.05)).toBeCloseTo(0.5);
    expect(envelopeLevelAt({ ...base, releaseAt: 12, releaseLevel: 0.5 }, 11)).toBeCloseTo(0.5);
  });

  it('ramps from the stored release level to zero over the release', () => {
    const released = { ...base, releaseAt: 12, releaseLevel: 0.5 };
    expect(envelopeLevelAt(released, 12)).toBeCloseTo(0.5);
    expect(envelopeLevelAt(released, 12.2)).toBeCloseTo(0.25);
    expect(envelopeLevelAt(released, 12.4)).toBe(0);
    expect(envelopeLevelAt(released, 20)).toBe(0);
  });

  it('continues from the first release line when a voice is released twice', () => {
    // Released at 12 (from 0.5), then stopped at 12.2 when the ramp sits at 0.25.
    const first = { ...base, releaseAt: 12, releaseLevel: 0.5 };
    const levelAtStop = envelopeLevelAt(first, 12.2);
    const second = { ...first, releaseAt: 12.2, releaseLevel: levelAtStop, releaseDuration: 0.02 };
    expect(envelopeLevelAt(second, 12.2)).toBeCloseTo(0.25);
    expect(envelopeLevelAt(second, 12.21)).toBeCloseTo(0.125);
  });

  it('is silent before a scheduled note starts', () => {
    expect(envelopeLevelAt(base, 9)).toBe(0);
  });
});

describe('clampAdsr', () => {
  it('enforces click-safe minimums and a 0–1 sustain', () => {
    expect(clampAdsr({ attack: 0, decay: 0, sustain: 2, release: 0 })).toEqual({
      attack: MIN_ATTACK_S,
      decay: 0.001,
      sustain: 1,
      release: MIN_RELEASE_S,
    });
    expect(clampAdsr({ attack: Number.NaN, decay: 0.2, sustain: -1, release: 1 }).sustain).toBe(0);
  });
});

import { expect, test, type Page } from '@playwright/test';

import type { Onset, RenderBeatCheckOptions } from './support/beatCheckHarness';

/**
 * Offline render checks for BeatChecker (src/audio/beatChecker.ts). Each test
 * renders the real class through renderTimeline — the Clock is ticked in step
 * with the render — and asserts on the audio: where clicks land, which are
 * accented, that the track lines up with them sample-for-sample, and that
 * loops and region ends behave.
 */

const BEATS = [0.5, 1.0, 1.5, 2.0, 2.5];
const POSITIONS = [1, 2, 3, 4, 1];
/** BeatChecker starts the region this long after play (LEAD_IN_S). */
const LEAD_IN = 0.1;
/** Half a millisecond — far tighter than the 10–50 ms jitter of JS timers. */
const TOLERANCE = 0.0005;

async function render(page: Page, options: RenderBeatCheckOptions): Promise<Onset[]> {
  return page.evaluate(async (opts) => {
    const harness = await import('/tests/smoke/support/beatCheckHarness.ts');
    return harness.renderBeatCheck(opts);
  }, options);
}

function expectTimes(onsets: Onset[], expected: number[]) {
  expect(onsets.map((onset) => onset.time)).toHaveLength(expected.length);
  onsets.forEach((onset, index) => {
    expect(Math.abs(onset.time - expected[index])).toBeLessThan(TOLERANCE);
  });
}

test.describe('BeatChecker (headless browser)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('clicks on every measured beat, with the bar-1 click louder', async ({ page }) => {
    const onsets = await render(page, {
      seconds: 3.2,
      trackDuration: 3,
      beats: BEATS,
      positions: POSITIONS,
      meter: 4,
      region: { start: 0, end: 3, loop: false },
      trackVolume: 0,
    });
    expectTimes(onsets, BEATS.map((beat) => LEAD_IN + beat));
    const [bar1, beat2, beat3, beat4, nextBar1] = onsets.map((onset) => onset.peak);
    expect(bar1).toBeGreaterThan(beat2 * 1.3);
    expect(nextBar1).toBeGreaterThan(beat3 * 1.3);
    expect(Math.abs(beat2 - beat4)).toBeLessThan(0.05);
  });

  test('plays the track sample-aligned with the clicks', async ({ page }) => {
    const base = {
      seconds: 3.2,
      trackDuration: 3,
      beats: BEATS,
      positions: POSITIONS,
      meter: 4,
      region: { start: 0, end: 3, loop: false },
    };
    const clicks = await render(page, { ...base, trackVolume: 0 });
    const track = await render(page, { ...base, clickVolume: 0, trackMarkers: BEATS });
    expect(track).toHaveLength(clicks.length);
    track.forEach((marker, index) => {
      expect(Math.abs(marker.time - clicks[index].time)).toBeLessThan(2 / 48000);
    });
  });

  test('moves the bar-1 click when shifted', async ({ page }) => {
    const onsets = await render(page, {
      seconds: 3.2,
      trackDuration: 3,
      beats: BEATS,
      positions: POSITIONS,
      meter: 4,
      region: { start: 0, end: 3, loop: false },
      trackVolume: 0,
      accentShift: 1,
    });
    const peaks = onsets.map((onset) => onset.peak);
    // Position 2 (index 1) now carries the accent; position 1 does not.
    expect(peaks[1]).toBeGreaterThan(peaks[0] * 1.3);
    expect(peaks[1]).toBeGreaterThan(peaks[2] * 1.3);
  });

  test('loops a region seamlessly and never clicks during the lead-in', async ({ page }) => {
    // 1.95 sits 0.05 s before the loop end, so the lead-in window (which reads
    // as the tail of the pass before the first) would click it if unguarded.
    const beats = [1.0, 1.25, 1.5, 1.75, 1.95];
    const onsets = await render(page, {
      seconds: 3.5,
      trackDuration: 3,
      beats,
      positions: [1, 2, 3, 4, 1],
      meter: 4,
      region: { start: 1.0, end: 2.0, loop: true },
      trackVolume: 0,
    });
    const expected: number[] = [];
    for (let pass = 0; pass < 4; pass += 1) {
      for (const beat of beats) {
        const time = LEAD_IN + pass * 1.0 + (beat - 1.0);
        if (time < 3.5 - 0.03) expected.push(time);
      }
    }
    expect(onsets[0].time).toBeGreaterThanOrEqual(LEAD_IN - TOLERANCE);
    expectTimes(onsets, expected);
  });

  test('plays a non-looped region to its exact end, then stops', async ({ page }) => {
    const onsets = await render(page, {
      seconds: 3.2,
      trackDuration: 3,
      beats: BEATS,
      positions: POSITIONS,
      meter: 4,
      region: { start: 0.5, end: 1.6, loop: false },
      // 1.55: 50 ms before the region end — must still sound (no early cut).
      // 1.61: 10 ms after it — must not (the track stops on time, not on the
      // next clock tick). 2.0 / 2.5: well past the end.
      trackMarkers: [0.5, 1.0, 1.5, 1.55, 1.61, 2.0, 2.5],
    });
    // Clicks and markers coincide at 0.5 / 1.0 / 1.5.
    expectTimes(onsets, [LEAD_IN, LEAD_IN + 0.5, LEAD_IN + 1.0, LEAD_IN + 1.05]);
  });
});

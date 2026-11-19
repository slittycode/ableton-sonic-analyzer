/**
 * Browser-side harness for key-check / beat-check smoke specs. Loaded by
 * page.evaluate(() => import('/tests/smoke/support/beatCheckHarness.ts')) so
 * it resolves @audiorective/* through the same Vite dep graph as the app.
 *
 * Renders BeatChecker offline with renderTimeline (the Clock is driven in
 * step with the render) and reports onset times and peak levels.
 */

import { renderTimeline } from '@audiorective/clock';

import { BeatChecker, type BeatCheckPlayRegion } from '../../../src/audio/beatChecker';

export interface RenderBeatCheckOptions {
  seconds: number;
  trackDuration: number;
  beats: number[];
  positions: number[];
  meter: number;
  region: BeatCheckPlayRegion;
  accentShift?: number;
  clickVolume?: number;
  trackVolume?: number;
  /** Track-seconds positions of short pulses written into the track audio. */
  trackMarkers?: number[];
}

export interface Onset {
  time: number;
  peak: number;
}

const SAMPLE_RATE = 48000;

export async function renderBeatCheck(options: RenderBeatCheckOptions): Promise<Onset[]> {
  const rendered = await renderTimeline(
    { seconds: options.seconds, channels: 1, sampleRate: SAMPLE_RATE },
    (ctx, tickSource) => {
      const checker = new BeatChecker(ctx, { tickSource });
      checker.output.connect(ctx.destination);

      const track = ctx.createBuffer(1, Math.round(options.trackDuration * SAMPLE_RATE), SAMPLE_RATE);
      const data = track.getChannelData(0);
      for (const marker of options.trackMarkers ?? []) {
        const at = Math.round(marker * SAMPLE_RATE);
        for (let i = 0; i < 96 && at + i < data.length; i += 1) data[at + i] = 0.5; // 2 ms pulse
      }
      checker.setTrackBuffer(track, 'harness');
      checker.setBeats(options.beats, options.positions, options.meter);
      checker.params.accentShift.value = options.accentShift ?? 0;
      checker.params.clickVolume.value = options.clickVolume ?? 1;
      checker.params.trackVolume.value = options.trackVolume ?? 1;
      checker.play(options.region);
    },
  );
  return findOnsets(rendered.getChannelData(0), SAMPLE_RATE);
}

/** An onset is the first sample above threshold after at least 5 ms of near-silence. */
function findOnsets(data: Float32Array, sampleRate: number): Onset[] {
  const threshold = 0.01;
  const quietSamples = Math.round(0.005 * sampleRate);
  const onsets: Onset[] = [];
  let quiet = quietSamples;
  for (let i = 0; i < data.length; i += 1) {
    if (Math.abs(data[i]) > threshold) {
      if (quiet >= quietSamples) {
        let peak = 0;
        for (let j = i; j < Math.min(data.length, i + Math.round(0.025 * sampleRate)); j += 1) {
          peak = Math.max(peak, Math.abs(data[j]));
        }
        onsets.push({ time: i / sampleRate, peak });
      }
      quiet = 0;
    } else {
      quiet += 1;
    }
  }
  return onsets;
}

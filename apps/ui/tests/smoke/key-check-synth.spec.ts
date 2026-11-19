import { expect, test } from '@playwright/test';

/**
 * Headless render checks for KeySynth (src/audio/keySynth.ts).
 *
 * The Node unit suite has no Web Audio, so these run in the smoke browser:
 * the page imports the processor straight from the Vite dev server and renders
 * it into an OfflineAudioContext — no audio device, no backend, deterministic.
 * Each test asserts on what the synth actually outputs: pitch against the A4
 * reference, silence after release, and sequence timing.
 */

type RenderReport = {
  pitchHz: number;
  heldRms: number;
  tailRms: number;
  activeVoicesAfter: number;
};

async function renderNote(
  page: import('@playwright/test').Page,
  options: { midi: number; referenceA4: number },
): Promise<RenderReport> {
  return page.evaluate(async ({ midi, referenceA4 }) => {
    const { KeySynth } = await import('/src/audio/keySynth.ts');
    const sampleRate = 48000;
    const ctx = new OfflineAudioContext(1, sampleRate * 1.6, sampleRate);
    const synth = new KeySynth(ctx);
    synth.output.connect(ctx.destination);
    synth.params.waveform.value = 'sine';
    synth.params.cutoff.value = 18000;
    synth.params.referenceA4.value = referenceA4;
    synth.params.release.value = 0.2;

    synth.noteOn(midi, 1, 0.1);
    synth.noteOff(midi, 0.8);
    const buffer = await ctx.startRendering();
    const data = buffer.getChannelData(0);

    const slice = (from: number, to: number) => data.subarray(Math.round(from * sampleRate), Math.round(to * sampleRate));
    const rms = (samples: Float32Array) => Math.sqrt(samples.reduce((sum, s) => sum + s * s, 0) / samples.length);

    // Pitch from rising zero crossings with linear interpolation, over a
    // steady sustain window.
    const steady = slice(0.4, 0.7);
    const crossings: number[] = [];
    for (let i = 1; i < steady.length; i += 1) {
      if (steady[i - 1] < 0 && steady[i] >= 0) {
        crossings.push(i - 1 + steady[i - 1] / (steady[i - 1] - steady[i]));
      }
    }
    const periods = (crossings[crossings.length - 1] - crossings[0]) / (crossings.length - 1);

    return {
      pitchHz: sampleRate / periods,
      heldRms: rms(steady),
      tailRms: rms(slice(1.1, 1.6)),
      activeVoicesAfter: synth.activeVoiceCount,
    };
  }, options);
}

test.describe('KeySynth (headless browser)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('plays A4 at the A4 reference and is silent after release', async ({ page }) => {
    const report = await renderNote(page, { midi: 69, referenceA4: 440 });
    expect(report.pitchHz).toBeGreaterThan(439.5);
    expect(report.pitchHz).toBeLessThan(440.5);
    expect(report.heldRms).toBeGreaterThan(0.02);
    expect(report.tailRms).toBeLessThan(1e-4);
    expect(report.activeVoicesAfter).toBe(0);
  });

  test('retunes to a measured reference', async ({ page }) => {
    const report = await renderNote(page, { midi: 57, referenceA4: 432 });
    expect(report.pitchHz).toBeGreaterThan(215.7);
    expect(report.pitchHz).toBeLessThan(216.3);
  });

  test('schedules sequences sample-accurately and stops cleanly', async ({ page }) => {
    const result = await page.evaluate(async () => {
      const { KeySynth } = await import('/src/audio/keySynth.ts');
      const sampleRate = 48000;
      const ctx = new OfflineAudioContext(1, sampleRate * 2, sampleRate);
      const synth = new KeySynth(ctx);
      synth.output.connect(ctx.destination);
      synth.params.attack.value = 0.003;
      synth.params.release.value = 0.05;

      const playback = synth.playSequence(
        [
          { midi: 60, startTime: 0.5, duration: 0.2, velocity: 1 },
          { midi: 64, startTime: 1.0, duration: 0.2, velocity: 1 },
        ],
        0,
      );
      const buffer = await ctx.startRendering();
      const data = buffer.getChannelData(0);
      const firstSound = data.findIndex((s) => Math.abs(s) > 1e-3) / sampleRate;
      const rms = (from: number, to: number) => {
        const part = data.subarray(Math.round(from * sampleRate), Math.round(to * sampleRate));
        return Math.sqrt(part.reduce((sum, s) => sum + s * s, 0) / part.length);
      };
      return {
        firstSound,
        gapRms: rms(0.8, 0.95),
        secondRms: rms(1.05, 1.15),
        afterEndRms: rms(playback.endsAt + 0.02, 2),
        endsAt: playback.endsAt,
      };
    });

    expect(result.firstSound).toBeGreaterThanOrEqual(0.5);
    expect(result.firstSound).toBeLessThan(0.505);
    expect(result.gapRms).toBeLessThan(1e-4);
    expect(result.secondRms).toBeGreaterThan(0.01);
    expect(result.endsAt).toBeCloseTo(1.25, 5);
    expect(result.afterEndRms).toBeLessThan(1e-4);
  });

  test('releases mid-decay from the envelope line, without a level jump', async ({ page }) => {
    const levels = await page.evaluate(async () => {
      const { KeySynth } = await import('/src/audio/keySynth.ts');
      const sampleRate = 48000;
      const ctx = new OfflineAudioContext(1, sampleRate, sampleRate);
      const synth = new KeySynth(ctx);
      synth.output.connect(ctx.destination);
      synth.params.waveform.value = 'sine';
      synth.params.cutoff.value = 18000;
      synth.params.attack.value = 0.01;
      synth.params.decay.value = 0.4;
      synth.params.sustain.value = 0.2;
      synth.params.release.value = 0.3;
      // 440 Hz → whole periods in 1/440 s; measure RMS per period.
      synth.noteOn(69, 1, 0);
      synth.noteOff(69, 0.2); // halfway down the decay
      const data = (await ctx.startRendering()).getChannelData(0);
      const period = sampleRate / 440;
      const rmsAround = (t: number) => {
        const start = Math.round(t * sampleRate);
        const part = data.subarray(start, start + Math.round(period * 2));
        return Math.sqrt(part.reduce((sum, s) => sum + s * s, 0) / part.length);
      };
      return { before: rmsAround(0.2 - 2 / 440), after: rmsAround(0.2) };
    });
    // A click or a hold-then-jump would show as a step between adjacent periods.
    expect(levels.after / levels.before).toBeGreaterThan(0.9);
    expect(levels.after / levels.before).toBeLessThan(1.0);
  });

  test('Session Musician previews play through the shared engine and end on time', async ({ page }) => {
    await page.mouse.click(5, 5); // user activation so the AudioContext may resume
    const result = await page.evaluate(async () => {
      const { previewNotes } = await import('/src/services/midi/midiPreview.ts');
      const { engine } = await import('/src/audio/engine.ts');
      const notes = [
        { midi: 60, name: 'C4', startTime: 0, duration: 0.15, velocity: 100, confidence: 1 },
        { midi: 64, name: 'E4', startTime: 0.2, duration: 0.15, velocity: 100, confidence: 1 },
      ];
      const started = performance.now();
      let voicesDuring = 0;
      await new Promise<void>((resolve) => {
        previewNotes(notes, () => resolve());
        setTimeout(() => {
          voicesDuring = engine.synth.activeVoiceCount;
        }, 300);
      });
      const elapsedMs = performance.now() - started;

      // A stopped preview reports not-playing immediately and fires onEnd once.
      let endCalls = 0;
      const handle = previewNotes(notes, () => {
        endCalls += 1;
      });
      handle.stop();
      handle.stop();
      return { elapsedMs, voicesDuring, state: engine.core.state(), stoppedPlaying: handle.playing, endCalls };
    });
    expect(result.state).toBe('running');
    expect(result.voicesDuring).toBeGreaterThan(0);
    // 0.35 s of notes + 0.3 s default release + lead-in/slack.
    expect(result.elapsedMs).toBeGreaterThan(600);
    expect(result.elapsedMs).toBeLessThan(2500);
    expect(result.stoppedPlaying).toBe(false);
    expect(result.endCalls).toBe(1);
  });

  test('caps polyphony by fading the oldest voice', async ({ page }) => {
    const result = await page.evaluate(async () => {
      const { KeySynth, KEY_SYNTH_POLYPHONY } = await import('/src/audio/keySynth.ts');
      const ctx = new OfflineAudioContext(1, 48000, 48000);
      const synth = new KeySynth(ctx);
      synth.output.connect(ctx.destination);
      for (let i = 0; i < KEY_SYNTH_POLYPHONY + 3; i += 1) synth.noteOn(48 + i, 0.8, 0.01 * i);
      return { held: synth.cells.heldNotes.value.length, limit: KEY_SYNTH_POLYPHONY };
    });
    expect(result.held).toBe(result.limit);
  });
});

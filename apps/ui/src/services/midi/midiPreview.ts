import type { MidiDisplayNote } from './types';

export interface PreviewHandle {
  stop(): void;
  readonly playing: boolean;
}

/**
 * Play a note draft through the page's shared KeySynth (src/audio/engine.ts).
 *
 * Previously each preview built and closed its own AudioContext with a fixed
 * triangle voice. Now every preview — and the Key Check keyboard — share one
 * engine, so previews are scheduled on one clock and play with whatever patch
 * the producer has dialled in on the keyboard.
 *
 * The engine module is imported dynamically on first use: it creates an
 * AudioContext at import time and must stay out of the static import graph
 * the Node test suite renders. previewNotes is only called from a click.
 */
export function previewNotes(notes: MidiDisplayNote[], onEnd?: () => void): PreviewHandle {
  let isPlaying = true;
  let stopPlayback: (() => void) | null = null;
  let timeoutId: number | undefined;

  const finish = () => {
    if (!isPlaying) return;
    isPlaying = false;
    window.clearTimeout(timeoutId);
    onEnd?.();
  };

  void import('../../audio/engine')
    .then(async ({ engine }) => {
      await engine.core.start();
      if (!isPlaying) return; // stopped while the engine was loading or resuming
      const playback = engine.synth.playSequence(
        notes.map((note) => ({
          midi: note.midi,
          startTime: note.startTime,
          duration: note.duration,
          velocity: note.velocity / 127,
        })),
      );
      stopPlayback = () => playback.stop();
      const remainingMs = (playback.endsAt - engine.core.context.currentTime) * 1000 + 100;
      timeoutId = window.setTimeout(finish, Math.max(0, remainingMs));
    })
    .catch((error: unknown) => {
      console.warn('[midiPreview] audio engine unavailable', error);
      finish();
    });

  return {
    stop() {
      if (!isPlaying) return;
      stopPlayback?.();
      finish();
    },
    get playing() {
      return isPlaying;
    },
  };
}

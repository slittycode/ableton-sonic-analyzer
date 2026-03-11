import { MidiDisplayNote } from './types';

function midiToFrequency(midi: number): number {
  return 440 * Math.pow(2, (midi - 69) / 12);
}

export interface PreviewHandle {
  stop(): void;
  readonly playing: boolean;
}

export function previewNotes(notes: MidiDisplayNote[], onEnd?: () => void): PreviewHandle {
  const ctx = new AudioContext();
  const masterGain = ctx.createGain();
  masterGain.gain.value = 0.35;
  masterGain.connect(ctx.destination);

  let isPlaying = true;
  const sorted = [...notes].sort((a, b) => a.startTime - b.startTime);
  const endTimes: number[] = [];

  for (const note of sorted) {
    const freq = midiToFrequency(note.midi);
    const start = ctx.currentTime + note.startTime;
    const dur = Math.max(0.05, note.duration);
    const end = start + dur;
    endTimes.push(end);

    const osc = ctx.createOscillator();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(freq, start);

    const env = ctx.createGain();
    const velocity = note.velocity / 127;
    const attackTime = 0.01;
    const releaseTime = Math.min(0.08, dur * 0.3);

    env.gain.setValueAtTime(0, start);
    env.gain.linearRampToValueAtTime(velocity * 0.6, start + attackTime);
    env.gain.setValueAtTime(velocity * 0.6, end - releaseTime);
    env.gain.linearRampToValueAtTime(0, end);

    osc.connect(env);
    env.connect(masterGain);

    osc.start(start);
    osc.stop(end + 0.01);
  }

  const lastEnd = endTimes.length ? Math.max(...endTimes) : ctx.currentTime;
  const totalDuration = (lastEnd - ctx.currentTime) * 1000 + 100;
  const timeoutId = window.setTimeout(() => {
    isPlaying = false;
    void ctx.close();
    onEnd?.();
  }, totalDuration);

  return {
    stop() {
      if (!isPlaying) return;
      isPlaying = false;
      window.clearTimeout(timeoutId);
      masterGain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.05);
      window.setTimeout(() => void ctx.close(), 100);
      onEnd?.();
    },
    get playing() {
      return isPlaying;
    },
  };
}

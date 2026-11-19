/**
 * KeySynth — a small polyphonic subtractive synth for ear-checking Phase 1
 * measurements (the Key Check keyboard, Session Musician previews).
 *
 *   voice (osc → env gain) ┐
 *   voice (osc → env gain) ┼─▶ bus ─▶ low-pass filter ─▶ volume ─▶ output
 *   voice (osc → env gain) ┘
 *
 * All audio behaviour lives here as methods (noteOn / noteOff / holdDrone /
 * playSequence); UI code only sets params and calls methods. The patch is the
 * producer's own — nothing here is derived from measurements, so it makes no
 * claim about the reference track's sound. The one measurement-driven value,
 * `referenceA4`, is set by the caller from Phase 1 tuning.
 *
 * Voices are one-shot OscillatorNodes created per note, so they are wired with
 * raw `.connect()` into the fixed summing `bus`: every voice is a leaf with
 * one destination, all native nodes, zero latency, nothing to compensate. The
 * static chain after the bus goes through `defineGraph`.
 */

import { AudioProcessor, type Cell, type Param, type SchedulableParam } from '@audiorective/core';

import { midiToFrequency } from '../services/keyCheck';
import { clampAdsr, envelopeLevelAt, type Adsr, type EnvelopeState } from './envelope';

export type KeySynthWaveform = 'sine' | 'triangle' | 'sawtooth' | 'square';

export const KEY_SYNTH_WAVEFORMS: readonly KeySynthWaveform[] = ['sine', 'triangle', 'sawtooth', 'square'];

/** Max simultaneously sounding voices; the oldest is faded out to make room. */
export const KEY_SYNTH_POLYPHONY = 10;

/** Per-voice peak gain at velocity 1. Leaves headroom for a full chord + drone. */
const VOICE_PEAK_GAIN = 0.22;
/** Fade used when a voice is stolen or everything is stopped at once. */
const FAST_FADE_S = 0.02;

export const KEY_SYNTH_DEFAULTS = {
  volume: 0.7,
  waveform: 'sawtooth' as KeySynthWaveform,
  cutoff: 2400,
  resonance: 0.8,
  attack: 0.01,
  decay: 0.3,
  sustain: 0.6,
  release: 0.3,
  referenceA4: 440,
};

export interface SequencedNote {
  midi: number;
  /** Seconds from the start of the sequence. */
  startTime: number;
  /** Seconds. */
  duration: number;
  /** 0–1. */
  velocity: number;
}

export interface SequencePlayback {
  /** Context time the last scheduled voice falls silent. */
  readonly endsAt: number;
  /** Fade out everything this sequence scheduled, including notes not yet started. */
  stop(): void;
}

interface Voice extends EnvelopeState {
  midi: number;
  osc: OscillatorNode;
  env: GainNode;
}

type KeySynthParams = {
  volume: SchedulableParam;
  cutoff: SchedulableParam;
  resonance: SchedulableParam;
  waveform: Param<KeySynthWaveform>;
  attack: Param<number>;
  decay: Param<number>;
  sustain: Param<number>;
  release: Param<number>;
  /** A4 reference in Hz. Set from Phase 1 tuning to play in tune with the track. */
  referenceA4: Param<number>;
};

type KeySynthCells = {
  /** MIDI notes currently held by noteOn (keyboard, computer keys). */
  heldNotes: Cell<number[]>;
  /** MIDI notes currently held by holdDrone. */
  droneNotes: Cell<number[]>;
};

export class KeySynth extends AudioProcessor<KeySynthParams, KeySynthCells> {
  private readonly _bus: GainNode;
  private readonly _out: GainNode;
  /** Every voice that may still be sounding (held, droning, or sequenced). */
  private readonly _voices = new Set<Voice>();
  private readonly _held = new Map<number, Voice>();
  private _drone: Voice[] = [];

  constructor(ctx: BaseAudioContext) {
    const bus = new GainNode(ctx, { gain: 1 });
    const filter = new BiquadFilterNode(ctx, { type: 'lowpass' });
    const out = new GainNode(ctx);

    super(ctx, ({ param, cell }) => ({
      params: {
        volume: param({ default: KEY_SYNTH_DEFAULTS.volume, bind: out.gain }),
        cutoff: param({ default: KEY_SYNTH_DEFAULTS.cutoff, bind: filter.frequency }),
        resonance: param({ default: KEY_SYNTH_DEFAULTS.resonance, bind: filter.Q }),
        waveform: param<KeySynthWaveform>({ default: KEY_SYNTH_DEFAULTS.waveform }),
        attack: param({ default: KEY_SYNTH_DEFAULTS.attack }),
        decay: param({ default: KEY_SYNTH_DEFAULTS.decay }),
        sustain: param({ default: KEY_SYNTH_DEFAULTS.sustain }),
        release: param({ default: KEY_SYNTH_DEFAULTS.release }),
        referenceA4: param({ default: KEY_SYNTH_DEFAULTS.referenceA4 }),
      },
      cells: {
        heldNotes: cell<number[]>([]),
        droneNotes: cell<number[]>([]),
      },
      // Native nodes only: nothing buffers past a render quantum.
      latency: 0,
    }));

    this._bus = bus;
    this._out = out;

    this.defineGraph(() => [
      [bus, filter],
      [filter, out],
    ]);

    // Waveform and tuning changes reach notes that are already sounding.
    this.effect(() => {
      const type = this.params.waveform.value;
      for (const voice of this._voices) voice.osc.type = type;
    });
    this.effect(() => {
      const reference = this.params.referenceA4.value;
      const now = this.context.currentTime;
      for (const voice of this._voices) {
        voice.osc.frequency.setTargetAtTime(midiToFrequency(voice.midi, reference), now, 0.01);
      }
    });
  }

  get output(): GainNode {
    return this._out;
  }

  /** Start a held note. Re-pressing a held note retriggers it. */
  noteOn(midi: number, velocity = 0.8, when = this.context.currentTime): void {
    const existing = this._held.get(midi);
    if (existing) this._release(existing, when, FAST_FADE_S);
    this._held.set(midi, this._startVoice(midi, velocity, when));
    this.cells.heldNotes.update((draft) => {
      if (!draft.includes(midi)) draft.push(midi);
    });
  }

  noteOff(midi: number, when = this.context.currentTime): void {
    const voice = this._held.get(midi);
    if (!voice) return;
    this._held.delete(midi);
    this._release(voice, when);
    this.cells.heldNotes.update((draft) => {
      const index = draft.indexOf(midi);
      if (index >= 0) draft.splice(index, 1);
    });
  }

  /** Release every held keyboard note (not the drone, not sequences). */
  allNotesOff(when = this.context.currentTime): void {
    for (const midi of [...this._held.keys()]) this.noteOff(midi, when);
  }

  /** Sustain `midis` until releaseDrone(). Replaces any current drone. */
  holdDrone(midis: readonly number[], velocity = 0.6): void {
    const now = this.context.currentTime;
    this.releaseDrone(now);
    this._drone = midis.map((midi) => this._startVoice(midi, velocity, now));
    this.cells.droneNotes.value = [...midis];
  }

  releaseDrone(when = this.context.currentTime): void {
    for (const voice of this._drone) this._release(voice, when);
    this._drone = [];
    if (this.cells.droneNotes.value.length) this.cells.droneNotes.value = [];
  }

  /** Schedule a note list against the context clock (sample-accurate). */
  playSequence(notes: readonly SequencedNote[], leadIn = 0.05): SequencePlayback {
    const t0 = this.context.currentTime + leadIn;
    const voices: Voice[] = [];
    let endsAt = t0;
    for (const note of [...notes].sort((a, b) => a.startTime - b.startTime)) {
      const start = t0 + Math.max(0, note.startTime);
      const voice = this._startVoice(note.midi, note.velocity, start);
      this._release(voice, start + Math.max(0.05, note.duration));
      voices.push(voice);
      endsAt = Math.max(endsAt, voice.releaseAt! + voice.releaseDuration);
    }
    return {
      endsAt,
      stop: () => {
        const now = this.context.currentTime;
        for (const voice of voices) {
          if (this._voices.has(voice)) this._release(voice, now, FAST_FADE_S);
        }
      },
    };
  }

  /** Fade out everything — held notes, drone and sequences — right now. */
  panic(): void {
    const now = this.context.currentTime;
    for (const voice of this._voices) this._release(voice, now, FAST_FADE_S);
    this._held.clear();
    this._drone = [];
    this.cells.heldNotes.value = [];
    this.cells.droneNotes.value = [];
  }

  /** Voices that have not yet been cleaned up (for tests and diagnostics). */
  get activeVoiceCount(): number {
    return this._voices.size;
  }

  override destroy(): void {
    for (const voice of this._voices) this._dispose(voice, true);
    this._voices.clear();
    this._held.clear();
    this._drone = [];
    super.destroy();
  }

  private _currentAdsr(): Adsr {
    return clampAdsr({
      attack: this.params.attack.value,
      decay: this.params.decay.value,
      sustain: this.params.sustain.value,
      release: this.params.release.value,
    });
  }

  private _startVoice(midi: number, velocity: number, when: number): Voice {
    this._makeRoom(when);

    const ctx = this.context;
    const adsr = this._currentAdsr();
    const peak = VOICE_PEAK_GAIN * Math.min(1, Math.max(0, velocity));
    const osc = new OscillatorNode(ctx, {
      type: this.params.waveform.value,
      frequency: midiToFrequency(midi, this.params.referenceA4.value),
    });
    const env = new GainNode(ctx, { gain: 0 });
    osc.connect(env);
    env.connect(this._bus);

    const gain = env.gain;
    gain.setValueAtTime(0, when);
    gain.linearRampToValueAtTime(peak, when + adsr.attack);
    gain.linearRampToValueAtTime(peak * adsr.sustain, when + adsr.attack + adsr.decay);
    osc.start(when);

    const voice: Voice = {
      midi,
      osc,
      env,
      startTime: when,
      peak,
      adsr,
      releaseAt: null,
      releaseLevel: 0,
      releaseDuration: adsr.release,
    };
    osc.onended = () => this._dispose(voice, false);
    this._voices.add(voice);
    return voice;
  }

  /**
   * Ramp a voice to silence starting at `when`. The ramp first lands on the
   * envelope's own line at `when` (all segments are linear, so this is exact),
   * which keeps both live note-offs and pre-scheduled releases click-free.
   */
  private _release(voice: Voice, when: number, duration = voice.adsr.release): void {
    const level = envelopeLevelAt(voice, when);
    const gain = voice.env.gain;
    gain.cancelScheduledValues(when);
    gain.linearRampToValueAtTime(level, when);
    gain.linearRampToValueAtTime(0, when + duration);
    voice.releaseAt = when;
    voice.releaseLevel = level;
    voice.releaseDuration = duration;
    voice.osc.stop(when + duration + 0.01);
  }

  /**
   * Once the polyphony limit is reached, fade out the oldest sounding voice.
   * The drone is never stolen while anything else can be — it is the reference
   * the producer is listening against.
   */
  private _makeRoom(when: number): void {
    // Count voices actually sounding at `when`: started by then and not yet
    // released. Voices in their release are on the way out (re-stealing them
    // would let held notes pile up past the limit), and voices scheduled for
    // later — a Session Musician preview queues every note up front — must
    // never be stolen: releasing one before its start deletes the note.
    const sounding = [...this._voices].filter(
      (voice) => voice.startTime <= when && (voice.releaseAt === null || voice.releaseAt > when),
    );
    if (sounding.length < KEY_SYNTH_POLYPHONY) return;
    const candidates = sounding.filter((voice) => !this._drone.includes(voice));
    const pool = candidates.length ? candidates : sounding;
    const oldest = pool.reduce((a, b) => (b.startTime < a.startTime ? b : a));
    for (const [midi, voice] of this._held) {
      if (voice === oldest) {
        this._held.delete(midi);
        this.cells.heldNotes.update((draft) => {
          const index = draft.indexOf(midi);
          if (index >= 0) draft.splice(index, 1);
        });
      }
    }
    this._release(oldest, when, FAST_FADE_S);
  }

  private _dispose(voice: Voice, stopNow: boolean): void {
    if (stopNow) {
      try {
        voice.osc.stop();
      } catch {
        // Never started or already stopped — nothing to do.
      }
    }
    voice.osc.onended = null;
    voice.osc.disconnect();
    voice.env.disconnect();
    this._voices.delete(voice);
  }
}

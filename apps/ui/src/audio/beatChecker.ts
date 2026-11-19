/**
 * BeatChecker — plays the producer's track with a click on every measured
 * beat, sample-locked to the same AudioContext clock, so Phase 1's beat grid
 * and bar-1 placement can be judged by ear.
 *
 *   BufferPlayer (track) ─▶ trackGain ─┐
 *   Sampler (bar-1 click) ─┐           ├─▶ output
 *   Sampler (beat click) ──┴▶ clickBus ┘
 *
 * Why BufferPlayer and not the page's waveform player: that one plays through
 * an <audio> element on the media clock, which cannot phase-lock to clicks
 * scheduled on the AudioContext clock. BufferPlayer's start(when, offset) is
 * sample-accurate against the same clock the clicks use.
 *
 * Scheduling belongs to @audiorective/clock: each play session builds a
 * Timeline at 60 BPM (so one beat-axis unit is one second of track time,
 * counted from the region start) and clicks are placed from the windows the
 * Clock hands out. Loops are a CycleBarRuler reading over that axis — the
 * BufferPlayer loops the same region natively.
 */

import { AudioProcessor, BufferPlayer, Sampler, type Cell, type Param, type SchedulableParam } from '@audiorective/core';
import { Clock, CycleBarRuler, Timeline, type TickSource } from '@audiorective/clock';

import { beatIndicesInRange, isAccentBeat } from '../services/beatCheck';

export interface BeatCheckPlayRegion {
  /** Track seconds. */
  start: number;
  /** Track seconds (exclusive). */
  end: number;
  loop: boolean;
}

export type BeatCheckTrackState =
  | { status: 'empty' }
  | { status: 'decoding'; key: string }
  | { status: 'ready'; key: string; duration: number }
  | { status: 'error'; key: string; message: string };

export type BeatCheckTransport = { state: 'stopped' } | { state: 'playing'; region: BeatCheckPlayRegion };

/** Seconds between pressing play and the first sound, so nothing lands in the past. */
const LEAD_IN_S = 0.1;
/** Accent and normal click pitches — distinct enough to tell bar 1 apart by ear. */
const ACCENT_CLICK_HZ = 2000;
const BEAT_CLICK_HZ = 1000;

type BeatCheckerParams = {
  trackVolume: SchedulableParam;
  clickVolume: SchedulableParam;
  /** Move the bar-1 click this many beats later than measured. */
  accentShift: Param<number>;
};

type BeatCheckerCells = {
  track: Cell<BeatCheckTrackState>;
  transport: Cell<BeatCheckTransport>;
};

interface Session {
  clock: { destroy(): void };
  region: BeatCheckPlayRegion;
  /** Context time of the region start (beat-axis 0). */
  t0: number;
}

export class BeatChecker extends AudioProcessor<BeatCheckerParams, BeatCheckerCells> {
  private readonly _player: BufferPlayer;
  private readonly _accentClick: Sampler;
  private readonly _beatClick: Sampler;
  private readonly _out: GainNode;
  private readonly _tickSource: TickSource | undefined;
  private _beats: number[] = [];
  private _positions: number[] = [];
  private _meter = 4;
  private _session: Session | null = null;
  private _decodeToken = 0;

  /**
   * @param options.tickSource Drives every play session's Clock. Leave unset
   *   in the app (a Worker timer); renderTimeline passes its own so the same
   *   class renders offline in tests.
   */
  constructor(ctx: BaseAudioContext, options: { tickSource?: TickSource } = {}) {
    const player = new BufferPlayer(ctx);
    const accentClick = new Sampler(ctx, { polyphony: 2, buffer: makeClick(ctx, ACCENT_CLICK_HZ, 1) });
    const beatClick = new Sampler(ctx, { polyphony: 2, buffer: makeClick(ctx, BEAT_CLICK_HZ, 0.6) });
    const trackGain = new GainNode(ctx);
    const clickBus = new GainNode(ctx);
    const out = new GainNode(ctx);

    super(ctx, ({ param, cell }) => ({
      params: {
        trackVolume: param({ default: 0.8, bind: trackGain.gain }),
        clickVolume: param({ default: 0.6, bind: clickBus.gain }),
        accentShift: param({ default: 0 }),
      },
      cells: {
        track: cell<BeatCheckTrackState>({ status: 'empty' }),
        transport: cell<BeatCheckTransport>({ state: 'stopped' }),
      },
      latency: 0,
    }));

    this._player = player;
    this._accentClick = accentClick;
    this._beatClick = beatClick;
    this._out = out;
    this._tickSource = options.tickSource;

    this.defineGraph(() => [
      [player, trackGain],
      [trackGain, out],
      [accentClick, clickBus],
      [beatClick, clickBus],
      [clickBus, out],
    ]);
  }

  get output(): GainNode {
    return this._out;
  }

  /** Measured beats (track seconds, ascending) and their bar positions (1..meter). */
  setBeats(beats: readonly number[], positions: readonly number[], meter: number): void {
    this._beats = [...beats];
    this._positions = positions.length === beats.length ? [...positions] : [];
    this._meter = Math.max(1, Math.round(meter));
  }

  /**
   * Decode the producer's file into memory for sample-accurate playback.
   * `key` identifies the file so re-opening the panel doesn't decode twice.
   */
  async loadTrack(file: Blob, key: string): Promise<void> {
    const current = this.cells.track.value;
    if ((current.status === 'ready' || current.status === 'decoding') && current.key === key) return;
    this.stop();
    const token = ++this._decodeToken;
    this.cells.track.value = { status: 'decoding', key };
    try {
      const buffer = await this.context.decodeAudioData(await file.arrayBuffer());
      if (token !== this._decodeToken) return;
      this.setTrackBuffer(buffer, key);
    } catch (error) {
      if (token !== this._decodeToken) return;
      this.cells.track.value = {
        status: 'error',
        key,
        message: error instanceof Error ? error.message : 'The browser could not decode this file.',
      };
    }
  }

  /** Use an already-decoded buffer (tests, or a caller that decoded elsewhere). */
  setTrackBuffer(buffer: AudioBuffer, key: string): void {
    this.stop();
    this._player.buffer = buffer;
    this.cells.track.value = { status: 'ready', key, duration: buffer.duration };
  }

  play(region: BeatCheckPlayRegion): void {
    this.stop();
    const track = this.cells.track.value;
    if (track.status !== 'ready') return;
    const start = Math.max(0, Math.min(region.start, track.duration));
    const end = Math.max(start, Math.min(region.end, track.duration));
    const length = end - start;
    if (length < 0.05) return;
    const played: BeatCheckPlayRegion = { start, end, loop: region.loop };

    // 60 BPM: one beat-axis unit = one second of track time from `start`.
    // numerator 1 / denominator 4 → one axis unit per bar, so `bars` is the
    // region length in seconds (fractional lengths are fine).
    const timeline = new Timeline({ audioContext: this.context, bpm: 60 }).addRuler(
      'loop',
      new CycleBarRuler({ numerator: 1, denominator: 4, bars: length }),
    );
    const clock = new Clock({
      timeline,
      tickSource: this._tickSource,
      onTick: (window) => {
        const session = this._session;
        if (!session || session.clock !== clock) return;
        if (!played.loop) {
          // End the session only once the region end has actually been
          // reached. A window's beat range runs a look-ahead ahead of now, so
          // ending on `window.beat.start >= length` would cut the tail early.
          // The audio itself already stops on time: play() schedules
          // player.stop() at the region end.
          if (window.time.current >= timeline.beatToTime(length)) {
            queueMicrotask(() => {
              if (this._session === session) this.stop();
            });
            return;
          }
          const from = Math.max(0, window.beat.start);
          const to = Math.min(length, window.beat.end);
          if (to <= from) return;
          for (const index of beatIndicesInRange(this._beats, start + from, start + to)) {
            this._click(index, timeline.beatToTime(this._beats[index] - start));
          }
          return;
        }
        for (const span of window.rulers.loop.spans) {
          for (const index of beatIndicesInRange(this._beats, start + span.fromCycle, start + span.toCycle)) {
            const when = span.toTime(this._beats[index] - start);
            // The lead-in reads as the tail of a pass before the first one.
            if (when < timeline.beatToTime(0) - 1e-9) continue;
            this._click(index, when);
          }
        }
      },
    });

    // The session must exist before start(): the Clock may emit its first
    // window synchronously, and onTick ignores windows from other sessions.
    const session: Session = { clock, region: played, t0: Number.NaN };
    this._session = session;

    // Start the axis slightly before 0 so beat 0 (the region start) lands
    // LEAD_IN_S in the future, then start the track exactly there.
    clock.start({ atBeat: -LEAD_IN_S });
    session.t0 = timeline.beatToTime(0);
    this._player.loop = played.loop;
    this._player.loopStart = start;
    this._player.loopEnd = end;
    this._player.start(session.t0, start);
    // Without a loop the track must end with the region, not the buffer.
    if (!played.loop) this._player.stop(session.t0 + length);

    this.cells.transport.value = { state: 'playing', region: played };
  }

  stop(): void {
    const session = this._session;
    if (!session) return;
    this._session = null;
    session.clock.destroy();
    this._player.stop();
    // Clicks already committed inside the look-ahead window would otherwise ring on.
    this._accentClick.stopAll();
    this._beatClick.stopAll();
    this.cells.transport.value = { state: 'stopped' };
  }

  /** Track position heard at context time `time` (pass engine.core.perceivedTime), or null when stopped. */
  trackPositionAt(time: number): number | null {
    const session = this._session;
    if (!session) return null;
    const { region, t0 } = session;
    const elapsed = time - t0;
    if (elapsed <= 0) return region.start;
    const length = region.end - region.start;
    if (region.loop) return region.start + (elapsed % length);
    return Math.min(region.end, region.start + elapsed);
  }

  override destroy(): void {
    this.stop();
    this._player.destroy();
    this._accentClick.destroy();
    this._beatClick.destroy();
    super.destroy();
  }

  private _click(beatIndex: number, when: number): void {
    const position = this._positions[beatIndex];
    const accent = position !== undefined && isAccentBeat(position, this._meter, this.params.accentShift.value);
    (accent ? this._accentClick : this._beatClick).trigger({ when });
  }
}

/** A short decaying sine "tick" — generated, so Beat Check ships no audio assets. */
function makeClick(ctx: BaseAudioContext, frequency: number, level: number): AudioBuffer {
  const sampleRate = ctx.sampleRate;
  const length = Math.round(sampleRate * 0.03);
  const buffer = ctx.createBuffer(1, length, sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < length; i += 1) {
    const t = i / sampleRate;
    data[i] = level * Math.sin(2 * Math.PI * frequency * t) * Math.exp(-t / 0.006) * (1 - i / length);
  }
  return buffer;
}

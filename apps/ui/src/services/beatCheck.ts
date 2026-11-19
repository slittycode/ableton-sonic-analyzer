/**
 * beatCheck — turns the Phase 1 rhythm measurements into what the Beat Check
 * player needs: the measured beat times, each beat's position in the bar, the
 * phrases to loop, and how much to trust each of those readings.
 *
 * Beat Check plays a click on every measured beat (`rhythmDetail.beatGrid`),
 * with a higher click on bar 1 (`rhythmDetail.beatPositions` / `downbeats`),
 * over the producer's own copy of the track. Flams or drift between click and
 * drums mean the beat grid is off; a high click that doesn't feel like bar 1
 * means the downbeat is off. This module only re-expresses Phase 1 fields.
 *
 * Pure — no Web Audio — so it runs under the Node unit suite.
 */

import type { Phase1Result } from '../types';
import { fundamentalsTrust, type FundamentalsTrust } from './fundamentalsTrust';

export interface BeatCheckRegion {
  id: string;
  label: string;
  /** Track seconds, inclusive. */
  start: number;
  /** Track seconds, exclusive. */
  end: number;
}

export interface BeatCheckModel {
  bpm: number | null;
  timeSignature: string | null;
  /** Beats per bar used for accents; 4 when Phase 1 has no usable meter. */
  meter: number;
  meterAssumed: boolean;
  trust: {
    tempo: FundamentalsTrust;
    beatGrid: FundamentalsTrust;
    downbeats: FundamentalsTrust;
    meter: FundamentalsTrust;
  };
  /** Measured beat times in track seconds, ascending. */
  beats: number[];
  /** Bar position (1..meter) of each beat, aligned with `beats`. */
  positions: number[];
  /** Where the positions came from. */
  positionSource: 'beat_positions' | 'downbeats' | 'none';
  downbeatSource: 'kick_accent' | 'stride' | null;
  downbeatConfidence: number | null;
  /** The whole track, then each measured 8-bar phrase. */
  regions: BeatCheckRegion[];
  durationSeconds: number | null;
  /** False when there are too few beats to click along to. */
  usable: boolean;
}

/** Downbeats are matched to beats within this tolerance when deriving positions. */
const DOWNBEAT_MATCH_TOLERANCE_S = 0.03;

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function parseMeter(timeSignature: string | null | undefined): number | null {
  if (typeof timeSignature !== 'string') return null;
  const match = timeSignature.trim().match(/^(\d{1,2})\s*\/\s*(\d{1,2})$/);
  if (!match) return null;
  const numerator = Number(match[1]);
  return numerator >= 1 && numerator <= 16 ? numerator : null;
}

function mod(value: number, divisor: number): number {
  return ((value % divisor) + divisor) % divisor;
}

/**
 * Bar position for each beat. Prefers Phase 1's own `beatPositions`; when that
 * is missing or misaligned, counts from the nearest measured downbeat.
 */
export function resolveBeatPositions(
  beats: readonly number[],
  beatPositions: readonly number[] | null | undefined,
  downbeats: readonly number[] | null | undefined,
  meter: number,
): { positions: number[]; source: BeatCheckModel['positionSource'] } {
  if (
    beatPositions &&
    beatPositions.length === beats.length &&
    beatPositions.every((position) => Number.isInteger(position) && position >= 1 && position <= meter)
  ) {
    return { positions: [...beatPositions], source: 'beat_positions' };
  }

  const anchors = (downbeats ?? []).filter(finite);
  if (anchors.length === 0) return { positions: [], source: 'none' };

  // Index of the first beat that lines up with a measured downbeat.
  const anchorIndex = beats.findIndex((beat) =>
    anchors.some((downbeat) => Math.abs(downbeat - beat) <= DOWNBEAT_MATCH_TOLERANCE_S),
  );
  if (anchorIndex < 0) return { positions: [], source: 'none' };
  return {
    positions: beats.map((_, index) => mod(index - anchorIndex, meter) + 1),
    source: 'downbeats',
  };
}

/**
 * Whether a beat gets the bar-1 click. `shift` moves the accent later by that
 * many beats, so the producer can hear whether bar 1 actually sits elsewhere.
 */
export function isAccentBeat(position: number, meter: number, shift: number): boolean {
  return mod(position - 1 - shift, meter) === 0;
}

/** Index of the first beat at or after `time` (binary search). */
export function firstBeatAtOrAfter(beats: readonly number[], time: number): number {
  let lo = 0;
  let hi = beats.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (beats[mid] < time) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** Indices of beats with from <= time < to. */
export function beatIndicesInRange(beats: readonly number[], from: number, to: number): number[] {
  const indices: number[] = [];
  for (let i = firstBeatAtOrAfter(beats, from); i < beats.length && beats[i] < to; i += 1) indices.push(i);
  return indices;
}

/** Index of the last beat at or before `time`, or -1. */
export function beatIndexAt(beats: readonly number[], time: number): number {
  const next = firstBeatAtOrAfter(beats, time + 1e-9);
  return next - 1;
}

export function formatTrackTime(seconds: number): string {
  const safe = Math.max(0, seconds);
  const minutes = Math.floor(safe / 60);
  const rest = safe - minutes * 60;
  return `${minutes}:${rest.toFixed(1).padStart(4, '0')}`;
}

function buildRegions(
  phase1: Phase1Result,
  beats: readonly number[],
  durationSeconds: number | null,
): BeatCheckRegion[] {
  const end = durationSeconds ?? (beats.length ? beats[beats.length - 1] + 1 : 0);
  const regions: BeatCheckRegion[] = [{ id: 'whole', label: 'Whole track', start: 0, end }];

  let starts = (phase1.rhythmDetail?.phraseGrid?.phrases8Bar ?? []).filter(finite);
  if (starts.length === 0) {
    // Fall back to every 8th measured downbeat.
    starts = (phase1.rhythmDetail?.downbeats ?? []).filter(finite).filter((_, index) => index % 8 === 0);
  }
  starts = [...new Set(starts)].sort((a, b) => a - b).filter((start) => start < end);

  starts.forEach((start, index) => {
    const phraseEnd = Math.min(end, starts[index + 1] ?? end);
    if (phraseEnd - start < 0.5) return;
    regions.push({
      id: `phrase-${index + 1}`,
      label: `Phrase ${index + 1} · ${formatTrackTime(start)}–${formatTrackTime(phraseEnd)}`,
      start,
      end: phraseEnd,
    });
  });
  return regions;
}

export function buildBeatCheckModel(phase1: Phase1Result): BeatCheckModel {
  const rhythm = phase1.rhythmDetail ?? null;
  const parsedMeter = parseMeter(phase1.timeSignature);
  const meter = parsedMeter ?? 4;
  const meterAssumed = parsedMeter === null || phase1.timeSignatureSource === 'assumed_four_four';

  const rawBeats = (rhythm?.beatGrid ?? []).filter(finite);
  const sorted = rawBeats.every((beat, index) => index === 0 || beat >= rawBeats[index - 1]);
  const beats = sorted ? rawBeats : [...rawBeats].sort((a, b) => a - b);
  const { positions, source } = resolveBeatPositions(
    beats,
    sorted ? rhythm?.beatPositions : null,
    rhythm?.downbeats,
    meter,
  );

  const durationSeconds = finite(phase1.durationSeconds) && phase1.durationSeconds > 0 ? phase1.durationSeconds : null;
  const downbeatSource = rhythm?.downbeatSource === 'kick_accent' || rhythm?.downbeatSource === 'stride'
    ? rhythm.downbeatSource
    : null;

  return {
    bpm: finite(phase1.bpm) && phase1.bpm > 0 ? phase1.bpm : null,
    timeSignature: typeof phase1.timeSignature === 'string' ? phase1.timeSignature : null,
    meter,
    meterAssumed,
    trust: {
      tempo: fundamentalsTrust(phase1, 'tempo'),
      beatGrid: fundamentalsTrust(phase1, 'beatGrid'),
      downbeats: fundamentalsTrust(phase1, 'downbeats'),
      meter: fundamentalsTrust(phase1, 'meter'),
    },
    beats,
    positions,
    positionSource: source,
    downbeatSource,
    downbeatConfidence: finite(rhythm?.downbeatConfidence) ? rhythm!.downbeatConfidence! : null,
    regions: buildRegions(phase1, beats, durationSeconds),
    durationSeconds,
    usable: beats.length >= 2,
  };
}

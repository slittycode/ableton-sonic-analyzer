/**
 * Transport for `GET /api/analysis-runs/{run_id}/transcription/pianoroll`.
 *
 * The endpoint renders the pitch-note translation stage's
 * `transcriptionDetail` as a velocity-encoded `(pitch, time)` matrix. The
 * frontend treats this as a derived view — Phase 1 stays authoritative; the
 * pianoroll just visualises what was already measured.
 *
 * Field names are camelCase to match the backend response verbatim (CLAUDE.md
 * tripwire #3: no conversion layer between JSON and TS).
 */

import { fetchJson } from './httpClient';

export type PianorollMode = 'frame' | 'onset';

export interface TranscriptionPianorollPayload {
  mode: PianorollMode;
  /** Lower MIDI pitch bound, inclusive. */
  pitchLow: number;
  /** Upper MIDI pitch bound, exclusive. */
  pitchHigh: number;
  ticksPerQuarter: number;
  /** Phase 1 BPM at time 0, or null when measurement didn't emit one. */
  quartersPerMinute: number | null;
  /** Phase 1 time signature like "4/4", or null if unknown. */
  timeSignature: string | null;
  /** Number of notes that survived validation in `build_score`. */
  noteCount: number;
  /**
   * `(pitchHigh - pitchLow)` rows × `time_steps` columns, values 0..127.
   * Row index 0 corresponds to MIDI `pitchLow`. Empty rows are still present
   * — callers should not rely on row length signalling "any note here".
   */
  frames: number[][];
}

export interface TranscriptionPianorollOptions {
  mode?: PianorollMode;
  /** Inclusive MIDI lower bound. */
  pitchLow?: number;
  /** Exclusive MIDI upper bound. */
  pitchHigh?: number;
  /** Time resolution in ticks per quarter note. */
  tpq?: number;
  signal?: AbortSignal;
}

export function buildTranscriptionPianorollUrl(
  apiBaseUrl: string,
  runId: string,
  options: TranscriptionPianorollOptions = {},
): string {
  const params = new URLSearchParams();
  if (options.mode !== undefined) params.set('mode', options.mode);
  if (options.pitchLow !== undefined) params.set('pitchLow', String(options.pitchLow));
  if (options.pitchHigh !== undefined) params.set('pitchHigh', String(options.pitchHigh));
  if (options.tpq !== undefined) params.set('tpq', String(options.tpq));
  const query = params.toString();
  return `${apiBaseUrl}/api/analysis-runs/${encodeURIComponent(runId)}/transcription/pianoroll${
    query ? `?${query}` : ''
  }`;
}

export async function fetchTranscriptionPianoroll(
  apiBaseUrl: string,
  runId: string,
  options: TranscriptionPianorollOptions = {},
): Promise<TranscriptionPianorollPayload> {
  const url = buildTranscriptionPianorollUrl(apiBaseUrl, runId, options);
  return fetchJson(url, { signal: options.signal }) as Promise<TranscriptionPianorollPayload>;
}

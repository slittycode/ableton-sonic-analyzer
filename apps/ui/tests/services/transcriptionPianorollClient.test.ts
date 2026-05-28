import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildTranscriptionPianorollUrl,
  fetchTranscriptionPianoroll,
  type TranscriptionPianorollPayload,
} from '../../src/services/transcriptionPianorollClient';
import { BackendClientError } from '../../src/services/backendPhase1Client';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, init: ResponseInit = { status: 200 }) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  });
}

function validPayload(
  overrides: Partial<TranscriptionPianorollPayload> = {},
): TranscriptionPianorollPayload {
  return {
    mode: 'frame',
    pitchLow: 21,
    pitchHigh: 109,
    ticksPerQuarter: 4,
    quartersPerMinute: 128.0,
    timeSignature: '4/4',
    noteCount: 1,
    // 88 pitch rows × 4 time steps — only row 39 (MIDI 60) has values.
    frames: Array.from({ length: 88 }, (_, row) =>
      row === 60 - 21 ? [100, 100, 100, 100] : [0, 0, 0, 0],
    ),
    ...overrides,
  };
}

describe('buildTranscriptionPianorollUrl', () => {
  it('uses the canonical run sub-resource path with no query when defaults are used', () => {
    const url = buildTranscriptionPianorollUrl('https://api.example.com', 'run-abc');
    expect(url).toBe(
      'https://api.example.com/api/analysis-runs/run-abc/transcription/pianoroll',
    );
  });

  it('encodes the runId so colons and slashes are safe', () => {
    const url = buildTranscriptionPianorollUrl(
      'https://api.example.com',
      'run/with:special',
    );
    expect(url).toContain('/api/analysis-runs/run%2Fwith%3Aspecial/');
  });

  it('emits camelCase query params that match the backend contract', () => {
    const url = buildTranscriptionPianorollUrl('https://api.example.com', 'r', {
      mode: 'onset',
      pitchLow: 60,
      pitchHigh: 72,
      tpq: 8,
    });
    expect(url).toContain('mode=onset');
    expect(url).toContain('pitchLow=60');
    expect(url).toContain('pitchHigh=72');
    expect(url).toContain('tpq=8');
  });

  it('omits the query string entirely when no options are provided', () => {
    const url = buildTranscriptionPianorollUrl('https://api.example.com', 'r');
    expect(url).not.toContain('?');
  });
});

describe('fetchTranscriptionPianoroll', () => {
  it('returns the typed payload on a 200 response', async () => {
    const expected = validPayload();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(expected));

    const result = await fetchTranscriptionPianoroll('https://api.example.com', 'run-x');

    expect(result).toEqual(expected);
  });

  it('forwards an AbortSignal so the caller can cancel the request', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse(validPayload()));
    const controller = new AbortController();

    await fetchTranscriptionPianoroll('https://api.example.com', 'run-x', {
      signal: controller.signal,
    });

    expect(fetchMock).toHaveBeenCalled();
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.signal).toBe(controller.signal);
  });

  it('throws BackendClientError with the server code on a 409', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: 'TRANSCRIPTION_NOT_COMPLETED',
            message: 'Pitch-note translation has not finished. Wait and retry.',
          },
        },
        { status: 409, statusText: 'Conflict' },
      ),
    );

    let captured: unknown;
    try {
      await fetchTranscriptionPianoroll('https://api.example.com', 'run-x');
    } catch (error) {
      captured = error;
    }

    expect(captured).toBeInstanceOf(BackendClientError);
    const err = captured as BackendClientError;
    expect(err.message).toContain('Pitch-note translation has not finished');
    expect((err.details as { serverCode?: string }).serverCode).toBe(
      'TRANSCRIPTION_NOT_COMPLETED',
    );
  });

  it('throws BackendClientError on a 404 TRANSCRIPTION_NOT_AVAILABLE', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: 'TRANSCRIPTION_NOT_AVAILABLE',
            message: 'Pitch-note translation did not produce a transcriptionDetail.',
          },
        },
        { status: 404 },
      ),
    );

    await expect(
      fetchTranscriptionPianoroll('https://api.example.com', 'run-x'),
    ).rejects.toBeInstanceOf(BackendClientError);
  });
});

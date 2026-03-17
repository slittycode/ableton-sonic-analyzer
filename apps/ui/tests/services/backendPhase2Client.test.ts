import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { analyzePhase2WithBackend } from '../../src/services/backendPhase2Client';
import { BackendClientError } from '../../src/services/backendPhase1Client';

const mockPhase1Result = {
  bpm: 128,
  key: 'A minor',
  keyConfidence: 0.91,
} as never; // minimal stub — shape not validated by client

const minimalPhase2Result = {
  trackCharacter: 'Energetic techno.',
  detectedCharacteristics: [],
  arrangementOverview: { summary: 'Four sections.', segments: [] },
  sonicElements: { kick: 'Kick 2', bass: 'Analog', melodicArp: 'Wavetable', grooveAndTiming: 'tight', effectsAndTexture: 'reverb' },
  mixAndMasterChain: [],
  secretSauce: { title: 'Sidechain Pump', explanation: 'Heavy sidechain.', implementationSteps: [] },
  confidenceNotes: [],
  abletonRecommendations: [],
};

function mockFile(name = 'track.mp3', size = 1024): File {
  return new File([new Uint8Array(size)], name, { type: 'audio/mpeg' });
}

function mockFetch(response: Partial<Response> & { jsonBody?: unknown }): typeof fetch {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: 'OK',
    json: () => Promise.resolve(response.jsonBody ?? {}),
    ...response,
  } as Response);
}

describe('analyzePhase2WithBackend', () => {
  const baseOptions = { apiBaseUrl: 'http://127.0.0.1:8100' };

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch({
      jsonBody: { requestId: 'req_1', phase2: minimalPhase2Result, message: 'Phase 2 advisory complete.' },
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns a success result with phase2 data on 200', async () => {
    const { result, log } = await analyzePhase2WithBackend(
      mockFile(),
      mockPhase1Result,
      'gemini-2.5-flash',
      baseOptions,
    );

    expect(result).toEqual(minimalPhase2Result);
    expect(log.status).toBe('success');
    expect(log.source).toBe('backend');
    expect(log.message).toBe('Phase 2 advisory complete.');
  });

  it('returns a skipped result when phase2 is null in response', async () => {
    vi.stubGlobal('fetch', mockFetch({
      jsonBody: { requestId: 'req_2', phase2: null, message: 'Phase 2 advisory skipped because Gemini returned an empty response.' },
    }));

    const { result, log } = await analyzePhase2WithBackend(
      mockFile(),
      mockPhase1Result,
      'gemini-2.5-flash',
      baseOptions,
    );

    expect(result).toBeNull();
    expect(log.status).toBe('skipped');
    expect(log.message).toContain('skipped');
  });

  it('throws BackendClientError when response is not ok', async () => {
    vi.stubGlobal('fetch', mockFetch({
      ok: false,
      status: 429,
      statusText: 'Too Many Requests',
      jsonBody: {
        requestId: 'req_3',
        error: { code: 'GEMINI_QUOTA', message: 'Quota exceeded.', retryable: true },
      },
    }));

    await expect(
      analyzePhase2WithBackend(mockFile(), mockPhase1Result, 'gemini-2.5-flash', baseOptions),
    ).rejects.toMatchObject({
      code: 'BACKEND_HTTP_ERROR',
      message: 'Quota exceeded.',
    });
  });

  it('retryable flag is preserved from server error payload', async () => {
    vi.stubGlobal('fetch', mockFetch({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
      jsonBody: {
        requestId: 'req_4',
        error: { code: 'GEMINI_GENERATE_FAILED', message: 'Gemini failed.', retryable: true },
      },
    }));

    let caught: BackendClientError | undefined;
    try {
      await analyzePhase2WithBackend(mockFile(), mockPhase1Result, 'gemini-2.5-flash', baseOptions);
    } catch (e) {
      caught = e as BackendClientError;
    }

    expect(caught?.details?.retryable).toBe(true);
  });

  it('throws BackendClientError when response body is non-JSON', async () => {
    vi.stubGlobal('fetch', mockFetch({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: () => Promise.reject(new SyntaxError('Unexpected token')),
    }));

    await expect(
      analyzePhase2WithBackend(mockFile(), mockPhase1Result, 'gemini-2.5-flash', baseOptions),
    ).rejects.toMatchObject({ code: 'BACKEND_BAD_RESPONSE' });
  });

  it('re-throws user cancelled error when signal is aborted before fetch', async () => {
    const controller = new AbortController();
    controller.abort();

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(Object.assign(new Error('AbortError'), { name: 'AbortError' })));

    await expect(
      analyzePhase2WithBackend(mockFile(), mockPhase1Result, 'gemini-2.5-flash', {
        ...baseOptions,
        signal: controller.signal,
      }),
    ).rejects.toMatchObject({ code: 'USER_CANCELLED' });
  });

  it('includes model name in the log entry', async () => {
    const { log } = await analyzePhase2WithBackend(
      mockFile(),
      mockPhase1Result,
      'gemini-2.5-pro',
      baseOptions,
    );

    expect(log.model).toBe('gemini-2.5-pro');
  });

  it('includes audio metadata in the log entry', async () => {
    const file = mockFile('my-track.wav', 2048);
    const { log } = await analyzePhase2WithBackend(file, mockPhase1Result, 'gemini-2.5-flash', baseOptions);

    expect(log.audioMetadata?.name).toBe('my-track.wav');
    expect(log.audioMetadata?.size).toBe(2048);
  });

  it('records responseLength from phase2 JSON on success', async () => {
    const { log } = await analyzePhase2WithBackend(
      mockFile(),
      mockPhase1Result,
      'gemini-2.5-flash',
      baseOptions,
    );

    expect(log.responseLength).toBeGreaterThan(0);
  });

  it('sets responseLength to 0 on skipped result', async () => {
    vi.stubGlobal('fetch', mockFetch({
      jsonBody: { requestId: 'req_skip', phase2: null, message: 'Skipped.' },
    }));

    const { log } = await analyzePhase2WithBackend(
      mockFile(),
      mockPhase1Result,
      'gemini-2.5-flash',
      baseOptions,
    );

    expect(log.responseLength).toBe(0);
  });
});

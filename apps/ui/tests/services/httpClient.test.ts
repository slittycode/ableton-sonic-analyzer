import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchJson } from '../../src/services/httpClient';
import { BackendClientError } from '../../src/services/backendPhase1Client';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('fetchJson — happy path', () => {
  it('returns the parsed JSON body on 2xx', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true, value: 42 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const result = await fetchJson('https://api.example.com/x', {});
    expect(result).toEqual({ ok: true, value: 42 });
  });

  it('passes the URL straight through to fetch', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('{}', { status: 200 }));
    await fetchJson('https://api.example.com/run/123', { method: 'GET' });
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.com/run/123',
      expect.objectContaining({ method: 'GET' }),
    );
  });
});

describe('fetchJson — error envelopes', () => {
  it('wraps a TypeError (network unreachable) in NETWORK_UNREACHABLE', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(fetchJson('https://api.example.com', {})).rejects.toMatchObject({
      code: 'NETWORK_UNREACHABLE',
    });
  });

  it('preserves the original TypeError as the cause', async () => {
    const original = new TypeError('Failed to fetch');
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(original);
    try {
      await fetchJson('https://api.example.com', {});
      throw new Error('expected fetchJson to throw');
    } catch (error) {
      expect(error).toBeInstanceOf(BackendClientError);
      expect((error as BackendClientError).details?.cause).toBe(original);
    }
  });

  it('throws createUserCancelledError when the signal is already aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    // fetch will reject because the signal is aborted before we even get there;
    // httpClient checks ``init.signal?.aborted`` and short-circuits to USER_CANCELLED.
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new DOMException('Aborted', 'AbortError'));
    await expect(
      fetchJson('https://api.example.com', { signal: controller.signal }),
    ).rejects.toMatchObject({ code: 'USER_CANCELLED' });
  });

  it('passes non-TypeError errors through unchanged (no wrapping)', async () => {
    const original = new Error('something exploded');
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(original);
    await expect(fetchJson('https://api.example.com', {})).rejects.toBe(original);
  });

  it('wraps a non-Error throw value in a generic Error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue('string-thrown');
    await expect(fetchJson('https://api.example.com', {})).rejects.toBeInstanceOf(Error);
  });
});

describe('fetchJson — response parsing', () => {
  it('throws BACKEND_BAD_RESPONSE when the response is not valid JSON', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('<html>not json</html>', {
        status: 200,
        headers: { 'Content-Type': 'text/html' },
      }),
    );
    await expect(fetchJson('https://api.example.com', {})).rejects.toMatchObject({
      code: 'BACKEND_BAD_RESPONSE',
    });
  });

  it('attaches the response status when JSON parsing fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('not json', {
        status: 200,
        statusText: 'OK',
      }),
    );
    try {
      await fetchJson('https://api.example.com', {});
      throw new Error('expected throw');
    } catch (error) {
      expect(error).toBeInstanceOf(BackendClientError);
      expect((error as BackendClientError).details?.status).toBe(200);
    }
  });
});

describe('fetchJson — HTTP error propagation', () => {
  it('throws BACKEND_HTTP_ERROR on a non-2xx response with a typed envelope', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: 'ANALYSIS_TIMEOUT',
            message: 'Backend analysis exceeded the deadline.',
            retryable: true,
          },
        }),
        {
          status: 500,
          statusText: 'Internal Server Error',
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    );

    try {
      await fetchJson('https://api.example.com', {});
      throw new Error('expected throw');
    } catch (error) {
      expect(error).toBeInstanceOf(BackendClientError);
      const typed = error as BackendClientError;
      expect(typed.code).toBe('BACKEND_HTTP_ERROR');
      expect(typed.message).toBe('Backend analysis exceeded the deadline.');
      expect(typed.details?.status).toBe(500);
      expect(typed.details?.serverCode).toBe('ANALYSIS_TIMEOUT');
      expect(typed.details?.retryable).toBe(true);
    }
  });

  it('falls back to a generic message when the body has no error.message', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ unrelated: 'shape' }), {
        status: 400,
        statusText: 'Bad Request',
      }),
    );
    await expect(fetchJson('https://api.example.com', {})).rejects.toMatchObject({
      code: 'BACKEND_HTTP_ERROR',
      message: 'Request failed.',
    });
  });

  it('does not crash when error.retryable is missing or non-boolean', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: 'X', message: 'msg', retryable: 'truthy-string' } }),
        { status: 502 },
      ),
    );
    try {
      await fetchJson('https://api.example.com', {});
      throw new Error('expected throw');
    } catch (error) {
      expect(error).toBeInstanceOf(BackendClientError);
      // Non-boolean retryable is dropped (undefined), not coerced.
      expect((error as BackendClientError).details?.retryable).toBeUndefined();
    }
  });

  it('handles an error envelope that is missing entirely', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: null }), { status: 503 }),
    );
    await expect(fetchJson('https://api.example.com', {})).rejects.toMatchObject({
      code: 'BACKEND_HTTP_ERROR',
      message: 'Request failed.',
    });
  });
});

describe('fetchJson — init forwarding via buildConfiguredRequestInit', () => {
  it('does not strip caller-supplied headers', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('{}', { status: 200 }));
    await fetchJson('https://api.example.com', {
      method: 'POST',
      headers: { 'X-Trace-Id': 'abc-123' },
    });
    const passedInit = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(passedInit).toBeDefined();
    // ``buildConfiguredRequestInit`` may wrap headers in a Headers instance
    // when injecting hosted-mode headers, or pass the plain object through
    // when none are configured. Accept either.
    const headers = passedInit?.headers;
    if (headers instanceof Headers) {
      expect(headers.get('X-Trace-Id')).toBe('abc-123');
    } else {
      expect(headers).toMatchObject({ 'X-Trace-Id': 'abc-123' });
    }
  });
});

import { describe, expect, it, vi } from 'vitest';

import {
  assertLiveE2EPreflight,
  backendSupportsPhase1Routes,
  validateLiveGeminiEnv,
} from '../e2e/support/preflight';

describe('e2e preflight', () => {
  it('reports missing live Gemini prerequisites', () => {
    const issues = validateLiveGeminiEnv({
      VITE_ENABLE_PHASE2_GEMINI: 'false',
    });

    expect(issues).toEqual([
      'VITE_ENABLE_PHASE2_GEMINI must be set to "true" for the full live E2E suite.',
    ]);
  });

  it('accepts a valid live Gemini environment', () => {
    expect(
      validateLiveGeminiEnv({
        VITE_ENABLE_PHASE2_GEMINI: 'true',
      }),
    ).toEqual([]);
  });

  it('detects whether the backend exposes both phase 1 routes', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        paths: {
          '/api/analyze': {},
          '/api/analyze/estimate': {},
          '/api/phase2': {},
        },
      }),
    });

    await expect(backendSupportsPhase1Routes('http://127.0.0.1:8100', fetchImpl)).resolves.toBe(true);
    expect(fetchImpl).toHaveBeenCalledWith('http://127.0.0.1:8100/openapi.json', expect.any(Object));
  });

  it('fails fast when the backend is unreachable or missing required routes', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        paths: {
          '/api/analyze': {},
        },
      }),
    });

    await expect(
      assertLiveE2EPreflight({
        env: {
          VITE_ENABLE_PHASE2_GEMINI: 'true',
          VITE_API_BASE_URL: 'http://127.0.0.1:8100',
        },
        fetchImpl,
      }),
    ).rejects.toThrow(
      'Backend at http://127.0.0.1:8100 must expose /api/analyze and /api/analyze/estimate for the full live E2E suite.',
    );
  });
});

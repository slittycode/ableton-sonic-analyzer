import { describe, expect, it, vi } from 'vitest';

import {
  assertLiveE2EPreflight,
  backendSupportsPhase1Routes,
  isPlaceholderGeminiApiKey,
  validateLiveGeminiEnv,
} from '../e2e/support/preflight';

describe('e2e preflight', () => {
  it('treats empty and placeholder Gemini keys as invalid', () => {
    expect(isPlaceholderGeminiApiKey('')).toBe(true);
    expect(isPlaceholderGeminiApiKey('   ')).toBe(true);
    expect(isPlaceholderGeminiApiKey('your_real_key_here')).toBe(true);
    expect(isPlaceholderGeminiApiKey('playwright-smoke-key')).toBe(true);
    expect(isPlaceholderGeminiApiKey('AIzaSy-real-looking-key')).toBe(false);
  });

  it('reports missing live Gemini prerequisites', () => {
    const issues = validateLiveGeminiEnv({
      VITE_ENABLE_PHASE2_GEMINI: 'false',
      VITE_GEMINI_API_KEY: 'your_real_key_here',
    });

    expect(issues).toEqual([
      'VITE_ENABLE_PHASE2_GEMINI must be set to "true" for the full live E2E suite.',
      'VITE_GEMINI_API_KEY must be set to a real Gemini API key for the full live E2E suite.',
    ]);
  });

  it('accepts a valid live Gemini environment', () => {
    expect(
      validateLiveGeminiEnv({
        VITE_ENABLE_PHASE2_GEMINI: 'true',
        VITE_GEMINI_API_KEY: 'AIzaSy-valid-key',
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
          VITE_GEMINI_API_KEY: 'AIzaSy-valid-key',
          VITE_API_BASE_URL: 'http://127.0.0.1:8100',
        },
        fetchImpl,
      }),
    ).rejects.toThrow(
      'Backend at http://127.0.0.1:8100 must expose /api/analyze and /api/analyze/estimate for the full live E2E suite.',
    );
  });
});

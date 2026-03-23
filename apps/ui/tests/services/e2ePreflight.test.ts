import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  assertLiveE2EPreflight,
  backendSupportsLiveE2ERoutes,
  isPlaceholderGeminiApiKey,
  validateLiveE2EEnv,
} from '../e2e/support/preflight';

const tempDirs: string[] = [];

async function createTempFile(name: string, contents = 'fixture'): Promise<string> {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'sonic-e2e-preflight-'));
  tempDirs.push(tempDir);
  const filePath = path.join(tempDir, name);
  await fs.writeFile(filePath, contents);
  return filePath;
}

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map((dir) => fs.rm(dir, { recursive: true, force: true })));
});

describe('e2e preflight', () => {
  it('treats empty and placeholder Gemini keys as invalid', () => {
    expect(isPlaceholderGeminiApiKey('')).toBe(true);
    expect(isPlaceholderGeminiApiKey('   ')).toBe(true);
    expect(isPlaceholderGeminiApiKey('your_real_key_here')).toBe(true);
    expect(isPlaceholderGeminiApiKey('playwright-smoke-key')).toBe(true);
    expect(isPlaceholderGeminiApiKey('AIzaSy-real-looking-key')).toBe(false);
  });

  it('reports missing live Gemini prerequisites', async () => {
    const issues = await validateLiveE2EEnv({
      TEST_FLAC_PATH: '',
      VITE_ENABLE_PHASE2_GEMINI: 'false',
      GEMINI_API_KEY: 'your_real_key_here',
    });

    expect(issues).toEqual([
      'TEST_FLAC_PATH must point to a readable audio file for the full live E2E suite.',
      'VITE_ENABLE_PHASE2_GEMINI must be set to "true" for the full live E2E suite.',
      'GEMINI_API_KEY must be set to a real Gemini API key for the full live E2E suite.',
    ]);
  });

  it('accepts a valid live Gemini environment', async () => {
    const trackPath = await createTempFile('fixture.flac');

    expect(
      await validateLiveE2EEnv({
        TEST_FLAC_PATH: trackPath,
        VITE_ENABLE_PHASE2_GEMINI: 'true',
        GEMINI_API_KEY: 'AIzaSy-valid-key',
      }),
    ).toEqual([]);
  });

  it('rejects unreadable or non-audio live track paths', async () => {
    const textPath = await createTempFile('fixture.txt', 'not audio');

    await expect(
      validateLiveE2EEnv({
        TEST_FLAC_PATH: textPath,
        VITE_ENABLE_PHASE2_GEMINI: 'true',
        GEMINI_API_KEY: 'AIzaSy-valid-key',
      }),
    ).resolves.toEqual([
      'TEST_FLAC_PATH must point to a readable audio file for the full live E2E suite.',
    ]);
  });

  it('detects whether the backend exposes the canonical live E2E routes', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        paths: {
          '/api/analysis-runs/estimate': {},
          '/api/analysis-runs': {},
          '/api/analysis-runs/{run_id}': {},
        },
      }),
    });

    await expect(backendSupportsLiveE2ERoutes('http://127.0.0.1:8100', fetchImpl)).resolves.toBe(true);
    expect(fetchImpl).toHaveBeenCalledWith('http://127.0.0.1:8100/openapi.json', expect.any(Object));
  });

  it('fails fast when the backend is unreachable or missing required routes', async () => {
    const trackPath = await createTempFile('fixture.wav');
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        paths: {
          '/api/analysis-runs/estimate': {},
        },
      }),
    });

    await expect(
      assertLiveE2EPreflight({
        env: {
          TEST_FLAC_PATH: trackPath,
          VITE_ENABLE_PHASE2_GEMINI: 'true',
          GEMINI_API_KEY: 'AIzaSy-valid-key',
          VITE_API_BASE_URL: 'http://127.0.0.1:8100',
        },
        fetchImpl,
      }),
    ).rejects.toThrow(
      'Backend at http://127.0.0.1:8100 must expose /api/analysis-runs/estimate, /api/analysis-runs, and /api/analysis-runs/{run_id} for the full live E2E suite.',
    );
  });
});

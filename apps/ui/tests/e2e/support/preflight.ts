import { access } from 'node:fs/promises';
import path from 'node:path';

const DEFAULT_BACKEND_BASE_URL = 'http://127.0.0.1:8100';
const PLACEHOLDER_GEMINI_KEYS = new Set([
  'your_real_key_here',
  'your_key_here',
  'test-gemini-key',
  'playwright-smoke-key',
  'replace_me',
  'changeme',
]);

type FetchLike = typeof fetch;

export function resolveLiveBackendBaseUrl(env: Record<string, string | undefined>): string {
  return env.VITE_API_BASE_URL?.trim() || DEFAULT_BACKEND_BASE_URL;
}

export function isPlaceholderGeminiApiKey(value: string | null | undefined): boolean {
  const normalized = value?.trim() ?? '';
  if (normalized.length === 0) return true;

  const lowered = normalized.toLowerCase();
  return (
    PLACEHOLDER_GEMINI_KEYS.has(lowered) ||
    lowered.includes('placeholder') ||
    lowered.includes('dummy') ||
    lowered.includes('example') ||
    lowered.includes('your_real_key_here')
  );
}

const AUDIO_EXTENSIONS = new Set([
  '.aac',
  '.aif',
  '.aiff',
  '.flac',
  '.m4a',
  '.mp3',
  '.ogg',
  '.wav',
  '.wma',
]);

async function isReadableAudioFile(filePath: string | undefined): Promise<boolean> {
  const normalized = filePath?.trim() ?? '';
  if (!normalized) return false;

  const extension = path.extname(normalized).toLowerCase();
  if (!AUDIO_EXTENSIONS.has(extension)) {
    return false;
  }

  try {
    await access(normalized);
    return true;
  } catch {
    return false;
  }
}

export async function validateLiveE2EEnv(env: Record<string, string | undefined>): Promise<string[]> {
  const issues: string[] = [];
  if (!(await isReadableAudioFile(env.TEST_FLAC_PATH))) {
    issues.push('TEST_FLAC_PATH must point to a readable audio file for the full live E2E suite.');
  }

  if (env.VITE_ENABLE_PHASE2_GEMINI !== 'true') {
    issues.push('VITE_ENABLE_PHASE2_GEMINI must be set to "true" for the full live E2E suite.');
  }

  if (isPlaceholderGeminiApiKey(env.GEMINI_API_KEY)) {
    issues.push('GEMINI_API_KEY must be set to a real Gemini API key for the full live E2E suite.');
  }

  return issues;
}

interface LiveE2EPreflightOptions {
  env?: Record<string, string | undefined>;
  fetchImpl?: FetchLike;
}

async function assertCanonicalAnalysisRunsBackend(
  backendBaseUrl: string,
  suiteLabel: string,
  fetchImpl: FetchLike = fetch,
): Promise<void> {
  const backendReady = await backendSupportsCanonicalAnalysisRunRoutes(backendBaseUrl, fetchImpl);

  if (!backendReady) {
    throw new Error(
      `Backend at ${backendBaseUrl} must expose /api/analysis-runs/estimate, /api/analysis-runs, and /api/analysis-runs/{run_id} for ${suiteLabel}.`,
    );
  }
}

export async function validateIntegrationE2EEnv(
  _env: Record<string, string | undefined>,
): Promise<string[]> {
  return [];
}

export async function backendSupportsCanonicalAnalysisRunRoutes(
  baseUrl: string,
  fetchImpl: FetchLike = fetch,
): Promise<boolean> {
  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), 2_500);

  try {
    const response = await fetchImpl(`${baseUrl.replace(/\/+$/, '')}/openapi.json`, {
      signal: controller.signal,
    });
    if (!response.ok) return false;

    const spec = (await response.json()) as { paths?: Record<string, unknown> };
    return Boolean(
      spec.paths?.['/api/analysis-runs/estimate'] &&
      spec.paths?.['/api/analysis-runs'] &&
      spec.paths?.['/api/analysis-runs/{run_id}'],
    );
  } catch {
    return false;
  } finally {
    clearTimeout(timeoutHandle);
  }
}

export async function backendSupportsLiveE2ERoutes(
  baseUrl: string,
  fetchImpl: FetchLike = fetch,
): Promise<boolean> {
  return backendSupportsCanonicalAnalysisRunRoutes(baseUrl, fetchImpl);
}

export async function assertLiveE2EPreflight(options: LiveE2EPreflightOptions = {}): Promise<void> {
  const env = options.env ?? (process.env as Record<string, string | undefined>);
  const issues = await validateLiveE2EEnv(env);

  if (issues.length > 0) {
    throw new Error(issues.join('\n'));
  }

  const backendBaseUrl = resolveLiveBackendBaseUrl(env);
  await assertCanonicalAnalysisRunsBackend(backendBaseUrl, 'the full live E2E suite', options.fetchImpl);
}

export async function assertIntegrationE2EPreflight(
  options: LiveE2EPreflightOptions = {},
): Promise<void> {
  const env = options.env ?? (process.env as Record<string, string | undefined>);
  const issues = await validateIntegrationE2EEnv(env);

  if (issues.length > 0) {
    throw new Error(issues.join('\n'));
  }

  const backendBaseUrl = resolveLiveBackendBaseUrl(env);
  await assertCanonicalAnalysisRunsBackend(backendBaseUrl, 'the local integration E2E suite', options.fetchImpl);
}

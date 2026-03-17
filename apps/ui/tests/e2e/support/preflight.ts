const DEFAULT_BACKEND_BASE_URL = 'http://127.0.0.1:8100';

type FetchLike = typeof fetch;

export function resolveLiveBackendBaseUrl(env: Record<string, string | undefined>): string {
  return env.VITE_API_BASE_URL?.trim() || DEFAULT_BACKEND_BASE_URL;
}

export function validateLiveGeminiEnv(env: Record<string, string | undefined>): string[] {
  const issues: string[] = [];

  if (env.VITE_ENABLE_PHASE2_GEMINI !== 'true') {
    issues.push('VITE_ENABLE_PHASE2_GEMINI must be set to "true" for the full live E2E suite.');
  }

  return issues;
}

export async function backendSupportsPhase1Routes(
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
      spec.paths?.['/api/analyze'] &&
      spec.paths?.['/api/analyze/estimate'] &&
      spec.paths?.['/api/phase2'],
    );
  } catch {
    return false;
  } finally {
    clearTimeout(timeoutHandle);
  }
}

interface LiveE2EPreflightOptions {
  env?: Record<string, string | undefined>;
  fetchImpl?: FetchLike;
}

export async function assertLiveE2EPreflight(options: LiveE2EPreflightOptions = {}): Promise<void> {
  const env = options.env ?? (process.env as Record<string, string | undefined>);
  const issues = validateLiveGeminiEnv(env);

  if (issues.length > 0) {
    throw new Error(issues.join('\n'));
  }

  const backendBaseUrl = resolveLiveBackendBaseUrl(env);
  const backendReady = await backendSupportsPhase1Routes(backendBaseUrl, options.fetchImpl);

  if (!backendReady) {
    throw new Error(
      `Backend at ${backendBaseUrl} must expose /api/analyze and /api/analyze/estimate for the full live E2E suite.`,
    );
  }
}

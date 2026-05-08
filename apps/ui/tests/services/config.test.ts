import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe('resolveAppConfig', () => {
  it('defaults the Phase 2 config gate to on when the env flag is unset', async () => {
    const {
      isGeminiPhase2ConfigEnabled,
      resolveAppConfig,
    } = await vi.importActual<typeof import('../../src/config')>('../../src/config');

    const config = resolveAppConfig({
      VITE_API_BASE_URL: undefined,
      VITE_ENABLE_PHASE2_GEMINI: undefined,
    });

    expect(config.enablePhase2Gemini).toBe(true);
    expect(isGeminiPhase2ConfigEnabled(config)).toBe(true);
  });

  it('disables Phase 2 when the env kill-switch is set to false', async () => {
    const {
      isGeminiPhase2ConfigEnabled,
      resolveAppConfig,
    } = await vi.importActual<typeof import('../../src/config')>('../../src/config');

    const config = resolveAppConfig({
      VITE_ENABLE_PHASE2_GEMINI: 'false',
    });

    expect(isGeminiPhase2ConfigEnabled(config)).toBe(false);
  });

  it('allows runtime overrides to replace build-time env values', async () => {
    const {
      buildConfiguredRequestInit,
      isGeminiPhase2ConfigEnabled,
      resolveAppConfig,
    } = await vi.importActual<typeof import('../../src/config')>('../../src/config');

    const config = resolveAppConfig(
      {
        VITE_ENABLE_PHASE2_GEMINI: 'true',
      },
      {
        VITE_ENABLE_PHASE2_GEMINI: 'false',
      },
    );

    expect(isGeminiPhase2ConfigEnabled(config)).toBe(false);
    expect(buildConfiguredRequestInit({}, config)).toEqual({});
  });

  it('uses the current web origin as the hosted fallback API base URL', async () => {
    const { resolveAppConfig } =
      await vi.importActual<typeof import('../../src/config')>('../../src/config');

    const fakeWindow = {
      location: { origin: 'https://asa.example.com/' },
    } as unknown as Window;

    const config = resolveAppConfig(
      {
        VITE_RUNTIME_PROFILE: 'hosted',
      },
      {},
      fakeWindow,
    );

    expect(config.runtimeProfile).toBe('hosted');
    expect(config.apiBaseUrl).toBe('https://asa.example.com');
  });

  it('parses hosted request headers and merges them into request init values', async () => {
    const {
      buildConfiguredRequestInit,
      resolveAppConfig,
    } = await vi.importActual<typeof import('../../src/config')>('../../src/config');

    const config = resolveAppConfig(
      {
        VITE_API_REQUEST_HEADERS_JSON: '{"X-ASA-User-Id":"beta-user-123","X-ASA-User-Email":"beta@example.com"}',
      },
      {},
    );

    const init = buildConfiguredRequestInit(
      {
        headers: {
          Accept: 'application/json',
        },
      },
      config,
    );
    const headers = new Headers(init.headers);

    expect(config.requestHeaders).toEqual({
      'X-ASA-User-Id': 'beta-user-123',
      'X-ASA-User-Email': 'beta@example.com',
    });
    expect(headers.get('Accept')).toBe('application/json');
    expect(headers.get('X-ASA-User-Id')).toBe('beta-user-123');
    expect(headers.get('X-ASA-User-Email')).toBe('beta@example.com');
  });

  it('preserves env request headers when browser overrides omit them', async () => {
    vi.stubEnv(
      'VITE_API_REQUEST_HEADERS_JSON',
      '{"X-ASA-User-Id":"beta-user-123","X-ASA-User-Email":"beta@example.com"}',
    );
    vi.stubGlobal(
      'window',
      {
        location: { origin: 'https://asa.example.com/' },
      } as unknown as Window,
    );

    const { appConfig } =
      await vi.importActual<typeof import('../../src/config')>('../../src/config');

    expect(appConfig.requestHeaders).toEqual({
      'X-ASA-User-Id': 'beta-user-123',
      'X-ASA-User-Email': 'beta@example.com',
    });
  });
});

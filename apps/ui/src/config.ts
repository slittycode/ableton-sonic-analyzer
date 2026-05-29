import uiPackage from '../package.json';

export interface AppConfig {
  apiBaseUrl: string;
  enablePhase2Gemini: boolean;
  /**
   * Operator opt-in for the MT3 polyphonic-transcription UI control. Defaults
   * OFF — MT3 needs a separate venv + ~4GB weights, so the toggle is hidden
   * unless an operator sets VITE_ENABLE_MT3. Gates the control only; the
   * results panel renders any MT3 result that exists regardless of this flag.
   */
  enableMt3: boolean;
  runtimeProfile: RuntimeProfile;
  requestHeaders: Record<string, string>;
}

type AppConfigEnv = Partial<
  Pick<
    ImportMetaEnv,
    | 'VITE_API_BASE_URL'
    | 'VITE_ENABLE_PHASE2_GEMINI'
    | 'VITE_ENABLE_MT3'
    | 'VITE_RUNTIME_PROFILE'
    | 'VITE_API_REQUEST_HEADERS_JSON'
  >
>;

type RuntimeProfile = 'local' | 'hosted';

function parseBooleanFlag(value: string | undefined, defaultValue: boolean): boolean {
  if (value === undefined) return defaultValue;
  return value.trim().toLowerCase() === 'true';
}

function resolveRuntimeProfile(value: string | undefined): RuntimeProfile {
  return value?.trim().toLowerCase() === 'hosted' ? 'hosted' : 'local';
}

function normalizeBaseUrl(
  value: string | undefined,
  runtimeProfile: RuntimeProfile,
  runtimeWindow?: Window,
): string {
  const fallback =
    runtimeProfile === 'hosted'
      ? runtimeWindow?.location?.origin?.replace(/\/+$/, '') ?? ''
      : 'http://127.0.0.1:8100';
  const raw = value?.trim();
  if (!raw) return fallback;
  return raw.replace(/\/+$/, '');
}

function readRuntimeEnvOverrides(runtimeWindow?: Window): AppConfigEnv {
  if (!runtimeWindow) {
    return {};
  }

  return {
    VITE_API_BASE_URL: runtimeWindow.__VITE_API_BASE_URL_OVERRIDE__,
    VITE_ENABLE_PHASE2_GEMINI: runtimeWindow.__VITE_ENABLE_PHASE2_GEMINI_OVERRIDE__,
    VITE_ENABLE_MT3: runtimeWindow.__VITE_ENABLE_MT3_OVERRIDE__,
    ...(runtimeWindow.__ASA_REQUEST_HEADERS_OVERRIDE__ !== undefined
      ? {
          VITE_API_REQUEST_HEADERS_JSON:
            typeof runtimeWindow.__ASA_REQUEST_HEADERS_OVERRIDE__ === 'string'
              ? runtimeWindow.__ASA_REQUEST_HEADERS_OVERRIDE__
              : JSON.stringify(runtimeWindow.__ASA_REQUEST_HEADERS_OVERRIDE__),
        }
      : {}),
  };
}

function parseRequestHeaders(value: string | undefined): Record<string, string> {
  if (!value?.trim()) {
    return {};
  }

  try {
    const parsed = JSON.parse(value) as Record<string, unknown>;
    return Object.fromEntries(
      Object.entries(parsed).flatMap(([key, entry]) =>
        typeof entry === 'string' && key.trim() !== '' ? [[key, entry]] : [],
      ),
    );
  } catch {
    return {};
  }
}

export function resolveAppConfig(
  env: AppConfigEnv,
  overrides: AppConfigEnv = {},
  runtimeWindow?: Window,
): AppConfig {
  const runtimeProfile = resolveRuntimeProfile(
    overrides.VITE_RUNTIME_PROFILE ?? env.VITE_RUNTIME_PROFILE,
  );
  return {
    runtimeProfile,
    apiBaseUrl: normalizeBaseUrl(
      overrides.VITE_API_BASE_URL ?? env.VITE_API_BASE_URL,
      runtimeProfile,
      runtimeWindow,
    ),
    enablePhase2Gemini: parseBooleanFlag(
      overrides.VITE_ENABLE_PHASE2_GEMINI ?? env.VITE_ENABLE_PHASE2_GEMINI,
      true,
    ),
    enableMt3: parseBooleanFlag(
      overrides.VITE_ENABLE_MT3 ?? env.VITE_ENABLE_MT3,
      false,
    ),
    requestHeaders: parseRequestHeaders(
      overrides.VITE_API_REQUEST_HEADERS_JSON ?? env.VITE_API_REQUEST_HEADERS_JSON,
    ),
  };
}

const runtimeWindow = typeof window === 'undefined' ? undefined : window;

export const appVersionLabel = `v${uiPackage.version}`;

export const appConfig: AppConfig = resolveAppConfig(
  import.meta.env,
  readRuntimeEnvOverrides(runtimeWindow),
  runtimeWindow,
);

export function isGeminiPhase2ConfigEnabled(config: AppConfig = appConfig): boolean {
  return config.enablePhase2Gemini;
}

export function isMt3ConfigEnabled(config: AppConfig = appConfig): boolean {
  return config.enableMt3;
}

export function buildConfiguredRequestInit(
  init: RequestInit = {},
  config: AppConfig = appConfig,
): RequestInit {
  if (Object.keys(config.requestHeaders).length === 0) {
    return init;
  }

  const headers = new Headers(init.headers);
  for (const [key, value] of Object.entries(config.requestHeaders)) {
    headers.set(key, value);
  }

  return {
    ...init,
    headers,
  };
}

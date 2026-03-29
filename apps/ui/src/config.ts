import uiPackage from '../package.json';

export interface AppConfig {
  apiBaseUrl: string;
  enablePhase2Gemini: boolean;
}

type AppConfigEnv = Partial<
  Pick<ImportMetaEnv, 'VITE_API_BASE_URL' | 'VITE_ENABLE_PHASE2_GEMINI'>
>;

function parseBooleanFlag(value: string | undefined, defaultValue: boolean): boolean {
  if (value === undefined) return defaultValue;
  return value.trim().toLowerCase() === 'true';
}

function normalizeBaseUrl(value: string | undefined): string {
  const fallback = 'http://127.0.0.1:8100';
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
  };
}

export function resolveAppConfig(env: AppConfigEnv, overrides: AppConfigEnv = {}): AppConfig {
  return {
    apiBaseUrl: normalizeBaseUrl(overrides.VITE_API_BASE_URL ?? env.VITE_API_BASE_URL),
    enablePhase2Gemini: parseBooleanFlag(
      overrides.VITE_ENABLE_PHASE2_GEMINI ?? env.VITE_ENABLE_PHASE2_GEMINI,
      true,
    ),
  };
}

const runtimeWindow = typeof window === 'undefined' ? undefined : window;

export const appVersionLabel = `v${uiPackage.version}`;

export const appConfig: AppConfig = resolveAppConfig(
  import.meta.env,
  readRuntimeEnvOverrides(runtimeWindow),
);

export function isGeminiPhase2ConfigEnabled(config: AppConfig = appConfig): boolean {
  return config.enablePhase2Gemini;
}

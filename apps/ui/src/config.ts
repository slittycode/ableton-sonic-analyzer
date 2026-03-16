export interface AppConfig {
  apiBaseUrl: string;
  enablePhase2Gemini: boolean;
  geminiApiKey: string;
}

type AppConfigEnv = Partial<
  Pick<ImportMetaEnv, 'VITE_API_BASE_URL' | 'VITE_ENABLE_PHASE2_GEMINI' | 'VITE_GEMINI_API_KEY'>
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
    VITE_GEMINI_API_KEY: runtimeWindow.__VITE_GEMINI_API_KEY_OVERRIDE__,
  };
}

export function resolveAppConfig(env: AppConfigEnv, overrides: AppConfigEnv = {}): AppConfig {
  return {
    apiBaseUrl: normalizeBaseUrl(overrides.VITE_API_BASE_URL ?? env.VITE_API_BASE_URL),
    enablePhase2Gemini: parseBooleanFlag(
      overrides.VITE_ENABLE_PHASE2_GEMINI ?? env.VITE_ENABLE_PHASE2_GEMINI,
      true,
    ),
    geminiApiKey: (overrides.VITE_GEMINI_API_KEY ?? env.VITE_GEMINI_API_KEY ?? '').trim(),
  };
}

const runtimeWindow = typeof window === 'undefined' ? undefined : window;

export const appConfig: AppConfig = resolveAppConfig(
  import.meta.env,
  readRuntimeEnvOverrides(runtimeWindow),
);

export function isGeminiPhase2ConfigEnabled(config: AppConfig = appConfig): boolean {
  return config.enablePhase2Gemini;
}

export function hasGeminiPhase2ApiKey(config: AppConfig = appConfig): boolean {
  return config.geminiApiKey.length > 0;
}

export function canRunGeminiPhase2(config: AppConfig = appConfig): boolean {
  return isGeminiPhase2ConfigEnabled(config) && hasGeminiPhase2ApiKey(config);
}

export function isGeminiPhase2Available(config: AppConfig = appConfig): boolean {
  return canRunGeminiPhase2(config);
}

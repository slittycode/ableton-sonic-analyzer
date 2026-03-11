interface AppConfig {
  apiBaseUrl: string;
  enablePhase2Gemini: boolean;
  geminiApiKey: string;
}

function parseBooleanFlag(value: string | undefined, defaultValue: boolean): boolean {
  if (value === undefined) return defaultValue;
  return value.trim().toLowerCase() === "true";
}

function normalizeBaseUrl(value: string | undefined): string {
  const fallback = "http://127.0.0.1:8100";
  const raw = value?.trim();
  if (!raw) return fallback;
  return raw.replace(/\/+$/, "");
}

export const appConfig: AppConfig = {
  apiBaseUrl: normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL),
  enablePhase2Gemini: parseBooleanFlag(import.meta.env.VITE_ENABLE_PHASE2_GEMINI, false),
  geminiApiKey: (import.meta.env.VITE_GEMINI_API_KEY ?? "").trim(),
};

export function isGeminiPhase2Available(): boolean {
  return appConfig.enablePhase2Gemini && appConfig.geminiApiKey.length > 0;
}

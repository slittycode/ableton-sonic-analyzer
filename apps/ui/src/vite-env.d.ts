/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_ENABLE_PHASE2_GEMINI?: string;
  readonly VITE_GEMINI_API_KEY?: string;
  readonly DISABLE_HMR?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  __VITE_API_BASE_URL_OVERRIDE__?: string;
  __VITE_ENABLE_PHASE2_GEMINI_OVERRIDE__?: string;
  __VITE_GEMINI_API_KEY_OVERRIDE__?: string;
  __SONIC_BENCHMARK__?: boolean;
}

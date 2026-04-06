/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_API_REQUEST_HEADERS_JSON?: string;
  readonly VITE_ENABLE_PHASE2_GEMINI?: string;
  readonly VITE_RUNTIME_PROFILE?: string;
  readonly DISABLE_HMR?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  __VITE_API_BASE_URL_OVERRIDE__?: string;
  __VITE_ENABLE_PHASE2_GEMINI_OVERRIDE__?: string;
  __ASA_REQUEST_HEADERS_OVERRIDE__?: string | Record<string, string>;
  __SONIC_BENCHMARK__?: boolean;
}

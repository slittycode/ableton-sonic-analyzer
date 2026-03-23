import { defineConfig } from '@playwright/test';

const SMOKE_PORT = 3100;
const smokeBaseUrl = `http://127.0.0.1:${SMOKE_PORT}`;
const smokeBackendUrl = process.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8100';
const smokePhase2Enabled = process.env.VITE_ENABLE_PHASE2_GEMINI ?? 'true';

export default defineConfig({
  testDir: './tests/smoke',
  timeout: 90_000,
  use: {
    headless: true,
    baseURL: smokeBaseUrl,
  },
  webServer: {
    command: `VITE_API_BASE_URL=${smokeBackendUrl} VITE_ENABLE_PHASE2_GEMINI=${smokePhase2Enabled} npm run dev:local`,
    url: smokeBaseUrl,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});

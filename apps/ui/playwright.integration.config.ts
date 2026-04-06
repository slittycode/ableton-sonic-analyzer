import { defineConfig } from '@playwright/test';

const INTEGRATION_PORT = 3100;
const integrationBaseUrl = `http://127.0.0.1:${INTEGRATION_PORT}`;
const integrationBackendUrl = process.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8100';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  globalSetup: './tests/e2e/support/integrationGlobalSetup.ts',
  reporter: 'list',
  timeout: 12 * 60 * 1_000,
  expect: {
    timeout: 30_000,
  },
  use: {
    acceptDownloads: true,
    baseURL: integrationBaseUrl,
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev:local',
    env: {
      ...process.env,
      VITE_API_BASE_URL: integrationBackendUrl,
      VITE_ENABLE_PHASE2_GEMINI: 'false',
    },
    url: integrationBaseUrl,
    reuseExistingServer: false,
    timeout: 120_000,
  },
  workers: 1,
});

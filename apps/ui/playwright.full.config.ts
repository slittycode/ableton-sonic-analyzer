import { defineConfig } from '@playwright/test';

const FULL_PORT = 3100;
const fullBaseUrl = `http://127.0.0.1:${FULL_PORT}`;
const fullBackendUrl = process.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8100';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  globalSetup: './tests/e2e/support/globalSetup.ts',
  reporter: 'list',
  timeout: 12 * 60 * 1_000,
  expect: {
    timeout: 30_000,
  },
  use: {
    acceptDownloads: true,
    baseURL: fullBaseUrl,
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev:local',
    env: {
      ...process.env,
      VITE_API_BASE_URL: fullBackendUrl,
      VITE_ENABLE_PHASE2_GEMINI: process.env.VITE_ENABLE_PHASE2_GEMINI ?? '',
    },
    url: fullBaseUrl,
    reuseExistingServer: false,
    timeout: 120_000,
  },
  workers: 1,
});

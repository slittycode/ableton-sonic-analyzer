import { defineConfig } from '@playwright/test';

const SMOKE_PORT = 3100;
const smokeBaseUrl = `http://127.0.0.1:${SMOKE_PORT}`;

export default defineConfig({
  testDir: './tests/smoke',
  timeout: 90_000,
  use: {
    headless: true,
    baseURL: smokeBaseUrl,
  },
  webServer: {
    command: `npm run dev -- --port=${SMOKE_PORT} --host=127.0.0.1`,
    url: smokeBaseUrl,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});

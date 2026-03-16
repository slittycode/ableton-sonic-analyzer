import type { Page } from '@playwright/test';

export async function disablePhase2ForTest(page: Page) {
  await page.addInitScript(() => {
    window.__VITE_ENABLE_PHASE2_GEMINI_OVERRIDE__ = 'false';
    window.__VITE_GEMINI_API_KEY_OVERRIDE__ = 'playwright-smoke-key';
  });
}

export async function enablePhase2ForTest(page: Page) {
  await page.addInitScript(() => {
    window.__VITE_ENABLE_PHASE2_GEMINI_OVERRIDE__ = 'true';
    window.__VITE_GEMINI_API_KEY_OVERRIDE__ = 'playwright-smoke-key';
  });
}

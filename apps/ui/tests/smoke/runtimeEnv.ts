import type { Page } from '@playwright/test';

export async function disablePhase2ForTest(page: Page) {
  await page.addInitScript(() => {
    window.__VITE_ENABLE_PHASE2_GEMINI_OVERRIDE__ = 'false';
  });
}

export async function enablePhase2ForTest(page: Page) {
  await page.addInitScript(() => {
    window.__VITE_ENABLE_PHASE2_GEMINI_OVERRIDE__ = 'true';
  });
}

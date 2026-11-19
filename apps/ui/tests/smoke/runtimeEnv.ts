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

export async function enableMt3ForTest(page: Page) {
  await page.addInitScript(() => {
    window.__VITE_ENABLE_MT3_OVERRIDE__ = 'true';
  });
}

export async function enableKeyCheckForTest(page: Page) {
  await page.addInitScript(() => {
    window.__VITE_ENABLE_KEY_CHECK_OVERRIDE__ = 'true';
  });
}

export async function enableBeatCheckForTest(page: Page) {
  await page.addInitScript(() => {
    window.__VITE_ENABLE_BEAT_CHECK_OVERRIDE__ = 'true';
  });
}

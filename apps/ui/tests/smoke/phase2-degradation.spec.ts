import { expect, test } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { disablePhase2ForTest, enablePhase2ForTest } from './runtimeEnv';

const testDir = path.dirname(fileURLToPath(import.meta.url));

const PHASE1_STUB = {
  bpm: 126,
  bpmConfidence: 0.93,
  key: 'F minor',
  keyConfidence: 0.88,
  timeSignature: '4/4',
  durationSeconds: 210.6,
  lufsIntegrated: -7.9,
  truePeak: -0.2,
  stereoWidth: 0.69,
  stereoCorrelation: 0.84,
  spectralBalance: {
    subBass: -0.7,
    lowBass: 1.2,
    mids: -0.3,
    upperMids: 0.4,
    highs: 1.0,
    brilliance: 0.8,
  },
};

function fixturePath(): string {
  return path.resolve(testDir, './fixtures/silence.wav');
}

function stubEstimateRoute(page: import('@playwright/test').Page, requestId: string) {
  return page.route('**/api/analyze/estimate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId,
        estimate: {
          durationSeconds: 10,
          totalLowMs: 22000,
          totalHighMs: 38000,
          stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 }],
        },
      }),
    });
  });
}

function stubAnalyzeRoute(page: import('@playwright/test').Page, requestId = 'req_phase2_degrade') {
  return page.route('**/api/analyze', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId,
        phase1: PHASE1_STUB,
        diagnostics: { backendDurationMs: 400, engineVersion: 'smoke' },
      }),
    });
  });
}

async function expectAnalysisResultsVisible(page: import('@playwright/test').Page) {
  await expect(page.getByText('Analysis Results')).toBeVisible({ timeout: 15_000 });
}

test('Phase 2 controls show config-disabled state when the env kill-switch is off', async ({ page }) => {
  await disablePhase2ForTest(page);
  await stubEstimateRoute(page, 'req_est_p2off');
  await stubAnalyzeRoute(page);

  await page.goto('/', { waitUntil: 'networkidle' });

  await expect(page.getByLabel('PHASE 2 ADVISORY')).toBeDisabled();
  await expect(page.getByTestId('phase2-status-inline')).toHaveText('PHASE 2 CONFIG OFF');
  await expect(page.getByTestId('phase2-model-desktop')).toBeDisabled();

  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  await expectAnalysisResultsVisible(page);
  await expect(page.getByText('126')).toBeVisible();
  await expect(
    page.getByText('Phase 2 advisory skipped because it was disabled by configuration.', { exact: true }).first(),
  ).toBeVisible();
});

test('turning Phase 2 off in the UI runs Phase 1 only and records the user-disabled reason', async ({ page }) => {
  await enablePhase2ForTest(page);
  await stubEstimateRoute(page, 'req_est_user_off');
  await stubAnalyzeRoute(page, 'req_user_off');

  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByLabel('PHASE 2 ADVISORY').uncheck();

  await expect(page.getByTestId('phase2-status-inline')).toHaveText('PHASE 2 USER OFF');

  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  await expectAnalysisResultsVisible(page);
  await expect(
    page.getByText('Phase 2 advisory skipped because it was disabled in the UI.', { exact: true }).first(),
  ).toBeVisible();
});

test('Phase 2 runs Phase 1 and delegates Gemini to the backend when enabled', async ({ page }) => {
  await enablePhase2ForTest(page);
  await stubEstimateRoute(page, 'req_est_p2_backend');
  await stubAnalyzeRoute(page, 'req_p2_backend');
  await page.route('**/api/phase2', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_p2_backend',
        phase2: null,
        message: 'Phase 2 advisory skipped because Gemini returned an empty response.',
        diagnostics: { backendDurationMs: 50, engineVersion: 'gemini-2.5-flash' },
      }),
    });
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());

  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  await expectAnalysisResultsVisible(page);
  await expect(page.getByText('126')).toBeVisible();
  await expect(
    page.getByText('Phase 2 advisory skipped because Gemini returned an empty response.', { exact: true }).first(),
  ).toBeVisible();
});

test('malformed Gemini Phase 2 response degrades gracefully to skipped', async ({ page }) => {
  await enablePhase2ForTest(page);
  await stubEstimateRoute(page, 'req_est_p2_malformed');
  await stubAnalyzeRoute(page, 'req_p2_malformed');
  await page.route('**/api/phase2', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_p2_malformed',
        phase2: null,
        message: 'Phase 2 advisory skipped because Gemini returned invalid JSON.',
        diagnostics: { backendDurationMs: 100, engineVersion: 'gemini-2.5-flash' },
      }),
    });
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await expect(page.getByLabel('PHASE 2 ADVISORY')).toBeChecked();

  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  await expectAnalysisResultsVisible(page);
  await expect(page.getByText('126')).toBeVisible();
  await expect(page.getByText('System Diagnostics')).toBeVisible();
  await expect(
    page.getByText('Phase 2 advisory skipped because Gemini returned invalid JSON.', { exact: true }).first(),
  ).toBeVisible();
});

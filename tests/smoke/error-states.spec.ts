import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

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

async function loadFileAndClick(page: import('@playwright/test').Page) {
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();
}

test('backend 500 shows error banner and ERROR status in diagnostic log', async ({ page }) => {
  await page.route('**/api/analyze/estimate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_est_err_500',
        estimate: {
          durationSeconds: 10,
          totalLowMs: 22000,
          totalHighMs: 38000,
          stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 }],
        },
      }),
    });
  });

  await page.route('**/api/analyze', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_err_500',
        error: {
          code: 'BACKEND_INTERNAL_ERROR',
          message: 'Internal server error during analysis.',
          phase: 'analysis',
          retryable: false,
        },
      }),
    });
  });

  await loadFileAndClick(page);

  const errorBanner = page.locator('div.p-3.text-red-400');
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner).toContainText('ERROR');
  await expect(errorBanner).toContainText('Internal server error during analysis.');

  await expect(page.getByText('System Diagnostics')).toBeVisible();
  const errorBadge = page.locator('text=ERROR').first();
  await expect(errorBadge).toBeVisible();
});

test('backend 502 (analyzer failed) shows error message in banner', async ({ page }) => {
  await page.route('**/api/analyze/estimate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_est_err_502',
        estimate: {
          durationSeconds: 10,
          totalLowMs: 22000,
          totalHighMs: 38000,
          stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 }],
        },
      }),
    });
  });

  await page.route('**/api/analyze', async (route) => {
    await route.fulfill({
      status: 502,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_err_502',
        error: {
          code: 'ANALYZER_FAILED',
          message: 'Analyzer subprocess exited with non-zero status.',
          phase: 'analysis',
          retryable: false,
        },
      }),
    });
  });

  await loadFileAndClick(page);

  const errorBanner = page.locator('div.p-3.text-red-400');
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner).toContainText('Analyzer subprocess exited with non-zero status.');

  await expect(page.getByText('System Diagnostics')).toBeVisible();
  await expect(page.getByText('ANALYZER_FAILED')).toBeVisible();
});

test('network failure shows NETWORK_UNREACHABLE-style error', async ({ page }) => {
  await page.route('**/api/analyze/estimate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_est_err_net',
        estimate: {
          durationSeconds: 10,
          totalLowMs: 22000,
          totalHighMs: 38000,
          stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 }],
        },
      }),
    });
  });

  await page.route('**/api/analyze', async (route) => {
    await route.abort('connectionrefused');
  });

  await loadFileAndClick(page);

  const errorBanner = page.locator('div.p-3.text-red-400');
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner).toContainText('ERROR');
});

test('estimate endpoint failure shows yellow warning but does not block analysis', async ({ page }) => {
  await page.route('**/api/analyze/estimate', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'text/plain',
      body: 'Internal Server Error',
    });
  });

  await page.route('**/api/analyze', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_est_fallback',
        phase1: PHASE1_STUB,
        diagnostics: { backendDurationMs: 400, engineVersion: 'smoke' },
      }),
    });
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());

  await expect(page.getByText(/Estimate unavailable/i)).toBeVisible();

  const analyzeButton = page.getByRole('button', { name: /Initiate Analysis/i });
  await expect(analyzeButton).toBeVisible();
  await expect(analyzeButton).toBeEnabled();

  await analyzeButton.click();
  await expect(page.getByText('Analysis Results')).toBeVisible();
});

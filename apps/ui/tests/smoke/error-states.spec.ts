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

function stubEstimateRoute(page: import('@playwright/test').Page) {
  return page.route('**/api/analyze/estimate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_est_err',
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

test('backend 500 shows error banner and ERROR status in diagnostic log', async ({ page }) => {
  await stubEstimateRoute(page);

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

  const errorBanner = page.locator('div.p-3.text-error');
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner).toContainText('ERROR');
  await expect(errorBanner).toContainText('Internal server error during analysis.');

  await expect(page.getByText('System Diagnostics')).toBeVisible();
  const errorBadge = page.locator('text=ERROR').first();
  await expect(errorBadge).toBeVisible();
});

test('backend 502 (analyzer failed) shows error message in banner', async ({ page }) => {
  await stubEstimateRoute(page);

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

  const errorBanner = page.locator('div.p-3.text-error');
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner).toContainText('Analyzer subprocess exited with non-zero status.');

  await expect(page.getByText('System Diagnostics')).toBeVisible();
  await expect(page.getByText('ANALYZER_FAILED')).toBeVisible();
});

test('network failure shows NETWORK_UNREACHABLE-style error', async ({ page }) => {
  await stubEstimateRoute(page);

  await page.route('**/api/analyze', async (route) => {
    await route.abort('connectionrefused');
  });

  await loadFileAndClick(page);

  const errorBanner = page.locator('div.p-3.text-error');
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

test('wrong backend service warning disables initiate analysis until the backend URL is fixed', async ({ page }) => {
  await page.route('**/api/analyze/estimate', async (route) => {
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Not Found' }),
    });
  });

  await page.route('**/openapi.json', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        info: { title: 'Multi-Agent Dashboard API' },
        paths: {
          '/api/state': {},
        },
      }),
    });
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());

  await expect(page.getByText(/Multi-Agent Dashboard API/)).toBeVisible();
  await expect(page.getByText(/Sonic Analyzer Local API/)).toBeVisible();
  await expect(page.getByText(/127\.0\.0\.1:8100/)).toBeVisible();
  await expect(page.getByText(/VITE_API_BASE_URL=http:\/\/127\.0\.0\.1:8100/i)).toBeVisible();

  const analyzeButton = page.getByRole('button', { name: /Initiate Analysis/i });
  await expect(analyzeButton).toBeVisible();
  await expect(analyzeButton).toBeDisabled();
});

test('error banner dismiss button removes the error', async ({ page }) => {
  await stubEstimateRoute(page);

  await page.route('**/api/analyze', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_err_dismiss',
        error: {
          code: 'BACKEND_INTERNAL_ERROR',
          message: 'Server error for dismiss test.',
          phase: 'analysis',
          retryable: false,
        },
      }),
    });
  });

  await loadFileAndClick(page);

  const errorBanner = page.locator('div.p-3.text-error');
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner).toContainText('Server error for dismiss test.');

  // No Retry button for non-retryable errors
  await expect(errorBanner.getByRole('button', { name: /Retry/i })).toHaveCount(0);

  // Click the dismiss (X) button
  const dismissBtn = errorBanner.getByLabel('Dismiss error');
  await expect(dismissBtn).toBeVisible();
  await dismissBtn.click();

  await expect(errorBanner).toHaveCount(0);
});

test('error banner shows Retry button for retryable errors', async ({ page }) => {
  await stubEstimateRoute(page);

  let callCount = 0;
  await page.route('**/api/analyze', async (route) => {
    callCount++;
    if (callCount === 1) {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          requestId: 'req_err_retry',
          error: {
            code: 'SERVICE_UNAVAILABLE',
            message: 'Backend temporarily unavailable.',
            phase: 'analysis',
            retryable: true,
          },
        }),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          requestId: 'req_retry_ok',
          phase1: PHASE1_STUB,
          diagnostics: { backendDurationMs: 200, engineVersion: 'smoke' },
        }),
      });
    }
  });

  // Stub the backend Phase 2 endpoint so it completes quickly when enabled
  await page.route('**/api/phase2', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_retry_p2',
        phase2: null,
        message: 'Phase 2 advisory skipped because Gemini returned an empty response.',
        diagnostics: { backendDurationMs: 50, engineVersion: 'gemini-2.5-flash' },
      }),
    });
  });

  await loadFileAndClick(page);

  const errorBanner = page.locator('div.p-3.text-error');
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner).toContainText('Backend temporarily unavailable.');

  // Retry button should be visible for retryable errors
  const retryBtn = errorBanner.getByRole('button', { name: /Retry/i });
  await expect(retryBtn).toBeVisible();

  // Click retry — should trigger re-analysis and succeed this time
  await retryBtn.click();
  await expect(page.getByText('Analysis Results')).toBeVisible({ timeout: 30000 });
});

test('cancel during phase 2 returns to idle without an error banner and logs skipped advisory', async ({ page }) => {
  await stubEstimateRoute(page);

  await page.route('**/api/analyze', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_phase2_cancel',
        phase1: PHASE1_STUB,
        diagnostics: { backendDurationMs: 250, engineVersion: 'smoke' },
      }),
    });
  });

  let releasePhase2Route: (() => void) | null = null;
  await page.route('**/api/phase2', async (route) => {
    await new Promise<void>((resolve) => {
      releasePhase2Route = resolve;
    });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_phase2_cancel',
        phase2: null,
        message: 'Phase 2 advisory skipped because Gemini returned an empty response.',
        diagnostics: { backendDurationMs: 100, engineVersion: 'gemini-2.5-flash' },
      }),
    });
  });

  await loadFileAndClick(page);

  await expect(page.getByText('Generating the advisory pass from completed local DSP measurements.')).toBeVisible();

  const cancelButton = page.getByRole('button', { name: /Cancel analysis/i });
  await expect(cancelButton).toBeVisible();
  await cancelButton.click();

  releasePhase2Route?.();

  await expect(page.locator('div.p-3.text-error')).toHaveCount(0);
  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByText('Analysis cancelled by user.')).toBeVisible();
  await expect(page.getByText('SKIPPED')).toBeVisible();
});

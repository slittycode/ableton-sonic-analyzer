import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const testDir = path.dirname(fileURLToPath(import.meta.url));

async function stubEstimateRoute(page: import('@playwright/test').Page) {
  await page.route('**/api/analyze/estimate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_estimate_smoke_001',
        estimate: {
          durationSeconds: 210.6,
          totalLowMs: 22000,
          totalHighMs: 38000,
          stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 }],
        },
      }),
    });
  });
}

test('upload + backend phase1 success renders analysis results', async ({ page }) => {
  await stubEstimateRoute(page);

  await page.route('**/api/analyze', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_smoke_001',
        phase1: {
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
        },
        diagnostics: {
          backendDurationMs: 980,
          engineVersion: 'smoke',
        },
      }),
    });
  });

  await page.goto('/', { waitUntil: 'networkidle' });

  const fixturePath = path.resolve(testDir, './fixtures/silence.wav');
  await page.setInputFiles('#audio-upload', fixturePath);

  await expect(page.getByRole('button', { name: /Initiate Analysis/i })).toBeVisible();
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByText('System Diagnostics')).toBeVisible();
  await expect(page.getByText('126')).toBeVisible();
});

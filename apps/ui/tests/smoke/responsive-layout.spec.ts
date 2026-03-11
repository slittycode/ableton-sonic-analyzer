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

function stubRoutes(page: import('@playwright/test').Page) {
  return Promise.all([
    page.route('**/api/analyze/estimate', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          requestId: 'req_est_responsive',
          estimate: {
            durationSeconds: 10,
            totalLowMs: 22000,
            totalHighMs: 38000,
            stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 }],
          },
        }),
      });
    }),
    page.route('**/api/analyze', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          requestId: 'req_responsive_001',
          phase1: PHASE1_STUB,
          diagnostics: { backendDurationMs: 400, engineVersion: 'smoke' },
        }),
      });
    }),
  ]);
}

test('mobile viewport (375px) renders landing and results in single column', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await expect(page.getByText('Drop Audio Here')).toBeVisible();
  await expect(page.getByText('NO SIGNAL DETECTED')).toBeVisible();

  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();
  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByText('126')).toBeVisible();
  await expect(page.getByText('System Diagnostics')).toBeVisible();
});

test('tablet viewport (768px) renders results with readable metrics', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();
  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByText('126')).toBeVisible();
  await expect(page.getByText(/F mi/)).toBeVisible();
  await expect(page.getByText('4/4')).toBeVisible();
});

test('desktop viewport (1280px) renders two-column grid layout', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await expect(page.getByText('Drop Audio Here')).toBeVisible();
  await expect(page.getByText('NO SIGNAL DETECTED')).toBeVisible();

  const inputSection = page.locator('.lg\\:col-span-4');
  const monitorSection = page.locator('.lg\\:col-span-8');

  await expect(inputSection).toBeVisible();
  await expect(monitorSection).toBeVisible();

  const inputBox = await inputSection.boundingBox();
  const monitorBox = await monitorSection.boundingBox();

  expect(inputBox).toBeTruthy();
  expect(monitorBox).toBeTruthy();

  if (inputBox && monitorBox) {
    expect(inputBox.y).toBeCloseTo(monitorBox.y, -1);
    expect(monitorBox.x).toBeGreaterThan(inputBox.x);
  }
});

test('mobile viewport hides model selector and CPU meter', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/', { waitUntil: 'networkidle' });

  // Brand should always be visible
  await expect(page.getByText('SonicAnalyzer')).toBeVisible();

  // Model selector label and CPU meter should be hidden on mobile
  await expect(page.getByText('Phase 2 Model')).not.toBeVisible();
  await expect(page.getByText('CPU')).not.toBeVisible();
});

test('desktop viewport shows model selector and CPU meter', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/', { waitUntil: 'networkidle' });

  await expect(page.getByText('SonicAnalyzer')).toBeVisible();
  await expect(page.getByText('Phase 2 Model')).toBeVisible();
  await expect(page.getByText('CPU')).toBeVisible();
});

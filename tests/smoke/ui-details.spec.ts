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
          requestId: 'req_est_ui',
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
          requestId: 'req_ui_001',
          phase1: PHASE1_STUB,
          diagnostics: { backendDurationMs: 400, engineVersion: 'smoke' },
        }),
      });
    }),
  ]);
}

test('NO SIGNAL DETECTED placeholder is shown before any file is loaded', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });
  await expect(page.getByText('NO SIGNAL DETECTED')).toBeVisible();
});

test('NO SIGNAL DETECTED disappears when a file is selected', async ({ page }) => {
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await expect(page.getByText('NO SIGNAL DETECTED')).toBeVisible();
  await page.setInputFiles('#audio-upload', fixturePath());
  await expect(page.getByText('NO SIGNAL DETECTED')).toHaveCount(0);
});

test('CPU indicator bar is visible in the header', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });
  await expect(page.getByText('CPU')).toBeVisible();
});

test('CPU indicator animates during analysis', async ({ page }) => {
  await page.route('**/api/analyze/estimate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_est_cpu',
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
    await new Promise((resolve) => setTimeout(resolve, 2000));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_cpu_001',
        phase1: PHASE1_STUB,
        diagnostics: { backendDurationMs: 400, engineVersion: 'smoke' },
      }),
    });
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  const cpuBar = page.locator('.animate-pulse').first();
  await expect(cpuBar).toBeVisible();

  await expect(page.getByText('Analysis Results')).toBeVisible();
});

test('diagnostic log shows SUCCESS badge and model info after analysis', async ({ page }) => {
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByText('System Diagnostics')).toBeVisible();

  const successBadge = page.locator('.bg-green-500\\/10').filter({ hasText: 'SUCCESS' });
  await expect(successBadge).toBeVisible();

  await expect(page.getByText('local-dsp-engine')).toBeVisible();

  // Scope to the diagnostics section to avoid matching the FileUpload file card
  const diagnostics = page.locator('.mt-12.space-y-4');
  await expect(diagnostics.getByText('silence.wav')).toBeVisible();
  await expect(diagnostics.getByText('audio/wav')).toBeVisible();
});

test('top metric cards show TEMPO, KEY SIG, METER, CHARACTER after analysis', async ({ page }) => {
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  await expect(page.getByText('Analysis Results')).toBeVisible();

  await expect(page.getByText('TEMPO')).toBeVisible();
  await expect(page.getByText('KEY SIG')).toBeVisible();
  await expect(page.getByText('METER')).toBeVisible();
  await expect(page.getByText('CHARACTER')).toBeVisible();

  await expect(page.getByText('126')).toBeVisible();
  await expect(page.getByText(/F mi/)).toBeVisible();
  await expect(page.getByText('4/4')).toBeVisible();
});

test('header shows SonicAnalyzer brand and Local DSP Engine label', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });
  await expect(page.getByText('SonicAnalyzer')).toBeVisible();
  await expect(page.getByText('Local DSP Engine')).toBeVisible();
});

test('JSON_DATA and REPORT_MD buttons are visible after analysis', async ({ page }) => {
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByRole('button', { name: /JSON_DATA/i })).toBeVisible();
  await expect(page.getByRole('button', { name: /REPORT_MD/i })).toBeVisible();
});

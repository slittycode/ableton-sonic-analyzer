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

function stubBackendRoutes(page: import('@playwright/test').Page) {
  return Promise.all([
    page.route('**/api/analyze/estimate', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          requestId: 'req_est_file',
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
          requestId: 'req_file_001',
          phase1: PHASE1_STUB,
          diagnostics: { backendDurationMs: 400, engineVersion: 'smoke' },
        }),
      });
    }),
    // Stub Gemini so Phase 2 completes quickly when enabled
    page.route('**://generativelanguage.googleapis.com/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ candidates: [] }),
      });
    }),
  ]);
}

test('clear button removes file and returns to upload drop zone', async ({ page }) => {
  await stubBackendRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await expect(page.getByText('Drop Audio Here')).toBeVisible();

  await page.setInputFiles('#audio-upload', fixturePath());
  await expect(page.getByText('silence.wav')).toBeVisible();
  await expect(page.getByText(/Ready/)).toBeVisible();

  const clearButton = page.getByTitle('Remove File');
  await expect(clearButton).toBeVisible();
  await clearButton.click();

  await expect(page.getByText('Drop Audio Here')).toBeVisible();
  await expect(page.getByText('silence.wav')).toHaveCount(0);
});

test('re-upload after results resets to file-selected state', async ({ page }) => {
  await stubBackendRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();
  await expect(page.getByText('Analysis Results')).toBeVisible();

  // Wait for analysis to fully complete (including Phase 2 if enabled)
  // so that isAnalyzing=false and the clear button becomes visible.
  const clearBtn = page.getByTitle('Remove File');
  await expect(clearBtn).toBeVisible({ timeout: 30000 });
  await clearBtn.click();
  await expect(page.getByText('Drop Audio Here')).toBeVisible();
  await page.setInputFiles('#audio-upload', fixturePath());

  await expect(page.getByText('silence.wav')).toBeVisible();
  await expect(page.getByRole('button', { name: /Initiate Analysis/i })).toBeVisible();
  await expect(page.getByText('Analysis Results')).toHaveCount(0);
});

test('file size is displayed in MB after selecting a file', async ({ page }) => {
  await stubBackendRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await page.setInputFiles('#audio-upload', fixturePath());

  await expect(page.getByText(/\d+\.\d+ MB/)).toBeVisible();
});

test('format badges (MP3, WAV, FLAC, AIFF) are visible on the drop zone', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });

  for (const format of ['MP3', 'WAV', 'FLAC', 'AIFF']) {
    await expect(page.getByText(format, { exact: true })).toBeVisible();
  }
});

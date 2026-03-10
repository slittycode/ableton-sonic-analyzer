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

function stubAnalyzeRoute(page: import('@playwright/test').Page) {
  return page.route('**/api/analyze', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_phase2_degrade',
        phase1: PHASE1_STUB,
        diagnostics: { backendDurationMs: 400, engineVersion: 'smoke' },
      }),
    });
  });
}

test('Phase 2 OFF indicator shown when Gemini feature flag is disabled', async ({ page }) => {
  await page.route('**/api/analyze/estimate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_est_p2off',
        estimate: {
          durationSeconds: 10,
          totalLowMs: 22000,
          totalHighMs: 38000,
          stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 }],
        },
      }),
    });
  });
  await stubAnalyzeRoute(page);

  await page.goto('/', { waitUntil: 'networkidle' });

  // Phase 2 is controlled by Vite env vars baked at build time.
  // If Phase 2 is enabled in this environment, skip the test.
  const phase2OffVisible = await page.getByText('PHASE 2 OFF').count();
  if (phase2OffVisible === 0) {
    test.skip(true, 'Phase 2 Gemini is enabled in this test environment — PHASE 2 OFF label is not rendered.');
    return;
  }

  await expect(page.getByText('PHASE 2 OFF')).toBeVisible();
  await expect(page.getByText('Phase 2 Model')).toBeVisible();

  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByText('126')).toBeVisible();
});

test('malformed Gemini Phase 2 response degrades gracefully to skipped', async ({ page }) => {
  await page.addInitScript(() => {
    (window as unknown as Record<string, string>).__VITE_ENABLE_PHASE2_GEMINI_OVERRIDE__ = 'true';
  });

  await page.route('**/api/analyze/estimate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_est_p2_malformed',
        estimate: {
          durationSeconds: 10,
          totalLowMs: 22000,
          totalHighMs: 38000,
          stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 }],
        },
      }),
    });
  });
  await stubAnalyzeRoute(page);

  await page.route('**://generativelanguage.googleapis.com/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        candidates: [
          {
            content: {
              role: 'model',
              parts: [{ text: 'This is not valid JSON for phase 2 {{{broken' }],
            },
          },
        ],
      }),
    });
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());

  const phase2Enabled = await page.getByText('PHASE 2 OFF').count();

  if (phase2Enabled > 0) {
    test.skip(true, 'Phase 2 Gemini is not enabled in this test environment — cannot test degradation path.');
    return;
  }

  await page.getByRole('button', { name: /Initiate Analysis/i }).click();
  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByText('126')).toBeVisible();
  await expect(page.getByText('System Diagnostics')).toBeVisible();
});

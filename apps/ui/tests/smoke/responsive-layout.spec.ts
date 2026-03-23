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
    lowMids: 0.0,
    mids: -0.3,
    upperMids: 0.4,
    highs: 1.0,
    brilliance: 0.8,
  },
};

const PHASE2_STUB = {
  trackCharacter: 'Deterministic smoke response.',
  detectedCharacteristics: [],
  arrangementOverview: { summary: 'Smoke summary.', segments: [] },
  sonicElements: {
    kick: 'Kick.',
    bass: 'Bass.',
    melodicArp: 'Arp.',
    grooveAndTiming: 'Groove.',
    effectsAndTexture: 'FX.',
  },
  mixAndMasterChain: [],
  secretSauce: {
    title: 'Smoke Sauce',
    explanation: 'Smoke explanation.',
    implementationSteps: [],
  },
  confidenceNotes: [],
  abletonRecommendations: [],
};

function fixturePath(): string {
  return path.resolve(testDir, './fixtures/silence.wav');
}

function stubRoutes(page: import('@playwright/test').Page) {
  return Promise.all([
    page.route('**/api/analysis-runs/estimate', async (route) => {
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
    page.route('**/api/analysis-runs', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          runId: 'run_responsive_001',
          requestedStages: {
            pitchNoteMode: 'off',
            pitchNoteBackend: 'auto',
            interpretationMode: 'async',
            interpretationProfile: 'producer_summary',
            interpretationModel: 'gemini-3.1-pro-preview',
          },
          artifacts: {
            sourceAudio: {
              artifactId: 'artifact_responsive_001',
              filename: 'silence.wav',
              mimeType: 'audio/wav',
              sizeBytes: 2048,
              contentSha256: 'abc123',
              path: '/tmp/silence.wav',
            },
          },
          stages: {
            measurement: {
              status: 'queued',
              authoritative: true,
              result: null,
              provenance: null,
              diagnostics: null,
              error: null,
            },
            pitchNoteTranslation: {
              status: 'not_requested',
              authoritative: false,
              preferredAttemptId: null,
              attemptsSummary: [],
              result: null,
              provenance: null,
              diagnostics: null,
              error: null,
            },
            interpretation: {
              status: 'blocked',
              authoritative: false,
              preferredAttemptId: null,
              attemptsSummary: [],
              result: null,
              provenance: null,
              diagnostics: null,
              error: null,
            },
          },
        }),
      });
    }),
    page.route('**/api/analysis-runs/run_responsive_001', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          runId: 'run_responsive_001',
          requestedStages: {
            pitchNoteMode: 'off',
            pitchNoteBackend: 'auto',
            interpretationMode: 'async',
            interpretationProfile: 'producer_summary',
            interpretationModel: 'gemini-3.1-pro-preview',
          },
          artifacts: {
            sourceAudio: {
              artifactId: 'artifact_responsive_001',
              filename: 'silence.wav',
              mimeType: 'audio/wav',
              sizeBytes: 2048,
              contentSha256: 'abc123',
              path: '/tmp/silence.wav',
            },
          },
          stages: {
            measurement: {
              status: 'completed',
              authoritative: true,
              result: PHASE1_STUB,
              provenance: null,
              diagnostics: { timings: { totalMs: 400, analysisMs: 360, serverOverheadMs: 40, flagsUsed: [], fileSizeBytes: 2048, fileDurationSeconds: 10, msPerSecondOfAudio: 40 } },
              error: null,
            },
            pitchNoteTranslation: {
              status: 'not_requested',
              authoritative: false,
              preferredAttemptId: null,
              attemptsSummary: [],
              result: null,
              provenance: null,
              diagnostics: null,
              error: null,
            },
            interpretation: {
              status: 'completed',
              authoritative: false,
              preferredAttemptId: 'int_responsive_001',
              attemptsSummary: [
                { attemptId: 'int_responsive_001', profileId: 'producer_summary', modelName: 'gemini-3.1-pro-preview', status: 'completed' },
              ],
              result: PHASE2_STUB,
              provenance: null,
              diagnostics: null,
              error: null,
            },
          },
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
  await page.getByRole('button', { name: /Run Analysis/i }).click();
  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByText('126', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('System Diagnostics')).toBeVisible();
});

test('tablet viewport (768px) renders results with readable metrics', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Run Analysis/i }).click();
  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByText('126', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('F minor', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('4/4', { exact: true }).first()).toBeVisible();
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

test('mobile viewport moves the model selector into the input panel and hides the toolbar CPU meter', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/', { waitUntil: 'networkidle' });

  await expect(page.getByText('SonicAnalyzer')).toBeVisible();
  await expect(page.getByLabel('AI INTERPRETATION')).toBeVisible();
  await expect(page.getByTestId('phase2-model-mobile')).toBeVisible();
  await expect(page.getByTestId('phase2-model-desktop')).not.toBeVisible();
  await expect(page.getByText('CPU')).not.toBeVisible();
});

test('desktop viewport shows model selector and CPU meter', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/', { waitUntil: 'networkidle' });

  await expect(page.getByText('SonicAnalyzer')).toBeVisible();
  await expect(page.getByTestId('phase2-model-desktop')).toBeVisible();
  await expect(page.getByTestId('phase2-model-mobile')).not.toBeVisible();
  await expect(page.getByText('CPU')).toBeVisible();
});

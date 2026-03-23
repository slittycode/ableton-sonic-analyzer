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
    lowMids: 0.0,
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
  return page.route('**/api/analysis-runs/estimate', async (route) => {
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
  return page.route('**/api/analysis-runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: requestId,
        requestedStages: {
          pitchNoteMode: 'off',
          pitchNoteBackend: 'auto',
          interpretationMode: 'off',
          interpretationProfile: 'producer_summary',
          interpretationModel: null,
        },
        artifacts: {
          sourceAudio: {
            artifactId: `${requestId}_artifact`,
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
            status: 'not_requested',
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
  });
}

function stubRunPoll(
  page: import('@playwright/test').Page,
  runId: string,
  options: {
    interpretationMode: 'off' | 'async';
    interpretationStatus: 'not_requested' | 'completed' | 'failed';
    interpretationResult?: Record<string, unknown> | null;
    interpretationError?: { code: string; message: string };
  },
) {
  return page.route(`**/api/analysis-runs/${runId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId,
        requestedStages: {
          pitchNoteMode: 'off',
          pitchNoteBackend: 'auto',
          interpretationMode: options.interpretationMode,
          interpretationProfile: 'producer_summary',
          interpretationModel: options.interpretationMode === 'off' ? null : 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: `${runId}_artifact`,
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
            status: options.interpretationStatus,
            authoritative: false,
            preferredAttemptId: options.interpretationStatus === 'completed' ? `${runId}_int` : null,
            attemptsSummary: options.interpretationStatus === 'completed'
              ? [{ attemptId: `${runId}_int`, profileId: 'producer_summary', modelName: 'gemini-3.1-pro-preview', status: 'completed' }]
              : [],
            result: options.interpretationResult ?? null,
            provenance: null,
            diagnostics: null,
            error: options.interpretationError
              ? { ...options.interpretationError, retryable: true, phase: 'interpretation' }
              : null,
          },
        },
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
  await stubRunPoll(page, 'req_phase2_degrade', {
    interpretationMode: 'off',
    interpretationStatus: 'not_requested',
  });

  await page.goto('/', { waitUntil: 'networkidle' });

  await expect(page.getByLabel('AI INTERPRETATION')).toBeDisabled();
  await expect(page.getByTestId('phase2-status-inline')).toHaveText('INTERPRETATION CONFIG OFF');
  await expect(page.getByTestId('phase2-model-desktop')).toBeDisabled();

  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Run Analysis/i }).click();

  await expectAnalysisResultsVisible(page);
  await expect(page.getByText('126')).toBeVisible();
  await expect(
    page.getByText('AI interpretation skipped because it was disabled by configuration.', { exact: true }).first(),
  ).toBeVisible();
});

test('turning Phase 2 off in the UI runs Phase 1 only and records the user-disabled reason', async ({ page }) => {
  await enablePhase2ForTest(page);
  await stubEstimateRoute(page, 'req_est_user_off');
  await stubAnalyzeRoute(page, 'req_user_off');
  await stubRunPoll(page, 'req_user_off', {
    interpretationMode: 'off',
    interpretationStatus: 'not_requested',
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByLabel('AI INTERPRETATION').uncheck();

  await expect(page.getByTestId('phase2-status-inline')).toHaveText('INTERPRETATION USER OFF');

  await page.getByRole('button', { name: /Run Analysis/i }).click();

  await expectAnalysisResultsVisible(page);
  await expect(
    page.getByText('AI interpretation skipped because it was disabled in the UI.', { exact: true }).first(),
  ).toBeVisible();
});

test('Phase 2 runs Phase 1 and delegates Gemini to the backend when enabled', async ({ page }) => {
  await enablePhase2ForTest(page);
  await stubEstimateRoute(page, 'req_est_p2_backend');
  await stubAnalyzeRoute(page, 'req_p2_backend');
  await stubRunPoll(page, 'req_p2_backend', {
    interpretationMode: 'async',
    interpretationStatus: 'completed',
    interpretationResult: {
      trackCharacter: 'Grounded interpretation output.',
      detectedCharacteristics: [],
      arrangementOverview: { summary: 'Four sections.', segments: [] },
      sonicElements: {
        kick: 'Kick',
        bass: 'Bass',
        melodicArp: 'Arp',
        grooveAndTiming: 'Groove',
        effectsAndTexture: 'Texture',
      },
      mixAndMasterChain: [],
      secretSauce: { title: 'Sauce', explanation: 'Do thing', implementationSteps: [] },
      confidenceNotes: [],
      abletonRecommendations: [],
    },
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());

  await page.getByRole('button', { name: /Run Analysis/i }).click();

  await expectAnalysisResultsVisible(page);
  await expect(page.getByText('126', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Sauce', exact: true })).toBeVisible();
});

test('malformed Gemini Phase 2 response degrades gracefully to skipped', async ({ page }) => {
  await enablePhase2ForTest(page);
  await stubEstimateRoute(page, 'req_est_p2_malformed');
  await stubAnalyzeRoute(page, 'req_p2_malformed');
  await stubRunPoll(page, 'req_p2_malformed', {
    interpretationMode: 'async',
    interpretationStatus: 'failed',
    interpretationError: {
      code: 'INTERPRETATION_FAILED',
      message: 'Gemini returned invalid JSON.',
    },
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await expect(page.getByLabel('AI INTERPRETATION')).toBeChecked();

  await page.getByRole('button', { name: /Run Analysis/i }).click();

  await expectAnalysisResultsVisible(page);
  await expect(page.getByText('126')).toBeVisible();
  await expect(page.getByText('System Diagnostics')).toBeVisible();
  await expect(
    page.getByText('Gemini returned invalid JSON.', { exact: true }).first(),
  ).toBeVisible();
});

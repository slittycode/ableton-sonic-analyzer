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

type RunSnapshotOverrides = {
  requestedStages?: Record<string, unknown>;
  stages?: {
    measurement?: Record<string, unknown>;
    symbolicExtraction?: Record<string, unknown>;
    interpretation?: Record<string, unknown>;
  };
};

function buildRunSnapshot(runId: string, overrides: RunSnapshotOverrides = {}) {
  return {
    runId,
    requestedStages: {
      symbolicMode: 'off',
      symbolicBackend: 'auto',
      interpretationMode: 'async',
      interpretationProfile: 'producer_summary',
      interpretationModel: 'gemini-3.1-pro-preview',
      ...overrides.requestedStages,
    },
    artifacts: {
      sourceAudio: {
        artifactId: `artifact_${runId}`,
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
        ...overrides.stages?.measurement,
      },
      symbolicExtraction: {
        status: 'not_requested',
        authoritative: false,
        preferredAttemptId: null,
        attemptsSummary: [],
        result: null,
        provenance: null,
        diagnostics: null,
        error: null,
        ...overrides.stages?.symbolicExtraction,
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
        ...overrides.stages?.interpretation,
      },
    },
  };
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

  await page.route('**/api/analysis-runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
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

  const errorBanner = page.locator('div.p-3.bg-error\\/10');
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner).toContainText('ERROR');
  await expect(errorBanner).toContainText('Internal server error during analysis.');

  await expect(page.getByText('System Diagnostics')).toBeVisible();
  await expect(page.getByText('BACKEND_INTERNAL_ERROR')).toBeVisible();
});

test('backend 502 (analyzer failed) shows error message in banner', async ({ page }) => {
  await stubEstimateRoute(page);

  await page.route('**/api/analysis-runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
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

  const errorBanner = page.locator('div.p-3.bg-error\\/10');
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner).toContainText('Analyzer subprocess exited with non-zero status.');

  await expect(page.getByText('System Diagnostics')).toBeVisible();
  await expect(page.getByText('ANALYZER_FAILED')).toBeVisible();
});

test('network failure shows NETWORK_UNREACHABLE-style error', async ({ page }) => {
  await stubEstimateRoute(page);

  await page.route('**/api/analysis-runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await route.abort('connectionrefused');
  });

  await loadFileAndClick(page);

  const errorBanner = page.locator('div.p-3.bg-error\\/10');
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner).toContainText('Cannot reach the local DSP backend');
});

test('estimate endpoint failure shows yellow warning but does not block analysis', async ({ page }) => {
  await page.route('**/api/analyze/estimate', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'text/plain',
      body: 'Internal Server Error',
    });
  });

  await page.route('**/api/analysis-runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildRunSnapshot('run_estimate_fallback')),
    });
  });

  await page.route('**/api/analysis-runs/run_estimate_fallback', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        buildRunSnapshot('run_estimate_fallback', {
          stages: {
            measurement: {
              status: 'completed',
              result: PHASE1_STUB,
              diagnostics: {
                timings: {
                  totalMs: 400,
                  analysisMs: 360,
                  serverOverheadMs: 40,
                  flagsUsed: [],
                  fileSizeBytes: 2048,
                  fileDurationSeconds: 10,
                  msPerSecondOfAudio: 40,
                },
              },
            },
            interpretation: {
              status: 'completed',
              preferredAttemptId: 'int_estimate_fallback',
              attemptsSummary: [
                {
                  attemptId: 'int_estimate_fallback',
                  profileId: 'producer_summary',
                  modelName: 'gemini-3.1-pro-preview',
                  status: 'completed',
                },
              ],
              result: PHASE2_STUB,
            },
          },
        }),
      ),
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

  await page.route('**/api/analysis-runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
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

  const errorBanner = page.locator('div.p-3.bg-error\\/10');
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner).toContainText('Server error for dismiss test.');
  await expect(errorBanner.getByRole('button', { name: /Retry/i })).toHaveCount(0);

  const dismissBtn = errorBanner.getByLabel('Dismiss error');
  await expect(dismissBtn).toBeVisible();
  await dismissBtn.click();

  await expect(errorBanner).toHaveCount(0);
});

test('error banner shows Retry button for retryable errors', async ({ page }) => {
  await stubEstimateRoute(page);

  let callCount = 0;
  await page.route('**/api/analysis-runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    callCount += 1;
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
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildRunSnapshot('run_retry_ok')),
    });
  });

  await page.route('**/api/analysis-runs/run_retry_ok', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        buildRunSnapshot('run_retry_ok', {
          stages: {
            measurement: {
              status: 'completed',
              result: PHASE1_STUB,
              diagnostics: {
                timings: {
                  totalMs: 200,
                  analysisMs: 180,
                  serverOverheadMs: 20,
                  flagsUsed: [],
                  fileSizeBytes: 2048,
                  fileDurationSeconds: 10,
                  msPerSecondOfAudio: 20,
                },
              },
            },
            interpretation: {
              status: 'completed',
              preferredAttemptId: 'int_retry_ok',
              attemptsSummary: [
                {
                  attemptId: 'int_retry_ok',
                  profileId: 'producer_summary',
                  modelName: 'gemini-3.1-pro-preview',
                  status: 'completed',
                },
              ],
              result: PHASE2_STUB,
            },
          },
        }),
      ),
    });
  });

  await loadFileAndClick(page);

  const errorBanner = page.locator('div.p-3.bg-error\\/10');
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner).toContainText('Backend temporarily unavailable.');

  const retryBtn = errorBanner.getByRole('button', { name: /Retry/i });
  await expect(retryBtn).toBeVisible();
  await retryBtn.click();

  await expect(page.getByText('Analysis Results')).toBeVisible({ timeout: 30000 });
});

test('stop monitoring during interpretation preserves completed measurement without showing an error banner', async ({ page }) => {
  await stubEstimateRoute(page);

  await page.route('**/api/analysis-runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildRunSnapshot('run_stop_monitoring')),
    });
  });

  await page.route('**/api/analysis-runs/run_stop_monitoring', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        buildRunSnapshot('run_stop_monitoring', {
          stages: {
            measurement: {
              status: 'completed',
              result: PHASE1_STUB,
              diagnostics: {
                timings: {
                  totalMs: 250,
                  analysisMs: 220,
                  serverOverheadMs: 30,
                  flagsUsed: [],
                  fileSizeBytes: 2048,
                  fileDurationSeconds: 10,
                  msPerSecondOfAudio: 25,
                },
              },
            },
            interpretation: {
              status: 'running',
              preferredAttemptId: 'int_stop_monitoring',
              attemptsSummary: [
                {
                  attemptId: 'int_stop_monitoring',
                  profileId: 'producer_summary',
                  modelName: 'gemini-3.1-pro-preview',
                  status: 'running',
                },
              ],
            },
          },
        }),
      ),
    });
  });

  await loadFileAndClick(page);

  await expect(page.getByText('Analysis Results')).toBeVisible();
  const signalPanel = page.getByTestId('signal-panel');
  await expect(signalPanel).toBeVisible();
  await expect(signalPanel.getByText('Signal Monitor').first()).toBeVisible();
  await expect(signalPanel.getByTestId('waveform-player')).toBeVisible();
  await expect(signalPanel.getByText('Canonical Stage Monitor')).toBeVisible();

  const playButton = signalPanel.getByTestId('waveform-play-toggle');
  await expect(playButton).toBeVisible();
  await expect(playButton).toBeEnabled({ timeout: 10000 });
  await playButton.click();
  await expect(playButton).toBeEnabled();

  const stopButton = page.getByRole('button', { name: /Stop monitoring/i });
  await expect(stopButton).toBeVisible();
  await stopButton.click();

  await expect(page.locator('div.p-3.bg-error\\/10')).toHaveCount(0);
  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByText('Monitoring stopped.')).toBeVisible();
});

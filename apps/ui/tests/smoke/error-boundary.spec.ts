import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Smoke coverage for the ErrorBoundary FALLBACK RENDER.
 *
 * Unit tests cover the boundary's capture logic (getDerivedStateFromError), but
 * not the fallback UI itself (Vitest is node-env). This drives the real
 * upload -> run -> results flow against a mocked backend, then ABORTS the lazy
 * AnalysisResults chunk request to force a load failure, and asserts the
 * ErrorBoundary fallback renders instead of a blank page. That chunk-load
 * failure is the production failure mode the boundary exists to contain.
 *
 * Model: tests/smoke/transcription-pianoroll.spec.ts (same mocked run-lifecycle
 * pattern). Smoke runs the Vite dev server (playwright.config.ts webServer), so
 * the lazy module is served unbundled at a stable, hashless path containing
 * "AnalysisResults".
 */

const testDir = path.dirname(fileURLToPath(import.meta.url));
const RUN_ID = 'run_smoke_error_boundary_001';

// Minimal valid Phase1Result — enough for the results surface (and thus the
// lazy AnalysisResults import) to mount once measurement completes.
const PHASE1_RESULT = {
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

const BASE_RUN = {
  runId: RUN_ID,
  requestedStages: {
    pitchNoteMode: 'off',
    pitchNoteBackend: 'auto',
    interpretationMode: 'off',
    interpretationProfile: 'producer_summary',
    interpretationModel: null,
  },
  artifacts: {
    sourceAudio: {
      artifactId: 'artifact_error_boundary_001',
      filename: 'silence.wav',
      mimeType: 'audio/wav',
      sizeBytes: 2048,
      contentSha256: 'abc123',
      path: 'uploads/test.wav',
    },
  },
};

const NOT_REQUESTED_STAGE = {
  status: 'not_requested',
  authoritative: false,
  preferredAttemptId: null,
  attemptsSummary: [],
  result: null,
  provenance: null,
  diagnostics: null,
  error: null,
};

async function stubEstimate(page: import('@playwright/test').Page) {
  let hits = 0;
  await page.route('**/api/analysis-runs/estimate', async (route) => {
    hits += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_estimate_error_boundary_001',
        estimate: {
          durationSeconds: 210.6,
          totalLowMs: 107000,
          totalHighMs: 203000,
          stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 }],
        },
      }),
    });
  });
  return () => hits;
}

/** Mocks create-run (POST) + a completed-measurement snapshot (GET). */
async function mockRunLifecycle(page: import('@playwright/test').Page) {
  await page.route('**/api/analysis-runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...BASE_RUN,
        stages: {
          measurement: { status: 'queued', authoritative: true, result: null, provenance: null, diagnostics: null, error: null },
          pitchNoteTranslation: NOT_REQUESTED_STAGE,
          interpretation: NOT_REQUESTED_STAGE,
        },
      }),
    });
  });

  await page.route(`**/api/analysis-runs/${RUN_ID}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...BASE_RUN,
        stages: {
          measurement: {
            status: 'completed',
            authoritative: true,
            result: PHASE1_RESULT,
            provenance: null,
            diagnostics: { timings: { totalMs: 980, analysisMs: 900, serverOverheadMs: 80, flagsUsed: [], fileSizeBytes: 2048, fileDurationSeconds: 210.6, msPerSecondOfAudio: 4.6 } },
            error: null,
          },
          pitchNoteTranslation: NOT_REQUESTED_STAGE,
          interpretation: NOT_REQUESTED_STAGE,
        },
      }),
    });
  });
}

test('ErrorBoundary fallback renders when the AnalysisResults chunk fails to load', async ({ page }) => {
  const getEstimateHits = await stubEstimate(page);
  await mockRunLifecycle(page);

  // Force the lazy AnalysisResults chunk to fail loading. Registered before
  // navigation so it intercepts the dynamic import when measurement completes.
  await page.route('**/AnalysisResults**', (route) => route.abort('failed'));

  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', path.resolve(testDir, './fixtures/silence.wav'));
  await expect.poll(() => getEstimateHits()).toBeGreaterThanOrEqual(1);
  await page.getByRole('button', { name: /Run Analysis/i }).click();

  // The boundary catches the lazy-import rejection and renders its recoverable
  // fallback — the app is NOT blanked.
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByText('The analysis results view failed to render')).toBeVisible();
  await expect(page.getByRole('button', { name: /Try again/i })).toBeVisible();
  await expect(page.getByRole('button', { name: /Reload page/i })).toBeVisible();
});

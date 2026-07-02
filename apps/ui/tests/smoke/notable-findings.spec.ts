import { test, expect, type Page } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const testDir = path.dirname(fileURLToPath(import.meta.url));
const RUN_ID = 'run_notable_findings_001';

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

const BASE_PHASE1 = {
  bpm: 126,
  bpmConfidence: 0.93,
  key: 'F minor',
  keyConfidence: 0.88,
  timeSignature: '4/4',
  durationSeconds: 210.6,
  lufsIntegrated: -12,
  truePeak: -3,
  plr: 9,
  crestFactor: 7,
  stereoWidth: 0.69,
  stereoCorrelation: 0.84,
  monoCompatible: true,
  spectralBalance: {
    subBass: -11,
    lowBass: -14,
    lowMids: -22,
    mids: -18,
    upperMids: -20,
    highs: -23,
    brilliance: -27,
  },
};

async function stubEstimateRoute(page: Page) {
  let hits = 0;
  await page.route('**/api/analysis-runs/estimate', async (route) => {
    hits += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_estimate_notable_findings',
        estimate: {
          durationSeconds: 210.6,
          totalLowMs: 22000,
          totalHighMs: 38000,
          stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 }],
        },
      }),
    });
  });
  return () => hits;
}

async function stubAnalysisRun(
  page: Page,
  { phase1Overrides = {} }: { phase1Overrides?: Record<string, unknown> } = {},
) {
  await page.route('**/api/analysis-runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: RUN_ID,
        requestedStages: {
          pitchNoteMode: 'off',
          pitchNoteBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_notable_findings',
            filename: 'silence.wav',
            mimeType: 'audio/wav',
            sizeBytes: 2048,
            contentSha256: 'abc123',
            path: 'uploads/test.wav',
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
  });

  await page.route(`**/api/analysis-runs/${RUN_ID}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: RUN_ID,
        requestedStages: {
          pitchNoteMode: 'off',
          pitchNoteBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_notable_findings',
            filename: 'silence.wav',
            mimeType: 'audio/wav',
            sizeBytes: 2048,
            contentSha256: 'abc123',
            path: 'uploads/test.wav',
          },
        },
        stages: {
          measurement: {
            status: 'completed',
            authoritative: true,
            result: { ...BASE_PHASE1, ...phase1Overrides },
            provenance: null,
            diagnostics: { timings: { totalMs: 980, analysisMs: 900, serverOverheadMs: 80, flagsUsed: [], fileSizeBytes: 2048, fileDurationSeconds: 10, msPerSecondOfAudio: 98 } },
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
            preferredAttemptId: 'int_notable_findings',
            attemptsSummary: [
              { attemptId: 'int_notable_findings', profileId: 'producer_summary', modelName: 'gemini-3.1-pro-preview', status: 'completed' },
            ],
            result: PHASE2_STUB,
            provenance: null,
            diagnostics: null,
            error: null,
          },
        },
      }),
    });
  });
}

async function uploadAndDriveToResults(page: Page, getEstimateHits: () => number) {
  await page.goto('/', { waitUntil: 'networkidle' });

  const fixturePath = path.resolve(testDir, './fixtures/silence.wav');
  await page.setInputFiles('#audio-upload', fixturePath);
  await expect.poll(() => getEstimateHits()).toBe(1);

  await expect(page.getByRole('button', { name: /Run Analysis/i })).toBeVisible();
  await page.getByRole('button', { name: /Run Analysis/i }).click();
  await expect(page.getByText('Analysis Results')).toBeVisible();
}

test('shows the Worth Checking panel when Phase 1 has a clipping defect', async ({ page }) => {
  const getEstimateHits = await stubEstimateRoute(page);
  await stubAnalysisRun(page, { phase1Overrides: { saturationDetail: { clippedSampleCount: 128 } } });

  await uploadAndDriveToResults(page, getEstimateHits);

  const panel = page.getByTestId('notable-findings');
  await expect(panel).toBeVisible();
  await expect(panel).toContainText('Master is clipping');
});

test('hides the Worth Checking panel on a clean track', async ({ page }) => {
  const getEstimateHits = await stubEstimateRoute(page);
  await stubAnalysisRun(page, {
    phase1Overrides: {
      saturationDetail: { clippedSampleCount: 0 },
      truePeak: -3,
      monoCompatible: true,
    },
  });

  await uploadAndDriveToResults(page, getEstimateHits);

  await expect(page.getByTestId('notable-findings')).toHaveCount(0);
});

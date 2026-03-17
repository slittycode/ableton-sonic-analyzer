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

test('upload + backend phase1 success renders analysis results', async ({ page }) => {
  await stubEstimateRoute(page);

  await page.route('**/api/analysis-runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: 'run_smoke_001',
        requestedStages: {
          symbolicMode: 'off',
          symbolicBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_smoke_001',
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
          symbolicExtraction: {
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

  await page.route('**/api/analysis-runs/run_smoke_001', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: 'run_smoke_001',
        requestedStages: {
          symbolicMode: 'off',
          symbolicBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_smoke_001',
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
            result: {
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
            provenance: null,
            diagnostics: { timings: { totalMs: 980, analysisMs: 900, serverOverheadMs: 80, flagsUsed: [], fileSizeBytes: 2048, fileDurationSeconds: 10, msPerSecondOfAudio: 98 } },
            error: null,
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
          },
          interpretation: {
            status: 'completed',
            authoritative: false,
            preferredAttemptId: 'int_smoke_001',
            attemptsSummary: [
              { attemptId: 'int_smoke_001', profileId: 'producer_summary', modelName: 'gemini-3.1-pro-preview', status: 'completed' },
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

  await page.goto('/', { waitUntil: 'networkidle' });

  const fixturePath = path.resolve(testDir, './fixtures/silence.wav');
  await page.setInputFiles('#audio-upload', fixturePath);

  await expect(page.getByRole('button', { name: /Initiate Analysis/i })).toBeVisible();
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByText('System Diagnostics')).toBeVisible();
  await expect(page.getByText('126', { exact: true }).first()).toBeVisible();
});

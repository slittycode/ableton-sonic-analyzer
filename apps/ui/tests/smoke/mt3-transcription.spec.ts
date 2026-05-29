import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { enableMt3ForTest } from './runtimeEnv';

/**
 * Smoke coverage for the MT3 polyphonic-transcription opt-in (frontend wiring).
 *
 * MT3 is gated behind VITE_ENABLE_MT3 (default OFF). The dev server the smoke
 * suite launches runs flag-off, so this test flips the runtime override via
 * `enableMt3ForTest` (addInitScript → window.__VITE_ENABLE_MT3_OVERRIDE__)
 * BEFORE `page.goto`, so config.ts reads it at module-eval. The test then:
 *   1. asserts the MT3 checkbox is reachable and toggling it makes the
 *      create-run POST body carry mt3_mode=enabled, and
 *   2. that a completed run whose mt3 stage carries tracks renders the
 *      Mt3TranscriptionPanel (additive view; Phase 1 stays authoritative).
 * AI interpretation is unchecked so no Gemini stub is needed; all stages in
 * the polled snapshot are terminal so the analyzer's poll loop returns.
 */

const testDir = path.dirname(fileURLToPath(import.meta.url));
const RUN_ID = 'run_smoke_mt3_001';

function hasMultipartTextField(body: string, fieldName: string, expected: string): boolean {
  const normalizedBody = body.replace(/\r?\n/g, '\n');
  const pattern = new RegExp(`name="${fieldName}"\\n\\n${expected}\\n`);
  return pattern.test(normalizedBody);
}

const MEASUREMENT_RESULT = {
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
  spectralBalance: { subBass: -0.7, lowBass: 1.2, lowMids: 0.0, mids: -0.3, upperMids: 0.4, highs: 1.0, brilliance: 0.8 },
};

// Full Mt3StageSnapshot — parseMt3Stage validates status + each attempt
// (attemptId, checkpointId) + result.version + each track.
const MT3_STAGE_COMPLETED = {
  status: 'completed',
  publicStatus: 'completed',
  authoritative: false,
  preferredAttemptId: 'mt3_smoke_001',
  attemptsSummary: [{ attemptId: 'mt3_smoke_001', checkpointId: 'magenta-mt3-base', status: 'completed' }],
  result: {
    version: 'mt3-py-0.1.0+magenta-mt3-base',
    stemsUsed: ['bass'],
    tracks: [
      { instrument: 'bass', midiArtifactId: 'artifact_mt3_bass', midiSizeBytes: 512, noteCount: 12, pitchRange: [36, 60] },
    ],
  },
  provenance: null,
  diagnostics: null,
  error: null,
};

const REQUESTED_STAGES = {
  pitchNoteMode: 'stem_notes',
  pitchNoteBackend: 'auto',
  interpretationMode: 'off',
  interpretationProfile: 'producer_summary',
  interpretationModel: null,
  mt3Mode: 'enabled',
};

const SOURCE_ARTIFACT = {
  artifactId: 'artifact_mt3_src_001',
  filename: 'silence.wav',
  mimeType: 'audio/wav',
  sizeBytes: 2048,
  contentSha256: 'abc123',
  path: 'uploads/test.wav',
};

async function stubEstimate(page: import('@playwright/test').Page) {
  let hits = 0;
  await page.route('**/api/analysis-runs/estimate', async (route) => {
    hits += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_estimate_mt3_001',
        estimate: {
          durationSeconds: 210.6,
          totalLowMs: 120000,
          totalHighMs: 240000,
          stages: [
            { key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 },
            { key: 'mt3_transcription', label: 'MT3 polyphonic transcription', lowMs: 60000, highMs: 120000 },
          ],
        },
      }),
    });
  });
  return () => hits;
}

test('MT3 opt-in sends mt3_mode=enabled and renders the transcription panel', async ({ page }) => {
  await enableMt3ForTest(page);
  const getEstimateHits = await stubEstimate(page);

  let createBody = '';
  await page.route('**/api/analysis-runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    createBody = route.request().postData() ?? '';
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: RUN_ID,
        requestedStages: REQUESTED_STAGES,
        artifacts: { sourceAudio: SOURCE_ARTIFACT },
        stages: {
          measurement: { status: 'queued', authoritative: true, result: null, provenance: null, diagnostics: null, error: null },
          pitchNoteTranslation: { status: 'blocked', authoritative: false, preferredAttemptId: null, attemptsSummary: [], result: null, provenance: null, diagnostics: null, error: null },
          interpretation: { status: 'not_requested', authoritative: false, preferredAttemptId: null, attemptsSummary: [], result: null, provenance: null, diagnostics: null, error: null },
          mt3: { status: 'blocked', publicStatus: 'queued', authoritative: false, preferredAttemptId: null, attemptsSummary: [], result: null, provenance: null, diagnostics: null, error: null },
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
        requestedStages: REQUESTED_STAGES,
        artifacts: { sourceAudio: SOURCE_ARTIFACT },
        stages: {
          measurement: {
            status: 'completed',
            authoritative: true,
            result: MEASUREMENT_RESULT,
            provenance: null,
            diagnostics: { timings: { totalMs: 980, analysisMs: 900, serverOverheadMs: 80, flagsUsed: [], fileSizeBytes: 2048, fileDurationSeconds: 10, msPerSecondOfAudio: 98 } },
            error: null,
          },
          // Terminal so isRunTerminal fires; null result is a valid completed state.
          pitchNoteTranslation: { status: 'completed', authoritative: false, preferredAttemptId: 'sym_mt3_001', attemptsSummary: [{ attemptId: 'sym_mt3_001', backendId: 'auto', mode: 'stem_notes', status: 'completed' }], result: null, provenance: null, diagnostics: null, error: null },
          interpretation: { status: 'not_requested', authoritative: false, preferredAttemptId: null, attemptsSummary: [], result: null, provenance: null, diagnostics: null, error: null },
          mt3: MT3_STAGE_COMPLETED,
        },
      }),
    });
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  const fixturePath = path.resolve(testDir, './fixtures/silence.wav');
  await page.setInputFiles('#audio-upload', fixturePath);

  // Uncheck AI INTERPRETATION (no Gemini stub needed); opt into MT3.
  await page.getByLabel('AI INTERPRETATION').uncheck();
  const mt3Toggle = page.getByLabel('MT3 POLYPHONIC TRANSCRIPTION');
  await expect(mt3Toggle).toBeVisible();
  await mt3Toggle.check();
  await expect(mt3Toggle).toBeChecked();

  await expect.poll(() => getEstimateHits()).toBeGreaterThanOrEqual(1);
  await page.getByRole('button', { name: /Run Analysis/i }).click();

  await expect(page.getByText('Analysis Results')).toBeVisible();

  // The create-run POST carried the opt-in.
  expect(hasMultipartTextField(createBody, 'mt3_mode', 'enabled')).toBe(true);

  // The MT3 stage result rendered the additive panel + per-track download.
  await expect(page.getByTestId('mt3-transcription-panel')).toBeVisible();
  await expect(page.getByTestId('mt3-download-bass')).toBeVisible();
});

test('MT3 checkbox is hidden when the VITE_ENABLE_MT3 flag is off', async ({ page }) => {
  // No enableMt3ForTest() — the dev server runs flag-off by default.
  await stubEstimate(page);
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', path.resolve(testDir, './fixtures/silence.wav'));

  await expect(page.getByLabel('PITCH/NOTE TRANSLATION')).toBeVisible();
  await expect(page.getByLabel('MT3 POLYPHONIC TRANSCRIPTION')).toHaveCount(0);
});

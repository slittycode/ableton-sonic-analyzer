import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { enableKeyCheckForTest } from './runtimeEnv';

/**
 * Key Check panel inside the real results view. The panel is behind
 * VITE_ENABLE_KEY_CHECK (default OFF); the first test flips the runtime
 * override before page.goto, the second confirms flag-off renders nothing.
 * Backend calls are stubbed; the measurement result carries the full-mode
 * key fields the panel reads (keyEnsemble, tuning, fundamentals key trust).
 */

const testDir = path.dirname(fileURLToPath(import.meta.url));
const RUN_ID = 'run_smoke_key_check_001';

const MEASUREMENT_RESULT = {
  bpm: 126,
  bpmConfidence: 0.93,
  key: 'F minor',
  keyConfidence: 0.88,
  keyEnsemble: {
    method: 'profile_vote.v1',
    agreement: 2,
    profiles: [
      { profile: 'edma', key: 'F minor', strength: 0.88 },
      { profile: 'temperley', key: 'F minor', strength: 0.8 },
      { profile: 'krumhansl', key: 'Ab major', strength: 0.71 },
    ],
    alternates: [{ key: 'Ab major', strength: 0.71 }],
  },
  tuningFrequency: 438.2,
  tuningCents: -7.1,
  fundamentalsQuality: {
    schemaVersion: 'fundamentals-quality.v1',
    targetProfile: 'electronic_ableton_v1',
    analysisMode: 'full',
    localOnly: true,
    llmExcluded: true,
    overallStatus: 'authoritative',
    domains: {
      key: {
        status: 'authoritative',
        plainEnglish: 'Key was measured locally.',
        source: 'edma',
        confidence: 0.88,
        evidence: { key: 'F minor' },
      },
    },
  },
  timeSignature: '4/4',
  durationSeconds: 210.6,
  lufsIntegrated: -7.9,
  truePeak: -0.2,
  stereoWidth: 0.69,
  stereoCorrelation: 0.84,
  spectralBalance: { subBass: -0.7, lowBass: 1.2, lowMids: 0.0, mids: -0.3, upperMids: 0.4, highs: 1.0, brilliance: 0.8 },
};

const NOT_REQUESTED = {
  status: 'not_requested',
  authoritative: false,
  preferredAttemptId: null,
  attemptsSummary: [],
  result: null,
  provenance: null,
  diagnostics: null,
  error: null,
};

function runSnapshot(measurementStatus: 'queued' | 'completed') {
  return {
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
        artifactId: 'artifact_key_check_001',
        filename: 'silence.wav',
        mimeType: 'audio/wav',
        sizeBytes: 2048,
        contentSha256: 'abc123',
        path: 'uploads/test.wav',
      },
    },
    stages: {
      measurement: {
        status: measurementStatus,
        authoritative: true,
        result: measurementStatus === 'completed' ? MEASUREMENT_RESULT : null,
        provenance: null,
        diagnostics: null,
        error: null,
      },
      pitchNoteTranslation: NOT_REQUESTED,
      interpretation: NOT_REQUESTED,
    },
  };
}

async function runStubbedAnalysis(page: Page) {
  await page.route('**/api/analysis-runs/estimate', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_key_check_estimate',
        estimate: {
          durationSeconds: 210.6,
          totalLowMs: 22000,
          totalHighMs: 38000,
          stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 }],
        },
      }),
    }),
  );
  await page.route('**/api/analysis-runs', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(runSnapshot('queued')) })
      : route.fallback(),
  );
  await page.route(`**/api/analysis-runs/${RUN_ID}`, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(runSnapshot('completed')) }),
  );

  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', path.resolve(testDir, './fixtures/silence.wav'));
  await page.getByLabel('AI INTERPRETATION').uncheck(); // no Gemini stub needed
  await page.getByRole('button', { name: /Run Analysis/i }).click();
  await expect(page.getByTestId('analysis-results-root')).toBeVisible();
}

test('Key Check panel shows the measured key and plays the keyboard + drone', async ({ page }) => {
  await enableKeyCheckForTest(page);
  await runStubbedAnalysis(page);

  const panel = page.getByTestId('key-check-panel');
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId('key-check-measured-key')).toHaveText('F minor');
  await expect(panel).toContainText('LOCAL');
  await expect(panel).toContainText('2 of 3 agree');
  await expect(panel).toContainText('Ab major');
  await expect(panel).toContainText('438.2');
  await expect(panel).toContainText('F minor and Ab major share every note');
  await expect(panel).not.toContainText('[object Object]');

  await panel.getByTestId('key-check-open').click();
  await expect(panel.getByTestId('key-check-instrument')).toBeVisible();

  // F minor: Bb (70) is in scale, B (71) is not; F (65) is the tonic.
  const keyboard = panel.getByTestId('key-check-keyboard');
  await expect(keyboard.locator('[data-midi="70"]')).toHaveAttribute('data-in-scale', 'true');
  await expect(keyboard.locator('[data-midi="71"]')).toHaveAttribute('data-in-scale', 'false');
  await expect(keyboard.locator('[data-midi="65"]')).toHaveAttribute('aria-label', /tonic/);

  // Pointer press lights the key while held.
  const f4 = keyboard.locator('[data-midi="65"]');
  const box = (await f4.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height - 12);
  await page.mouse.down();
  await expect(f4).toHaveAttribute('aria-pressed', 'true');
  await page.mouse.up();
  await expect(f4).toHaveAttribute('aria-pressed', 'false');

  // Tonic drone holds F3 + C4 (tonic + fifth), and follows the alternate key.
  await panel.getByTestId('key-check-drone').click();
  await expect(keyboard.locator('[data-midi="53"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(keyboard.locator('[data-midi="60"]')).toHaveAttribute('aria-pressed', 'true');
  await panel.getByRole('button', { name: /Ab major · alternate/i }).click();
  await expect(keyboard.locator('[data-midi="56"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(keyboard.locator('[data-midi="53"]')).toHaveAttribute('aria-pressed', 'false');
  await panel.getByTestId('key-check-drone').click();
  await expect(keyboard.locator('[aria-pressed="true"]')).toHaveCount(0);
});

test('Key Check panel stays hidden while the flag is off', async ({ page }) => {
  await runStubbedAnalysis(page);
  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByTestId('key-check-panel')).toHaveCount(0);
});

import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const testDir = path.dirname(fileURLToPath(import.meta.url));
const uiPackage = JSON.parse(
  fs.readFileSync(path.resolve(testDir, '../../package.json'), 'utf8'),
) as { version: string };
const uiVersionLabel = `v${uiPackage.version}`;

const buildStepPattern = (
  bars: number,
  primarySteps: number[],
  primaryValue: number,
  secondaryValue = 0,
): number[] =>
  Array.from({ length: bars * 16 }, (_, index) => {
    const stepInBar = index % 16;
    if (primarySteps.includes(stepInBar)) return primaryValue;
    return secondaryValue;
  });

const PHASE1_STUB = {
  bpm: 126,
  bpmConfidence: 0.93,
  key: 'F minor',
  keyConfidence: 0.88,
  timeSignature: '4/4',
  timeSignatureSource: 'assumed_four_four',
  timeSignatureConfidence: 0,
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
  grooveDetail: {
    kickSwing: 0.47,
    hihatSwing: 0.46,
    kickAccent: [1.0, 0.2, 0.9, 0.1],
    hihatAccent: [0.2, 0.8, 0.6, 1.0],
  },
  beatsLoudness: {
    kickDominantRatio: 0.62,
    midDominantRatio: 0.18,
    highDominantRatio: 0.2,
    patternBeatsPerBar: 4,
    lowBandAccentPattern: [1.0, 0.24, 0.82, 0.16],
    midBandAccentPattern: [0.22, 1.0, 0.34, 0.28],
    highBandAccentPattern: [0.3, 0.88, 1.0, 0.92],
    overallAccentPattern: [1.0, 0.55, 0.92, 0.61],
    accentPattern: [1.0, 0.55, 0.92, 0.61],
    meanBeatLoudness: 0.42,
    beatLoudnessVariation: 0.83,
    beatCount: 362,
  },
  rhythmTimeline: {
    beatsPerBar: 4,
    stepsPerBeat: 4,
    availableBars: 16,
    selectionMethod: 'representative_dsp_window',
    windows: [
      {
        bars: 8,
        startBar: 5,
        endBar: 12,
        lowBandSteps: buildStepPattern(8, [0, 8], 1.0),
        midBandSteps: buildStepPattern(8, [4, 12], 0.72),
        highBandSteps: buildStepPattern(8, [0, 2, 4, 6, 8, 10, 12, 14], 0.38, 0.14),
        overallSteps: buildStepPattern(8, [0, 4, 8, 12], 0.92, 0.2),
      },
      {
        bars: 16,
        startBar: 1,
        endBar: 16,
        lowBandSteps: buildStepPattern(16, [0, 8], 1.0),
        midBandSteps: buildStepPattern(16, [4, 12], 0.72),
        highBandSteps: buildStepPattern(16, [0, 2, 4, 6, 8, 10, 12, 14], 0.38, 0.14),
        overallSteps: buildStepPattern(16, [0, 4, 8, 12], 0.92, 0.2),
      },
    ],
  },
};

const PHASE2_STUB = {
  trackCharacter: 'Deterministic smoke response.',
  detectedCharacteristics: [],
  arrangementOverview: { summary: 'Smoke summary.', segments: [] },
  audioObservations: {
    soundDesignFingerprint: 'Smoke fingerprint from the audio path.',
    elementCharacter: [
      {
        element: 'Kick',
        description: 'Smoke-test kick description.',
      },
    ],
    productionSignatures: ['Smoke-test transition delay.'],
    mixContext: 'Smoke-test mix context.',
  },
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
          requestId: 'req_est_ui',
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
          runId: 'run_ui_001',
          requestedStages: {
            pitchNoteMode: 'off',
            pitchNoteBackend: 'auto',
            interpretationMode: 'async',
            interpretationProfile: 'producer_summary',
            interpretationModel: 'gemini-3.1-pro-preview',
          },
          artifacts: {
            sourceAudio: {
              artifactId: 'artifact_ui_001',
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
    page.route('**/api/analysis-runs/run_ui_001', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          runId: 'run_ui_001',
          requestedStages: {
            pitchNoteMode: 'off',
            pitchNoteBackend: 'auto',
            interpretationMode: 'async',
            interpretationProfile: 'producer_summary',
            interpretationModel: 'gemini-3.1-pro-preview',
          },
          artifacts: {
            sourceAudio: {
              artifactId: 'artifact_ui_001',
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
              preferredAttemptId: 'int_ui_001',
              attemptsSummary: [
                { attemptId: 'int_ui_001', profileId: 'producer_summary', modelName: 'gemini-3.1-pro-preview', status: 'completed' },
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

test('NO SIGNAL DETECTED placeholder is shown before any file is loaded', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });
  await expect(page.getByText('NO SIGNAL DETECTED')).toBeVisible();
});

test('NO SIGNAL DETECTED disappears when a file is selected', async ({ page }) => {
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await expect(page.getByText('NO SIGNAL DETECTED')).toBeVisible();
  await page.setInputFiles('#audio-upload', fixturePath());
  await expect(page.getByText('NO SIGNAL DETECTED')).toHaveCount(0);
});

test('CPU indicator bar is visible in the header', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });
  await expect(page.getByTestId('app-toolbar').getByText(/^CPU$/)).toBeVisible();
});

test('CPU indicator animates during analysis', async ({ page }) => {
  await page.route('**/api/analysis-runs/estimate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_est_cpu',
        estimate: {
          durationSeconds: 10,
          totalLowMs: 22000,
          totalHighMs: 38000,
          stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 }],
        },
      }),
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
      body: JSON.stringify({
        runId: 'run_cpu_001',
        requestedStages: {
          pitchNoteMode: 'off',
          pitchNoteBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_cpu_001',
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
  });

  let pollCount = 0;
  await page.route('**/api/analysis-runs/run_cpu_001', async (route) => {
    pollCount += 1;
    if (pollCount === 1) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: 'run_cpu_001',
        requestedStages: {
          pitchNoteMode: 'off',
          pitchNoteBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_cpu_001',
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
            preferredAttemptId: 'int_cpu_001',
            attemptsSummary: [
              { attemptId: 'int_cpu_001', profileId: 'producer_summary', modelName: 'gemini-3.1-pro-preview', status: 'completed' },
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
  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Run Analysis/i }).click();

  await expect(page.getByTestId('app-toolbar').getByText(/^CPU$/)).toBeVisible();

  const cpuBar = page.getByTestId('cpu-meter-fill');
  await expect(cpuBar).toBeVisible();

  await expect(page.getByText('Analysis Results')).toBeVisible();
});

test('rhythm section renders the DSP-grounded 8-bar sequencer and can expand to 16 bars', async ({ page }) => {
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Run Analysis/i }).click();

  await expect(page.getByText('Analysis Results')).toBeVisible();
  const rhythmPanel = page.getByTestId('rhythm-grid-panel');
  await expect(rhythmPanel.getByText('Rhythm Grid')).toBeVisible();
  await expect(rhythmPanel.getByText('LOW BAND')).toBeVisible();
  await expect(rhythmPanel.getByText('MID BAND')).toBeVisible();
  await expect(rhythmPanel.getByText('HIGH BAND')).toBeVisible();
  await expect(rhythmPanel.getByText('OVERALL ACCENT')).toBeVisible();
  await expect(rhythmPanel.getByText('DSP band-energy lanes. Frequency-band proxies, not isolated stems.')).toBeVisible();
  await expect(page.getByTestId('rhythm-grid-window-8')).toBeVisible();
  await expect(page.getByTestId('rhythm-grid-window-16')).toBeVisible();
  await expect(rhythmPanel.getByTestId('rhythm-grid-bar-5')).toBeVisible();
  await expect(rhythmPanel.getByTestId('rhythm-grid-bar-12')).toBeVisible();
  await page.getByTestId('rhythm-grid-window-16').click();
  await expect(rhythmPanel.getByTestId('rhythm-grid-bar-1')).toBeVisible();
  await expect(rhythmPanel.getByTestId('rhythm-grid-bar-16')).toBeVisible();
  await expect(page.getByRole('button', { name: 'grid' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'energy' })).toHaveCount(0);
});

test('diagnostic log shows SUCCESS badge and model info after analysis', async ({ page }) => {
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Run Analysis/i }).click();

  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByText('System Diagnostics')).toBeVisible();

  const diagnostics = page.locator('.mt-12.space-y-4');
  const successBadge = diagnostics.locator('.bg-success\\/10').filter({ hasText: 'SUCCESS' }).first();
  await expect(successBadge).toBeVisible();

  await expect(page.getByText('local-dsp-engine')).toBeVisible();

  // Scope to the diagnostics section to avoid matching the FileUpload file card
  await expect(diagnostics.getByText('silence.wav')).toBeVisible();
  await expect(diagnostics.getByText('audio/wav')).toBeVisible();
});

test('top metric cards show TEMPO, KEY SIG, METER, CHARACTER after analysis', async ({ page }) => {
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Run Analysis/i }).click();

  await expect(page.getByText('Analysis Results')).toBeVisible();

  await expect(page.getByText('TEMPO', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('KEY SIG', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('METER', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('CHARACTER', { exact: true }).first()).toBeVisible();

  await expect(page.getByText('126', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('F minor', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('4/4', { exact: true }).first()).toBeVisible();
});

test('header shows SonicAnalyzer brand and Local DSP Engine version label', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });
  await expect(page.getByText('SonicAnalyzer')).toBeVisible();
  await expect(page.getByText('Local DSP Engine')).toBeVisible();
  await expect(page.getByText(uiVersionLabel)).toBeVisible();
});

test('JSON_DATA and REPORT_MD buttons are visible after analysis', async ({ page }) => {
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Run Analysis/i }).click();

  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByRole('button', { name: /JSON_DATA/i })).toBeVisible();
  await expect(page.getByRole('button', { name: /REPORT_MD/i })).toBeVisible();
});

test('audio observations panel appears when the interpretation includes perceptual notes', async ({ page }) => {
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Run Analysis/i }).click();

  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByText('Audio Observations')).toBeVisible();
  await expect(page.getByText('Perceptual / Audio-Derived')).toBeVisible();
  await expect(page.getByText('Smoke fingerprint from the audio path.')).toBeVisible();
});

test('diagnostic log can be collapsed and expanded via toggle button', async ({ page }) => {
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Run Analysis/i }).click();

  await expect(page.getByText('Analysis Results')).toBeVisible();

  // Toggle button should be visible with aria-expanded
  const toggleBtn = page.getByLabel('Toggle diagnostic log');
  await expect(toggleBtn).toBeVisible();
  await expect(toggleBtn).toHaveAttribute('aria-expanded', 'true');

  // Log content should be visible (expanded by default after analysis)
  const logContent = page.locator('.mt-12.space-y-4 .bg-bg-surface-darker');
  await expect(logContent).toBeVisible();

  // Click to collapse
  await toggleBtn.click();
  await expect(toggleBtn).toHaveAttribute('aria-expanded', 'false');
  await expect(logContent).toHaveCount(0);

  // Click to expand again
  await toggleBtn.click();
  await expect(toggleBtn).toHaveAttribute('aria-expanded', 'true');
  await expect(logContent).toBeVisible();
});

test('diagnostic log entry count is shown in toggle header', async ({ page }) => {
  await stubRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Run Analysis/i }).click();

  await expect(page.getByText('Analysis Results')).toBeVisible();

  // Should show entry count (at least "1 entry" or "2 entries" depending on Phase 2)
  const toggleBtn = page.getByLabel('Toggle diagnostic log');
  await expect(toggleBtn).toContainText(/\d+ entr/);
});

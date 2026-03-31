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

function fixturePath(): string {
  return path.resolve(testDir, './fixtures/silence.wav');
}

function stubBackendRoutes(page: import('@playwright/test').Page) {
  return Promise.all([
    page.route('**/api/analysis-runs/estimate', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          requestId: 'req_est_file',
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
          runId: 'run_file_validation_001',
          requestedStages: {
            pitchNoteMode: 'stem_notes',
            pitchNoteBackend: 'auto',
            interpretationMode: 'async',
            interpretationProfile: 'producer_summary',
            interpretationModel: 'gemini-3.1-pro-preview',
          },
          artifacts: {
            sourceAudio: {
              artifactId: 'artifact_file_validation_001',
              filename: 'silence.wav',
              mimeType: 'audio/wav',
              sizeBytes: 2048,
              contentSha256: 'abc123',
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
              status: 'blocked',
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
    page.route('**/api/analysis-runs/run_file_validation_001', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          runId: 'run_file_validation_001',
          requestedStages: {
            pitchNoteMode: 'stem_notes',
            pitchNoteBackend: 'auto',
            interpretationMode: 'async',
            interpretationProfile: 'producer_summary',
            interpretationModel: 'gemini-3.1-pro-preview',
          },
          artifacts: {
            sourceAudio: {
              artifactId: 'artifact_file_validation_001',
              filename: 'silence.wav',
              mimeType: 'audio/wav',
              sizeBytes: 2048,
              contentSha256: 'abc123',
            },
          },
          stages: {
            measurement: {
              status: 'completed',
              authoritative: true,
              result: PHASE1_STUB,
              provenance: null,
              diagnostics: {
                timings: {
                  totalMs: 980,
                  analysisMs: 900,
                  serverOverheadMs: 80,
                  flagsUsed: [],
                  fileSizeBytes: 2048,
                  fileDurationSeconds: 10,
                  msPerSecondOfAudio: 98,
                },
              },
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
              preferredAttemptId: 'int_file_validation_001',
              attemptsSummary: [
                {
                  attemptId: 'int_file_validation_001',
                  profileId: 'producer_summary',
                  modelName: 'gemini-3.1-pro-preview',
                  status: 'completed',
                },
              ],
              result: {
                trackCharacter: 'Deterministic file validation smoke response.',
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
              },
              provenance: null,
              diagnostics: null,
              error: null,
            },
          },
        }),
      });
    }),
    // Stub Gemini so Phase 2 completes quickly when enabled
    page.route('**://generativelanguage.googleapis.com/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ candidates: [] }),
      });
    }),
  ]);
}

test('clear button removes file and returns to upload drop zone', async ({ page }) => {
  await stubBackendRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await expect(page.getByText('Drop Audio Here')).toBeVisible();

  await page.setInputFiles('#audio-upload', fixturePath());
  await expect(page.getByText('silence.wav')).toBeVisible();
  await expect(page.getByText(/Ready/)).toBeVisible();

  const clearButton = page.getByTitle('Remove File');
  await expect(clearButton).toBeVisible();
  await clearButton.click();

  await expect(page.getByText('Drop Audio Here')).toBeVisible();
  await expect(page.getByText('silence.wav')).toHaveCount(0);
});

test('re-upload after results resets to file-selected state', async ({ page }) => {
  await stubBackendRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await page.setInputFiles('#audio-upload', fixturePath());
  await page.getByRole('button', { name: /Run Analysis/i }).click();
  await expect(page.getByText('Analysis Results')).toBeVisible();

  // Wait for analysis to fully complete (including Phase 2 if enabled)
  // so that isAnalyzing=false and the clear button becomes visible.
  const clearBtn = page.getByTitle('Remove File');
  await expect(clearBtn).toBeVisible({ timeout: 30000 });
  await clearBtn.click();
  await expect(page.getByText('Drop Audio Here')).toBeVisible();
  await page.setInputFiles('#audio-upload', fixturePath());

  await expect(page.getByText('silence.wav')).toBeVisible();
  await expect(page.getByRole('button', { name: /Run Analysis/i })).toBeVisible();
  await expect(page.getByText('Analysis Results')).toHaveCount(0);
});

test('file size is displayed in MB after selecting a file', async ({ page }) => {
  await stubBackendRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await page.setInputFiles('#audio-upload', fixturePath());

  await expect(page.getByText(/\d+\.\d+ MB/)).toBeVisible();
});

test('file picker accepts blank-mime WAV uploads via extension fallback', async ({ page }) => {
  await stubBackendRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await page.setInputFiles('#audio-upload', {
    name: 'mystery.wav',
    mimeType: '',
    buffer: Buffer.from('RIFF'),
  });

  await expect(page.getByText('mystery.wav')).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('drag-and-drop accepts blank-mime FLAC uploads via extension fallback', async ({ page }) => {
  await stubBackendRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await page.evaluate(() => {
    const dropZone = document.getElementById('audio-upload')?.parentElement;
    if (!dropZone) throw new Error('Upload drop zone not found.');

    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(new File(['fLaC'], 'mystery.flac', { type: '' }));
    const dropEvent = new DragEvent('drop', {
      bubbles: true,
      cancelable: true,
      dataTransfer,
    });

    dropZone.dispatchEvent(dropEvent);
  });

  await expect(page.getByText('mystery.flac')).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('global drag overlay appears for valid audio files and global drop replaces the current file', async ({ page }) => {
  await stubBackendRoutes(page);
  await page.goto('/', { waitUntil: 'networkidle' });

  await page.setInputFiles('#audio-upload', fixturePath());
  await expect(page.getByText('silence.wav')).toBeVisible();

  await page.evaluate(() => {
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(new File(['RIFF'], 'replacement.wav', { type: 'audio/wav' }));

    document.dispatchEvent(
      new DragEvent('dragenter', {
        bubbles: true,
        cancelable: true,
        dataTransfer,
      }),
    );
  });

  await expect(page.getByText('Drop Audio Here')).toBeVisible();

  await page.evaluate(() => {
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(new File(['RIFF'], 'replacement.wav', { type: 'audio/wav' }));

    document.dispatchEvent(
      new DragEvent('drop', {
        bubbles: true,
        cancelable: true,
        dataTransfer,
      }),
    );
  });

  await expect(page.getByText('replacement.wav')).toBeVisible();
  await expect(page.getByText('silence.wav')).toHaveCount(0);
});

test('load demo track fetches demo.mp3 into the upload flow', async ({ page }) => {
  await stubBackendRoutes(page);
  await page.route('**/demo.mp3', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'audio/mpeg',
      body: Buffer.from('ID3'),
    });
  });

  await page.goto('/', { waitUntil: 'networkidle' });

  await page.getByRole('button', { name: /Load Demo Track/i }).click();

  await expect(page.getByText('demo.mp3')).toBeVisible();
  await expect(page.getByText(/Ready/)).toBeVisible();
});

test('format badges (MP3, WAV, FLAC, AIFF) are visible on the drop zone', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });

  for (const format of ['MP3', 'WAV', 'FLAC', 'AIFF']) {
    await expect(page.getByText(format, { exact: true })).toBeVisible();
  }
});

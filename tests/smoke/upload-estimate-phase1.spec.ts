import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const testDir = path.dirname(fileURLToPath(import.meta.url));

function hasMultipartBoolean(body: string, fieldName: string, expected: boolean): boolean {
  const normalizedBody = body.replace(/\r?\n/g, '\n');
  const pattern = new RegExp(`name="${fieldName}"\\n\\n${expected ? 'true' : 'false'}\\n`);
  return pattern.test(normalizedBody);
}

test('upload shows estimate and local DSP processing copy before phase1 completes', async ({ page }) => {
  await page.route('**/api/analyze/estimate', async (route) => {
    const body = route.request().postData() ?? '';
    const transcribeEnabled = hasMultipartBoolean(body, 'transcribe', true);
    const stemSeparationEnabled = hasMultipartBoolean(body, 'separate', true);
    const estimate =
      transcribeEnabled && stemSeparationEnabled
        ? {
            totalLowMs: 107000,
            totalHighMs: 203000,
            stages: [
              {
                key: 'local_dsp',
                label: 'Local DSP analysis',
                lowMs: 22000,
                highMs: 38000,
              },
              {
                key: 'demucs_separation',
                label: 'Demucs separation',
                lowMs: 45000,
                highMs: 90000,
              },
              {
                key: 'transcription_stems',
                label: 'Basic Pitch on bass + other stems',
                lowMs: 40000,
                highMs: 75000,
              },
            ],
          }
        : transcribeEnabled
          ? {
              totalLowMs: 47000,
              totalHighMs: 113000,
              stages: [
                {
                  key: 'local_dsp',
                  label: 'Local DSP analysis',
                  lowMs: 22000,
                  highMs: 38000,
                },
                {
                  key: 'transcription_full_mix',
                  label: 'Basic Pitch on full mix',
                  lowMs: 25000,
                  highMs: 75000,
                },
              ],
            }
          : {
              totalLowMs: 22000,
              totalHighMs: 38000,
              stages: [
                {
                  key: 'local_dsp',
                  label: 'Local DSP analysis',
                  lowMs: 22000,
                  highMs: 38000,
                },
              ],
            };

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_estimate_smoke_001',
        estimate: {
          durationSeconds: 214.6,
          ...estimate,
        },
      }),
    });
  });

  await page.route('**/api/analyze', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_smoke_002',
        phase1: {
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
        diagnostics: {
          backendDurationMs: 980,
          engineVersion: 'smoke',
          estimatedLowMs: 22000,
          estimatedHighMs: 38000,
        },
      }),
    });
  });

  await page.goto('/', { waitUntil: 'networkidle' });

  const fixturePath = path.resolve(testDir, './fixtures/silence.wav');
  await page.setInputFiles('#audio-upload', fixturePath);

  await expect(page.getByText('Phase 2 Model')).toBeVisible();
  await expect(page.getByText(/Estimated local analysis/i)).toBeVisible();
  await expect(page.getByText('22s-38s')).toBeVisible();

  const transcribeToggle = page.getByLabel('MIDI TRANSCRIPTION');
  const stemToggle = page.getByLabel('STEM SEPARATION');

  await expect(transcribeToggle).not.toBeChecked();
  await expect(stemToggle).toBeDisabled();

  await transcribeToggle.check();
  await expect(stemToggle).toBeEnabled();
  await expect(page.getByText('47s-113s')).toBeVisible();

  await stemToggle.check();
  await expect(page.getByText('107s-203s')).toBeVisible();

  await transcribeToggle.uncheck();
  await expect(stemToggle).toBeDisabled();
  await expect(stemToggle).not.toBeChecked();
  await expect(page.getByText('22s-38s')).toBeVisible();

  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  await expect(page.getByRole('heading', { name: 'Phase 1: Local DSP analysis' })).toBeVisible();
  await expect(page.getByText('Request in flight').first()).toBeVisible();
  await expect(page.getByText('Analysis Results')).toBeVisible();
});

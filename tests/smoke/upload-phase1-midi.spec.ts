import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const testDir = path.dirname(fileURLToPath(import.meta.url));

test('phase1 melody detail renders session musician panel', async ({ page }) => {
  await page.route('**/api/analyze', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_smoke_midi_001',
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
          melodyDetail: {
            noteCount: 3,
            notes: [
              { midi: 60, onset: 0.2, duration: 0.3 },
              { midi: 64, onset: 0.8, duration: 0.2 },
              { midi: 67, onset: 1.2, duration: 0.4 },
            ],
            dominantNotes: [60, 64, 67],
            pitchRange: { min: 60, max: 67 },
            pitchConfidence: 0.72,
            midiFile: null,
            sourceSeparated: true,
            vibratoPresent: false,
            vibratoExtent: 0,
            vibratoRate: 0,
            vibratoConfidence: 0.1,
          },
        },
        diagnostics: {
          backendDurationMs: 980,
          engineVersion: 'smoke-midi',
        },
      }),
    });
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  const fixturePath = path.resolve(testDir, './fixtures/silence.wav');
  await page.setInputFiles('#audio-upload', fixturePath);
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  const panel = page.locator('section').filter({ hasText: /SESSION MUSICIAN/i }).first();

  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(panel.getByRole('heading', { name: /SESSION MUSICIAN/i }).first()).toBeVisible();
  await expect(panel.getByText('Audio to MIDI transcription')).toBeVisible();
  await expect(panel.getByRole('button', { name: /Download \.mid/i })).toBeVisible();
  const swingSlider = panel.locator('input[type="range"]');
  await expect(swingSlider).toBeDisabled();

  await panel.getByRole('button', { name: '1/16 note' }).click();
  await expect(swingSlider).toBeEnabled();

  await panel.getByRole('button', { name: /Collapse session musician panel/i }).click();
  await expect(panel.getByRole('button', { name: '1/16 note' })).toHaveCount(0);

  await panel.getByRole('button', { name: /Expand session musician panel/i }).click();
  await expect(panel.getByRole('button', { name: '1/16 note' })).toBeVisible();
});

test('missing melodyDetail shows MIDI unavailable state', async ({ page }) => {
  await page.route('**/api/analyze', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_smoke_midi_awaiting_001',
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
          engineVersion: 'smoke-midi-awaiting',
        },
      }),
    });
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  const fixturePath = path.resolve(testDir, './fixtures/silence.wav');
  await page.setInputFiles('#audio-upload', fixturePath);
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  const panel = page.locator('section').filter({ hasText: /SESSION MUSICIAN/i }).first();
  await expect(panel.getByText('MIDI TRANSCRIPTION UNAVAILABLE')).toBeVisible();
  await expect(
    panel.getByText('Re-run analysis with FLAC source for melody extraction, or paste DSP JSON with melodyDetail field populated'),
  ).toBeVisible();
  await expect(panel.getByRole('button', { name: /Preview/i })).toBeDisabled();
  await expect(panel.getByRole('button', { name: /Download \.mid/i })).toBeDisabled();
});

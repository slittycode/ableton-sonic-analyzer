import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const testDir = path.dirname(fileURLToPath(import.meta.url));

function hasMultipartBoolean(body: string, fieldName: string, expected: boolean): boolean {
  const normalizedBody = body.replace(/\r?\n/g, '\n');
  const pattern = new RegExp(`name="${fieldName}"\\n\\n${expected ? 'true' : 'false'}\\n`);
  return pattern.test(normalizedBody);
}

async function stubGeminiPhase2(page: import('@playwright/test').Page) {
  await page.route('**://generativelanguage.googleapis.com/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        candidates: [
          {
            content: {
              role: 'model',
              parts: [
                {
                  text: JSON.stringify({
                    trackCharacter: 'Deterministic smoke response.',
                    detectedCharacteristics: [
                      { name: 'Stereo Discipline', confidence: 'HIGH', explanation: 'Controlled width.' },
                    ],
                    arrangementOverview: {
                      summary: 'Smoke summary.',
                      segments: [{ index: 1, startTime: 0, endTime: 20, description: 'Intro segment' }],
                    },
                    sonicElements: {
                      kick: 'Kick.',
                      bass: 'Bass.',
                      melodicArp: 'Arp.',
                      grooveAndTiming: 'Groove.',
                      effectsAndTexture: 'FX.',
                    },
                    mixAndMasterChain: [
                      { order: 1, device: 'Drum Buss', parameter: 'Drive', value: '5 dB', reason: 'Punch.' },
                      { order: 2, device: 'EQ Eight', parameter: 'Low Cut', value: '30 Hz', reason: 'Cleanup.' },
                      { order: 3, device: 'Operator', parameter: 'Detune', value: '0.08', reason: 'Melodic body.' },
                      { order: 4, device: 'Saturator', parameter: 'Drive', value: '2.5 dB', reason: 'Mid body.' },
                      { order: 5, device: 'Utility', parameter: 'Width', value: '125%', reason: 'Stereo control.' },
                      { order: 6, device: 'Auto Filter', parameter: 'High Shelf', value: '+2 dB', reason: 'Air.' },
                      { order: 7, device: 'Glue Compressor', parameter: 'Threshold', value: '-4 dB', reason: 'Glue.' },
                      { order: 8, device: 'Limiter', parameter: 'Ceiling', value: '-0.3 dB', reason: 'Mastering.' },
                    ],
                    secretSauce: {
                      title: 'Smoke Sauce',
                      explanation: 'Smoke explanation.',
                      implementationSteps: ['Step 1'],
                    },
                    confidenceNotes: [{ field: 'Key Signature', value: 'HIGH', reason: 'Stable.' }],
                    abletonRecommendations: [
                      {
                        device: 'Operator',
                        category: 'SYNTHESIS',
                        parameter: 'Coarse',
                        value: '1.00',
                        reason: 'Matches tonal center.',
                      },
                    ],
                  }),
                },
              ],
            },
          },
        ],
      }),
    });
  });
}

test('phase1 dual-source session musician panel toggles between polyphonic and monophonic views', async ({ page }) => {
  await stubGeminiPhase2(page);
  await page.route('**/api/analyze/estimate', async (route) => {
    const body = route.request().postData() ?? '';
    const transcribeEnabled = hasMultipartBoolean(body, 'transcribe', true);
    const stemSeparationEnabled = hasMultipartBoolean(body, 'separate', true);

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_estimate_smoke_midi_001',
        estimate: {
          durationSeconds: 214.6,
          totalLowMs: transcribeEnabled && stemSeparationEnabled ? 107000 : 22000,
          totalHighMs: transcribeEnabled && stemSeparationEnabled ? 203000 : 38000,
          stages: transcribeEnabled && stemSeparationEnabled
            ? [
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
              ]
            : [
                {
                  key: 'local_dsp',
                  label: 'Local DSP analysis',
                  lowMs: 22000,
                  highMs: 38000,
                },
              ],
        },
      }),
    });
  });

  await page.route('**/api/analyze', async (route) => {
    const body = route.request().postData() ?? '';
    expect(hasMultipartBoolean(body, 'transcribe', true)).toBe(true);
    expect(hasMultipartBoolean(body, 'separate', true)).toBe(true);

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
          transcriptionDetail: {
            transcriptionMethod: 'basic-pitch',
            noteCount: 2,
            averageConfidence: 0.83,
            stemSeparationUsed: true,
            stemsTranscribed: ['bass', 'other'],
            dominantPitches: [
              { pitchMidi: 48, pitchName: 'C3', count: 4 },
              { pitchMidi: 55, pitchName: 'G3', count: 3 },
            ],
            pitchRange: {
              minMidi: 48,
              maxMidi: 67,
              minName: 'C3',
              maxName: 'G4',
            },
            notes: [
              {
                pitchMidi: 48,
                pitchName: 'C3',
                onsetSeconds: 0.1,
                durationSeconds: 0.4,
                confidence: 0.92,
                stemSource: 'bass',
              },
              {
                pitchMidi: 67,
                pitchName: 'G4',
                onsetSeconds: 0.5,
                durationSeconds: 0.2,
                confidence: 0.74,
                stemSource: 'other',
              },
            ],
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
  await page.getByLabel('MIDI TRANSCRIPTION').check();
  await page.getByLabel('STEM SEPARATION').check();
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  const panel = page.locator('section').filter({ hasText: /SESSION MUSICIAN/i }).first();

  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(panel.getByRole('heading', { name: /SESSION MUSICIAN/i }).first()).toBeVisible();
  await expect(panel.getByText('Audio to MIDI transcription')).toBeVisible();
  await expect(panel.getByRole('button', { name: 'POLYPHONIC' })).toBeVisible();
  await expect(panel.getByRole('button', { name: 'MONOPHONIC' })).toBeVisible();
  await expect(panel.getByText('SOURCES: BASIC PITCH').first()).toBeVisible();
  await expect(panel.getByText('STEM-AWARE')).toBeVisible();
  await expect(panel.getByText('STEMS: bass, other')).toBeVisible();
  await expect(panel.getByText('Polyphonic transcription via Basic Pitch')).toBeVisible();
  await expect(panel.getByRole('button', { name: /Download \.mid/i })).toBeVisible();
  const sliders = panel.locator('input[type="range"]');
  const confidenceSlider = sliders.nth(0);
  const swingSlider = sliders.nth(1);
  await expect(confidenceSlider).toBeEnabled();
  await expect(swingSlider).toBeDisabled();

  await panel.getByRole('button', { name: '1/16 note' }).click();
  await expect(swingSlider).toBeEnabled();

  await panel.getByRole('button', { name: 'MONOPHONIC' }).click();
  await expect(panel.getByText('SOURCES: ESSENTIA').first()).toBeVisible();
  await expect(panel.getByText('Monophonic pitch detection via Essentia')).toBeVisible();
  await expect(confidenceSlider).toBeDisabled();

  await panel.getByRole('button', { name: 'POLYPHONIC' }).click();
  await expect(panel.getByText('SOURCES: BASIC PITCH').first()).toBeVisible();
  await expect(panel.getByText('Polyphonic transcription via Basic Pitch')).toBeVisible();
  await expect(confidenceSlider).toBeEnabled();

  await panel.getByRole('button', { name: /Collapse session musician panel/i }).click();
  await expect(panel.getByRole('button', { name: '1/16 note' })).toHaveCount(0);

  await panel.getByRole('button', { name: /Expand session musician panel/i }).click();
  await expect(panel.getByRole('button', { name: '1/16 note' })).toBeVisible();
});

test('missing melodyDetail shows MIDI unavailable state', async ({ page }) => {
  await stubGeminiPhase2(page);
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
  await expect(panel.locator('p').filter({ hasText: 'MIDI TRANSCRIPTION UNAVAILABLE' })).toBeVisible();
  await expect(
    panel.getByText('Run with --transcribe flag for Basic Pitch polyphonic transcription, or ensure melodyDetail is present in DSP JSON'),
  ).toBeVisible();
  await expect(panel.getByRole('button', { name: /Preview/i })).toBeDisabled();
  await expect(panel.getByRole('button', { name: /Download \.mid/i })).toBeDisabled();
});

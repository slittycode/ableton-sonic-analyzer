import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const testDir = path.dirname(fileURLToPath(import.meta.url));

function hasMultipartBoolean(body: string, fieldName: string, expected: boolean): boolean {
  const normalizedBody = body.replace(/\r?\n/g, '\n');
  const pattern = new RegExp(`name="${fieldName}"\\n\\n${expected ? 'true' : 'false'}\\n`);
  return pattern.test(normalizedBody);
}

function hasMultipartTextField(body: string, fieldName: string, expected: string): boolean {
  const normalizedBody = body.replace(/\r?\n/g, '\n');
  const pattern = new RegExp(`name="${fieldName}"\\n\\n${expected}\\n`);
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

async function pressSliderKey(locator: import('@playwright/test').Locator, key: string, times: number) {
  await locator.focus();
  for (let index = 0; index < times; index += 1) {
    await locator.press(key);
  }
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
                  label: 'Torchcrepe on bass + other stems',
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

  await page.route('**/api/analysis-runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    const body = route.request().postData() ?? '';
    expect(hasMultipartTextField(body, 'symbolic_mode', 'stem_notes')).toBe(true);
    expect(hasMultipartTextField(body, 'symbolic_backend', 'auto')).toBe(true);

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: 'run_smoke_midi_001',
        requestedStages: {
          symbolicMode: 'stem_notes',
          symbolicBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_smoke_midi_001',
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
  });

  await page.route('**/api/analysis-runs/run_smoke_midi_001', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: 'run_smoke_midi_001',
        requestedStages: {
          symbolicMode: 'stem_notes',
          symbolicBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_smoke_midi_001',
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
                lowMids: 0.0,
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
            provenance: null,
            diagnostics: { timings: { totalMs: 980, analysisMs: 900, serverOverheadMs: 80, flagsUsed: ['--transcribe', '--separate'], fileSizeBytes: 2048, fileDurationSeconds: 10, msPerSecondOfAudio: 98 } },
            error: null,
          },
          symbolicExtraction: {
            status: 'completed',
            authoritative: false,
            preferredAttemptId: 'sym_smoke_midi_001',
            attemptsSummary: [
              { attemptId: 'sym_smoke_midi_001', backendId: 'auto', mode: 'stem_notes', status: 'completed' },
            ],
            result: {
              transcriptionMethod: 'torchcrepe-viterbi',
              noteCount: 2,
              averageConfidence: 0.83,
              stemSeparationUsed: true,
              fullMixFallback: false,
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
            provenance: null,
            diagnostics: null,
            error: null,
          },
          interpretation: {
            status: 'completed',
            authoritative: false,
            preferredAttemptId: 'int_smoke_midi_001',
            attemptsSummary: [
              { attemptId: 'int_smoke_midi_001', profileId: 'producer_summary', modelName: 'gemini-3.1-pro-preview', status: 'completed' },
            ],
            result: {
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
                implementationSteps: ['Step 1'],
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
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  const fixturePath = path.resolve(testDir, './fixtures/silence.wav');
  await page.setInputFiles('#audio-upload', fixturePath);
  await expect(page.getByLabel('SYMBOLIC EXTRACTION')).toBeChecked();
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  const panel = page.locator('section').filter({ hasText: /SESSION MUSICIAN/i }).first();

  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(panel.getByRole('heading', { name: /SESSION MUSICIAN/i }).first()).toBeVisible();
  await expect(panel.getByText('Symbolic notes and melody guide')).toBeVisible();
  await expect(panel.getByRole('button', { name: 'SYMBOLIC' })).toBeVisible();
  await expect(panel.getByRole('button', { name: 'MELODY' })).toBeVisible();
  await expect(panel.getByText('SOURCE: BASIC PITCH LEGACY').first()).toBeVisible();
  await expect(panel.getByText('Range: C3 - G4')).toHaveCount(1);
  await expect(panel.getByText('Confidence: 83%')).toHaveCount(1);
  await expect(panel.getByText('2 / 2 NOTES')).toBeVisible();
  await expect(panel.getByText('STEM-AWARE')).toBeVisible();
  await expect(panel.getByText('STEMS: bass, other')).toBeVisible();
  await expect(panel.getByText('BASIC PITCH LEGACY symbolic notes')).toBeVisible();
  const previewButton = panel.getByRole('button', { name: /Preview/i });
  const downloadButton = panel.getByRole('button', { name: /Download \.mid/i });
  await expect(previewButton).toBeVisible();
  await expect(previewButton).toBeEnabled();
  await expect(downloadButton).toBeVisible();
  await expect(downloadButton).toBeEnabled();
  const sliders = panel.locator('input[type="range"]');
  const confidenceSlider = sliders.nth(0);
  const swingSlider = sliders.nth(1);
  await expect(confidenceSlider).toBeEnabled();
  await expect(swingSlider).toBeDisabled();

  await pressSliderKey(confidenceSlider, 'End', 1);
  await pressSliderKey(confidenceSlider, 'ArrowLeft', 4);
  await expect(confidenceSlider).toHaveValue('0.8');
  await expect(panel.getByText('80%')).toBeVisible();
  await expect(panel.getByText('1 / 2 NOTES')).toBeVisible();

  await panel.getByRole('button', { name: '1/16 note' }).click();
  await expect(swingSlider).toBeEnabled();
  await pressSliderKey(swingSlider, 'ArrowRight', 30);
  await expect(swingSlider).toHaveValue('30');

  const downloadPromise = page.waitForEvent('download');
  await downloadButton.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('track-analysis.mid');

  await panel.getByRole('button', { name: 'MELODY' }).click();
  await expect(panel.getByText('SOURCE: ESSENTIA MELODY').first()).toBeVisible();
  await expect(panel.getByText('Monophonic melody guide via Essentia')).toBeVisible();
  await expect(panel.getByText('STEM-AWARE')).toHaveCount(0);
  await expect(panel.getByText('STEMS: bass, other')).toHaveCount(0);
  await expect(panel.getByText('3 NOTES')).toBeVisible();
  await expect(panel.getByText('3 / 3 NOTES')).toHaveCount(0);
  await expect(panel.getByText('Per-note confidence not available in melody-guide mode')).toBeVisible();
  await expect(panel.getByText('Adjust confidence threshold to filter noise before export.')).toHaveCount(0);
  await expect(confidenceSlider).toBeDisabled();
  await expect(confidenceSlider).toHaveValue('0.8');

  await panel.getByRole('button', { name: 'SYMBOLIC' }).click();
  await expect(panel.getByText('SOURCE: BASIC PITCH LEGACY').first()).toBeVisible();
  await expect(panel.getByText('BASIC PITCH LEGACY symbolic notes')).toBeVisible();
  await expect(panel.getByText('STEM-AWARE')).toBeVisible();
  await expect(panel.getByText('STEMS: bass, other')).toBeVisible();
  await expect(panel.getByText('1 / 2 NOTES')).toBeVisible();
  await expect(confidenceSlider).toBeEnabled();
  await expect(confidenceSlider).toHaveValue('0.8');

  await panel.getByRole('button', { name: /Collapse session musician panel/i }).click();
  await expect(panel.getByRole('button', { name: '1/16 note' })).toHaveCount(0);

  await panel.getByRole('button', { name: /Expand session musician panel/i }).click();
  await expect(panel.getByRole('button', { name: '1/16 note' })).toBeVisible();
});

test('missing melodyDetail shows MIDI unavailable state', async ({ page }) => {
  await stubGeminiPhase2(page);
  await page.route('**/api/analyze/estimate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_estimate_smoke_midi_awaiting_001',
        estimate: {
          durationSeconds: 210.6,
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
        runId: 'run_smoke_midi_awaiting_001',
        requestedStages: {
          symbolicMode: 'off',
          symbolicBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_smoke_midi_awaiting_001',
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

  await page.route('**/api/analysis-runs/run_smoke_midi_awaiting_001', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: 'run_smoke_midi_awaiting_001',
        requestedStages: {
          symbolicMode: 'off',
          symbolicBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_smoke_midi_awaiting_001',
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
                lowMids: 0.0,
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
            preferredAttemptId: 'int_smoke_midi_awaiting_001',
            attemptsSummary: [
              { attemptId: 'int_smoke_midi_awaiting_001', profileId: 'producer_summary', modelName: 'gemini-3.1-pro-preview', status: 'completed' },
            ],
            result: {
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
                implementationSteps: ['Step 1'],
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
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  const fixturePath = path.resolve(testDir, './fixtures/silence.wav');
  await page.setInputFiles('#audio-upload', fixturePath);
  await page.getByRole('button', { name: /Initiate Analysis/i }).click();

  const panel = page.locator('section').filter({ hasText: /SESSION MUSICIAN/i }).first();
  await expect(panel.locator('p').filter({ hasText: 'SYMBOLIC NOTES UNAVAILABLE' })).toBeVisible();
  await expect(
    panel.getByText('Run with symbolic extraction enabled, or ensure melodyDetail is present in the DSP payload for a melody guide'),
  ).toBeVisible();
  await expect(panel.getByRole('button', { name: /Preview/i })).toBeDisabled();
  await expect(panel.getByRole('button', { name: /Download \.mid/i })).toBeDisabled();
});

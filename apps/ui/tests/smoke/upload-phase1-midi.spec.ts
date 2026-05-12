import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const testDir = path.dirname(fileURLToPath(import.meta.url));

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

test('phase1 dual-source session musician panel renders both blocks simultaneously', async ({ page }) => {
  await stubGeminiPhase2(page);
  await page.route('**/api/analysis-runs/estimate', async (route) => {
    const body = route.request().postData() ?? '';
    const pitchNoteTranslationEnabled = hasMultipartTextField(body, 'pitch_note_mode', 'stem_notes');

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_estimate_smoke_midi_001',
        estimate: {
          durationSeconds: 214.6,
          totalLowMs: pitchNoteTranslationEnabled ? 107000 : 22000,
          totalHighMs: pitchNoteTranslationEnabled ? 203000 : 38000,
          stages: pitchNoteTranslationEnabled
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
    expect(hasMultipartTextField(body, 'pitch_note_mode', 'stem_notes')).toBe(true);
    expect(hasMultipartTextField(body, 'pitch_note_backend', 'auto')).toBe(true);

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: 'run_smoke_midi_001',
        requestedStages: {
          pitchNoteMode: 'stem_notes',
          pitchNoteBackend: 'auto',
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
          pitchNoteMode: 'stem_notes',
          pitchNoteBackend: 'auto',
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
            path: 'uploads/test.wav',
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
          pitchNoteTranslation: {
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
  await expect(page.getByLabel('PITCH/NOTE TRANSLATION')).toBeChecked();
  await page.getByRole('button', { name: /Run Analysis/i }).click();

  const panel = page.locator('section').filter({ hasText: /SESSION MUSICIAN/i }).first();

  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(panel.getByRole('heading', { name: /SESSION MUSICIAN/i }).first()).toBeVisible();

  // Both blocks render at once — no toggle.
  const noteDraft = panel.getByTestId('note-draft-block');
  const melodyContour = panel.getByTestId('melody-contour-block');
  await expect(noteDraft).toBeVisible();
  await expect(melodyContour).toBeVisible();
  await expect(panel.getByRole('button', { name: /^PITCH\/NOTE$/ })).toHaveCount(0);
  await expect(panel.getByRole('button', { name: /^MELODY$/ })).toHaveCount(0);

  // Confidence band pills show "label · NN%" with the matching tier copy.
  await expect(noteDraft.getByText('Solid scaffold · 83%')).toBeVisible();
  await expect(melodyContour.getByText('Workable draft · 72%')).toBeVisible();

  // Stem note draft has stem filter + per-note confidence slider; melody does not.
  await expect(noteDraft.getByRole('button', { name: 'bass' })).toBeVisible();
  await expect(noteDraft.getByRole('button', { name: 'other' })).toBeVisible();
  await expect(noteDraft.locator('input[type="range"]')).toHaveCount(2); // confidence + swing
  await expect(melodyContour.locator('input[type="range"]')).toHaveCount(1); // swing only

  // Both blocks expose their own MIDI controls with distinct test IDs.
  const stemsPreview = noteDraft.getByTestId('midi-preview-stems');
  const stemsDownload = noteDraft.getByTestId('midi-download-stems');
  const melodyPreview = melodyContour.getByTestId('midi-preview-melody');
  const melodyDownload = melodyContour.getByTestId('midi-download-melody');
  await expect(stemsPreview).toBeEnabled();
  await expect(stemsDownload).toBeEnabled();
  await expect(melodyPreview).toBeEnabled();
  await expect(melodyDownload).toBeEnabled();

  // Quantize controls still work inside Block A.
  await noteDraft.getByRole('button', { name: '1/16 note' }).click();
  const stemsSwing = noteDraft.locator('input[type="range"]').nth(1);
  await expect(stemsSwing).toBeEnabled();
  await pressSliderKey(stemsSwing, 'ArrowRight', 30);
  await expect(stemsSwing).toHaveValue('30');

  // Stem-note Download produces the per-block filename.
  const stemsDownloadPromise = page.waitForEvent('download');
  await stemsDownload.click();
  const stemsFile = await stemsDownloadPromise;
  expect(stemsFile.suggestedFilename()).toBe('track-analysis-stems.mid');

  // Melody Download produces its own filename.
  const melodyDownloadPromise = page.waitForEvent('download');
  await melodyDownload.click();
  const melodyFile = await melodyDownloadPromise;
  expect(melodyFile.suggestedFilename()).toBe('track-analysis-melody.mid');

  // Shared preview controller: only one preview is active at a time. Starting
  // melody preview while stems is playing flips the stems button back to
  // "Preview" and the melody button shows "Stop".
  await stemsPreview.click();
  await expect(stemsPreview).toContainText(/Stop/);
  await melodyPreview.click();
  await expect(melodyPreview).toContainText(/Stop/);
  await expect(stemsPreview).not.toContainText(/Stop/);
  await melodyPreview.click(); // stop melody so the test ends cleanly
  await expect(melodyPreview).not.toContainText(/Stop/);

  // Slider-filtered-to-zero: drag the confidence slider above the highest
  // per-note confidence (0.92) so every note is filtered. Download hides;
  // the explanatory note appears; the piano roll remains.
  const stemsConfidenceSlider = noteDraft.locator('input[type="range"]').nth(0);
  await stemsConfidenceSlider.focus();
  await pressSliderKey(stemsConfidenceSlider, 'End', 1);
  await expect(stemsConfidenceSlider).toHaveValue('1');
  await expect(noteDraft.getByText(/Confidence slider filtered every note/i)).toBeVisible();
  await expect(noteDraft.getByTestId('midi-download-stems')).toHaveCount(0);
  await expect(noteDraft.getByTestId('note-draft-piano-roll')).toBeVisible();

  // Collapse hides the blocks; expand restores them.
  await panel.getByRole('button', { name: /Collapse session musician panel/i }).click();
  await expect(noteDraft.getByRole('button', { name: '1/16 note' })).toHaveCount(0);
  await panel.getByRole('button', { name: /Expand session musician panel/i }).click();
  await expect(noteDraft.getByRole('button', { name: '1/16 note' })).toBeVisible();
});

test('missing melodyDetail shows MIDI unavailable state', async ({ page }) => {
  await stubGeminiPhase2(page);
  await page.route('**/api/analysis-runs/estimate', async (route) => {
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
          pitchNoteMode: 'off',
          pitchNoteBackend: 'auto',
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

  await page.route('**/api/analysis-runs/run_smoke_midi_awaiting_001', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: 'run_smoke_midi_awaiting_001',
        requestedStages: {
          pitchNoteMode: 'off',
          pitchNoteBackend: 'auto',
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
            path: 'uploads/test.wav',
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
  await page.getByRole('button', { name: /Run Analysis/i }).click();

  const panel = page.locator('section').filter({ hasText: /SESSION MUSICIAN/i }).first();
  // pitchNoteMode='off' + no melodyDetail: the off-state banner is the only thing rendered.
  // Neither block renders, so the Preview / Download buttons are not in the DOM at all.
  await expect(panel.getByTestId('session-musician-off-banner')).toBeVisible();
  await expect(panel.getByTestId('note-draft-block')).toHaveCount(0);
  await expect(panel.getByTestId('melody-contour-block')).toHaveCount(0);
  await expect(panel.getByTestId('midi-preview-stems')).toHaveCount(0);
  await expect(panel.getByTestId('midi-download-stems')).toHaveCount(0);
  await expect(panel.getByTestId('midi-preview-melody')).toHaveCount(0);
  await expect(panel.getByTestId('midi-download-melody')).toHaveCount(0);
});

test('pitch/note off with melody present shows opted-out state', async ({ page }) => {
  await stubGeminiPhase2(page);
  await page.route('**/api/analysis-runs/estimate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_estimate_smoke_midi_optedout_001',
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
        runId: 'run_smoke_midi_optedout_001',
        requestedStages: {
          pitchNoteMode: 'off',
          pitchNoteBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_smoke_midi_optedout_001',
            filename: 'silence.wav',
            mimeType: 'audio/wav',
            sizeBytes: 2048,
            contentSha256: 'abc123',
            path: '/tmp/silence.wav',
          },
        },
        stages: {
          measurement: { status: 'queued', authoritative: true, result: null, provenance: null, diagnostics: null, error: null },
          pitchNoteTranslation: { status: 'not_requested', authoritative: false, preferredAttemptId: null, attemptsSummary: [], result: null, provenance: null, diagnostics: null, error: null },
          interpretation: { status: 'blocked', authoritative: false, preferredAttemptId: null, attemptsSummary: [], result: null, provenance: null, diagnostics: null, error: null },
        },
      }),
    });
  });

  await page.route('**/api/analysis-runs/run_smoke_midi_optedout_001', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: 'run_smoke_midi_optedout_001',
        requestedStages: {
          pitchNoteMode: 'off',
          pitchNoteBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_smoke_midi_optedout_001',
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
                sourceSeparated: false,
                vibratoPresent: false,
                vibratoExtent: 0,
                vibratoRate: 0,
                vibratoConfidence: 0.1,
              },
            },
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
            preferredAttemptId: 'int_smoke_midi_optedout_001',
            attemptsSummary: [
              { attemptId: 'int_smoke_midi_optedout_001', profileId: 'producer_summary', modelName: 'gemini-3.1-pro-preview', status: 'completed' },
            ],
            result: {
              trackCharacter: 'Deterministic smoke response.',
              detectedCharacteristics: [],
              arrangementOverview: { summary: 'Smoke summary.', segments: [] },
              sonicElements: { kick: 'Kick.', bass: 'Bass.', melodicArp: 'Arp.', grooveAndTiming: 'Groove.', effectsAndTexture: 'FX.' },
              mixAndMasterChain: [],
              secretSauce: { title: 'Smoke Sauce', explanation: 'Smoke explanation.', implementationSteps: ['Step 1'] },
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
  await page.getByRole('button', { name: /Run Analysis/i }).click();

  const panel = page.locator('section').filter({ hasText: /SESSION MUSICIAN/i }).first();
  // Opted-out banner is the primary disclosure
  await expect(panel.getByTestId('session-musician-off-banner')).toBeVisible();
  await expect(
    panel.locator('p').filter({ hasText: /Re-enable the Stem Pitch\/Note Translation toggle/i }).first(),
  ).toBeVisible();

  // Block A (stem note draft) is absent because pitchNoteMode='off'.
  await expect(panel.getByTestId('note-draft-block')).toHaveCount(0);
  await expect(panel.getByTestId('midi-preview-stems')).toHaveCount(0);
  await expect(panel.getByTestId('midi-download-stems')).toHaveCount(0);

  // Block B (melody contour) still renders normally, with its own controls.
  const melodyContour = panel.getByTestId('melody-contour-block');
  await expect(melodyContour).toBeVisible();
  await expect(melodyContour.getByTestId('midi-preview-melody')).toBeEnabled();
  await expect(melodyContour.getByTestId('midi-download-melody')).toBeEnabled();
  // Block B owns its own quantize controls.
  await expect(melodyContour.getByRole('button', { name: '1/16 note' })).toBeVisible();
});

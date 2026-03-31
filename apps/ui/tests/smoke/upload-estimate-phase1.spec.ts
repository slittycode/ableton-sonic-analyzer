import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const testDir = path.dirname(fileURLToPath(import.meta.url));

function hasMultipartTextField(body: string, fieldName: string, expected: string): boolean {
  const normalizedBody = body.replace(/\r?\n/g, '\n');
  const pattern = new RegExp(`name="${fieldName}"\\n\\n${expected}\\n`);
  return pattern.test(normalizedBody);
}

test('upload shows estimate and local DSP processing copy before phase1 completes', async ({ page }) => {
  await page.route('**/api/analysis-runs/estimate', async (route) => {
    const body = route.request().postData() ?? '';
    const pitchNoteMode = hasMultipartTextField(body, 'pitch_note_mode', 'stem_notes') ? 'stem_notes' : 'off';
    const estimate =
      pitchNoteMode === 'stem_notes'
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
                label: 'Pitch/Note Translation on stems',
                lowMs: 40000,
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

  let runPollCount = 0;
  await page.route('**/api/analysis-runs', async (route) => {
    const request = route.request();
    if (request.method() !== 'POST') {
      await route.fallback();
      return;
    }

    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: 'run_smoke_002',
        requestedStages: {
          pitchNoteMode: 'off',
          pitchNoteBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_smoke_002',
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

  await page.route('**/api/analysis-runs/run_smoke_002', async (route) => {
    runPollCount += 1;
    const completed = runPollCount > 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: 'run_smoke_002',
        requestedStages: {
          pitchNoteMode: 'off',
          pitchNoteBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_smoke_002',
            filename: 'silence.wav',
            mimeType: 'audio/wav',
            sizeBytes: 2048,
            contentSha256: 'abc123',
          },
        },
        stages: {
          measurement: {
            status: completed ? 'completed' : 'running',
            authoritative: true,
            result: completed
              ? {
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
                }
              : null,
            provenance: null,
            diagnostics: completed ? { timings: { totalMs: 980, analysisMs: 900, serverOverheadMs: 80, flagsUsed: [], fileSizeBytes: 2048, fileDurationSeconds: 10, msPerSecondOfAudio: 98 } } : null,
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
            status: completed ? 'completed' : 'running',
            authoritative: false,
            preferredAttemptId: completed ? 'int_smoke_002' : null,
            attemptsSummary: completed
              ? [{ attemptId: 'int_smoke_002', profileId: 'producer_summary', modelName: 'gemini-3.1-pro-preview', status: 'completed' }]
              : [],
            result: completed
              ? {
                  trackCharacter: 'Tight modern electronic mix.',
                  detectedCharacteristics: [],
                  arrangementOverview: { summary: 'Four sections.', segments: [] },
                  sonicElements: {
                    kick: 'Punchy kick body.',
                    bass: 'Focused bass lane.',
                    melodicArp: 'Simple melodic motif.',
                    grooveAndTiming: 'Quantized groove.',
                    effectsAndTexture: 'Light atmospherics.',
                  },
                  mixAndMasterChain: [],
                  secretSauce: { title: 'Punch Layering', explanation: 'Layered transient enhancement.', implementationSteps: [] },
                  confidenceNotes: [],
                  abletonRecommendations: [],
                }
              : null,
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

  await expect(page.getByTestId('phase2-model-desktop')).toBeVisible();
  await expect(page.getByText(/Estimated local analysis/i)).toBeVisible();

  const pitchNoteToggle = page.getByLabel("PITCH/NOTE TRANSLATION");
  await expect(pitchNoteToggle).toBeChecked();
  await expect(page.getByText('107s-203s')).toBeVisible();

  await pitchNoteToggle.uncheck();
  await expect(page.getByText('22s-38s')).toBeVisible();

  await page.getByRole('button', { name: /Run Analysis/i }).click();

  await expect(page.getByRole('heading', { name: 'Analysis Results' })).toBeVisible();
  await expect(page.getByText('Analysis Results')).toBeVisible();
});

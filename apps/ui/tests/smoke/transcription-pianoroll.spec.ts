import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Smoke coverage for the transcription pianoroll surface (PR-B).
 *
 * The block (`TranscriptionPianorollBlock`) mounts in the Session Musician
 * suite once the run snapshot's `pitchNoteTranslation` stage carries a
 * transcriptionDetail with `noteCount > 0` (projected into
 * `phase1.transcriptionDetail` by `projectPhase1FromRun`). It then fetches the
 * derived matrix from the canonical run sub-resource
 * `GET /api/analysis-runs/{run_id}/transcription/pianoroll` and paints a canvas
 * heatmap. These tests drive the real upload→run→results flow with a mocked
 * backend and assert both the success render and the structured-error render.
 */

const testDir = path.dirname(fileURLToPath(import.meta.url));
const RUN_ID = 'run_smoke_pianoroll_001';

const PHASE2_STUB = {
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
  secretSauce: { title: 'Smoke Sauce', explanation: 'Smoke explanation.', implementationSteps: [] },
  confidenceNotes: [],
  abletonRecommendations: [],
};

// Unwrapped transcriptionDetail — mirrors what the pitch-note worker stores
// directly as the stage result (see server.py _execute_pitch_note_attempt).
const TRANSCRIPTION_RESULT = {
  transcriptionMethod: 'torchcrepe-viterbi',
  noteCount: 2,
  averageConfidence: 0.83,
  stemSeparationUsed: true,
  fullMixFallback: false,
  stemsTranscribed: ['bass', 'other'],
  perStemAverageConfidence: { bass: 0.92, other: 0.74 },
  dominantPitches: [{ pitchMidi: 60, pitchName: 'C4', count: 2 }],
  pitchRange: { minMidi: 60, maxMidi: 67, minName: 'C4', maxName: 'G4' },
  notes: [
    { pitchMidi: 60, pitchName: 'C4', onsetSeconds: 0.1, durationSeconds: 0.4, confidence: 0.92, stemSource: 'bass' },
    { pitchMidi: 67, pitchName: 'G4', onsetSeconds: 0.5, durationSeconds: 0.2, confidence: 0.74, stemSource: 'other' },
  ],
};

// 88 pitch rows (21..109 exclusive); only MIDI 60 (row 39) carries velocity.
const PIANOROLL_PAYLOAD = {
  mode: 'frame' as const,
  pitchLow: 21,
  pitchHigh: 109,
  ticksPerQuarter: 4,
  quartersPerMinute: 126.0,
  timeSignature: '4/4',
  noteCount: 2,
  frames: Array.from({ length: 88 }, (_, row) =>
    row === 60 - 21 ? [100, 110, 120, 127] : [0, 0, 0, 0],
  ),
};

async function stubEstimate(page: import('@playwright/test').Page) {
  let hits = 0;
  await page.route('**/api/analysis-runs/estimate', async (route) => {
    hits += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_estimate_pianoroll_001',
        estimate: {
          durationSeconds: 210.6,
          totalLowMs: 107000,
          totalHighMs: 203000,
          stages: [
            { key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 },
            { key: 'transcription_stems', label: 'Torchcrepe on bass + other stems', lowMs: 40000, highMs: 75000 },
          ],
        },
      }),
    });
  });
  return () => hits;
}

/** Mocks create-run (POST) + completed snapshot (GET) carrying a transcription. */
async function mockRunLifecycle(page: import('@playwright/test').Page) {
  await page.route('**/api/analysis-runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runId: RUN_ID,
        requestedStages: {
          pitchNoteMode: 'stem_notes',
          pitchNoteBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_pianoroll_001',
            filename: 'silence.wav',
            mimeType: 'audio/wav',
            sizeBytes: 2048,
            contentSha256: 'abc123',
            path: 'uploads/test.wav',
          },
        },
        stages: {
          measurement: { status: 'queued', authoritative: true, result: null, provenance: null, diagnostics: null, error: null },
          pitchNoteTranslation: { status: 'blocked', authoritative: false, preferredAttemptId: null, attemptsSummary: [], result: null, provenance: null, diagnostics: null, error: null },
          interpretation: { status: 'blocked', authoritative: false, preferredAttemptId: null, attemptsSummary: [], result: null, provenance: null, diagnostics: null, error: null },
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
        requestedStages: {
          pitchNoteMode: 'stem_notes',
          pitchNoteBackend: 'auto',
          interpretationMode: 'async',
          interpretationProfile: 'producer_summary',
          interpretationModel: 'gemini-3.1-pro-preview',
        },
        artifacts: {
          sourceAudio: {
            artifactId: 'artifact_pianoroll_001',
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
              spectralBalance: { subBass: -0.7, lowBass: 1.2, lowMids: 0.0, mids: -0.3, upperMids: 0.4, highs: 1.0, brilliance: 0.8 },
            },
            provenance: null,
            diagnostics: { timings: { totalMs: 980, analysisMs: 900, serverOverheadMs: 80, flagsUsed: ['--transcribe', '--separate'], fileSizeBytes: 2048, fileDurationSeconds: 10, msPerSecondOfAudio: 98 } },
            error: null,
          },
          pitchNoteTranslation: {
            status: 'completed',
            authoritative: false,
            preferredAttemptId: 'sym_pianoroll_001',
            attemptsSummary: [{ attemptId: 'sym_pianoroll_001', backendId: 'auto', mode: 'stem_notes', status: 'completed' }],
            result: TRANSCRIPTION_RESULT,
            provenance: null,
            diagnostics: null,
            error: null,
          },
          interpretation: {
            status: 'completed',
            authoritative: false,
            preferredAttemptId: 'int_pianoroll_001',
            attemptsSummary: [{ attemptId: 'int_pianoroll_001', profileId: 'producer_summary', modelName: 'gemini-3.1-pro-preview', status: 'completed' }],
            result: PHASE2_STUB,
            provenance: null,
            diagnostics: null,
            error: null,
          },
        },
      }),
    });
  });
}

async function uploadAndRun(page: import('@playwright/test').Page, getEstimateHits: () => number) {
  await page.goto('/', { waitUntil: 'networkidle' });
  const fixturePath = path.resolve(testDir, './fixtures/silence.wav');
  await page.setInputFiles('#audio-upload', fixturePath);
  await expect.poll(() => getEstimateHits()).toBeGreaterThanOrEqual(1);
  await page.getByRole('button', { name: /Run Analysis/i }).click();
  await expect(page.getByText('Analysis Results')).toBeVisible();
}

test('transcription pianoroll heatmap renders from the run sub-resource', async ({ page }) => {
  const getEstimateHits = await stubEstimate(page);
  await mockRunLifecycle(page);

  let requestedUrl = '';
  await page.route(`**/api/analysis-runs/${RUN_ID}/transcription/pianoroll`, async (route) => {
    requestedUrl = route.request().url();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(PIANOROLL_PAYLOAD),
    });
  });

  await uploadAndRun(page, getEstimateHits);

  const block = page.getByTestId('transcription-pianoroll');
  await expect(block).toBeVisible();
  // Citation cites Phase 1's BPM + time signature — chain of custody on the surface.
  await expect(block).toContainText('frame mode · 2 notes · 126 BPM · 4/4');
  const canvas = block.locator('canvas');
  await expect(canvas).toBeVisible();
  await expect(canvas).toHaveAttribute('aria-label', /Transcription pianoroll/);

  // The block must hit the canonical run sub-resource, not a query-style route.
  expect(requestedUrl).toContain(`/api/analysis-runs/${RUN_ID}/transcription/pianoroll`);
});

test('transcription pianoroll surfaces the backend error code', async ({ page }) => {
  const getEstimateHits = await stubEstimate(page);
  await mockRunLifecycle(page);

  await page.route(`**/api/analysis-runs/${RUN_ID}/transcription/pianoroll`, async (route) => {
    await route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({
        error: {
          code: 'TRANSCRIPTION_NOT_COMPLETED',
          message: 'Pitch-note translation has not finished. Wait and retry.',
        },
      }),
    });
  });

  await uploadAndRun(page, getEstimateHits);

  const errorBlock = page.getByTestId('transcription-pianoroll-error');
  await expect(errorBlock).toBeVisible();
  await expect(errorBlock).toContainText('Pitch-note translation has not finished');
  // The structured backend code rides through to the surface for correlation.
  await expect(errorBlock).toContainText('TRANSCRIPTION_NOT_COMPLETED');
});

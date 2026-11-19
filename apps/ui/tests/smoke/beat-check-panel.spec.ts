import { expect, test, type Page } from '@playwright/test';

import { enableBeatCheckForTest } from './runtimeEnv';

/**
 * Beat Check panel inside the real results view, behind VITE_ENABLE_BEAT_CHECK
 * (default OFF). Backend calls are stubbed; the uploaded file is a generated
 * 4-second silent WAV so the browser has something real to decode and play.
 * Audio correctness (click timing, alignment, loops) is covered offline in
 * beat-check-audio.spec.ts; this spec covers wiring and transport.
 */

const RUN_ID = 'run_smoke_beat_check_001';
const TRACK_SECONDS = 4;

function silentWav(seconds: number, sampleRate = 22050): Buffer {
  const samples = Math.round(seconds * sampleRate);
  const buffer = Buffer.alloc(44 + samples * 2);
  buffer.write('RIFF', 0);
  buffer.writeUInt32LE(36 + samples * 2, 4);
  buffer.write('WAVE', 8);
  buffer.write('fmt ', 12);
  buffer.writeUInt32LE(16, 16); // PCM chunk size
  buffer.writeUInt16LE(1, 20); // PCM
  buffer.writeUInt16LE(1, 22); // mono
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write('data', 36);
  buffer.writeUInt32LE(samples * 2, 40);
  return buffer;
}

const domain = (status: string, plainEnglish: string) => ({
  status,
  plainEnglish,
  source: 'smoke',
  confidence: status === 'authoritative' ? 0.95 : 0.3,
  evidence: {},
});

const measurementResult = (seconds: number) => ({
  bpm: 120,
  bpmConfidence: 0.95,
  key: 'A minor',
  keyConfidence: 0.9,
  timeSignature: '4/4',
  timeSignatureSource: 'assumed_four_four',
  durationSeconds: seconds,
  lufsIntegrated: -8,
  truePeak: -0.5,
  stereoWidth: 0.6,
  stereoCorrelation: 0.8,
  spectralBalance: { subBass: 0, lowBass: 0, lowMids: 0, mids: 0, upperMids: 0, highs: 0, brilliance: 0 },
  rhythmDetail: {
    onsetRate: 2,
    beatGrid: [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
    downbeats: [0.5, 2.5],
    beatPositions: [1, 2, 3, 4, 1, 2, 3],
    downbeatSource: 'kick_accent',
    downbeatConfidence: 0.2,
    grooveAmount: 0.05,
    tempoStability: 0.95,
    phraseGrid: { phrases4Bar: [0.5], phrases8Bar: [0.5], phrases16Bar: [0.5], totalBars: 2, totalPhrases8Bar: 1 },
  },
  fundamentalsQuality: {
    schemaVersion: 'fundamentals-quality.v1',
    targetProfile: 'electronic_ableton_v1',
    analysisMode: 'full',
    localOnly: true,
    llmExcluded: true,
    overallStatus: 'ambiguous',
    domains: {
      tempo: domain('authoritative', 'Tempo was measured locally.'),
      beatGrid: domain('authoritative', 'Beat grid was derived locally.'),
      downbeats: domain('ambiguous', 'Bar starts are uncertain.'),
      meter: domain('ambiguous', 'Meter is a working assumption.'),
    },
  },
});

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

function runSnapshot(measurementStatus: 'queued' | 'completed', seconds: number) {
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
        artifactId: 'artifact_beat_check_001',
        filename: 'beat-check.wav',
        mimeType: 'audio/wav',
        sizeBytes: 44 + seconds * 22050 * 2,
        contentSha256: 'abc123',
        path: 'uploads/beat-check.wav',
      },
    },
    stages: {
      measurement: {
        status: measurementStatus,
        authoritative: true,
        result: measurementStatus === 'completed' ? measurementResult(seconds) : null,
        provenance: null,
        diagnostics: null,
        error: null,
      },
      pitchNoteTranslation: NOT_REQUESTED,
      interpretation: NOT_REQUESTED,
    },
  };
}

async function runStubbedAnalysis(page: Page, seconds = TRACK_SECONDS) {
  await page.route('**/api/analysis-runs/estimate', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'req_beat_check_estimate',
        estimate: {
          durationSeconds: seconds,
          totalLowMs: 2000,
          totalHighMs: 4000,
          stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 2000, highMs: 4000 }],
        },
      }),
    }),
  );
  await page.route('**/api/analysis-runs', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(runSnapshot('queued', seconds)) })
      : route.fallback(),
  );
  await page.route(`**/api/analysis-runs/${RUN_ID}`, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(runSnapshot('completed', seconds)) }),
  );

  await page.goto('/', { waitUntil: 'networkidle' });
  await page.setInputFiles('#audio-upload', {
    name: 'beat-check.wav',
    mimeType: 'audio/wav',
    buffer: silentWav(seconds),
  });
  await page.getByLabel('AI INTERPRETATION').uncheck(); // no Gemini stub needed
  await page.getByRole('button', { name: /Run Analysis/i }).click();
  await expect(page.getByTestId('analysis-results-root')).toBeVisible();
}

test('Beat Check panel shows rhythm measurements and plays, loops and stops', async ({ page }) => {
  await enableBeatCheckForTest(page);
  await runStubbedAnalysis(page);

  const panel = page.getByTestId('beat-check-panel');
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId('beat-check-bpm')).toContainText('120');
  await expect(panel).toContainText('7 beats');
  await expect(panel).toContainText('LOCAL');
  await expect(panel).toContainText('CHECK');
  await expect(panel).toContainText('ASSUMED');
  await expect(panel).not.toContainText('[object Object]');

  await panel.getByTestId('beat-check-open').click();
  await expect(panel.getByTestId('beat-check-player')).toBeVisible();
  await expect(panel.getByTestId('beat-check-track-status')).toContainText('Track ready · 0:04.0');

  const region = panel.getByTestId('beat-check-region');
  await expect(region.locator('option')).toHaveText(['Whole track', 'Phrase 1 · 0:00.5–0:04.0']);

  const transport = panel.getByTestId('beat-check-transport');
  await transport.click();
  await expect(transport).toHaveText('Stop');
  // The counter follows the measured bar positions as playback advances.
  await expect(panel.getByTestId('beat-check-counter')).toHaveText(/Bar 1 · beat [1-4]/, { timeout: 5000 });
  await expect(panel.getByTestId('beat-check-counter')).toHaveText(/Bar 2 · beat [1-3]/, { timeout: 5000 });

  // Shifting the accent is reflected on the beat LEDs.
  await panel.getByRole('button', { name: '+1 beat', exact: true }).click();
  await expect(panel.getByRole('button', { name: '+1 beat', exact: true })).toHaveAttribute('aria-pressed', 'true');

  // Looping a phrase restarts playback on that region and keeps playing past its length.
  await region.selectOption({ label: 'Phrase 1 · 0:00.5–0:04.0' });
  await panel.getByLabel('Loop').check();
  await expect(transport).toHaveText('Stop');
  await page.waitForTimeout(4200);
  await expect(transport).toHaveText('Stop');

  await transport.click();
  await expect(transport).toHaveText('Play');
  await expect(panel.getByTestId('beat-check-counter')).toHaveText('—');
});

test('A non-looped play ends by itself at the end of the track', async ({ page }) => {
  await enableBeatCheckForTest(page);
  await runStubbedAnalysis(page);
  const panel = page.getByTestId('beat-check-panel');
  await panel.getByTestId('beat-check-open').click();
  await expect(panel.getByTestId('beat-check-track-status')).toContainText('Track ready');
  const transport = panel.getByTestId('beat-check-transport');
  await transport.click();
  await expect(transport).toHaveText('Stop');
  await expect(transport).toHaveText('Play', { timeout: TRACK_SECONDS * 1000 + 3000 });
});

test('Beat Check and the waveform player never play the track at the same time', async ({ page }) => {
  // Codex review on #219: two unsynchronised copies of the track would sound
  // like the flamming Beat Check asks the producer to listen for.
  await enableBeatCheckForTest(page);
  // 20 s so neither player can simply reach the end inside an assertion's
  // timeout — the stop/pause must come from the other player starting.
  await runStubbedAnalysis(page, 20);
  const waveformToggle = page.getByTestId('waveform-play-toggle');
  const quick = { timeout: 1500 };
  const panel = page.getByTestId('beat-check-panel');
  await panel.getByTestId('beat-check-open').click();
  await expect(panel.getByTestId('beat-check-track-status')).toContainText('Track ready');
  const transport = panel.getByTestId('beat-check-transport');

  // Waveform first, then Beat Check: the waveform pauses.
  await waveformToggle.click();
  await expect.poll(() => waveformIsPlaying(page)).toBe(true);
  await transport.click();
  await expect(transport).toHaveText('Stop');
  await expect.poll(() => waveformIsPlaying(page), quick).toBe(false);

  // Beat Check first, then the waveform: Beat Check stops.
  await waveformToggle.click();
  await expect.poll(() => waveformIsPlaying(page)).toBe(true);
  await expect(transport).toHaveText('Play', quick);
});

/** True while the waveform player's media element is playing. */
async function waveformIsPlaying(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const media = [...document.querySelectorAll('audio, video')] as HTMLMediaElement[];
    const shadowMedia = [...document.querySelectorAll('[data-testid="waveform-track"] *')]
      .flatMap((el) => [...((el as HTMLElement).shadowRoot?.querySelectorAll('audio, video') ?? [])]) as HTMLMediaElement[];
    return [...media, ...shadowMedia].some((el) => !el.paused);
  });
}

test('Beat Check panel stays hidden while the flag is off', async ({ page }) => {
  await runStubbedAnalysis(page);
  await expect(page.getByText('Analysis Results')).toBeVisible();
  await expect(page.getByTestId('beat-check-panel')).toHaveCount(0);
});

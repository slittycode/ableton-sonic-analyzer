import { expect, test } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const testDir = path.dirname(fileURLToPath(import.meta.url));
const fixture = fs.readFileSync(path.resolve(testDir, './fixtures/silence.wav'));

const metadata = {
  title: 'Linked reference',
  creator: 'Example Artist',
  durationSeconds: 10,
  attributionUrl: 'https://example.com/reference',
  filename: 'reference.wav',
  mimeType: 'audio/wav',
  sizeBytes: fixture.length,
  experimental: false,
};

function intake(status: string) {
  return {
    intakeId: 'intake-link-1',
    provider: 'direct',
    status,
    rightsConfirmedAt: '2026-06-19T00:00:00Z',
    metadata: status === 'ready' || status === 'completed' ? metadata : null,
    error: null,
    expiresAt: status === 'ready' ? '2026-06-19T00:15:00Z' : null,
    runId: status === 'completed' ? 'run-link-1' : null,
    createdAt: '2026-06-19T00:00:00Z',
    updatedAt: '2026-06-19T00:00:01Z',
  };
}

function runSnapshot(completed: boolean) {
  return {
    runId: 'run-link-1',
    source: {
      kind: 'link',
      provider: 'direct',
      title: metadata.title,
      creator: metadata.creator,
      attributionUrl: metadata.attributionUrl,
      rightsConfirmedAt: '2026-06-19T00:00:00Z',
      experimental: false,
    },
    requestedStages: {
      analysisMode: 'full',
      pitchNoteMode: 'off',
      pitchNoteBackend: 'auto',
      interpretationMode: 'off',
      interpretationProfile: 'producer_summary',
      interpretationModel: null,
      mt3Mode: 'off',
    },
    artifacts: {
      sourceAudio: {
        artifactId: 'artifact-link-1',
        filename: metadata.filename,
        mimeType: metadata.mimeType,
        sizeBytes: metadata.sizeBytes,
        contentSha256: 'link-hash',
      },
    },
    stages: {
      measurement: {
        status: completed ? 'completed' : 'queued',
        authoritative: true,
        result: completed ? {
          bpm: 120,
          bpmConfidence: 0.9,
          key: 'A minor',
          keyConfidence: 0.8,
          timeSignature: '4/4',
          durationSeconds: 10,
          lufsIntegrated: -12,
          truePeak: -1,
          stereoWidth: 0.5,
          stereoCorrelation: 0.9,
          spectralBalance: {
            subBass: 0,
            lowBass: 0,
            lowMids: 0,
            mids: 0,
            upperMids: 0,
            highs: 0,
            brilliance: 0,
          },
        } : null,
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
        status: 'not_requested',
        authoritative: false,
        preferredAttemptId: null,
        attemptsSummary: [],
        result: null,
        provenance: null,
        diagnostics: null,
        error: null,
      },
    },
  };
}

test('check link, prepare audio, and continue through the normal results workflow', async ({ page }) => {
  await page.addInitScript(() => {
    const original = URL.revokeObjectURL.bind(URL);
    (window as typeof window & { revokedObjectUrls: number }).revokedObjectUrls = 0;
    URL.revokeObjectURL = (url: string) => {
      (window as typeof window & { revokedObjectUrls: number }).revokedObjectUrls += 1;
      original(url);
    };
  });

  await page.route('**/api/audio-source-capabilities', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      limits: { maxBytes: 104857600, maxDurationSeconds: 900, maxActiveIntakes: 4 },
      providers: [
        { id: 'direct', enabled: true, experimental: false, environments: ['local', 'hosted'], missingSetup: [] },
      ],
    }),
  }));
  await page.route('**/api/audio-source-intakes', async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().postDataJSON()).toEqual({
      url: 'https://example.com/reference.wav',
      rightsConfirmed: true,
    });
    await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(intake('queued')) });
  });
  let intakePolls = 0;
  await page.route('**/api/audio-source-intakes/intake-link-1', async (route) => {
    intakePolls += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(intake(intakePolls > 1 ? 'ready' : 'fetching')),
    });
  });
  await page.route('**/api/audio-source-intakes/intake-link-1/estimate', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      estimate: {
        durationSeconds: 10,
        totalLowMs: 1000,
        totalHighMs: 2000,
        stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 1000, highMs: 2000 }],
      },
    }),
  }));
  await page.route('**/api/audio-source-intakes/intake-link-1/analysis-runs', (route) => route.fulfill({
    status: 202,
    contentType: 'application/json',
    body: JSON.stringify({ intakeId: 'intake-link-1', status: 'completed', runId: 'run-link-1' }),
  }));
  await page.route('**/api/analysis-runs/run-link-1/source-audio', (route) => route.fulfill({
    status: 200,
    contentType: 'audio/wav',
    headers: { 'Content-Disposition': 'attachment; filename="reference.wav"' },
    body: fixture,
  }));
  let runPolls = 0;
  await page.route('**/api/analysis-runs/run-link-1', (route) => {
    runPolls += 1;
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(runSnapshot(runPolls > 1)),
    });
  });

  await page.goto('/', { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'Paste link' }).click();
  await page.getByLabel('Music link').fill('https://example.com/reference.wav');
  const checkButton = page.getByRole('button', { name: 'Check link' });
  await expect(checkButton).toBeDisabled();
  await page.getByLabel('I own this audio or have permission to analyse it').check();
  await checkButton.click();

  await expect(page.getByText('Fetching source audio…')).toBeVisible();
  await expect(page.getByTestId('link-source-summary')).toContainText('direct');
  await expect(page.getByText('Example Artist — Linked reference')).toBeVisible();
  await expect(page.getByText('1s-2s')).toBeVisible();

  await page.getByLabel('PITCH/NOTE TRANSLATION').uncheck();
  await page.getByLabel('AI INTERPRETATION').uncheck();
  await page.getByRole('button', { name: 'Run Analysis' }).click();

  await expect(page.getByRole('heading', { name: 'Analysis Results' })).toBeVisible();
  await expect(page.getByTestId('analysis-results-subtitle')).toContainText('Linked reference');
  await page.getByRole('button', { name: /Analyze another link/ }).click();
  await expect.poll(() => page.evaluate(() => (
    window as typeof window & { revokedObjectUrls: number }
  ).revokedObjectUrls)).toBeGreaterThan(0);
});

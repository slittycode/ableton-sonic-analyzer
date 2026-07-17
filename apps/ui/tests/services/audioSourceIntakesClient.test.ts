import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createAnalysisRunFromIntake,
  createAudioSourceIntake,
  estimateAudioSourceIntake,
  getAudioSourceCapabilities,
  waitForAudioSourceIntake,
} from '../../src/services/audioSourceIntakesClient';

const readyIntake = {
  intakeId: 'intake-1',
  provider: 'direct',
  status: 'ready',
  rightsConfirmedAt: '2026-06-19T00:00:00Z',
  metadata: {
    title: 'Linked track',
    creator: 'Artist',
    durationSeconds: 30,
    attributionUrl: 'https://example.com/track',
    filename: 'track.wav',
    mimeType: 'audio/wav',
    sizeBytes: 100,
    experimental: false,
  },
  error: null,
  expiresAt: '2026-06-19T00:15:00Z',
  runId: null,
  createdAt: '2026-06-19T00:00:00Z',
  updatedAt: '2026-06-19T00:00:01Z',
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('audioSourceIntakesClient', () => {
  it('loads provider capability and limit information', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      limits: { maxBytes: 104857600, maxDurationSeconds: 900 },
      providers: [{ id: 'direct', enabled: true, experimental: false, environments: ['local'], missingSetup: [] }],
    }));
    vi.stubGlobal('fetch', fetchMock);

    const capabilities = await getAudioSourceCapabilities();

    expect(capabilities.limits.maxDurationSeconds).toBe(900);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/audio-source-capabilities'),
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('sends permission confirmation without placing the URL in the request path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ...readyIntake, status: 'queued', metadata: null }, 202));
    vi.stubGlobal('fetch', fetchMock);

    await createAudioSourceIntake('https://example.com/track.wav?token=secret', true);

    const [requestUrl, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(requestUrl).toMatch(/\/api\/audio-source-intakes$/);
    expect(requestUrl).not.toContain('secret');
    expect(JSON.parse(String(init.body))).toEqual({
      url: 'https://example.com/track.wav?token=secret',
      rightsConfirmed: true,
    });
  });

  it('returns a prepared intake and reports its progress update', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(readyIntake));
    vi.stubGlobal('fetch', fetchMock);
    const updates: string[] = [];

    const result = await waitForAudioSourceIntake('intake-1', (intake) => updates.push(intake.status));

    expect(result.status).toBe('ready');
    expect(updates).toEqual(['ready']);
  });

  it('uses stored duration for estimates', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      estimate: { durationSeconds: 30, totalLowMs: 1000, totalHighMs: 2000, stages: [] },
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await estimateAudioSourceIntake('intake-1', {
      analysisMode: 'full',
      pitchNoteMode: 'off',
      pitchNoteBackend: 'auto',
      interpretationMode: 'off',
      interpretationProfile: 'producer_summary',
      mt3Mode: 'off',
    });

    expect(result.estimate.durationSeconds).toBe(30);
    expect(fetchMock.mock.calls[0][0]).toContain('/intake-1/estimate');
  });

  it('creates an intake run then resolves the canonical run snapshot', async () => {
    const runSnapshot = {
      runId: 'run-1',
      source: { kind: 'link', provider: 'direct', title: 'Linked track', creator: null, attributionUrl: null, rightsConfirmedAt: null, experimental: false },
      requestedStages: { analysisMode: 'full', pitchNoteMode: 'off', pitchNoteBackend: 'auto', interpretationMode: 'off', interpretationProfile: 'producer_summary', interpretationModel: null, mt3Mode: 'off' },
      artifacts: { sourceAudio: { artifactId: 'a', filename: 'track.wav', mimeType: 'audio/wav', sizeBytes: 100, contentSha256: 'hash' } },
      stages: {
        measurement: { status: 'queued', authoritative: true, result: null, provenance: null, diagnostics: null, error: null },
        pitchNoteTranslation: { status: 'not_requested', authoritative: false, preferredAttemptId: null, attemptsSummary: [], result: null, provenance: null, diagnostics: null, error: null },
        interpretation: { status: 'not_requested', authoritative: false, preferredAttemptId: null, attemptsSummary: [], result: null, provenance: null, diagnostics: null, error: null },
        mt3: { status: 'not_requested', publicStatus: null, authoritative: false, preferredAttemptId: null, attemptsSummary: [], result: null, provenance: null, diagnostics: null, error: null },
      },
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ intakeId: 'intake-1', status: 'completed', runId: 'run-1' }, 202))
      .mockResolvedValueOnce(jsonResponse(runSnapshot));
    vi.stubGlobal('fetch', fetchMock);

    const result = await createAnalysisRunFromIntake('intake-1', {
      analysisMode: 'full',
      pitchNoteMode: 'off',
      pitchNoteBackend: 'auto',
      interpretationMode: 'off',
      interpretationProfile: 'producer_summary',
      mt3Mode: 'off',
    });

    expect(result.runId).toBe('run-1');
    expect(result.source.kind).toBe('link');
    expect(fetchMock.mock.calls[1][0]).toContain('/api/analysis-runs/run-1');
  });
});

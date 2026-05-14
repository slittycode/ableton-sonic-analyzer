import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  artifactStreamUrl,
  fetchExistingManifest,
  generateSamples,
  parseManifest,
} from '../../src/services/sampleGenerationClient';
import { BackendClientError } from '../../src/services/backendPhase1Client';

const baseManifest = {
  schemaVersion: 'samples.v1',
  runId: 'run-abc',
  generatedAt: '2026-05-14T20:31:00Z',
  synthesisBackend: 'sine_fallback',
  soundfont: null,
  framing: 'Heuristic audition.',
  theoryBackend: 'pytheory',
  samples: [
    {
      id: 'tonal_chord_progression',
      label: 'Chord progression in F# minor',
      category: 'tonal',
      filename: 'tonal_chord_progression.wav',
      mimeType: 'audio/wav',
      durationSeconds: 4.62,
      confidence: 'HIGH',
      lowConfidence: false,
      cites: {
        phase1Fields: ['key', 'keyConfidence', 'bpm'],
        phase2Recommendations: [],
        rationale: 'Diatonic progression in F# minor.',
      },
      midiFilename: 'tonal_chord_progression.mid',
      artifactId: 'art-1',
      midiArtifactId: 'art-mid-1',
    },
    {
      id: 'drum_kick',
      label: 'Kick at 55 Hz',
      category: 'drums',
      filename: 'drum_kick.wav',
      mimeType: 'audio/wav',
      durationSeconds: 0.45,
      confidence: 'HIGH',
      lowConfidence: false,
      cites: {
        phase1Fields: ['kickDetail.fundamentalHz'],
        phase2Recommendations: [],
        rationale: 'Sub-sine at measured fundamental.',
      },
      artifactId: 'art-2',
    },
  ],
};

describe('parseManifest', () => {
  it('parses a well-formed manifest', () => {
    const parsed = parseManifest(baseManifest);
    expect(parsed.schemaVersion).toBe('samples.v1');
    expect(parsed.runId).toBe('run-abc');
    expect(parsed.synthesisBackend).toBe('sine_fallback');
    expect(parsed.theoryBackend).toBe('pytheory');
    expect(parsed.samples).toHaveLength(2);
    expect(parsed.samples[0].category).toBe('tonal');
    expect(parsed.samples[0].cites.phase1Fields).toEqual([
      'key',
      'keyConfidence',
      'bpm',
    ]);
    expect(parsed.samples[1].artifactId).toBe('art-2');
  });

  it('rejects unrecognized schema versions', () => {
    expect(() => parseManifest({ ...baseManifest, schemaVersion: 'samples.v9' })).toThrow(
      BackendClientError,
    );
  });

  it('rejects non-object payloads', () => {
    expect(() => parseManifest(null)).toThrow(BackendClientError);
    expect(() => parseManifest('not a manifest')).toThrow(BackendClientError);
  });

  it('normalizes unknown synthesis backends to the safe fallback', () => {
    const parsed = parseManifest({ ...baseManifest, synthesisBackend: 'some-future-thing' });
    expect(parsed.synthesisBackend).toBe('sine_fallback');
  });

  it('coerces unknown category and confidence values to safe defaults', () => {
    const malformed = {
      ...baseManifest,
      samples: [{ ...baseManifest.samples[0], category: 'weird', confidence: 'HUH' }],
    };
    const parsed = parseManifest(malformed);
    expect(parsed.samples[0].category).toBe('tonal');
    expect(parsed.samples[0].confidence).toBe('MED');
  });
});

describe('artifactStreamUrl', () => {
  it('encodes run and artifact ids', () => {
    const url = artifactStreamUrl('run/with slash', 'art ifact', 'http://api');
    expect(url).toBe(
      'http://api/api/analysis-runs/run%2Fwith%20slash/artifacts/art%20ifact',
    );
  });
});

describe('generateSamples + fetchExistingManifest', () => {
  const originalFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('generateSamples POSTs and returns parsed manifest', async () => {
    const mockFetch = vi.fn(async () =>
      new Response(JSON.stringify(baseManifest), {
        status: 201,
        headers: { 'content-type': 'application/json' },
      }),
    );
    globalThis.fetch = mockFetch as unknown as typeof fetch;

    const result = await generateSamples('run-abc', { apiBaseUrl: 'http://api' });
    expect(result.runId).toBe('run-abc');
    expect(mockFetch).toHaveBeenCalledOnce();
    const [calledUrl, calledInit] = mockFetch.mock.calls[0];
    expect(calledUrl).toBe('http://api/api/analysis-runs/run-abc/samples');
    expect((calledInit as RequestInit).method).toBe('POST');
  });

  it('generateSamples adds force=true query param', async () => {
    const mockFetch = vi.fn(async () =>
      new Response(JSON.stringify(baseManifest), {
        status: 201,
        headers: { 'content-type': 'application/json' },
      }),
    );
    globalThis.fetch = mockFetch as unknown as typeof fetch;

    await generateSamples('run-abc', { apiBaseUrl: 'http://api', force: true });
    const [calledUrl] = mockFetch.mock.calls[0];
    expect(calledUrl).toBe('http://api/api/analysis-runs/run-abc/samples?force=true');
  });

  it('fetchExistingManifest returns null when the server reports SAMPLES_NOT_GENERATED', async () => {
    const mockFetch = vi.fn(async () =>
      new Response(
        JSON.stringify({
          error: { code: 'SAMPLES_NOT_GENERATED', message: 'not yet' },
        }),
        { status: 404, headers: { 'content-type': 'application/json' } },
      ),
    );
    globalThis.fetch = mockFetch as unknown as typeof fetch;

    const result = await fetchExistingManifest('run-abc', { apiBaseUrl: 'http://api' });
    expect(result).toBeNull();
  });

  it('fetchExistingManifest rethrows other backend errors', async () => {
    const mockFetch = vi.fn(async () =>
      new Response(
        JSON.stringify({ error: { code: 'UNEXPECTED', message: 'boom' } }),
        { status: 500, headers: { 'content-type': 'application/json' } },
      ),
    );
    globalThis.fetch = mockFetch as unknown as typeof fetch;

    await expect(
      fetchExistingManifest('run-abc', { apiBaseUrl: 'http://api' }),
    ).rejects.toBeInstanceOf(BackendClientError);
  });
});

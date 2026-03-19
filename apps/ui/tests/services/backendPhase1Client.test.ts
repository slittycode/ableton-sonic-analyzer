import {
  estimatePhase1WithBackend,
  parseBackendAnalyzeResponse,
  BackendClientError,
  deriveAnalyzeTimeoutMs,
  mapBackendError,
  resetBackendIdentityCacheForTests,
} from '../../src/services/backendPhase1Client';
import { afterEach, vi } from 'vitest';

const validPayload = {
  requestId: 'req_123',
  phase1: {
    bpm: 128,
    bpmConfidence: 0.98,
    key: 'A minor',
    keyConfidence: 0.91,
    timeSignature: '4/4',
    durationSeconds: 184.2,
    lufsIntegrated: -8.4,
    lufsRange: 3.1,
    truePeak: -0.5,
    crestFactor: 8.6,
    stereoWidth: 0.75,
    stereoCorrelation: 0.82,
    stereoDetail: {
      stereoWidth: 0.75,
      stereoCorrelation: 0.82,
      subBassMono: true,
    },
    spectralBalance: {
      subBass: -1.2,
      lowBass: 0.8,
      mids: -0.4,
      upperMids: 0.2,
      highs: 1.1,
      brilliance: 0.5,
    },
    spectralDetail: {
      spectralCentroidMean: 1820.5,
    },
    rhythmDetail: {
      grooveAmount: 0.42,
    },
    melodyDetail: {
      noteCount: 3,
      notes: [
        { midi: 60, onset: 0.1, duration: 0.25 },
        { midi: 64, onset: 0.4, duration: 0.3 },
        { midi: 67, onset: 0.8, duration: 0.2 },
      ],
      dominantNotes: [60, 64, 67],
      pitchRange: { min: 60, max: 67 },
      pitchConfidence: 0.71,
      midiFile: '/tmp/example.mid',
      sourceSeparated: true,
      vibratoPresent: false,
      vibratoExtent: 0.0,
      vibratoRate: 0.0,
      vibratoConfidence: 0.05,
    },
    transcriptionDetail: {
      transcriptionMethod: 'basic-pitch-legacy',
      noteCount: 2,
      averageConfidence: 0.83,
      stemSeparationUsed: true,
      fullMixFallback: false,
      stemsTranscribed: ['bass', 'other'],
      dominantPitches: [
        { pitchMidi: 48, pitchName: 'C3', count: 5 },
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
    grooveDetail: {
      grooveAmount: 0.42,
    },
    sidechainDetail: {
      confidence: 0.31,
    },
    acidDetail: {
      isAcid: true,
      confidence: 0.68,
      resonanceLevel: 0.45,
      centroidOscillationHz: 120,
      bassRhythmDensity: 6.2,
    },
    reverbDetail: {
      rt60: 0.82,
      isWet: true,
      tailEnergyRatio: 0.41,
      measured: true,
    },
    vocalDetail: {
      hasVocals: true,
      confidence: 0.72,
      vocalEnergyRatio: 0.35,
      formantStrength: 0.48,
      mfccLikelihood: 0.61,
    },
    supersawDetail: {
      isSupersaw: false,
      confidence: 0.12,
      voiceCount: 1,
      avgDetuneCents: 3.2,
      spectralComplexity: 0.18,
    },
    bassDetail: {
      averageDecayMs: 85,
      type: 'punchy',
      transientRatio: 0.72,
      fundamentalHz: 55,
      transientCount: 48,
      swingPercent: 3.5,
      grooveType: 'straight',
    },
    kickDetail: {
      isDistorted: false,
      thd: 0.08,
      harmonicRatio: 0.22,
      fundamentalHz: 52,
      kickCount: 64,
    },
    effectsDetail: {
      reverbLikely: true,
    },
    synthesisCharacter: {
      analogLike: true,
    },
    danceability: {
      danceability: 1.24,
      dfa: 0.87,
    },
    structure: {
      sections: 5,
    },
    arrangementDetail: {
      sectionCount: 5,
    },
    segmentLoudness: [{ start: 0, value: -8.2 }],
    segmentSpectral: [
      {
        segmentIndex: 0,
        barkBands: Array.from({ length: 24 }, (_, i) => -20 + i * 0.5),
        spectralCentroid: 1820.5,
        spectralRolloff: 6120.2,
        stereoWidth: null,
        stereoCorrelation: null,
      },
      {
        segmentIndex: 1,
        barkBands: Array.from({ length: 24 }, (_, i) => -18 + i * 0.4),
        spectralCentroid: 2015.4,
        spectralRolloff: 6401.7,
        stereoWidth: null,
        stereoCorrelation: null,
      },
    ],
    segmentKey: [{ start: 0, key: 'A minor' }],
    chordDetail: {
      progression: ['Am', 'G'],
    },
    perceptual: {
      energy: 0.77,
    },
  },
  diagnostics: {
    backendDurationMs: 1420,
    engineVersion: '0.4.0',
    timings: {
      totalMs: 1560,
      analysisMs: 1420,
      serverOverheadMs: 140,
      flagsUsed: ['--transcribe'],
      fileSizeBytes: 543210,
      fileDurationSeconds: 184.2,
      msPerSecondOfAudio: 7.71,
    },
  },
};

const validEstimatePayload = {
  requestId: 'req_estimate_123',
  estimate: {
    durationSeconds: 214.6,
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
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  resetBackendIdentityCacheForTests();
});

describe('parseBackendAnalyzeResponse', () => {
  it('accepts a valid backend payload', () => {
    const parsed = parseBackendAnalyzeResponse({
      ...validPayload,
      analysisRunId: 'run_123',
    });

    expect(parsed.requestId).toBe('req_123');
    expect(parsed.analysisRunId).toBe('run_123');
    expect(parsed.phase1.bpm).toBe(128);
    expect(parsed.diagnostics?.engineVersion).toBe('0.4.0');
    expect(parsed.diagnostics?.timings).toEqual(validPayload.diagnostics.timings);
    expect(parsed.phase1.melodyDetail?.noteCount).toBe(3);
    expect(parsed.phase1.melodyDetail?.notes[0].midi).toBe(60);
    expect(parsed.phase1.transcriptionDetail?.noteCount).toBe(2);
    expect(parsed.phase1.transcriptionDetail?.fullMixFallback).toBe(false);
    expect(parsed.phase1.transcriptionDetail?.notes[0].stemSource).toBe('bass');
    expect(parsed.phase1.lufsRange).toBe(3.1);
    expect(parsed.phase1.crestFactor).toBe(8.6);
    expect(parsed.phase1.stereoDetail).toEqual(validPayload.phase1.stereoDetail);
    expect(parsed.phase1.structure).toEqual(validPayload.phase1.structure);
    expect(parsed.phase1.segmentLoudness).toEqual(validPayload.phase1.segmentLoudness);
    expect(parsed.phase1.segmentSpectral).toEqual(validPayload.phase1.segmentSpectral);
    expect(parsed.phase1.perceptual).toEqual(validPayload.phase1.perceptual);
    expect(parsed.phase1.danceability).toEqual(validPayload.phase1.danceability);

    // Detector fields survive parsing
    expect(parsed.phase1.acidDetail).toEqual({
      isAcid: true,
      confidence: 0.68,
      resonanceLevel: 0.45,
      centroidOscillationHz: 120,
      bassRhythmDensity: 6.2,
    });
    expect(parsed.phase1.reverbDetail).toEqual({
      rt60: 0.82,
      isWet: true,
      tailEnergyRatio: 0.41,
      measured: true,
    });
    expect(parsed.phase1.vocalDetail).toEqual({
      hasVocals: true,
      confidence: 0.72,
      vocalEnergyRatio: 0.35,
      formantStrength: 0.48,
      mfccLikelihood: 0.61,
    });
    expect(parsed.phase1.supersawDetail).toEqual({
      isSupersaw: false,
      confidence: 0.12,
      voiceCount: 1,
      avgDetuneCents: 3.2,
      spectralComplexity: 0.18,
    });
    expect(parsed.phase1.bassDetail).toEqual({
      averageDecayMs: 85,
      type: 'punchy',
      transientRatio: 0.72,
      fundamentalHz: 55,
      transientCount: 48,
      swingPercent: 3.5,
      grooveType: 'straight',
    });
    expect(parsed.phase1.kickDetail).toEqual({
      isDistorted: false,
      thd: 0.08,
      harmonicRatio: 0.22,
      fundamentalHz: 52,
      kickCount: 64,
    });
  });

  it('parses null/missing detector fields as null', () => {
    const payload = {
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        acidDetail: null,
        reverbDetail: null,
        vocalDetail: undefined,
        supersawDetail: null,
        bassDetail: null,
        kickDetail: null,
      },
    };
    const parsed = parseBackendAnalyzeResponse(payload);
    expect(parsed.phase1.acidDetail).toBeNull();
    expect(parsed.phase1.reverbDetail).toBeNull();
    expect(parsed.phase1.vocalDetail).toBeNull();
    expect(parsed.phase1.supersawDetail).toBeNull();
    expect(parsed.phase1.bassDetail).toBeNull();
    expect(parsed.phase1.kickDetail).toBeNull();
  });

  it('falls back to stereoDetail when top-level stereo fields are missing', () => {
    const payload = {
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        stereoWidth: undefined,
        stereoCorrelation: undefined,
        stereoDetail: {
          ...validPayload.phase1.stereoDetail,
          stereoWidth: 0.66,
          stereoCorrelation: 0.79,
        },
      },
    };

    const parsed = parseBackendAnalyzeResponse(payload);
    expect(parsed.phase1.stereoWidth).toBe(0.66);
    expect(parsed.phase1.stereoCorrelation).toBe(0.79);
  });

  it('throws when phase1 is missing', () => {
    expect(() =>
      parseBackendAnalyzeResponse({
        requestId: 'req_123',
      }),
    ).toThrow(/phase1/i);
  });

  it('throws when spectralBalance contains non-numeric values', () => {
    expect(() =>
      parseBackendAnalyzeResponse({
        ...validPayload,
        phase1: {
          ...validPayload.phase1,
          spectralBalance: {
            ...validPayload.phase1.spectralBalance,
            mids: 'invalid',
          },
        },
      }),
    ).toThrow(/spectralBalance/i);
  });

  it('throws when diagnostics.timings contains malformed values', () => {
    expect(() =>
      parseBackendAnalyzeResponse({
        ...validPayload,
        diagnostics: {
          ...validPayload.diagnostics,
          timings: {
            ...validPayload.diagnostics.timings,
            flagsUsed: ['--transcribe', 7],
          },
        },
      }),
    ).toThrow(/flagsUsed/i);
  });

  it('parses payloads that omit melodyDetail', () => {
    const parsed = parseBackendAnalyzeResponse({
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        melodyDetail: undefined,
      },
    });

    expect(parsed.phase1.melodyDetail).toBeUndefined();
  });

  it('sanitizes malformed melodyDetail instead of crashing', () => {
    const parsed = parseBackendAnalyzeResponse({
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        melodyDetail: {
          noteCount: 'three',
          notes: [
            { midi: 'C4', onset: 0.2, duration: 0.5 },
            { midi: 200, onset: -2, duration: 0.1 },
            { midi: 64, onset: 0.6, duration: -1 },
          ],
          dominantNotes: [63.7, 'bad', 150],
          pitchRange: { min: 'bad', max: 300 },
          pitchConfidence: 5,
          midiFile: 123,
          sourceSeparated: 'true',
          vibratoPresent: 'yes',
          vibratoExtent: 'none',
          vibratoRate: null,
          vibratoConfidence: -3,
        },
      },
    });

    expect(parsed.phase1.melodyDetail).toBeDefined();
    expect(parsed.phase1.melodyDetail?.notes).toEqual([{ midi: 127, onset: 0, duration: 0.1 }]);
    expect(parsed.phase1.melodyDetail?.noteCount).toBe(1);
    expect(parsed.phase1.melodyDetail?.dominantNotes).toEqual([64, 127]);
    expect(parsed.phase1.melodyDetail?.pitchRange).toEqual({ min: null, max: 127 });
    expect(parsed.phase1.melodyDetail?.pitchConfidence).toBe(1);
    expect(parsed.phase1.melodyDetail?.vibratoConfidence).toBe(0);
    expect(parsed.phase1.melodyDetail?.midiFile).toBeNull();
    expect(parsed.phase1.melodyDetail?.sourceSeparated).toBe(false);
  });

  it('parses explicit fullMixFallback and only falls back when stemSeparationUsed is explicitly false', () => {
    const explicitFullMix = parseBackendAnalyzeResponse({
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        transcriptionDetail: {
          ...validPayload.phase1.transcriptionDetail,
          fullMixFallback: true,
          stemSeparationUsed: false,
        },
      },
    });

    const inferredFullMix = parseBackendAnalyzeResponse({
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        transcriptionDetail: {
          ...validPayload.phase1.transcriptionDetail,
          fullMixFallback: undefined,
          stemSeparationUsed: false,
        },
      },
    });

    const missingFieldsStayFalse = parseBackendAnalyzeResponse({
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        transcriptionDetail: {
          ...validPayload.phase1.transcriptionDetail,
          fullMixFallback: undefined,
          stemSeparationUsed: undefined,
        },
      },
    });

    expect(explicitFullMix.phase1.transcriptionDetail?.fullMixFallback).toBe(true);
    expect(inferredFullMix.phase1.transcriptionDetail?.fullMixFallback).toBe(true);
    expect(missingFieldsStayFalse.phase1.transcriptionDetail?.fullMixFallback).toBe(false);
  });

  it('treats malformed optional danceability objects as null', () => {
    const parsed = parseBackendAnalyzeResponse({
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        danceability: {
          danceability: 'high',
          dfa: null,
        },
      },
    });

    expect(parsed.phase1.danceability).toBeNull();
  });

  it('sanitizes segmentSpectral entries and drops malformed rows', () => {
    const parsed = parseBackendAnalyzeResponse({
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        segmentSpectral: [
          {
            segmentIndex: 2,
            barkBands: [-12.4, -11.7, -9.1],
            spectralCentroid: 1600.3,
          },
          {
            segmentIndex: 1,
            barkBands: [-10, 'bad', -8.8],
            spectralCentroid: 'invalid',
          },
          {
            segmentIndex: 'x',
            barkBands: [-5, -4, -3],
          },
          {
            segmentIndex: 4,
            barkBands: [],
          },
        ],
      },
    });

    expect(parsed.phase1.segmentSpectral).toEqual([
      {
        segmentIndex: 1,
        barkBands: [-10, -8.8],
        spectralCentroid: null,
        spectralRolloff: null,
        stereoWidth: null,
        stereoCorrelation: null,
      },
      {
        segmentIndex: 2,
        barkBands: [-12.4, -11.7, -9.1],
        spectralCentroid: 1600.3,
        spectralRolloff: null,
        stereoWidth: null,
        stereoCorrelation: null,
      },
    ]);
  });
});

describe('mapBackendError', () => {
  it('maps network failures to a user-friendly message', () => {
    const mapped = mapBackendError(new TypeError('Failed to fetch'));

    expect(mapped).toBeInstanceOf(BackendClientError);
    expect(mapped.code).toBe('NETWORK_UNREACHABLE');
    expect(mapped.message).toMatch(/Cannot reach the local DSP backend/i);
  });

  it('preserves explicit backend client errors', () => {
    const original = new BackendClientError('BACKEND_HTTP_ERROR', 'Backend failed', {
      status: 502,
    });

    const mapped = mapBackendError(original);

    expect(mapped).toBe(original);
    expect(mapped.details?.status).toBe(502);
  });

  it('maps AbortError to a client timeout with the configured timeout budget', () => {
    const mapped = mapBackendError(
      new DOMException('The operation was aborted.', 'AbortError'),
      { timeoutMs: 456000 },
    );

    expect(mapped).toBeInstanceOf(BackendClientError);
    expect(mapped.code).toBe('CLIENT_TIMEOUT');
    expect(mapped.message).toBe('The UI timed out waiting for the local DSP backend response.');
    expect(mapped.details?.timeoutMs).toBe(456000);
  });
});

describe('deriveAnalyzeTimeoutMs', () => {
  it('adds a one-minute buffer to larger estimate highs', () => {
    expect(deriveAnalyzeTimeoutMs(396000)).toBe(456000);
  });

  it('enforces a minimum timeout floor for short estimate highs', () => {
    expect(deriveAnalyzeTimeoutMs(38000)).toBe(180000);
  });

  it('falls back to the long default when no estimate is available', () => {
    expect(deriveAnalyzeTimeoutMs()).toBe(600000);
  });
});

describe('estimatePhase1WithBackend', () => {
  it('parses the backend preflight estimate contract', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(validEstimatePayload), {
          status: 200,
          headers: {
            'Content-Type': 'application/json',
          },
        }),
      ),
    );

    const result = await estimatePhase1WithBackend(
      new File(['wave'], 'track.mp3', { type: 'audio/mpeg' }),
      { apiBaseUrl: 'http://127.0.0.1:8100' },
    );

    expect(result.requestId).toBe('req_estimate_123');
    expect(result.estimate.totalLowMs).toBe(22000);
    expect(result.estimate.stages[0].key).toBe('local_dsp');
  });

  it('sends the current transcribe and separate flags to the estimate endpoint', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const formData = init?.body as FormData;
      expect(formData.get('transcribe')).toBe('true');
      expect(formData.get('separate')).toBe('true');

      return new Response(JSON.stringify(validEstimatePayload), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
        },
      });
    });

    vi.stubGlobal('fetch', fetchMock);

    await estimatePhase1WithBackend(
      new File(['wave'], 'track.mp3', { type: 'audio/mpeg' }),
      { apiBaseUrl: 'http://127.0.0.1:8100', transcribe: true, separate: true },
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('classifies route-style estimate failures as wrong-service when openapi identifies another API', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);

        if (url.endsWith('/api/analyze/estimate')) {
          return new Response(JSON.stringify({ detail: 'Not Found' }), {
            status: 404,
            headers: {
              'Content-Type': 'application/json',
            },
          });
        }

        if (url.endsWith('/openapi.json')) {
          return new Response(
            JSON.stringify({
              info: { title: 'Multi-Agent Dashboard API' },
              paths: {
                '/api/state': {},
              },
            }),
            {
              status: 200,
              headers: {
                'Content-Type': 'application/json',
              },
            },
          );
        }

        throw new Error(`Unexpected fetch URL: ${url}`);
      }),
    );

    await expect(
      estimatePhase1WithBackend(
        new File(['wave'], 'track.mp3', { type: 'audio/mpeg' }),
        { apiBaseUrl: 'http://localhost:8000' },
      ),
    ).rejects.toMatchObject({
      code: 'BACKEND_WRONG_SERVICE',
      message: expect.stringContaining('http://127.0.0.1:8100'),
      details: {
        status: 404,
        configuredBaseUrl: 'http://localhost:8000',
        detectedServiceTitle: 'Multi-Agent Dashboard API',
      },
    });
  });

  it('mentions stale local env overrides in the wrong-service guidance for legacy localhost:8000 configs', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);

        if (url.endsWith('/api/analyze/estimate')) {
          return new Response(JSON.stringify({ detail: 'Not Found' }), {
            status: 404,
            headers: {
              'Content-Type': 'application/json',
            },
          });
        }

        if (url.endsWith('/openapi.json')) {
          return new Response(
            JSON.stringify({
              info: { title: 'Multi-Agent Dashboard API' },
              paths: {
                '/api/state': {},
              },
            }),
            {
              status: 200,
              headers: {
                'Content-Type': 'application/json',
              },
            },
          );
        }

        throw new Error(`Unexpected fetch URL: ${url}`);
      }),
    );

    await expect(
      estimatePhase1WithBackend(
        new File(['wave'], 'track.mp3', { type: 'audio/mpeg' }),
        { apiBaseUrl: 'http://localhost:8000' },
      ),
    ).rejects.toMatchObject({
      code: 'BACKEND_WRONG_SERVICE',
      message: expect.stringContaining('stale local'),
    });
  });

  it('reuses cached backend identity results across estimate and analyze requests', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith('/api/analyze/estimate') || url.endsWith('/api/analyze')) {
        return new Response(JSON.stringify({ detail: 'Not Found' }), {
          status: 404,
          headers: {
            'Content-Type': 'application/json',
          },
        });
      }

      if (url.endsWith('/openapi.json')) {
        return new Response(
          JSON.stringify({
            info: { title: 'Multi-Agent Dashboard API' },
            paths: {
              '/api/state': {},
            },
          }),
          {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
            },
          },
        );
      }

      throw new Error(`Unexpected fetch URL: ${url}`);
    });

    vi.stubGlobal('fetch', fetchMock);

    await expect(
      estimatePhase1WithBackend(
        new File(['wave'], 'track.mp3', { type: 'audio/mpeg' }),
        { apiBaseUrl: 'http://127.0.0.1:8100' },
      ),
    ).rejects.toMatchObject({ code: 'BACKEND_WRONG_SERVICE' });

    const openApiCalls = fetchMock.mock.calls.filter(([input]) => String(input).endsWith('/openapi.json'));
    expect(openApiCalls).toHaveLength(1);
  });
});

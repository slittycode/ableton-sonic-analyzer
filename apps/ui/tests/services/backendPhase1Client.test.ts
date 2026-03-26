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
    bpmPercival: 127.5,
    bpmAgreement: true,
    key: 'A minor',
    keyConfidence: 0.91,
    keyProfile: 'edma',
    tuningFrequency: 440.12,
    tuningCents: 0.05,
    timeSignature: '4/4',
    timeSignatureSource: 'assumed_four_four',
    timeSignatureConfidence: 0,
    durationSeconds: 184.2,
    sampleRate: 44100,
    lufsIntegrated: -8.4,
    lufsRange: 3.1,
    lufsMomentaryMax: -3.2,
    lufsShortTermMax: -4.8,
    truePeak: -0.5,
    plr: 7.9,
    crestFactor: 8.6,
    dynamicSpread: 0.42,
    dynamicCharacter: {
      dynamicComplexity: 0.5,
      loudnessVariation: 0.3,
      spectralFlatness: 0.2,
      logAttackTime: -0.8,
      attackTimeStdDev: 0.15,
    },
    stereoWidth: 0.75,
    stereoCorrelation: 0.82,
    stereoDetail: {
      stereoWidth: 0.75,
      stereoCorrelation: 0.82,
      subBassMono: true,
    },
    monoCompatible: true,
    spectralBalance: {
      subBass: -1.2,
      lowBass: 0.8,
      lowMids: 0.0,
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
      transcriptionMethod: 'torchcrepe-viterbi',
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
    beatsLoudness: {
      kickDominantRatio: 0.45,
      midDominantRatio: 0.35,
      highDominantRatio: 0.20,
      accentPattern: [1.0, 0.6, 0.8, 0.5],
      meanBeatLoudness: 0.32,
      beatLoudnessVariation: 0.18,
      beatCount: 256,
    },
    sidechainDetail: {
      pumpingStrength: 0.65,
      pumpingConfidence: 0.31,
      pumpingRegularity: 0.82,
      pumpingRate: 'quarter',
      envelopeShape: [1.0, 0.9, 0.7, 0.5, 0.3, 0.2, 0.15, 0.1, 0.08, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01, 0.005],
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
    segmentSpectral: [{ start: 0, centroid: 1820.5 }],
    segmentStereo: [{ segmentIndex: 0, stereoWidth: 0.8, stereoCorrelation: 0.9 }],
    segmentKey: [{ segmentIndex: 0, key: 'A minor', keyConfidence: 0.85 }],
    essentiaFeatures: {
      zeroCrossingRate: 0.12,
      hfc: 0.45,
      spectralComplexity: 0.33,
      dissonance: 0.21,
    },
    chordDetail: {
      progression: ['Am', 'G'],
    },
    perceptual: {
      energy: 0.77,
    },

    // BPM correction metadata
    bpmDoubletime: false,
    bpmSource: 'rhythm_extractor_confirmed',
    bpmRawOriginal: 128.0,

    // Detectors
    acidDetail: {
      isAcid: false,
      confidence: 0.12,
      resonanceLevel: 0.08,
      centroidOscillationHz: 120.5,
      bassRhythmDensity: 0.45,
    },
    reverbDetail: {
      rt60: 1.2,
      isWet: true,
      tailEnergyRatio: 0.35,
      measured: true,
    },
    vocalDetail: {
      hasVocals: false,
      confidence: 0.85,
      vocalEnergyRatio: 0.02,
      formantStrength: 0.05,
      mfccLikelihood: 0.1,
    },
    supersawDetail: {
      isSupersaw: false,
      confidence: 0.08,
      voiceCount: 1,
      avgDetuneCents: 2.5,
      spectralComplexity: 0.15,
    },
    bassDetail: {
      averageDecayMs: 45,
      type: 'punchy',
      transientRatio: 0.72,
      fundamentalHz: 55.0,
      transientCount: 128,
      swingPercent: 3.2,
      grooveType: 'straight',
    },
    kickDetail: {
      isDistorted: false,
      thd: 0.08,
      harmonicRatio: 0.35,
      fundamentalHz: 52.0,
      kickCount: 256,
    },
    genreDetail: {
      genre: 'techno',
      confidence: 0.82,
      secondaryGenre: 'tech house',
      genreFamily: 'techno',
      topScores: [
        { genre: 'techno', score: 0.82 },
        { genre: 'tech house', score: 0.65 },
      ],
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
    expect(parsed.phase1.plr).toBe(7.9);
    expect(parsed.phase1.crestFactor).toBe(8.6);
    expect(parsed.phase1.stereoDetail).toEqual(validPayload.phase1.stereoDetail);
    expect(parsed.phase1.monoCompatible).toBe(true);
    expect(parsed.phase1.spectralBalance.lowMids).toBe(0.0);
    expect(parsed.phase1.structure).toEqual(validPayload.phase1.structure);
    expect(parsed.phase1.segmentLoudness).toEqual(validPayload.phase1.segmentLoudness);
    expect(parsed.phase1.perceptual).toEqual(validPayload.phase1.perceptual);
    expect(parsed.phase1.danceability).toEqual(validPayload.phase1.danceability);

    // New fields
    expect(parsed.phase1.bpmPercival).toBe(127.5);
    expect(parsed.phase1.bpmAgreement).toBe(true);
    expect(parsed.phase1.keyProfile).toBe('edma');
    expect(parsed.phase1.tuningFrequency).toBe(440.12);
    expect(parsed.phase1.tuningCents).toBe(0.05);
    expect(parsed.phase1.timeSignatureSource).toBe('assumed_four_four');
    expect(parsed.phase1.timeSignatureConfidence).toBe(0);
    expect(parsed.phase1.sampleRate).toBe(44100);
    expect(parsed.phase1.lufsMomentaryMax).toBe(-3.2);
    expect(parsed.phase1.lufsShortTermMax).toBe(-4.8);
    expect(parsed.phase1.dynamicSpread).toBe(0.42);
    expect(parsed.phase1.dynamicCharacter).toEqual(validPayload.phase1.dynamicCharacter);
    expect(parsed.phase1.beatsLoudness?.kickDominantRatio).toBe(0.45);
    expect(parsed.phase1.beatsLoudness?.accentPattern).toEqual([1.0, 0.6, 0.8, 0.5]);
    expect(parsed.phase1.beatsLoudness?.beatCount).toBe(256);
    expect(parsed.phase1.sidechainDetail).toEqual(validPayload.phase1.sidechainDetail);
    expect(parsed.phase1.segmentStereo).toEqual(validPayload.phase1.segmentStereo);
    expect(parsed.phase1.segmentKey).toEqual(validPayload.phase1.segmentKey);
    expect(parsed.phase1.essentiaFeatures).toEqual(validPayload.phase1.essentiaFeatures);

    // BPM correction metadata
    expect(parsed.phase1.bpmDoubletime).toBe(false);
    expect(parsed.phase1.bpmSource).toBe('rhythm_extractor_confirmed');
    expect(parsed.phase1.bpmRawOriginal).toBe(128.0);

    // Detector results
    expect(parsed.phase1.acidDetail?.isAcid).toBe(false);
    expect(parsed.phase1.acidDetail?.confidence).toBe(0.12);
    expect(parsed.phase1.reverbDetail?.isWet).toBe(true);
    expect(parsed.phase1.reverbDetail?.rt60).toBe(1.2);
    expect(parsed.phase1.vocalDetail?.hasVocals).toBe(false);
    expect(parsed.phase1.supersawDetail?.isSupersaw).toBe(false);
    expect(parsed.phase1.bassDetail?.type).toBe('punchy');
    expect(parsed.phase1.kickDetail?.kickCount).toBe(256);
    expect(parsed.phase1.genreDetail?.genre).toBe('techno');
    expect(parsed.phase1.genreDetail?.genreFamily).toBe('techno');
  });

  it('parses payload without new fields (backward compat)', () => {
    const minimalPhase1 = {
      bpm: 128,
      bpmConfidence: 0.98,
      key: 'A minor',
      keyConfidence: 0.91,
      timeSignature: '4/4',
      durationSeconds: 184.2,
      lufsIntegrated: -8.4,
      truePeak: -0.5,
      stereoWidth: 0.75,
      stereoCorrelation: 0.82,
      spectralBalance: validPayload.phase1.spectralBalance,
    };
    const parsed = parseBackendAnalyzeResponse({
      requestId: 'req_compat',
      phase1: minimalPhase1,
    });

    expect(parsed.phase1.bpm).toBe(128);
    expect(parsed.phase1.bpmPercival).toBeNull();
    expect(parsed.phase1.bpmAgreement).toBeNull();
    expect(parsed.phase1.keyProfile).toBeNull();
    expect(parsed.phase1.tuningFrequency).toBeNull();
    expect(parsed.phase1.timeSignatureSource).toBeNull();
    expect(parsed.phase1.timeSignatureConfidence).toBeNull();
    expect(parsed.phase1.sampleRate).toBeNull();
    expect(parsed.phase1.lufsMomentaryMax).toBeNull();
    expect(parsed.phase1.lufsShortTermMax).toBeNull();
    expect(parsed.phase1.plr).toBe(7.9);
    expect(parsed.phase1.dynamicSpread).toBeNull();
    expect(parsed.phase1.dynamicCharacter).toBeNull();
    expect(parsed.phase1.beatsLoudness).toBeNull();
    expect(parsed.phase1.segmentStereo).toBeNull();
    expect(parsed.phase1.essentiaFeatures).toBeNull();
    expect(parsed.phase1.bpmDoubletime).toBeNull();
    expect(parsed.phase1.bpmSource).toBeNull();
    expect(parsed.phase1.bpmRawOriginal).toBeNull();
    expect(parsed.phase1.monoCompatible).toBeNull();
    expect(parsed.phase1.acidDetail).toBeNull();
    expect(parsed.phase1.genreDetail).toBeNull();
  });

  it('throws when phase1 is missing', () => {
    expect(() =>
      parseBackendAnalyzeResponse({
        requestId: 'req_123',
      }),
    ).toThrow(/phase1/i);
  });

  it('falls back lowMids to mids when lowMids is absent', () => {
    const { lowMids: _ignoredLowMids, ...legacyBalance } = validPayload.phase1.spectralBalance;
    const parsed = parseBackendAnalyzeResponse({
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        spectralBalance: legacyBalance,
      },
    });

    expect(parsed.phase1.spectralBalance.lowMids).toBe(parsed.phase1.spectralBalance.mids);
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

  it('handles malformed detector payloads gracefully', () => {
    const malformedPayload = {
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        acidDetail: { isAcid: true }, // missing required numeric fields
        genreDetail: 'not an object',
        kickDetail: null,
      },
    };
    const parsed = parseBackendAnalyzeResponse(malformedPayload);
    expect(parsed.phase1.acidDetail).toBeNull();
    expect(parsed.phase1.genreDetail).toBeNull();
    expect(parsed.phase1.kickDetail).toBeNull();
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

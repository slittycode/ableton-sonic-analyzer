import {
  estimatePhase1WithBackend,
  parseBackendAnalyzeResponse,
  BackendClientError,
  deriveAnalyzeTimeoutMs,
  mapBackendError,
  resetBackendIdentityCacheForTests,
} from '../../src/services/backendPhase1Client';
import { afterEach, vi } from 'vitest';
import { validBackendAnalyzeResponse as validPayload } from '../fixtures/phase1FullPayload';

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
    expect(parsed.phase1.textureCharacter).toEqual(validPayload.phase1.textureCharacter);
    expect(parsed.phase1.beatsLoudness?.kickDominantRatio).toBe(0.45);
    expect(parsed.phase1.beatsLoudness?.patternBeatsPerBar).toBe(4);
    expect(parsed.phase1.beatsLoudness?.lowBandAccentPattern).toEqual([1.0, 0.3, 0.8, 0.2]);
    expect(parsed.phase1.beatsLoudness?.midBandAccentPattern).toEqual([0.2, 1.0, 0.4, 0.3]);
    expect(parsed.phase1.beatsLoudness?.highBandAccentPattern).toEqual([0.1, 0.2, 0.6, 1.0]);
    expect(parsed.phase1.beatsLoudness?.overallAccentPattern).toEqual([1.0, 0.6, 0.8, 0.5]);
    expect(parsed.phase1.beatsLoudness?.accentPattern).toEqual([1.0, 0.6, 0.8, 0.5]);
    expect(parsed.phase1.beatsLoudness?.beatCount).toBe(256);
    expect(parsed.phase1.rhythmTimeline?.beatsPerBar).toBe(4);
    expect(parsed.phase1.rhythmTimeline?.stepsPerBeat).toBe(4);
    expect(parsed.phase1.rhythmTimeline?.availableBars).toBe(16);
    expect(parsed.phase1.rhythmTimeline?.selectionMethod).toBe('representative_dsp_window');
    expect(parsed.phase1.rhythmTimeline?.windows).toHaveLength(2);
    expect(parsed.phase1.rhythmTimeline?.windows[0]?.bars).toBe(8);
    expect(parsed.phase1.rhythmTimeline?.windows[0]?.lowBandSteps).toHaveLength(128);
    expect(parsed.phase1.rhythmTimeline?.windows[1]?.bars).toBe(16);
    expect(parsed.phase1.rhythmTimeline?.windows[1]?.overallSteps).toHaveLength(256);
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
    // Contract-drift guard: the reverb/vocal subfields the Phase 2 prompt may
    // cite must survive parsing, or legitimate citations fail the existence check.
    expect(parsed.phase1.reverbDetail?.perBandRt60).toEqual({
      low: 1.4,
      lowMids: 1.1,
      highMids: 0.8,
      highs: 0.5,
    });
    expect(parsed.phase1.reverbDetail?.preDelayMs).toBe(22.5);
    expect(parsed.phase1.vocalDetail?.hasVocals).toBe(false);
    expect(parsed.phase1.vocalDetail?.stemEnergyRatio).toBe(0.12);
    expect(parsed.phase1.vocalDetail?.stemOtherCorrelation).toBe(0.41);
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
    expect(parsed.phase1.textureCharacter).toBeNull();
    expect(parsed.phase1.beatsLoudness).toBeNull();
    expect(parsed.phase1.rhythmTimeline).toBeNull();
    expect(parsed.phase1.segmentStereo).toBeNull();
    expect(parsed.phase1.essentiaFeatures).toBeNull();
    expect(parsed.phase1.bpmDoubletime).toBeNull();
    expect(parsed.phase1.bpmSource).toBeNull();
    expect(parsed.phase1.bpmRawOriginal).toBeNull();
    expect(parsed.phase1.monoCompatible).toBeNull();
    expect(parsed.phase1.acidDetail).toBeNull();
    expect(parsed.phase1.genreDetail).toBeNull();
  });

  it('falls back gracefully when legacy beatsLoudness payload omits the new pattern arrays', () => {
    const parsed = parseBackendAnalyzeResponse({
      requestId: 'req_legacy_beats',
      phase1: {
        ...validPayload.phase1,
        beatsLoudness: {
          kickDominantRatio: 0.45,
          midDominantRatio: 0.35,
          highDominantRatio: 0.2,
          accentPattern: [1.0, 0.6, 0.8, 0.5],
          meanBeatLoudness: 0.32,
          beatLoudnessVariation: 0.18,
          beatCount: 256,
        },
      },
    });

    expect(parsed.phase1.beatsLoudness?.patternBeatsPerBar).toBe(4);
    expect(parsed.phase1.beatsLoudness?.overallAccentPattern).toEqual([1.0, 0.6, 0.8, 0.5]);
    expect(parsed.phase1.beatsLoudness?.lowBandAccentPattern).toEqual([0, 0, 0, 0]);
    expect(parsed.phase1.beatsLoudness?.midBandAccentPattern).toEqual([0, 0, 0, 0]);
    expect(parsed.phase1.beatsLoudness?.highBandAccentPattern).toEqual([0, 0, 0, 0]);
  });

  it('sanitizes malformed rhythmTimeline windows instead of crashing the rest of phase1 parsing', () => {
    const parsed = parseBackendAnalyzeResponse({
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        rhythmTimeline: {
          beatsPerBar: 4,
          stepsPerBeat: 4,
          availableBars: 12,
          selectionMethod: 'representative_dsp_window',
          windows: [
            {
              bars: 8,
              startBar: 3,
              endBar: 10,
              lowBandSteps: [1, 0, 1],
              midBandSteps: 'bad',
              highBandSteps: null,
              overallSteps: undefined,
            },
          ],
        },
      },
    });

    expect(parsed.phase1.rhythmTimeline?.windows).toHaveLength(1);
    expect(parsed.phase1.rhythmTimeline?.windows[0]?.bars).toBe(8);
    expect(parsed.phase1.rhythmTimeline?.windows[0]?.lowBandSteps).toHaveLength(128);
    expect(parsed.phase1.rhythmTimeline?.windows[0]?.midBandSteps.every((value) => value === 0)).toBe(true);
    expect(parsed.phase1.rhythmTimeline?.windows[0]?.highBandSteps.every((value) => value === 0)).toBe(true);
    expect(parsed.phase1.rhythmTimeline?.windows[0]?.overallSteps.every((value) => value === 0)).toBe(true);
  });

  it('parses chordDetail.chordTimeline with labelLong and the new Viterbi meta-fields', () => {
    const parsed = parseBackendAnalyzeResponse(validPayload);
    const chord = parsed.phase1.chordDetail;
    expect(chord).not.toBeNull();
    expect(chord?.chordTimelineSource).toBe('librosa_viterbi');
    expect(chord?.chordTimelineAgreement).toBe(true);
    expect(chord?.chordTimeline).toHaveLength(2);
    expect(chord?.chordTimeline?.[0]).toEqual({
      startSec: 0.0,
      endSec: 4.0,
      label: 'Am',
      labelLong: 'A minor',
      confidence: 0.81,
    });
    expect(chord?.chordSequence).toEqual(['Am', 'F', 'C', 'G']);
    expect(chord?.chordChangeCount).toBe(1);
  });

  it('accepts chordTimeline entries that omit labelLong for back-compat with older payloads', () => {
    const parsed = parseBackendAnalyzeResponse({
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        chordDetail: {
          ...validPayload.phase1.chordDetail,
          chordTimeline: [
            { startSec: 0.0, endSec: 2.0, label: 'Cm', confidence: 0.7 },
          ],
          // labelLong intentionally absent on this segment
        },
      },
    });
    expect(parsed.phase1.chordDetail?.chordTimeline).toHaveLength(1);
    const seg = parsed.phase1.chordDetail?.chordTimeline?.[0];
    expect(seg?.label).toBe('Cm');
    expect(seg?.labelLong).toBeUndefined();
  });

  it('drops malformed chordTimeline entries without rejecting the rest of chordDetail', () => {
    const parsed = parseBackendAnalyzeResponse({
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        chordDetail: {
          chordSequence: ['Am'],
          chordStrength: 0.5,
          chordTimeline: [
            // good
            { startSec: 0, endSec: 2, label: 'Am', labelLong: 'A minor', confidence: 0.8 },
            // bad: missing label
            { startSec: 2, endSec: 4, confidence: 0.6 },
            // bad: NaN confidence
            { startSec: 4, endSec: 6, label: 'C', confidence: Number.NaN },
            // bad: endSec < startSec
            { startSec: 8, endSec: 6, label: 'F', confidence: 0.7 },
            // good — emits after sort
            { startSec: 6, endSec: 8, label: 'G', labelLong: 'G major', confidence: 1.5 }, // confidence clamped
            // bad: not a record
            'oops',
          ],
          chordChangeCount: 1,
          chordTimelineSource: 'librosa_viterbi',
          chordTimelineAgreement: null,
        },
      },
    });
    const tl = parsed.phase1.chordDetail?.chordTimeline;
    expect(tl).toHaveLength(2);
    expect(tl?.[0]?.label).toBe('Am');
    expect(tl?.[1]?.label).toBe('G');
    expect(tl?.[1]?.confidence).toBe(1); // clamped from 1.5
    // chordDetail as a whole is still parsed (not nulled).
    expect(parsed.phase1.chordDetail?.chordStrength).toBe(0.5);
    expect(parsed.phase1.chordDetail?.chordTimelineAgreement).toBeNull();
  });

  it('treats chordTimelineAgreement as null when neither true nor false is passed', () => {
    const parsed = parseBackendAnalyzeResponse({
      ...validPayload,
      phase1: {
        ...validPayload.phase1,
        chordDetail: {
          ...validPayload.phase1.chordDetail,
          chordTimelineAgreement: 'yes', // junk value should normalize to null
        },
      },
    });
    expect(parsed.phase1.chordDetail?.chordTimelineAgreement).toBeNull();
  });

  it('throws when phase1 is missing', () => {
    expect(() =>
      parseBackendAnalyzeResponse({
        requestId: 'req_123',
      }),
    ).toThrow(/phase1/i);
  });

  it('maps legacy loudnessVariation payloads onto loudnessDb', () => {
    const parsed = parseBackendAnalyzeResponse({
      requestId: 'req_legacy_dynamic',
      phase1: {
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
        dynamicCharacter: {
          dynamicComplexity: 3.05,
          loudnessVariation: -14.93,
          spectralFlatness: 0.0631,
          logAttackTime: -3.9299,
          attackTimeStdDev: 0.0476,
        },
      },
    });

    expect(parsed.phase1.dynamicCharacter?.loudnessDb).toBe(-14.93);
    expect(parsed.phase1.dynamicCharacter?.loudnessVariation).toBe(-14.93);
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

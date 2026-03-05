import {
  parseBackendAnalyzeResponse,
  BackendClientError,
  mapBackendError,
} from '../../src/services/backendPhase1Client';

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
    truePeak: -0.5,
    stereoWidth: 0.75,
    stereoCorrelation: 0.82,
    spectralBalance: {
      subBass: -1.2,
      lowBass: 0.8,
      mids: -0.4,
      upperMids: 0.2,
      highs: 1.1,
      brilliance: 0.5,
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
  },
  diagnostics: {
    backendDurationMs: 1420,
    engineVersion: '0.4.0',
  },
};

describe('parseBackendAnalyzeResponse', () => {
  it('accepts a valid backend payload', () => {
    const parsed = parseBackendAnalyzeResponse(validPayload);

    expect(parsed.requestId).toBe('req_123');
    expect(parsed.phase1.bpm).toBe(128);
    expect(parsed.diagnostics?.engineVersion).toBe('0.4.0');
    expect(parsed.phase1.melodyDetail?.noteCount).toBe(3);
    expect(parsed.phase1.melodyDetail?.notes[0].midi).toBe(60);
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
});

describe('mapBackendError', () => {
  it('maps network failures to a user-friendly message', () => {
    const mapped = mapBackendError(new TypeError('Failed to fetch'));

    expect(mapped).toBeInstanceOf(BackendClientError);
    expect(mapped.code).toBe('NETWORK_UNREACHABLE');
    expect(mapped.message).toMatch(/Cannot reach DSP backend/i);
  });

  it('preserves explicit backend client errors', () => {
    const original = new BackendClientError('BACKEND_HTTP_ERROR', 'Backend failed', {
      status: 502,
    });

    const mapped = mapBackendError(original);

    expect(mapped).toBe(original);
    expect(mapped.details?.status).toBe(502);
  });
});

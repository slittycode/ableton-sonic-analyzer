import { afterEach, describe, expect, it, vi } from 'vitest';

import type {
  AnalysisRunSnapshot,
  DiagnosticLogEntry,
  Phase1Result,
  Phase2Result,
} from '../../src/types';

const {
  createAnalysisRunMock,
  getAnalysisRunMock,
  isGeminiPhase2ConfigEnabledMock,
  validatePhase2ConsistencyMock,
} = vi.hoisted(() => ({
  createAnalysisRunMock: vi.fn(),
  getAnalysisRunMock: vi.fn(),
  isGeminiPhase2ConfigEnabledMock: vi.fn(() => true),
  validatePhase2ConsistencyMock: vi.fn(),
}));

vi.mock('../../src/config', () => ({
  appConfig: {
    apiBaseUrl: 'http://127.0.0.1:8100',
  },
  canRunGeminiPhase2: () => isGeminiPhase2ConfigEnabledMock(),
  isGeminiPhase2ConfigEnabled: isGeminiPhase2ConfigEnabledMock,
}));

vi.mock('../../src/services/backendPhase1Client', async () => {
  const actual = await vi.importActual<typeof import('../../src/services/backendPhase1Client')>(
    '../../src/services/backendPhase1Client',
  );

  return {
    ...actual,
    mapBackendError: (error: unknown) => (error instanceof Error ? error : new Error(String(error))),
  };
});

vi.mock('../../src/services/analysisRunsClient', async () => {
  const actual = await vi.importActual<typeof import('../../src/services/analysisRunsClient')>(
    '../../src/services/analysisRunsClient',
  );

  return {
    ...actual,
    createAnalysisRun: createAnalysisRunMock,
    getAnalysisRun: getAnalysisRunMock,
  };
});

vi.mock('../../src/services/phase2Validator', () => ({
  validatePhase2Consistency: validatePhase2ConsistencyMock,
}));

import { BackendClientError } from '../../src/services/backendPhase1Client';
import { analyzeAudio } from '../../src/services/analyzer';

const phase1Result: Phase1Result = {
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
    lowMids: 0.0,
    mids: -0.4,
    upperMids: 0.2,
    highs: 1.1,
    brilliance: 0.5,
  },
};

const phase2Result: Phase2Result = {
  trackCharacter: 'Tight modern electronic mix.',
  detectedCharacteristics: [
    { name: 'Stereo Discipline', confidence: 'HIGH', explanation: 'Controlled width and correlation.' },
  ],
  arrangementOverview: {
    summary: 'Arrangement transitions and energy shifts.',
    segments: [
      {
        index: 1,
        startTime: 0,
        endTime: 30,
        lufs: -8.4,
        description: 'Intro: sparse opening.',
      },
    ],
  },
  sonicElements: {
    kick: 'Punchy kick body.',
    bass: 'Focused bass lane.',
    melodicArp: 'Simple melodic motif.',
    grooveAndTiming: 'Quantized groove.',
    effectsAndTexture: 'Light atmospherics.',
  },
  mixAndMasterChain: [
    {
      order: 1,
      device: 'Drum Buss',
      parameter: 'Drive',
      value: '5 dB',
      reason: 'Adds punch to drums.',
    },
  ],
  secretSauce: {
    title: 'Punch Layering',
    explanation: 'Layered transient enhancement.',
    implementationSteps: ['Step 1', 'Step 2'],
  },
  confidenceNotes: [{ field: 'Key Signature', value: 'HIGH', reason: 'Stable detection.' }],
  abletonRecommendations: [
    {
      device: 'Operator',
      category: 'SYNTHESIS',
      parameter: 'Coarse',
      value: '1.00',
      reason: 'Matches tonal center.',
    },
  ],
};

afterEach(() => {
  createAnalysisRunMock.mockReset();
  getAnalysisRunMock.mockReset();
  isGeminiPhase2ConfigEnabledMock.mockReset();
  validatePhase2ConsistencyMock.mockReset();
  isGeminiPhase2ConfigEnabledMock.mockReturnValue(true);
});

function makeRunSnapshot(overrides?: Partial<AnalysisRunSnapshot>): AnalysisRunSnapshot {
  return {
    runId: 'run_123',
    requestedStages: {
      symbolicMode: 'stem_notes',
      symbolicBackend: 'auto',
      interpretationMode: 'async',
      interpretationProfile: 'producer_summary',
      interpretationModel: 'gemini-2.5-pro',
    },
    artifacts: {
      sourceAudio: {
        artifactId: 'artifact_123',
        filename: 'track.mp3',
        mimeType: 'audio/mpeg',
        sizeBytes: 4096,
        contentSha256: 'abc123',
        path: '/tmp/track.mp3',
      },
    },
    stages: {
      measurement: {
        status: 'completed',
        authoritative: true,
        result: phase1Result,
        provenance: null,
        diagnostics: {
          backendDurationMs: 1420,
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
        error: null,
      },
      symbolicExtraction: {
        status: 'completed',
        authoritative: false,
        preferredAttemptId: 'sym_123',
        attemptsSummary: [
          {
            attemptId: 'sym_123',
            backendId: 'auto',
            mode: 'stem_notes',
            status: 'completed',
          },
        ],
        result: phase1Result.transcriptionDetail ?? null,
        provenance: null,
        diagnostics: null,
        error: null,
      },
      interpretation: {
        status: 'completed',
        authoritative: false,
        preferredAttemptId: 'int_123',
        attemptsSummary: [
          {
            attemptId: 'int_123',
            profileId: 'producer_summary',
            modelName: 'gemini-2.5-pro',
            status: 'completed',
          },
        ],
        result: phase2Result,
        provenance: null,
        diagnostics: null,
        error: null,
      },
    },
    ...overrides,
  };
}

describe('analyzeAudio', () => {
  it('creates and polls a canonical analysis run instead of calling legacy wrapper endpoints', async () => {
    createAnalysisRunMock.mockResolvedValue(makeRunSnapshot({
      stages: {
        measurement: {
          status: 'queued',
          authoritative: true,
          result: null,
          provenance: null,
          diagnostics: null,
          error: null,
        },
        symbolicExtraction: {
          status: 'blocked',
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
    }));
    getAnalysisRunMock
      .mockResolvedValueOnce(makeRunSnapshot({
        stages: {
          measurement: {
            status: 'running',
            authoritative: true,
            result: null,
            provenance: null,
            diagnostics: null,
            error: null,
          },
          symbolicExtraction: {
            status: 'blocked',
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
      }))
      .mockResolvedValueOnce(makeRunSnapshot());

    const file = new File(['audio-data'], 'track.mp3', { type: 'audio/mpeg' });
    let phase1Log: DiagnosticLogEntry | undefined;
    const onRunUpdate = vi.fn();

    await analyzeAudio(
      file,
      'gemini-2.5-pro',
      null,
      (_result, log) => {
        phase1Log = log;
      },
      () => {},
      (error) => {
        throw error;
      },
      {
        symbolicRequested: true,
        interpretationRequested: true,
        interpretationConfigEnabled: true,
        onRunUpdate,
        pollIntervalMs: 0,
      },
    );

    expect(createAnalysisRunMock).toHaveBeenCalledWith(
      file,
      expect.objectContaining({
        symbolicMode: 'stem_notes',
        symbolicBackend: 'auto',
        interpretationMode: 'async',
        interpretationProfile: 'producer_summary',
        interpretationModel: 'gemini-2.5-pro',
      }),
    );
    expect(getAnalysisRunMock).toHaveBeenCalledWith('run_123', expect.any(Object));
    expect(onRunUpdate).toHaveBeenCalled();
    expect(phase1Log?.phase).toContain('Measurement');
  });

  it('passes projected phase 1 and phase 2 results to completion callbacks', async () => {
    createAnalysisRunMock.mockResolvedValue(makeRunSnapshot());
    getAnalysisRunMock.mockResolvedValue(makeRunSnapshot());
    const file = new File(['audio-data'], 'track.mp3', { type: 'audio/mpeg' });
    const onPhase1Complete = vi.fn();
    const onPhase2Complete = vi.fn();

    await analyzeAudio(
      file,
      'gemini-2.5-pro',
      null,
      onPhase1Complete,
      onPhase2Complete,
      (error) => {
        throw error;
      },
      {
        symbolicRequested: true,
        interpretationRequested: true,
        interpretationConfigEnabled: true,
        pollIntervalMs: 0,
      },
    );

    expect(onPhase1Complete).toHaveBeenCalledWith(
      expect.objectContaining({
        bpm: 128,
      }),
      expect.objectContaining({
        phase: expect.stringContaining('Measurement'),
      }),
    );
    expect(onPhase2Complete).toHaveBeenCalledWith(
      phase2Result,
      expect.objectContaining({
        phase: expect.stringContaining('Interpretation'),
      }),
    );
  });

  it('skips interpretation cleanly when it is disabled in the UI', async () => {
    createAnalysisRunMock.mockResolvedValue(makeRunSnapshot({
      requestedStages: {
        symbolicMode: 'stem_notes',
        symbolicBackend: 'auto',
        interpretationMode: 'off',
        interpretationProfile: 'producer_summary',
        interpretationModel: null,
      },
      stages: {
        measurement: {
          status: 'completed',
          authoritative: true,
          result: phase1Result,
          provenance: null,
          diagnostics: null,
          error: null,
        },
        symbolicExtraction: {
          status: 'completed',
          authoritative: false,
          preferredAttemptId: 'sym_123',
          attemptsSummary: [],
          result: phase1Result.transcriptionDetail ?? null,
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
    }));
    getAnalysisRunMock.mockResolvedValue(makeRunSnapshot({
      requestedStages: {
        symbolicMode: 'stem_notes',
        symbolicBackend: 'auto',
        interpretationMode: 'off',
        interpretationProfile: 'producer_summary',
        interpretationModel: null,
      },
      stages: {
        measurement: {
          status: 'completed',
          authoritative: true,
          result: phase1Result,
          provenance: null,
          diagnostics: null,
          error: null,
        },
        symbolicExtraction: {
          status: 'completed',
          authoritative: false,
          preferredAttemptId: 'sym_123',
          attemptsSummary: [],
          result: phase1Result.transcriptionDetail ?? null,
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
    }));
    const file = new File(['audio-data'], 'track.mp3', { type: 'audio/mpeg' });
    const onPhase2Complete = vi.fn();

    await analyzeAudio(
      file,
      'gemini-2.5-pro',
      null,
      () => {},
      onPhase2Complete,
      (error) => {
        throw error;
      },
      {
        symbolicRequested: true,
        interpretationRequested: false,
        interpretationConfigEnabled: true,
        pollIntervalMs: 0,
      },
    );

    expect(onPhase2Complete).toHaveBeenCalledWith(
      null,
      expect.objectContaining({
        phase: expect.stringContaining('Skipped'),
        status: 'skipped',
      }),
    );
  });

  it('treats stop-monitoring as user-cancelled and suppresses later results', async () => {
    createAnalysisRunMock.mockResolvedValue(makeRunSnapshot({
      stages: {
        measurement: {
          status: 'running',
          authoritative: true,
          result: null,
          provenance: null,
          diagnostics: null,
          error: null,
        },
        symbolicExtraction: {
          status: 'blocked',
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
    }));
    let resolvePoll: ((value: AnalysisRunSnapshot) => void) | null = null;
    getAnalysisRunMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePoll = resolve;
        }),
    );
    const file = new File(['audio-data'], 'track.mp3', { type: 'audio/mpeg' });
    const onRunUpdate = vi.fn();
    const onPhase2Complete = vi.fn();
    const onError = vi.fn();
    const controller = new AbortController();

    const promise = analyzeAudio(
      file,
      'gemini-2.5-pro',
      null,
      () => {},
      onPhase2Complete,
      onError,
      {
        symbolicRequested: true,
        interpretationRequested: true,
        interpretationConfigEnabled: true,
        signal: controller.signal,
        onRunUpdate,
        pollIntervalMs: 0,
      },
    );

    controller.abort();
    resolvePoll?.(makeRunSnapshot());

    await promise;

    expect(onRunUpdate).not.toHaveBeenCalled();
    expect(onPhase2Complete).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0]?.[0]).toBeInstanceOf(BackendClientError);
    expect((onError.mock.calls[0]?.[0] as BackendClientError).code).toBe('USER_CANCELLED');
  });

  it('attaches a validation report to the interpretation log when output is available', async () => {
    createAnalysisRunMock.mockResolvedValue(makeRunSnapshot());
    getAnalysisRunMock.mockResolvedValue(makeRunSnapshot());
    const validationReport = {
      violations: [
        {
          type: 'GENRE_IGNORES_DSP',
          field: 'confidenceNotes',
          severity: 'WARNING',
          message: 'Missing rhythm cluster reference.',
        },
      ],
      passed: true,
      summary: {
        errorCount: 0,
        warningCount: 1,
        checkedFields: 5,
      },
    };
    validatePhase2ConsistencyMock.mockReturnValue(validationReport);

    const file = new File(['audio-data'], 'track.mp3', { type: 'audio/mpeg' });
    const onPhase2Complete = vi.fn();

    await analyzeAudio(
      file,
      'gemini-2.5-pro',
      null,
      () => {},
      onPhase2Complete,
      (error) => {
        throw error;
      },
      {
        symbolicRequested: true,
        interpretationRequested: true,
        interpretationConfigEnabled: true,
        pollIntervalMs: 0,
      },
    );

    expect(validatePhase2ConsistencyMock).toHaveBeenCalledWith(phase1Result, phase2Result);
    expect(onPhase2Complete).toHaveBeenCalledWith(
      phase2Result,
      expect.objectContaining({
        requestId: 'run_123',
        validationReport,
      }),
    );
  });

  it('silently skips validation when the validator throws', async () => {
    createAnalysisRunMock.mockResolvedValue(makeRunSnapshot());
    getAnalysisRunMock.mockResolvedValue(makeRunSnapshot());
    validatePhase2ConsistencyMock.mockImplementation(() => {
      throw new Error('validator blew up');
    });

    const file = new File(['audio-data'], 'track.mp3', { type: 'audio/mpeg' });
    const onPhase2Complete = vi.fn();
    const onError = vi.fn();

    await analyzeAudio(
      file,
      'gemini-2.5-pro',
      null,
      () => {},
      onPhase2Complete,
      onError,
      {
        symbolicRequested: true,
        interpretationRequested: true,
        interpretationConfigEnabled: true,
        pollIntervalMs: 0,
      },
    );

    expect(validatePhase2ConsistencyMock).toHaveBeenCalledWith(phase1Result, phase2Result);
    expect(onError).not.toHaveBeenCalled();
    expect(onPhase2Complete).toHaveBeenCalledTimes(1);
    expect(onPhase2Complete.mock.calls[0]?.[0]).toBe(phase2Result);
    expect(onPhase2Complete.mock.calls[0]?.[1]?.validationReport).toBeUndefined();
    expect(onPhase2Complete.mock.calls[0]?.[1]?.requestId).toBe('run_123');
  });
});

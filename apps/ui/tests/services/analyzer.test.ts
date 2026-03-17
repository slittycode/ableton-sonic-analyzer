import { afterEach, describe, expect, it, vi } from 'vitest';

import type {
  BackendAnalyzeResponse,
  DiagnosticLogEntry,
  Phase1Result,
  Phase2Result,
} from '../../src/types';

const {
  analyzePhase1WithBackendMock,
  analyzePhase2WithBackendMock,
  isGeminiPhase2ConfigEnabledMock,
  validatePhase2ConsistencyMock,
} = vi.hoisted(() => ({
  analyzePhase1WithBackendMock: vi.fn(),
  analyzePhase2WithBackendMock: vi.fn(),
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
    analyzePhase1WithBackend: analyzePhase1WithBackendMock,
    mapBackendError: (error: unknown) => (error instanceof Error ? error : new Error(String(error))),
  };
});

vi.mock('../../src/services/backendPhase2Client', () => ({
  analyzePhase2WithBackend: analyzePhase2WithBackendMock,
}));

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
  analyzePhase1WithBackendMock.mockReset();
  analyzePhase2WithBackendMock.mockReset();
  isGeminiPhase2ConfigEnabledMock.mockReset();
  validatePhase2ConsistencyMock.mockReset();
  isGeminiPhase2ConfigEnabledMock.mockReturnValue(true);
});

describe('analyzeAudio', () => {
  it('attaches backend timings to the phase 1 success log', async () => {
    const backendResult: BackendAnalyzeResponse = {
      requestId: 'req_123',
      phase1: phase1Result,
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
    };
    analyzePhase1WithBackendMock.mockResolvedValue(backendResult);

    const file = new File(['audio-data'], 'track.mp3', { type: 'audio/mpeg' });
    let phase1Log: DiagnosticLogEntry | undefined;

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
      { transcribe: true, separate: false, phase2Requested: false },
    );

    expect(phase1Log?.requestId).toBe('req_123');
    expect(phase1Log?.timings).toEqual(backendResult.diagnostics?.timings);
  });

  it('forwards an explicit timeout budget to the backend phase 1 client', async () => {
    const backendResult: BackendAnalyzeResponse = {
      requestId: 'req_456',
      phase1: phase1Result,
    };
    analyzePhase1WithBackendMock.mockResolvedValue(backendResult);

    const file = new File(['audio-data'], 'track.mp3', { type: 'audio/mpeg' });

    await analyzeAudio(
      file,
      'gemini-2.5-pro',
      null,
      () => {},
      () => {},
      (error) => {
        throw error;
      },
      { transcribe: true, separate: true, timeoutMs: 456000, phase2Requested: false },
    );

    expect(analyzePhase1WithBackendMock).toHaveBeenCalledWith(
      file,
      null,
      expect.objectContaining({
        apiBaseUrl: 'http://127.0.0.1:8100',
        transcribe: true,
        separate: true,
        timeoutMs: 456000,
      }),
    );
  });

  it('skips phase 2 with a user-disabled reason when the UI toggle is off', async () => {
    const backendResult: BackendAnalyzeResponse = {
      requestId: 'req_user_off',
      phase1: phase1Result,
    };
    analyzePhase1WithBackendMock.mockResolvedValue(backendResult);

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
        phase2Requested: false,
        phase2ConfigEnabled: true,
      },
    );

    expect(analyzePhase2WithBackendMock).not.toHaveBeenCalled();
    expect(onPhase2Complete).toHaveBeenCalledWith(
      null,
      expect.objectContaining({
        phase: 'Phase 2: Advisory skipped',
        status: 'skipped',
        message: 'Phase 2 advisory skipped because it was disabled in the UI.',
      }),
    );
  });

  it('treats a phase 2 abort as user-cancelled and suppresses the late advisory result', async () => {
    isGeminiPhase2ConfigEnabledMock.mockReturnValue(true);

    const backendResult: BackendAnalyzeResponse = {
      requestId: 'req_phase2_cancel',
      phase1: phase1Result,
    };
    analyzePhase1WithBackendMock.mockResolvedValue(backendResult);

    let resolvePhase2:
      | ((value: { result: { trackCharacter: string }; log: DiagnosticLogEntry }) => void)
      | null = null;
    analyzePhase2WithBackendMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePhase2 = resolve;
        }),
    );

    const file = new File(['audio-data'], 'track.mp3', { type: 'audio/mpeg' });
    const onPhase1Complete = vi.fn();
    const onPhase2Complete = vi.fn();
    const onError = vi.fn();
    const controller = new AbortController();

    const promise = analyzeAudio(
      file,
      'gemini-2.5-pro',
      null,
      onPhase1Complete,
      onPhase2Complete,
      onError,
      { signal: controller.signal, phase2Requested: true, phase2ConfigEnabled: true },
    );

    await vi.waitFor(() => expect(analyzePhase2WithBackendMock).toHaveBeenCalledTimes(1));

    controller.abort();
    resolvePhase2?.({
      result: { trackCharacter: 'late advisory result' },
      log: {
        model: 'gemini-2.5-pro',
        phase: 'Phase 2: Advisory',
        promptLength: 10,
        responseLength: 20,
        durationMs: 100,
        audioMetadata: {
          name: file.name,
          size: file.size,
          type: file.type,
        },
        timestamp: new Date().toISOString(),
        source: 'backend',
        status: 'success',
        message: 'Phase 2 advisory complete.',
      },
    } as never);

    await promise;

    expect(onPhase1Complete).toHaveBeenCalledTimes(1);
    expect(onPhase2Complete).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0]?.[0]).toBeInstanceOf(BackendClientError);
    expect((onError.mock.calls[0]?.[0] as BackendClientError).code).toBe('USER_CANCELLED');
  });

  it('attaches a validation report to the phase 2 log when advisory output is available', async () => {
    isGeminiPhase2ConfigEnabledMock.mockReturnValue(true);

    const backendResult: BackendAnalyzeResponse = {
      requestId: 'req_phase2_validation',
      phase1: phase1Result,
    };
    analyzePhase1WithBackendMock.mockResolvedValue(backendResult);

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
    analyzePhase2WithBackendMock.mockResolvedValue({
      result: phase2Result,
      log: {
        model: 'gemini-2.5-pro',
        phase: 'Phase 2: Advisory reconstruction',
        promptLength: 10,
        responseLength: 20,
        durationMs: 100,
        audioMetadata: {
          name: 'track.mp3',
          size: 10,
          type: 'audio/mpeg',
        },
        timestamp: new Date().toISOString(),
        source: 'backend',
        status: 'success',
        message: 'Phase 2 advisory complete.',
      },
    });

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
      { phase2Requested: true, phase2ConfigEnabled: true },
    );

    expect(validatePhase2ConsistencyMock).toHaveBeenCalledWith(backendResult.phase1, phase2Result);
    expect(onPhase2Complete).toHaveBeenCalledWith(
      phase2Result,
      expect.objectContaining({
        requestId: 'req_phase2_validation',
        validationReport,
      }),
    );
  });

  it('silently skips validation when the validator throws', async () => {
    isGeminiPhase2ConfigEnabledMock.mockReturnValue(true);

    const backendResult: BackendAnalyzeResponse = {
      requestId: 'req_phase2_validation_throw',
      phase1: phase1Result,
    };
    analyzePhase1WithBackendMock.mockResolvedValue(backendResult);
    validatePhase2ConsistencyMock.mockImplementation(() => {
      throw new Error('validator blew up');
    });
    analyzePhase2WithBackendMock.mockResolvedValue({
      result: phase2Result,
      log: {
        model: 'gemini-2.5-pro',
        phase: 'Phase 2: Advisory reconstruction',
        promptLength: 10,
        responseLength: 20,
        durationMs: 100,
        audioMetadata: {
          name: 'track.mp3',
          size: 10,
          type: 'audio/mpeg',
        },
        timestamp: new Date().toISOString(),
        source: 'backend',
        status: 'success',
        message: 'Phase 2 advisory complete.',
      },
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
      { phase2Requested: true, phase2ConfigEnabled: true },
    );

    expect(validatePhase2ConsistencyMock).toHaveBeenCalledWith(backendResult.phase1, phase2Result);
    expect(onError).not.toHaveBeenCalled();
    expect(onPhase2Complete).toHaveBeenCalledTimes(1);
    expect(onPhase2Complete.mock.calls[0]?.[0]).toBe(phase2Result);
    expect(onPhase2Complete.mock.calls[0]?.[1]?.validationReport).toBeUndefined();
    expect(onPhase2Complete.mock.calls[0]?.[1]?.requestId).toBe('req_phase2_validation_throw');
  });
});

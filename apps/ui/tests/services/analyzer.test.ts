import { afterEach, describe, expect, it, vi } from 'vitest';

import type { BackendAnalyzeResponse, DiagnosticLogEntry, Phase1Result } from '../../src/types';

const {
  analyzePhase1WithBackendMock,
  analyzePhase2WithGeminiMock,
  canRunGeminiPhase2Mock,
  isGeminiPhase2ConfigEnabledMock,
} = vi.hoisted(() => ({
  analyzePhase1WithBackendMock: vi.fn(),
  analyzePhase2WithGeminiMock: vi.fn(),
  canRunGeminiPhase2Mock: vi.fn(() => false),
  isGeminiPhase2ConfigEnabledMock: vi.fn(() => true),
}));

vi.mock('../../src/config', () => ({
  appConfig: {
    apiBaseUrl: 'http://127.0.0.1:8100',
  },
  canRunGeminiPhase2: canRunGeminiPhase2Mock,
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

vi.mock('../../src/services/geminiPhase2Client', () => ({
  analyzePhase2WithGemini: analyzePhase2WithGeminiMock,
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

afterEach(() => {
  analyzePhase1WithBackendMock.mockReset();
  analyzePhase2WithGeminiMock.mockReset();
  canRunGeminiPhase2Mock.mockReset();
  isGeminiPhase2ConfigEnabledMock.mockReset();
  canRunGeminiPhase2Mock.mockReturnValue(false);
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
      { transcribe: true, separate: false },
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
      { transcribe: true, separate: true, timeoutMs: 456000 },
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

    expect(analyzePhase2WithGeminiMock).not.toHaveBeenCalled();
    expect(onPhase2Complete).toHaveBeenCalledWith(
      null,
      expect.objectContaining({
        phase: 'Phase 2: Advisory skipped',
        status: 'skipped',
        message: 'Phase 2 advisory skipped because it was disabled in the UI.',
      }),
    );
  });

  it('keeps missing API key distinct from configuration kill-switches', async () => {
    const backendResult: BackendAnalyzeResponse = {
      requestId: 'req_missing_key',
      phase1: phase1Result,
    };
    analyzePhase1WithBackendMock.mockResolvedValue(backendResult);
    canRunGeminiPhase2Mock.mockReturnValue(false);
    isGeminiPhase2ConfigEnabledMock.mockReturnValue(true);

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
        phase2Requested: true,
        phase2ConfigEnabled: true,
      },
    );

    expect(analyzePhase2WithGeminiMock).not.toHaveBeenCalled();
    expect(onPhase2Complete).toHaveBeenCalledWith(
      null,
      expect.objectContaining({
        phase: 'Phase 2: Advisory skipped',
        status: 'skipped',
        message: 'Phase 2 advisory skipped because Gemini is enabled but no API key is configured.',
      }),
    );
  });

  it('treats a phase 2 abort as user-cancelled and suppresses the late advisory result', async () => {
    canRunGeminiPhase2Mock.mockReturnValue(true);

    const backendResult: BackendAnalyzeResponse = {
      requestId: 'req_phase2_cancel',
      phase1: phase1Result,
    };
    analyzePhase1WithBackendMock.mockResolvedValue(backendResult);

    let resolvePhase2:
      | ((value: { result: { trackCharacter: string }; log: DiagnosticLogEntry }) => void)
      | null = null;
    analyzePhase2WithGeminiMock.mockImplementation(
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
      { signal: controller.signal },
    );

    await vi.waitFor(() => expect(analyzePhase2WithGeminiMock).toHaveBeenCalledTimes(1));

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
        source: 'gemini',
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
});

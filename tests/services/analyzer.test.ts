import { afterEach, describe, expect, it, vi } from 'vitest';

import type { BackendAnalyzeResponse, DiagnosticLogEntry, Phase1Result } from '../../src/types';

const { analyzePhase1WithBackendMock } = vi.hoisted(() => ({
  analyzePhase1WithBackendMock: vi.fn(),
}));

vi.mock('../../src/config', () => ({
  appConfig: {
    apiBaseUrl: 'http://localhost:8000',
  },
  isGeminiPhase2Available: () => false,
}));

vi.mock('../../src/services/backendPhase1Client', () => ({
  analyzePhase1WithBackend: analyzePhase1WithBackendMock,
  mapBackendError: (error: unknown) =>
    error instanceof Error ? error : new Error(String(error)),
}));

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
        apiBaseUrl: 'http://localhost:8000',
        transcribe: true,
        separate: true,
        timeoutMs: 456000,
      }),
    );
  });
});

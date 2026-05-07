import { describe, expect, it } from 'vitest';

import type { AnalysisRunSnapshot, DiagnosticLogEntry } from '../../src/types';
import { buildDisplayDiagnosticLogs } from '../../src/services/diagnosticLogs';

const audioMetadata: DiagnosticLogEntry['audioMetadata'] = {
  name: 'track.mp3',
  size: 4096,
  type: 'audio/mpeg',
};

function makeSnapshot(): AnalysisRunSnapshot {
  return {
    runId: 'run_123',
    requestedStages: {
      pitchNoteMode: 'stem_notes',
      pitchNoteBackend: 'auto',
      interpretationMode: 'async',
      interpretationProfile: 'producer_summary',
      interpretationModel: 'gemini-3.1-pro-preview',
    },
    artifacts: {
      sourceAudio: {
        artifactId: 'artifact_123',
        filename: 'track.mp3',
        mimeType: 'audio/mpeg',
        sizeBytes: 4096,
        contentSha256: 'abc123',
      },
    },
    stages: {
      measurement: {
        status: 'completed',
        authoritative: true,
        result: null,
        provenance: null,
        diagnostics: {
          backendDurationMs: 73542.51,
          timings: {
            totalMs: 73560.11,
            analysisMs: 73542.51,
            serverOverheadMs: 17.6,
            flagsUsed: ['--measure'],
            fileSizeBytes: 18789567,
            fileDurationSeconds: 469.2,
            msPerSecondOfAudio: 156.74,
          },
        },
        error: null,
      },
      pitchNoteTranslation: {
        status: 'completed',
        authoritative: false,
        preferredAttemptId: 'pitch_1',
        attemptsSummary: [{ attemptId: 'pitch_1', backendId: 'torchcrepe-viterbi', mode: 'stem_notes', status: 'completed' }],
        result: null,
        provenance: { backendId: 'torchcrepe-viterbi' },
        diagnostics: {
          backendDurationMs: 254776.24,
          timings: {
            totalMs: 254790.0,
            analysisMs: 254776.24,
            serverOverheadMs: 13.76,
            flagsUsed: ['--transcribe'],
            fileSizeBytes: 18789567,
            fileDurationSeconds: 469.2,
            msPerSecondOfAudio: 543.02,
          },
        },
        error: null,
      },
      interpretation: {
        status: 'completed',
        authoritative: false,
        preferredAttemptId: 'interp_1',
        attemptsSummary: [{ attemptId: 'interp_1', profileId: 'producer_summary', modelName: 'gemini-3.1-pro-preview', status: 'completed' }],
        result: null,
        provenance: null,
        diagnostics: {
          requestId: 'req_123',
          backendDurationMs: 98645.66,
          timings: {
            totalMs: 98663.26,
            analysisMs: 98645.66,
            serverOverheadMs: 17.6,
            flagsUsed: ['inline'],
            fileSizeBytes: 18789567,
            fileDurationSeconds: null,
            msPerSecondOfAudio: null,
          },
        },
        error: null,
      },
    },
  };
}

describe('buildDisplayDiagnosticLogs', () => {
  it('returns live logs unchanged when transient logs already exist', () => {
    const existingLogs: DiagnosticLogEntry[] = [
      {
        model: 'local-dsp-engine',
        phase: 'Measurement',
        stageKey: 'measurement',
        promptLength: 0,
        responseLength: 0,
        durationMs: 1000,
        audioMetadata,
        timestamp: '2026-03-26T08:00:00.000Z',
        source: 'backend',
        status: 'success',
        message: 'Measurement complete.',
      },
    ];

    expect(
      buildDisplayDiagnosticLogs({
        logs: existingLogs,
        analysisRun: makeSnapshot(),
        audioMetadata,
        interpretationModel: 'gemini-3.1-pro-preview',
      }),
    ).toEqual(existingLogs);
  });

  it('derives deterministic fallback logs from analysis-run stage diagnostics when live logs are empty', () => {
    const logs = buildDisplayDiagnosticLogs({
      logs: [],
      analysisRun: makeSnapshot(),
      audioMetadata,
      interpretationModel: 'gemini-3.1-pro-preview',
    });

    expect(logs.map((entry) => entry.stageKey)).toEqual([
      'measurement',
      'pitchNoteTranslation',
      'interpretation',
    ]);
    expect(logs[0].durationMs).toBe(73543);
    expect(logs[0].timings?.analysisMs).toBe(73542.51);
    expect(logs[1].model).toBe('torchcrepe-viterbi');
    expect(logs[1].message).toBe('Pitch/Note Translation complete.');
    expect(logs[2].model).toBe('gemini-3.1-pro-preview');
    expect(logs[2].requestId).toBe('req_123');
  });
});

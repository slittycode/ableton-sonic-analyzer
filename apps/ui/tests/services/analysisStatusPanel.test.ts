import { describe, expect, it } from 'vitest';

import { resolveEstimateStageSummary, resolveStageSummary } from '../../src/components/AnalysisStatusPanel';
import { AnalysisRunSnapshot } from '../../src/types';

function createRunSnapshot(overrides?: Partial<AnalysisRunSnapshot>): AnalysisRunSnapshot {
  return {
    runId: 'run_1',
    requestedStages: {
      symbolicMode: 'stem_notes',
      symbolicBackend: 'auto',
      interpretationMode: 'async',
      interpretationProfile: 'producer_summary',
      interpretationModel: 'gemini-2.5-flash',
    },
    artifacts: {
      sourceAudio: {
        artifactId: 'artifact_1',
        filename: 'track.wav',
        mimeType: 'audio/wav',
        sizeBytes: 123,
        contentSha256: 'abc',
        path: '/tmp/track.wav',
      },
    },
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
    ...overrides,
  };
}

describe('resolveStageSummary', () => {
  it('uses backend progress message for running stages and enables typewriter seed', () => {
    const run = createRunSnapshot({
      stages: {
        ...createRunSnapshot().stages,
        measurement: {
          ...createRunSnapshot().stages.measurement,
          status: 'running',
          diagnostics: {
            progress: {
              stepKey: 'computing_measurements',
              message: 'Computing authoritative local DSP measurements.',
              updatedAt: '2026-03-19T00:00:00Z',
              seq: 2,
            },
          },
        },
      },
    });

    const summary = resolveStageSummary(run, 'measurement');
    expect(summary.message).toBe('Computing authoritative local DSP measurements.');
    expect(summary.typewriterSeed).toBe('Computing authoritative local DSP measurements.');
  });

  it('falls back to generic running copy when backend progress is absent', () => {
    const run = createRunSnapshot();
    const summary = resolveStageSummary(run, 'measurement');
    expect(summary.message).toBe('Currently processing.');
    expect(summary.typewriterSeed).toBeNull();
  });

  it('does not typewriter-animate completed stage copy', () => {
    const run = createRunSnapshot({
      stages: {
        ...createRunSnapshot().stages,
        measurement: {
          ...createRunSnapshot().stages.measurement,
          status: 'completed',
        },
      },
    });

    const summary = resolveStageSummary(run, 'measurement');
    expect(summary.message).toBe('Authoritative local measurement complete.');
    expect(summary.typewriterSeed).toBeNull();
  });

  it('changes typewriter seed only when progress message text changes', () => {
    const base = createRunSnapshot({
      stages: {
        ...createRunSnapshot().stages,
        measurement: {
          ...createRunSnapshot().stages.measurement,
          status: 'running',
          diagnostics: {
            progress: {
              stepKey: 'step_a',
              message: 'Preparing measurement runtime.',
              updatedAt: '2026-03-19T00:00:00Z',
              seq: 1,
            },
          },
        },
      },
    });
    const sameMessageDifferentSeq = createRunSnapshot({
      ...base,
      stages: {
        ...base.stages,
        measurement: {
          ...base.stages.measurement,
          diagnostics: {
            progress: {
              stepKey: 'step_a',
              message: 'Preparing measurement runtime.',
              updatedAt: '2026-03-19T00:00:01Z',
              seq: 2,
            },
          },
        },
      },
    });
    const changedMessage = createRunSnapshot({
      ...base,
      stages: {
        ...base.stages,
        measurement: {
          ...base.stages.measurement,
          diagnostics: {
            progress: {
              stepKey: 'step_b',
              message: 'Computing authoritative local DSP measurements.',
              updatedAt: '2026-03-19T00:00:02Z',
              seq: 3,
            },
          },
        },
      },
    });

    const firstSeed = resolveStageSummary(base, 'measurement').typewriterSeed;
    const secondSeed = resolveStageSummary(sameMessageDifferentSeq, 'measurement').typewriterSeed;
    const thirdSeed = resolveStageSummary(changedMessage, 'measurement').typewriterSeed;

    expect(firstSeed).toBe(secondSeed);
    expect(thirdSeed).not.toBe(firstSeed);
  });
});

describe('resolveEstimateStageSummary', () => {
  it('uses backend pipeline progress message for running demucs row with typewriter seed', () => {
    const run = createRunSnapshot({
      stages: {
        ...createRunSnapshot().stages,
        measurement: {
          ...createRunSnapshot().stages.measurement,
          diagnostics: {
            pipelineProgress: {
              separation: {
                status: 'running',
                stepKey: 'separation_running',
                message: 'Demucs is separating stems from the source audio.',
                updatedAt: '2026-03-19T00:00:00Z',
                seq: 2,
              },
            },
          },
        },
      },
    });

    const summary = resolveEstimateStageSummary(run, 'demucs_separation');
    expect(summary).not.toBeNull();
    expect(summary?.message).toBe('Demucs is separating stems from the source audio.');
    expect(summary?.typewriterSeed).toBe('Demucs is separating stems from the source audio.');
  });

  it('renders pending/completed pipeline row text without typewriter seed', () => {
    const run = createRunSnapshot({
      stages: {
        ...createRunSnapshot().stages,
        measurement: {
          ...createRunSnapshot().stages.measurement,
          diagnostics: {
            pipelineProgress: {
              transcription_stems: {
                status: 'pending',
                stepKey: 'transcription_pending',
                message: 'Legacy Basic Pitch transcription is queued for bass and other stems.',
                updatedAt: '2026-03-19T00:00:00Z',
                seq: 1,
              },
            },
          },
        },
      },
    });

    const summary = resolveEstimateStageSummary(run, 'transcription_stems');
    expect(summary).not.toBeNull();
    expect(summary?.message).toBe('Legacy Basic Pitch transcription is queued for bass and other stems.');
    expect(summary?.typewriterSeed).toBeNull();
  });

  it('returns null when no backend pipeline progress is present', () => {
    const run = createRunSnapshot();
    const summary = resolveEstimateStageSummary(run, 'demucs_separation');
    expect(summary).toBeNull();
  });

  it('returns null for estimate rows outside demucs/transcription scope', () => {
    const run = createRunSnapshot({
      stages: {
        ...createRunSnapshot().stages,
        measurement: {
          ...createRunSnapshot().stages.measurement,
          diagnostics: {
            pipelineProgress: {
              separation: {
                status: 'running',
                stepKey: 'separation_running',
                message: 'Demucs is separating stems from the source audio.',
                updatedAt: '2026-03-19T00:00:00Z',
                seq: 2,
              },
            },
          },
        },
      },
    });
    const summary = resolveEstimateStageSummary(run, 'local_dsp');
    expect(summary).toBeNull();
  });
});

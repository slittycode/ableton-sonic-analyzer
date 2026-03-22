import { afterEach, describe, expect, it, vi } from 'vitest';

import type { AnalysisRunSnapshot } from '../../src/types';
import {
  createAnalysisRun,
  createInterpretationAttempt,
  createSymbolicExtractionAttempt,
  getAnalysisRun,
  projectPhase1FromRun,
  projectPhase2FromRun,
  projectStemSummaryFromRun,
} from '../../src/services/analysisRunsClient';

const baseRunSnapshot: AnalysisRunSnapshot = {
  runId: 'run_123',
  requestedStages: {
    symbolicMode: 'stem_notes',
    symbolicBackend: 'auto',
    interpretationMode: 'async',
    interpretationProfile: 'producer_summary',
    interpretationModel: 'gemini-2.5-flash',
  },
  artifacts: {
    sourceAudio: {
      artifactId: 'artifact_123',
      filename: 'track.mp3',
      mimeType: 'audio/mpeg',
      sizeBytes: 1024,
      contentSha256: 'abc123',
      path: '/tmp/track.mp3',
    },
  },
  stages: {
    measurement: {
      status: 'completed',
      authoritative: true,
      result: {
        bpm: 126,
        bpmConfidence: 0.93,
        key: 'F minor',
        keyConfidence: 0.88,
        timeSignature: '4/4',
        durationSeconds: 210.6,
        lufsIntegrated: -7.9,
        truePeak: -0.2,
        stereoWidth: 0.69,
        stereoCorrelation: 0.84,
        spectralBalance: {
          subBass: -0.7,
          lowBass: 1.2,
          lowMids: 0.0,
          mids: -0.3,
          upperMids: 0.4,
          highs: 1,
          brilliance: 0.8,
        },
      },
      provenance: null,
      diagnostics: null,
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
      result: {
        transcriptionMethod: 'torchcrepe',
        noteCount: 2,
        averageConfidence: 0.81,
        stemSeparationUsed: true,
        fullMixFallback: false,
        stemsTranscribed: ['bass', 'other'],
        dominantPitches: [],
        pitchRange: {
          minMidi: 48,
          maxMidi: 67,
          minName: 'C3',
          maxName: 'G4',
        },
        notes: [],
      },
      provenance: {
        backendId: 'auto',
      },
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
          modelName: 'gemini-2.5-flash',
          status: 'completed',
        },
      ],
      result: {
        trackCharacter: 'Tight modern electronic mix.',
        detectedCharacteristics: [],
        arrangementOverview: { summary: 'Four sections.', segments: [] },
        sonicElements: {
          kick: 'Punchy kick body.',
          bass: 'Focused bass lane.',
          melodicArp: 'Simple melodic motif.',
          grooveAndTiming: 'Quantized groove.',
          effectsAndTexture: 'Light atmospherics.',
        },
        mixAndMasterChain: [],
        secretSauce: {
          title: 'Punch Layering',
          explanation: 'Layered transient enhancement.',
          implementationSteps: [],
        },
        confidenceNotes: [],
        abletonRecommendations: [],
      },
      provenance: {
        modelName: 'gemini-2.5-flash',
      },
      diagnostics: null,
      error: null,
    },
  },
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('analysisRunsClient', () => {
  it('creates a canonical run with symbolic and interpretation form fields', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: () => Promise.resolve(baseRunSnapshot),
    } as Response);
    vi.stubGlobal('fetch', fetchSpy);

    const file = new File(['audio-data'], 'track.mp3', { type: 'audio/mpeg' });
    const snapshot = await createAnalysisRun(file, {
      apiBaseUrl: 'http://127.0.0.1:8100',
      symbolicMode: 'stem_notes',
      symbolicBackend: 'auto',
      interpretationMode: 'async',
      interpretationProfile: 'producer_summary',
      interpretationModel: 'gemini-2.5-flash',
    });

    expect(snapshot.runId).toBe('run_123');

    const request = fetchSpy.mock.calls[0];
    expect(request[0]).toBe('http://127.0.0.1:8100/api/analysis-runs');
    const body = request[1].body as FormData;
    expect(body.get('symbolic_mode')).toBe('stem_notes');
    expect(body.get('symbolic_backend')).toBe('auto');
    expect(body.get('interpretation_mode')).toBe('async');
    expect(body.get('interpretation_profile')).toBe('producer_summary');
    expect(body.get('interpretation_model')).toBe('gemini-2.5-flash');
  });

  it('fetches an analysis run snapshot', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: () => Promise.resolve(baseRunSnapshot),
    } as Response));

    const snapshot = await getAnalysisRun('run_123', {
      apiBaseUrl: 'http://127.0.0.1:8100',
    });

    expect(snapshot.stages.measurement.status).toBe('completed');
    expect(snapshot.stages.symbolicExtraction.preferredAttemptId).toBe('sym_123');
  });

  it('projects phase 1 from the canonical run and injects symbolic transcription detail', () => {
    const phase1 = projectPhase1FromRun(baseRunSnapshot);

    expect(phase1?.bpm).toBe(126);
    expect(phase1?.transcriptionDetail?.transcriptionMethod).toBe('torchcrepe');
  });

  it('strips leaked transcriptionDetail from canonical measurement while preserving symbolic output', async () => {
    const payloadWithTranscription = {
      ...baseRunSnapshot,
      stages: {
        ...baseRunSnapshot.stages,
        measurement: {
          ...baseRunSnapshot.stages.measurement,
          result: {
            ...baseRunSnapshot.stages.measurement.result,
            transcriptionDetail: {
              transcriptionMethod: 'torchcrepe-viterbi',
              noteCount: 1,
              averageConfidence: 0.5,
              stemSeparationUsed: false,
              fullMixFallback: true,
              stemsTranscribed: ['full_mix'],
              dominantPitches: [],
              pitchRange: {
                minMidi: 60,
                maxMidi: 60,
                minName: 'C4',
                maxName: 'C4',
              },
              notes: [],
            },
          },
        },
      },
    };

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: () => Promise.resolve(payloadWithTranscription),
    } as Response));

    const snapshot = await getAnalysisRun('run_123', {
      apiBaseUrl: 'http://127.0.0.1:8100',
    });
    const projectedPhase1 = projectPhase1FromRun(snapshot);

    expect(snapshot.stages.measurement.result).not.toBeNull();
    expect('transcriptionDetail' in (snapshot.stages.measurement.result ?? {})).toBe(false);
    expect(snapshot.stages.symbolicExtraction.result?.transcriptionMethod).toBe('torchcrepe');
    expect(projectedPhase1?.transcriptionDetail?.transcriptionMethod).toBe('torchcrepe');
  });

  it('projects phase 2 from the interpretation stage', () => {
    const phase2 = projectPhase2FromRun(baseRunSnapshot);

    expect(phase2?.trackCharacter).toBe('Tight modern electronic mix.');
  });

  it('keeps stem summary additive and out of the producer-summary projection path', async () => {
    const stemSummarySnapshot = {
      ...baseRunSnapshot,
      requestedStages: {
        ...baseRunSnapshot.requestedStages,
        interpretationProfile: 'stem_summary',
      },
      stages: {
        ...baseRunSnapshot.stages,
        interpretation: {
          ...baseRunSnapshot.stages.interpretation,
          attemptsSummary: [
            {
              attemptId: 'int_stem_123',
              profileId: 'stem_summary',
              modelName: 'gemini-2.5-flash',
              status: 'completed',
            },
          ],
          preferredAttemptId: 'int_stem_123',
          result: {
            summary: 'Bass pulses anchor the groove while the upper stem stays approximate.',
            bars: [
              {
                barStart: 1,
                barEnd: 2,
                startTime: 0,
                endTime: 3.75,
                noteHypotheses: ['C3 pedal'],
                scaleDegreeHypotheses: ['1'],
                rhythmicPattern: 'Short off-beat bass pulses.',
                uncertaintyLevel: 'LOW',
                uncertaintyReason: 'Symbolic extraction and measured bar grid agree.',
              },
            ],
            globalPatterns: {
              bassRole: 'Anchors the groove.',
              melodicRole: 'Sparse upper register punctuation.',
              pumpingOrModulation: 'Measured pumping suggests compressor-driven movement.',
            },
            uncertaintyFlags: ['Upper melodic content is approximate.'],
          },
        },
      },
    } satisfies AnalysisRunSnapshot;

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: () => Promise.resolve(stemSummarySnapshot),
    } as Response));

    const snapshot = await getAnalysisRun('run_123', {
      apiBaseUrl: 'http://127.0.0.1:8100',
    });

    expect(projectPhase2FromRun(snapshot)).toBeNull();
    expect(projectStemSummaryFromRun(snapshot)?.bars[0].noteHypotheses).toEqual(['C3 pedal']);
  });

  it('creates symbolic retry attempts against the canonical endpoint', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      statusText: 'Accepted',
      json: () => Promise.resolve(baseRunSnapshot),
    } as Response);
    vi.stubGlobal('fetch', fetchSpy);

    await createSymbolicExtractionAttempt('run_123', {
      apiBaseUrl: 'http://127.0.0.1:8100',
      symbolicMode: 'stem_notes',
      symbolicBackend: 'auto',
    });

    expect(fetchSpy.mock.calls[0]?.[0]).toBe('http://127.0.0.1:8100/api/analysis-runs/run_123/symbolic-extractions');
  });

  it('creates interpretation retry attempts against the canonical endpoint', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      statusText: 'Accepted',
      json: () => Promise.resolve(baseRunSnapshot),
    } as Response);
    vi.stubGlobal('fetch', fetchSpy);

    await createInterpretationAttempt('run_123', {
      apiBaseUrl: 'http://127.0.0.1:8100',
      interpretationProfile: 'producer_summary',
      interpretationModel: 'gemini-2.5-flash',
    });

    expect(fetchSpy.mock.calls[0]?.[0]).toBe('http://127.0.0.1:8100/api/analysis-runs/run_123/interpretations');
  });
});

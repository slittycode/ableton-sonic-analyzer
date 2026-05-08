import { afterEach, describe, expect, it, vi } from 'vitest';

import type { AnalysisRunSnapshot } from '../../src/types';
import * as analysisRunsClient from '../../src/services/analysisRunsClient';
import {
  createAnalysisRun,
  estimateAnalysisRun,
  createInterpretationAttempt,
  createPitchNoteTranslationAttempt,
  getAnalysisRun,
  interruptAnalysisRun,
  projectPhase1FromRun,
  projectPhase2FromRun,
  projectStemSummaryFromRun,
} from '../../src/services/analysisRunsClient';

const baseRunSnapshot: AnalysisRunSnapshot = {
  runId: 'run_123',
  requestedStages: {
    pitchNoteMode: 'stem_notes',
    pitchNoteBackend: 'auto',
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
    pitchNoteTranslation: {
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
  it('creates a canonical estimate request with staged fields', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: () => Promise.resolve({
        requestId: 'req_estimate_123',
        estimate: {
          durationSeconds: 210.6,
          totalLowMs: 22000,
          totalHighMs: 38000,
          stages: [{ key: 'local_dsp', label: 'Local DSP analysis', lowMs: 22000, highMs: 38000 }],
        },
      }),
    } as Response);
    vi.stubGlobal('fetch', fetchSpy);

    const file = new File(['audio-data'], 'track.mp3', { type: 'audio/mpeg' });
    const estimate = await estimateAnalysisRun(file, {
      apiBaseUrl: 'http://127.0.0.1:8100',
      pitchNoteMode: 'stem_notes',
      pitchNoteBackend: 'auto',
      interpretationMode: 'async',
      interpretationProfile: 'producer_summary',
      interpretationModel: 'gemini-2.5-flash',
    });

    expect(estimate.requestId).toBe('req_estimate_123');

    const request = fetchSpy.mock.calls[0];
    expect(request[0]).toBe('http://127.0.0.1:8100/api/analysis-runs/estimate');
    const body = request[1].body as FormData;
    expect(body.get('pitch_note_mode')).toBe('stem_notes');
    expect(body.get('pitch_note_backend')).toBe('auto');
    expect(body.get('interpretation_mode')).toBe('async');
    expect(body.get('interpretation_profile')).toBe('producer_summary');
    expect(body.get('interpretation_model')).toBe('gemini-2.5-flash');
  });

  it('classifies canonical estimate failures as wrong-service when openapi identifies another API', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);

        if (url.endsWith('/api/analysis-runs/estimate')) {
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
      estimateAnalysisRun(
        new File(['wave'], 'track.mp3', { type: 'audio/mpeg' }),
        {
          apiBaseUrl: 'http://localhost:8000',
          pitchNoteMode: 'off',
          pitchNoteBackend: 'auto',
          interpretationMode: 'off',
          interpretationProfile: 'producer_summary',
        },
      ),
    ).rejects.toMatchObject({
      code: 'BACKEND_WRONG_SERVICE',
      message: expect.stringContaining('/api/analysis-runs/estimate'),
      details: {
        status: 404,
        configuredBaseUrl: 'http://localhost:8000',
        detectedServiceTitle: 'Multi-Agent Dashboard API',
      },
    });
  });

  it('creates a canonical run with pitch/note and interpretation form fields', async () => {
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
      pitchNoteMode: 'stem_notes',
      pitchNoteBackend: 'auto',
      interpretationMode: 'async',
      interpretationProfile: 'producer_summary',
      interpretationModel: 'gemini-2.5-flash',
    });

    expect(snapshot.runId).toBe('run_123');

    const request = fetchSpy.mock.calls[0];
    expect(request[0]).toBe('http://127.0.0.1:8100/api/analysis-runs');
    const body = request[1].body as FormData;
    expect(body.get('pitch_note_mode')).toBe('stem_notes');
    expect(body.get('pitch_note_backend')).toBe('auto');
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
    expect(snapshot.stages.pitchNoteTranslation.preferredAttemptId).toBe('sym_123');
  });

  it('projects phase 1 from the canonical run and injects pitch/note transcription detail', () => {
    const phase1 = projectPhase1FromRun(baseRunSnapshot);

    expect(phase1?.bpm).toBe(126);
    expect(phase1?.transcriptionDetail?.transcriptionMethod).toBe('torchcrepe');
  });

  it('strips leaked transcriptionDetail from canonical measurement while preserving pitch/note output', async () => {
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
    expect(snapshot.stages.pitchNoteTranslation.result?.transcriptionMethod).toBe('torchcrepe');
    expect(projectedPhase1?.transcriptionDetail?.transcriptionMethod).toBe('torchcrepe');
  });

  it('projects phase 2 from the interpretation stage', () => {
    const phase2 = projectPhase2FromRun(baseRunSnapshot);

    expect(phase2?.trackCharacter).toBe('Tight modern electronic mix.');
  });

  it('projects interpretation.v2 producer-summary fields without breaking the run snapshot parser', async () => {
    const v2Snapshot = {
      ...baseRunSnapshot,
      stages: {
        ...baseRunSnapshot.stages,
        interpretation: {
          ...baseRunSnapshot.stages.interpretation,
          result: {
            ...baseRunSnapshot.stages.interpretation.result,
            projectSetup: {
              tempoBpm: 126,
              timeSignature: '4/4',
              sampleRate: 48000,
              bitDepth: 24,
              headroomTarget: '-6 dB',
              sessionGoal: 'Recreate the measured club energy with a controlled low end.',
            },
            trackLayout: [
              {
                order: 1,
                name: 'Drum Group',
                type: 'GROUP',
                purpose: 'Bus kick and percussion together.',
                grounding: {
                  phase1Fields: ['grooveDetail.kickSwing', 'crestFactor'],
                  segmentIndexes: [1],
                },
              },
            ],
            routingBlueprint: {
              sidechainSource: 'Kick',
              sidechainTargets: ['Bass'],
              returns: [
                {
                  name: 'Return A',
                  purpose: 'Short reverb for top percussion.',
                  sendSources: ['Drum Group'],
                  deviceFocus: 'Hybrid Reverb',
                  levelGuidance: '-18 dB baseline send',
                },
              ],
              notes: ['Keep the sub path dry.'],
            },
            warpGuide: {
              fullTrack: {
                warpMode: 'Complex Pro',
                settings: 'Formants 100, Envelope 128',
                reason: 'Protect the full mix while checking arrangement cues.',
              },
              drums: {
                warpMode: 'Beats',
                reason: 'Measured kick transients favor a transient-preserving mode.',
              },
              bass: {
                warpMode: 'Tones',
                reason: 'Bass sustain is better served by a tonal mode.',
              },
              melodic: {
                warpMode: 'Complex',
                reason: 'Melodic material needs harmonic stability.',
              },
              rationale: 'Use stem-appropriate warp modes when reconstructing clips.',
            },
            arrangementOverview: {
              summary: 'Four sections.',
              segments: [
                {
                  index: 1,
                  startTime: 0,
                  endTime: 16,
                  description: 'Intro section',
                  sceneName: 'INTRO',
                  abletonAction: 'Launch the intro scene with filtered drums.',
                  automationFocus: 'Open the filter over the last 4 bars.',
                },
              ],
            },
            mixAndMasterChain: [
              {
                order: 1,
                device: 'EQ Eight',
                deviceFamily: 'NATIVE',
                trackContext: 'Master',
                workflowStage: 'MIX',
                parameter: 'Band 1 Frequency',
                value: '35 Hz',
                reason: 'Tighten the sub shelf before glue compression.',
              },
            ],
            secretSauce: {
              title: 'Punch Layering',
              explanation: 'Layered transient enhancement.',
              implementationSteps: [],
              workflowSteps: [
                {
                  step: 1,
                  trackContext: 'Drum Group',
                  device: 'Glue Compressor',
                  parameter: 'Attack',
                  value: '3 ms',
                  instruction: 'Set up light glue before the build opens up.',
                  measurementJustification: 'Measured crest factor supports a controlled transient shape.',
                },
              ],
            },
            abletonRecommendations: [
              {
                device: 'Glue Compressor',
                deviceFamily: 'NATIVE',
                trackContext: 'Master',
                workflowStage: 'MIX',
                category: 'DYNAMICS',
                parameter: 'Attack',
                value: '3 ms',
                reason: 'Keep transients intact.',
                advancedTip: 'Drive lightly.',
              },
            ],
            audioObservations: {
              soundDesignFingerprint:
                'By ear the bass feels FM-leaning and tightly enveloped, while the hats sit inside a filtered synthetic wash.',
              elementCharacter: [
                {
                  element: 'Kick',
                  description: 'Short click transient with a compact low-end tail.',
                },
              ],
              productionSignatures: ['Short gated reverb feel on percussion accents.'],
              mixContext:
                'The low end feels deliberately forward while the ambience stays tucked behind the groove.',
            },
          },
          provenance: {
            schemaVersion: 'interpretation.v2',
            modelName: 'gemini-2.5-flash',
          },
          diagnostics: {
            validationWarnings: [
              {
                code: 'UNKNOWN_PARAMETER',
                path: 'abletonRecommendations[0].parameter',
                message: 'Parameter mismatch surfaced as a caution.',
              },
            ],
          },
        },
      },
    } satisfies AnalysisRunSnapshot;

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: () => Promise.resolve(v2Snapshot),
    } as Response));

    const snapshot = await getAnalysisRun('run_123', {
      apiBaseUrl: 'http://127.0.0.1:8100',
    });
    const phase2 = projectPhase2FromRun(snapshot);

    expect(phase2?.projectSetup?.sampleRate).toBe(48000);
    expect(phase2?.trackLayout?.[0]?.grounding.phase1Fields).toContain('grooveDetail.kickSwing');
    expect(phase2?.routingBlueprint?.returns[0]?.deviceFocus).toBe('Hybrid Reverb');
    expect(phase2?.warpGuide?.fullTrack.warpMode).toBe('Complex Pro');
    expect(phase2?.secretSauce.workflowSteps?.[0]?.trackContext).toBe('Drum Group');
    expect(phase2?.audioObservations?.elementCharacter[0]?.element).toBe('Kick');
    expect((snapshot.stages.interpretation.provenance as Record<string, unknown> | null)?.schemaVersion).toBe('interpretation.v2');
    expect((snapshot.stages.interpretation.diagnostics as Record<string, unknown> | null)?.validationWarnings).toBeTruthy();
  });

  it('exposes schema-version and validation-warning helpers for the Phase B UI path', () => {
    const getPhase2SchemaVersion = (
      analysisRunsClient as Record<string, unknown>
    ).getPhase2SchemaVersionFromRun as
      | ((snapshot: AnalysisRunSnapshot) => string | null)
      | undefined;
    const projectPhase2ValidationWarnings = (
      analysisRunsClient as Record<string, unknown>
    ).projectPhase2ValidationWarningsFromRun as
      | ((snapshot: AnalysisRunSnapshot) => Array<Record<string, unknown>>)
      | undefined;

    expect(typeof getPhase2SchemaVersion).toBe('function');
    expect(typeof projectPhase2ValidationWarnings).toBe('function');

    const v2Snapshot: AnalysisRunSnapshot = {
      ...baseRunSnapshot,
      stages: {
        ...baseRunSnapshot.stages,
        interpretation: {
          ...baseRunSnapshot.stages.interpretation,
          provenance: {
            schemaVersion: 'interpretation.v2',
          },
          diagnostics: {
            validationWarnings: [
              {
                code: 'UNKNOWN_DEVICE',
                path: 'mixAndMasterChain[0].device',
                message: 'Device mismatch surfaced as a caution.',
                originalValue: 'Glue Comp',
                coercedValue: 'Glue Compressor',
                dropReason: 'Legacy alias was normalized before validation.',
              },
            ],
          },
        },
      },
    };

    expect(getPhase2SchemaVersion?.(v2Snapshot)).toBe('interpretation.v2');
    expect(projectPhase2ValidationWarnings?.(v2Snapshot)).toEqual([
      {
        code: 'UNKNOWN_DEVICE',
        path: 'mixAndMasterChain[0].device',
        message: 'Device mismatch surfaced as a caution.',
        originalValue: 'Glue Comp',
        coercedValue: 'Glue Compressor',
        dropReason: 'Legacy alias was normalized before validation.',
      },
    ]);
  });

  it('keeps stem summary additive and out of the producer-summary projection path', async () => {
    const stemSummarySnapshot = {
      ...baseRunSnapshot,
      stages: {
        ...baseRunSnapshot.stages,
        interpretation: {
          ...baseRunSnapshot.stages.interpretation,
          attemptsSummary: [
            {
              attemptId: 'int_123',
              profileId: 'producer_summary',
              modelName: 'gemini-2.5-flash',
              status: 'completed',
            },
            {
              attemptId: 'int_stem_123',
              profileId: 'stem_summary',
              modelName: 'gemini-2.5-flash',
              status: 'completed',
            },
          ],
          preferredAttemptId: 'int_stem_123',
          result: {
            summary: 'Bass stem: Bass pulses anchor the groove. Musical stem: Upper motion stays approximate.',
            stems: [
              {
                stem: 'bass',
                label: 'Bass stem',
                summary: 'Bass pulses anchor the groove.',
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
                    uncertaintyReason: 'Pitch/Note Translation and measured bar grid agree.',
                  },
                ],
                globalPatterns: {
                  bassRole: 'Anchors the groove.',
                  melodicRole: 'Sparse upper register punctuation.',
                  pumpingOrModulation: 'Measured pumping suggests compressor-driven movement.',
                },
                uncertaintyFlags: ['Upper melodic content is approximate.'],
              },
              {
                stem: 'other',
                label: 'Musical stem',
                summary: 'Upper motion stays approximate.',
                bars: [],
                globalPatterns: {
                  bassRole: 'Not applicable.',
                  melodicRole: 'Sparse upper register punctuation.',
                  pumpingOrModulation: 'Measured pumping suggests compressor-driven movement.',
                },
                uncertaintyFlags: ['Upper melodic content is approximate.'],
              },
            ],
            uncertaintyFlags: ['Upper melodic content is approximate.'],
          },
          profiles: {
            producer_summary: {
              attemptId: 'int_123',
              status: 'completed',
              modelName: 'gemini-2.5-flash',
              result: baseRunSnapshot.stages.interpretation.result,
              provenance: { schemaVersion: 'interpretation.v2' },
              diagnostics: null,
              error: null,
            },
            stem_summary: {
              attemptId: 'int_stem_123',
              status: 'completed',
              modelName: 'gemini-2.5-flash',
              result: {
                summary: 'Bass stem: Bass pulses anchor the groove. Musical stem: Upper motion stays approximate.',
                stems: [
                  {
                    stem: 'bass',
                    label: 'Bass stem',
                    summary: 'Bass pulses anchor the groove.',
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
                        uncertaintyReason: 'Pitch/Note Translation and measured bar grid agree.',
                      },
                    ],
                    globalPatterns: {
                      bassRole: 'Anchors the groove.',
                      melodicRole: 'Sparse upper register punctuation.',
                      pumpingOrModulation: 'Measured pumping suggests compressor-driven movement.',
                    },
                    uncertaintyFlags: ['Upper melodic content is approximate.'],
                  },
                ],
                uncertaintyFlags: ['Upper melodic content is approximate.'],
              },
              provenance: { schemaVersion: 'interpretation.v1' },
              diagnostics: null,
              error: null,
            },
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

    expect(projectPhase2FromRun(snapshot)?.trackCharacter).toBe('Tight modern electronic mix.');
    expect(projectStemSummaryFromRun(snapshot)?.stems[0].bars[0].noteHypotheses).toEqual(['C3 pedal']);
  });

  it('creates pitch/note retry attempts against the canonical endpoint', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      statusText: 'Accepted',
      json: () => Promise.resolve(baseRunSnapshot),
    } as Response);
    vi.stubGlobal('fetch', fetchSpy);

    await createPitchNoteTranslationAttempt('run_123', {
      apiBaseUrl: 'http://127.0.0.1:8100',
      pitchNoteMode: 'stem_notes',
      pitchNoteBackend: 'auto',
    });

    expect(fetchSpy.mock.calls[0]?.[0]).toBe('http://127.0.0.1:8100/api/analysis-runs/run_123/pitch-note-translations');
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

  it('interrupts an analysis run through the canonical endpoint', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      statusText: 'Accepted',
      json: () => Promise.resolve(baseRunSnapshot),
    } as Response);
    vi.stubGlobal('fetch', fetchSpy);

    await interruptAnalysisRun('run_123', {
      apiBaseUrl: 'http://127.0.0.1:8100',
    });

    expect(fetchSpy.mock.calls[0]?.[0]).toBe('http://127.0.0.1:8100/api/analysis-runs/run_123/interrupt');
    expect(fetchSpy.mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
    });
  });
});

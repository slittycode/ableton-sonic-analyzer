import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Phase1Result, Phase2Result } from '../../src/types';

const INLINE_SIZE_LIMIT = 20_971_520;

const {
  GoogleGenAIMock,
  filesUploadMock,
  filesDeleteMock,
  generateContentMock,
} = vi.hoisted(() => ({
  GoogleGenAIMock: vi.fn(),
  filesUploadMock: vi.fn(),
  filesDeleteMock: vi.fn(),
  generateContentMock: vi.fn(),
}));

vi.mock('../../src/config', () => ({
  appConfig: {
    geminiApiKey: 'test-gemini-key',
  },
  isGeminiPhase2Available: () => true,
}));

vi.mock('@google/genai', () => ({
  GoogleGenAI: GoogleGenAIMock,
  Type: {
    OBJECT: 'OBJECT',
    STRING: 'STRING',
    ARRAY: 'ARRAY',
    NUMBER: 'NUMBER',
  },
}));

import { analyzePhase2WithGemini } from '../../src/services/geminiPhase2Client';

const basePhase1: Phase1Result = {
  bpm: 126,
  bpmConfidence: 0.91,
  key: 'F minor',
  keyConfidence: 0.87,
  timeSignature: '4/4',
  durationSeconds: 210.6,
  lufsIntegrated: -7.9,
  truePeak: -0.2,
  stereoWidth: 0.69,
  stereoCorrelation: 0.84,
  spectralBalance: {
    subBass: -0.7,
    lowBass: 1.2,
    mids: -0.3,
    upperMids: 0.4,
    highs: 1.0,
    brilliance: 0.8,
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
        spectralNote: 'High shelf lift around 8 kHz on hats.',
      },
    ],
    noveltyNotes: 'Novel shifts at 14.0s and 63.5s align with transitions.',
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
      advancedTip: 'Modulate coarse slowly.',
    },
  ],
};

const uploadedFile = {
  name: 'files/abc123',
  uri: 'gs://gemini/files/abc123',
  mimeType: 'audio/flac',
};

const audioMetadata = {
  name: 'track.flac',
  size: 1024,
  type: 'audio/flac',
} as const;

const phase2Response = {
  text: JSON.stringify(phase2Result),
};

const fileReaderInstances: MockFileReader[] = [];

class MockFileReader {
  result: string | ArrayBuffer | null = null;
  onload: (() => void) | null = null;
  onerror: ((error?: unknown) => void) | null = null;

  readAsDataURL = vi.fn(() => {
    this.result = 'data:audio/mpeg;base64,ZmFrZQ==';
    queueMicrotask(() => this.onload?.());
  });

  constructor() {
    fileReaderInstances.push(this);
  }
}

function createSmallFile(): File {
  return new File(['wave'], 'track.mp3', { type: 'audio/mpeg' });
}

function createLargeFile(): File {
  return {
    size: INLINE_SIZE_LIMIT + 1,
    type: 'audio/flac',
    name: 'track.flac',
  } as unknown as File;
}

function getRequestParts(): Array<Record<string, unknown>> {
  return generateContentMock.mock.calls[0][0].contents[0].parts as Array<Record<string, unknown>>;
}

function getPromptText(): string {
  const promptPart = getRequestParts()[1];

  if (!promptPart || typeof promptPart.text !== 'string') {
    throw new Error('Gemini prompt text part missing.');
  }

  return promptPart.text;
}

beforeEach(() => {
  filesUploadMock.mockReset();
  filesDeleteMock.mockReset();
  generateContentMock.mockReset();
  GoogleGenAIMock.mockReset();
  fileReaderInstances.length = 0;

  filesUploadMock.mockResolvedValue(uploadedFile);
  filesDeleteMock.mockResolvedValue(undefined);
  generateContentMock.mockResolvedValue(phase2Response);
  GoogleGenAIMock.mockImplementation(function MockGoogleGenAI() {
    return {
      files: {
        upload: filesUploadMock,
        delete: filesDeleteMock,
      },
      models: {
        generateContent: generateContentMock,
      },
    };
  });

  vi.stubGlobal('FileReader', MockFileReader);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('analyzePhase2WithGemini', () => {
  it('uses inlineData for files at or below the inline size limit without uploading', async () => {
    const file = createSmallFile();

    const response = await analyzePhase2WithGemini({
      file,
      modelName: 'gemini-2.5-pro',
      phase1Result: basePhase1,
      audioMetadata,
    });

    const parts = getRequestParts();

    expect(fileReaderInstances).toHaveLength(1);
    expect(fileReaderInstances[0]?.readAsDataURL).toHaveBeenCalledWith(file);
    expect(filesUploadMock).not.toHaveBeenCalled();
    expect(filesDeleteMock).not.toHaveBeenCalled();
    expect(parts[0]).toEqual({
      inlineData: {
        data: 'ZmFrZQ==',
        mimeType: 'audio/mpeg',
      },
    });
    expect(parts.some((part) => 'fileData' in part)).toBe(false);
    expect(response.result.trackCharacter).toBe(phase2Result.trackCharacter);
    expect(response.log.message).toBe('Phase 2 advisory complete.');
  });

  it('uses DSP context for anchoring and audio perception for genre naming in the prompt', async () => {
    await analyzePhase2WithGemini({
      file: createSmallFile(),
      modelName: 'gemini-2.5-pro',
      phase1Result: basePhase1,
      audioMetadata,
    });

    const prompt = getPromptText();

    expect(prompt).toContain(
      'For measured values, the JSON is authoritative. For genre identification only, audio perception is authoritative.',
    );
    expect(prompt).toContain('RHYTHM CLUSTER (from DSP measurements — use as context, not as genre):');
    expect(prompt).toContain('SYNTHESIS TIER (from synthesisCharacter — use to confirm genre, not define it):');
    expect(prompt).toContain('GENRE INFERENCE PROCESS:');
    expect(prompt).toContain('1. State the rhythm cluster and synthesis tier from the JSON above.');
    expect(prompt).toContain(
      "4. Never override the measured DSP values with audio perception. Only use audio perception for the genre label itself.",
    );
    expect(prompt).toContain('Rhythm cluster: which bucket and why');
    expect(prompt).toContain(
      'Synthesis tier: which tier and the specific inharmonicity + oddToEvenRatio values',
    );
    expect(prompt).toContain(
      'Genre confidence: HIGH/MED/LOW with specific reason for any degradation',
    );
    expect(prompt).not.toContain('You are a producer reading a spec sheet, not an audio analyser.');
    expect(prompt).not.toContain('STEP 2 — SYNTHESIS PROFILE (within the cluster from Step 1):');
    expect(prompt).not.toContain('STEP 3 — BPM AS TIEBREAKER');
    expect(prompt).not.toContain('3+ indicators match → HIGH confidence');
  });

  it('uses the Files API for files larger than the inline size limit', async () => {
    await analyzePhase2WithGemini({
      file: createLargeFile(),
      modelName: 'gemini-2.5-pro',
      phase1Result: basePhase1,
      audioMetadata,
    });

    const parts = getRequestParts();

    expect(filesUploadMock).toHaveBeenCalledTimes(1);
    expect(parts[0]).toEqual({
      fileData: {
        fileUri: uploadedFile.uri,
        mimeType: uploadedFile.mimeType,
      },
    });
    expect(parts.some((part) => 'inlineData' in part)).toBe(false);
  });

  it('passes the uploaded file uri and mime type into the generateContent fileData part', async () => {
    await analyzePhase2WithGemini({
      file: createLargeFile(),
      modelName: 'gemini-2.5-pro',
      phase1Result: basePhase1,
      audioMetadata,
    });

    const filePart = getRequestParts()[0]?.fileData as Record<string, string>;

    expect(filePart.fileUri).toBe(uploadedFile.uri);
    expect(filePart.mimeType).toBe(uploadedFile.mimeType);
  });

  it('deletes the uploaded Gemini file after successful large-file generation', async () => {
    await analyzePhase2WithGemini({
      file: createLargeFile(),
      modelName: 'gemini-2.5-pro',
      phase1Result: basePhase1,
      audioMetadata,
    });

    expect(filesDeleteMock).toHaveBeenCalledWith({ name: uploadedFile.name });
  });

  it('swallows Gemini file deletion failures on the large-file path', async () => {
    filesDeleteMock.mockRejectedValueOnce(new Error('delete failed'));

    const response = await analyzePhase2WithGemini({
      file: createLargeFile(),
      modelName: 'gemini-2.5-pro',
      phase1Result: basePhase1,
      audioMetadata,
    });

    expect(response.result.trackCharacter).toBe(phase2Result.trackCharacter);
    expect(filesDeleteMock).toHaveBeenCalledWith({ name: uploadedFile.name });
  });

  it('retries retryable Gemini upload failures on the large-file path', async () => {
    vi.useFakeTimers();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(Math, 'random').mockReturnValue(0);
    filesUploadMock
      .mockRejectedValueOnce(new Error('503 temporary outage'))
      .mockResolvedValueOnce(uploadedFile);

    const promise = analyzePhase2WithGemini({
      file: createLargeFile(),
      modelName: 'gemini-2.5-pro',
      phase1Result: basePhase1,
      audioMetadata,
    });

    await vi.runAllTimersAsync();
    const response = await promise;

    expect(filesUploadMock).toHaveBeenCalledTimes(2);
    expect(console.warn).toHaveBeenCalledWith('[Phase2] Upload attempt 1 of 3...');
    expect(console.warn).toHaveBeenCalledWith(
      '[Phase2] Upload attempt 1 failed (503 temporary outage), retrying in 2000ms...',
    );
    expect(console.warn).toHaveBeenCalledWith('[Phase2] Upload attempt 2 of 3...');
    expect(response.result.trackCharacter).toBe(phase2Result.trackCharacter);
  });

  it('logs when all upload retry attempts are exhausted', async () => {
    vi.useFakeTimers();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(Math, 'random').mockReturnValue(0);
    filesUploadMock.mockRejectedValue(new Error('503 temporary outage'));

    const promise = analyzePhase2WithGemini({
      file: createLargeFile(),
      modelName: 'gemini-2.5-pro',
      phase1Result: basePhase1,
      audioMetadata,
    });
    const rejection = expect(promise).rejects.toThrow('503 temporary outage');

    await vi.runAllTimersAsync();

    await rejection;
    expect(filesUploadMock).toHaveBeenCalledTimes(3);
    expect(console.warn).toHaveBeenCalledWith('[Phase2] Upload attempt 1 of 3...');
    expect(console.warn).toHaveBeenCalledWith('[Phase2] Upload attempt 2 of 3...');
    expect(console.warn).toHaveBeenCalledWith('[Phase2] Upload attempt 3 of 3...');
    expect(console.warn).toHaveBeenCalledWith(
      '[Phase2] Upload attempts exhausted after 3 tries (503 temporary outage).',
    );
  });

  it('does not emit upload warnings when generateContent retries', async () => {
    vi.useFakeTimers();
    const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(Math, 'random').mockReturnValue(0);
    generateContentMock
      .mockRejectedValueOnce(new Error('503 temporary outage'))
      .mockResolvedValueOnce(phase2Response);

    const promise = analyzePhase2WithGemini({
      file: createLargeFile(),
      modelName: 'gemini-2.5-pro',
      phase1Result: basePhase1,
      audioMetadata,
    });

    await vi.runAllTimersAsync();
    const response = await promise;

    expect(generateContentMock).toHaveBeenCalledTimes(2);
    expect(response.result.trackCharacter).toBe(phase2Result.trackCharacter);
    expect(consoleWarnSpy).toHaveBeenCalledTimes(1);
    expect(consoleWarnSpy).toHaveBeenCalledWith('[Phase2] Upload attempt 1 of 3...');
    expect(
      consoleWarnSpy.mock.calls.some(([message]) =>
        String(message).includes('retrying in'),
      ),
    ).toBe(false);
    expect(
      consoleWarnSpy.mock.calls.some(([message]) =>
        String(message).includes('attempts exhausted'),
      ),
    ).toBe(false);
  });

  it('excludes delete latency from upload and generation durations in the large-file success log', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const timestamps = [1_000, 1_300, 1_900, 2_500];
    vi.spyOn(Date, 'now').mockImplementation(() => timestamps.shift() ?? 2_500);
    filesDeleteMock.mockImplementationOnce(async () => {
      Date.now();
    });

    const response = await analyzePhase2WithGemini({
      file: createLargeFile(),
      modelName: 'gemini-2.5-pro',
      phase1Result: basePhase1,
      audioMetadata,
    });

    expect(response.log.durationMs).toBe(900);
    expect(response.log.message).toBe('Phase 2 advisory complete. Upload: 300ms, Generate: 600ms');
  });

  it('degrades malformed Gemini JSON into a skipped phase 2 result', async () => {
    generateContentMock.mockResolvedValueOnce({
      text: '{"trackCharacter":',
    });

    const response = await analyzePhase2WithGemini({
      file: createSmallFile(),
      modelName: 'gemini-2.5-pro',
      phase1Result: basePhase1,
      audioMetadata,
    });

    expect(response.result).toBeNull();
    expect(response.log.phase).toBe('Phase 2: Advisory skipped');
    expect(response.log.status).toBe('skipped');
    expect(response.log.message).toBe('Phase 2 advisory skipped because Gemini returned invalid JSON.');
  });

  it('degrades structurally invalid Gemini JSON into a skipped phase 2 result', async () => {
    generateContentMock.mockResolvedValueOnce({
      text: JSON.stringify({
        trackCharacter: 'Only a headline with the rest missing.',
      }),
    });

    const response = await analyzePhase2WithGemini({
      file: createSmallFile(),
      modelName: 'gemini-2.5-pro',
      phase1Result: basePhase1,
      audioMetadata,
    });

    expect(response.result).toBeNull();
    expect(response.log.phase).toBe('Phase 2: Advisory skipped');
    expect(response.log.status).toBe('skipped');
    expect(response.log.message).toBe('Phase 2 advisory skipped because Gemini returned an invalid response shape.');
  });
});

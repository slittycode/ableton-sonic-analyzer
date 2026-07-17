import {
  AnalysisRunArtifact,
  AnalysisRunRequestedStages,
  AnalysisRunSnapshot,
  AnalysisStageError,
  AnalysisStageStatus,
  BackendEstimateResponse,
  InterpretationAttemptSummary,
  InterpretationSchemaVersion,
  InterpretationResult,
  InterpretationStageSnapshot,
  InterpretationValidationWarning,
  MeasurementResult,
  Mt3AttemptSummary,
  Mt3StageSnapshot,
  Mt3Track,
  Mt3Transcription,
  Phase1Result,
  Phase2Result,
  SpectralArtifactRef,
  SpectralArtifacts,
  StemSummaryResult,
  PitchNoteTranslationAttemptSummary,
  PitchNoteTranslationStageSnapshot,
  PublicStageStatus,
} from '../types';
import { parsePhase1Result } from './backendPhase1Client';
import { requestBackendEstimate } from './backendPhase1Client';
import { fetchJson } from './httpClient';

interface AnalysisRunsClientOptions {
  apiBaseUrl: string;
  signal?: AbortSignal;
}

interface CreateAnalysisRunOptions extends AnalysisRunsClientOptions {
  analysisMode?: 'full' | 'standard';
  pitchNoteMode: string;
  pitchNoteBackend: string;
  interpretationMode: string;
  interpretationProfile: string;
  interpretationModel?: string | null;
  /**
   * Opt-in for the MT3 polyphonic-transcription stage. Defaults to "off"
   * when omitted. The backend enforces the {"off","enabled"} enum at
   * route entry — sending anything else returns 400 MT3_MODE_UNSUPPORTED.
   */
  mt3Mode?: 'off' | 'enabled';
}

type EstimateAnalysisRunOptions = CreateAnalysisRunOptions;

interface CreatePitchNoteAttemptOptions extends AnalysisRunsClientOptions {
  pitchNoteMode: string;
  pitchNoteBackend: string;
}

interface CreateInterpretationAttemptOptions extends AnalysisRunsClientOptions {
  interpretationProfile: string;
  interpretationModel: string;
}

const ANALYSIS_RUN_STATUSES = new Set<AnalysisStageStatus>([
  'queued',
  'running',
  'blocked',
  'ready',
  'completed',
  'failed',
  'interrupted',
  'not_requested',
]);

// Mirror of stage_status.PUBLIC_STATUS_VALUES on the backend. Five-value
// collapse exposed as the additive `publicStatus` field; the Python
// source of truth is `apps/backend/stage_status.py`.
const PUBLIC_STAGE_STATUSES = new Set<PublicStageStatus>([
  'queued',
  'running',
  'completed',
  'failed',
  'interrupted',
]);

export async function estimateAnalysisRun(
  file: File,
  options: EstimateAnalysisRunOptions,
): Promise<BackendEstimateResponse> {
  const body = new FormData();
  body.append('track', file);
  body.append('analysis_mode', options.analysisMode ?? 'full');
  body.append('pitch_note_mode', options.pitchNoteMode);
  body.append('pitch_note_backend', options.pitchNoteBackend);
  body.append('interpretation_mode', options.interpretationMode);
  body.append('interpretation_profile', options.interpretationProfile);
  if (options.interpretationModel) {
    body.append('interpretation_model', options.interpretationModel);
  }
  body.append('mt3_mode', options.mt3Mode ?? 'off');

  return requestBackendEstimate(body, {
    apiBaseUrl: options.apiBaseUrl,
    endpointPath: '/api/analysis-runs/estimate',
    requiredRoutes: ['/api/analysis-runs/estimate', '/api/analysis-runs', '/api/analysis-runs/{run_id}'],
    signal: options.signal,
    sourceLabel: 'Analysis run estimate endpoint',
  });
}

export async function createAnalysisRun(
  file: File,
  options: CreateAnalysisRunOptions,
): Promise<AnalysisRunSnapshot> {
  const body = new FormData();
  body.append('track', file);
  body.append('analysis_mode', options.analysisMode ?? 'full');
  body.append('pitch_note_mode', options.pitchNoteMode);
  body.append('pitch_note_backend', options.pitchNoteBackend);
  body.append('interpretation_mode', options.interpretationMode);
  body.append('interpretation_profile', options.interpretationProfile);
  if (options.interpretationModel) {
    body.append('interpretation_model', options.interpretationModel);
  }
  body.append('mt3_mode', options.mt3Mode ?? 'off');

  const response = await fetchJson(
    `${options.apiBaseUrl}/api/analysis-runs`,
    {
      method: 'POST',
      body,
      signal: options.signal,
    },
  );

  return parseAnalysisRunSnapshot(response);
}

export async function interruptAnalysisRun(
  runId: string,
  options: AnalysisRunsClientOptions,
): Promise<AnalysisRunSnapshot> {
  const response = await fetchJson(
    `${options.apiBaseUrl}/api/analysis-runs/${runId}/interrupt`,
    {
      method: 'POST',
      signal: options.signal,
    },
  );

  return parseAnalysisRunSnapshot(response);
}

export async function getAnalysisRun(
  runId: string,
  options: AnalysisRunsClientOptions,
): Promise<AnalysisRunSnapshot> {
  const response = await fetchJson(
    `${options.apiBaseUrl}/api/analysis-runs/${runId}`,
    {
      method: 'GET',
      signal: options.signal,
    },
  );

  return parseAnalysisRunSnapshot(response);
}

export async function createPitchNoteTranslationAttempt(
  runId: string,
  options: CreatePitchNoteAttemptOptions,
): Promise<AnalysisRunSnapshot> {
  const body = new FormData();
  body.append('pitch_note_mode', options.pitchNoteMode);
  body.append('pitch_note_backend', options.pitchNoteBackend);

  const response = await fetchJson(
    `${options.apiBaseUrl}/api/analysis-runs/${runId}/pitch-note-translations`,
    {
      method: 'POST',
      body,
      signal: options.signal,
    },
  );

  return parseAnalysisRunSnapshot(response);
}

/**
 * Manually enqueue an MT3 polyphonic-transcription attempt on an existing
 * run. Use when the initial `createAnalysisRun` POST sent `mt3Mode: 'off'`
 * (or omitted it) and the user later opts in. The measurement stage must
 * already be `completed` — the backend returns 409 MEASUREMENT_NOT_READY
 * otherwise.
 *
 * Returns the post-enqueue snapshot. Poll `getAnalysisRun` to see the
 * stage advance from `queued` → `running` → `completed|failed`.
 */
export async function createMt3TranscriptionAttempt(
  runId: string,
  options: AnalysisRunsClientOptions,
): Promise<AnalysisRunSnapshot> {
  const response = await fetchJson(
    `${options.apiBaseUrl}/api/analysis-runs/${runId}/mt3-transcriptions`,
    {
      method: 'POST',
      signal: options.signal,
    },
  );

  return parseAnalysisRunSnapshot(response);
}

export async function createInterpretationAttempt(
  runId: string,
  options: CreateInterpretationAttemptOptions,
): Promise<AnalysisRunSnapshot> {
  const body = new FormData();
  body.append('interpretation_profile', options.interpretationProfile);
  body.append('interpretation_model', options.interpretationModel);

  const response = await fetchJson(
    `${options.apiBaseUrl}/api/analysis-runs/${runId}/interpretations`,
    {
      method: 'POST',
      body,
      signal: options.signal,
    },
  );

  return parseAnalysisRunSnapshot(response);
}

export function projectPhase1FromRun(snapshot: AnalysisRunSnapshot): Phase1Result | null {
  if (snapshot.stages.measurement.result == null) {
    return null;
  }

  const measurement: MeasurementResult = snapshot.stages.measurement.result;
  const pitchNote = snapshot.stages.pitchNoteTranslation.result;
  const mt3 = snapshot.stages.mt3?.result ?? null;

  const result: Phase1Result = pitchNote
    ? { ...measurement, transcriptionDetail: pitchNote }
    : measurement;

  // MT3 namespace: present only when the stage produced a non-null result.
  // Matches the absent-when-off contract documented in
  // apps/backend/JSON_SCHEMA.md "Optional MT3 Namespace".
  if (mt3) {
    return { ...result, transcription: { mt3 } };
  }
  return result;
}

export function projectPhase2FromRun(snapshot: AnalysisRunSnapshot): Phase2Result | null {
  const profile = getInterpretationProfileSnapshot(snapshot.stages.interpretation, 'producer_summary');
  if (!profile) {
    return null;
  }
  return profile.result as Phase2Result | null;
}

export function getPhase2SchemaVersionFromRun(
  snapshot: AnalysisRunSnapshot,
): InterpretationSchemaVersion | null {
  const profile = getInterpretationProfileSnapshot(snapshot.stages.interpretation, 'producer_summary');
  if (!profile) {
    return null;
  }

  const provenance = parseNullableRecord(profile.provenance);
  const schemaVersion = asString(provenance?.schemaVersion);
  if (schemaVersion === 'interpretation.v1' || schemaVersion === 'interpretation.v2') {
    return schemaVersion;
  }
  return null;
}

export function projectPhase2ValidationWarningsFromRun(
  snapshot: AnalysisRunSnapshot,
): InterpretationValidationWarning[] {
  const profile = getInterpretationProfileSnapshot(snapshot.stages.interpretation, 'producer_summary');
  if (!profile) {
    return [];
  }

  const diagnostics = parseNullableRecord(profile.diagnostics);
  const rawWarnings = Array.isArray(diagnostics?.validationWarnings)
    ? diagnostics.validationWarnings
    : [];

  return rawWarnings.flatMap((warning): InterpretationValidationWarning[] => {
    const parsed = parseNullableRecord(warning);
    const message = asString(parsed?.message);
    if (!message) {
      return [];
    }
    return [
      {
        code: asString(parsed?.code) ?? undefined,
        path: asString(parsed?.path) ?? undefined,
        message,
        originalValue: asString(parsed?.originalValue) ?? undefined,
        coercedValue: asString(parsed?.coercedValue) ?? undefined,
        dropReason: asString(parsed?.dropReason) ?? undefined,
      },
    ];
  });
}

export function projectStemSummaryFromRun(snapshot: AnalysisRunSnapshot): StemSummaryResult | null {
  const profile = getInterpretationProfileSnapshot(snapshot.stages.interpretation, 'stem_summary');
  if (!profile) {
    return null;
  }
  return profile.result as StemSummaryResult | null;
}

function parseAnalysisRunSnapshot(value: unknown): AnalysisRunSnapshot {
  const root = expectRecord(value, 'analysis run');
  const stages = expectRecord(root.stages, 'analysis run stages');
  const measurement = expectRecord(stages.measurement, 'measurement stage');
  const pitchNoteTranslation = expectRecord(stages.pitchNoteTranslation, 'pitch/note translation stage');
  const interpretation = expectRecord(stages.interpretation, 'interpretation stage');
  // mt3 is required on the snapshot — the backend always emits it (status
  // "not_requested" when mt3_mode is "off"). Old payloads predating the
  // stage may be missing it; we synthesize a default not_requested
  // snapshot in that case so the type contract is satisfied without
  // forcing a 422 on legacy responses.
  const mt3 = stages.mt3 == null
    ? null
    : expectRecord(stages.mt3, 'mt3 stage');

  const artifactsRaw = expectRecord(root.artifacts, 'artifacts');

  return {
    runId: expectString(root.runId, 'runId'),
    source: parseAnalysisRunSource(root.source),
    requestedStages: parseRequestedStages(root.requestedStages),
    artifacts: {
      sourceAudio: parseArtifact(expectRecord(artifactsRaw.sourceAudio, 'sourceAudio')),
      ...(Array.isArray(artifactsRaw.stems)
        ? {
            stems: artifactsRaw.stems.map((artifact, index) =>
              parseArtifact(expectRecord(artifact, `stem artifact ${index}`)),
            ),
          }
        : {}),
      ...(artifactsRaw.spectral ? { spectral: parseSpectralArtifacts(artifactsRaw.spectral) } : {}),
    },
    stages: {
      measurement: {
        status: expectStageStatus(measurement.status),
        publicStatus: parsePublicStageStatus(measurement.publicStatus),
        authoritative: true,
        result: measurement.result == null ? null : parseCanonicalMeasurementResult(measurement.result),
        provenance: parseNullableRecord(measurement.provenance),
        diagnostics: parseNullableRecord(measurement.diagnostics),
        error: parseNullableError(measurement.error),
      },
      pitchNoteTranslation: parsePitchNoteStage(pitchNoteTranslation),
      interpretation: parseInterpretationStage(interpretation),
      mt3: mt3 == null ? defaultMt3Stage() : parseMt3Stage(mt3),
    },
  };
}

function parseAnalysisRunSource(value: unknown): AnalysisRunSnapshot['source'] {
  if (value == null) {
    return {
      kind: 'upload',
      provider: 'upload',
      title: null,
      creator: null,
      attributionUrl: null,
      rightsConfirmedAt: null,
      experimental: false,
    };
  }
  const source = expectRecord(value, 'analysis run source');
  return {
    kind: source.kind === 'link' ? 'link' : 'upload',
    provider: asString(source.provider) ?? 'upload',
    title: asString(source.title),
    creator: asString(source.creator),
    attributionUrl: asString(source.attributionUrl),
    rightsConfirmedAt: asString(source.rightsConfirmedAt),
    experimental: source.experimental === true,
  };
}

function defaultMt3Stage(): Mt3StageSnapshot {
  return {
    status: 'not_requested',
    publicStatus: null,
    authoritative: false,
    preferredAttemptId: null,
    attemptsSummary: [],
    result: null,
    provenance: null,
    diagnostics: null,
    error: null,
  };
}

function parseCanonicalMeasurementResult(value: unknown): MeasurementResult {
  const { transcriptionDetail: _transcriptionDetail, ...measurement } = parsePhase1Result(value);
  return measurement;
}

function parseRequestedStages(value: unknown): AnalysisRunRequestedStages {
  const requested = expectRecord(value, 'requestedStages');
  return {
    analysisMode:
      requested.analysisMode == null ? 'full' : expectAnalysisMode(requested.analysisMode),
    pitchNoteMode: expectString(requested.pitchNoteMode, 'requestedStages.pitchNoteMode'),
    pitchNoteBackend: expectString(requested.pitchNoteBackend, 'requestedStages.pitchNoteBackend'),
    interpretationMode: expectString(requested.interpretationMode, 'requestedStages.interpretationMode'),
    interpretationProfile: expectString(requested.interpretationProfile, 'requestedStages.interpretationProfile'),
    interpretationModel: asString(requested.interpretationModel),
    // Default to "off" if the server response predates the mt3Mode field
    // (older runs may not have it on requestedStages). Matches the
    // "absent unless requested" contract — the legacy default IS off.
    mt3Mode: asString(requested.mt3Mode) ?? 'off',
  };
}

function parseArtifact(value: Record<string, unknown>): AnalysisRunArtifact {
  return {
    artifactId: expectString(value.artifactId, 'artifactId'),
    filename: expectString(value.filename, 'filename'),
    mimeType: expectString(value.mimeType, 'mimeType'),
    sizeBytes: expectNumber(value.sizeBytes, 'sizeBytes'),
    contentSha256: expectString(value.contentSha256, 'contentSha256'),
    path: asString(value.path) ?? undefined,
  };
}

function parseSpectralArtifactRef(value: unknown, label: string): SpectralArtifactRef {
  const s = value as Record<string, unknown>;
  const ref: SpectralArtifactRef = {
    artifactId: expectString(s.artifactId, `${label} artifactId`),
    kind: expectString(s.kind, `${label} kind`) as SpectralArtifactRef['kind'],
    filename: expectString(s.filename, `${label} filename`),
    mimeType: expectString(s.mimeType, `${label} mimeType`),
    sizeBytes: expectNumber(s.sizeBytes, `${label} sizeBytes`),
  };
  // Optional. Backend only emits it for `spectrogram_stft` (source-SR
  // preserved). Without this pass-through the hover crosshair would always
  // fall back to 44100 and report wrong Hz on 48k/96k files.
  if (typeof s.sampleRate === 'number' && Number.isFinite(s.sampleRate)) {
    ref.sampleRate = s.sampleRate;
  }
  return ref;
}

function parseSpectralArtifacts(value: unknown): SpectralArtifacts {
  const raw = value as Record<string, unknown>;
  const spectrograms = Array.isArray(raw.spectrograms) ? raw.spectrograms : [];
  return {
    spectrograms: spectrograms.map((s) => parseSpectralArtifactRef(s, 'spectral')),
    timeSeries: raw.timeSeries ? parseSpectralArtifactRef(raw.timeSeries, 'ts') : null,
    onsetStrength: raw.onsetStrength ? parseSpectralArtifactRef(raw.onsetStrength, 'onset') : null,
    chromaInteractive: raw.chromaInteractive ? parseSpectralArtifactRef(raw.chromaInteractive, 'chroma') : null,
  };
}

function parsePitchNoteStage(value: Record<string, unknown>): PitchNoteTranslationStageSnapshot {
  return {
    status: expectStageStatus(value.status),
    publicStatus: parsePublicStageStatus(value.publicStatus),
    authoritative: false,
    preferredAttemptId: asString(value.preferredAttemptId),
    attemptsSummary: Array.isArray(value.attemptsSummary)
      ? value.attemptsSummary.map(parsePitchNoteAttemptSummary)
      : [],
    result: value.result == null ? null : parsePitchNoteResult(value.result),
    provenance: parseNullableRecord(value.provenance),
    diagnostics: parseNullableRecord(value.diagnostics),
    error: parseNullableError(value.error),
  };
}

function parseInterpretationStage(value: Record<string, unknown>): InterpretationStageSnapshot {
  const attemptsSummary = Array.isArray(value.attemptsSummary)
    ? value.attemptsSummary.map(parseInterpretationAttemptSummary)
    : [];
  const preferredProfileId = getPreferredInterpretationProfileId({
    preferredAttemptId: asString(value.preferredAttemptId),
    attemptsSummary,
  });
  const profilesRaw = parseNullableRecord(value.profiles);
  const profiles = profilesRaw
    ? Object.fromEntries(
        Object.entries(profilesRaw).map(([profileId, profileValue]) => [
          profileId,
          parseInterpretationProfileSnapshot(profileValue, profileId),
        ]),
      )
    : undefined;
  return {
    status: expectStageStatus(value.status),
    publicStatus: parsePublicStageStatus(value.publicStatus),
    authoritative: false,
    preferredAttemptId: asString(value.preferredAttemptId),
    attemptsSummary,
    result: value.result == null ? null : parseInterpretationResult(value.result, preferredProfileId),
    provenance: parseNullableRecord(value.provenance),
    diagnostics: parseNullableRecord(value.diagnostics),
    error: parseNullableError(value.error),
    profiles,
  };
}

function parseInterpretationProfileSnapshot(
  value: unknown,
  profileId: string,
): NonNullable<InterpretationStageSnapshot['profiles']>[string] {
  const profile = expectRecord(value, `interpretation profile ${profileId}`);
  return {
    attemptId: expectString(profile.attemptId, `${profileId} attemptId`),
    status: expectStageStatus(profile.status),
    modelName: asString(profile.modelName),
    result:
      profile.result == null
        ? null
        : parseInterpretationResult(profile.result, profileId),
    provenance: parseNullableRecord(profile.provenance),
    diagnostics: parseNullableRecord(profile.diagnostics),
    error: parseNullableError(profile.error),
  };
}

function parsePitchNoteAttemptSummary(value: unknown): PitchNoteTranslationAttemptSummary {
  const attempt = expectRecord(value, 'pitch/note attempt');
  return {
    attemptId: expectString(attempt.attemptId, 'pitch/note attemptId'),
    backendId: expectString(attempt.backendId, 'pitch/note backendId'),
    mode: expectString(attempt.mode, 'pitch/note mode'),
    status: expectStageStatus(attempt.status),
  };
}

function parseMt3Stage(value: Record<string, unknown>): Mt3StageSnapshot {
  return {
    status: expectStageStatus(value.status),
    publicStatus: parsePublicStageStatus(value.publicStatus),
    authoritative: false,
    preferredAttemptId: asString(value.preferredAttemptId),
    attemptsSummary: Array.isArray(value.attemptsSummary)
      ? value.attemptsSummary.map(parseMt3AttemptSummary)
      : [],
    result: value.result == null ? null : parseMt3Result(value.result),
    provenance: parseNullableRecord(value.provenance),
    diagnostics: parseNullableRecord(value.diagnostics),
    error: parseNullableError(value.error),
  };
}

function parseMt3AttemptSummary(value: unknown): Mt3AttemptSummary {
  const attempt = expectRecord(value, 'mt3 attempt');
  return {
    attemptId: expectString(attempt.attemptId, 'mt3 attemptId'),
    checkpointId: expectString(attempt.checkpointId, 'mt3 checkpointId'),
    status: expectStageStatus(attempt.status),
  };
}

function parseMt3Result(value: unknown): Mt3Transcription {
  const result = expectRecord(value, 'mt3 result');
  const tracksRaw = Array.isArray(result.tracks) ? result.tracks : [];
  return {
    version: expectString(result.version, 'mt3 result.version'),
    stemsUsed: Array.isArray(result.stemsUsed)
      ? result.stemsUsed.flatMap((entry) => {
          const stem = asString(entry);
          return stem == null ? [] : [stem];
        })
      : [],
    tracks: tracksRaw.map((entry, index) => parseMt3Track(entry, index)),
  };
}

function parseMt3Track(value: unknown, index: number): Mt3Track {
  const track = expectRecord(value, `mt3 track ${index}`);
  const pitchRangeRaw = Array.isArray(track.pitchRange) ? track.pitchRange : [0, 0];
  const minMidi = expectNumber(pitchRangeRaw[0] ?? 0, `mt3 track ${index} pitchRange[0]`);
  const maxMidi = expectNumber(pitchRangeRaw[1] ?? 0, `mt3 track ${index} pitchRange[1]`);
  return {
    instrument: expectString(track.instrument, `mt3 track ${index} instrument`),
    midiArtifactId: asString(track.midiArtifactId),
    midiSizeBytes: expectNumber(track.midiSizeBytes ?? 0, `mt3 track ${index} midiSizeBytes`),
    noteCount: expectNumber(track.noteCount ?? 0, `mt3 track ${index} noteCount`),
    pitchRange: [minMidi, maxMidi],
  };
}

function parseInterpretationAttemptSummary(value: unknown): InterpretationAttemptSummary {
  const attempt = expectRecord(value, 'interpretation attempt');
  return {
    attemptId: expectString(attempt.attemptId, 'interpretation attemptId'),
    profileId: expectString(attempt.profileId, 'interpretation profileId'),
    modelName: asString(attempt.modelName),
    status: expectStageStatus(attempt.status),
  };
}

function parseInterpretationResult(
  value: unknown,
  profileId: string | null,
): InterpretationResult {
  if (profileId === 'stem_summary') {
    return parseStemSummaryResult(value);
  }
  return expectRecord(value, 'interpretation result') as unknown as Phase2Result;
}

function parseStemSummaryResult(value: unknown): StemSummaryResult {
  const result = expectRecord(value, 'stem summary result');
  const stems = Array.isArray(result.stems)
    ? result.stems.map((entry) => {
        const stem = expectRecord(entry, 'stem summary stem');
        const globalPatterns = expectRecord(stem.globalPatterns, 'stem summary globalPatterns');
        return {
          stem: expectString(stem.stem, 'stem summary stem kind') as StemSummaryResult['stems'][number]['stem'],
          label: expectString(stem.label, 'stem summary label'),
          summary: expectString(stem.summary, 'stem summary summary'),
          bars: Array.isArray(stem.bars)
            ? stem.bars.map((barEntry) => {
                const bar = expectRecord(barEntry, 'stem summary bar');
                return {
                  barStart: expectNumber(bar.barStart, 'stem summary barStart'),
                  barEnd: expectNumber(bar.barEnd, 'stem summary barEnd'),
                  startTime: expectNumber(bar.startTime, 'stem summary startTime'),
                  endTime: expectNumber(bar.endTime, 'stem summary endTime'),
                  noteHypotheses: Array.isArray(bar.noteHypotheses) ? bar.noteHypotheses.map((item) => String(item)) : [],
                  scaleDegreeHypotheses: Array.isArray(bar.scaleDegreeHypotheses)
                    ? bar.scaleDegreeHypotheses.map((item) => String(item))
                    : [],
                  rhythmicPattern: expectString(bar.rhythmicPattern, 'stem summary rhythmicPattern'),
                  uncertaintyLevel: expectString(bar.uncertaintyLevel, 'stem summary uncertaintyLevel') as StemSummaryResult['stems'][number]['bars'][number]['uncertaintyLevel'],
                  uncertaintyReason: expectString(bar.uncertaintyReason, 'stem summary uncertaintyReason'),
                };
              })
            : [],
          globalPatterns: {
            bassRole: expectString(globalPatterns.bassRole, 'stem summary bassRole'),
            melodicRole: expectString(globalPatterns.melodicRole, 'stem summary melodicRole'),
            pumpingOrModulation: expectString(globalPatterns.pumpingOrModulation, 'stem summary pumpingOrModulation'),
            synthesisCharacter: expectStemSummaryPattern(
              globalPatterns.synthesisCharacter,
              'stem summary synthesisCharacter',
              'No reliable synthesis character measured.',
            ),
            vocalPresence: expectStemSummaryPattern(
              globalPatterns.vocalPresence,
              'stem summary vocalPresence',
              'No reliable vocal evidence measured.',
            ),
            bassCharacter: expectStemSummaryPattern(
              globalPatterns.bassCharacter,
              'stem summary bassCharacter',
              'Bass character unavailable for this stem.',
            ),
          },
          uncertaintyFlags: Array.isArray(stem.uncertaintyFlags)
            ? stem.uncertaintyFlags.map((item) => String(item))
            : [],
        };
      })
    : [];

  if (stems.length > 0) {
    return {
      summary: expectString(result.summary, 'stem summary summary'),
      stems,
      uncertaintyFlags: Array.isArray(result.uncertaintyFlags)
        ? result.uncertaintyFlags.map((item) => String(item))
        : [],
    };
  }

  const globalPatterns = expectRecord(result.globalPatterns, 'stem summary globalPatterns');
  return {
    summary: expectString(result.summary, 'stem summary summary'),
    stems: [
      {
        stem: 'other',
        label: 'Musical stem',
        summary: expectString(result.stemSummary ?? result.summary, 'stem summary per-stem summary'),
        bars: Array.isArray(result.bars)
          ? result.bars.map((entry) => {
              const bar = expectRecord(entry, 'stem summary bar');
              return {
                barStart: expectNumber(bar.barStart, 'stem summary barStart'),
                barEnd: expectNumber(bar.barEnd, 'stem summary barEnd'),
                startTime: expectNumber(bar.startTime, 'stem summary startTime'),
                endTime: expectNumber(bar.endTime, 'stem summary endTime'),
                noteHypotheses: Array.isArray(bar.noteHypotheses) ? bar.noteHypotheses.map((item) => String(item)) : [],
                scaleDegreeHypotheses: Array.isArray(bar.scaleDegreeHypotheses)
                  ? bar.scaleDegreeHypotheses.map((item) => String(item))
                  : [],
                rhythmicPattern: expectString(bar.rhythmicPattern, 'stem summary rhythmicPattern'),
                uncertaintyLevel: expectString(bar.uncertaintyLevel, 'stem summary uncertaintyLevel') as StemSummaryResult['stems'][number]['bars'][number]['uncertaintyLevel'],
                uncertaintyReason: expectString(bar.uncertaintyReason, 'stem summary uncertaintyReason'),
              };
            })
          : [],
        globalPatterns: {
          bassRole: expectString(globalPatterns.bassRole, 'stem summary bassRole'),
          melodicRole: expectString(globalPatterns.melodicRole, 'stem summary melodicRole'),
          pumpingOrModulation: expectString(globalPatterns.pumpingOrModulation, 'stem summary pumpingOrModulation'),
          synthesisCharacter: expectStemSummaryPattern(
            globalPatterns.synthesisCharacter,
            'stem summary synthesisCharacter',
            'No reliable synthesis character measured.',
          ),
          vocalPresence: expectStemSummaryPattern(
            globalPatterns.vocalPresence,
            'stem summary vocalPresence',
            'No reliable vocal evidence measured.',
          ),
          bassCharacter: expectStemSummaryPattern(
            globalPatterns.bassCharacter,
            'stem summary bassCharacter',
            'Bass character unavailable for this stem.',
          ),
        },
        uncertaintyFlags: Array.isArray(result.uncertaintyFlags)
          ? result.uncertaintyFlags.map((item) => String(item))
          : [],
      },
    ],
    uncertaintyFlags: Array.isArray(result.uncertaintyFlags)
      ? result.uncertaintyFlags.map((item) => String(item))
      : [],
  };
}

function getInterpretationProfileSnapshot(
  stage: InterpretationStageSnapshot,
  profileId: string,
): NonNullable<InterpretationStageSnapshot['profiles']>[string] | null {
  const directProfile = stage.profiles?.[profileId];
  if (directProfile) {
    return directProfile;
  }
  const preferredProfileId = getPreferredInterpretationProfileId(stage);
  if (preferredProfileId === profileId) {
    return {
      attemptId: stage.preferredAttemptId ?? '',
      status: stage.status,
      modelName: null,
      result: stage.result,
      provenance: stage.provenance,
      diagnostics: stage.diagnostics,
      error: stage.error,
    };
  }
  return null;
}

function parsePitchNoteResult(value: unknown): NonNullable<PitchNoteTranslationStageSnapshot['result']> {
  type Parsed = NonNullable<PitchNoteTranslationStageSnapshot['result']>;
  const result = expectRecord(value, 'pitch/note result');
  return {
    transcriptionMethod: asString(result.transcriptionMethod) ?? 'unknown',
    noteCount: expectNumber(result.noteCount, 'pitch/note noteCount'),
    averageConfidence: expectNumber(result.averageConfidence, 'pitch/note averageConfidence'),
    stemSeparationUsed: Boolean(result.stemSeparationUsed),
    fullMixFallback: Boolean(result.fullMixFallback),
    stemsTranscribed: Array.isArray(result.stemsTranscribed)
      ? result.stemsTranscribed.map((entry) => String(entry))
      : [],
    perStemAverageConfidence: parsePerStemAverageConfidence(result.perStemAverageConfidence),
    dominantPitches: Array.isArray(result.dominantPitches)
      ? result.dominantPitches.map((entry) => expectRecord(entry, 'dominant pitch') as Parsed['dominantPitches'][number])
      : [],
    pitchRange: expectRecord(result.pitchRange, 'pitch/note pitchRange') as Parsed['pitchRange'],
    notes: Array.isArray(result.notes)
      ? result.notes.map((entry) => expectRecord(entry, 'pitch/note note') as unknown as Parsed['notes'][number])
      : [],
  };
}

function parsePerStemAverageConfidence(value: unknown): Record<string, number> | undefined {
  if (typeof value !== 'object' || value == null || Array.isArray(value)) return undefined;
  const result: Record<string, number> = {};
  for (const [key, raw] of Object.entries(value as Record<string, unknown>)) {
    if (typeof raw !== 'number' || !Number.isFinite(raw)) continue;
    result[key] = raw;
  }
  return result;
}

function parseNullableRecord(value: unknown): Record<string, unknown> | null {
  if (value == null) {
    return null;
  }
  return expectRecord(value, 'record');
}

function expectAnalysisMode(value: unknown): 'full' | 'standard' {
  if (value === 'full' || value === 'standard') {
    return value;
  }
  throw new Error(`analysisMode must be 'full' or 'standard'; received ${String(value)}`);
}

function parseNullableError(value: unknown): AnalysisStageError | null {
  if (value == null) {
    return null;
  }
  const error = expectRecord(value, 'stage error');
  return {
    code: expectString(error.code, 'stage error code'),
    message: expectString(error.message, 'stage error message'),
    retryable: typeof error.retryable === 'boolean' ? error.retryable : undefined,
    phase: asString(error.phase) ?? undefined,
  };
}

function expectRecord(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== 'object' || value == null || Array.isArray(value)) {
    throw new Error(`Expected ${label} to be an object.`);
  }
  return value as Record<string, unknown>;
}

function expectString(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Expected ${label} to be a non-empty string.`);
  }
  return value;
}

function expectStemSummaryPattern(value: unknown, label: string, fallback: string): string {
  if (value === undefined) {
    return fallback;
  }
  return expectString(value, label);
}

function expectNumber(value: unknown, label: string): number {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    throw new Error(`Expected ${label} to be a number.`);
  }
  return value;
}

function expectStageStatus(value: unknown): AnalysisStageStatus {
  if (typeof value !== 'string' || !ANALYSIS_RUN_STATUSES.has(value as AnalysisStageStatus)) {
    throw new Error(`Expected stage status to be one of ${Array.from(ANALYSIS_RUN_STATUSES).join(', ')}.`);
  }
  return value as AnalysisStageStatus;
}

/**
 * Parse the additive `publicStatus` field on a stage. Returns `null` for
 * either a JSON null (the documented "not in pipeline" signal) or for
 * missing values on legacy snapshots that pre-date the field — callers
 * that need the public collapse can use this without crashing on
 * older runs.
 */
function parsePublicStageStatus(value: unknown): PublicStageStatus | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'string') return null;
  return PUBLIC_STAGE_STATUSES.has(value as PublicStageStatus)
    ? (value as PublicStageStatus)
    : null;
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null;
}

function getPreferredInterpretationProfileId(
  stage: Pick<InterpretationStageSnapshot, 'preferredAttemptId' | 'attemptsSummary'>,
): string | null {
  const preferredAttempt = stage.attemptsSummary.find((attempt) => attempt.attemptId === stage.preferredAttemptId);
  return preferredAttempt?.profileId ?? stage.attemptsSummary[0]?.profileId ?? null;
}

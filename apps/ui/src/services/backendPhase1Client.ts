import {
  AcidDetail,
  BackendAnalyzeResponse,
  BackendDiagnostics,
  BackendTimingDiagnostics,
  BackendErrorResponse,
  BackendEstimateResponse,
  BassDetail,
  BeatsLoudness,
  DanceabilityResult,
  DynamicCharacter,
  GenreDetail,
  KickDetail,
  Phase1Result,
  ReverbDetail,
  SupersawDetail,
  VocalDetail,
} from "../types";

const ANALYZE_TIMEOUT_FLOOR_MS = 180_000;
const ANALYZE_TIMEOUT_PADDING_MS = 60_000;
const DEFAULT_BACKEND_TIMEOUT_MS = 600_000;
const DEFAULT_ESTIMATE_TIMEOUT_MS = 30_000;
const BACKEND_IDENTITY_TIMEOUT_MS = 2_500;
const DEFAULT_LOCAL_BACKEND_URL = "http://127.0.0.1:8100";
const EXPECTED_BACKEND_API_TITLE = "Sonic Analyzer Local API";
const LEGACY_LOCAL_BACKEND_URLS = new Set([
  "http://localhost:8000",
  "http://127.0.0.1:8000",
  "http://localhost:8010",
  "http://127.0.0.1:8010",
]);

export type BackendErrorCode =
  | "NETWORK_UNREACHABLE"
  | "BACKEND_HTTP_ERROR"
  | "BACKEND_WRONG_SERVICE"
  | "BACKEND_BAD_RESPONSE"
  | "BACKEND_TIMEOUT"
  | "CLIENT_TIMEOUT"
  | "USER_CANCELLED"
  | "BACKEND_UNKNOWN_ERROR";

interface BackendClientErrorDetails {
  status?: number;
  statusText?: string;
  bodySnippet?: string;
  cause?: unknown;
  requestId?: string;
  serverCode?: string;
  phase?: string;
  retryable?: boolean;
  timeoutMs?: number;
  diagnostics?: BackendDiagnostics;
  configuredBaseUrl?: string;
  detectedServiceTitle?: string;
}

export class BackendClientError extends Error {
  readonly code: BackendErrorCode;
  readonly details?: BackendClientErrorDetails;

  constructor(code: BackendErrorCode, message: string, details?: BackendClientErrorDetails) {
    super(message);
    this.name = "BackendClientError";
    this.code = code;
    this.details = details;
  }
}

export function createUserCancelledError(message = "Analysis was cancelled by the user."): BackendClientError {
  return new BackendClientError("USER_CANCELLED", message);
}

export interface AnalyzePhase1Options {
  apiBaseUrl: string;
  timeoutMs?: number;
  analysisMode?: 'full' | 'standard';
  transcribe?: boolean;
  separate?: boolean;
  signal?: AbortSignal;
}

type UnknownRecord = Record<string, unknown>;
type BackendIdentityProbe = {
  title: string | null;
  paths: string[];
};

const backendIdentityCache = new Map<string, Promise<BackendIdentityProbe | null>>();

export function resetBackendIdentityCacheForTests(): void {
  backendIdentityCache.clear();
}

export function deriveAnalyzeTimeoutMs(estimatedHighMs?: number): number {
  if (typeof estimatedHighMs !== "number" || !Number.isFinite(estimatedHighMs) || estimatedHighMs <= 0) {
    return DEFAULT_BACKEND_TIMEOUT_MS;
  }

  return Math.max(Math.round(estimatedHighMs) + ANALYZE_TIMEOUT_PADDING_MS, ANALYZE_TIMEOUT_FLOOR_MS);
}

export async function estimatePhase1WithBackend(
  file: File,
  options: AnalyzePhase1Options,
): Promise<BackendEstimateResponse> {
  return requestBackendEstimate(
    buildTrackFormData(
      file,
      null,
      options.transcribe ?? false,
      options.separate ?? false,
      options.analysisMode ?? 'full',
    ),
    {
      apiBaseUrl: options.apiBaseUrl,
      endpointPath: "/api/analyze/estimate",
      requiredRoutes: ["/api/analyze", "/api/analyze/estimate"],
      timeoutMs: options.timeoutMs,
      sourceLabel: "DSP estimate endpoint",
    },
  );
}

interface RequestBackendEstimateOptions {
  apiBaseUrl: string;
  endpointPath: string;
  requiredRoutes: string[];
  timeoutMs?: number;
  sourceLabel?: string;
  signal?: AbortSignal;
}

export async function requestBackendEstimate(
  formData: FormData,
  options: RequestBackendEstimateOptions,
): Promise<BackendEstimateResponse> {
  try {
    const response = await postBackendMultipart(
      `${normalizeBaseUrl(options.apiBaseUrl)}${options.endpointPath}`,
      formData,
      options.timeoutMs ?? DEFAULT_ESTIMATE_TIMEOUT_MS,
      options.signal,
    );

    const payload = await parseJsonPayload(response, options.sourceLabel ?? "DSP estimate endpoint");

    return parseBackendEstimateResponse(payload);
  } catch (error) {
    const diagnosedError = await maybePromoteWrongServiceError(
      error,
      options.apiBaseUrl,
      options.requiredRoutes,
    );
    if (diagnosedError instanceof BackendClientError) {
      throw diagnosedError;
    }
    throw new BackendClientError(
      "BACKEND_BAD_RESPONSE",
      `${options.sourceLabel ?? "DSP estimate endpoint"} response did not match the expected contract: ${formatError(diagnosedError)}`,
      { cause: diagnosedError },
    );
  }
}

export function parseBackendAnalyzeResponse(payload: unknown): BackendAnalyzeResponse {
  const root = expectRecord(payload, "response");
  const requestId = expectOptionalString(root, "requestId") ?? "unknown";
  const analysisRunId = expectOptionalString(root, "analysisRunId") ?? undefined;
  const phase1 = parsePhase1Result(root.phase1);
  const diagnostics = parseOptionalBackendDiagnostics(root.diagnostics);

  return {
    requestId,
    analysisRunId,
    phase1,
    diagnostics,
  };
}

export function parseBackendEstimateResponse(payload: unknown): BackendEstimateResponse {
  const root = expectRecord(payload, "response");
  const requestId = expectOptionalString(root, "requestId") ?? "unknown";
  const estimateRecord = expectRecord(root.estimate, "estimate");
  const rawStages = expectArray(estimateRecord.stages, "estimate.stages");

  return {
    requestId,
    estimate: {
      durationSeconds: expectNumber(estimateRecord, "durationSeconds", "estimate.durationSeconds"),
      totalLowMs: expectNumber(estimateRecord, "totalLowMs", "estimate.totalLowMs"),
      totalHighMs: expectNumber(estimateRecord, "totalHighMs", "estimate.totalHighMs"),
      stages: rawStages.map((stageValue, index) => {
        const stage = expectRecord(stageValue, `estimate.stages[${index}]`);
        return {
          key: expectString(stage, "key"),
          label: expectString(stage, "label"),
          lowMs: expectNumber(stage, "lowMs", `estimate.stages[${index}].lowMs`),
          highMs: expectNumber(stage, "highMs", `estimate.stages[${index}].highMs`),
        };
      }),
    },
  };
}

export function mapBackendError(
  error: unknown,
  context?: { timeoutMs?: number },
): BackendClientError {
  if (error instanceof BackendClientError) {
    return error;
  }

  if (error instanceof DOMException && error.name === "AbortError") {
    return new BackendClientError(
      "CLIENT_TIMEOUT",
      "The UI timed out waiting for the local DSP backend response.",
      { cause: error, timeoutMs: context?.timeoutMs },
    );
  }

  if (error instanceof TypeError) {
    return new BackendClientError(
      "NETWORK_UNREACHABLE",
      "Cannot reach the local DSP backend. Confirm it is running and the API base URL is correct.",
      { cause: error },
    );
  }

  return new BackendClientError(
    "BACKEND_UNKNOWN_ERROR",
    `Unexpected DSP backend error: ${formatError(error)}`,
    { cause: error },
  );
}

async function maybePromoteWrongServiceError(
  error: unknown,
  apiBaseUrl: string,
  requiredRoutes: string[],
): Promise<unknown> {
  if (!(error instanceof BackendClientError)) {
    return error;
  }

  const status = error.details?.status;
  if (status !== 404 && status !== 405) {
    return error;
  }

  const identity = await getBackendIdentity(apiBaseUrl);
  if (!identity) {
    return error;
  }

  const configuredBaseUrl = normalizeBaseUrl(apiBaseUrl);
  const hasRequiredRoutes = requiredRoutes.every((route) => identity.paths.includes(route));
  if (identity.title === EXPECTED_BACKEND_API_TITLE && hasRequiredRoutes) {
    return error;
  }

  return new BackendClientError(
    "BACKEND_WRONG_SERVICE",
    buildWrongServiceMessage(configuredBaseUrl, identity, requiredRoutes),
    {
      ...error.details,
      configuredBaseUrl,
      detectedServiceTitle: identity.title ?? undefined,
    },
  );
}

async function getBackendIdentity(apiBaseUrl: string): Promise<BackendIdentityProbe | null> {
  const normalizedBaseUrl = normalizeBaseUrl(apiBaseUrl);
  const cachedProbe = backendIdentityCache.get(normalizedBaseUrl);
  if (cachedProbe) {
    return cachedProbe;
  }

  const probePromise = probeBackendIdentity(normalizedBaseUrl);
  backendIdentityCache.set(normalizedBaseUrl, probePromise);
  return probePromise;
}

async function probeBackendIdentity(apiBaseUrl: string): Promise<BackendIdentityProbe | null> {
  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), BACKEND_IDENTITY_TIMEOUT_MS);

  try {
    const response = await fetch(`${apiBaseUrl}/openapi.json`, {
      method: "GET",
      signal: controller.signal,
    });

    if (!response.ok) return null;

    const payload = await response.json();
    if (!isRecord(payload)) return null;

    const info = isRecord(payload.info) ? payload.info : null;
    const title = toOptionalStringOrNull(info?.title) ?? null;
    const paths = isRecord(payload.paths) ? payload.paths : null;

    return {
      title,
      paths: paths ? Object.keys(paths) : [],
    };
  } catch {
    return null;
  } finally {
    clearTimeout(timeoutHandle);
  }
}

function buildWrongServiceMessage(
  configuredBaseUrl: string,
  identity: BackendIdentityProbe,
  requiredRoutes: string[],
): string {
  const detectedTitle = identity.title ? `"${identity.title}"` : "a different API";
  const missingRoutes = requiredRoutes.filter((route) => !identity.paths.includes(route));
  const missingRouteMessage = missingRoutes.length
    ? ` It does not expose ${missingRoutes.join(" and ")}.`
    : "";
  const staleOverrideMessage = LEGACY_LOCAL_BACKEND_URLS.has(configuredBaseUrl)
    ? " A stale local .env or shell override may still be forcing the old backend URL."
    : "";

  return `Configured DSP backend URL ${configuredBaseUrl} is serving ${detectedTitle}, not ${EXPECTED_BACKEND_API_TITLE}.${missingRouteMessage}${staleOverrideMessage} Start Sonic Analyzer on ${DEFAULT_LOCAL_BACKEND_URL}. For the synced local stack, use ./scripts/dev.sh or run the UI with VITE_API_BASE_URL=${DEFAULT_LOCAL_BACKEND_URL} npm run dev:local.`;
}

function normalizeBaseUrl(value: string): string {
  return value.replace(/\/+$/, "");
}

async function postBackendMultipart(
  endpoint: string,
  formData: FormData,
  timeoutMs: number,
  externalSignal?: AbortSignal,
): Promise<Response> {
  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), timeoutMs);

  if (externalSignal) {
    if (externalSignal.aborted) {
      clearTimeout(timeoutHandle);
      throw createUserCancelledError();
    }
    const onExternalAbort = () => controller.abort();
    externalSignal.addEventListener("abort", onExternalAbort, { once: true });
  }

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });

    if (!response.ok) {
      throw await toBackendHttpError(response);
    }

    return response;
  } catch (error) {
    if (externalSignal?.aborted) {
      throw createUserCancelledError();
    }
    throw mapBackendError(error, { timeoutMs });
  } finally {
    clearTimeout(timeoutHandle);
  }
}

async function parseJsonPayload(response: Response, sourceLabel: string): Promise<unknown> {
  return response.json().catch((error) => {
    throw new BackendClientError(
      "BACKEND_BAD_RESPONSE",
      `${sourceLabel} returned a non-JSON response.`,
      { cause: error },
    );
  });
}

async function toBackendHttpError(response: Response): Promise<BackendClientError> {
  const responseText = await response.text().catch(() => "");
  const parsedEnvelope = tryParseBackendErrorResponse(responseText);

  if (parsedEnvelope) {
    return createBackendErrorFromEnvelope(response, parsedEnvelope, responseText);
  }

  if (response.status === 504) {
    return new BackendClientError(
      "BACKEND_TIMEOUT",
      "Local DSP analysis timed out before completion.",
      {
        status: response.status,
        statusText: response.statusText,
        bodySnippet: responseText.slice(0, 500),
      },
    );
  }

  return new BackendClientError(
    "BACKEND_HTTP_ERROR",
    `DSP backend request failed (HTTP ${response.status}).`,
    {
      status: response.status,
      statusText: response.statusText,
      bodySnippet: responseText.slice(0, 500),
    },
  );
}

function createBackendErrorFromEnvelope(
  response: Response,
  payload: BackendErrorResponse,
  responseText: string,
): BackendClientError {
  const details: BackendClientErrorDetails = {
    status: response.status,
    statusText: response.statusText,
    bodySnippet: responseText.slice(0, 500),
    requestId: payload.requestId,
    serverCode: payload.error.code,
    phase: payload.error.phase,
    retryable: payload.error.retryable,
    diagnostics: payload.diagnostics,
  };

  if (payload.error.code === "ANALYZER_TIMEOUT" || response.status === 504) {
    return new BackendClientError("BACKEND_TIMEOUT", payload.error.message, details);
  }

  return new BackendClientError("BACKEND_HTTP_ERROR", payload.error.message, details);
}

function tryParseBackendErrorResponse(payloadText: string): BackendErrorResponse | null {
  if (!payloadText.trim()) return null;

  try {
    const parsed = JSON.parse(payloadText);
    const root = expectRecord(parsed, "error response");
    const errorRecord = expectRecord(root.error, "error");

    return {
      requestId: expectOptionalString(root, "requestId") ?? "unknown",
      error: {
        code: expectString(errorRecord, "code"),
        message: expectString(errorRecord, "message"),
        phase: expectString(errorRecord, "phase"),
        retryable: expectBoolean(errorRecord, "retryable"),
      },
      diagnostics: parseOptionalBackendDiagnostics(root.diagnostics),
    };
  } catch {
    return null;
  }
}

function buildTrackFormData(
  file: File,
  dspJsonOverride: string | null,
  transcribe = false,
  separate = false,
  analysisMode: 'full' | 'standard' = 'full',
): FormData {
  const formData = new FormData();
  formData.append("track", file);
  formData.append("transcribe", transcribe ? "true" : "false");
  formData.append("separate", separate ? "true" : "false");
  formData.append("analysis_mode", analysisMode);
  if (dspJsonOverride?.trim()) {
    formData.append("dsp_json_override", dspJsonOverride);
  }
  return formData;
}

function parseOptionalBackendDiagnostics(value: unknown): BackendDiagnostics | undefined {
  if (value === undefined || value === null) return undefined;

  const diagnosticsRecord = expectRecord(value, "diagnostics");
  return {
    backendDurationMs: expectNumber(diagnosticsRecord, "backendDurationMs"),
    engineVersion: expectOptionalString(diagnosticsRecord, "engineVersion") ?? undefined,
    estimatedLowMs: expectOptionalNumber(diagnosticsRecord, "estimatedLowMs") ?? undefined,
    estimatedHighMs: expectOptionalNumber(diagnosticsRecord, "estimatedHighMs") ?? undefined,
    timeoutSeconds: expectOptionalNumber(diagnosticsRecord, "timeoutSeconds") ?? undefined,
    stdoutSnippet: expectOptionalString(diagnosticsRecord, "stdoutSnippet") ?? undefined,
    stderrSnippet: expectOptionalString(diagnosticsRecord, "stderrSnippet") ?? undefined,
    timings: parseOptionalBackendTimings(diagnosticsRecord.timings),
  };
}

function parseOptionalBackendTimings(value: unknown): BackendTimingDiagnostics | undefined {
  if (value === undefined || value === null) return undefined;

  const timingsRecord = expectRecord(value, "diagnostics.timings");
  return {
    totalMs: expectNumber(timingsRecord, "totalMs", "diagnostics.timings.totalMs"),
    analysisMs: expectNumber(timingsRecord, "analysisMs", "diagnostics.timings.analysisMs"),
    serverOverheadMs: expectNumber(
      timingsRecord,
      "serverOverheadMs",
      "diagnostics.timings.serverOverheadMs",
    ),
    flagsUsed: expectStringArray(timingsRecord.flagsUsed, "diagnostics.timings.flagsUsed"),
    fileSizeBytes: expectNumber(timingsRecord, "fileSizeBytes", "diagnostics.timings.fileSizeBytes"),
    fileDurationSeconds: expectNullableNumber(
      timingsRecord,
      "fileDurationSeconds",
      "diagnostics.timings.fileDurationSeconds",
    ),
    msPerSecondOfAudio: expectNullableNumber(
      timingsRecord,
      "msPerSecondOfAudio",
      "diagnostics.timings.msPerSecondOfAudio",
    ),
  };
}

export function parsePhase1Result(value: unknown): Phase1Result {
  const phase1 = expectRecord(value, "phase1");
  const spectralBalance = expectRecord(phase1.spectralBalance, "phase1.spectralBalance");
  const melodyDetail = parseOptionalMelodyDetail(phase1);
  const transcriptionDetail = parseOptionalTranscriptionDetail(phase1);

  // stereoWidth/stereoCorrelation may be top-level (normalized by server) or only
  // inside stereoDetail (raw DB rows stored before the normalization fix).
  const stereoFallback = isRecord(phase1.stereoDetail) ? phase1.stereoDetail : {};
  const stereoWidth = toNumber(phase1.stereoWidth) ?? toNumber(stereoFallback.stereoWidth);
  const stereoCorrelation = toNumber(phase1.stereoCorrelation) ?? toNumber(stereoFallback.stereoCorrelation);
  if (stereoWidth === null || stereoCorrelation === null) {
    throw new BackendClientError("BACKEND_BAD_RESPONSE", "Expected stereoWidth and stereoCorrelation to be numbers");
  }

  const lufsIntegrated = expectNumber(phase1, "lufsIntegrated");
  const truePeak = expectNumber(phase1, "truePeak");
  const explicitPlr = toNumber(phase1.plr);
  const normalizedPlr = explicitPlr ?? roundToTwoDecimals(truePeak - lufsIntegrated);
  const monoCompatible = phase1.monoCompatible === true
    ? true
    : phase1.monoCompatible === false
      ? false
      : (stereoFallback.subBassMono === true
          ? true
          : stereoFallback.subBassMono === false
            ? false
            : null);
  const lowMids =
    toNumber(spectralBalance.lowMids) ??
    expectNumber(spectralBalance, "mids", "spectralBalance.mids");

  return {
    bpm: expectNumber(phase1, "bpm"),
    bpmConfidence: expectNumber(phase1, "bpmConfidence"),
    bpmPercival: toNumber(phase1.bpmPercival),
    bpmAgreement: phase1.bpmAgreement === true ? true : phase1.bpmAgreement === false ? false : null,
    bpmDoubletime: phase1.bpmDoubletime === true ? true : phase1.bpmDoubletime === false ? false : null,
    bpmSource: typeof phase1.bpmSource === "string" ? phase1.bpmSource : null,
    bpmRawOriginal: toNumber(phase1.bpmRawOriginal),
    key: expectNullableString(phase1, "key"),
    keyConfidence: expectNumber(phase1, "keyConfidence"),
    keyProfile: toOptionalStringOrNull(phase1.keyProfile),
    tuningFrequency: toNumber(phase1.tuningFrequency),
    tuningCents: toNumber(phase1.tuningCents),
    timeSignature: expectString(phase1, "timeSignature"),
    timeSignatureSource: toOptionalStringOrNull(phase1.timeSignatureSource),
    timeSignatureConfidence: toNumber(phase1.timeSignatureConfidence),
    durationSeconds: expectNumber(phase1, "durationSeconds"),
    sampleRate: toNumber(phase1.sampleRate),
    lufsIntegrated,
    lufsRange: toNumber(phase1.lufsRange),
    lufsMomentaryMax: toNumber(phase1.lufsMomentaryMax),
    lufsShortTermMax: toNumber(phase1.lufsShortTermMax),
    truePeak,
    plr: normalizedPlr,
    crestFactor: toNumber(phase1.crestFactor),
    dynamicSpread: toNumber(phase1.dynamicSpread),
    dynamicCharacter: parseOptionalDynamicCharacter(phase1.dynamicCharacter),
    stereoWidth,
    stereoCorrelation,
    stereoDetail: isRecord(phase1.stereoDetail) ? phase1.stereoDetail as unknown as Phase1Result["stereoDetail"] : null,
    monoCompatible,
    spectralBalance: {
      subBass: expectNumber(spectralBalance, "subBass", "spectralBalance.subBass"),
      lowBass: expectNumber(spectralBalance, "lowBass", "spectralBalance.lowBass"),
      lowMids,
      mids: expectNumber(spectralBalance, "mids", "spectralBalance.mids"),
      upperMids: expectNumber(spectralBalance, "upperMids", "spectralBalance.upperMids"),
      highs: expectNumber(spectralBalance, "highs", "spectralBalance.highs"),
      brilliance: expectNumber(spectralBalance, "brilliance", "spectralBalance.brilliance"),
    },
    spectralDetail: isRecord(phase1.spectralDetail) ? phase1.spectralDetail as Phase1Result["spectralDetail"] : null,
    rhythmDetail: isRecord(phase1.rhythmDetail) ? phase1.rhythmDetail as unknown as Phase1Result["rhythmDetail"] : null,
    melodyDetail,
    transcriptionDetail,
    pitchDetail: isRecord(phase1.pitchDetail) ? phase1.pitchDetail as unknown as Phase1Result["pitchDetail"] : null,
    grooveDetail: isRecord(phase1.grooveDetail) ? phase1.grooveDetail as unknown as Phase1Result["grooveDetail"] : null,
    beatsLoudness: parseOptionalBeatsLoudness(phase1.beatsLoudness),
    sidechainDetail: isRecord(phase1.sidechainDetail) ? phase1.sidechainDetail as unknown as Phase1Result["sidechainDetail"] : null,
    effectsDetail: isRecord(phase1.effectsDetail) ? phase1.effectsDetail as Phase1Result["effectsDetail"] : null,
    synthesisCharacter: isRecord(phase1.synthesisCharacter) ? phase1.synthesisCharacter as Phase1Result["synthesisCharacter"] : null,
    danceability: parseOptionalDanceability(phase1.danceability),
    structure: isRecord(phase1.structure) ? phase1.structure as Phase1Result["structure"] : null,
    arrangementDetail: isRecord(phase1.arrangementDetail) ? phase1.arrangementDetail as Phase1Result["arrangementDetail"] : null,
    segmentLoudness: Array.isArray(phase1.segmentLoudness) ? phase1.segmentLoudness as Phase1Result["segmentLoudness"] : null,
    segmentSpectral: Array.isArray(phase1.segmentSpectral) ? phase1.segmentSpectral as Phase1Result["segmentSpectral"] : null,
    segmentStereo: Array.isArray(phase1.segmentStereo) ? phase1.segmentStereo as Phase1Result["segmentStereo"] : null,
    segmentKey: Array.isArray(phase1.segmentKey) ? phase1.segmentKey as Phase1Result["segmentKey"] : null,
    chordDetail: isRecord(phase1.chordDetail) ? phase1.chordDetail as Phase1Result["chordDetail"] : null,
    perceptual: isRecord(phase1.perceptual) ? phase1.perceptual as unknown as Phase1Result["perceptual"] : null,
    essentiaFeatures: isRecord(phase1.essentiaFeatures) ? phase1.essentiaFeatures as Phase1Result["essentiaFeatures"] : null,
    acidDetail: parseOptionalAcidDetail(phase1.acidDetail),
    reverbDetail: parseOptionalReverbDetail(phase1.reverbDetail),
    vocalDetail: parseOptionalVocalDetail(phase1.vocalDetail),
    supersawDetail: parseOptionalSupersawDetail(phase1.supersawDetail),
    bassDetail: parseOptionalBassDetail(phase1.bassDetail),
    kickDetail: parseOptionalKickDetail(phase1.kickDetail),
    genreDetail: parseOptionalGenreDetail(phase1.genreDetail),
  };
}

function roundToTwoDecimals(value: number): number {
  if (!Number.isFinite(value)) return value;
  return Math.round(value * 100) / 100;
}

function parseOptionalDanceability(value: unknown): DanceabilityResult | null {
  if (value === undefined || value === null) return null;
  if (!isRecord(value)) return null;

  const danceability = toNumber(value.danceability);
  const dfa = toNumber(value.dfa);
  if (danceability === null || dfa === null) return null;

  return { danceability, dfa };
}

function parseOptionalDynamicCharacter(value: unknown): DynamicCharacter | null {
  if (value === undefined || value === null) return null;
  if (!isRecord(value)) return null;

  const dynamicComplexity = toNumber(value.dynamicComplexity);
  const loudnessVariation = toNumber(value.loudnessVariation);
  const spectralFlatness = toNumber(value.spectralFlatness);
  const logAttackTime = toNumber(value.logAttackTime);
  const attackTimeStdDev = toNumber(value.attackTimeStdDev);
  if (dynamicComplexity === null || loudnessVariation === null ||
      spectralFlatness === null || logAttackTime === null || attackTimeStdDev === null) return null;

  return { dynamicComplexity, loudnessVariation, spectralFlatness, logAttackTime, attackTimeStdDev };
}

function parseOptionalBeatsLoudness(value: unknown): BeatsLoudness | null {
  if (value === undefined || value === null) return null;
  if (!isRecord(value)) return null;

  const kickDominantRatio = toNumber(value.kickDominantRatio);
  const midDominantRatio = toNumber(value.midDominantRatio);
  const highDominantRatio = toNumber(value.highDominantRatio);
  const meanBeatLoudness = toNumber(value.meanBeatLoudness);
  const beatLoudnessVariation = toNumber(value.beatLoudnessVariation);
  const beatCount = toNumber(value.beatCount);

  if (kickDominantRatio === null || midDominantRatio === null || highDominantRatio === null ||
      meanBeatLoudness === null || beatLoudnessVariation === null || beatCount === null) return null;

  const accentPattern = Array.isArray(value.accentPattern)
    ? value.accentPattern.map((v: unknown) => toNumber(v) ?? 0).slice(0, 4) as number[]
    : [0, 0, 0, 0];

  return {
    kickDominantRatio, midDominantRatio, highDominantRatio,
    accentPattern, meanBeatLoudness, beatLoudnessVariation,
    beatCount: Math.round(beatCount),
  };
}

function parseOptionalAcidDetail(value: unknown): AcidDetail | null {
  if (value === undefined || value === null) return null;
  if (!isRecord(value)) return null;
  const confidence = toNumber(value.confidence);
  const resonanceLevel = toNumber(value.resonanceLevel);
  const centroidOscillationHz = toNumber(value.centroidOscillationHz);
  const bassRhythmDensity = toNumber(value.bassRhythmDensity);
  if (confidence === null || resonanceLevel === null || centroidOscillationHz === null || bassRhythmDensity === null) return null;
  return {
    isAcid: value.isAcid === true,
    confidence,
    resonanceLevel,
    centroidOscillationHz,
    bassRhythmDensity,
  };
}

function parseOptionalReverbDetail(value: unknown): ReverbDetail | null {
  if (value === undefined || value === null) return null;
  if (!isRecord(value)) return null;
  return {
    rt60: toNumber(value.rt60),
    isWet: value.isWet === true,
    tailEnergyRatio: toNumber(value.tailEnergyRatio),
    measured: value.measured === true,
  };
}

function parseOptionalVocalDetail(value: unknown): VocalDetail | null {
  if (value === undefined || value === null) return null;
  if (!isRecord(value)) return null;
  const confidence = toNumber(value.confidence);
  const vocalEnergyRatio = toNumber(value.vocalEnergyRatio);
  const formantStrength = toNumber(value.formantStrength);
  const mfccLikelihood = toNumber(value.mfccLikelihood);
  if (confidence === null || vocalEnergyRatio === null || formantStrength === null || mfccLikelihood === null) return null;
  return {
    hasVocals: value.hasVocals === true,
    confidence,
    vocalEnergyRatio,
    formantStrength,
    mfccLikelihood,
  };
}

function parseOptionalSupersawDetail(value: unknown): SupersawDetail | null {
  if (value === undefined || value === null) return null;
  if (!isRecord(value)) return null;
  const confidence = toNumber(value.confidence);
  const voiceCount = toNumber(value.voiceCount);
  const avgDetuneCents = toNumber(value.avgDetuneCents);
  const spectralComplexity = toNumber(value.spectralComplexity);
  if (confidence === null || voiceCount === null || avgDetuneCents === null || spectralComplexity === null) return null;
  return {
    isSupersaw: value.isSupersaw === true,
    confidence,
    voiceCount,
    avgDetuneCents,
    spectralComplexity,
  };
}

function parseOptionalBassDetail(value: unknown): BassDetail | null {
  if (value === undefined || value === null) return null;
  if (!isRecord(value)) return null;
  const averageDecayMs = toNumber(value.averageDecayMs);
  const transientRatio = toNumber(value.transientRatio);
  const transientCount = toNumber(value.transientCount);
  const swingPercent = toNumber(value.swingPercent);
  if (averageDecayMs === null || transientRatio === null || transientCount === null || swingPercent === null) return null;
  const validTypes = ["punchy", "medium", "rolling", "sustained"] as const;
  const type = validTypes.includes(value.type as typeof validTypes[number])
    ? (value.type as typeof validTypes[number])
    : "medium";
  return {
    averageDecayMs,
    type,
    transientRatio,
    fundamentalHz: toNumber(value.fundamentalHz),
    transientCount,
    swingPercent,
    grooveType: typeof value.grooveType === "string" ? value.grooveType : "unknown",
  };
}

function parseOptionalKickDetail(value: unknown): KickDetail | null {
  if (value === undefined || value === null) return null;
  if (!isRecord(value)) return null;
  const thd = toNumber(value.thd);
  const harmonicRatio = toNumber(value.harmonicRatio);
  const kickCount = toNumber(value.kickCount);
  if (thd === null || harmonicRatio === null || kickCount === null) return null;
  return {
    isDistorted: value.isDistorted === true,
    thd,
    harmonicRatio,
    fundamentalHz: toNumber(value.fundamentalHz),
    kickCount,
  };
}

function parseOptionalGenreDetail(value: unknown): GenreDetail | null {
  if (value === undefined || value === null) return null;
  if (!isRecord(value)) return null;
  const confidence = toNumber(value.confidence);
  if (confidence === null || typeof value.genre !== "string") return null;
  const validFamilies = ["house", "techno", "dnb", "ambient", "trance", "dubstep", "breaks", "other"] as const;
  const genreFamily = validFamilies.includes(value.genreFamily as typeof validFamilies[number])
    ? (value.genreFamily as typeof validFamilies[number])
    : "other";
  const topScores = Array.isArray(value.topScores)
    ? value.topScores
        .filter((s: unknown) => isRecord(s) && typeof s.genre === "string" && toNumber(s.score) !== null)
        .map((s: Record<string, unknown>) => ({ genre: s.genre as string, score: toNumber(s.score)! }))
    : [];
  return {
    genre: value.genre,
    confidence,
    secondaryGenre: typeof value.secondaryGenre === "string" ? value.secondaryGenre : null,
    genreFamily,
    topScores,
  };
}

function parseOptionalMelodyDetail(phase1: UnknownRecord): Phase1Result["melodyDetail"] | undefined {
  const raw = phase1.melodyDetail;
  if (!isRecord(raw)) return undefined;

  const notes = parseMelodyNotes(raw.notes);
  const dominantNotes = parseDominantNotes(raw.dominantNotes);
  const pitchRange = parsePitchRange(raw.pitchRange, notes);
  const noteCountRaw = toNumber(raw.noteCount);
  const noteCount = noteCountRaw === null ? notes.length : Math.max(0, Math.round(noteCountRaw));

  return {
    noteCount,
    notes,
    dominantNotes,
    pitchRange,
    pitchConfidence: clamp01(toNumberOrFallback(raw.pitchConfidence, 0)),
    midiFile: toOptionalStringOrNull(raw.midiFile),
    sourceSeparated: toBooleanOrFallback(raw.sourceSeparated, false),
    vibratoPresent: toBooleanOrFallback(raw.vibratoPresent, false),
    vibratoExtent: toNumberOrFallback(raw.vibratoExtent, 0),
    vibratoRate: toNumberOrFallback(raw.vibratoRate, 0),
    vibratoConfidence: clamp01(toNumberOrFallback(raw.vibratoConfidence, 0)),
  };
}

function parseOptionalTranscriptionDetail(
  phase1: UnknownRecord,
): Phase1Result["transcriptionDetail"] | undefined {
  const raw = phase1.transcriptionDetail;
  if (raw === undefined) return undefined;
  if (raw === null || !isRecord(raw)) return null;

  const notes = parseTranscriptionNotes(raw.notes);
  const dominantPitches = parseDominantPitches(raw.dominantPitches);
  const pitchRange = parseTranscriptionPitchRange(raw.pitchRange, notes);
  const noteCountRaw = toNumber(raw.noteCount);
  const noteCount = noteCountRaw === null ? notes.length : Math.max(0, Math.round(noteCountRaw));

  return {
    transcriptionMethod: toOptionalStringOrNull(raw.transcriptionMethod) ?? "torchcrepe-viterbi",
    noteCount,
    averageConfidence: clamp01(toNumberOrFallback(raw.averageConfidence, 0)),
    stemSeparationUsed: toBooleanOrFallback(raw.stemSeparationUsed, false),
    fullMixFallback: toBooleanOrFallback(
      raw.fullMixFallback,
      raw.stemSeparationUsed === false,
    ),
    stemsTranscribed: parseTranscribedStems(raw.stemsTranscribed),
    dominantPitches,
    pitchRange,
    notes,
  };
}

function parseMelodyNotes(value: unknown): NonNullable<Phase1Result["melodyDetail"]>["notes"] {
  if (!Array.isArray(value)) return [];

  const parsed = value
    .map((entry) => {
      if (!isRecord(entry)) return null;
      const midiRaw = toNumber(entry.midi);
      const onsetRaw = toNumber(entry.onset);
      const durationRaw = toNumber(entry.duration);
      if (midiRaw === null || onsetRaw === null || durationRaw === null) return null;
      if (durationRaw <= 0) return null;

      return {
        midi: Math.max(0, Math.min(127, Math.round(midiRaw))),
        onset: Math.max(0, onsetRaw),
        duration: durationRaw,
      };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null);

  return parsed.sort((a, b) => a.onset - b.onset);
}

function parseDominantNotes(value: unknown): number[] {
  if (!Array.isArray(value)) return [];

  const normalized = value
    .map((entry) => toNumber(entry))
    .filter((entry): entry is number => entry !== null)
    .map((entry) => Math.max(0, Math.min(127, Math.round(entry))));

  return Array.from(new Set(normalized)).slice(0, 5);
}

function parsePitchRange(
  value: unknown,
  notes: NonNullable<Phase1Result["melodyDetail"]>["notes"],
): NonNullable<Phase1Result["melodyDetail"]>["pitchRange"] {
  if (isRecord(value)) {
    const parsedMin = value.min === null ? null : toNumber(value.min);
    const parsedMax = value.max === null ? null : toNumber(value.max);
    return {
      min: parsedMin === null ? null : Math.max(0, Math.min(127, Math.round(parsedMin))),
      max: parsedMax === null ? null : Math.max(0, Math.min(127, Math.round(parsedMax))),
    };
  }

  if (!notes.length) return { min: null, max: null };
  const midiValues = notes.map((note) => note.midi);
  return {
    min: Math.min(...midiValues),
    max: Math.max(...midiValues),
  };
}

function parseTranscriptionNotes(value: unknown): NonNullable<Phase1Result["transcriptionDetail"]>["notes"] {
  if (!Array.isArray(value)) return [];

  const parsed = value
    .map((entry) => {
      if (!isRecord(entry)) return null;
      const pitchMidiRaw = toNumber(entry.pitchMidi);
      const onsetSecondsRaw = toNumber(entry.onsetSeconds);
      const durationSecondsRaw = toNumber(entry.durationSeconds);
      if (pitchMidiRaw === null || onsetSecondsRaw === null || durationSecondsRaw === null) return null;
      if (durationSecondsRaw <= 0 || onsetSecondsRaw < 0) return null;

      const pitchMidi = Math.max(0, Math.min(127, Math.round(pitchMidiRaw)));
      const stemSource = toStemSource(entry.stemSource);

      return {
        pitchMidi,
        pitchName: toOptionalStringOrNull(entry.pitchName) ?? `MIDI ${pitchMidi}`,
        onsetSeconds: onsetSecondsRaw,
        durationSeconds: durationSecondsRaw,
        confidence: clamp01(toNumberOrFallback(entry.confidence, 0)),
        stemSource,
      };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null);

  return parsed.sort((a, b) => a.onsetSeconds - b.onsetSeconds);
}

function parseDominantPitches(
  value: unknown,
): NonNullable<Phase1Result["transcriptionDetail"]>["dominantPitches"] {
  if (!Array.isArray(value)) return [];

  return value
    .map((entry) => {
      if (!isRecord(entry)) return null;
      const pitchMidiRaw = toNumber(entry.pitchMidi);
      const countRaw = toNumber(entry.count);
      if (pitchMidiRaw === null || countRaw === null) return null;

      const pitchMidi = Math.max(0, Math.min(127, Math.round(pitchMidiRaw)));
      return {
        pitchMidi,
        pitchName: toOptionalStringOrNull(entry.pitchName) ?? `MIDI ${pitchMidi}`,
        count: Math.max(0, Math.round(countRaw)),
      };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null);
}

function parseTranscriptionPitchRange(
  value: unknown,
  notes: NonNullable<Phase1Result["transcriptionDetail"]>["notes"],
): NonNullable<Phase1Result["transcriptionDetail"]>["pitchRange"] {
  if (isRecord(value)) {
    const minMidiRaw = value.minMidi === null ? null : toNumber(value.minMidi);
    const maxMidiRaw = value.maxMidi === null ? null : toNumber(value.maxMidi);
    return {
      minMidi: minMidiRaw === null ? null : Math.max(0, Math.min(127, Math.round(minMidiRaw))),
      maxMidi: maxMidiRaw === null ? null : Math.max(0, Math.min(127, Math.round(maxMidiRaw))),
      minName: toOptionalStringOrNull(value.minName),
      maxName: toOptionalStringOrNull(value.maxName),
    };
  }

  if (!notes.length) {
    return {
      minMidi: null,
      maxMidi: null,
      minName: null,
      maxName: null,
    };
  }

  const midiValues = notes.map((note) => note.pitchMidi);
  const sorted = [...midiValues].sort((a, b) => a - b);
  const minMidi = sorted[0] ?? null;
  const maxMidi = sorted[sorted.length - 1] ?? null;
  const minNote = notes.find((note) => note.pitchMidi === minMidi);
  const maxNote = notes.find((note) => note.pitchMidi === maxMidi);

  return {
    minMidi,
    maxMidi,
    minName: minNote?.pitchName ?? null,
    maxName: maxNote?.pitchName ?? null,
  };
}

function parseTranscribedStems(value: unknown): string[] {
  if (!Array.isArray(value)) return [];

  return value
    .map((entry) => toOptionalStringOrNull(entry))
    .filter((entry): entry is string => entry !== null);
}

function toStemSource(
  value: unknown,
): NonNullable<Phase1Result["transcriptionDetail"]>["notes"][number]["stemSource"] {
  return value === "bass" || value === "other" || value === "full_mix" ? value : "full_mix";
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function expectArray(value: unknown, label: string): unknown[] {
  if (!Array.isArray(value)) {
    throw new Error(`Expected ${label} to be an array.`);
  }
  return value;
}

function expectStringArray(value: unknown, label: string): string[] {
  return expectArray(value, label).map((entry, index) => {
    if (typeof entry !== "string") {
      throw new Error(`Expected ${label}[${index}] to be a string.`);
    }
    return entry;
  });
}

function toNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function toNumberOrFallback(value: unknown, fallback: number): number {
  const parsed = toNumber(value);
  return parsed === null ? fallback : parsed;
}

function toBooleanOrFallback(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function toOptionalStringOrNull(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return normalized.length ? normalized : null;
}

function expectRecord(value: unknown, label: string): UnknownRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`Expected ${label} to be an object.`);
  }
  return value as UnknownRecord;
}

function expectString(record: UnknownRecord, key: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Expected ${key} to be a non-empty string.`);
  }
  return value;
}

function expectOptionalString(record: UnknownRecord, key: string): string | null {
  const value = record[key];
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Expected ${key} to be a string when provided.`);
  }
  return value;
}

function expectNullableString(record: UnknownRecord, key: string): string | null {
  const value = record[key];
  if (value === null) return null;
  if (typeof value !== "string") {
    throw new Error(`Expected ${key} to be a string or null.`);
  }
  return value;
}

function expectBoolean(record: UnknownRecord, key: string): boolean {
  const value = record[key];
  if (typeof value !== "boolean") {
    throw new Error(`Expected ${key} to be a boolean.`);
  }
  return value;
}

function expectNumber(record: UnknownRecord, key: string, label = key): number {
  const value = record[key];
  if (typeof value !== "number" || Number.isNaN(value)) {
    throw new Error(`Expected ${label} to be a number.`);
  }
  return value;
}

function expectOptionalNumber(record: UnknownRecord, key: string): number | null {
  const value = record[key];
  if (value === undefined || value === null) return null;
  if (typeof value !== "number" || Number.isNaN(value)) {
    throw new Error(`Expected ${key} to be a number when provided.`);
  }
  return value;
}

function expectNullableNumber(record: UnknownRecord, key: string, label = key): number | null {
  const value = record[key];
  if (value === null) return null;
  if (typeof value !== "number" || Number.isNaN(value)) {
    throw new Error(`Expected ${label} to be a number or null.`);
  }
  return value;
}

function formatError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

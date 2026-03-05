import { BackendAnalyzeResponse, Phase1Result } from "../types";

const DEFAULT_BACKEND_TIMEOUT_MS = 120_000;

export type BackendErrorCode =
  | "NETWORK_UNREACHABLE"
  | "BACKEND_HTTP_ERROR"
  | "BACKEND_BAD_RESPONSE"
  | "BACKEND_TIMEOUT"
  | "BACKEND_UNKNOWN_ERROR";

interface BackendClientErrorDetails {
  status?: number;
  statusText?: string;
  bodySnippet?: string;
  cause?: unknown;
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

export interface AnalyzePhase1Options {
  apiBaseUrl: string;
  timeoutMs?: number;
}

type UnknownRecord = Record<string, unknown>;

export async function analyzePhase1WithBackend(
  file: File,
  dspJsonOverride: string | null,
  options: AnalyzePhase1Options,
): Promise<BackendAnalyzeResponse> {
  const endpoint = `${options.apiBaseUrl}/api/analyze`;
  const timeoutMs = options.timeoutMs ?? DEFAULT_BACKEND_TIMEOUT_MS;
  const formData = new FormData();
  formData.append("track", file);
  if (dspJsonOverride?.trim()) {
    formData.append("dsp_json_override", dspJsonOverride);
  }

  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });

    if (!response.ok) {
      const responseText = await response.text().catch(() => "");
      throw new BackendClientError(
        "BACKEND_HTTP_ERROR",
        `DSP backend request failed (HTTP ${response.status}).`,
        {
          status: response.status,
          statusText: response.statusText,
          bodySnippet: responseText.slice(0, 500),
        },
      );
    }

    const payload = await response.json().catch((error) => {
      throw new BackendClientError(
        "BACKEND_BAD_RESPONSE",
        "DSP backend returned a non-JSON response.",
        { cause: error },
      );
    });

    try {
      return parseBackendAnalyzeResponse(payload);
    } catch (error) {
      throw new BackendClientError(
        "BACKEND_BAD_RESPONSE",
        `DSP backend response did not match the expected contract: ${formatError(error)}`,
        { cause: error },
      );
    }
  } catch (error) {
    throw mapBackendError(error);
  } finally {
    clearTimeout(timeoutHandle);
  }
}

export function parseBackendAnalyzeResponse(payload: unknown): BackendAnalyzeResponse {
  const root = expectRecord(payload, "response");
  const requestId = expectOptionalString(root, "requestId") ?? "unknown";
  const phase1 = parsePhase1Result(root.phase1);

  let diagnostics: BackendAnalyzeResponse["diagnostics"] | undefined;
  if (root.diagnostics !== undefined && root.diagnostics !== null) {
    const diagnosticsRecord = expectRecord(root.diagnostics, "diagnostics");
    diagnostics = {
      backendDurationMs: expectNumber(diagnosticsRecord, "backendDurationMs"),
      engineVersion: expectString(diagnosticsRecord, "engineVersion"),
    };
  }

  return {
    requestId,
    phase1,
    diagnostics,
  };
}

export function mapBackendError(error: unknown): BackendClientError {
  if (error instanceof BackendClientError) {
    return error;
  }

  if (error instanceof DOMException && error.name === "AbortError") {
    return new BackendClientError(
      "BACKEND_TIMEOUT",
      "DSP backend timed out while processing the track.",
      { cause: error },
    );
  }

  if (error instanceof TypeError) {
    return new BackendClientError(
      "NETWORK_UNREACHABLE",
      "Cannot reach DSP backend. Confirm the local backend is running and VITE_API_BASE_URL is correct.",
      { cause: error },
    );
  }

  return new BackendClientError(
    "BACKEND_UNKNOWN_ERROR",
    `Unexpected DSP backend error: ${formatError(error)}`,
    { cause: error },
  );
}

function parsePhase1Result(value: unknown): Phase1Result {
  const phase1 = expectRecord(value, "phase1");
  const spectralBalance = expectRecord(phase1.spectralBalance, "phase1.spectralBalance");
  const melodyDetail = parseOptionalMelodyDetail(phase1);

  return {
    bpm: expectNumber(phase1, "bpm"),
    bpmConfidence: expectNumber(phase1, "bpmConfidence"),
    key: expectNullableString(phase1, "key"),
    keyConfidence: expectNumber(phase1, "keyConfidence"),
    timeSignature: expectString(phase1, "timeSignature"),
    durationSeconds: expectNumber(phase1, "durationSeconds"),
    lufsIntegrated: expectNumber(phase1, "lufsIntegrated"),
    truePeak: expectNumber(phase1, "truePeak"),
    stereoWidth: expectNumber(phase1, "stereoWidth"),
    stereoCorrelation: expectNumber(phase1, "stereoCorrelation"),
    spectralBalance: {
      subBass: expectNumber(spectralBalance, "subBass", "spectralBalance.subBass"),
      lowBass: expectNumber(spectralBalance, "lowBass", "spectralBalance.lowBass"),
      mids: expectNumber(spectralBalance, "mids", "spectralBalance.mids"),
      upperMids: expectNumber(spectralBalance, "upperMids", "spectralBalance.upperMids"),
      highs: expectNumber(spectralBalance, "highs", "spectralBalance.highs"),
      brilliance: expectNumber(spectralBalance, "brilliance", "spectralBalance.brilliance"),
    },
    melodyDetail,
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

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
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

function expectNumber(record: UnknownRecord, key: string, label = key): number {
  const value = record[key];
  if (typeof value !== "number" || Number.isNaN(value)) {
    throw new Error(`Expected ${label} to be a number.`);
  }
  return value;
}

function formatError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

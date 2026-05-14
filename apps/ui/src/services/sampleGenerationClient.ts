/**
 * Typed HTTP client for the Phase 3 audition-sample endpoints.
 *
 * Endpoints:
 * - POST /api/analysis-runs/{run_id}/samples            — generate (returns manifest)
 * - GET  /api/analysis-runs/{run_id}/samples            — fetch existing manifest
 * - GET  /api/analysis-runs/{run_id}/artifacts/{id}     — stream a WAV/MIDI
 *
 * The first two return the same manifest shape; the third is a binary stream
 * we expose as a URL the consumer can hand to an <audio> element.
 */

import { SamplesManifest } from '../types/samples';
import { fetchJson } from './httpClient';
import { BackendClientError } from './backendPhase1Client';

export interface SampleGenerationClientOptions {
  apiBaseUrl: string;
  signal?: AbortSignal;
}

/**
 * The backend returns 404 `SAMPLES_NOT_GENERATED` when no manifest exists yet.
 * Surface that as null instead of a thrown error so the UI can decide whether
 * to show the "generate" CTA or a "samples not yet available" state.
 */
export async function fetchExistingManifest(
  runId: string,
  options: SampleGenerationClientOptions,
): Promise<SamplesManifest | null> {
  const url = `${options.apiBaseUrl}/api/analysis-runs/${encodeURIComponent(runId)}/samples`;
  try {
    const payload = await fetchJson(url, { method: 'GET', signal: options.signal });
    return parseManifest(payload);
  } catch (err) {
    if (
      err instanceof BackendClientError &&
      err.details?.serverCode === 'SAMPLES_NOT_GENERATED'
    ) {
      return null;
    }
    throw err;
  }
}

export async function generateSamples(
  runId: string,
  options: SampleGenerationClientOptions & { force?: boolean },
): Promise<SamplesManifest> {
  const params = new URLSearchParams();
  if (options.force) params.set('force', 'true');
  const query = params.toString();
  const url = `${options.apiBaseUrl}/api/analysis-runs/${encodeURIComponent(runId)}/samples${
    query ? `?${query}` : ''
  }`;
  const payload = await fetchJson(url, { method: 'POST', signal: options.signal });
  return parseManifest(payload);
}

export function artifactStreamUrl(
  runId: string,
  artifactId: string,
  apiBaseUrl: string,
): string {
  const encodedRun = encodeURIComponent(runId);
  const encodedArtifact = encodeURIComponent(artifactId);
  return `${apiBaseUrl}/api/analysis-runs/${encodedRun}/artifacts/${encodedArtifact}`;
}

// --- Parsing ----------------------------------------------------------- //

export function parseManifest(payload: unknown): SamplesManifest {
  if (!isRecord(payload)) {
    throw new BackendClientError(
      'BACKEND_BAD_RESPONSE',
      'Sample manifest payload was not an object.',
    );
  }
  const schemaVersion = payload.schemaVersion;
  if (schemaVersion !== 'samples.v1') {
    throw new BackendClientError(
      'BACKEND_BAD_RESPONSE',
      `Unrecognized sample manifest schema: ${String(schemaVersion)}`,
    );
  }
  const samplesRaw = payload.samples;
  if (!Array.isArray(samplesRaw)) {
    throw new BackendClientError(
      'BACKEND_BAD_RESPONSE',
      'Sample manifest missing `samples` array.',
    );
  }
  return {
    schemaVersion: 'samples.v1',
    runId: String(payload.runId ?? ''),
    generatedAt: String(payload.generatedAt ?? ''),
    synthesisBackend:
      payload.synthesisBackend === 'fluidsynth' ? 'fluidsynth' : 'sine_fallback',
    soundfont: typeof payload.soundfont === 'string' ? payload.soundfont : null,
    framing: typeof payload.framing === 'string' ? payload.framing : '',
    theoryBackend: payload.theoryBackend === 'pytheory' ? 'pytheory' : 'fallback',
    samples: samplesRaw.map(parseSampleRecord),
    manifestArtifactId:
      typeof payload.manifestArtifactId === 'string'
        ? payload.manifestArtifactId
        : undefined,
  };
}

function parseSampleRecord(raw: unknown): SamplesManifest['samples'][number] {
  if (!isRecord(raw)) {
    throw new BackendClientError(
      'BACKEND_BAD_RESPONSE',
      'Sample record was not an object.',
    );
  }
  const cites = isRecord(raw.cites) ? raw.cites : {};
  return {
    id: String(raw.id ?? ''),
    label: String(raw.label ?? ''),
    category: parseCategory(raw.category),
    filename: String(raw.filename ?? ''),
    mimeType: String(raw.mimeType ?? 'audio/wav'),
    durationSeconds: Number.isFinite(raw.durationSeconds)
      ? Number(raw.durationSeconds)
      : 0,
    confidence: parseConfidence(raw.confidence),
    lowConfidence: Boolean(raw.lowConfidence),
    cites: {
      phase1Fields: Array.isArray(cites.phase1Fields)
        ? cites.phase1Fields.map(String)
        : [],
      phase2Recommendations: Array.isArray(cites.phase2Recommendations)
        ? cites.phase2Recommendations.map(String)
        : [],
      rationale: typeof cites.rationale === 'string' ? cites.rationale : '',
    },
    midiFilename: typeof raw.midiFilename === 'string' ? raw.midiFilename : undefined,
    artifactId: typeof raw.artifactId === 'string' ? raw.artifactId : undefined,
    midiArtifactId:
      typeof raw.midiArtifactId === 'string' ? raw.midiArtifactId : undefined,
  };
}

function parseCategory(value: unknown): SamplesManifest['samples'][number]['category'] {
  if (value === 'tonal' || value === 'drums' || value === 'melody') return value;
  return 'tonal';
}

function parseConfidence(
  value: unknown,
): SamplesManifest['samples'][number]['confidence'] {
  if (value === 'HIGH' || value === 'MED' || value === 'LOW') return value;
  return 'MED';
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

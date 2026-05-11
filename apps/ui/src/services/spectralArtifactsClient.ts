import type {
  ChromaInteractiveData,
  OnsetStrengthData,
  SpectralArtifactRef,
  SpectralTimeSeriesData,
} from '../types';
import { buildConfiguredRequestInit } from '../config';
import { fetchJson } from './httpClient';

export function buildArtifactUrl(
  apiBaseUrl: string,
  runId: string,
  artifactId: string,
): string {
  return `${apiBaseUrl}/api/analysis-runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`;
}

export async function fetchArtifactImageObjectUrl(
  apiBaseUrl: string,
  runId: string,
  artifactId: string,
  init: RequestInit = {},
): Promise<{ url: string; revoke: () => void }> {
  const url = buildArtifactUrl(apiBaseUrl, runId, artifactId);
  const response = await fetch(url, buildConfiguredRequestInit(init));
  if (!response.ok) {
    throw new Error(`Failed to fetch artifact image: ${response.status}`);
  }

  const objectUrl = URL.createObjectURL(await response.blob());
  let revoked = false;

  return {
    url: objectUrl,
    revoke: () => {
      if (revoked) {
        return;
      }
      revoked = true;
      URL.revokeObjectURL(objectUrl);
    },
  };
}

export async function fetchSpectralTimeSeries(
  apiBaseUrl: string,
  runId: string,
  artifactId: string,
  options?: { signal?: AbortSignal },
): Promise<SpectralTimeSeriesData> {
  const url = buildArtifactUrl(apiBaseUrl, runId, artifactId);
  return fetchJson(url, { signal: options?.signal }) as Promise<SpectralTimeSeriesData>;
}

export type SpectralEnhancementKind = 'cqt' | 'hpss' | 'onset' | 'chroma_interactive';

export async function generateSpectralEnhancement(
  apiBaseUrl: string,
  runId: string,
  kind: SpectralEnhancementKind,
  options?: { signal?: AbortSignal },
): Promise<{ artifacts: SpectralArtifactRef[] }> {
  const url = `${apiBaseUrl}/api/analysis-runs/${encodeURIComponent(runId)}/spectral-enhancements/${encodeURIComponent(kind)}`;
  return fetchJson(url, { method: 'POST', signal: options?.signal }) as Promise<{ artifacts: SpectralArtifactRef[] }>;
}

export async function fetchOnsetStrengthData(
  apiBaseUrl: string,
  runId: string,
  artifactId: string,
  options?: { signal?: AbortSignal },
): Promise<OnsetStrengthData> {
  const url = buildArtifactUrl(apiBaseUrl, runId, artifactId);
  return fetchJson(url, { signal: options?.signal }) as Promise<OnsetStrengthData>;
}

export async function fetchChromaInteractiveData(
  apiBaseUrl: string,
  runId: string,
  artifactId: string,
  options?: { signal?: AbortSignal },
): Promise<ChromaInteractiveData> {
  const url = buildArtifactUrl(apiBaseUrl, runId, artifactId);
  return fetchJson(url, { signal: options?.signal }) as Promise<ChromaInteractiveData>;
}

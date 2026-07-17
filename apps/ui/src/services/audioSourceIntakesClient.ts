import { appConfig, buildConfiguredRequestInit } from '../config';
import { AnalysisRunSnapshot, BackendEstimateResponse } from '../types';
import { BackendClientError, createUserCancelledError } from './backendPhase1Client';
import { getAnalysisRun } from './analysisRunsClient';
import { fetchJson } from './httpClient';

export type AudioSourceIntakeStatus =
  | 'queued'
  | 'fetching'
  | 'normalizing'
  | 'ready'
  | 'completed'
  | 'failed'
  | 'interrupted'
  | 'expired';

export interface AudioSourceMetadata {
  title: string;
  creator: string | null;
  durationSeconds: number;
  attributionUrl: string | null;
  filename: string;
  mimeType: string;
  sizeBytes: number;
  experimental: boolean;
}

export interface AudioSourceIntake {
  intakeId: string;
  provider: string;
  status: AudioSourceIntakeStatus;
  rightsConfirmedAt: string;
  metadata: AudioSourceMetadata | null;
  error: { code?: string; message: string; retryable?: boolean } | null;
  expiresAt: string | null;
  runId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface AudioSourceProviderCapability {
  id: string;
  enabled: boolean;
  experimental: boolean;
  environments: string[];
  missingSetup: string[];
}

export interface AudioSourceCapabilities {
  limits: { maxBytes: number; maxDurationSeconds: number };
  providers: AudioSourceProviderCapability[];
}

export interface AudioSourceAnalysisOptions {
  analysisMode: 'full' | 'standard';
  pitchNoteMode: string;
  pitchNoteBackend: string;
  interpretationMode: string;
  interpretationProfile: string;
  interpretationModel?: string;
  mt3Mode: 'off' | 'enabled';
}

export async function getAudioSourceCapabilities(signal?: AbortSignal): Promise<AudioSourceCapabilities> {
  return (await fetchJson(`${appConfig.apiBaseUrl}/api/audio-source-capabilities`, {
    method: 'GET',
    signal,
  })) as AudioSourceCapabilities;
}

export async function createAudioSourceIntake(
  url: string,
  rightsConfirmed: boolean,
  signal?: AbortSignal,
): Promise<AudioSourceIntake> {
  return (await fetchJson(`${appConfig.apiBaseUrl}/api/audio-source-intakes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, rightsConfirmed }),
    signal,
  })) as AudioSourceIntake;
}

export async function getAudioSourceIntake(
  intakeId: string,
  signal?: AbortSignal,
): Promise<AudioSourceIntake> {
  return (await fetchJson(`${appConfig.apiBaseUrl}/api/audio-source-intakes/${intakeId}`, {
    method: 'GET',
    signal,
  })) as AudioSourceIntake;
}

export async function estimateAudioSourceIntake(
  intakeId: string,
  options: AudioSourceAnalysisOptions,
  signal?: AbortSignal,
): Promise<BackendEstimateResponse> {
  return (await fetchJson(`${appConfig.apiBaseUrl}/api/audio-source-intakes/${intakeId}/estimate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options),
    signal,
  })) as BackendEstimateResponse;
}

export async function createAnalysisRunFromIntake(
  intakeId: string,
  options: AudioSourceAnalysisOptions,
  signal?: AbortSignal,
): Promise<AnalysisRunSnapshot> {
  const response = (await fetchJson(
    `${appConfig.apiBaseUrl}/api/audio-source-intakes/${intakeId}/analysis-runs`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options),
      signal,
    },
  )) as { runId: string };
  return getAnalysisRun(response.runId, { apiBaseUrl: appConfig.apiBaseUrl, signal });
}

export async function interruptAudioSourceIntake(
  intakeId: string,
  signal?: AbortSignal,
): Promise<AudioSourceIntake> {
  return (await fetchJson(`${appConfig.apiBaseUrl}/api/audio-source-intakes/${intakeId}/interrupt`, {
    method: 'POST',
    signal,
  })) as AudioSourceIntake;
}

export async function fetchRunSourceAudio(runId: string, signal?: AbortSignal): Promise<File> {
  let response: Response;
  try {
    response = await fetch(
      `${appConfig.apiBaseUrl}/api/analysis-runs/${runId}/source-audio`,
      buildConfiguredRequestInit({ method: 'GET', signal }),
    );
  } catch (error) {
    if (signal?.aborted) throw createUserCancelledError();
    throw error;
  }
  if (!response.ok) {
    throw new BackendClientError('BACKEND_HTTP_ERROR', 'The prepared audio could not be loaded for playback.', {
      status: response.status,
      statusText: response.statusText,
    });
  }
  const blob = await response.blob();
  const disposition = response.headers.get('content-disposition') ?? '';
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plainName = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  const filename = encodedName ? decodeURIComponent(encodedName) : plainName ?? 'linked-audio';
  return new File([blob], filename, { type: blob.type || 'application/octet-stream' });
}

export async function waitForAudioSourceIntake(
  intakeId: string,
  onUpdate: (intake: AudioSourceIntake) => void,
  signal?: AbortSignal,
): Promise<AudioSourceIntake> {
  while (true) {
    if (signal?.aborted) throw createUserCancelledError();
    const intake = await getAudioSourceIntake(intakeId, signal);
    onUpdate(intake);
    if (['ready', 'completed'].includes(intake.status)) return intake;
    if (['failed', 'interrupted', 'expired'].includes(intake.status)) {
      throw new BackendClientError(
        'BACKEND_HTTP_ERROR',
        intake.error?.message ??
          (intake.status === 'expired'
            ? 'This checked link expired. Check the link again.'
            : 'The linked audio could not be prepared.'),
        { serverCode: intake.error?.code, retryable: intake.error?.retryable },
      );
    }
    await new Promise<void>((resolve, reject) => {
      const timer = globalThis.setTimeout(resolve, 700);
      signal?.addEventListener('abort', () => {
        globalThis.clearTimeout(timer);
        reject(createUserCancelledError());
      }, { once: true });
    });
  }
}

import { appConfig, buildConfiguredRequestInit } from '../config';
import { BackendClientError, createUserCancelledError } from './backendPhase1Client';

export async function fetchJson(url: string, init: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(url, buildConfiguredRequestInit(init));
  } catch (error) {
    if (init.signal?.aborted) {
      throw createUserCancelledError();
    }
    if (error instanceof TypeError) {
      throw new BackendClientError(
        'NETWORK_UNREACHABLE',
        appConfig.runtimeProfile === 'hosted'
          ? 'Cannot reach the ASA backend service. Confirm the hosted API URL and deployment are available.'
          : 'Cannot reach the local DSP backend. Confirm it is running and the API base URL is correct.',
        { cause: error },
      );
    }
    throw error instanceof Error ? error : new Error(String(error));
  }

  let payload: Record<string, unknown>;
  try {
    payload = (await response.json()) as Record<string, unknown>;
  } catch (error) {
    throw new BackendClientError(
      'BACKEND_BAD_RESPONSE',
      'Backend returned a non-JSON response.',
      {
        status: response.status,
        statusText: response.statusText,
        cause: error,
      },
    );
  }

  if (!response.ok) {
    const errorObj = asRecord(payload.error);
    throw new BackendClientError(
      'BACKEND_HTTP_ERROR',
      asString(errorObj?.message) ?? 'Request failed.',
      {
        status: response.status,
        statusText: response.statusText,
        serverCode: asString(errorObj?.code) ?? undefined,
        retryable: typeof errorObj?.retryable === 'boolean' ? errorObj.retryable : undefined,
      },
    );
  }

  return payload;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value == null || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null;
}

/**
 * Container around `TranscriptionPianoroll` that owns the fetch lifecycle.
 *
 * Designed to be mounted from `AnalysisResults` once `apiBaseUrl + runId` are
 * available *and* a transcription was requested for the run. The block does
 * its own gating: it shows a loading skeleton while the request is in flight,
 * a tone-down error notice on failure (with the backend error code so the
 * tester can correlate to the server error envelope), and the canvas heatmap
 * on success.
 *
 * The backend codes that surface here in practice:
 *   1. `TRANSCRIPTION_NOT_REQUESTED` — the parent shouldn't have rendered us
 *      in this case, but we handle it defensively so a partial render of the
 *      page doesn't crash.
 *   2. `TRANSCRIPTION_NOT_COMPLETED` — the stage hasn't finished. The parent
 *      can re-mount us when polling completes.
 *   3. `TRANSCRIPTION_NOT_AVAILABLE` — completed but empty / failed /
 *      interrupted. Caller's affordance is to retry transcription.
 */

import React, { useEffect, useState } from 'react';
import {
  fetchTranscriptionPianoroll,
  type TranscriptionPianorollOptions,
  type TranscriptionPianorollPayload,
} from '../services/transcriptionPianorollClient';
import { BackendClientError } from './../services/backendPhase1Client';
import { TranscriptionPianoroll } from './TranscriptionPianoroll';

interface Props {
  apiBaseUrl: string;
  runId: string;
  /** Pass-through options for `fetchTranscriptionPianoroll`. */
  options?: TranscriptionPianorollOptions;
}

type FetchState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string; code: string | null }
  | { kind: 'success'; payload: TranscriptionPianorollPayload };

export function TranscriptionPianorollBlock({ apiBaseUrl, runId, options }: Props) {
  const [state, setState] = useState<FetchState>({ kind: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: 'loading' });
    fetchTranscriptionPianoroll(apiBaseUrl, runId, {
      ...options,
      signal: controller.signal,
    })
      .then((payload) => {
        if (controller.signal.aborted) return;
        setState({ kind: 'success', payload });
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        if (error instanceof BackendClientError) {
          // `BackendClientError.details.serverCode` carries the structured
          // backend code (e.g. TRANSCRIPTION_NOT_COMPLETED) when the
          // response carried one.
          const serverCode =
            (error.details as { serverCode?: string } | undefined)?.serverCode ?? null;
          setState({ kind: 'error', message: error.message, code: serverCode });
        } else {
          setState({
            kind: 'error',
            message: error instanceof Error ? error.message : String(error),
            code: null,
          });
        }
      });
    return () => controller.abort();
  }, [apiBaseUrl, runId, options]);

  if (state.kind === 'loading') {
    return (
      <div className="space-y-2" data-testid="transcription-pianoroll-loading">
        <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
          Transcription Pianoroll · loading
        </span>
        <div className="rounded-sm border border-border bg-bg-panel h-[200px] animate-pulse" />
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="space-y-2" data-testid="transcription-pianoroll-error">
        <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
          Transcription Pianoroll
        </span>
        <div className="rounded-sm border border-border bg-bg-panel p-3 text-xs text-text-secondary">
          {state.message}
          {state.code !== null && (
            <span className="ml-2 opacity-60 font-mono">[{state.code}]</span>
          )}
        </div>
      </div>
    );
  }

  return <TranscriptionPianoroll payload={state.payload} />;
}

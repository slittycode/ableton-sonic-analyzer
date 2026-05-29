/**
 * MT3 polyphonic-transcription client helpers.
 *
 * The MT3 stage result (instrument list, note counts, pitch ranges) already
 * arrives inline on the analysis-run snapshot — `Mt3TranscriptionPanel` renders
 * it directly with no fetch. The only network call here is per-track MIDI
 * download: each `Mt3Track.midiArtifactId` references a persisted `.mid` blob in
 * the artifact store, fetched lazily on the user's click rather than bloating
 * every snapshot poll with 0.5-3 MB of base64 per track.
 *
 * Chain of custody: MT3 output is additive to Phase 1 (PURPOSE.md invariant
 * #1). This module only downloads bytes — it never reinterprets or overrides
 * any measured value.
 */
import { buildConfiguredRequestInit } from '../config';
import { buildArtifactUrl } from './spectralArtifactsClient';

/**
 * Build a friendly, filesystem-safe download filename for a track's MIDI.
 * Pure (no I/O) so it is unit-testable in the node Vitest env.
 */
export function buildMt3MidiFileName(instrument: string): string {
  const safe = instrument.trim().replace(/[^a-zA-Z0-9_-]+/g, '_').replace(/^_+|_+$/g, '');
  return `mt3-${safe || 'track'}.mid`;
}

/**
 * Fetch a track's MIDI artifact bytes as a Blob. Throws on a non-2xx response
 * so callers can surface the failure. Network-only (no DOM) — exercised by the
 * service test with a mocked `fetch`.
 */
export async function fetchMt3TrackMidiBlob(
  apiBaseUrl: string,
  runId: string,
  artifactId: string,
  init: RequestInit = {},
): Promise<Blob> {
  const url = buildArtifactUrl(apiBaseUrl, runId, artifactId);
  const response = await fetch(url, buildConfiguredRequestInit(init));
  if (!response.ok) {
    throw new Error(`Failed to fetch MT3 MIDI artifact: ${response.status}`);
  }
  return response.blob();
}

/**
 * Fetch a track's MIDI artifact and trigger a browser download via a transient
 * anchor element. DOM-dependent, so it is intentionally NOT covered by the
 * node-env service test (tripwire #5: no `document`/`window` in tests/services);
 * the fetch half is covered through `fetchMt3TrackMidiBlob`. Mirrors the
 * anchor-download pattern in `services/midi/midiExport.ts`.
 */
export async function downloadMt3TrackMidi(
  apiBaseUrl: string,
  runId: string,
  artifactId: string,
  instrument: string,
  init: RequestInit = {},
): Promise<void> {
  const blob = await fetchMt3TrackMidiBlob(apiBaseUrl, runId, artifactId, init);
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = buildMt3MidiFileName(instrument);
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(objectUrl);
}

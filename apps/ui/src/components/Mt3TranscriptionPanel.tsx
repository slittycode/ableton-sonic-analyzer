// Renders the optional MT3 polyphonic-transcription stage result.
//
// MT3 (Magenta Multi-Task Multitrack) produces per-instrument MIDI from the
// Demucs stems (or full mix). This panel is purely additive: it sits beside the
// Session Musician / Stem Notes suite and never restates or overrides any
// Phase 1 measurement (PURPOSE.md invariant #1) — hence the BEST EFFORT badge,
// matching <StemListeningNotesPanel>.
//
// The stage metadata (instruments, note counts, pitch ranges) arrives inline on
// the run snapshot and is projected onto `phase1.transcription.mt3`; this panel
// reads it directly. The MIDI bytes themselves are fetched lazily per track on
// the user's Download click via `mt3Client.downloadMt3TrackMidi` — they are too
// large to inline on every snapshot poll.
//
// As with sibling panels, the StickyNav anchor ID (`section-mt3`) lives on the
// wrapper <div> in AnalysisResults, not here — this component carries only the
// test ID.

import React, { useState } from 'react';
import type { Mt3Track, Mt3Transcription } from '../types';
import { Button, DataTable, type DataTableColumn } from './ui';
import { downloadMt3TrackMidi } from '../services/mt3Client';
import { midiToNoteName } from '../services/sessionMusician';
import {
  formatDisplayText,
  getTextRoleClassName,
  type TextRole,
} from '../utils/displayText';

function textRoleClassName(role: TextRole, className = ''): string {
  return [getTextRoleClassName(role), className].filter(Boolean).join(' ');
}

function formatKb(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '—';
  return `${(bytes / 1024).toFixed(1)} KB`;
}

function pitchRangeLabel(track: Mt3Track): string {
  if (track.noteCount <= 0) return '—';
  const [lo, hi] = track.pitchRange;
  return lo === hi ? midiToNoteName(lo) : `${midiToNoteName(lo)}–${midiToNoteName(hi)}`;
}

interface Mt3TranscriptionPanelProps {
  result: Mt3Transcription;
  apiBaseUrl: string;
  runId: string;
}

export function Mt3TranscriptionPanel({
  result,
  apiBaseUrl,
  runId,
}: Mt3TranscriptionPanelProps) {
  const [downloadingArtifactId, setDownloadingArtifactId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const tracks = Array.isArray(result.tracks) ? result.tracks : [];
  // Defensive: the parent gates on a non-null result, but an empty track list
  // carries no usable MIDI — render nothing rather than an empty table.
  if (tracks.length === 0) return null;

  const stemsUsed = Array.isArray(result.stemsUsed) ? result.stemsUsed : [];
  const totalNotes = tracks.reduce((sum, track) => sum + (track.noteCount || 0), 0);

  async function handleDownload(track: Mt3Track): Promise<void> {
    if (!track.midiArtifactId) return;
    setError(null);
    setDownloadingArtifactId(track.midiArtifactId);
    try {
      await downloadMt3TrackMidi(apiBaseUrl, runId, track.midiArtifactId, track.instrument);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDownloadingArtifactId(null);
    }
  }

  const columns: DataTableColumn<Mt3Track>[] = [
    { key: 'instrument', label: 'Instrument', displayCase: 'title' },
    {
      key: 'noteCount',
      label: 'Notes',
      align: 'right',
      monospace: true,
      render: (track) => track.noteCount.toLocaleString(),
    },
    {
      key: 'pitchRange',
      label: 'Pitch Range',
      align: 'right',
      monospace: true,
      render: pitchRangeLabel,
    },
    {
      key: 'midiSizeBytes',
      label: 'Size',
      align: 'right',
      monospace: true,
      render: (track) => formatKb(track.midiSizeBytes),
    },
    {
      key: 'download',
      label: 'MIDI',
      align: 'right',
      render: (track) => (
        <Button
          variant="secondary"
          size="sm"
          disabled={!track.midiArtifactId || downloadingArtifactId === track.midiArtifactId}
          onClick={() => handleDownload(track)}
          data-testid={`mt3-download-${track.instrument}`}
        >
          {downloadingArtifactId === track.midiArtifactId
            ? 'Downloading…'
            : track.midiArtifactId
              ? 'Download .mid'
              : 'No MIDI'}
        </Button>
      ),
    },
  ];

  return (
    <section data-testid="mt3-transcription-panel" className="space-y-4">
      <div className="flex items-center justify-between gap-3 border-b border-border pb-2">
        <h2
          data-text-role="section-title"
          className={textRoleClassName('section-title', 'flex items-center gap-2')}
        >
          <span className="w-2 h-2 bg-accent rounded-full flex-shrink-0" />
          {formatDisplayText('MT3 polyphonic transcription', 'title')}
        </h2>
        <span className="text-meta font-mono bg-bg-panel border border-accent/30 text-accent px-2 py-1 rounded font-bold">
          BEST EFFORT
        </span>
      </div>

      <p className={textRoleClassName('body', 'text-text-secondary')}>
        Per-instrument MIDI extracted by MT3 from{' '}
        {stemsUsed.length > 0 ? (
          <>the {formatDisplayText(stemsUsed.join(', '), 'none')} stem{stemsUsed.length > 1 ? 's' : ''}</>
        ) : (
          'the full mix'
        )}
        . {totalNotes.toLocaleString()} notes across {tracks.length} track
        {tracks.length > 1 ? 's' : ''}. This is an additive starting point for a
        rebuild — it never overrides the Phase 1 key, chords, or beat grid.
      </p>

      <DataTable<Mt3Track> data={tracks} columns={columns} />

      {error && (
        <p
          data-testid="mt3-download-error"
          className={textRoleClassName('meta', 'text-error')}
        >
          MIDI download failed: {error}
        </p>
      )}

      {result.version && (
        <p className={textRoleClassName('meta', 'text-text-muted font-mono')}>
          {formatDisplayText('Checkpoint', 'eyebrow')}: {result.version}
        </p>
      )}
    </section>
  );
}

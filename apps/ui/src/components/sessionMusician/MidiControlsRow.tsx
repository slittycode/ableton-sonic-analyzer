// Inline Preview + Download buttons for a single Session Musician block.
//
// The component reads its play/stop state from the shared PreviewController
// (created once in SessionMusicianPanel) so that pressing Preview on one
// block automatically stops the other. It does NOT call usePreviewController
// internally.

import React, { useCallback } from 'react';
import { Download, Play, Square } from 'lucide-react';
import { downloadMidiFile } from '../../services/midi/midiExport';
import type { MidiDisplayNote } from '../../services/midi/types';
import type { PreviewController, PreviewId } from './usePreviewController';

interface MidiControlsRowProps {
  notes: MidiDisplayNote[];
  bpm: number;
  previewId: PreviewId;
  previewLabel: string;
  downloadLabel: string;
  downloadFilename: string;
  controller: PreviewController;
  /** Hides the Download button entirely (used when we have no notes to export). */
  hideDownload?: boolean;
  /** Hint shown on hover. */
  downloadTitle?: string;
  /** Optional aria-label override for the Download button. */
  downloadAriaLabel?: string;
}

export function MidiControlsRow({
  notes,
  bpm,
  previewId,
  previewLabel,
  downloadLabel,
  downloadFilename,
  controller,
  hideDownload = false,
  downloadTitle,
  downloadAriaLabel,
}: MidiControlsRowProps) {
  const hasNotes = notes.length > 0;
  const isThisActive = controller.activePreviewId === previewId;
  const disabled = !hasNotes;

  const handlePreview = useCallback(() => {
    if (isThisActive) {
      controller.stop();
      return;
    }
    controller.start(previewId, notes);
  }, [controller, isThisActive, notes, previewId]);

  const handleDownload = useCallback(() => {
    if (!notes.length) return;
    downloadMidiFile(notes, bpm, downloadFilename);
  }, [bpm, downloadFilename, notes]);

  const previewTestId = `midi-preview-${previewId}`;
  const downloadTestId = `midi-download-${previewId}`;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={handlePreview}
        disabled={disabled}
        data-testid={previewTestId}
        title={isThisActive ? `Stop ${previewLabel.toLowerCase()}` : previewLabel}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-accent/10 border border-accent/40 text-accent text-xs font-mono uppercase rounded-sm disabled:opacity-40 disabled:cursor-not-allowed hover:bg-accent/20 transition-colors"
      >
        {isThisActive ? <Square className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
        {isThisActive ? 'Stop' : previewLabel}
      </button>
      {!hideDownload && (
        <button
          type="button"
          onClick={handleDownload}
          disabled={disabled}
          data-testid={downloadTestId}
          title={downloadTitle ?? downloadLabel}
          aria-label={downloadAriaLabel ?? downloadLabel}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-bg-panel border border-border text-text-primary text-xs font-mono uppercase rounded-sm disabled:opacity-40 disabled:cursor-not-allowed hover:bg-bg-card transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          {downloadLabel}
        </button>
      )}
    </div>
  );
}

// Single shared MIDI preview controller for the Session Musician panel.
//
// One remote control, not two: the hook is called ONCE in SessionMusicianPanel
// and the returned PreviewController is passed down to both MidiControlsRow
// instances (stems + melody). Starting a preview on one block automatically
// stops the other; closing the panel or unmounting tears everything down.

import { useCallback, useEffect, useRef, useState } from 'react';
import { previewNotes, type PreviewHandle } from '../../services/midi/midiPreview';
import type { MidiDisplayNote } from '../../services/midi/types';

export type PreviewId = 'stems' | 'melody';

export interface PreviewController {
  activePreviewId: PreviewId | null;
  isPlaying: boolean;
  start(id: PreviewId, notes: MidiDisplayNote[], onEnd?: () => void): void;
  stop(): void;
}

export function usePreviewController(): PreviewController {
  const handleRef = useRef<PreviewHandle | null>(null);
  const [activePreviewId, setActivePreviewId] = useState<PreviewId | null>(null);

  const stop = useCallback(() => {
    handleRef.current?.stop();
    handleRef.current = null;
    setActivePreviewId(null);
  }, []);

  const start = useCallback(
    (id: PreviewId, notes: MidiDisplayNote[], onEnd?: () => void) => {
      // Always stop the previous preview before starting a new one. This is
      // what prevents two simultaneous previews from playing if the user
      // clicks Block B while Block A is still playing.
      handleRef.current?.stop();
      handleRef.current = null;

      if (!notes.length) {
        setActivePreviewId(null);
        return;
      }

      const handle = previewNotes(notes, () => {
        handleRef.current = null;
        setActivePreviewId(null);
        onEnd?.();
      });
      handleRef.current = handle;
      setActivePreviewId(id);
    },
    [],
  );

  // Tear down on unmount so an in-progress preview doesn't leak past the panel.
  useEffect(() => {
    return () => {
      handleRef.current?.stop();
      handleRef.current = null;
    };
  }, []);

  return {
    activePreviewId,
    isPlaying: activePreviewId !== null,
    start,
    stop,
  };
}

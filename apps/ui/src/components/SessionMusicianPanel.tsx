// Session Musician panel — orchestrates two stacked pitch reads (Block A:
// stem-aware note draft, Block B: measurement-layer melody contour) plus the
// off-state banner. The actual content rendering lives in the block
// components in ./sessionMusician/; this file owns the panel shell, the
// shared preview controller, and the off-state copy.

import React, { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, Music2 } from 'lucide-react';
import { Phase1Result, TranscriptionDetail } from '../types';
import { getTextRoleClassName } from '../utils/displayText';
import { Button, DeviceRack, EmptyState } from './ui';
import { MelodyContourBlock } from './sessionMusician/MelodyContourBlock';
import { NoteDraftBlock } from './sessionMusician/NoteDraftBlock';
import {
  deriveNoteDraftRenderState,
  isLegacyTranscriptionMethod,
  type PitchNoteMode,
} from '../services/sessionMusician/renderState';
import { usePreviewController } from './sessionMusician/usePreviewController';
import type { MidiDisplayNote } from '../services/midi/types';

// ---------------------------------------------------------------------------
// Backwards-compatible exports.
//
// These helpers were exported from the old panel; tests and external callers
// still import them. The values and behaviour are preserved exactly — only
// the panel implementation around them has been re-organised.
// ---------------------------------------------------------------------------

export const MIDI_DOWNLOAD_FILE_NAME = 'track-analysis.mid';

export function filterNotesByConfidence(
  notes: MidiDisplayNote[],
  confidenceThreshold: number,
): MidiDisplayNote[] {
  return notes.filter((note) => note.confidence >= confidenceThreshold);
}

export function formatFilteredNoteCount(
  filteredCount: number,
  totalCount: number,
  confidenceThreshold: number,
): string {
  if (confidenceThreshold <= 0) {
    return `${totalCount} NOTES`;
  }
  return `${filteredCount} / ${totalCount} NOTES`;
}

export function formatVibratoConfidence(confidence: number, vibratoPresent: boolean): string {
  const rounded = Math.round(confidence * 100);
  if (vibratoPresent && rounded === 0) {
    return '< 1';
  }
  return String(rounded);
}

type LegacySessionMusicianSource = 'pitchNote' | 'melodyGuide' | 'optedOut' | 'none';

export function deriveTranscriptionProvenance(
  activeSource: LegacySessionMusicianSource | string,
  transcriptionDetail: TranscriptionDetail | null | undefined,
): { transcriptionPathLabel: string | null; stemSourcesLabel: string | null } {
  if (activeSource !== 'pitchNote' || !transcriptionDetail) {
    return { transcriptionPathLabel: null, stemSourcesLabel: null };
  }
  return {
    transcriptionPathLabel: transcriptionDetail.stemSeparationUsed ? 'STEM-AWARE' : 'FULL MIX',
    stemSourcesLabel:
      transcriptionDetail.stemSeparationUsed && transcriptionDetail.stemsTranscribed.length
        ? transcriptionDetail.stemsTranscribed.join(', ')
        : null,
  };
}

// Re-exports so existing imports (e.g. tests) can grab everything from the
// panel module path.
export { deriveNoteDraftRenderState, isLegacyTranscriptionMethod };

// ---------------------------------------------------------------------------
// Off-state banner copy
// ---------------------------------------------------------------------------

const OFF_BANNER_WITH_MELODY =
  "Stem pitch/note translation is off. You're seeing the measurement-layer melody contour below. Re-enable the Stem Pitch/Note Translation toggle in the request panel to attempt a stem-aware note draft. The stem listening notes below still describe each stem in plain language when interpretation runs.";

const OFF_BANNER_NO_MELODY_WITH_LISTENING =
  'Session Musician is off. You still get BPM, key, structure, and Phase 2 device recommendations. The measurement-layer melody contour appears when available. Re-enable the Stem Pitch/Note Translation toggle to attempt a stem-aware note draft. The stem listening notes below describe each stem in plain language.';

const OFF_BANNER_NO_MELODY_NO_LISTENING =
  'Session Musician is off. You still get BPM, key, structure, and Phase 2 device recommendations. The measurement-layer melody contour appears when available. Re-enable the Stem Pitch/Note Translation toggle to attempt a stem-aware note draft.';

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

interface SessionMusicianPanelProps {
  phase1: Phase1Result;
  sourceFileName?: string | null;
  pitchNoteMode?: PitchNoteMode;
  /** Set by AnalysisResults when the Gemini stem listening notes section will render. */
  hasStemListeningNotes?: boolean;
  /**
   * Optional callback for the "Re-analyze with stem-aware pipeline" button
   * that NoteDraftBlock renders only in the `legacy` render state. App owns
   * the run-creation primitives; passing `undefined` hides the button.
   */
  onReanalyzeWithStemAware?: () => void;
}

export function SessionMusicianPanel({
  phase1,
  pitchNoteMode = null,
  hasStemListeningNotes = false,
  onReanalyzeWithStemAware,
}: SessionMusicianPanelProps) {
  const melodyDetail = phase1.melodyDetail ?? null;
  const transcriptionDetail = phase1.transcriptionDetail ?? null;
  const [expanded, setExpanded] = useState(true);
  const controller = usePreviewController();

  const isOptedOut = pitchNoteMode === 'off';

  const renderState = useMemo(
    () => deriveNoteDraftRenderState(transcriptionDetail, pitchNoteMode),
    [transcriptionDetail, pitchNoteMode],
  );

  const hasMelodyNotes = (melodyDetail?.notes?.length ?? 0) > 0;
  const showNoteDraftBlock = renderState !== 'absent';
  const showMelodyBlock = !!melodyDetail;

  const offBannerCopy = useMemo(() => {
    if (!isOptedOut) return null;
    if (hasMelodyNotes) return OFF_BANNER_WITH_MELODY;
    if (hasStemListeningNotes) return OFF_BANNER_NO_MELODY_WITH_LISTENING;
    return OFF_BANNER_NO_MELODY_NO_LISTENING;
  }, [hasMelodyNotes, hasStemListeningNotes, isOptedOut]);

  const panelSummary = useMemo(() => {
    if (isOptedOut) {
      return 'Pitch/note translation is off';
    }
    if (showNoteDraftBlock && showMelodyBlock) {
      return 'Two reads of the pitched material in this track. Use either, neither, or both.';
    }
    if (showNoteDraftBlock) {
      return "Stem-aware note draft. Designed for cleanup in Ableton's piano roll, not as exact note truth.";
    }
    if (showMelodyBlock) {
      return 'Measurement-layer melody contour. Tracks the loudest pitched line across the full mix.';
    }
    return 'No pitched material detected. Check the stem listening notes below.';
  }, [isOptedOut, showMelodyBlock, showNoteDraftBlock]);

  return (
    // <section> wrapper preserves the semantic element that smoke
    // selectors target (upload-phase1-midi.spec.ts:631 uses
    // `page.locator('section').filter({ hasText: /SESSION MUSICIAN/i })`).
    // DeviceRack itself renders a <div>; without this wrapper the smoke
    // locator finds nothing and the panel reads as missing.
    <section
      data-testid="session-musician-panel"
      aria-label="Session Musician"
    >
    <DeviceRack
      name="Session Musician"
      subtitle="· Pitch & Melody"
      status="idle"
      className="space-y-0"
      action={
        <Button
          variant="ghost"
          iconOnly
          size="sm"
          onClick={() => setExpanded((prev) => !prev)}
          aria-label={expanded ? 'Collapse session musician panel' : 'Expand session musician panel'}
          title={expanded ? 'Collapse' : 'Expand'}
        >
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </Button>
      }
    >
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-full border border-accent/30 bg-accent/10">
            <Music2 className="w-4 h-4 text-accent" />
          </div>
          <p
            data-text-role="body"
            className={[getTextRoleClassName('body'), 'opacity-80'].join(' ')}
          >
            {panelSummary}
          </p>
        </div>

        {offBannerCopy && (
          <EmptyState
            data-testid="session-musician-off-banner"
            tone="warning"
            padding="sm"
            title="Pitch/note translation is off"
            description={offBannerCopy}
            className="border-accent/20 bg-bg-panel"
          />
        )}

        {expanded && (
          <>
            {showNoteDraftBlock && (
              <NoteDraftBlock
                transcriptionDetail={transcriptionDetail}
                pitchNoteMode={pitchNoteMode}
                controller={controller}
                bpm={phase1.bpm}
                trackDurationSeconds={phase1.durationSeconds}
                onReanalyzeWithStemAware={onReanalyzeWithStemAware}
              />
            )}
            {showMelodyBlock && (
              <MelodyContourBlock
                melodyDetail={melodyDetail}
                controller={controller}
                bpm={phase1.bpm}
                trackDurationSeconds={phase1.durationSeconds}
              />
            )}
            {!showNoteDraftBlock && !showMelodyBlock && !offBannerCopy && (
              <EmptyState
                data-testid="session-musician-no-data"
                tone="neutral"
                padding="sm"
                title="PITCH & MELODY UNAVAILABLE"
                description="Neither stem-aware transcription nor a measurement-layer melody contour were produced for this run. Check the stem listening notes if interpretation ran."
              />
            )}
          </>
        )}
      </div>
    </DeviceRack>
    </section>
  );
}

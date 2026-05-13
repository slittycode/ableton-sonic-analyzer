// Block B — Melody contour.
//
// Renders the measurement-layer Essentia melody when available. Has only two
// content-bearing render states (present / ran-with-no-result), no confidence
// slider (per-note confidence isn't available from PredominantPitchMelodia),
// and a separate MIDI filename so Ableton drag-and-drop is unambiguous.

import React, { useMemo, useState } from 'react';
import type { MelodyDetail } from '../../types';
import type { QuantizeOptions } from '../../services/midi/types';
import { quantizeNotes } from '../../services/midi/quantization';
import { melodyNotesToDisplayNotes } from '../../services/sessionMusician/noteConversion';
import { ConfidenceBandBadge } from './ConfidenceBandBadge';
import { MidiControlsRow } from './MidiControlsRow';
import { PianoRollCanvas } from './PianoRollCanvas';
import { QuantizeControls } from './QuantizeControls';
import type { PreviewController } from './usePreviewController';

export const MIDI_DOWNLOAD_FILE_NAME_MELODY = 'track-analysis-melody.mid';

const PIANO_ROLL_HEIGHT_MELODY = 180;

const SUBTITLE =
  'The loudest pitched line in the full mix. Usually the vocal or lead synth, but it can drift between instruments without warning.';

const RAN_WITH_NO_RESULT_NOTICE =
  "Melody extraction ran but didn't find a pitched line. This is normal for purely percussive tracks.";

function formatVibratoConfidencePercent(confidence: number, present: boolean): string {
  const rounded = Math.round(confidence * 100);
  if (present && rounded === 0) return '< 1';
  return String(rounded);
}

interface MelodyContourBlockProps {
  melodyDetail: MelodyDetail | null | undefined;
  controller: PreviewController;
  bpm: number;
  trackDurationSeconds: number;
}

export function MelodyContourBlock({
  melodyDetail,
  controller,
  bpm,
  trackDurationSeconds,
}: MelodyContourBlockProps) {
  const [quantize, setQuantize] = useState<QuantizeOptions>({ grid: 'off', swing: 0 });

  const displayNotesSource = useMemo(
    () => melodyNotesToDisplayNotes(melodyDetail),
    [melodyDetail],
  );

  const displayNotes = useMemo(
    () => quantizeNotes(displayNotesSource, bpm || 120, quantize),
    [bpm, displayNotesSource, quantize],
  );

  if (!melodyDetail) return null;

  const hasNotes = (melodyDetail.notes?.length ?? 0) > 0;

  const headerBlock = (
    <div className="space-y-1">
      <h3 className="text-xs font-mono uppercase tracking-wide text-text-primary">
        Melody contour
      </h3>
      <p className="text-[11px] font-mono text-text-secondary/90 leading-relaxed">{SUBTITLE}</p>
    </div>
  );

  if (!hasNotes) {
    return (
      <section
        data-testid="melody-contour-block"
        data-render-state="ran-with-no-result"
        className="space-y-3 rounded-sm border border-border bg-bg-panel/30 p-4"
      >
        {headerBlock}
        <p className="text-[11px] font-mono text-text-secondary leading-relaxed">
          {RAN_WITH_NO_RESULT_NOTICE}
        </p>
      </section>
    );
  }

  const piano =
    trackDurationSeconds && trackDurationSeconds > 0
      ? trackDurationSeconds
      : Math.max(
          1,
          ...displayNotes.map((note) => note.startTime + note.duration),
          1,
        );

  const noteCount = melodyDetail.notes.length;
  const rangeText =
    typeof melodyDetail.pitchRange?.min === 'number' &&
    typeof melodyDetail.pitchRange?.max === 'number'
      ? `${melodyDetail.pitchRange.min} – ${melodyDetail.pitchRange.max}`
      : 'n/a';

  const vibratoLabel = melodyDetail.vibratoPresent
    ? `present (${melodyDetail.vibratoRate.toFixed(1)} Hz / ${melodyDetail.vibratoExtent.toFixed(2)} cents / ${formatVibratoConfidencePercent(melodyDetail.vibratoConfidence, true)}%)`
    : `not detected (${Math.round(melodyDetail.vibratoConfidence * 100)}%)`;

  return (
    <section
      data-testid="melody-contour-block"
      data-render-state="present"
      className="space-y-3 rounded-sm border border-border bg-bg-panel/30 p-4"
    >
      {headerBlock}

      <ConfidenceBandBadge
        confidence={melodyDetail.pitchConfidence}
        testId="melody-contour-band"
      />

      <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono uppercase tracking-wide text-text-secondary">
        <span>{noteCount} NOTES</span>
        <span className="opacity-50">|</span>
        <span>MIDI range: {rangeText}</span>
        <span className="opacity-50">|</span>
        <span>ESSENTIA MELODY</span>
        <span className="opacity-50">|</span>
        <span>{melodyDetail.sourceSeparated ? 'SOURCE-SEPARATED' : 'FULL MIX'}</span>
      </div>

      <PianoRollCanvas
        notes={displayNotes}
        duration={piano}
        height={PIANO_ROLL_HEIGHT_MELODY}
        testId="melody-contour-piano-roll"
      />

      <QuantizeControls value={quantize} onChange={setQuantize} />

      <MidiControlsRow
        notes={displayNotes}
        bpm={bpm}
        previewId="melody"
        previewLabel="Preview melody"
        downloadLabel="Download melody .mid"
        downloadFilename={MIDI_DOWNLOAD_FILE_NAME_MELODY}
        controller={controller}
      />

      <div className="rounded-sm border border-border/60 bg-bg-card p-3 space-y-1">
        <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
          Melody metadata
        </p>
        <p className="text-[11px] font-mono text-text-secondary leading-relaxed">
          Melody MIDI: {melodyDetail.midiFile ? 'available' : 'none'} · Vibrato: {vibratoLabel}
        </p>
      </div>
    </section>
  );
}

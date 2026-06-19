// Block A — Stem note draft.
//
// One component, six render states; the state matrix is driven by
// deriveNoteDraftRenderState(). Each render state has its own header subtitle,
// optional notice copy, and decides whether the piano roll, stem filter,
// confidence slider, and Download button appear. See the plan in
// .claude/plans/re-evaluate-asa-s-session-musician-* and the explanatory copy
// at the top of services/sessionMusician/renderState.ts for the load-bearing
// precedence rules.

import React, { useMemo, useState } from 'react';
import { RotateCw } from 'lucide-react';
import type { TranscriptionDetail } from '../../types';
import type { QuantizeOptions } from '../../services/midi/types';
import { quantizeNotes } from '../../services/midi/quantization';
import {
  deriveNoteDraftRenderState,
  selectNoteDraftBandConfidence,
  type NoteDraftRenderState,
  type PitchNoteMode,
} from '../../services/sessionMusician/renderState';
import { transcriptionNotesToDisplayNotes } from '../../services/sessionMusician/noteConversion';
import { ConfidenceBandBadge } from './ConfidenceBandBadge';
import { MidiControlsRow } from './MidiControlsRow';
import { PianoRollCanvas } from './PianoRollCanvas';
import { QuantizeControls } from './QuantizeControls';
import type { PreviewController } from './usePreviewController';

export const MIDI_DOWNLOAD_FILE_NAME_STEMS = 'track-analysis-stems.mid';

const DEFAULT_CONFIDENCE_THRESHOLD = 0.2;

const SUBTITLE_BY_STATE: Record<NoteDraftRenderState, string> = {
  'stem-aware': 'Bass and lead, transcribed from Demucs-separated stems.',
  'full-mix-fallback': "Full-mix fallback — stem separation didn't run cleanly.",
  legacy: 'Legacy run — produced before the current torchcrepe pipeline.',
  'ran-with-no-result': "Ran but didn't find a pitched line.",
  'requested-but-unavailable':
    "Requested, but the stage didn't produce output.",
  absent: '',
};

const NOTICE_BY_STATE: Partial<Record<NoteDraftRenderState, string>> = {
  'full-mix-fallback':
    'Pitch was tracked across the entire mix instead of stems, so notes drift between instruments. Treat the pitch range and most-frequent notes as scale hints. The piano roll below is approximate.',
  legacy:
    'Re-analyze for current stem-aware quality. The notes below are kept for archival. Pitch range and most-played notes are still informative.',
  'ran-with-no-result':
    "Pitch/note translation ran but didn't find a pitched line in the stems. Check the stem listening notes below for what the stems actually contain.",
  'requested-but-unavailable':
    'Stem note draft was requested but the pitch/note translation stage produced no output. The stage may have failed or the audio may not have a pitched line in the stems. Check the stem listening notes below, or re-run.',
};

const STAYS_USEFUL_HEADLINE =
  'Even at low confidence, these signals stay useful:';
const STAYS_USEFUL_DETAIL =
  'Pitch range tells you how to set up your MIDI track and synth range. The most-played notes hint at the scale to play along in. Note durations are still a rhythmic grid.';

function formatPitchNoteMethodLabel(method: string | null | undefined): string {
  const normalized = (method ?? '').trim().toLowerCase();
  if (normalized === 'torchcrepe-viterbi' || normalized === 'torchcrepe') {
    return 'TORCHCREPE';
  }
  if (
    normalized === 'basic-pitch' ||
    normalized === 'basic_pitch' ||
    normalized === 'basic-pitch-legacy'
  ) {
    return 'BASIC PITCH (LEGACY)';
  }
  if (!normalized) return 'PITCH/NOTE EXTRACTION';
  return (method ?? '').replace(/[_-]+/g, ' ').toUpperCase();
}

function averageNoteDuration(transcription: TranscriptionDetail): string {
  const total = transcription.notes.reduce((sum, note) => sum + note.durationSeconds, 0);
  if (transcription.notes.length === 0) return '0.00s';
  return `${(total / transcription.notes.length).toFixed(2)}s`;
}

interface NoteDraftBlockProps {
  transcriptionDetail: TranscriptionDetail | null | undefined;
  pitchNoteMode: PitchNoteMode;
  controller: PreviewController;
  bpm: number;
  /** Used to scale the piano-roll x-axis; defaults to last-note-end when missing. */
  trackDurationSeconds: number;
  /**
   * When set AND the render state is `legacy`, the block renders a button
   * that re-runs analysis on the current source file with the stem-aware
   * torchcrepe pipeline forced on. Hidden in all other render states.
   */
  onReanalyzeWithStemAware?: () => void;
}

export function NoteDraftBlock({
  transcriptionDetail,
  pitchNoteMode,
  controller,
  bpm,
  trackDurationSeconds,
  onReanalyzeWithStemAware,
}: NoteDraftBlockProps) {
  const renderState = useMemo(
    () => deriveNoteDraftRenderState(transcriptionDetail, pitchNoteMode),
    [transcriptionDetail, pitchNoteMode],
  );

  const [stemFilter, setStemFilter] = useState<string | null>(null);
  const [confidenceThreshold, setConfidenceThreshold] = useState(DEFAULT_CONFIDENCE_THRESHOLD);
  const [quantize, setQuantize] = useState<QuantizeOptions>({ grid: 'off', swing: 0 });

  const sourceNotes = useMemo(
    () => transcriptionNotesToDisplayNotes(transcriptionDetail, stemFilter),
    [stemFilter, transcriptionDetail],
  );

  // Confidence slider only applies in stem-aware mode; otherwise pass through.
  const filteredNotes = useMemo(() => {
    if (renderState !== 'stem-aware') return sourceNotes;
    return sourceNotes.filter((note) => note.confidence >= confidenceThreshold);
  }, [confidenceThreshold, renderState, sourceNotes]);

  const displayNotes = useMemo(
    () => quantizeNotes(filteredNotes, bpm || 120, quantize),
    [bpm, filteredNotes, quantize],
  );

  if (renderState === 'absent') return null;

  const subtitle = SUBTITLE_BY_STATE[renderState];
  const notice = NOTICE_BY_STATE[renderState];
  const headerBlock = (
    <div className="space-y-1">
      <h3 className="text-xs font-mono uppercase tracking-wide text-text-primary">
        Stem note draft
      </h3>
      {subtitle && (
        <p className="text-eyebrow font-mono text-text-secondary/90 leading-relaxed">
          {subtitle}
        </p>
      )}
    </div>
  );

  // Non-content states: render header + notice only.
  if (renderState === 'requested-but-unavailable' || renderState === 'ran-with-no-result') {
    return (
      <section
        data-testid="note-draft-block"
        data-render-state={renderState}
        className="space-y-3 rounded-sm border border-border bg-bg-panel/30 p-4"
      >
        {headerBlock}
        {notice && (
          <p className="text-eyebrow font-mono text-text-secondary leading-relaxed">{notice}</p>
        )}
      </section>
    );
  }

  // From here on we know transcriptionDetail is populated with at least one note.
  if (!transcriptionDetail) return null;

  const filteredCount = displayNotes.length;
  const sourceCount = sourceNotes.length;
  const showFilterRatio = renderState === 'stem-aware' && confidenceThreshold > 0;
  const countLabel = showFilterRatio
    ? `${filteredCount} / ${sourceCount} NOTES`
    : `${sourceCount} NOTES`;

  const methodLabel = formatPitchNoteMethodLabel(transcriptionDetail.transcriptionMethod);
  const dominantNames = transcriptionDetail.dominantPitches
    .map((entry) => entry.pitchName)
    .slice(0, 4);
  const rangeText =
    transcriptionDetail.pitchRange.minName && transcriptionDetail.pitchRange.maxName
      ? `${transcriptionDetail.pitchRange.minName} – ${transcriptionDetail.pitchRange.maxName}`
      : 'n/a';
  const avgLength = averageNoteDuration(transcriptionDetail);

  const piano = trackDurationSeconds && trackDurationSeconds > 0 ? trackDurationSeconds : Math.max(
    1,
    ...displayNotes.map((note) => note.startTime + note.duration),
    1,
  );

  const isOverride = renderState === 'full-mix-fallback' || renderState === 'legacy';
  const bandOverrideLabel =
    renderState === 'full-mix-fallback'
      ? 'Full-mix fallback'
      : renderState === 'legacy'
        ? 'Legacy run'
        : undefined;
  const bandOverrideCopy = isOverride ? (notice ?? null) : undefined;
  const bandOverrideTone = isOverride ? ('rough' as const) : undefined;

  // Per-stem band confidence selection — see services/sessionMusician/renderState.ts
  // for the precedence and fallback rules.
  const bandConfidence = selectNoteDraftBandConfidence(
    transcriptionDetail,
    stemFilter,
    renderState,
  );

  // Slider filtered everything out — keep the piano roll rendered (it shows
  // "no notes" gracefully) but hide the Download since there's nothing to ship.
  const sliderEmptiedNotes =
    renderState === 'stem-aware' && sourceCount > 0 && filteredCount === 0;

  return (
    <section
      data-testid="note-draft-block"
      data-render-state={renderState}
      className="space-y-3 rounded-sm border border-border bg-bg-panel/30 p-4"
    >
      {headerBlock}

      <ConfidenceBandBadge
        confidence={bandConfidence}
        overrideLabel={bandOverrideLabel ?? null}
        overrideCopy={bandOverrideCopy ?? null}
        overrideTone={bandOverrideTone}
        testId="note-draft-band"
      />

      {renderState === 'legacy' && onReanalyzeWithStemAware && (
        <button
          type="button"
          onClick={onReanalyzeWithStemAware}
          data-testid="note-draft-reanalyze"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-accent/10 border border-accent/40 text-accent text-xs font-mono uppercase rounded-sm hover:bg-accent/20 transition-colors w-fit"
        >
          <RotateCw className="w-3.5 h-3.5" />
          Re-analyze with stem-aware pipeline
        </button>
      )}

      <div className="flex flex-wrap items-center gap-2 text-meta font-mono uppercase tracking-wide text-text-secondary">
        <span>{countLabel}</span>
        <span className="opacity-50">|</span>
        <span>Range: {rangeText}</span>
        <span className="opacity-50">|</span>
        <span>{methodLabel}</span>
        <span className="opacity-50">|</span>
        <span>
          {transcriptionDetail.stemSeparationUsed && !transcriptionDetail.fullMixFallback
            ? 'STEM-AWARE'
            : 'FULL MIX'}
        </span>
      </div>

      {renderState === 'stem-aware' && transcriptionDetail.stemsTranscribed.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap">
          <span className="text-meta font-mono uppercase text-text-secondary mr-1">Stems:</span>
          {transcriptionDetail.stemsTranscribed.map((stem) => (
            <button
              key={stem}
              type="button"
              onClick={() => setStemFilter((prev) => (prev === stem ? null : stem))}
              className={`px-2 py-1 rounded border text-meta font-mono uppercase transition-colors ${
                stemFilter === stem
                  ? 'border-accent text-accent bg-accent/10'
                  : 'border-border bg-bg-panel/40 text-text-secondary hover:text-text-primary'
              }`}
            >
              {stem}
            </button>
          ))}
          {stemFilter && (
            <button
              type="button"
              onClick={() => setStemFilter(null)}
              className="px-2 py-1 rounded border border-border bg-bg-panel/40 text-meta font-mono uppercase text-text-secondary hover:text-text-primary transition-colors"
            >
              All
            </button>
          )}
        </div>
      )}

      <PianoRollCanvas notes={displayNotes} duration={piano} testId="note-draft-piano-roll" />

      {renderState === 'stem-aware' && (
        <div
          className="flex items-center gap-2 px-2 py-1 rounded border border-border bg-bg-card w-fit"
          title="Drag to hide notes below this per-note confidence"
        >
          <span className="text-meta font-mono uppercase text-text-secondary">Confidence</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={confidenceThreshold}
            onChange={(event) => setConfidenceThreshold(Number(event.target.value))}
            className="w-24 h-1 accent-accent"
          />
          <span className="text-meta font-mono text-text-secondary w-8 text-right">
            {Math.round(confidenceThreshold * 100)}%
          </span>
        </div>
      )}

      {sliderEmptiedNotes && (
        <p className="text-eyebrow font-mono text-warning/90 leading-relaxed">
          Confidence slider filtered every note. Lower the threshold to see and export anything.
        </p>
      )}

      <QuantizeControls value={quantize} onChange={setQuantize} />

      <MidiControlsRow
        notes={displayNotes}
        bpm={bpm}
        previewId="stems"
        previewLabel="Preview"
        downloadLabel="Download .mid"
        downloadFilename={MIDI_DOWNLOAD_FILE_NAME_STEMS}
        controller={controller}
        hideDownload={sliderEmptiedNotes}
      />

      <div className="rounded-sm border border-border/60 bg-bg-card p-3 space-y-2">
        <p className="text-meta font-mono uppercase tracking-wide text-text-secondary">
          {STAYS_USEFUL_HEADLINE}
        </p>
        <p className="text-eyebrow font-mono text-text-secondary leading-relaxed">
          {STAYS_USEFUL_DETAIL}
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          <span className="px-2 py-1 rounded-sm border border-border text-meta font-mono text-text-primary bg-bg-panel/40">
            Range: {rangeText}
          </span>
          {dominantNames.length > 0 && (
            <span className="px-2 py-1 rounded-sm border border-border text-meta font-mono text-text-primary bg-bg-panel/40">
              Most-played: {dominantNames.join(', ')}
            </span>
          )}
          <span className="px-2 py-1 rounded-sm border border-border text-meta font-mono text-text-primary bg-bg-panel/40">
            Avg note length: {avgLength}
          </span>
        </div>
      </div>
    </section>
  );
}

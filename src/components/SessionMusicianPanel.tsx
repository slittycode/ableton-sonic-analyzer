import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Download,
  Grid3X3,
  Info,
  Music2,
  Play,
  SlidersHorizontal,
  Square,
} from 'lucide-react';
import { Phase1Result } from '../types';
import { downloadMidiFile } from '../services/midi/midiExport';
import { previewNotes, PreviewHandle } from '../services/midi/midiPreview';
import { gridLabel, quantizeNotes } from '../services/midi/quantization';
import { MidiDisplayNote, QuantizeGrid, QuantizeOptions } from '../services/midi/types';

const GRID_OPTIONS: QuantizeGrid[] = ['off', '1/4', '1/8', '1/16', '1/32'];
const PIANO_ROLL_HEIGHT = 240;
const KEY_WIDTH = 40;
export const MIDI_DOWNLOAD_FILE_NAME = 'track-analysis.mid';

const NOTE_COLORS = {
  fill: '#ff9500',
  fillHigh: '#ffb14d',
  fillLow: '#664526',
  stroke: '#e67e22',
  grid: '#262626',
  text: '#9ca3af',
  bg: '#101010',
};

export function filterNotesByConfidence(notes: MidiDisplayNote[], confidenceThreshold: number): MidiDisplayNote[] {
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

function midiToNoteName(midi: number): string {
  const names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const;
  const clamped = Math.max(0, Math.min(127, Math.round(midi)));
  const octave = Math.floor(clamped / 12) - 1;
  return `${names[clamped % 12]}${octave}`;
}

function drawPianoRoll(canvas: HTMLCanvasElement, notes: MidiDisplayNote[], duration: number) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const width = rect.width;
  const height = rect.height;

  ctx.fillStyle = NOTE_COLORS.bg;
  ctx.fillRect(0, 0, width, height);

  if (!notes.length) {
    ctx.fillStyle = NOTE_COLORS.text;
    ctx.font = '12px ui-monospace, monospace';
    ctx.textAlign = 'center';
    ctx.fillText('No notes detected', width / 2, height / 2);
    return;
  }

  const midiValues = notes.map((note) => note.midi);
  const minMidi = Math.max(0, Math.min(...midiValues) - 2);
  const maxMidi = Math.min(127, Math.max(...midiValues) + 2);
  const range = Math.max(1, maxMidi - minMidi);
  const plotX = KEY_WIDTH;
  const plotWidth = width - KEY_WIDTH;
  const noteHeight = Math.max(3, height / range);

  ctx.font = '9px ui-monospace, monospace';
  ctx.textAlign = 'right';
  for (let midi = minMidi; midi <= maxMidi; midi += 1) {
    const y = height - ((midi - minMidi) / range) * height;
    ctx.strokeStyle = midi % 12 === 0 ? '#424242' : NOTE_COLORS.grid;
    ctx.lineWidth = midi % 12 === 0 ? 1 : 0.5;
    ctx.beginPath();
    ctx.moveTo(plotX, y);
    ctx.lineTo(width, y);
    ctx.stroke();

    if (midi % 12 === 0 || range <= 24) {
      ctx.fillStyle = NOTE_COLORS.text;
      ctx.fillText(midiToNoteName(midi), KEY_WIDTH - 4, y + 3);
    }
  }

  const secondsStep = duration > 30 ? 5 : duration > 10 ? 2 : 1;
  for (let sec = 0; sec <= duration; sec += secondsStep) {
    const x = plotX + (sec / duration) * plotWidth;
    ctx.strokeStyle = NOTE_COLORS.grid;
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();

    ctx.fillStyle = '#5f5f5f';
    ctx.font = '8px ui-monospace, monospace';
    ctx.textAlign = 'center';
    ctx.fillText(`${sec}s`, x, height - 2);
  }

  for (const note of notes) {
    const x = plotX + (note.startTime / duration) * plotWidth;
    const widthPx = Math.max(2, (note.duration / duration) * plotWidth);
    const y = height - ((note.midi - minMidi) / range) * height - noteHeight / 2;

    const alpha = 0.4 + note.confidence * 0.6;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = note.confidence > 0.7 ? NOTE_COLORS.fillHigh : note.confidence > 0.3 ? NOTE_COLORS.fill : NOTE_COLORS.fillLow;
    ctx.fillRect(x, y, widthPx, Math.max(2, noteHeight - 1));

    ctx.globalAlpha = 1;
    ctx.strokeStyle = NOTE_COLORS.stroke;
    ctx.lineWidth = 0.5;
    ctx.strokeRect(x, y, widthPx, Math.max(2, noteHeight - 1));
  }
}

interface SessionMusicianPanelProps {
  phase1: Phase1Result;
  sourceFileName?: string | null;
}

export function SessionMusicianPanel({ phase1, sourceFileName }: SessionMusicianPanelProps) {
  const melodyDetail = phase1.melodyDetail;
  const transcriptionDetail = phase1.transcriptionDetail ?? null;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const previewRef = useRef<PreviewHandle | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [sourceMode, setSourceMode] = useState<"polyphonic" | "monophonic">("polyphonic");
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.2);
  const [quantizeOptions, setQuantizeOptions] = useState<QuantizeOptions>({ grid: 'off', swing: 0 });
  const hasTranscription = !!transcriptionDetail?.noteCount && transcriptionDetail.noteCount > 0;
  const hasMelody = !!melodyDetail?.notes?.length;
  const canToggle = hasTranscription && hasMelody;
  const activeSource = canToggle
    ? sourceMode
    : hasTranscription
      ? 'polyphonic'
      : hasMelody
        ? 'monophonic'
        : 'none';

  const activeNotes = useMemo<MidiDisplayNote[]>(() => {
    if (activeSource === 'polyphonic' && transcriptionDetail?.notes?.length) {
      return transcriptionDetail.notes.map((note) => ({
        midi: note.pitchMidi,
        name: note.pitchName,
        startTime: note.onsetSeconds,
        duration: note.durationSeconds,
        velocity: 90,
        confidence: note.confidence,
      }));
    }

    if (activeSource === 'monophonic' && melodyDetail?.notes?.length) {
      return melodyDetail.notes.map((note) => ({
        midi: note.midi,
        name: midiToNoteName(note.midi),
        startTime: note.onset,
        duration: note.duration,
        velocity: 90,
        confidence: melodyDetail.pitchConfidence,
      }));
    }

    return [];
  }, [activeSource, melodyDetail, transcriptionDetail]);

  const filteredNotes = useMemo(
    () => filterNotesByConfidence(activeNotes, confidenceThreshold),
    [activeNotes, confidenceThreshold],
  );

  const displayNotes = useMemo(
    () => quantizeNotes(filteredNotes, phase1.bpm || 120, quantizeOptions),
    [filteredNotes, phase1.bpm, quantizeOptions],
  );

  const duration = useMemo(() => {
    if (!displayNotes.length) return Math.max(1, phase1.durationSeconds || 1);
    return Math.max(...displayNotes.map((note) => note.startTime + note.duration), phase1.durationSeconds || 1, 1);
  }, [displayNotes, phase1.durationSeconds]);

  useEffect(() => {
    if (!canvasRef.current || activeSource === 'none' || !expanded) return;
    drawPianoRoll(canvasRef.current, displayNotes, duration);
  }, [activeSource, displayNotes, duration, expanded]);

  useEffect(() => {
    if (!canvasRef.current || activeSource === 'none' || !expanded) return;
    const canvas = canvasRef.current;
    const observer = new ResizeObserver(() => {
      drawPianoRoll(canvas, displayNotes, duration);
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [activeSource, displayNotes, duration, expanded]);

  useEffect(() => () => previewRef.current?.stop(), []);

  const handlePreview = useCallback(() => {
    if (isPreviewing) {
      previewRef.current?.stop();
      previewRef.current = null;
      setIsPreviewing(false);
      return;
    }

    if (!displayNotes.length) return;

    const handle = previewNotes(displayNotes, () => {
      setIsPreviewing(false);
      previewRef.current = null;
    });
    previewRef.current = handle;
    setIsPreviewing(true);
  }, [displayNotes, isPreviewing]);

  const handleDownload = useCallback(() => {
    if (!displayNotes.length) return;
    downloadMidiFile(displayNotes, phase1.bpm, MIDI_DOWNLOAD_FILE_NAME);
  }, [displayNotes, phase1.bpm]);

  const stats = useMemo(() => {
    if (activeSource === 'none' || !activeNotes.length) return null;
    const midiValues = displayNotes.map((note) => note.midi);
    const minMidi = midiValues.length ? Math.min(...midiValues) : null;
    const maxMidi = midiValues.length ? Math.max(...midiValues) : null;
    const avgConfidence = Math.round(
      (activeSource === 'polyphonic'
        ? transcriptionDetail?.averageConfidence ?? 0
        : melodyDetail?.pitchConfidence ?? 0) * 100,
    );
    const totalDuration = displayNotes.reduce((sum, note) => sum + note.duration, 0).toFixed(1);

    return {
      countLabel: formatFilteredNoteCount(displayNotes.length, activeNotes.length, confidenceThreshold),
      range: minMidi === null || maxMidi === null ? 'n/a' : `${midiToNoteName(minMidi)} - ${midiToNoteName(maxMidi)}`,
      avgConfidence,
      totalDuration,
    };
  }, [activeNotes.length, activeSource, confidenceThreshold, displayNotes, melodyDetail, transcriptionDetail]);
  const hasSourceNotes = activeNotes.length > 0;
  const hasNotes = displayNotes.length > 0;
  const confidenceThresholdPercent = Math.round(confidenceThreshold * 100);
  const dominantNoteNames =
    activeSource === 'polyphonic'
      ? transcriptionDetail?.dominantPitches.map((note) => note.pitchName) ?? []
      : melodyDetail?.dominantNotes.map((note) => midiToNoteName(note)) ?? [];
  const rangeLabel =
    activeSource === 'polyphonic'
      ? transcriptionDetail?.pitchRange.minName && transcriptionDetail?.pitchRange.maxName
        ? `${transcriptionDetail.pitchRange.minName} - ${transcriptionDetail.pitchRange.maxName}`
        : 'n/a'
      : melodyDetail?.pitchRange.min === null || melodyDetail?.pitchRange.max === null || !melodyDetail?.pitchRange
        ? 'n/a'
        : `${midiToNoteName(melodyDetail.pitchRange.min)} - ${midiToNoteName(melodyDetail.pitchRange.max)}`;
  const confidencePercent =
    activeSource === 'polyphonic'
      ? Math.round((transcriptionDetail?.averageConfidence ?? 0) * 100)
      : activeSource === 'monophonic'
        ? Math.round((melodyDetail?.pitchConfidence ?? 0) * 100)
        : 0;
  const isDraft =
    activeSource === 'polyphonic'
      ? (transcriptionDetail?.averageConfidence ?? 0) < 0.15
      : activeSource === 'monophonic'
        ? (melodyDetail?.pitchConfidence ?? 0) < 0.15
        : false;
  const sourceBadgeLabel =
    activeSource === 'polyphonic'
      ? 'SOURCES: BASIC PITCH'
      : activeSource === 'monophonic'
        ? 'SOURCES: ESSENTIA'
        : null;
  const transcriptionPathLabel = transcriptionDetail
    ? transcriptionDetail.stemSeparationUsed
      ? 'STEM-AWARE'
      : 'FULL MIX'
    : null;
  const stemSourcesLabel =
    transcriptionDetail?.stemSeparationUsed && transcriptionDetail.stemsTranscribed.length
      ? transcriptionDetail.stemsTranscribed.join(', ')
      : null;

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between border-b border-border pb-2">
        <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
          <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
          SESSION MUSICIAN
        </h2>
        <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">MIDI TRANSCRIPTION</span>
      </div>

      <div className="bg-bg-card border border-border rounded-sm p-4 space-y-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-full border border-accent/30 bg-accent/10">
              <Music2 className="w-4 h-4 text-accent" />
            </div>
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wider">SESSION MUSICIAN</h3>
              <p className="text-[10px] font-mono uppercase tracking-widest text-text-secondary opacity-70">
                Audio to MIDI transcription
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handlePreview}
              disabled={!displayNotes.length}
              title={isPreviewing ? 'Stop preview' : 'Preview MIDI'}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-accent/10 border border-accent/40 text-accent text-xs font-mono uppercase rounded-sm disabled:opacity-40 disabled:cursor-not-allowed hover:bg-accent/20 transition-colors"
            >
              {isPreviewing ? <Square className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
              {isPreviewing ? 'Stop' : 'Preview'}
            </button>
            <button
              onClick={handleDownload}
              disabled={!displayNotes.length}
              title="Download .mid file"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-bg-panel border border-border text-text-primary text-xs font-mono uppercase rounded-sm disabled:opacity-40 disabled:cursor-not-allowed hover:bg-bg-card transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              Download .mid
            </button>
            {canToggle && (
              <div className="inline-flex items-center rounded-sm border border-border bg-bg-panel/40 p-0.5">
                <button
                  onClick={() => setSourceMode('polyphonic')}
                  className={`px-2 py-1 rounded-sm text-[10px] font-mono uppercase transition-colors ${
                    activeSource === 'polyphonic'
                      ? 'bg-accent text-bg-app'
                      : 'text-text-secondary hover:text-text-primary'
                  }`}
                >
                  POLYPHONIC
                </button>
                <button
                  onClick={() => setSourceMode('monophonic')}
                  className={`px-2 py-1 rounded-sm text-[10px] font-mono uppercase transition-colors ${
                    activeSource === 'monophonic'
                      ? 'bg-accent text-bg-app'
                      : 'text-text-secondary hover:text-text-primary'
                  }`}
                >
                  MONOPHONIC
                </button>
              </div>
            )}
            <button
              onClick={() => setExpanded((prev) => !prev)}
              aria-label={expanded ? 'Collapse session musician panel' : 'Expand session musician panel'}
              title={expanded ? 'Collapse' : 'Expand'}
              className="p-1.5 text-text-secondary hover:text-text-primary transition-colors"
            >
              {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {expanded && (
          <>
            {activeSource === 'none' && (
              <div className="border border-border rounded-sm px-3 py-2 bg-bg-panel/40 space-y-1">
                <p className="text-[11px] font-mono text-text-secondary uppercase tracking-wide">
                  MIDI TRANSCRIPTION UNAVAILABLE
                </p>
                <p className="text-[10px] font-mono text-text-secondary/80">
                  Run with --transcribe flag for Basic Pitch polyphonic transcription, or ensure melodyDetail is present in DSP JSON
                </p>
              </div>
            )}

            {activeSource !== 'none' && (
              <>
                {stats && (
                  <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                    <span>{stats.countLabel}</span>
                    <span className="opacity-50">|</span>
                    <span>Range: {stats.range}</span>
                    <span className="opacity-50">|</span>
                    <span>Confidence: {stats.avgConfidence}%</span>
                    <span className="opacity-50">|</span>
                    <span>Duration: {stats.totalDuration}s</span>
                    {sourceBadgeLabel && (
                      <>
                        <span className="opacity-50">|</span>
                        <span>{sourceBadgeLabel}</span>
                      </>
                    )}
                  </div>
                )}

                {transcriptionPathLabel && (
                  <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                    <span
                      className={`px-2 py-1 rounded border ${
                        transcriptionDetail?.stemSeparationUsed
                          ? 'border-accent/40 text-accent bg-accent/10'
                          : 'border-border bg-bg-panel/40'
                      }`}
                    >
                      {transcriptionPathLabel}
                    </span>
                    {stemSourcesLabel && (
                      <span className="px-2 py-1 rounded border border-border bg-bg-panel/40">
                        STEMS: {stemSourcesLabel}
                      </span>
                    )}
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                  {!stats && (
                    <span className="px-2 py-1 rounded border border-border bg-bg-panel/40">
                      {activeSource === 'polyphonic' ? transcriptionDetail?.noteCount ?? 0 : melodyDetail?.noteCount ?? 0} notes
                    </span>
                  )}
                  <span className="px-2 py-1 rounded border border-border bg-bg-panel/40">Range: {rangeLabel}</span>
                  <span className="px-2 py-1 rounded border border-border bg-bg-panel/40">Confidence: {confidencePercent}%</span>
                  {sourceBadgeLabel && (
                    <span className="px-2 py-1 rounded border border-border bg-bg-panel/40">{sourceBadgeLabel}</span>
                  )}
                  {isDraft && (
                    <span className="px-2 py-1 rounded border border-yellow-500/30 text-yellow-400 bg-yellow-500/10">
                      Draft transcription
                    </span>
                  )}
                </div>

                {dominantNoteNames.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {dominantNoteNames.map((name, idx) => (
                      <span
                        key={`${name}-${idx}`}
                        className="px-2 py-1 rounded-sm border border-border text-[10px] font-mono text-text-primary bg-bg-panel/40"
                      >
                        {name}
                      </span>
                    ))}
                  </div>
                )}

                <div className="rounded-sm border border-border overflow-hidden">
                  <canvas ref={canvasRef} className="w-full" style={{ height: PIANO_ROLL_HEIGHT }} />
                </div>
              </>
            )}

            <div className="flex flex-wrap items-center gap-4 p-3 border border-border rounded-sm bg-bg-panel/40">
              <div className="flex items-center gap-2">
                <Grid3X3 className="w-3.5 h-3.5 text-text-secondary" />
                <span className="text-[10px] font-mono uppercase text-text-secondary">Quantize</span>
              </div>

              <div className="flex items-center gap-1">
                {GRID_OPTIONS.map((grid) => (
                  <button
                    key={grid}
                    onClick={() => setQuantizeOptions((prev) => ({ ...prev, grid }))}
                    disabled={!hasNotes}
                    className={`px-2 py-1 text-[10px] font-mono rounded border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                      quantizeOptions.grid === grid
                        ? 'border-accent text-accent bg-accent/10'
                        : 'border-border text-text-secondary bg-bg-card hover:bg-bg-panel'
                    }`}
                  >
                    {gridLabel(grid)}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-2 px-2 py-1 rounded border border-border bg-bg-card">
                <span className="text-[10px] font-mono uppercase text-text-secondary">CONFIDENCE</span>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={confidenceThreshold}
                  onChange={(event) => setConfidenceThreshold(Number(event.target.value))}
                  disabled={!hasSourceNotes}
                  className="w-20 h-1 accent-accent disabled:opacity-30"
                />
                <span className="text-[10px] font-mono text-text-secondary w-8 text-right">{confidenceThresholdPercent}%</span>
              </div>

              <div className="flex items-center gap-2 ml-auto">
                <SlidersHorizontal className="w-3.5 h-3.5 text-text-secondary" />
                <span className="text-[10px] font-mono uppercase text-text-secondary">Swing</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={quantizeOptions.swing}
                  onChange={(event) =>
                    setQuantizeOptions((prev) => ({
                      ...prev,
                      swing: Number(event.target.value),
                    }))
                  }
                  disabled={quantizeOptions.grid === 'off' || !hasNotes}
                  className="w-20 h-1 accent-accent disabled:opacity-30"
                />
                <span className="text-[10px] font-mono text-text-secondary w-8 text-right">{quantizeOptions.swing}%</span>
              </div>
            </div>

            <div className="flex items-start gap-2 text-[10px] font-mono text-text-secondary/80">
              <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span title="Session musician transcription details">
                {activeSource === 'polyphonic'
                  ? 'Polyphonic transcription via Basic Pitch. Adjust quantize before preview/export. Adjust confidence threshold to filter noise before export.'
                  : activeSource === 'monophonic'
                    ? 'Monophonic pitch detection via Essentia. Adjust quantize before preview/export. Adjust confidence threshold to filter noise before export.'
                    : 'MIDI transcription unavailable until transcriptionDetail or melodyDetail is present in the DSP payload.'}
                {isDraft ? ' Confidence is low, so treat this clip as a draft scaffold.' : ''}
              </span>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

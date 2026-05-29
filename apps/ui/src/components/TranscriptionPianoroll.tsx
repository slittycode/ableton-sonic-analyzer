/**
 * Canvas heatmap of a transcription pianoroll matrix.
 *
 * Pure renderer: takes a `TranscriptionPianorollPayload` (rows × cols of
 * velocity values) and paints a pitch × time grid. No fetching here — the
 * `TranscriptionPianorollBlock` container owns the request lifecycle.
 *
 * Visual conventions mirror `ChromaHeatmap`:
 *   1. Black background, pitch labels on the left, time flowing left → right.
 *   2. Lowest pitch (`pitchLow`) at the bottom — matches Ableton's piano roll.
 *   3. dpr-scaled canvas + ResizeObserver redraw.
 *
 * Velocity ramps from a dim cyan (the confidence floor, velocity 64) up to a
 * bright yellow (velocity 127). Below 64 should be impossible in practice —
 * the backend module floors at 64 — but is treated as "show, slightly dimmer"
 * rather than dropped so unusual upstream data is still visible.
 */

import React, { useCallback, useEffect, useRef } from 'react';
import type { TranscriptionPianorollPayload } from '../services/transcriptionPianorollClient';

interface Props {
  payload: TranscriptionPianorollPayload;
}

const LABEL_WIDTH = 32;
const MIN_CANVAS_HEIGHT = 200;
const PIXELS_PER_PITCH_ROW = 3;
const PITCH_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const;

function midiToPitchName(midi: number): string {
  const clamped = Math.max(0, Math.min(127, Math.round(midi)));
  return `${PITCH_NAMES[clamped % 12]}${Math.floor(clamped / 12) - 1}`;
}

function velocityToColor(v: number): string {
  if (v <= 0) return '#09090b';
  // Map [64, 127] onto cyan → yellow. Below 64 (impossible in practice) gets a
  // dim grey rather than the cyan endpoint so an out-of-spec value is visually
  // distinct.
  if (v < 64) return `hsl(220, 15%, ${15 + (v / 64) * 15}%)`;
  const t = (v - 64) / (127 - 64);
  const hue = 200 - t * 140;
  const sat = 70 + t * 25;
  const light = 28 + t * 38;
  return `hsl(${hue}, ${sat}%, ${light}%)`;
}

export function TranscriptionPianoroll({ payload }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;
    const pitchCount = payload.pitchHigh - payload.pitchLow;
    const timeSteps = payload.frames[0]?.length ?? 0;
    const plotX = LABEL_WIDTH;
    const plotW = w - LABEL_WIDTH;

    ctx.fillStyle = '#09090b';
    ctx.fillRect(0, 0, w, h);

    if (pitchCount <= 0 || timeSteps === 0 || payload.noteCount === 0) {
      ctx.fillStyle = '#52525b';
      ctx.font = '11px ui-monospace, monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('No notes transcribed', w / 2, h / 2);
      return;
    }

    const cellW = plotW / timeSteps;
    const cellH = h / pitchCount;

    // Lowest pitch (pitchLow) at the bottom — Ableton convention.
    for (let row = 0; row < pitchCount; row++) {
      const rowY = h - (row + 1) * cellH;
      const cells = payload.frames[row];
      if (!cells) continue;
      for (let col = 0; col < timeSteps; col++) {
        const v = cells[col];
        if (v <= 0) continue;
        ctx.fillStyle = velocityToColor(v);
        ctx.fillRect(
          plotX + col * cellW,
          rowY,
          Math.ceil(cellW) + 1,
          Math.ceil(cellH) + 1,
        );
      }
    }

    // Pitch labels — every octave only, to avoid clutter at the default 88-row
    // height.
    ctx.font = '9px ui-monospace, monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#71717a';
    for (let row = 0; row < pitchCount; row++) {
      const midi = payload.pitchLow + row;
      if (midi % 12 !== 0) continue;
      const rowY = h - (row + 1) * cellH + cellH / 2;
      ctx.fillText(midiToPitchName(midi), LABEL_WIDTH - 4, rowY);
    }
  }, [payload]);

  useEffect(() => {
    draw();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver(() => draw());
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [draw]);

  const pitchCount = Math.max(1, payload.pitchHigh - payload.pitchLow);
  const canvasHeight = Math.max(pitchCount * PIXELS_PER_PITCH_ROW, MIN_CANVAS_HEIGHT);

  const citationParts: string[] = [
    `${payload.mode} mode`,
    `${payload.noteCount} ${payload.noteCount === 1 ? 'note' : 'notes'}`,
  ];
  if (payload.quartersPerMinute !== null) {
    citationParts.push(`${Math.round(payload.quartersPerMinute)} BPM`);
  }
  if (payload.timeSignature !== null) {
    citationParts.push(payload.timeSignature);
  }
  const citation = citationParts.join(' · ');

  return (
    <div className="space-y-2" data-testid="transcription-pianoroll">
      <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
        Transcription Pianoroll · {citation}
      </span>
      <div className="rounded-sm overflow-hidden border border-border bg-bg-panel">
        <canvas
          ref={canvasRef}
          className="w-full"
          style={{ height: canvasHeight }}
          aria-label={`Transcription pianoroll, ${citation}.`}
        />
      </div>
    </div>
  );
}

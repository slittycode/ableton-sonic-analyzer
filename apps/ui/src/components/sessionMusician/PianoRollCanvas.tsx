// Presentational piano-roll renderer shared by the two Session Musician blocks.
// Owns the canvas, the ResizeObserver, and the drawing logic — but no note
// data, no quantize, no MIDI export. It just paints what it's given.

import React, { useEffect, useRef } from 'react';
import type { MidiDisplayNote } from '../../services/midi/types';
import { midiToNoteName } from '../../services/sessionMusician/noteConversion';

const NOTE_COLORS = {
  fill: '#ff8800',
  fillHigh: '#ffb14d',
  fillLow: '#664526',
  stroke: '#e67e22',
  grid: '#262626',
  text: '#9ca3af',
  bg: '#101010',
};

const KEY_WIDTH = 40;
const DEFAULT_HEIGHT = 240;

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
    ctx.fillStyle =
      note.confidence > 0.7
        ? NOTE_COLORS.fillHigh
        : note.confidence > 0.3
          ? NOTE_COLORS.fill
          : NOTE_COLORS.fillLow;
    ctx.fillRect(x, y, widthPx, Math.max(2, noteHeight - 1));

    ctx.globalAlpha = 1;
    ctx.strokeStyle = NOTE_COLORS.stroke;
    ctx.lineWidth = 0.5;
    ctx.strokeRect(x, y, widthPx, Math.max(2, noteHeight - 1));
  }
}

interface PianoRollCanvasProps {
  notes: MidiDisplayNote[];
  duration: number;
  height?: number;
  testId?: string;
}

export function PianoRollCanvas({
  notes,
  duration,
  height = DEFAULT_HEIGHT,
  testId,
}: PianoRollCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!canvasRef.current) return;
    drawPianoRoll(canvasRef.current, notes, duration);
  }, [notes, duration]);

  useEffect(() => {
    if (!canvasRef.current) return;
    const canvas = canvasRef.current;
    const observer = new ResizeObserver(() => {
      drawPianoRoll(canvas, notes, duration);
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [notes, duration]);

  return (
    <div className="rounded-sm border border-border overflow-hidden">
      <canvas
        ref={canvasRef}
        role="img"
        aria-label="Piano roll of detected notes"
        data-testid={testId}
        className="w-full"
        style={{ height }}
      />
    </div>
  );
}

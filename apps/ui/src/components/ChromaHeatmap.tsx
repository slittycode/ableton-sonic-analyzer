import React, { useCallback, useEffect, useRef } from 'react';
import type { ChromaInteractiveData } from '../types';
import { dbToColor } from '../utils/colorScales';
import { useSpectralCursor } from '../hooks/useSpectralCursorBus';

interface ChromaHeatmapProps {
  data: ChromaInteractiveData;
}

const LABEL_WIDTH = 28;
const ROW_HEIGHT = 18;

export function ChromaHeatmap({ data }: ChromaHeatmapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tooltipRef = useRef<{ x: number; col: number } | null>(null);
  const { publish, subscribe } = useSpectralCursor('chroma-heatmap');

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
    const numBands = data.pitchClasses.length;
    const numPoints = data.timePoints.length;
    const plotX = LABEL_WIDTH;
    const plotW = w - LABEL_WIDTH;

    ctx.fillStyle = '#09090b';
    ctx.fillRect(0, 0, w, h);

    if (numPoints === 0 || numBands === 0) return;

    const cellW = plotW / numPoints;
    const cellH = h / numBands;

    // Draw heatmap cells (pitch class 0 = C at bottom)
    for (let b = 0; b < numBands; b++) {
      const rowY = h - (b + 1) * cellH;
      const row = data.chroma[b];
      for (let p = 0; p < numPoints; p++) {
        ctx.fillStyle = dbToColor(row[p]);
        ctx.fillRect(plotX + p * cellW, rowY, Math.ceil(cellW) + 1, Math.ceil(cellH) + 1);
      }
    }

    // Pitch labels
    ctx.font = '9px ui-monospace, monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#71717a';
    for (let b = 0; b < numBands; b++) {
      const rowY = h - (b + 1) * cellH + cellH / 2;
      ctx.fillText(data.pitchClasses[b], LABEL_WIDTH - 4, rowY);
    }

    // Time axis
    const duration = data.timePoints[numPoints - 1] ?? 0;
    if (duration > 0) {
      const timeStep = duration > 120 ? 30 : duration > 60 ? 15 : duration > 20 ? 5 : 2;
      ctx.font = '8px ui-monospace, monospace';
      ctx.textAlign = 'center';
      ctx.fillStyle = '#52525b';
      for (let t = 0; t <= duration; t += timeStep) {
        const x = plotX + (t / duration) * plotW;
        const mins = Math.floor(t / 60);
        const secs = Math.floor(t % 60);
        ctx.fillText(`${mins}:${secs.toString().padStart(2, '0')}`, x, h - 2);
      }
    }

    // Hover cursor
    const tip = tooltipRef.current;
    if (tip && tip.col >= 0 && tip.col < numPoints) {
      const hoverX = plotX + (tip.col + 0.5) * cellW;
      ctx.strokeStyle = 'rgba(255,255,255,0.3)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(hoverX, 0);
      ctx.lineTo(hoverX, h);
      ctx.stroke();

      // Tooltip
      const time = data.timePoints[tip.col];
      const mins = Math.floor(time / 60);
      const secs = Math.floor(time % 60);
      const maxPitch = data.chroma.reduce(
        (best, row, i) => (row[tip.col] > best.val ? { val: row[tip.col], idx: i } : best),
        { val: -1, idx: 0 },
      );
      const label = `${mins}:${secs.toString().padStart(2, '0')} · ${data.pitchClasses[maxPitch.idx]} ${maxPitch.val.toFixed(2)}`;
      const textW = ctx.measureText(label).width + 8;
      const tooltipX = Math.min(hoverX + 4, w - textW - 4);
      ctx.fillStyle = 'rgba(0,0,0,0.75)';
      ctx.fillRect(tooltipX, 6, textW, 16);
      ctx.fillStyle = '#e4e4e7';
      ctx.font = '9px ui-monospace, monospace';
      ctx.textAlign = 'left';
      ctx.fillText(label, tooltipX + 4, 17);
    }
  }, [data]);

  useEffect(() => {
    draw();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver(() => draw());
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [draw]);

  // Subscribe to external cursor events from sibling visualizations
  useEffect(() => {
    return subscribe((time) => {
      if (time === null) {
        tooltipRef.current = null;
      } else {
        // Find nearest column index via binary search
        const pts = data.timePoints;
        let lo = 0;
        let hi = pts.length - 1;
        while (lo < hi) {
          const mid = (lo + hi) >> 1;
          if (pts[mid] < time) lo = mid + 1;
          else hi = mid;
        }
        // Check if lo-1 is closer
        const col =
          lo > 0 && Math.abs(pts[lo - 1] - time) < Math.abs(pts[lo] - time) ? lo - 1 : lo;
        tooltipRef.current = { x: 0, col };
      }
      draw();
    });
  }, [subscribe, draw, data]);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const plotW = rect.width - LABEL_WIDTH;
      const col = Math.floor(((mouseX - LABEL_WIDTH) / plotW) * data.timePoints.length);
      tooltipRef.current = { x: mouseX, col };
      draw();
      // Publish cursor time to sibling visualizations
      if (col >= 0 && col < data.timePoints.length) {
        publish(data.timePoints[col]);
      }
    },
    [data, draw, publish],
  );

  const handleMouseLeave = useCallback(() => {
    tooltipRef.current = null;
    draw();
    publish(null);
  }, [draw, publish]);

  const canvasHeight = Math.max(data.pitchClasses.length * ROW_HEIGHT, 140);

  return (
    <div className="space-y-2">
      <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
        Interactive Chroma
      </span>
      <div className="rounded-sm overflow-hidden border border-border bg-bg-panel">
        <canvas
          ref={canvasRef}
          className="w-full cursor-crosshair"
          style={{ height: canvasHeight }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        />
      </div>
    </div>
  );
}

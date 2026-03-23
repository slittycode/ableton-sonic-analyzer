import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { OnsetStrengthData, SpectralTimeSeriesData } from '../types';
import { useSpectralCursor } from '../hooks/useSpectralCursorBus';

interface SpectralEvolutionChartProps {
  data: SpectralTimeSeriesData;
  onsetStrength?: OnsetStrengthData | null;
}

interface SeriesConfig {
  key: string;
  label: string;
  color: string;
  unit: string;
}

const SERIES: SeriesConfig[] = [
  { key: 'spectralCentroid', label: 'Centroid', color: '#60a5fa', unit: 'Hz' },
  { key: 'spectralRolloff', label: 'Rolloff', color: '#a78bfa', unit: 'Hz' },
  { key: 'spectralBandwidth', label: 'Bandwidth', color: '#34d399', unit: 'Hz' },
  { key: 'spectralFlatness', label: 'Flatness', color: '#fbbf24', unit: '' },
  { key: 'onsetStrength', label: 'Onset', color: '#f87171', unit: '' },
];

function getSeriesValues(
  series: SeriesConfig,
  data: SpectralTimeSeriesData,
  onsetStrength: OnsetStrengthData | null | undefined,
): number[] | undefined {
  if (series.key === 'onsetStrength') {
    return onsetStrength?.onsetStrength;
  }
  return (data as unknown as Record<string, unknown>)[series.key] as number[] | undefined;
}

function drawChart(
  canvas: HTMLCanvasElement,
  data: SpectralTimeSeriesData,
  visibleSeries: Set<string>,
  onsetStrength: OnsetStrengthData | null | undefined,
  hoveredTime: number | null = null,
) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;
  const padding = { top: 8, right: 8, bottom: 20, left: 8 };
  const plotW = w - padding.left - padding.right;
  const plotH = h - padding.top - padding.bottom;

  ctx.clearRect(0, 0, w, h);

  // Draw time axis ticks
  const duration = data.timePoints[data.timePoints.length - 1] ?? 0;
  if (duration > 0) {
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    ctx.font = '9px monospace';
    ctx.textAlign = 'center';
    const tickCount = Math.min(6, Math.floor(duration / 10) + 1);
    for (let i = 0; i <= tickCount; i++) {
      const t = (duration * i) / tickCount;
      const x = padding.left + (t / duration) * plotW;
      const mins = Math.floor(t / 60);
      const secs = Math.floor(t % 60);
      ctx.fillText(`${mins}:${secs.toString().padStart(2, '0')}`, x, h - 4);
    }
  }

  // Draw each visible series
  for (const series of SERIES) {
    if (!visibleSeries.has(series.key)) continue;

    const values = getSeriesValues(series, data, onsetStrength);
    if (!values || values.length === 0) continue;

    // Normalize to 0-1 range for this series
    let min = Infinity;
    let max = -Infinity;
    for (const v of values) {
      if (v < min) min = v;
      if (v > max) max = v;
    }
    const range = max - min || 1;

    ctx.beginPath();
    ctx.strokeStyle = series.color;
    ctx.lineWidth = 1.5;
    ctx.globalAlpha = 0.85;

    for (let i = 0; i < values.length; i++) {
      const x = padding.left + (i / (values.length - 1)) * plotW;
      const y = padding.top + plotH - ((values[i] - min) / range) * plotH;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  // Hover cursor line + value readouts
  if (hoveredTime !== null && duration > 0) {
    const hoverX = padding.left + (hoveredTime / duration) * plotW;
    if (hoverX >= padding.left && hoverX <= padding.left + plotW) {
      ctx.strokeStyle = 'rgba(255,255,255,0.35)';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(hoverX, padding.top);
      ctx.lineTo(hoverX, padding.top + plotH);
      ctx.stroke();
      ctx.setLineDash([]);

      // Value readouts at the cursor position
      const timeIdx = Math.round(
        (hoveredTime / duration) * (data.timePoints.length - 1),
      );
      let readoutY = padding.top + 12;
      const flipSide = hoverX > w / 2;
      for (const series of SERIES) {
        if (!visibleSeries.has(series.key)) continue;
        const values = getSeriesValues(series, data, onsetStrength);
        if (!values || values.length === 0) continue;
        const idx = Math.min(Math.max(0, timeIdx), values.length - 1);
        const val = values[idx];
        const label = series.unit
          ? `${series.label}: ${val.toFixed(0)} ${series.unit}`
          : `${series.label}: ${val.toFixed(4)}`;
        ctx.font = '9px ui-monospace, monospace';
        ctx.fillStyle = series.color;
        ctx.textAlign = flipSide ? 'right' : 'left';
        ctx.fillText(label, flipSide ? hoverX - 6 : hoverX + 6, readoutY);
        readoutY += 12;
      }
    }
  }
}

export function SpectralEvolutionChart({ data, onsetStrength }: SpectralEvolutionChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const hoveredTimeRef = useRef<number | null>(null);
  const [visibleSeries, setVisibleSeries] = useState<Set<string>>(
    () => new Set(['spectralCentroid', 'spectralRolloff']),
  );

  const { publish, subscribe } = useSpectralCursor('evolution-chart');

  const toggleSeries = useCallback((key: string) => {
    setVisibleSeries((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    drawChart(canvas, data, visibleSeries, onsetStrength, hoveredTimeRef.current);
  }, [data, visibleSeries, onsetStrength]);

  useEffect(() => {
    redraw();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver(() => redraw());
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [redraw]);

  // Subscribe to external cursor events from sibling visualizations
  useEffect(() => {
    return subscribe((time) => {
      hoveredTimeRef.current = time;
      redraw();
    });
  }, [subscribe, redraw]);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const paddingLeft = 8;
      const paddingRight = 8;
      const plotW = rect.width - paddingLeft - paddingRight;
      const duration = data.timePoints[data.timePoints.length - 1] ?? 0;
      if (duration <= 0 || plotW <= 0) return;
      const time = Math.max(0, Math.min(duration, ((mouseX - paddingLeft) / plotW) * duration));
      hoveredTimeRef.current = time;
      redraw();
      publish(time);
    },
    [data, redraw, publish],
  );

  const handleMouseLeave = useCallback(() => {
    hoveredTimeRef.current = null;
    redraw();
    publish(null);
  }, [redraw, publish]);

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
          Spectral Evolution
        </span>
        <div className="flex gap-1 flex-wrap">
          {SERIES.filter((s) => s.key !== 'onsetStrength' || onsetStrength).map((s) => (
            <button
              key={s.key}
              onClick={() => toggleSeries(s.key)}
              className={`px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide rounded-sm transition-colors flex items-center gap-1 ${
                visibleSeries.has(s.key)
                  ? 'border border-opacity-30'
                  : 'text-text-secondary hover:text-text-primary border border-transparent opacity-50'
              }`}
              style={
                visibleSeries.has(s.key)
                  ? { color: s.color, borderColor: `${s.color}40` }
                  : undefined
              }
            >
              <span
                className="inline-block w-2 h-2 rounded-full"
                style={{ backgroundColor: s.color, opacity: visibleSeries.has(s.key) ? 1 : 0.3 }}
              />
              {s.label}
            </button>
          ))}
        </div>
      </div>
      <div className="rounded-sm overflow-hidden border border-border bg-bg-panel">
        <canvas
          ref={canvasRef}
          className="w-full cursor-crosshair"
          style={{ height: '120px' }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        />
      </div>
    </div>
  );
}

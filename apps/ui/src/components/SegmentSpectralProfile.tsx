import React, { useMemo } from 'react';
import type { Phase1Result, SegmentSpectralEntry } from '../types';

interface SegmentSpectralProfileProps {
  segmentSpectral: Phase1Result['segmentSpectral'];
  segmentLoudness: Phase1Result['segmentLoudness'];
}

interface SegmentCellData {
  segmentIndex: number;
  label: string;
  timeLabel: string | null;
  barkBands: number[];
}

const MIN_INTENSITY = 0.5;

function toFiniteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function toSegmentTimeLabel(segmentLoudness: Phase1Result['segmentLoudness'], segmentIndex: number): string | null {
  if (!Array.isArray(segmentLoudness)) return null;

  const byIndex = segmentLoudness.find((entry) => {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return false;
    const record = entry as Record<string, unknown>;
    return Math.round(toFiniteNumber(record.segmentIndex) ?? -1) === segmentIndex;
  });

  const fallbackByPosition = segmentLoudness[segmentIndex];
  const candidate = (byIndex ?? fallbackByPosition) as Record<string, unknown> | undefined;
  if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) return null;

  const start = toFiniteNumber(candidate.start);
  const end = toFiniteNumber(candidate.end);

  if (start === null && end === null) return null;
  const fmt = (v: number) => v >= 10 ? `${Math.round(v)}s` : `${v.toFixed(1)}s`;
  if (start !== null && end !== null && end >= start) {
    return `${fmt(start)}–${fmt(end)}`;
  }
  if (start !== null) return fmt(start);
  return fmt(end!);
}

function getDisplaySegments(
  segmentSpectral: Phase1Result['segmentSpectral'],
  segmentLoudness: Phase1Result['segmentLoudness'],
): SegmentCellData[] {
  if (!Array.isArray(segmentSpectral)) return [];

  const parsed = segmentSpectral
    .map((entry: SegmentSpectralEntry): SegmentCellData | null => {
      if (!entry || !Array.isArray(entry.barkBands)) return null;
      const barkBands = entry.barkBands.filter((band) => Number.isFinite(band));
      if (barkBands.length === 0) return null;

      const segmentIndex = Math.max(0, Math.round(entry.segmentIndex));
      return {
        segmentIndex,
        label: `S${segmentIndex + 1}`,
        timeLabel: toSegmentTimeLabel(segmentLoudness, segmentIndex),
        barkBands,
      };
    })
    .filter((entry): entry is SegmentCellData => entry !== null)
    .sort((left, right) => left.segmentIndex - right.segmentIndex);

  if (parsed.length === 0) return [];

  const sharedBandCount = Math.min(...parsed.map((entry) => entry.barkBands.length));
  if (!Number.isFinite(sharedBandCount) || sharedBandCount < 1) return [];

  return parsed.map((entry) => ({
    ...entry,
    barkBands: entry.barkBands.slice(0, sharedBandCount),
  }));
}

function toHeatColor(intensity: number): string {
  const clamped = Math.max(0, Math.min(intensity, 1));
  const lightness = 14 + clamped * 50;
  const saturation = 45 + clamped * 45;
  return `hsl(30 ${saturation}% ${lightness}%)`;
}

export function SegmentSpectralProfile({ segmentSpectral, segmentLoudness }: SegmentSpectralProfileProps) {
  const segments = useMemo(
    () => getDisplaySegments(segmentSpectral, segmentLoudness),
    [segmentSpectral, segmentLoudness],
  );

  const title = segments.length <= 4 ? 'Per-section spectral profile' : 'Segment spectral heatmap';

  if (segments.length === 0) {
    return (
      <div className="bg-bg-card border border-border rounded-sm p-4 space-y-2">
        <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
          {title}
        </p>
        <p className="text-xs font-mono text-text-secondary opacity-80">
          Segment Bark-band data unavailable for this run.
        </p>
      </div>
    );
  }

  const bandCount = segments[0].barkBands.length;
  const allValues = segments.flatMap((segment) => segment.barkBands);
  const minValue = Math.min(...allValues);
  const maxValue = Math.max(...allValues);
  const range = maxValue - minValue;

  // Scale cell size based on column count so few-column grids aren't absurdly tall
  const cellWidth = segments.length <= 4 ? 80 : segments.length <= 8 ? 48 : 28;
  const cellHeight = segments.length <= 4 ? 10 : 7;
  const padLeft = 44;
  const padTop = 16;
  const padBottom = 44;
  const padRight = 10;
  const plotWidth = segments.length * cellWidth;
  const plotHeight = bandCount * cellHeight;
  const viewWidth = padLeft + plotWidth + padRight;
  const viewHeight = padTop + plotHeight + padBottom;

  const ariaLabel = `${title}. ${segments.length} sections by ${bandCount} Bark bands.`;

  return (
    <div className="bg-bg-card border border-border rounded-sm p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
          {title}
        </p>
        <span className="text-[10px] font-mono text-text-secondary opacity-70">
          {segments.length} x {bandCount}
        </span>
      </div>

      <svg
        viewBox={`0 0 ${viewWidth} ${viewHeight}`}
        className="w-full h-auto max-w-md mx-auto"
        role="img"
        aria-label={ariaLabel}
      >
        {segments.map((segment, columnIndex) => (
          segment.barkBands.map((value, bandIndex) => {
            const x = padLeft + columnIndex * cellWidth;
            const y = padTop + (bandCount - 1 - bandIndex) * cellHeight;
            const intensity = range === 0 ? MIN_INTENSITY : (value - minValue) / range;
            const fill = toHeatColor(intensity);

            return (
              <g key={`${segment.segmentIndex}-${bandIndex}`}>
                <title>{`${segment.label}, Bark ${bandIndex + 1}: ${value.toFixed(2)} dB`}</title>
                <rect
                  x={x}
                  y={y}
                  width={cellWidth - 1}
                  height={cellHeight - 1}
                  rx={1}
                  fill={fill}
                />
              </g>
            );
          })
        ))}

        <text
          x={padLeft - 8}
          y={padTop + 6}
          textAnchor="end"
          fill="currentColor"
          className="text-text-secondary"
          fontSize={9}
          fontFamily="monospace"
          fillOpacity={0.75}
        >
          High
        </text>
        <text
          x={padLeft - 8}
          y={padTop + plotHeight}
          textAnchor="end"
          fill="currentColor"
          className="text-text-secondary"
          fontSize={9}
          fontFamily="monospace"
          fillOpacity={0.75}
        >
          Low
        </text>

        {segments.map((segment, columnIndex) => {
          const x = padLeft + columnIndex * cellWidth + (cellWidth - 1) / 2;
          const yBase = padTop + plotHeight + 10;

          return (
            <g key={`x-label-${segment.segmentIndex}`}>
              <text
                x={x}
                y={yBase}
                textAnchor="middle"
                fill="currentColor"
                className="text-text-secondary"
                fontSize={9}
                fontFamily="monospace"
                fillOpacity={0.85}
              >
                {segment.label}
              </text>
              {segment.timeLabel && (
                <text
                  x={x}
                  y={yBase + 9}
                  textAnchor="middle"
                  fill="currentColor"
                  className="text-text-secondary"
                  fontSize={8}
                  fontFamily="monospace"
                  fillOpacity={0.6}
                >
                  {segment.timeLabel}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary opacity-70">
        Bark-band energy per section (not a continuous-time spectrogram)
      </p>
    </div>
  );
}

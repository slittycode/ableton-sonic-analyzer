import React, { useMemo } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import type { Phase1Result } from '../types';

interface SpectralBalanceCurveProps {
  spectralBalance: Phase1Result['spectralBalance'];
  barkBands: number[] | null | undefined;
}

const ACCENT = '#ff8800';

type CurveMode = 'bark24' | 'aggregate6';

const AGGREGATE_BANDS = [
  { key: 'subBass' as const, label: 'Sub', freqHz: 40 },
  { key: 'lowBass' as const, label: 'Low', freqHz: 120 },
  { key: 'mids' as const, label: 'Mid', freqHz: 600 },
  { key: 'upperMids' as const, label: 'Upper Mid', freqHz: 4000 },
  { key: 'highs' as const, label: 'High', freqHz: 9000 },
  { key: 'brilliance' as const, label: 'Air', freqHz: 16000 },
] as const;

const AGGREGATE_X_POSITIONS = [0.08, 0.20, 0.42, 0.64, 0.80, 0.92];

const VIEW_W = 560;
const VIEW_H = 200;
const PAD_TOP = 30;
const PAD_BOTTOM = 40;
const PAD_LEFT = 10;
const PAD_RIGHT = 10;
const PLOT_H = VIEW_H - PAD_TOP - PAD_BOTTOM;
const PLOT_CENTER_Y = PAD_TOP + PLOT_H / 2;

interface Point {
  x: number;
  y: number;
  value: number;
  label: string;
  freqHz: number;
}

interface AxisTick {
  x: number;
  label: string;
  index: number;
}

function describeSpectralCharacter(spectralBalance: Phase1Result['spectralBalance']): string {
  const { subBass, lowBass, mids, upperMids, highs, brilliance } = spectralBalance;

  const bassAvg = (subBass + lowBass) / 2;
  const midsAvg = (mids + upperMids) / 2;
  const highsAvg = (highs + brilliance) / 2;
  const allValues = [subBass, lowBass, mids, upperMids, highs, brilliance];
  const range = Math.max(...allValues) - Math.min(...allValues);

  const descriptors: string[] = [];

  if (range <= 3) return 'Balanced';
  if (bassAvg > midsAvg + 3) descriptors.push('Bass-heavy');
  if (highsAvg > midsAvg + 3) descriptors.push('Bright');
  if (midsAvg < bassAvg - 3 && midsAvg < highsAvg - 3) descriptors.push('Scooped mids');
  if (midsAvg > bassAvg + 3 && midsAvg > highsAvg + 3) descriptors.push('Mid-forward');
  if (upperMids < mids - 3 && upperMids < highs - 3) descriptors.push('presence dip');
  if (highsAvg < midsAvg - 3 && highsAvg < bassAvg - 3) descriptors.push('Dark');

  if (descriptors.length === 0) return 'Balanced';
  if (descriptors.length === 1) return descriptors[0];

  const primary = descriptors[0];
  const secondary = descriptors.slice(1).map((item) => (item === 'presence dip' ? item : item.toLowerCase()));
  return `${primary} with ${secondary.join(' and ')}`;
}

function barkToHz(z: number): number {
  return 600 * Math.sinh(z / 6);
}

function barkBandCenterHz(index: number, totalBands: number): number {
  const z = ((index + 0.5) / totalBands) * 24;
  return barkToHz(z);
}

function formatHzLabel(freqHz: number): string {
  if (freqHz >= 1000) return `${(freqHz / 1000).toFixed(freqHz >= 10000 ? 0 : 1)}k`;
  return `${Math.round(freqHz)}`;
}

function linearPath(points: Point[]): string {
  if (points.length < 2) return '';
  return points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(' ');
}

function aggregateTicks(points: Point[]): AxisTick[] {
  return points.map((point, index) => ({ x: point.x, label: point.label, index }));
}

function barkTicks(points: Point[]): AxisTick[] {
  const lastIndex = points.length - 1;
  const candidateIndices = [0, Math.floor(lastIndex * 0.25), Math.floor(lastIndex * 0.5), Math.floor(lastIndex * 0.75), lastIndex];
  const unique = [...new Set(candidateIndices)].filter((index) => index >= 0 && index < points.length);

  return unique.map((index) => {
    const freqHz = barkBandCenterHz(index, points.length);
    return {
      x: points[index].x,
      label: formatHzLabel(freqHz),
      index,
    };
  });
}

export function SpectralBalanceCurve({ spectralBalance, barkBands }: SpectralBalanceCurveProps) {
  const prefersReducedMotion = useReducedMotion();

  const {
    points,
    mode,
    modeLabel,
    axisCaption,
    curvePath,
    fillPath,
    maxAbsDb,
    zeroLineY,
    character,
    ticks,
    labeledPointIndices,
  } = useMemo(() => {
    const sanitizedBark = Array.isArray(barkBands)
      ? barkBands.filter((value): value is number => Number.isFinite(value))
      : [];

    const mode: CurveMode = sanitizedBark.length >= 2 ? 'bark24' : 'aggregate6';
    const values = mode === 'bark24'
      ? sanitizedBark
      : AGGREGATE_BANDS.map((band) => spectralBalance[band.key]);

    const maxAbs = Math.max(...values.map((value) => Math.abs(value)), 1);
    const scale = (PLOT_H / 2) / maxAbs;

    const computedPoints: Point[] = mode === 'bark24'
      ? values.map((value, index) => {
          const ratio = values.length === 1 ? 0 : index / (values.length - 1);
          const x = PAD_LEFT + ratio * (VIEW_W - PAD_LEFT - PAD_RIGHT);
          const y = PLOT_CENTER_Y - value * scale;
          return {
            x,
            y,
            value,
            label: `B${index + 1}`,
            freqHz: barkBandCenterHz(index, values.length),
          };
        })
      : values.map((value, index) => {
          const x = PAD_LEFT + AGGREGATE_X_POSITIONS[index] * (VIEW_W - PAD_LEFT - PAD_RIGHT);
          const y = PLOT_CENTER_Y - value * scale;
          return {
            x,
            y,
            value,
            label: AGGREGATE_BANDS[index].label,
            freqHz: AGGREGATE_BANDS[index].freqHz,
          };
        });

    const curve = linearPath(computedPoints);
    const firstPoint = computedPoints[0];
    const lastPoint = computedPoints[computedPoints.length - 1];
    const baselineY = PLOT_CENTER_Y + PLOT_H / 2;
    const fill = `${curve} L ${lastPoint.x.toFixed(2)} ${baselineY.toFixed(2)} L ${firstPoint.x.toFixed(2)} ${baselineY.toFixed(2)} Z`;

    const ticks = mode === 'bark24' ? barkTicks(computedPoints) : aggregateTicks(computedPoints);
    const labeledPointIndices = new Set(ticks.map((tick) => tick.index));

    return {
      points: computedPoints,
      mode,
      modeLabel: mode === 'bark24' ? '24-band Bark global average' : '6-band aggregate fallback',
      axisCaption: mode === 'bark24' ? 'Bark-scale center frequency (Hz)' : 'Sub/Low/Mid/Upper Mid/High/Air bands',
      curvePath: curve,
      fillPath: fill,
      maxAbsDb: maxAbs,
      zeroLineY: PLOT_CENTER_Y,
      character: describeSpectralCharacter(spectralBalance),
      ticks,
      labeledPointIndices,
    };
  }, [barkBands, spectralBalance]);

  const approxPathLength = useMemo(() => {
    let total = 0;
    for (let i = 1; i < points.length; i += 1) {
      const dx = points[i].x - points[i - 1].x;
      const dy = points[i].y - points[i - 1].y;
      total += Math.sqrt(dx * dx + dy * dy);
    }
    return Math.ceil(total);
  }, [points]);

  const gridLines = useMemo(() => {
    const lines: { y: number; db: number }[] = [{ y: zeroLineY, db: 0 }];
    const step = maxAbsDb <= 6 ? 3 : maxAbsDb <= 12 ? 6 : 12;
    const scale = (PLOT_H / 2) / maxAbsDb;

    for (let db = step; db <= maxAbsDb; db += step) {
      lines.push({ y: zeroLineY - db * scale, db });
      lines.push({ y: zeroLineY + db * scale, db: -db });
    }

    return lines;
  }, [zeroLineY, maxAbsDb]);

  const ariaLabel = `Spectral balance (${modeLabel}). Character ${character}.`;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between border-b border-border pb-2">
        <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
          <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
          Spectral Balance
        </h2>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono bg-bg-panel border border-border px-2 py-1 rounded text-text-secondary">
            {modeLabel}
          </span>
          <span className="text-[10px] font-mono bg-bg-panel border border-border px-2 py-1 rounded font-bold text-text-secondary">
            PHASE 1
          </span>
        </div>
      </div>

      <div className="bg-bg-card border border-border rounded-sm p-4">
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          className="w-full h-auto"
          aria-label={ariaLabel}
          role="img"
        >
          <defs>
            <linearGradient id="spectral-fill-gradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={ACCENT} stopOpacity={0.15} />
              <stop offset="100%" stopColor={ACCENT} stopOpacity={0.02} />
            </linearGradient>
          </defs>

          {gridLines.map((line, i) => (
            <line
              key={`grid-${i}`}
              x1={PAD_LEFT}
              y1={line.y}
              x2={VIEW_W - PAD_RIGHT}
              y2={line.y}
              stroke="currentColor"
              className="text-text-secondary"
              strokeOpacity={line.db === 0 ? 0.25 : 0.1}
              strokeWidth={line.db === 0 ? 1 : 0.5}
              strokeDasharray={line.db === 0 ? '6 4' : undefined}
            />
          ))}

          {gridLines.map((line, i) => (
            <text
              key={`grid-label-${i}`}
              x={PAD_LEFT - 2}
              y={line.y + 3}
              textAnchor="end"
              className="text-text-secondary"
              fill="currentColor"
              fillOpacity={0.4}
              fontSize={8}
              fontFamily="monospace"
            >
              {line.db === 0 ? '0' : `${line.db > 0 ? '+' : ''}${line.db}`}
            </text>
          ))}

          <path d={fillPath} fill="url(#spectral-fill-gradient)" />

          {prefersReducedMotion ? (
            <path
              d={curvePath}
              fill="none"
              stroke={ACCENT}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ) : (
            <motion.path
              d={curvePath}
              fill="none"
              stroke={ACCENT}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              initial={{ strokeDasharray: approxPathLength, strokeDashoffset: approxPathLength }}
              animate={{ strokeDashoffset: 0 }}
              transition={{ duration: 0.3, ease: 'easeOut' }}
            />
          )}

          {points.map((point, index) => (
            <g key={`point-${index}`}>
              <title>{`${point.label}: ${point.value > 0 ? '+' : ''}${point.value.toFixed(1)} dB`}</title>
              <circle
                cx={point.x}
                cy={point.y}
                r={mode === 'bark24' ? 1.8 : 3}
                fill={ACCENT}
                stroke="var(--color-bg-card, #1a1a2e)"
                strokeWidth={1.2}
              />
            </g>
          ))}

          {points.map((point, index) => {
            if (!labeledPointIndices.has(index)) return null;

            const above = point.y > zeroLineY;
            const labelY = above ? point.y + 14 : point.y - 8;

            return (
              <text
                key={`db-${index}`}
                x={point.x}
                y={labelY}
                textAnchor="middle"
                fill="currentColor"
                className="text-text-secondary"
                fontSize={9}
                fontFamily="monospace"
                fillOpacity={0.7}
              >
                {point.value > 0 ? '+' : ''}{point.value.toFixed(1)}
              </text>
            );
          })}

          {ticks.map((tick) => (
            <text
              key={`label-${tick.index}`}
              x={tick.x}
              y={VIEW_H - 6}
              textAnchor="middle"
              fill="currentColor"
              className="text-text-secondary"
              fontSize={10}
              fontFamily="monospace"
              fillOpacity={0.7}
            >
              {tick.label}
            </text>
          ))}
        </svg>

        <div className="mt-3 pt-3 border-t border-border/50 space-y-1">
          <p className="text-xs font-mono text-text-secondary">Character: {character}</p>
          <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary opacity-70">
            {axisCaption} · Linear segments through measured points only
          </p>
        </div>
      </div>
    </div>
  );
}

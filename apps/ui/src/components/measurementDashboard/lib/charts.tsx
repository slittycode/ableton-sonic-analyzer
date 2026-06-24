import React from 'react';
import { motion } from 'motion/react';

import { SPECTRAL_CHART_PALETTE } from './constants';
import { chordToneForLabel, formatNumber } from './formatters';
import { StatusBadge } from './scaffold';

// Chart / table / leaf presentational helpers for the Measurement Dashboard,
// moved verbatim out of the MeasurementDashboard monolith (Phase 4 split) so
// the extracted panels and the main component share one source.

export const ChordTokenRow = ({ chords }: { chords: string[] }) => (
  <div className="mt-2 flex flex-wrap items-center gap-1.5 text-sm text-text-primary break-words">
    {chords.map((chord, index) => (
      <React.Fragment key={`${chord}-${index}`}>
        <StatusBadge label={chord} tone={chordToneForLabel(chord)} compact />
        {index < chords.length - 1 && (
          <span className="text-text-secondary/45 font-mono text-xs">→</span>
        )}
      </React.Fragment>
    ))}
  </div>
);

export const BarChart = ({
  values,
  count,
  label,
  height = 'h-6',
  colors = SPECTRAL_CHART_PALETTE,
}: {
  values: number[];
  count: number;
  label: string;
  height?: string;
  colors?: string[];
}) => {
  const padding = Math.max(0, count - values.length);
  const displayValues = [...values, ...Array(padding).fill(0)];
  const maxVal = Math.max(...displayValues.slice(0, count), 1);

  return (
    <div className="space-y-1.5">
      <span className="text-meta font-mono uppercase tracking-[0.16em] text-text-secondary">
        {label}
      </span>
      <div className="flex gap-1 items-end rounded-sm border border-border-light/60 bg-bg-surface-dark/80 p-2">
        {displayValues.slice(0, count).map((val, i) => {
          const percent = (val / maxVal) * 100;
          const color = colors[i % colors.length];
          return (
            <div
              key={i}
              className="flex-1 rounded-sm"
              style={{
                height: `calc(${height} * ${percent / 100})`,
                minHeight: val > 0 ? '4px' : '2px',
                opacity: val > 0 ? 1 : 0.2,
                background: `linear-gradient(to top, ${color}cc, ${color})`,
                boxShadow: val > 0 ? `0 0 10px ${color}33` : undefined,
              }}
              title={formatNumber(val, 3)}
            />
          );
        })}
      </div>
    </div>
  );
};

export const HorizontalDominance = ({
  kickRatio,
  midRatio,
  highRatio,
}: {
  kickRatio: number;
  midRatio: number;
  highRatio: number;
}) => {
  const total = kickRatio + midRatio + highRatio || 1;
  const kickPercent = (kickRatio / total) * 100;
  const midPercent = (midRatio / total) * 100;
  const highPercent = (highRatio / total) * 100;

  return (
    <div className="space-y-1">
      <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">
        Beat Dominance
      </span>
      <div className="flex h-5 gap-px overflow-hidden rounded-sm">
        <div
          className="bg-red-500"
          style={{ width: `${kickPercent}%` }}
          title={`Kick: ${formatNumber(kickRatio, 2)}`}
        />
        <div
          className="bg-yellow-500"
          style={{ width: `${midPercent}%` }}
          title={`Mid: ${formatNumber(midRatio, 2)}`}
        />
        <div
          className="bg-blue-500"
          style={{ width: `${highPercent}%` }}
          title={`High: ${formatNumber(highRatio, 2)}`}
        />
      </div>
      <div className="flex justify-between text-micro text-text-secondary gap-1">
        <span>K {formatNumber(kickRatio, 2)}</span>
        <span>M {formatNumber(midRatio, 2)}</span>
        <span>H {formatNumber(highRatio, 2)}</span>
      </div>
    </div>
  );
};

export const SimpleTable = <T extends object>({
  data,
  columns,
}: {
  data: T[];
  columns: { key: string; label: string; format?: (v: unknown) => string }[];
}) => (
  <div className="overflow-x-auto">
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr className="border-b border-border">
          {columns.map((col) => (
            <th
              key={col.key}
              className="px-2 py-1 text-left text-meta font-mono uppercase tracking-wide text-text-secondary font-normal"
            >
              {col.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.map((row, idx) => (
          <tr
            key={idx}
            className={`border-b border-border ${
              idx % 2 === 0 ? 'bg-bg-secondary' : ''
            }`}
          >
            {columns.map((col) => (
              <td
                key={`${idx}-${col.key}`}
                className="px-2 py-1 text-sm text-text-primary"
              >
                {(() => {
                  const value = (row as Record<string, unknown>)[col.key];
                  return col.format
                    ? col.format(value)
                    : formatNumber(value as number);
                })()}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

/* ── Rhythm & Groove leaf components ────────────────────────────────── */

export const BreathingBpmPulse = ({ bpm, bpmSource }: { bpm: number; bpmSource?: string | null }) => {
  const pulseDuration = bpm > 0 ? 60 / bpm : 0.5;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5 }}
      className="flex min-h-[188px] w-full shrink-0 items-center justify-center rounded-sm border border-border bg-bg-surface-dark px-4 py-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] md:w-[176px]"
    >
      <svg viewBox="0 0 120 120" className="w-[120px] h-[120px]">
        <circle cx="60" cy="60" r="52" fill="none" stroke="#ff880015" strokeWidth="10" />
        <circle
          cx="60"
          cy="60"
          r="52"
          fill="none"
          stroke="#ff8800"
          strokeWidth="2"
          strokeDasharray="3 9"
          opacity="0.4"
        >
          <animateTransform
            attributeName="transform"
            type="rotate"
            dur="8s"
            from="0 60 60"
            to="360 60 60"
            repeatCount="indefinite"
          />
        </circle>
        <circle
          cx="60"
          cy="60"
          r="38"
          fill="none"
          stroke="#a78bfa"
          strokeWidth="1.5"
          strokeDasharray="4 7"
          opacity="0.25"
        >
          <animateTransform
            attributeName="transform"
            type="rotate"
            dur="12s"
            from="360 60 60"
            to="0 60 60"
            repeatCount="indefinite"
          />
        </circle>
        <circle cx="60" cy="60" r="4" fill="#ff8800">
          <animate
            attributeName="r"
            values="3;5.5;3"
            dur={`${pulseDuration}s`}
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0.8;0.35;0.8"
            dur={`${pulseDuration}s`}
            repeatCount="indefinite"
          />
        </circle>
        <text
          x="60"
          y="57"
          textAnchor="middle"
          fill="#fff"
          fontSize="22"
          fontWeight="800"
          fontFamily="'JetBrains Mono', monospace"
        >
          {Math.round(bpm)}
        </text>
        <text
          x="60"
          y="70"
          textAnchor="middle"
          fill="#555"
          fontSize="8"
          fontFamily="'JetBrains Mono', monospace"
        >
          BPM
        </text>
        {bpmSource && (
          <text
            x="60"
            y="82"
            textAnchor="middle"
            fill="#00ff9d80"
            fontSize="6.5"
            fontFamily="'JetBrains Mono', monospace"
          >
            {bpmSource === 'percival_ratio_corrected'
              ? '● corrected'
              : bpmSource === 'rhythm_extractor_confirmed'
                ? '● confirmed'
                : '● detected'}
          </text>
        )}
      </svg>
    </motion.div>
  );
};

const COMPARATIVE_ZONES: Record<
  string,
  { color: string; zones: string[]; max: number; unit?: string }
> = {
  groove: { color: '#ff8800', zones: ['tight', 'loose', 'swung', 'free'], max: 1 },
  stability: {
    color: '#a78bfa',
    zones: ['erratic', 'loose', 'steady', 'locked'],
    max: 100,
    unit: '%',
  },
  danceability: {
    color: '#fbbf24',
    zones: ['ambient', 'chill', 'groovy', 'peak'],
    max: 1,
  },
  onsetRate: {
    color: '#34d399',
    zones: ['sparse', 'moderate', 'dense', 'maximal'],
    max: 8,
    unit: '/sec',
  },
};

export const ComparativeMetricTile = ({
  metricKey,
  value,
  delay = 0,
}: {
  metricKey: string;
  value: number;
  delay?: number;
}) => {
  const cfg = COMPARATIVE_ZONES[metricKey];
  if (!cfg) return null;
  const pct = Math.max(0, Math.min(100, (value / cfg.max) * 100));
  const displayValue = cfg.unit === '%' ? `${value.toFixed(1)}%` : value.toFixed(2);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay }}
      className="bg-bg-surface-dark border border-border rounded-sm p-3"
    >
      <span
        className="text-meta font-mono uppercase tracking-wider block"
        style={{ color: `${cfg.color}80` }}
      >
        {metricKey === 'onsetRate' ? 'Onset Rate' : metricKey}
      </span>
      <div className="flex items-baseline gap-1 mt-1">
        <span
          className="text-value-lg font-display font-extrabold tabular-nums"
          style={{ color: cfg.color }}
        >
          {cfg.unit === '/sec' ? value.toFixed(1) : displayValue}
        </span>
        {cfg.unit === '/sec' && (
          <span className="text-micro font-mono" style={{ color: `${cfg.color}60` }}>
            /sec
          </span>
        )}
      </div>
      <div className="relative mt-2.5">
        <div className="flex h-[6px] rounded-[3px] overflow-hidden">
          {cfg.zones.map((_, i) => (
            <div
              key={i}
              className="flex-1"
              style={{
                background: `linear-gradient(90deg, ${cfg.color}${
                  i === Math.floor(pct / 25) ? '30' : '12'
                }, ${cfg.color}${i === Math.floor(pct / 25) ? '40' : '18'})`,
              }}
            />
          ))}
        </div>
        <div
          className="absolute top-[-2px] w-[2px] h-[10px] rounded-sm"
          style={{
            left: `${pct}%`,
            transform: 'translateX(-50%)',
            background: cfg.color,
            boxShadow: `0 0 6px ${cfg.color}80`,
          }}
        />
        <div className="flex justify-between mt-1">
          {cfg.zones.map((z) => (
            <span key={z} className="text-pico font-mono text-[#444]">
              {z}
            </span>
          ))}
        </div>
      </div>
    </motion.div>
  );
};

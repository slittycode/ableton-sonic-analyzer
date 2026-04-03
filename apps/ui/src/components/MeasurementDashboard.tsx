import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import {
  ChromaInteractiveData,
  MeasurementAvailabilityContext,
  OnsetStrengthData,
  Phase1Result,
  PhraseGrid,
  SpectralArtifacts,
  SpectralTimeSeriesData,
} from '../types';
import { generateMixDoctorReport } from '../services/mixDoctor';
import {
  fetchChromaInteractiveData,
  fetchOnsetStrengthData,
  fetchSpectralTimeSeries,
  generateSpectralEnhancement,
  SpectralEnhancementKind,
} from '../services/spectralArtifactsClient';
import { getAnalysisRun } from '../services/analysisRunsClient';
import { SpectrogramViewer } from './SpectrogramViewer';
import { SpectralEvolutionChart } from './SpectralEvolutionChart';
import { ChromaHeatmap } from './ChromaHeatmap';
import { MiniHeatmap } from './MiniHeatmap';
import { MixDoctorPanel } from './MixDoctorPanel';
import {
  AccentMetricCard,
  DeltaBadge,
  MetricBar,
  MetricBarRow,
  OutlinePillButton,
  StatusBadge,
  StyledDataTable,
  TokenBadgeList,
} from './MeasurementPrimitives';
import { Sparkline } from './Sparkline';
import { SpectralCursorProvider } from '../hooks/useSpectralCursorBus';
import { formatDisplayText, getTextRoleClassName } from '../utils/displayText';

interface MeasurementDashboardProps {
  phase1: Phase1Result;
  spectralArtifacts?: SpectralArtifacts | null;
  measurementAvailability?: MeasurementAvailabilityContext;
  apiBaseUrl?: string;
  runId?: string;
}

const formatNumber = (value: number | null | undefined, decimals = 2): string => {
  if (value === null || value === undefined) return '—';
  return typeof value === 'number' ? value.toFixed(decimals) : '—';
};

const formatDuration = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const formatBpmScore = (value: number): string => `SCORE ${formatNumber(value, 2)}`;

const isAssumedMeter = (phase1: Phase1Result): boolean =>
  phase1.timeSignatureSource === 'assumed_four_four' || (phase1.timeSignatureConfidence ?? 1) <= 0;

const resolveBarCount = (phase1: Phase1Result): number => {
  const phraseGridBars = phase1.rhythmDetail?.phraseGrid?.totalBars;
  if (typeof phraseGridBars === 'number' && Number.isFinite(phraseGridBars) && phraseGridBars > 0) {
    return phraseGridBars;
  }

  const beatsPerBar = parseInt(phase1.timeSignature?.split('/')[0] || '4', 10) || 4;
  const totalBeats = (phase1.durationSeconds / 60) * phase1.bpm;
  return Math.floor(totalBeats / beatsPerBar);
};

const lufsToPercent = (value: number, min = -60, max = 0): number =>
  Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));

const LUFS_METER_GRADIENT = `linear-gradient(to right,
  rgba(0,255,157,0.7) 0%,
  rgba(0,255,157,0.7) 60%,
  rgba(255,184,0,0.7) 60%,
  rgba(255,184,0,0.7) 76.7%,
  rgba(255,136,0,0.8) 76.7%,
  rgba(255,136,0,0.8) 90%,
  rgba(255,51,51,0.8) 90%,
  rgba(255,51,51,0.8) 100%
)`;

const PLATFORM_REFS = [
  { lufs: -14, label: 'SPOT' },
  { lufs: -16, label: 'APPL' },
  { lufs: -23, label: 'BDCST' },
];

const SPECTRAL_BALANCE_PALETTE: Record<
  keyof Phase1Result['spectralBalance'],
  string
> = {
  subBass: '#ff6b00',
  lowBass: '#fb923c',
  lowMids: '#f59e0b',
  mids: '#facc15',
  upperMids: '#14b8a6',
  highs: '#38bdf8',
  brilliance: '#a78bfa',
};

const SPECTRAL_ROW_CONFIG: Array<{
  key: keyof Phase1Result['spectralBalance'];
  label: string;
}> = [
  { key: 'subBass', label: 'Sub Bass' },
  { key: 'lowBass', label: 'Low Bass' },
  { key: 'lowMids', label: 'Low Mids' },
  { key: 'mids', label: 'Mids' },
  { key: 'upperMids', label: 'Upper Mids' },
  { key: 'highs', label: 'Highs' },
  { key: 'brilliance', label: 'Brilliance' },
];

const SPECTRAL_CHART_PALETTE = [
  '#ff6b00',
  '#ff8c42',
  '#f59e0b',
  '#facc15',
  '#14b8a6',
  '#38bdf8',
  '#60a5fa',
  '#a78bfa',
];

const asFiniteNumber = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  return null;
};

const clamp = (value: number, min: number, max: number): number =>
  Math.max(min, Math.min(max, value));

const normalizePercent = (value: number, min: number, max: number): number => {
  if (max === min) return 0;
  return clamp(((value - min) / (max - min)) * 100, 0, 100);
};

const formatAnalysisModeLabel = (
  analysisMode?: MeasurementAvailabilityContext['analysisMode'],
): string => {
  if (analysisMode === 'full') return 'full run';
  if (analysisMode === 'standard') return 'standard run';
  return 'run';
};

const buildDynamicsTextureCopy = (
  kind: 'both' | 'dynamics' | 'texture',
  measurementAvailability?: MeasurementAvailabilityContext,
): {
  title: string;
  description: string;
  detail?: string;
} => {
  if (!measurementAvailability?.hasRunContext) {
    if (kind === 'both') {
      return {
        title: 'Measurements unavailable',
        description: 'This payload does not include dynamics or texture detail.',
      };
    }

    return {
      title: `${kind === 'dynamics' ? 'Dynamics' : 'Texture'} unavailable`,
      description: `This payload does not include ${kind} measurements.`,
    };
  }

  const runLabel = formatAnalysisModeLabel(measurementAvailability.analysisMode);

  if (kind === 'both') {
    return {
      title: 'Measurements not included in this run',
      description: `This ${runLabel} completed without dynamics or texture detail.`,
      detail: 'This usually means an older backend or partial measurement output.',
    };
  }

  return {
    title: `${kind === 'dynamics' ? 'Dynamics' : 'Texture'} unavailable`,
    description: `This ${runLabel} did not include ${kind} measurements.`,
    detail: 'This usually means an older backend or partial measurement output.',
  };
};

function UnavailableMeasurementCard({
  title,
  description,
  detail,
}: {
  title: string;
  description: string;
  detail?: string;
}) {
  return (
    <div className="space-y-3 rounded-sm border border-dashed border-border-light/60 bg-bg-surface-dark/40 p-4">
      <span className="text-[10px] font-mono uppercase tracking-[0.16em] text-text-secondary block">
        {title}
      </span>
      <p className="text-[11px] font-mono uppercase tracking-[0.14em] text-text-secondary/80">
        {description}
      </p>
      {detail ? (
        <p className="text-[10px] font-mono uppercase tracking-[0.12em] text-text-secondary/60">
          {detail}
        </p>
      ) : null}
    </div>
  );
}

const correlationPercent = (value: number | null | undefined): number =>
  typeof value === 'number' ? normalizePercent(value, -1, 1) : 0;

const isDynamicCharacterObject = (
  value: Phase1Result['dynamicCharacter'],
): value is NonNullable<Phase1Result['dynamicCharacter']> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isTextureCharacterObject = (
  value: Phase1Result['textureCharacter'],
): value is NonNullable<Phase1Result['textureCharacter']> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const chordToneForLabel = (
  chord: string,
): 'accent' | 'violet' | 'error' | 'warning' | 'muted' => {
  const normalized = chord.trim().toLowerCase();
  if (!normalized) return 'muted';
  if (/(dim|°|o)(?![a-z])/.test(normalized)) return 'error';
  if (/(aug|\+)/.test(normalized)) return 'warning';
  if (/(^|[^a-z])m(?!aj)/.test(normalized) || /min/.test(normalized)) return 'violet';
  if (/[a-g](maj|sus|add|7|9|11|13)?/.test(normalized)) return 'accent';
  return 'muted';
};

const loudnessToneColor = (value: number | null | undefined): string => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'var(--color-text-secondary)';
  if (value >= -8) return '#ff6b00';
  if (value >= -12) return '#ffb347';
  if (value >= -16) return '#ffd166';
  return '#a3e635';
};

const formatSigned = (value: number | null | undefined, decimals = 1): string => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}`;
};

const MetricRow = ({
  label,
  value,
  sparkline,
}: {
  label: string;
  value: React.ReactNode;
  sparkline?: React.ReactNode;
}) => (
  <div className="flex justify-between items-center gap-4">
    <span
      data-text-role="eyebrow"
      className={getTextRoleClassName('eyebrow')}
    >
      {formatDisplayText(label, 'eyebrow')}
    </span>
    <div className="flex items-center gap-2">
      {sparkline && <span className="flex-shrink-0">{sparkline}</span>}
      <span
        data-text-role="value"
        className={getTextRoleClassName('value')}
      >
        {value}
      </span>
    </div>
  </div>
);

const SectionHeader = ({
  number,
  title,
  isOpen,
  onToggle,
}: {
  number: number;
  title: string;
  isOpen: boolean;
  onToggle: () => void;
}) => (
  <button
    onClick={onToggle}
    className="w-full text-left flex items-center gap-2 hover:opacity-80 transition-opacity"
  >
    <span data-text-role="meta" className={getTextRoleClassName('meta')}>
      {number.toString().padStart(2, '0')}
    </span>
    <span
      data-text-role="section-title"
      className={[getTextRoleClassName('section-title'), 'flex-1'].join(' ')}
    >
      {formatDisplayText(title, 'title')}
    </span>
    <span className="text-text-secondary text-sm">{isOpen ? '−' : '+'}</span>
  </button>
);

const Section = ({
  id,
  testId,
  number,
  title,
  children,
}: {
  id?: string;
  testId?: string;
  number: number;
  title: string;
  children: React.ReactNode;
}) => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div
      id={id}
      data-testid={testId}
      className="bg-bg-card border border-border rounded-sm p-4 space-y-4 scroll-mt-24"
    >
      <SectionHeader
        number={number}
        title={title}
        isOpen={isOpen}
        onToggle={() => setIsOpen(!isOpen)}
      />
      {isOpen && <div className="space-y-3 pt-2">{children}</div>}
    </div>
  );
};

const ChordTokenRow = ({ chords }: { chords: string[] }) => (
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

const BarChart = ({
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
      <span className="text-[10px] font-mono uppercase tracking-[0.16em] text-text-secondary">
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

const HorizontalDominance = ({
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
      <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
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
      <div className="flex justify-between text-[9px] text-text-secondary gap-1">
        <span>K {formatNumber(kickRatio, 2)}</span>
        <span>M {formatNumber(midRatio, 2)}</span>
        <span>H {formatNumber(highRatio, 2)}</span>
      </div>
    </div>
  );
};

const SimpleTable = <T extends object>({
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
              className="px-2 py-1 text-left text-[10px] font-mono uppercase tracking-wide text-text-secondary font-normal"
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

/* ── Rhythm & Groove Components ─────────────────────────────────────── */

const BreathingBpmPulse = ({ bpm, bpmSource }: { bpm: number; bpmSource?: string | null }) => {
  const pulseDuration = bpm > 0 ? 60 / bpm : 0.5;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5 }}
      className="flex min-h-[188px] w-full shrink-0 items-center justify-center rounded-sm border border-[#1e1e1e] bg-[#141414] px-4 py-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] md:w-[176px]"
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

const ComparativeMetricTile = ({
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
      className="bg-[#141414] border border-[#1e1e1e] rounded-sm p-3"
    >
      <span
        className="text-[10px] font-mono uppercase tracking-wider block"
        style={{ color: `${cfg.color}80` }}
      >
        {metricKey === 'onsetRate' ? 'Onset Rate' : metricKey}
      </span>
      <div className="flex items-baseline gap-1 mt-1">
        <span
          className="text-[22px] font-display font-extrabold tabular-nums"
          style={{ color: cfg.color }}
        >
          {cfg.unit === '/sec' ? value.toFixed(1) : displayValue}
        </span>
        {cfg.unit === '/sec' && (
          <span className="text-[9px] font-mono" style={{ color: `${cfg.color}60` }}>
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
            <span key={z} className="text-[6px] font-mono text-[#444]">
              {z}
            </span>
          ))}
        </div>
      </div>
    </motion.div>
  );
};

const RhythmGridPanel = ({ phase1 }: { phase1: Phase1Result }) => {
  const rhythmTimeline = phase1.rhythmTimeline;
  const availableWindows = useMemo(
    () => (rhythmTimeline?.windows ?? []).slice().sort((left, right) => left.bars - right.bars),
    [rhythmTimeline],
  );
  const defaultWindowBars = availableWindows.find((window) => window.bars === 8)?.bars
    ?? availableWindows[0]?.bars
    ?? null;
  const [selectedWindowBars, setSelectedWindowBars] = useState<number | null>(defaultWindowBars);

  useEffect(() => {
    setSelectedWindowBars(defaultWindowBars);
  }, [defaultWindowBars]);

  const selectedWindow = useMemo(() => {
    if (availableWindows.length === 0) return null;
    return availableWindows.find((window) => window.bars === selectedWindowBars) ?? availableWindows[0];
  }, [availableWindows, selectedWindowBars]);

  if (!rhythmTimeline || !selectedWindow) return null;

  const beatsPerBar = Math.max(1, rhythmTimeline.beatsPerBar || 4);
  const stepsPerBeat = Math.max(1, rhythmTimeline.stepsPerBeat || 4);
  const stepsPerBar = beatsPerBar * stepsPerBeat;
  const barNumbers = Array.from(
    { length: selectedWindow.bars },
    (_, index) => selectedWindow.startBar + index,
  );
  const barCellWidth = stepsPerBar * 12 + (stepsPerBar - 1) * 2 + 8;
  const lanes = [
    {
      label: 'LOW BAND',
      helper: 'kick-weighted proxy',
      values: selectedWindow.lowBandSteps,
      rgb: '255, 68, 68',
      labelColor: '#ff6b6b',
    },
    {
      label: 'MID BAND',
      helper: 'snare-range proxy',
      values: selectedWindow.midBandSteps,
      rgb: '245, 158, 11',
      labelColor: '#fbbf24',
    },
    {
      label: 'HIGH BAND',
      helper: 'hat-range proxy',
      values: selectedWindow.highBandSteps,
      rgb: '96, 165, 250',
      labelColor: '#93c5fd',
    },
    {
      label: 'OVERALL ACCENT',
      helper: 'summed band energy',
      values: selectedWindow.overallSteps,
      rgb: '52, 211, 153',
      labelColor: '#6ee7b7',
    },
  ];

  return (
    <div
      data-testid="rhythm-grid-panel"
      className="rounded-sm border border-[#1e1e1e] bg-[#141414] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]"
    >
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
            Rhythm Grid
          </span>
          {isAssumedMeter(phase1) && (
            <span className="inline-flex items-center rounded-sm border border-[#3a2b1c] bg-[#20160c] px-2 py-1 text-[10px] font-mono uppercase tracking-[0.14em] text-[#d8a15d]">
              Assumed 4/4
            </span>
          )}
          {availableWindows.length > 1 && (
            <div className="ml-1 inline-flex items-center gap-1">
              {availableWindows.map((window) => {
                const isActive = selectedWindow.bars === window.bars;
                return (
                  <button
                    key={window.bars}
                    type="button"
                    onClick={() => setSelectedWindowBars(window.bars)}
                    data-testid={`rhythm-grid-window-${window.bars}`}
                    className={`rounded-sm border px-2 py-1 text-[10px] font-mono uppercase tracking-[0.14em] transition-colors ${
                      isActive
                        ? 'border-accent/50 bg-accent/10 text-accent'
                        : 'border-[#2a2a2a] bg-[#111111] text-text-secondary hover:border-accent/30 hover:text-text-primary'
                    }`}
                  >
                    {window.bars} BAR
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <p className="max-w-[360px] text-[10px] font-mono uppercase tracking-[0.14em] text-[#6d6d6d]">
          DSP band-energy lanes. Frequency-band proxies, not isolated stems.
        </p>
      </div>

      <div className="mt-4 overflow-x-auto pb-1">
        <div className="min-w-max">
          <div className="flex items-center gap-3">
            <div className="w-[136px] shrink-0" />
            {barNumbers.map((barNumber) => (
              <div
                key={`bar-header-${barNumber}`}
                data-testid={`rhythm-grid-bar-${barNumber}`}
                className="rounded-sm border border-[#242424] bg-[#101010] px-2 py-2 text-center text-[10px] font-mono text-text-secondary"
                style={{ width: `${barCellWidth}px` }}
              >
                {barNumber}
              </div>
            ))}
          </div>

          <div className="mt-2 space-y-2">
            {lanes.map((lane) => (
              <div key={lane.label} className="flex items-start gap-3">
                <div className="flex min-h-[42px] w-[136px] shrink-0 flex-col justify-center rounded-sm border border-[#202020] bg-[#121212] px-3 py-2">
                  <span
                    className="text-[10px] font-mono uppercase tracking-[0.12em]"
                    style={{ color: lane.labelColor }}
                  >
                    {lane.label}
                  </span>
                  <span className="mt-1 text-[8px] font-mono uppercase tracking-[0.12em] text-[#5f5f5f]">
                    {lane.helper}
                  </span>
                </div>

                <div className="flex gap-3">
                  {barNumbers.map((barNumber, barIndex) => {
                    const startIndex = barIndex * stepsPerBar;
                    const barSteps = lane.values.slice(startIndex, startIndex + stepsPerBar);
                    return (
                      <div
                        key={`${lane.label}-bar-${barNumber}`}
                        className="rounded-sm border border-[#202020] bg-[#111111] p-1"
                        style={{ width: `${barCellWidth}px` }}
                      >
                        <div
                          className="grid gap-[2px]"
                          style={{ gridTemplateColumns: `repeat(${stepsPerBar}, minmax(0, 1fr))` }}
                        >
                          {barSteps.map((value, stepIndex) => {
                            const clampedValue = clamp(value ?? 0, 0, 1);
                            const isActive = clampedValue > 0.02;
                            const isBeatBoundary = stepIndex % stepsPerBeat === 0;
                            const borderOpacity = isBeatBoundary ? 0.15 : 0.08;
                            const fillOpacity = isActive ? Math.max(0.14, clampedValue * 0.92) : 0.04;
                            return (
                              <div
                                key={`${lane.label}-${barNumber}-${stepIndex}`}
                                className="h-5 rounded-[2px] border transition-colors"
                                title={`${lane.label} bar ${barNumber} step ${stepIndex + 1}: ${formatNumber(clampedValue, 2)}`}
                                style={{
                                  borderColor: `rgba(255,255,255,${borderOpacity})`,
                                  backgroundColor: isActive
                                    ? `rgba(${lane.rgb}, ${fillOpacity})`
                                    : 'rgba(255,255,255,0.035)',
                                  boxShadow: isActive && clampedValue >= 0.55
                                    ? `inset 0 0 0 1px rgba(${lane.rgb}, 0.55), 0 0 8px rgba(${lane.rgb}, 0.14)`
                                    : undefined,
                                }}
                              />
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

const SidechainEnvelope = ({
  envelopeShape,
  pumpingRate,
  pumpingStrength,
  pumpingRegularity,
  pumpingConfidence,
}: {
  envelopeShape?: number[] | null;
  pumpingRate?: string | null;
  pumpingStrength?: number | null;
  pumpingRegularity?: number | null;
  pumpingConfidence?: number | null;
}) => {
  const resolvedStrength = pumpingStrength ?? 0;
  const resolvedRegularity = pumpingRegularity ?? 0;
  const resolvedConfidence = pumpingConfidence ?? 0;
  const contour =
    envelopeShape && envelopeShape.length > 0
      ? envelopeShape
      : Array.from({ length: 16 }, (_, index) => {
          const phase = (index / 15) * Math.PI * 3;
          const duck = Math.max(0, Math.sin(phase)) * (0.38 + resolvedStrength * 0.42);
          const stepAccent = index % 4 === 0 ? resolvedRegularity * 0.22 : 0;
          return 0.34 + duck + stepAccent;
        });

  const max = Math.max(...contour, 0.001);
  const w = 360;
  const h = 88;
  const pad = 6;

  const points = contour.map((v, i) => ({
    x: (i / (contour.length - 1)) * w,
    y: pad + (1 - v / max) * (h - pad * 2),
  }));

  let d = `M${points[0].x},${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const curr = points[i];
    const cpx = (prev.x + curr.x) / 2;
    d += ` C${cpx},${prev.y} ${cpx},${curr.y} ${curr.x},${curr.y}`;
  }
  const fillD = d + ` L${w},${h} L0,${h} Z`;

  const strengthLabel =
    resolvedStrength >= 0.7 ? 'heavy' : resolvedStrength >= 0.4 ? 'moderate' : 'subtle';

  return (
    <div className="flex h-full flex-col rounded-sm border border-[#242424] bg-[#101010] px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
      <div className="flex items-start justify-between gap-3">
        <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
          Sidechain Envelope
        </span>
        <span className="text-[8px] font-mono text-[#a78bfa75]">
          {pumpingRate ?? 'n/a'} · {strengthLabel}
        </span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="mt-3 h-[88px] w-full">
        <defs>
          <linearGradient id="sc-grad-panel" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#a78bfa" stopOpacity="0.3" />
            <stop offset="1" stopColor="#a78bfa" stopOpacity="0.02" />
          </linearGradient>
          <linearGradient id="sc-stroke-panel" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#8d72ee" stopOpacity="0.7" />
            <stop offset="0.55" stopColor="#b493ff" stopOpacity="0.95" />
            <stop offset="1" stopColor="#8d72ee" stopOpacity="0.7" />
          </linearGradient>
        </defs>
        {[0, 4, 8, 12].map((pos) => (
          <line
            key={pos}
            x1={(pos / 15) * w}
            y1="0"
            x2={(pos / 15) * w}
            y2={h}
            stroke="#1e1e1e"
            strokeWidth="0.5"
          />
        ))}
        <path d={fillD} fill="url(#sc-grad-panel)" />
        <path d={d} fill="none" stroke="url(#sc-stroke-panel)" strokeWidth="2.2" opacity="0.95" />
      </svg>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <div className="rounded-sm border border-[#232323] bg-[#121212] px-3 py-2">
          <span className="block text-[10px] font-mono uppercase tracking-wide text-text-secondary">
            Confidence
          </span>
          <span className="mt-1 block text-sm font-display font-bold text-text-primary">
            {Math.round(resolvedConfidence * 100)}%
          </span>
        </div>
        <div className="rounded-sm border border-[#232323] bg-[#121212] px-3 py-2">
          <span className="block text-[10px] font-mono uppercase tracking-wide text-text-secondary">
            Regularity
          </span>
          <span className="mt-1 block text-sm font-display font-bold text-text-primary">
            {formatNumber(resolvedRegularity, 2)}
          </span>
        </div>
      </div>
    </div>
  );
};

const EffectsFieldPanel = ({
  gatingDetected,
  gatingRate,
  gatingRegularity,
  gatingEventCount,
  pumpingStrength,
  pumpingRegularity,
  pumpingConfidence,
}: {
  gatingDetected?: boolean | null;
  gatingRate?: number | null;
  gatingRegularity?: number | null;
  gatingEventCount?: number | null;
  pumpingStrength?: number | null;
  pumpingRegularity?: number | null;
  pumpingConfidence?: number | null;
}) => {
  const rateLabel =
    gatingRate === 16
      ? '16th'
      : gatingRate === 8
        ? '8th'
        : gatingRate === 4
          ? 'quarter'
          : gatingRate != null
            ? `${gatingRate}`
            : 'n/a';

  if (gatingDetected) {
    const pulseStride = gatingRate === 16 ? 1 : gatingRate === 8 ? 2 : gatingRate === 4 ? 4 : 3;
    const pulseCells = Array.from({ length: 16 }, (_, index) => index % pulseStride === 0);

    return (
      <div className="flex h-full flex-col rounded-sm border border-[#242424] bg-[#101010] px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <span className="block text-[10px] font-mono uppercase tracking-wide text-text-secondary">
              Effects Field
            </span>
            <span className="mt-1 block text-[11px] font-mono uppercase tracking-[0.2em] text-[#fbbf24]">
              Gate Active
            </span>
          </div>
          <span className="text-[8px] font-mono text-[#fbbf2480]">{rateLabel}</span>
        </div>

        <div className="mt-4 grid grid-cols-8 gap-1.5">
          {pulseCells.map((active, index) => (
            <div
              key={index}
              className="rounded-sm border border-[#2e2614] bg-[#15120b]"
              style={{
                height: active ? 24 : 12,
                opacity: active ? 0.85 : 0.45,
                boxShadow: active ? '0 0 10px rgba(251,191,36,0.12)' : undefined,
              }}
            >
              <div
                className="h-full rounded-sm bg-gradient-to-t from-[#f59e0b] via-[#fbbf24] to-[#fde68a]"
                style={{ opacity: active ? 0.85 : 0.2 }}
              />
            </div>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-sm border border-[#2a2416] bg-[#121212] px-3 py-2">
            <span className="block text-[10px] font-mono uppercase tracking-wide text-text-secondary">
              Gate Events
            </span>
            <span className="mt-1 block text-sm font-display font-bold text-text-primary">
              {gatingEventCount ?? 'n/a'}
            </span>
          </div>
          <div className="rounded-sm border border-[#2a2416] bg-[#121212] px-3 py-2">
            <span className="block text-[10px] font-mono uppercase tracking-wide text-text-secondary">
              Gate Regularity
            </span>
            <div className="mt-2 h-[6px] rounded-full bg-[#1c1a12]">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[#f59e0b] to-[#fbbf24]"
                style={{ width: `${(gatingRegularity ?? 0) * 100}%`, opacity: 0.9 }}
              />
            </div>
          </div>
        </div>
      </div>
    );
  }

  const fallbackRows = [
    { label: 'Pump Strength', value: pumpingStrength ?? 0, color: '#a78bfa' },
    { label: 'Pump Regularity', value: pumpingRegularity ?? 0, color: '#60a5fa' },
    { label: 'Pump Confidence', value: pumpingConfidence ?? 0, color: '#34d399' },
  ];

  return (
    <div className="flex h-full flex-col rounded-sm border border-[#242424] bg-[#101010] px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="block text-[10px] font-mono uppercase tracking-wide text-text-secondary">
            Pump Matrix
          </span>
          <span className="mt-1 block text-[11px] font-mono uppercase tracking-[0.2em] text-[#a78bfa]">
            No Gating Effect
          </span>
        </div>
        <span className="text-[8px] font-mono text-[#8c8c8c]">{rateLabel}</span>
      </div>

      <div className="mt-4 space-y-3">
        {fallbackRows.map((row) => (
          <div key={row.label}>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                {row.label}
              </span>
              <span className="text-[8px] font-mono" style={{ color: `${row.color}cc` }}>
                {Math.round(row.value * 100)}%
              </span>
            </div>
            <div className="h-[6px] rounded-full bg-[#181818]">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${row.value * 100}%`,
                  background: `linear-gradient(90deg, ${row.color}66, ${row.color})`,
                  boxShadow: `0 0 10px ${row.color}24`,
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const PhraseStructureTimeline = ({ phraseGrid }: { phraseGrid: PhraseGrid }) => {
  const total = phraseGrid.totalBars || 1;
  const tiers = [
    { label: '16', items: phraseGrid.phrases16Bar, color: '#a78bfa', size: 16 },
    { label: '8', items: phraseGrid.phrases8Bar, color: '#fbbf24', size: 8 },
    { label: '4', items: phraseGrid.phrases4Bar, color: '#60a5fa', size: 4 },
  ];

  return (
    <div className="rounded-sm border border-[#1e1e1e] bg-[#141414] px-4 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
          Phrase Structure
        </span>
        <span className="text-[8px] font-mono uppercase tracking-[0.18em] text-[#666]">
          {total} bars
        </span>
      </div>
      <div className="space-y-2.5">
        {tiers.map((tier) => {
          if (!tier.items.length) return null;
          const segCount = tier.items.length;
          return (
            <div
              key={tier.label}
              className="grid grid-cols-[28px_minmax(0,1fr)] items-center gap-2"
            >
              <span
                className="text-[9px] font-mono font-bold uppercase tracking-[0.18em]"
                style={{ color: `${tier.color}bb` }}
              >
                {tier.label}
              </span>
              <div
                className="flex gap-1"
                style={{ height: tier.size === 16 ? 18 : tier.size === 8 ? 14 : 12 }}
              >
                {Array.from({ length: segCount }, (_, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-center rounded-[2px]"
                    style={{
                      flex: tier.size,
                      background: `linear-gradient(90deg, ${tier.color}22, ${tier.color}12)`,
                      border: `1px solid ${tier.color}45`,
                      boxShadow: `inset 0 1px 0 ${tier.color}18`,
                    }}
                  >
                    <span
                      className="font-mono"
                      style={{ fontSize: 8, color: `${tier.color}80` }}
                    >
                      {tier.label}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export function MeasurementDashboard({
  phase1,
  spectralArtifacts,
  measurementAvailability,
  apiBaseUrl,
  runId,
}: MeasurementDashboardProps) {
  const mixDoctorReport = useMemo(() => generateMixDoctorReport(phase1), [phase1]);

  // Local copy of spectral artifacts — updated after enhancement generation.
  const [localArtifacts, setLocalArtifacts] = useState(spectralArtifacts);
  useEffect(() => setLocalArtifacts(spectralArtifacts), [spectralArtifacts]);

  const [spectralTimeSeries, setSpectralTimeSeries] =
    useState<SpectralTimeSeriesData | null>(null);
  const [onsetData, setOnsetData] = useState<OnsetStrengthData | null>(null);
  const [chromaData, setChromaData] = useState<ChromaInteractiveData | null>(null);
  const [generating, setGenerating] = useState<Set<SpectralEnhancementKind>>(new Set());
  const dynamicCharacter = isDynamicCharacterObject(phase1.dynamicCharacter)
    ? phase1.dynamicCharacter
    : null;
  const textureCharacter = isTextureCharacterObject(phase1.textureCharacter)
    ? phase1.textureCharacter
    : null;
  const dynamicsTextureFallback = useMemo(
    () =>
      buildDynamicsTextureCopy(
        dynamicCharacter || textureCharacter
          ? dynamicCharacter
            ? 'texture'
            : 'dynamics'
          : 'both',
        measurementAvailability,
      ),
    [dynamicCharacter, measurementAvailability, textureCharacter],
  );
  const spectralBalanceStats = useMemo(() => {
    const values = SPECTRAL_ROW_CONFIG.map((row) => phase1.spectralBalance[row.key]);
    return {
      min: Math.min(...values),
      max: Math.max(...values),
    };
  }, [phase1.spectralBalance]);

  // Fetch spectral time-series
  useEffect(() => {
    if (!localArtifacts?.timeSeries || !apiBaseUrl || !runId) {
      setSpectralTimeSeries(null);
      return;
    }
    const controller = new AbortController();
    fetchSpectralTimeSeries(
      apiBaseUrl,
      runId,
      localArtifacts.timeSeries.artifactId,
      { signal: controller.signal },
    )
      .then(setSpectralTimeSeries)
      .catch(() => {});
    return () => controller.abort();
  }, [localArtifacts, apiBaseUrl, runId]);

  // Fetch onset strength data when artifact appears
  useEffect(() => {
    if (!localArtifacts?.onsetStrength || !apiBaseUrl || !runId) {
      setOnsetData(null);
      return;
    }
    const controller = new AbortController();
    fetchOnsetStrengthData(apiBaseUrl, runId, localArtifacts.onsetStrength.artifactId, { signal: controller.signal })
      .then(setOnsetData)
      .catch(() => {});
    return () => controller.abort();
  }, [localArtifacts?.onsetStrength, apiBaseUrl, runId]);

  // Fetch interactive chroma data when artifact appears
  useEffect(() => {
    if (!localArtifacts?.chromaInteractive || !apiBaseUrl || !runId) {
      setChromaData(null);
      return;
    }
    const controller = new AbortController();
    fetchChromaInteractiveData(apiBaseUrl, runId, localArtifacts.chromaInteractive.artifactId, { signal: controller.signal })
      .then(setChromaData)
      .catch(() => {});
    return () => controller.abort();
  }, [localArtifacts?.chromaInteractive, apiBaseUrl, runId]);

  const handleGenerate = useCallback(async (kind: SpectralEnhancementKind) => {
    if (!apiBaseUrl || !runId || generating.has(kind)) return;
    setGenerating((prev) => new Set(prev).add(kind));
    try {
      await generateSpectralEnhancement(apiBaseUrl, runId, kind);
      // Re-fetch the run snapshot to get updated artifact refs
      const snapshot = await getAnalysisRun(runId, { apiBaseUrl });
      if (snapshot.artifacts.spectral) {
        setLocalArtifacts(snapshot.artifacts.spectral);
      }
    } catch {
      // Silently handle — button returns to available state
    } finally {
      setGenerating((prev) => {
        const next = new Set(prev);
        next.delete(kind);
        return next;
      });
    }
  }, [apiBaseUrl, runId, generating]);

  return (
    <div data-testid="measurement-dashboard" className="space-y-4">
      {/* 1. Core Metrics */}
      <Section id="section-meas-core" number={1} title="Core Metrics">
        {/* Hero Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {/* BPM Tile */}
          <AccentMetricCard
            label="Tempo"
            value={formatNumber(phase1.bpm, 1)}
            unit="BPM"
            footer={
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <StatusBadge label={formatBpmScore(phase1.bpmConfidence)} tone="accent" compact />
                  {phase1.bpmAgreement !== undefined && phase1.bpmAgreement !== null && (
                    <StatusBadge
                      label={phase1.bpmAgreement ? 'Cross-Check ✓' : 'Cross-Check ✗'}
                      tone={phase1.bpmAgreement ? 'success' : 'error'}
                      compact
                    />
                  )}
                </div>
                {phase1.bpmDoubletime === true && phase1.bpmRawOriginal != null && (
                  <span className="block text-[8px] font-mono uppercase tracking-wide text-warning/80">
                    corrected from {formatNumber(phase1.bpmRawOriginal, 1)}
                  </span>
                )}
                {phase1.bpmPercival !== undefined && phase1.bpmPercival !== null && (
                  <span className="block text-[8px] font-mono uppercase tracking-wide text-text-secondary/50">
                    Percival {formatNumber(phase1.bpmPercival, 1)}
                  </span>
                )}
                {phase1.bpmSource != null && phase1.bpmSource !== 'rhythm_extractor' && (
                  <span className="block text-[8px] font-mono uppercase tracking-wide text-text-secondary/50">
                    Source {phase1.bpmSource.replace(/_/g, ' ')}
                  </span>
                )}
              </div>
            }
          />

          {/* Key Tile */}
          <AccentMetricCard
            label="Key Signature"
            value={<span className="truncate block">{phase1.key || '—'}</span>}
            footer={
              <div className="space-y-2">
                {phase1.keyProfile && (
                  <span className="block text-[8px] font-mono uppercase tracking-wide text-text-secondary/50">
                    Profile {phase1.keyProfile}
                  </span>
                )}
                <MetricBar value={phase1.keyConfidence} color="var(--color-accent)" glow />
                <span className="block text-[8px] font-mono uppercase tracking-wide text-text-secondary/60 tabular-nums">
                  CONF {Math.round(phase1.keyConfidence * 100)}%
                </span>
              </div>
            }
          />

          {/* Duration / Format Tile */}
          <AccentMetricCard
            label="Duration"
            value={formatDuration(phase1.durationSeconds)}
            unit={phase1.timeSignature}
            footer={(() => {
              const totalBars = resolveBarCount(phase1);
              const gridSegments = Math.min(Math.ceil(totalBars / 4), 24);
              const fullSegments = Math.floor(totalBars / 4);
              const remainder = (totalBars % 4) / 4;
              const meterStatus = isAssumedMeter(phase1) ? 'ASSUMED' : 'DETECTED';
              return (
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <StatusBadge label={meterStatus} tone="muted" compact />
                    <StatusBadge label={`${totalBars} BARS`} tone="accent" compact />
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-[8px] font-mono uppercase tracking-wide text-text-secondary/60">
                        Arrangement
                      </span>
                      {phase1.sampleRate !== undefined && phase1.sampleRate !== null && (
                        <span className="text-[8px] font-mono uppercase tracking-wide text-text-secondary/50 tabular-nums">
                          {(phase1.sampleRate / 1000).toFixed(1)} kHz
                        </span>
                      )}
                    </div>
                    <div className="flex gap-[3px] rounded-sm border border-border/30 bg-bg-app/70 p-1">
                      {Array.from({ length: gridSegments }).map((_, i) => (
                        <div
                          key={i}
                          className="h-2 flex-1 rounded-[2px]"
                          style={{
                            background:
                              i < fullSegments
                                ? `linear-gradient(90deg, rgba(255,107,0,${0.42 + (i / Math.max(gridSegments, 1)) * 0.28}), rgba(249,115,22,${0.58 + (i / Math.max(gridSegments, 1)) * 0.22}))`
                                : i === fullSegments && remainder > 0
                                  ? 'linear-gradient(90deg, rgba(255,107,0,0.28), rgba(249,115,22,0.18))'
                                  : 'rgba(255,255,255,0.04)',
                            opacity: i === fullSegments && remainder > 0 ? remainder : 1,
                          }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              );
            })()}
          />
        </div>

        {/* Genre Banner */}
        {phase1.genreDetail && (
          <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <div className={`w-2 h-2 rounded-full bg-accent ${phase1.genreDetail.confidence > 0.8 ? 'animate-pulse' : ''}`} />
                  <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">Genre Classification</span>
                </div>
                <span className="text-lg font-display font-bold text-text-primary capitalize block truncate">
                  {phase1.genreDetail.genre}
                </span>
                <TokenBadgeList
                  className="mt-2"
                  items={[
                    { label: phase1.genreDetail.genreFamily, tone: 'accent' },
                    ...(phase1.genreDetail.secondaryGenre
                      ? [{ label: phase1.genreDetail.secondaryGenre, tone: 'muted' as const }]
                      : []),
                  ]}
                />
              </div>
              <div className="shrink-0 text-right">
                <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">Conf</span>
                <span className="text-sm font-display font-bold text-text-primary ml-1.5 tabular-nums">
                  {Math.round(phase1.genreDetail.confidence * 100)}%
                </span>
              </div>
            </div>

            {/* Genre fingerprint — top scores as horizontal bars */}
            {phase1.genreDetail.topScores && phase1.genreDetail.topScores.length > 0 && (
              <div className="mt-3 pt-3 border-t border-border/50 space-y-1.5">
                <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">Genre Fingerprint</span>
                <div className="space-y-1">
                  {phase1.genreDetail.topScores.slice(0, 5).map((score, i) => {
                    const maxScore = phase1.genreDetail!.topScores[0]?.score || 1;
                    const pct = (score.score / maxScore) * 100;
                    const color = ['#ff6b00', '#fb923c', '#f59e0b', '#fdba74', '#fed7aa'][i] ?? '#fb923c';
                    return (
                      <div key={`${score.genre}-${i}`} className="flex items-center gap-2">
                        <span className="text-[8px] font-mono text-text-secondary/70 w-20 truncate text-right capitalize">
                          {score.genre}
                        </span>
                        <MetricBar
                          value={score.score}
                          min={0}
                          max={maxScore}
                          color={color}
                          glow={i === 0}
                          className="flex-1"
                          heightClassName="h-2"
                        />
                        <span className="text-[8px] font-mono text-text-secondary/50 tabular-nums w-8 text-right">
                          {(score.score * 100).toFixed(0)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tuning Detail */}
        {(phase1.tuningFrequency !== undefined && phase1.tuningFrequency !== null) && (
          <div className="flex items-center gap-3 px-1 flex-wrap">
            <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">Tuning</span>
            <span className="text-[9px] font-mono text-text-secondary/70 tabular-nums">
              {formatNumber(phase1.tuningFrequency, 1)} Hz
            </span>
            {phase1.tuningCents !== undefined && phase1.tuningCents !== null && (
              <DeltaBadge
                value={phase1.tuningCents}
                unit="cents"
                decimals={1}
                okThreshold={5}
                warnThreshold={12}
              />
            )}
          </div>
        )}
      </Section>

      {/* 2. Loudness & Dynamics */}
      <Section id="section-meas-loudness" number={2} title="Loudness & Dynamics">
        {/* Zone 1 — LUFS Meter Strip */}
        <div className="space-y-2">
          {/* Main meter */}
          <div className="relative h-8 bg-bg-surface-darker border border-border rounded-sm overflow-hidden">
            {/* Platform reference markers */}
            {PLATFORM_REFS.map((ref) => (
              <div
                key={ref.label}
                className="absolute top-0 bottom-0 border-l border-dashed border-text-secondary/25 z-10"
                style={{ left: `${lufsToPercent(ref.lufs)}%` }}
              >
                <span className="absolute -top-0.5 left-0.5 text-[7px] font-mono text-text-secondary/40 leading-none">
                  {ref.label}
                </span>
              </div>
            ))}
            {/* Meter fill */}
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${lufsToPercent(phase1.lufsIntegrated)}%` }}
              transition={{ duration: 0.6, ease: 'easeOut' }}
              className="absolute inset-y-0 left-0 rounded-sm"
              style={{ background: LUFS_METER_GRADIENT }}
            />
            {/* Value badge */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3, delay: 0.5 }}
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-bg-card/90 border border-border rounded-sm px-1.5 py-0.5 z-20"
            >
              <span className="text-sm font-mono font-bold text-text-primary tabular-nums">
                {formatNumber(phase1.lufsIntegrated, 1)}
              </span>
              <span className="text-[7px] font-mono text-text-secondary/50 ml-1">LUFS</span>
            </motion.div>
          </div>

          {/* Loudness hierarchy bars */}
          <div className="space-y-1">
            {[
              { label: 'MOM MAX', value: phase1.lufsMomentaryMax, color: '#ff6b00' },
              { label: 'ST MAX', value: phase1.lufsShortTermMax, color: '#fb923c' },
              { label: 'INTEGRATED', value: phase1.lufsIntegrated, color: '#ffd166' },
            ].filter((row) => row.value !== undefined && row.value !== null).map((row) => (
              <div key={row.label}>
                <MetricBarRow
                  label={row.label}
                  value={row.value}
                  min={-60}
                  max={0}
                  color={row.color}
                  valueLabel={`${formatNumber(row.value!, 1)} LUFS`}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Zone 2 — Headroom & Dynamics Panel */}
        <div className="border-t border-border pt-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Left — Headroom Diagram */}
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 flex flex-col items-center shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
              <span className="mb-3 self-start text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Headroom
              </span>
              <div className="relative w-8 bg-bg-panel border border-border/30 rounded-sm" style={{ height: 180 }}>
                {[
                  { label: '0 dB', value: 0 },
                  { label: '-6 dB', value: -6 },
                  { label: '-12 dB', value: -12 },
                  { label: '-18 dB', value: -18 },
                  { label: '-24 dB', value: -24 },
                ].map((tick) => (
                  <div
                    key={tick.label}
                    className="absolute left-0 right-0 border-t border-dashed border-text-secondary/18"
                    style={{ top: `${((3 - tick.value) / 51) * 100}%` }}
                  >
                    <span className="absolute -left-11 -top-1.5 text-[7px] font-mono text-text-secondary/35">
                      {tick.label}
                    </span>
                  </div>
                ))}
                {/* True Peak marker */}
                <div
                  className="absolute left-0 right-0 border-t-2 border-error/70 z-10"
                  style={{ top: `${Math.max(0, Math.min(100, ((3 - phase1.truePeak) / 51) * 100))}%` }}
                >
                  <span className="absolute left-7 -top-1.5 text-[7px] font-mono text-error/70 whitespace-nowrap">
                    TP {formatNumber(phase1.truePeak, 1)}
                  </span>
                </div>
                {/* Integrated LUFS marker */}
                <div
                  className="absolute left-0 right-0 border-t-2 border-accent/70 z-10"
                  style={{ top: `${Math.max(0, Math.min(100, ((3 - phase1.lufsIntegrated) / 51) * 100))}%` }}
                >
                  <span className="absolute left-7 -top-1.5 text-[7px] font-mono text-accent/70 whitespace-nowrap">
                    INT {formatNumber(phase1.lufsIntegrated, 1)}
                  </span>
                </div>
                {/* PLR gap fill */}
                <div
                  className="absolute left-0 right-0 bg-accent/10"
                  style={{
                    top: `${Math.max(0, Math.min(100, ((3 - phase1.truePeak) / 51) * 100))}%`,
                    bottom: `${100 - Math.max(0, Math.min(100, ((3 - phase1.lufsIntegrated) / 51) * 100))}%`,
                  }}
                />
                {/* PLR annotation */}
                {phase1.plr !== undefined && phase1.plr !== null && (
                  <div
                    className="absolute left-8 flex items-center z-20"
                    style={{
                      top: `${Math.max(0, Math.min(100, ((3 - phase1.truePeak) / 51) * 100))}%`,
                      bottom: `${100 - Math.max(0, Math.min(100, ((3 - phase1.lufsIntegrated) / 51) * 100))}%`,
                    }}
                  >
                    <span className="text-[9px] font-mono text-accent font-bold whitespace-nowrap">
                      PLR {formatNumber(phase1.plr, 1)}
                    </span>
                  </div>
                )}
                <span className="absolute left-1/2 bottom-1 -translate-x-1/2 text-[7px] font-mono uppercase tracking-wide text-text-secondary/35">
                  floor
                </span>
              </div>
            </div>

            {/* Right — Dynamics Metric Tiles */}
            <div className="grid grid-cols-2 gap-2 content-start">
              {[
                { label: 'Crest Factor', value: phase1.crestFactor, suffix: 'dB', decimals: 2 },
                { label: 'Dynamic Spread', value: phase1.dynamicSpread, suffix: '', decimals: 2 },
                { label: 'LUFS Range', value: phase1.lufsRange, suffix: 'LU', decimals: 1 },
                { label: 'True Peak', value: phase1.truePeak, suffix: 'dBTP', decimals: 2 },
              ].filter((tile) => tile.value !== undefined && tile.value !== null).map((tile) => (
                <div key={tile.label}>
                  <AccentMetricCard
                    label={tile.label}
                    value={formatNumber(tile.value!, tile.decimals)}
                    unit={tile.suffix ? <span className="text-[8px] font-mono text-text-secondary/45">{tile.suffix}</span> : undefined}
                    className="min-h-[110px]"
                  />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Zone 3 — Dynamics & Texture */}
        <div className="border-t border-border pt-3">
          <span data-text-role="subsection-title" className={[getTextRoleClassName('subsection-title'), 'block mb-3'].join(' ')}>
            Dynamics & Texture
          </span>
          {dynamicCharacter && textureCharacter ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="space-y-3 rounded-sm border border-border-light/60 bg-bg-surface-dark/70 p-4">
                <span data-text-role="subsection-title" className={[getTextRoleClassName('subsection-title'), 'block'].join(' ')}>
                  Dynamics
                </span>
                <MetricBarRow
                  label="Complexity"
                  value={dynamicCharacter.dynamicComplexity}
                  valueLabel={formatNumber(dynamicCharacter.dynamicComplexity, 3)}
                  min={0}
                  max={6}
                  color="#ff6b00"
                />
                <MetricBarRow
                  label="Estimated Loudness"
                  value={dynamicCharacter.loudnessDb}
                  valueLabel={`${formatNumber(dynamicCharacter.loudnessDb, 2)} dB`}
                  min={-30}
                  max={-6}
                  color="#fb923c"
                />
                <MetricBarRow
                  label="Log Attack Time"
                  value={dynamicCharacter.logAttackTime}
                  valueLabel={formatNumber(dynamicCharacter.logAttackTime, 3)}
                  min={-5}
                  max={-1.5}
                  color="#38bdf8"
                />
                <MetricBarRow
                  label="Attack Time Std Dev"
                  value={dynamicCharacter.attackTimeStdDev}
                  valueLabel={`${formatNumber(dynamicCharacter.attackTimeStdDev, 4)} s`}
                  min={0}
                  max={0.1}
                  color="#a78bfa"
                />
              </div>
              <div className="space-y-3 rounded-sm border border-border-light/60 bg-bg-surface-dark/70 p-4">
                <span data-text-role="subsection-title" className={[getTextRoleClassName('subsection-title'), 'block'].join(' ')}>
                  Texture
                </span>
                <MetricBarRow
                  label="Texture Score"
                  value={textureCharacter.textureScore}
                  valueLabel={formatNumber(textureCharacter.textureScore, 3)}
                  min={0}
                  max={1}
                  color="#f97316"
                />
                <MetricBarRow
                  label="Low-Band Flatness"
                  value={textureCharacter.lowBandFlatness}
                  valueLabel={formatNumber(textureCharacter.lowBandFlatness, 3)}
                  min={0}
                  max={1}
                  color="#facc15"
                />
                <MetricBarRow
                  label="Mid-Band Flatness"
                  value={textureCharacter.midBandFlatness}
                  valueLabel={formatNumber(textureCharacter.midBandFlatness, 3)}
                  min={0}
                  max={1}
                  color="#14b8a6"
                />
                <MetricBarRow
                  label="High-Band Flatness"
                  value={textureCharacter.highBandFlatness}
                  valueLabel={formatNumber(textureCharacter.highBandFlatness, 3)}
                  min={0}
                  max={1}
                  color="#60a5fa"
                />
                <MetricBarRow
                  label="Inharmonicity"
                  value={textureCharacter.inharmonicity}
                  valueLabel={formatNumber(textureCharacter.inharmonicity, 3)}
                  min={0}
                  max={0.25}
                  color="#f472b6"
                />
              </div>
            </div>
          ) : dynamicCharacter || textureCharacter ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {dynamicCharacter ? (
                <div className="space-y-3 rounded-sm border border-border-light/60 bg-bg-surface-dark/70 p-4">
                  <span className="text-[10px] font-mono uppercase tracking-[0.16em] text-text-secondary block">
                    Dynamics
                  </span>
                  <MetricBarRow
                    label="Complexity"
                    value={dynamicCharacter.dynamicComplexity}
                    valueLabel={formatNumber(dynamicCharacter.dynamicComplexity, 3)}
                    min={0}
                    max={6}
                    color="#ff6b00"
                  />
                  <MetricBarRow
                    label="Estimated Loudness"
                    value={dynamicCharacter.loudnessDb}
                    valueLabel={`${formatNumber(dynamicCharacter.loudnessDb, 2)} dB`}
                    min={-30}
                    max={-6}
                    color="#fb923c"
                  />
                  <MetricBarRow
                    label="Log Attack Time"
                    value={dynamicCharacter.logAttackTime}
                    valueLabel={formatNumber(dynamicCharacter.logAttackTime, 3)}
                    min={-5}
                    max={-1.5}
                    color="#38bdf8"
                  />
                  <MetricBarRow
                    label="Attack Time Std Dev"
                    value={dynamicCharacter.attackTimeStdDev}
                    valueLabel={`${formatNumber(dynamicCharacter.attackTimeStdDev, 4)} s`}
                    min={0}
                    max={0.1}
                    color="#a78bfa"
                  />
                </div>
              ) : (
                <UnavailableMeasurementCard
                  title={dynamicsTextureFallback.title}
                  description={dynamicsTextureFallback.description}
                  detail={dynamicsTextureFallback.detail}
                />
              )}
              {textureCharacter ? (
                <div className="space-y-3 rounded-sm border border-border-light/60 bg-bg-surface-dark/70 p-4">
                  <span className="text-[10px] font-mono uppercase tracking-[0.16em] text-text-secondary block">
                    Texture
                  </span>
                  <MetricBarRow
                    label="Texture Score"
                    value={textureCharacter.textureScore}
                    valueLabel={formatNumber(textureCharacter.textureScore, 3)}
                    min={0}
                    max={1}
                    color="#f97316"
                  />
                  <MetricBarRow
                    label="Low-Band Flatness"
                    value={textureCharacter.lowBandFlatness}
                    valueLabel={formatNumber(textureCharacter.lowBandFlatness, 3)}
                    min={0}
                    max={1}
                    color="#facc15"
                  />
                  <MetricBarRow
                    label="Mid-Band Flatness"
                    value={textureCharacter.midBandFlatness}
                    valueLabel={formatNumber(textureCharacter.midBandFlatness, 3)}
                    min={0}
                    max={1}
                    color="#14b8a6"
                  />
                  <MetricBarRow
                    label="High-Band Flatness"
                    value={textureCharacter.highBandFlatness}
                    valueLabel={formatNumber(textureCharacter.highBandFlatness, 3)}
                    min={0}
                    max={1}
                    color="#60a5fa"
                  />
                  <MetricBarRow
                    label="Inharmonicity"
                    value={textureCharacter.inharmonicity}
                    valueLabel={formatNumber(textureCharacter.inharmonicity, 3)}
                    min={0}
                    max={0.25}
                    color="#f472b6"
                  />
                </div>
              ) : (
                <UnavailableMeasurementCard
                  title={dynamicsTextureFallback.title}
                  description={dynamicsTextureFallback.description}
                  detail={dynamicsTextureFallback.detail}
                />
              )}
            </div>
          ) : (
            <AccentMetricCard
              label="Dynamics & Texture"
              value={dynamicsTextureFallback.title}
              unit={<span className="text-[8px] font-mono uppercase tracking-wide text-text-secondary/45">Unavailable</span>}
              accent="warning"
              footer={
                <div className="space-y-2">
                  <p className="text-[10px] font-mono uppercase tracking-[0.14em] text-text-secondary/70">
                    {dynamicsTextureFallback.description}
                  </p>
                  {dynamicsTextureFallback.detail ? (
                    <p className="text-[10px] font-mono uppercase tracking-[0.12em] text-text-secondary/55">
                      {dynamicsTextureFallback.detail}
                    </p>
                  ) : null}
                </div>
              }
            />
          )}
        </div>
      </Section>

      {/* 3. MixDoctor */}
      <Section id="section-meas-mixdoctor" number={3} title="MixDoctor">
        <MixDoctorPanel report={mixDoctorReport} />
      </Section>

      {/* 4. Spectral */}
      <Section id="section-meas-spectral" testId="spectral-section" number={4} title="Spectral">
        <div className="space-y-3">
          <div>
            <span data-text-role="subsection-title" className={getTextRoleClassName('subsection-title')}>
              Spectral Balance
            </span>
            <div className="mt-2 space-y-3">
              {SPECTRAL_ROW_CONFIG.map((row) => (
                <div key={row.key}>
                  <MetricBarRow
                    label={row.label}
                    value={phase1.spectralBalance[row.key]}
                    valueLabel={`${formatNumber(phase1.spectralBalance[row.key], 2)} dB`}
                    min={spectralBalanceStats.min}
                    max={spectralBalanceStats.max}
                    color={SPECTRAL_BALANCE_PALETTE[row.key]}
                  />
                </div>
              ))}
            </div>
          </div>
          {phase1.spectralDetail && (
            <div className="border-t border-border/30 pt-2 mt-2 space-y-3">
              {phase1.spectralDetail.spectralCentroidMean !== undefined &&
                phase1.spectralDetail.spectralCentroidMean !== null && (
                  <MetricBarRow
                    label="Centroid Mean"
                    value={phase1.spectralDetail.spectralCentroidMean}
                    min={0}
                    max={12000}
                    color={SPECTRAL_BALANCE_PALETTE.highs}
                    valueLabel={`${formatNumber(phase1.spectralDetail.spectralCentroidMean, 1)} Hz`}
                    sparkline={
                      spectralTimeSeries?.spectralCentroid &&
                      spectralTimeSeries.spectralCentroid.length > 1 && (
                        <Sparkline values={spectralTimeSeries.spectralCentroid} color={SPECTRAL_BALANCE_PALETTE.highs} />
                      )
                    }
                  />
                )}
              {phase1.spectralDetail.spectralRolloffMean !== undefined &&
                phase1.spectralDetail.spectralRolloffMean !== null && (
                  <MetricBarRow
                    label="Rolloff Mean"
                    value={phase1.spectralDetail.spectralRolloffMean}
                    min={0}
                    max={22050}
                    color={SPECTRAL_BALANCE_PALETTE.brilliance}
                    valueLabel={`${formatNumber(phase1.spectralDetail.spectralRolloffMean, 1)} Hz`}
                    sparkline={
                      spectralTimeSeries?.spectralRolloff &&
                      spectralTimeSeries.spectralRolloff.length > 1 && (
                        <Sparkline values={spectralTimeSeries.spectralRolloff} color={SPECTRAL_BALANCE_PALETTE.brilliance} />
                      )
                    }
                  />
                )}
              {phase1.spectralDetail.spectralBandwidthMean !== undefined &&
                phase1.spectralDetail.spectralBandwidthMean !== null && (
                  <MetricBarRow
                    label="Bandwidth Mean"
                    value={phase1.spectralDetail.spectralBandwidthMean}
                    min={0}
                    max={12000}
                    color={SPECTRAL_BALANCE_PALETTE.upperMids}
                    valueLabel={`${formatNumber(phase1.spectralDetail.spectralBandwidthMean, 1)} Hz`}
                    sparkline={
                      spectralTimeSeries?.spectralBandwidth &&
                      spectralTimeSeries.spectralBandwidth.length > 1 && (
                        <Sparkline values={spectralTimeSeries.spectralBandwidth} color={SPECTRAL_BALANCE_PALETTE.upperMids} />
                      )
                    }
                  />
                )}
              {phase1.spectralDetail.spectralFlatnessMean !== undefined &&
                phase1.spectralDetail.spectralFlatnessMean !== null && (
                  <MetricBarRow
                    label="Flatness Mean"
                    value={phase1.spectralDetail.spectralFlatnessMean}
                    min={0}
                    max={1}
                    color={SPECTRAL_BALANCE_PALETTE.lowMids}
                    valueLabel={formatNumber(phase1.spectralDetail.spectralFlatnessMean, 6)}
                    sparkline={
                      spectralTimeSeries?.spectralFlatness &&
                      spectralTimeSeries.spectralFlatness.length > 1 && (
                        <Sparkline values={spectralTimeSeries.spectralFlatness} color={SPECTRAL_BALANCE_PALETTE.lowMids} />
                      )
                    }
                  />
                )}
            </div>
          )}
        </div>

        {/* Enhancement Toolbar */}
        {apiBaseUrl && runId && (
          <div data-testid="spectral-enhancements-toolbar" className="border-t border-border pt-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mr-1">
                Enhancements
              </span>
              {([
                { kind: 'cqt' as SpectralEnhancementKind, label: 'CQT', done: localArtifacts?.spectrograms.some((s) => s.kind === 'spectrogram_cqt') },
                { kind: 'hpss' as SpectralEnhancementKind, label: 'HPSS', done: localArtifacts?.spectrograms.some((s) => s.kind === 'spectrogram_harmonic') },
                { kind: 'onset' as SpectralEnhancementKind, label: 'Onset', done: !!localArtifacts?.onsetStrength },
                { kind: 'chroma_interactive' as SpectralEnhancementKind, label: 'Chroma', done: !!localArtifacts?.chromaInteractive },
              ]).map(({ kind, label, done }) =>
                done ? (
                  <React.Fragment key={kind}>
                    <StatusBadge
                      label={`${label} ✓`}
                      tone="success"
                      compact
                    />
                  </React.Fragment>
                ) : (
                  <React.Fragment key={kind}>
                    <OutlinePillButton
                      onClick={() => handleGenerate(kind)}
                      disabled={generating.has(kind)}
                      tone="accent"
                      label={generating.has(kind) ? `${label}...` : `Generate ${label}`}
                    />
                  </React.Fragment>
                ),
              )}
            </div>
          </div>
        )}

        <SpectralCursorProvider>
          {localArtifacts && apiBaseUrl && runId && localArtifacts.spectrograms.length > 0 && (
            <div data-testid="spectral-visualizations-panel" className="border-t border-border pt-3">
              <SpectrogramViewer
                spectrograms={localArtifacts.spectrograms}
                apiBaseUrl={apiBaseUrl}
                runId={runId}
                durationSeconds={phase1.durationSeconds}
              />
            </div>
          )}

          {spectralTimeSeries && (
            <div className="border-t border-border pt-3">
              <SpectralEvolutionChart data={spectralTimeSeries} onsetStrength={onsetData} />
            </div>
          )}

          {chromaData && (
            <div className="border-t border-border pt-3">
              <ChromaHeatmap data={chromaData} />
            </div>
          )}
        </SpectralCursorProvider>

        {phase1.spectralDetail && (
          <>
            {phase1.spectralDetail.mfcc && phase1.spectralDetail.mfcc.length > 0 && (
              <BarChart
                values={phase1.spectralDetail.mfcc.slice(0, 8)}
                count={8}
                label="MFCC (first 8)"
              />
            )}
            {phase1.spectralDetail.chroma && phase1.spectralDetail.chroma.length > 0 && (
              <BarChart
                values={phase1.spectralDetail.chroma}
                count={12}
                label="Chroma (12 pitches)"
              />
            )}
            {phase1.spectralDetail.barkBands && phase1.spectralDetail.barkBands.length > 0 && (
              <BarChart
                values={phase1.spectralDetail.barkBands.slice(0, 16)}
                count={16}
                label="Bark Bands"
              />
            )}
            {phase1.spectralDetail.erbBands && phase1.spectralDetail.erbBands.length > 0 && (
              <BarChart
                values={phase1.spectralDetail.erbBands.slice(0, 16)}
                count={16}
                label="ERB Bands"
              />
            )}
            {phase1.spectralDetail.spectralContrast &&
              phase1.spectralDetail.spectralContrast.length > 0 && (
                <MiniHeatmap
                  title="Spectral Contrast"
                  rows={[
                    { label: 'Contrast', values: phase1.spectralDetail.spectralContrast.slice(0, 7) },
                    ...(phase1.spectralDetail.spectralValley && phase1.spectralDetail.spectralValley.length > 0
                      ? [{ label: 'Valley', values: phase1.spectralDetail.spectralValley.slice(0, 7) }]
                      : []),
                  ]}
                  cellLabels={['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7']}
                />
              )}
          </>
        )}

        {phase1.essentiaFeatures && (
          <>
            <div className="border-t border-border pt-3">
              <span data-text-role="subsection-title" className={getTextRoleClassName('subsection-title')}>
                Essentia Features
              </span>
            </div>
            {phase1.essentiaFeatures.zeroCrossingRate !== undefined &&
              phase1.essentiaFeatures.zeroCrossingRate !== null && (
                <MetricBarRow
                  label="Zero Crossing Rate"
                  value={phase1.essentiaFeatures.zeroCrossingRate}
                  min={0}
                  max={0.5}
                  color="#ff8c42"
                  valueLabel={formatNumber(phase1.essentiaFeatures.zeroCrossingRate, 3)}
                />
              )}
            {phase1.essentiaFeatures.hfc !== undefined && phase1.essentiaFeatures.hfc !== null && (
              <MetricBarRow
                label="High Frequency Content"
                value={phase1.essentiaFeatures.hfc}
                min={0}
                max={1}
                color="#38bdf8"
                valueLabel={formatNumber(phase1.essentiaFeatures.hfc, 2)}
              />
            )}
            {phase1.essentiaFeatures.spectralComplexity !== undefined &&
              phase1.essentiaFeatures.spectralComplexity !== null && (
                <MetricBarRow
                  label="Spectral Complexity"
                  value={phase1.essentiaFeatures.spectralComplexity}
                  min={0}
                  max={60}
                  color="#a78bfa"
                  valueLabel={formatNumber(phase1.essentiaFeatures.spectralComplexity, 2)}
                />
              )}
            {phase1.essentiaFeatures.dissonance !== undefined &&
              phase1.essentiaFeatures.dissonance !== null && (
                <MetricBarRow
                  label="Dissonance"
                  value={phase1.essentiaFeatures.dissonance}
                  min={0}
                  max={1}
                  color="#ef4444"
                  valueLabel={formatNumber(phase1.essentiaFeatures.dissonance, 2)}
                />
              )}
          </>
        )}
      </Section>

      {/* 5. Stereo Field */}
      <Section id="section-meas-stereo" number={5} title="Stereo Field">
        <MetricBarRow
          label="Stereo Width"
          value={phase1.stereoWidth}
          min={0}
          max={1}
          color="#38bdf8"
          leftLabel="narrow"
          rightLabel="wide"
          valueLabel={formatNumber(phase1.stereoWidth, 2)}
        />
        <MetricBarRow
          label="Stereo Correlation"
          value={phase1.stereoCorrelation}
          min={-1}
          max={1}
          color="#ff6b00"
          leftLabel="anti-phase"
          rightLabel="mono"
          valueLabel={formatNumber(phase1.stereoCorrelation, 2)}
        />
        {phase1.monoCompatible !== undefined && phase1.monoCompatible !== null && (
          <MetricRow
            label="Mono Compatible"
            value={<StatusBadge label={phase1.monoCompatible ? 'Yes' : 'No'} tone={phase1.monoCompatible ? 'success' : 'error'} compact />}
          />
        )}
        {phase1.stereoDetail && (
          <>
            {phase1.stereoDetail.subBassCorrelation !== undefined &&
              phase1.stereoDetail.subBassCorrelation !== null && (
                <MetricBarRow
                  label="Sub-Bass Correlation"
                  value={phase1.stereoDetail.subBassCorrelation}
                  min={-1}
                  max={1}
                  color="#14b8a6"
                  leftLabel="anti-phase"
                  rightLabel="mono"
                  valueLabel={formatNumber(phase1.stereoDetail.subBassCorrelation, 2)}
                />
              )}
            {phase1.stereoDetail.subBassMono !== undefined &&
              phase1.stereoDetail.subBassMono !== null && (
                <MetricRow
                  label="Sub-Bass Mono"
                  value={<StatusBadge label={phase1.stereoDetail.subBassMono ? 'Yes' : 'No'} tone={phase1.stereoDetail.subBassMono ? 'success' : 'error'} compact />}
                />
              )}
          </>
        )}
        {phase1.segmentStereo && phase1.segmentStereo.length > 0 && (
          <>
            <div className="border-t border-border pt-3 mt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Segment Stereo
              </span>
            </div>
            <StyledDataTable
              data={phase1.segmentStereo}
              columns={[
                {
                  key: 'segmentIndex',
                  label: 'Segment',
                  monospace: true,
                  render: (row) => String(row.segmentIndex ?? '—'),
                },
                {
                  key: 'width',
                  label: 'Width',
                  render: (row) => (
                    <div className="space-y-1">
                      <div className="text-right font-mono tabular-nums text-text-primary">
                        {formatNumber(row.stereoWidth, 2)}
                      </div>
                      <MetricBar
                        value={row.stereoWidth}
                        min={0}
                        max={1}
                        color="#38bdf8"
                        heightClassName="h-1.5"
                      />
                    </div>
                  ),
                },
                {
                  key: 'corr',
                  label: 'Corr',
                  render: (row) => (
                    <div className="space-y-1">
                      <div className="text-right font-mono tabular-nums text-text-primary">
                        {formatNumber(row.stereoCorrelation, 2)}
                      </div>
                      <MetricBar
                        value={row.stereoCorrelation}
                        min={-1}
                        max={1}
                        color="#ff6b00"
                        heightClassName="h-1.5"
                      />
                    </div>
                  ),
                },
              ]}
            />
          </>
        )}
      </Section>

      {/* 6. Rhythm & Groove */}
      <Section id="section-meas-rhythm" number={6} title="Rhythm & Groove">
        <div className="flex flex-col gap-4 md:flex-row md:items-stretch">
          <BreathingBpmPulse bpm={phase1.bpm} bpmSource={phase1.bpmSource} />
          <div className="flex-1 grid grid-cols-1 gap-2 md:grid-cols-2">
            {phase1.rhythmDetail && (
              <>
                <ComparativeMetricTile
                  metricKey="groove"
                  value={phase1.rhythmDetail.grooveAmount}
                  delay={0}
                />
                <ComparativeMetricTile
                  metricKey="stability"
                  value={
                    (phase1.rhythmDetail.tempoStability ??
                      1 - phase1.rhythmDetail.grooveAmount) * 100
                  }
                  delay={0.08}
                />
              </>
            )}
            {phase1.danceability && (
              <ComparativeMetricTile
                metricKey="danceability"
                value={phase1.danceability.danceability}
                delay={0.16}
              />
            )}
            {phase1.rhythmDetail && (
              <ComparativeMetricTile
                metricKey="onsetRate"
                value={phase1.rhythmDetail.onsetRate}
                delay={0.24}
              />
            )}
          </div>
        </div>

        {phase1.rhythmTimeline?.windows && phase1.rhythmTimeline.windows.length > 0 && (
          <div className="border-t border-border pt-3">
            <RhythmGridPanel phase1={phase1} />
          </div>
        )}

        {(phase1.grooveDetail || phase1.beatsLoudness) && (
          <div className="border-t border-border pt-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {phase1.grooveDetail && (
                <div className="bg-[#141414] border border-[#1e1e1e] rounded-sm p-3">
                  <div className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-3">
                    Swing
                  </div>
                  <div className="space-y-3">
                    {[
                      { label: 'KICK', value: phase1.grooveDetail.kickSwing, color: '#ff4444' },
                      { label: 'HH', value: phase1.grooveDetail.hihatSwing, color: '#60a5fa' },
                    ].map((s) => (
                      <div key={s.label}>
                        <div className="mb-1.5 flex items-center justify-between gap-3">
                          <span
                            className="text-[10px] font-mono uppercase tracking-[0.12em]"
                            style={{ color: `${s.color}80` }}
                          >
                            {s.label}
                          </span>
                          <span
                            className="text-[10px] font-mono font-bold"
                            style={{ color: s.color }}
                          >
                            {formatNumber(s.value, 2)}
                          </span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-sm border border-[#202020] bg-[#1a1a1a]">
                          <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${s.value * 100}%` }}
                            transition={{ duration: 0.5, ease: 'easeOut' }}
                            className="h-full rounded-sm"
                            style={{ background: s.color, opacity: 0.7 }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {phase1.beatsLoudness && (
                <div className="bg-[#141414] border border-[#1e1e1e] rounded-sm p-3">
                  <HorizontalDominance
                    kickRatio={phase1.beatsLoudness.kickDominantRatio}
                    midRatio={phase1.beatsLoudness.midDominantRatio}
                    highRatio={phase1.beatsLoudness.highDominantRatio}
                  />
                  <div className="mt-3 grid grid-cols-3 gap-3">
                    <div>
                      <span className="block text-[10px] font-mono text-text-secondary">Beat Count</span>
                      <span className="text-sm font-display font-bold text-text-primary">
                        {formatNumber(phase1.beatsLoudness.beatCount, 0)}
                      </span>
                    </div>
                    <div>
                      <span className="block text-[10px] font-mono text-text-secondary">Mean Loud</span>
                      <span className="text-sm font-display font-bold text-text-primary">
                        {formatNumber(phase1.beatsLoudness.meanBeatLoudness, 2)}
                      </span>
                    </div>
                    <div>
                      <span className="block text-[10px] font-mono text-text-secondary">Variation</span>
                      <span className="text-sm font-display font-bold text-text-primary">
                        {formatNumber(phase1.beatsLoudness.beatLoudnessVariation, 2)}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {(phase1.sidechainDetail ||
          (phase1.effectsDetail && phase1.effectsDetail.gatingDetected)) && (
          <div className="border-t border-border pt-3 space-y-2">
            <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary block">
              Sidechain & Effects
            </span>
            <div className="rounded-sm border border-[#1e1e1e] bg-[#141414] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
              <div className="grid gap-3 lg:grid-cols-[minmax(0,1.35fr)_minmax(260px,0.9fr)]">
                <SidechainEnvelope
                  envelopeShape={phase1.sidechainDetail?.envelopeShape}
                  pumpingRate={phase1.sidechainDetail?.pumpingRate}
                  pumpingStrength={phase1.sidechainDetail?.pumpingStrength}
                  pumpingRegularity={phase1.sidechainDetail?.pumpingRegularity}
                  pumpingConfidence={phase1.sidechainDetail?.pumpingConfidence}
                />
                <EffectsFieldPanel
                  gatingDetected={phase1.effectsDetail?.gatingDetected}
                  gatingRate={phase1.effectsDetail?.gatingRate ?? null}
                  gatingRegularity={phase1.effectsDetail?.gatingRegularity ?? null}
                  gatingEventCount={phase1.effectsDetail?.gatingEventCount ?? null}
                  pumpingStrength={phase1.sidechainDetail?.pumpingStrength ?? null}
                  pumpingRegularity={phase1.sidechainDetail?.pumpingRegularity ?? null}
                  pumpingConfidence={phase1.sidechainDetail?.pumpingConfidence ?? null}
                />
              </div>
            </div>
          </div>
        )}

        {phase1.rhythmDetail?.phraseGrid && (
          <div className="border-t border-border pt-3">
            <PhraseStructureTimeline phraseGrid={phase1.rhythmDetail.phraseGrid} />
          </div>
        )}

        {phase1.danceability && (
          <div className="border-t border-border pt-3">
            <MetricRow
              label="DFA (Rhythmic Complexity)"
              value={formatNumber(phase1.danceability.dfa, 3)}
            />
          </div>
        )}
      </Section>

      {/* 7. Harmony */}
      <Section id="section-meas-harmony" number={7} title="Harmony">
        {phase1.chordDetail && (
          <>
            {phase1.chordDetail.progression && phase1.chordDetail.progression.length > 0 && (
              <>
                <div>
                  <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                    Chord Progression
                  </span>
                  <ChordTokenRow chords={phase1.chordDetail.progression} />
                </div>
              </>
            )}
            {phase1.chordDetail.chordSequence && phase1.chordDetail.chordSequence.length > 0 && (
              <>
                <div className="border-t border-border pt-3">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                    Chord Sequence
                  </span>
                  <ChordTokenRow chords={phase1.chordDetail.chordSequence} />
                </div>
              </>
            )}
            {phase1.chordDetail.chordStrength !== undefined &&
              phase1.chordDetail.chordStrength !== null && (
                <MetricBarRow
                  label="Chord Strength"
                  value={phase1.chordDetail.chordStrength}
                  min={0}
                  max={1}
                  color="#ff6b00"
                  valueLabel={formatNumber(phase1.chordDetail.chordStrength, 2)}
                />
              )}
            {phase1.chordDetail.dominantChords && phase1.chordDetail.dominantChords.length > 0 && (
              <>
                <div className="border-t border-border pt-3">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                    Dominant Chords
                  </span>
                  <TokenBadgeList
                    className="mt-2"
                    items={phase1.chordDetail.dominantChords.map((chord) => ({
                      label: chord,
                      tone: chordToneForLabel(chord),
                    }))}
                  />
                </div>
              </>
            )}
          </>
        )}
        {phase1.segmentKey && phase1.segmentKey.length > 0 && (
          <>
            <div className={`${phase1.chordDetail ? 'border-t border-border pt-3 mt-3' : ''}`}>
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Segment Keys
              </span>
            </div>
            <StyledDataTable
              data={phase1.segmentKey}
              columns={[
                {
                  key: 'segmentIndex',
                  label: 'Segment',
                  monospace: true,
                  render: (row) => (row.segmentIndex === null || row.segmentIndex === undefined ? '—' : String(row.segmentIndex)),
                },
                {
                  key: 'key',
                  label: 'Key',
                  render: (row) => (row.key === null || row.key === undefined || row.key === '' ? '—' : row.key),
                },
                {
                  key: 'confidence',
                  label: 'Confidence',
                  render: (row) => (
                    <div className="space-y-1">
                      <div className="text-right font-mono tabular-nums text-text-primary">
                        {formatNumber(row.keyConfidence, 2)}
                      </div>
                      <MetricBar
                        value={row.keyConfidence}
                        min={0}
                        max={1}
                        color="#ff6b00"
                        heightClassName="h-1.5"
                      />
                    </div>
                  ),
                },
              ]}
            />
          </>
        )}
        {phase1.pitchDetail && phase1.pitchDetail.stems && (
          <>
            <div className="border-t border-border pt-3 mt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Pitch Extraction ({phase1.pitchDetail.method})
              </span>
            </div>
            {Object.entries(phase1.pitchDetail.stems).map(([stemName, stem]) => (
              <div key={stemName} className="space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wide text-accent">
                  {stemName}
                </span>
                <MetricRow
                  label="Median Pitch"
                  value={stem.medianPitchHz !== null ? `${stem.medianPitchHz} Hz` : '—'}
                />
                <MetricRow
                  label="Pitch Range (5–95%)"
                  value={
                    stem.pitchRangeLowHz !== null && stem.pitchRangeHighHz !== null
                      ? `${stem.pitchRangeLowHz} – ${stem.pitchRangeHighHz} Hz`
                      : '—'
                  }
                />
                <MetricRow
                  label="Mean Periodicity"
                  value={formatNumber(stem.meanPeriodicity, 3)}
                />
                <MetricRow
                  label="Voiced Frames"
                  value={`${stem.voicedFramePercent}%`}
                />
              </div>
            ))}
          </>
        )}
      </Section>

      {/* 8. Structure & Arrangement */}
      <Section id="section-meas-structure" number={8} title="Structure & Arrangement">
        {phase1.structure && (
          <>
            {phase1.structure.segmentCount !== undefined &&
              phase1.structure.segmentCount !== null && (
                <MetricRow
                  label="Segment Count"
                  value={formatNumber(phase1.structure.segmentCount, 0)}
                />
              )}
          </>
        )}
        {phase1.arrangementDetail && (
          <>
            {phase1.arrangementDetail.noveltyMean !== undefined &&
              phase1.arrangementDetail.noveltyMean !== null && (
                <MetricRow
                  label="Novelty Mean"
                  value={formatNumber(phase1.arrangementDetail.noveltyMean, 2)}
                />
              )}
            {phase1.arrangementDetail.noveltyStdDev !== undefined &&
              phase1.arrangementDetail.noveltyStdDev !== null && (
                <MetricRow
                  label="Novelty Std Dev"
                  value={formatNumber(phase1.arrangementDetail.noveltyStdDev, 2)}
                />
              )}
            {phase1.arrangementDetail.sectionCount !== undefined &&
              phase1.arrangementDetail.sectionCount !== null && (
                <MetricRow
                  label="Section Count"
                  value={formatNumber(phase1.arrangementDetail.sectionCount, 0)}
                />
              )}
          </>
        )}
        {phase1.segmentLoudness && phase1.segmentLoudness.length > 0 && (
          <>
            <div className="border-t border-border pt-3 mt-3">
              <span data-text-role="subsection-title" className={getTextRoleClassName('subsection-title')}>
                Segment Loudness
              </span>
            </div>
            <StyledDataTable
              data={phase1.segmentLoudness}
              columns={[
                {
                  key: 'segmentIndex',
                  label: 'Segment',
                  monospace: true,
                  render: (row) => String(row.segmentIndex !== undefined ? row.segmentIndex : '—'),
                },
                {
                  key: 'start',
                  label: 'Start (s)',
                  monospace: true,
                  render: (row) => formatNumber(row.start, 1),
                },
                {
                  key: 'end',
                  label: 'End (s)',
                  monospace: true,
                  render: (row) => formatNumber(row.end, 1),
                },
                {
                  key: 'lufs',
                  label: 'LUFS',
                  render: (row) => (
                    <span
                      className="font-mono font-bold tabular-nums"
                      style={{ color: loudnessToneColor(row.lufs) }}
                    >
                      {formatNumber(row.lufs, 1)}
                    </span>
                  ),
                },
              ]}
            />
          </>
        )}
        {phase1.segmentSpectral && phase1.segmentSpectral.length > 0 && (
          <>
            <div className="border-t border-border pt-3 mt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Segment Spectral
              </span>
            </div>
            <StyledDataTable
              data={phase1.segmentSpectral}
              columns={[
                {
                  key: 'segmentIndex',
                  label: 'Segment',
                  monospace: true,
                  render: (row) => String(row.segmentIndex !== undefined ? row.segmentIndex : '—'),
                },
                {
                  key: 'centroid',
                  label: 'Centroid (Hz)',
                  monospace: true,
                  render: (row) => formatNumber(row.spectralCentroid, 1),
                },
                {
                  key: 'rolloff',
                  label: 'Rolloff (Hz)',
                  monospace: true,
                  render: (row) => formatNumber(row.spectralRolloff, 1),
                },
                {
                  key: 'width',
                  label: 'Width',
                  render: (row) => (
                    <div className="space-y-1">
                      <div className="text-right font-mono tabular-nums text-text-primary">
                        {formatNumber(row.stereoWidth, 2)}
                      </div>
                      <MetricBar
                        value={row.stereoWidth}
                        min={0}
                        max={1}
                        color="#38bdf8"
                        heightClassName="h-1.5"
                      />
                    </div>
                  ),
                },
                {
                  key: 'corr',
                  label: 'Corr',
                  render: (row) => (
                    <div className="space-y-1">
                      <div className="text-right font-mono tabular-nums text-text-primary">
                        {formatNumber(row.stereoCorrelation, 2)}
                      </div>
                      <MetricBar
                        value={row.stereoCorrelation}
                        min={-1}
                        max={1}
                        color="#ff6b00"
                        heightClassName="h-1.5"
                      />
                    </div>
                  ),
                },
              ]}
            />
          </>
        )}
      </Section>

      {/* 9. Synthesis & Timbre */}
      <Section id="section-meas-synthesis" number={9} title="Synthesis & Timbre">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {phase1.synthesisCharacter && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span data-text-role="subsection-title" className={getTextRoleClassName('subsection-title')}>
                  Synthesis Character
                </span>
                {phase1.synthesisCharacter.analogLike !== undefined &&
                  phase1.synthesisCharacter.analogLike !== null && (
                    <StatusBadge
                      label={phase1.synthesisCharacter.analogLike ? 'Analog-Like' : 'Digital-Like'}
                      tone={phase1.synthesisCharacter.analogLike ? 'success' : 'muted'}
                      compact
                    />
                  )}
              </div>
              {phase1.synthesisCharacter.inharmonicity !== undefined &&
                phase1.synthesisCharacter.inharmonicity !== null && (
                  <MetricBarRow
                    label="Inharmonicity"
                    value={phase1.synthesisCharacter.inharmonicity}
                    min={0}
                    max={1}
                    color="#ff6b00"
                    valueLabel={formatNumber(phase1.synthesisCharacter.inharmonicity, 3)}
                  />
                )}
              {phase1.synthesisCharacter.oddToEvenRatio !== undefined &&
                phase1.synthesisCharacter.oddToEvenRatio !== null && (
                  <MetricBarRow
                    label="Odd-to-Even Ratio"
                    value={phase1.synthesisCharacter.oddToEvenRatio}
                    min={0}
                    max={3}
                    color="#f59e0b"
                    valueLabel={formatNumber(phase1.synthesisCharacter.oddToEvenRatio, 2)}
                  />
                )}
            </div>
          )}

          {phase1.perceptual && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <span data-text-role="subsection-title" className={getTextRoleClassName('subsection-title')}>
                Perceptual
              </span>
              <MetricBarRow
                label="Sharpness"
                value={phase1.perceptual.sharpness}
                min={0}
                max={1}
                color="#38bdf8"
                valueLabel={formatNumber(phase1.perceptual.sharpness, 2)}
              />
              <MetricBarRow
                label="Roughness"
                value={phase1.perceptual.roughness}
                min={0}
                max={1}
                color="#ef4444"
                valueLabel={formatNumber(phase1.perceptual.roughness, 2)}
              />
            </div>
          )}

          {phase1.sidechainDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span data-text-role="subsection-title" className={getTextRoleClassName('subsection-title')}>
                  Sidechain / Pumping
                </span>
                {phase1.sidechainDetail.pumpingRate && (
                  <StatusBadge label={phase1.sidechainDetail.pumpingRate} tone="info" compact />
                )}
              </div>
              <MetricBarRow
                label="Pumping Strength"
                value={phase1.sidechainDetail.pumpingStrength}
                min={0}
                max={1}
                color="#a78bfa"
                valueLabel={formatNumber(phase1.sidechainDetail.pumpingStrength, 2)}
              />
              <MetricBarRow
                label="Pumping Regularity"
                value={phase1.sidechainDetail.pumpingRegularity}
                min={0}
                max={1}
                color="#60a5fa"
                valueLabel={formatNumber(phase1.sidechainDetail.pumpingRegularity, 2)}
              />
              <MetricBarRow
                label="Pumping Confidence"
                value={phase1.sidechainDetail.pumpingConfidence}
                min={0}
                max={1}
                color="#34d399"
                valueLabel={formatNumber(phase1.sidechainDetail.pumpingConfidence, 2)}
              />
              {phase1.sidechainDetail.envelopeShape &&
                phase1.sidechainDetail.envelopeShape.length > 0 && (
                  <BarChart
                    values={phase1.sidechainDetail.envelopeShape.slice(0, 16)}
                    count={16}
                    label="Pumping Shape"
                    height="h-8"
                    colors={['#a78bfa', '#c084fc', '#60a5fa', '#34d399']}
                  />
                )}
            </div>
          )}

          {phase1.effectsDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                  Effects
                </span>
                {phase1.effectsDetail.gatingDetected !== undefined &&
                  phase1.effectsDetail.gatingDetected !== null && (
                    <StatusBadge
                      label={phase1.effectsDetail.gatingDetected ? 'Yes' : 'No'}
                      tone={phase1.effectsDetail.gatingDetected ? 'success' : 'error'}
                      compact
                    />
                  )}
              </div>
              {phase1.effectsDetail.gatingRate !== undefined &&
                phase1.effectsDetail.gatingRate !== null && (
                  <MetricBarRow
                    label="Gating Rate"
                    value={phase1.effectsDetail.gatingRate}
                    min={0}
                    max={8}
                    color="#f59e0b"
                    valueLabel={formatNumber(phase1.effectsDetail.gatingRate, 2)}
                  />
                )}
              {phase1.effectsDetail.gatingRegularity !== undefined &&
                phase1.effectsDetail.gatingRegularity !== null && (
                  <MetricBarRow
                    label="Gating Regularity"
                    value={phase1.effectsDetail.gatingRegularity}
                    min={0}
                    max={1}
                    color="#ffd166"
                    valueLabel={formatNumber(phase1.effectsDetail.gatingRegularity, 2)}
                  />
                )}
              {phase1.effectsDetail.gatingEventCount !== undefined &&
                phase1.effectsDetail.gatingEventCount !== null && (
                  <MetricRow
                    label="Gating Event Count"
                    value={<span className="font-mono tabular-nums">{formatNumber(phase1.effectsDetail.gatingEventCount, 0)}</span>}
                  />
                )}
            </div>
          )}

          {phase1.vocalDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                  Vocals
                </span>
                <StatusBadge
                  label={phase1.vocalDetail.hasVocals ? 'Yes' : 'No'}
                  tone={phase1.vocalDetail.hasVocals ? 'success' : 'error'}
                  compact
                />
              </div>
              <MetricBarRow
                label="Confidence"
                value={phase1.vocalDetail.confidence}
                min={0}
                max={1}
                color="#ff6b00"
                valueLabel={formatNumber(phase1.vocalDetail.confidence, 2)}
              />
              <MetricBarRow
                label="Vocal Energy Ratio"
                value={phase1.vocalDetail.vocalEnergyRatio}
                min={0}
                max={1}
                color="#38bdf8"
                valueLabel={formatNumber(phase1.vocalDetail.vocalEnergyRatio, 3)}
              />
              <MetricRow
                label="Formant Strength"
                value={<span className="font-mono tabular-nums">{formatNumber(phase1.vocalDetail.formantStrength, 3)}</span>}
              />
            </div>
          )}

          {phase1.acidDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                  Acid
                </span>
                <StatusBadge
                  label={phase1.acidDetail.isAcid ? 'Yes' : 'No'}
                  tone={phase1.acidDetail.isAcid ? 'success' : 'error'}
                  compact
                />
              </div>
              <MetricBarRow
                label="Confidence"
                value={phase1.acidDetail.confidence}
                min={0}
                max={1}
                color="#f97316"
                valueLabel={formatNumber(phase1.acidDetail.confidence, 2)}
              />
              <MetricBarRow
                label="Resonance Level"
                value={phase1.acidDetail.resonanceLevel}
                min={0}
                max={1}
                color="#ef4444"
                valueLabel={formatNumber(phase1.acidDetail.resonanceLevel, 3)}
              />
              <MetricRow
                label="Bass Rhythm Density"
                value={<span className="font-mono tabular-nums">{formatNumber(phase1.acidDetail.bassRhythmDensity, 3)}</span>}
              />
            </div>
          )}

          {phase1.supersawDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                  Supersaw
                </span>
                <StatusBadge
                  label={phase1.supersawDetail.isSupersaw ? 'Yes' : 'No'}
                  tone={phase1.supersawDetail.isSupersaw ? 'success' : 'error'}
                  compact
                />
              </div>
              <MetricBarRow
                label="Confidence"
                value={phase1.supersawDetail.confidence}
                min={0}
                max={1}
                color="#a78bfa"
                valueLabel={formatNumber(phase1.supersawDetail.confidence, 2)}
              />
              <MetricRow
                label="Voice Count"
                value={<span className="font-mono tabular-nums">{formatNumber(phase1.supersawDetail.voiceCount, 0)}</span>}
              />
              <MetricRow
                label="Avg Detune"
                value={
                  <span className="font-mono tabular-nums">
                    {formatNumber(phase1.supersawDetail.avgDetuneCents, 1)}
                    <span className="ml-1 text-[10px] text-text-secondary/50">cents</span>
                  </span>
                }
              />
            </div>
          )}

          {phase1.bassDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                  Bass Character
                </span>
                <StatusBadge label={phase1.bassDetail.type} tone="accent" compact />
              </div>
              <MetricRow
                label="Avg Decay"
                value={
                  <span className="font-mono tabular-nums">
                    {formatNumber(phase1.bassDetail.averageDecayMs, 0)}
                    <span className="ml-1 text-[10px] text-text-secondary/50">ms</span>
                  </span>
                }
              />
              <MetricBarRow
                label="Swing"
                value={phase1.bassDetail.swingPercent}
                min={0}
                max={100}
                color="#ff6b00"
                valueLabel={`${formatNumber(phase1.bassDetail.swingPercent, 1)}%`}
              />
              <MetricRow label="Groove Type" value={phase1.bassDetail.grooveType} />
              {phase1.bassDetail.fundamentalHz != null && (
                <MetricRow
                  label="Fundamental"
                  value={
                    <span className="font-mono tabular-nums">
                      {formatNumber(phase1.bassDetail.fundamentalHz, 1)}
                      <span className="ml-1 text-[10px] text-text-secondary/50">Hz</span>
                    </span>
                  }
                />
              )}
            </div>
          )}

          {phase1.kickDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                  Kick
                </span>
                <StatusBadge
                  label={phase1.kickDetail.isDistorted ? 'Yes' : 'No'}
                  tone={phase1.kickDetail.isDistorted ? 'warning' : 'success'}
                  compact
                />
              </div>
              <MetricRow
                label="THD"
                value={<span className="font-mono tabular-nums">{formatNumber(phase1.kickDetail.thd, 3)}</span>}
              />
              <MetricRow
                label="Kick Count"
                value={<span className="font-mono tabular-nums">{formatNumber(phase1.kickDetail.kickCount, 0)}</span>}
              />
              {phase1.kickDetail.fundamentalHz != null && (
                <MetricRow
                  label="Fundamental"
                  value={
                    <span className="font-mono tabular-nums">
                      {formatNumber(phase1.kickDetail.fundamentalHz, 1)}
                      <span className="ml-1 text-[10px] text-text-secondary/50">Hz</span>
                    </span>
                  }
                />
              )}
            </div>
          )}

          {phase1.reverbDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                  Reverb
                </span>
                <StatusBadge
                  label={phase1.reverbDetail.isWet ? 'Yes' : 'No'}
                  tone={phase1.reverbDetail.isWet ? 'success' : 'error'}
                  compact
                />
              </div>
              {phase1.reverbDetail.rt60 != null && (
                <MetricBarRow
                  label="RT60"
                  value={phase1.reverbDetail.rt60}
                  min={0}
                  max={8}
                  color="#38bdf8"
                  leftLabel="dry"
                  rightLabel="spacious"
                  valueLabel={`${formatNumber(phase1.reverbDetail.rt60, 2)} s`}
                />
              )}
              <MetricRow
                label="Measured"
                value={<StatusBadge label={phase1.reverbDetail.measured ? 'Yes' : 'No'} tone={phase1.reverbDetail.measured ? 'success' : 'muted'} compact />}
              />
            </div>
          )}
        </div>
      </Section>
    </div>
  );
}

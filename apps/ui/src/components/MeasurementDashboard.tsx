import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'motion/react';
import {
  ChromaInteractiveData,
  OnsetStrengthData,
  Phase1Result,
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
import { Sparkline } from './Sparkline';
import { SpectralCursorProvider } from '../hooks/useSpectralCursorBus';

interface MeasurementDashboardProps {
  phase1: Phase1Result;
  spectralArtifacts?: SpectralArtifacts | null;
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

interface NormalizedDC {
  complexity: number;
  loudnessVar: number;
  spectralFlat: number;
  attackTime: number;
  attackStd: number;
}

const normalizeDynamicCharacter = (dc: {
  dynamicComplexity: number;
  loudnessVariation: number;
  spectralFlatness: number;
  logAttackTime: number;
  attackTimeStdDev: number;
}): NormalizedDC => ({
  complexity: Math.max(0, Math.min(1, dc.dynamicComplexity)),
  loudnessVar: Math.max(0, Math.min(1, dc.loudnessVariation)),
  spectralFlat: Math.max(0, Math.min(1, dc.spectralFlatness)),
  attackTime: Math.max(0, Math.min(1, (dc.logAttackTime + 3) / 4)),
  attackStd: Math.max(0, Math.min(1, dc.attackTimeStdDev / 2)),
});

const RADAR_AXES = [
  { key: 'complexity' as const, label: 'Complexity' },
  { key: 'loudnessVar' as const, label: 'Loud Var' },
  { key: 'spectralFlat' as const, label: 'Spec Flat' },
  { key: 'attackStd' as const, label: 'Atk Std' },
  { key: 'attackTime' as const, label: 'Atk Time' },
];

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
    <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
      {label}
    </span>
    <div className="flex items-center gap-2">
      {sparkline && <span className="flex-shrink-0">{sparkline}</span>}
      <span className="text-sm font-display font-bold text-text-primary">
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
    <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
      {number.toString().padStart(2, '0')}
    </span>
    <span className="text-lg font-display font-bold text-text-primary flex-1">
      {title}
    </span>
    <span className="text-text-secondary text-sm">{isOpen ? '−' : '+'}</span>
  </button>
);

const Section = ({
  id,
  number,
  title,
  children,
}: {
  id?: string;
  number: number;
  title: string;
  children: React.ReactNode;
}) => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div id={id} className="bg-bg-card border border-border rounded-sm p-4 space-y-4 scroll-mt-24">
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

const BarChart = ({
  values,
  count,
  label,
  height = 'h-6',
}: {
  values: number[];
  count: number;
  label: string;
  height?: string;
}) => {
  const padding = Math.max(0, count - values.length);
  const displayValues = [...values, ...Array(padding).fill(0)];

  return (
    <div className="space-y-1">
      <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
        {label}
      </span>
      <div className="flex gap-1 items-end">
        {displayValues.slice(0, count).map((val, i) => {
          const maxVal = Math.max(...displayValues.slice(0, count), 1);
          const percent = (val / maxVal) * 100;
          return (
            <div
              key={i}
              className={`flex-1 bg-gradient-to-t from-blue-500 to-blue-400 rounded-sm`}
              style={{
                height: `calc(${height} * ${percent / 100})`,
                minHeight: val > 0 ? '4px' : '2px',
                opacity: val > 0 ? 1 : 0.2,
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

const DynamicCharacterRadar = ({ data }: { data: NormalizedDC }) => {
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
    const cx = w / 2;
    const cy = h / 2;
    const radius = Math.min(cx, cy) - 28;
    const axes = RADAR_AXES.length;

    ctx.fillStyle = '#222222';
    ctx.fillRect(0, 0, w, h);

    // Concentric pentagons
    for (const ring of [0.25, 0.5, 0.75, 1]) {
      ctx.beginPath();
      for (let i = 0; i < axes; i++) {
        const angle = (Math.PI * 2 * i) / axes - Math.PI / 2;
        const x = cx + Math.cos(angle) * radius * ring;
        const y = cy + Math.sin(angle) * radius * ring;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.strokeStyle = 'rgba(255,255,255,0.06)';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Axis lines
    for (let i = 0; i < axes; i++) {
      const angle = (Math.PI * 2 * i) / axes - Math.PI / 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius);
      ctx.strokeStyle = 'rgba(255,255,255,0.08)';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Data polygon
    const values = RADAR_AXES.map((a) => data[a.key]);
    ctx.beginPath();
    for (let i = 0; i < axes; i++) {
      const angle = (Math.PI * 2 * i) / axes - Math.PI / 2;
      const v = values[i];
      const x = cx + Math.cos(angle) * radius * v;
      const y = cy + Math.sin(angle) * radius * v;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.fillStyle = 'rgba(255,136,0,0.15)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(255,136,0,0.8)';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Data dots
    for (let i = 0; i < axes; i++) {
      const angle = (Math.PI * 2 * i) / axes - Math.PI / 2;
      const v = values[i];
      const x = cx + Math.cos(angle) * radius * v;
      const y = cy + Math.sin(angle) * radius * v;
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fillStyle = '#ff8800';
      ctx.fill();
    }

    // Axis labels
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.fillStyle = 'rgba(170,170,170,0.7)';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (let i = 0; i < axes; i++) {
      const angle = (Math.PI * 2 * i) / axes - Math.PI / 2;
      const lx = cx + Math.cos(angle) * (radius + 18);
      const ly = cy + Math.sin(angle) * (radius + 18);
      ctx.fillText(RADAR_AXES[i].label, lx, ly);
    }
  }, [data]);

  useEffect(() => {
    draw();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ro = new ResizeObserver(draw);
    ro.observe(canvas);
    return () => ro.disconnect();
  }, [draw]);

  return (
    <canvas
      ref={canvasRef}
      className="w-48 h-48"
      style={{ imageRendering: 'auto' }}
    />
  );
};

export function MeasurementDashboard({
  phase1,
  spectralArtifacts,
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
    <div className="space-y-4">
      {/* 1. Core Metrics */}
      <Section id="section-meas-core" number={1} title="Core Metrics">
        {/* Hero Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {/* BPM Tile */}
          <div className="bg-bg-panel border border-border rounded-sm p-4 hover:border-accent/30 transition-colors">
            <span className="text-[9px] font-mono text-text-secondary uppercase tracking-wider">Tempo</span>
            <div className="flex items-baseline gap-2 mt-2">
              <span className="text-2xl font-display font-bold text-text-primary">
                {formatNumber(phase1.bpm, 1)}
              </span>
              <span className="text-xs font-mono text-text-secondary">BPM</span>
            </div>
            {phase1.bpmDoubletime === true && phase1.bpmRawOriginal != null && (
              <span className="text-[8px] font-mono text-warning/70 block mt-1">
                corrected from {formatNumber(phase1.bpmRawOriginal, 1)}
              </span>
            )}
            <div className="mt-3 space-y-1">
              <div className="w-full h-1 bg-bg-app border border-border/20 rounded-sm overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${phase1.bpmConfidence * 100}%` }}
                  transition={{ duration: 0.6, ease: 'easeOut' }}
                  className="h-full bg-accent shadow-[0_0_4px_var(--color-accent)]"
                />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[8px] font-mono text-text-secondary/60 tabular-nums">
                  CONF {Math.round(phase1.bpmConfidence * 100)}%
                </span>
                {phase1.bpmAgreement !== undefined && phase1.bpmAgreement !== null && (
                  <span className={`text-[8px] font-mono ${phase1.bpmAgreement ? 'text-success/70' : 'text-error/70'}`}>
                    {phase1.bpmAgreement ? 'CROSS-CHECK ✓' : 'CROSS-CHECK ✗'}
                  </span>
                )}
              </div>
            </div>
            {phase1.bpmPercival !== undefined && phase1.bpmPercival !== null && (
              <span className="text-[8px] font-mono text-text-secondary/50 block mt-1">
                Percival: {formatNumber(phase1.bpmPercival, 1)}
              </span>
            )}
            {phase1.bpmSource != null && phase1.bpmSource !== "rhythm_extractor" && (
              <span className="text-[8px] font-mono text-text-secondary/50 block mt-0.5">
                Source: {phase1.bpmSource.replace(/_/g, ' ')}
              </span>
            )}
          </div>

          {/* Key Tile */}
          <div className="bg-bg-panel border border-border rounded-sm p-4 hover:border-accent/30 transition-colors">
            <span className="text-[9px] font-mono text-text-secondary uppercase tracking-wider">Key Signature</span>
            <div className="mt-2 overflow-hidden">
              <span className="text-2xl font-display font-bold text-text-primary truncate block">
                {phase1.key || '—'}
              </span>
            </div>
            {phase1.keyProfile && (
              <span className="text-[8px] font-mono text-text-secondary/50 block mt-1">
                Profile: {phase1.keyProfile}
              </span>
            )}
            <div className="mt-3 space-y-1">
              <div className="w-full h-1 bg-bg-app border border-border/20 rounded-sm overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${phase1.keyConfidence * 100}%` }}
                  transition={{ duration: 0.6, ease: 'easeOut' }}
                  className="h-full bg-accent shadow-[0_0_4px_var(--color-accent)]"
                />
              </div>
              <span className="text-[8px] font-mono text-text-secondary/60 tabular-nums">
                CONF {Math.round(phase1.keyConfidence * 100)}%
              </span>
            </div>
          </div>

          {/* Duration / Format Tile */}
          <div className="bg-bg-panel border border-border rounded-sm p-4 hover:border-accent/30 transition-colors">
            <span className="text-[9px] font-mono text-text-secondary uppercase tracking-wider">Duration</span>
            {(() => {
              const mins = Math.floor(phase1.durationSeconds / 60);
              const secs = Math.floor(phase1.durationSeconds % 60);
              const beatsPerBar = parseInt(phase1.timeSignature?.split('/')[0] || '4', 10) || 4;
              const totalBeats = (phase1.durationSeconds / 60) * phase1.bpm;
              const totalBars = Math.floor(totalBeats / beatsPerBar);
              const gridSegments = Math.min(Math.ceil(totalBars / 4), 24);
              const fullSegments = Math.floor(totalBars / 4);
              const remainder = (totalBars % 4) / 4;
              return (
                <>
                  {/* Transport LCD */}
                  <div className="flex items-center gap-0.5 mt-2">
                    <span className="bg-bg-app/80 border border-border/30 px-2 py-0.5 rounded-[2px] text-2xl font-mono font-bold text-text-primary tabular-nums leading-none">
                      {mins}
                    </span>
                    <span className="text-xl font-mono font-bold text-accent/50">:</span>
                    <span className="bg-bg-app/80 border border-border/30 px-2 py-0.5 rounded-[2px] text-2xl font-mono font-bold text-text-primary tabular-nums leading-none">
                      {String(secs).padStart(2, '0')}
                    </span>
                    <span className="text-[9px] font-mono text-text-secondary/50 ml-2 self-end mb-0.5">{phase1.timeSignature}</span>
                  </div>
                  {/* Bar count + grid */}
                  <div className="mt-3 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[8px] font-mono text-text-secondary/60 uppercase tracking-wide">Arrangement</span>
                      <span className="text-[8px] font-mono text-accent/80 tabular-nums font-bold">{totalBars} BARS</span>
                    </div>
                    <div className="flex gap-[2px]">
                      {Array.from({ length: gridSegments }).map((_, i) => (
                        <motion.div
                          key={i}
                          initial={{ scaleX: 0 }}
                          animate={{ scaleX: 1 }}
                          transition={{ duration: 0.25, delay: i * 0.025, ease: 'easeOut' }}
                          className="h-2 flex-1 rounded-[1px] origin-left"
                          style={{
                            backgroundColor: i < fullSegments
                              ? `rgba(255, 136, 0, ${0.3 + (i / gridSegments) * 0.4})`
                              : i === fullSegments && remainder > 0
                                ? `rgba(255, 136, 0, ${0.2})`
                                : undefined,
                          }}
                        />
                      ))}
                    </div>
                  </div>
                  {/* Supporting info */}
                  <div className="mt-2.5 space-y-1.5">
                    {phase1.sampleRate !== undefined && phase1.sampleRate !== null && (
                      <div className="flex items-center justify-between">
                        <span className="text-[8px] font-mono text-text-secondary/60 uppercase">Sample Rate</span>
                        <span className="text-xs font-display font-bold text-text-primary tabular-nums">{(phase1.sampleRate / 1000).toFixed(1)} kHz</span>
                      </div>
                    )}
                  </div>
                </>
              );
            })()}
          </div>
        </div>

        {/* Genre Banner */}
        {phase1.genreDetail && (
          <div className="bg-bg-panel border border-border rounded-sm p-4 hover:border-accent/30 transition-colors">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <div className={`w-2 h-2 rounded-full bg-accent ${phase1.genreDetail.confidence > 0.8 ? 'animate-pulse' : ''}`} />
                  <span className="text-[9px] font-mono text-text-secondary uppercase tracking-wider">Genre Classification</span>
                </div>
                <span className="text-lg font-display font-bold text-text-primary capitalize block truncate">
                  {phase1.genreDetail.genre}
                </span>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-[9px] font-mono text-text-secondary/70 uppercase">{phase1.genreDetail.genreFamily}</span>
                  {phase1.genreDetail.secondaryGenre && (
                    <>
                      <span className="text-text-secondary/30">/</span>
                      <span className="text-[9px] font-mono text-text-secondary/50 uppercase">{phase1.genreDetail.secondaryGenre}</span>
                    </>
                  )}
                </div>
              </div>
              <div className="shrink-0 text-right">
                <span className="text-[8px] font-mono text-text-secondary/60 uppercase">Conf</span>
                <span className="text-sm font-display font-bold text-text-primary ml-1.5 tabular-nums">
                  {Math.round(phase1.genreDetail.confidence * 100)}%
                </span>
              </div>
            </div>

            {/* Genre fingerprint — top scores as horizontal bars */}
            {phase1.genreDetail.topScores && phase1.genreDetail.topScores.length > 0 && (
              <div className="mt-3 pt-3 border-t border-border/50 space-y-1.5">
                <span className="text-[8px] font-mono text-text-secondary/50 uppercase tracking-wider">Genre Fingerprint</span>
                <div className="space-y-1">
                  {phase1.genreDetail.topScores.slice(0, 5).map((score, i) => {
                    const maxScore = phase1.genreDetail!.topScores[0]?.score || 1;
                    const pct = (score.score / maxScore) * 100;
                    return (
                      <div key={`${score.genre}-${i}`} className="flex items-center gap-2">
                        <span className="text-[8px] font-mono text-text-secondary/70 w-20 truncate text-right capitalize">
                          {score.genre}
                        </span>
                        <div className="flex-1 h-2 bg-bg-app border border-border/20 rounded-sm overflow-hidden">
                          <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${pct}%` }}
                            transition={{ duration: 0.5, delay: i * 0.08, ease: 'easeOut' }}
                            className={`h-full rounded-sm ${
                              i === 0 ? 'bg-accent shadow-[0_0_4px_var(--color-accent)]' : 'bg-accent/50'
                            }`}
                          />
                        </div>
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
          <div className="flex items-center gap-3 px-1">
            <span className="text-[8px] font-mono text-text-secondary/50 uppercase tracking-wider">Tuning</span>
            <span className="text-[9px] font-mono text-text-secondary/70 tabular-nums">
              {formatNumber(phase1.tuningFrequency, 1)} Hz
            </span>
            {phase1.tuningCents !== undefined && phase1.tuningCents !== null && (
              <span className={`text-[9px] font-mono tabular-nums ${
                Math.abs(phase1.tuningCents) > 10 ? 'text-warning/70' : 'text-text-secondary/50'
              }`}>
                {phase1.tuningCents >= 0 ? '+' : ''}{formatNumber(phase1.tuningCents, 1)} cents
              </span>
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
              { label: 'MOM MAX', value: phase1.lufsMomentaryMax, opacity: 'bg-accent/40', delay: 0 },
              { label: 'ST MAX', value: phase1.lufsShortTermMax, opacity: 'bg-accent/25', delay: 0.08 },
              { label: 'INTEGRATED', value: phase1.lufsIntegrated, opacity: 'bg-accent/15', delay: 0.16 },
            ].filter((row) => row.value !== undefined && row.value !== null).map((row) => (
              <div key={row.label} className="flex items-center gap-2">
                <span className="text-[8px] font-mono text-text-secondary/50 w-16 text-right shrink-0">
                  {row.label}
                </span>
                <div className="flex-1 h-1.5 bg-bg-surface-darker border border-border/20 rounded-sm overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${lufsToPercent(row.value!)}%` }}
                    transition={{ duration: 0.5, delay: row.delay, ease: 'easeOut' }}
                    className={`h-full rounded-sm ${row.opacity}`}
                  />
                </div>
                <span className="text-[8px] font-mono text-text-secondary/60 tabular-nums w-10 text-right shrink-0">
                  {formatNumber(row.value!, 1)}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Zone 2 — Headroom & Dynamics Panel */}
        <div className="border-t border-border pt-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Left — Headroom Diagram */}
            <div className="bg-bg-panel border border-border rounded-sm p-4 flex flex-col items-center">
              <span className="text-[8px] font-mono text-text-secondary/60 uppercase tracking-wider mb-3 self-start">
                Headroom
              </span>
              <div className="relative w-6 bg-bg-surface-darker border border-border/30 rounded-sm" style={{ height: 180 }}>
                {/* 0 dBFS reference */}
                <div className="absolute left-0 right-0 border-t border-dashed border-text-secondary/20" style={{ top: `${((3 - 0) / 51) * 100}%` }}>
                  <span className="absolute -left-9 -top-1.5 text-[7px] font-mono text-text-secondary/30">0 dB</span>
                </div>
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
                <div
                  key={tile.label}
                  className="bg-bg-panel border border-border rounded-sm p-3 hover:border-accent/30 transition-colors"
                >
                  <span className="text-[8px] font-mono text-text-secondary/60 uppercase tracking-wider block">
                    {tile.label}
                  </span>
                  <div className="flex items-baseline gap-1 mt-1.5">
                    <span className="text-lg font-display font-bold text-text-primary tabular-nums">
                      {formatNumber(tile.value!, tile.decimals)}
                    </span>
                    {tile.suffix && (
                      <span className="text-[7px] font-mono text-text-secondary/40">{tile.suffix}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Zone 3 — Dynamic Character Radar */}
        {phase1.dynamicCharacter && (
          <div className="border-t border-border pt-3">
            <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary block mb-3">
              Dynamic Character
            </span>
            <div className="flex gap-4 items-start">
              <DynamicCharacterRadar data={normalizeDynamicCharacter(phase1.dynamicCharacter)} />
              <div className="flex-1 space-y-2 pt-2">
                <MetricRow
                  label="Complexity"
                  value={formatNumber(phase1.dynamicCharacter.dynamicComplexity, 2)}
                />
                <MetricRow
                  label="Loudness Variation"
                  value={formatNumber(phase1.dynamicCharacter.loudnessVariation, 2)}
                />
                <MetricRow
                  label="Spectral Flatness"
                  value={formatNumber(phase1.dynamicCharacter.spectralFlatness, 2)}
                />
                <MetricRow
                  label="Log Attack Time"
                  value={formatNumber(phase1.dynamicCharacter.logAttackTime, 2)}
                />
                <MetricRow
                  label="Attack Time Std Dev"
                  value={formatNumber(phase1.dynamicCharacter.attackTimeStdDev, 2)}
                />
              </div>
            </div>
          </div>
        )}
      </Section>

      {/* 3. MixDoctor */}
      <Section id="section-meas-mixdoctor" number={3} title="MixDoctor">
        <MetricRow
          label="Target Genre"
          value={`${mixDoctorReport.genreName} (${mixDoctorReport.genreId})`}
        />
        <MetricRow
          label="Health Score"
          value={`${mixDoctorReport.overallScore}/100`}
        />
        <MetricRow
          label="Loudness Offset"
          value={formatNumber(mixDoctorReport.loudnessOffset, 2)}
        />

        <div className="border-t border-border pt-3">
          <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
            Advisory Summary
          </span>
          <div className="mt-2 space-y-2 text-sm text-text-primary">
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mr-2">
                Dynamics
              </span>
              {mixDoctorReport.dynamicsAdvice.message}
            </div>
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mr-2">
                Loudness
              </span>
              {mixDoctorReport.loudnessAdvice.message}
            </div>
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mr-2">
                Stereo
              </span>
              {mixDoctorReport.stereoAdvice.message}
            </div>
          </div>
        </div>

        <div className="border-t border-border pt-3">
          <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
            Band Diagnostics
          </span>
          <div className="mt-2">
            <SimpleTable
              data={mixDoctorReport.advice}
              columns={[
                { key: 'band', label: 'Band', format: (v) => String(v ?? '—') },
                {
                  key: 'normalizedDb',
                  label: 'Norm dB',
                  format: (v) => formatNumber(v as number, 1),
                },
                {
                  key: 'targetOptimalDb',
                  label: 'Target dB',
                  format: (v) => formatNumber(v as number, 1),
                },
                {
                  key: 'diffDb',
                  label: 'Delta dB',
                  format: (v) => formatNumber(v as number, 1),
                },
                { key: 'issue', label: 'Issue', format: (v) => String(v ?? '—') },
              ]}
            />
          </div>
        </div>
      </Section>

      {/* 4. Spectral */}
      <Section id="section-meas-spectral" number={4} title="Spectral">
        <div className="space-y-3">
          <div>
            <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
              Spectral Balance
            </span>
            <div className="mt-2 space-y-1.5">
              <MetricRow
                label="Sub Bass"
                value={formatNumber(phase1.spectralBalance.subBass, 2)}
              />
              <MetricRow
                label="Low Bass"
                value={formatNumber(phase1.spectralBalance.lowBass, 2)}
              />
              <MetricRow
                label="Low Mids"
                value={formatNumber(phase1.spectralBalance.lowMids, 2)}
              />
              <MetricRow label="Mids" value={formatNumber(phase1.spectralBalance.mids, 2)} />
              <MetricRow
                label="Upper Mids"
                value={formatNumber(phase1.spectralBalance.upperMids, 2)}
              />
              <MetricRow label="Highs" value={formatNumber(phase1.spectralBalance.highs, 2)} />
              <MetricRow
                label="Brilliance"
                value={formatNumber(phase1.spectralBalance.brilliance, 2)}
              />
            </div>
          </div>
          {phase1.spectralDetail && (
            <div className="border-t border-border/30 pt-2 mt-2 space-y-1.5">
              {phase1.spectralDetail.spectralCentroidMean !== undefined &&
                phase1.spectralDetail.spectralCentroidMean !== null && (
                  <MetricRow
                    label="Centroid Mean"
                    value={formatNumber(phase1.spectralDetail.spectralCentroidMean, 1)}
                    sparkline={
                      spectralTimeSeries?.spectralCentroid &&
                      spectralTimeSeries.spectralCentroid.length > 1 && (
                        <Sparkline values={spectralTimeSeries.spectralCentroid} color="#60a5fa" />
                      )
                    }
                  />
                )}
              {phase1.spectralDetail.spectralRolloffMean !== undefined &&
                phase1.spectralDetail.spectralRolloffMean !== null && (
                  <MetricRow
                    label="Rolloff Mean"
                    value={formatNumber(phase1.spectralDetail.spectralRolloffMean, 1)}
                    sparkline={
                      spectralTimeSeries?.spectralRolloff &&
                      spectralTimeSeries.spectralRolloff.length > 1 && (
                        <Sparkline values={spectralTimeSeries.spectralRolloff} color="#a78bfa" />
                      )
                    }
                  />
                )}
              {phase1.spectralDetail.spectralBandwidthMean !== undefined &&
                phase1.spectralDetail.spectralBandwidthMean !== null && (
                  <MetricRow
                    label="Bandwidth Mean"
                    value={formatNumber(phase1.spectralDetail.spectralBandwidthMean, 1)}
                    sparkline={
                      spectralTimeSeries?.spectralBandwidth &&
                      spectralTimeSeries.spectralBandwidth.length > 1 && (
                        <Sparkline values={spectralTimeSeries.spectralBandwidth} color="#34d399" />
                      )
                    }
                  />
                )}
              {phase1.spectralDetail.spectralFlatnessMean !== undefined &&
                phase1.spectralDetail.spectralFlatnessMean !== null && (
                  <MetricRow
                    label="Flatness Mean"
                    value={formatNumber(phase1.spectralDetail.spectralFlatnessMean, 6)}
                    sparkline={
                      spectralTimeSeries?.spectralFlatness &&
                      spectralTimeSeries.spectralFlatness.length > 1 && (
                        <Sparkline values={spectralTimeSeries.spectralFlatness} color="#fbbf24" />
                      )
                    }
                  />
                )}
            </div>
          )}
        </div>

        {/* Enhancement Toolbar */}
        {apiBaseUrl && runId && (
          <div className="border-t border-border pt-3">
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
                  <span
                    key={kind}
                    className="px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide text-success/70 border border-success/20 rounded-sm"
                  >
                    {label} ✓
                  </span>
                ) : (
                  <button
                    key={kind}
                    onClick={() => handleGenerate(kind)}
                    disabled={generating.has(kind)}
                    className="px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide rounded-sm border border-border text-text-secondary hover:text-text-primary hover:border-accent/30 transition-colors disabled:opacity-50 disabled:cursor-wait"
                  >
                    {generating.has(kind) ? `${label}...` : `Generate ${label}`}
                  </button>
                ),
              )}
            </div>
          </div>
        )}

        <SpectralCursorProvider>
          {localArtifacts && apiBaseUrl && runId && localArtifacts.spectrograms.length > 0 && (
            <div className="border-t border-border pt-3">
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
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Essentia Features
              </span>
            </div>
            {phase1.essentiaFeatures.zeroCrossingRate !== undefined &&
              phase1.essentiaFeatures.zeroCrossingRate !== null && (
                <MetricRow
                  label="Zero Crossing Rate"
                  value={formatNumber(phase1.essentiaFeatures.zeroCrossingRate, 3)}
                />
              )}
            {phase1.essentiaFeatures.hfc !== undefined && phase1.essentiaFeatures.hfc !== null && (
              <MetricRow
                label="High Frequency Content"
                value={formatNumber(phase1.essentiaFeatures.hfc, 2)}
              />
            )}
            {phase1.essentiaFeatures.spectralComplexity !== undefined &&
              phase1.essentiaFeatures.spectralComplexity !== null && (
                <MetricRow
                  label="Spectral Complexity"
                  value={formatNumber(phase1.essentiaFeatures.spectralComplexity, 2)}
                />
              )}
            {phase1.essentiaFeatures.dissonance !== undefined &&
              phase1.essentiaFeatures.dissonance !== null && (
                <MetricRow
                  label="Dissonance"
                  value={formatNumber(phase1.essentiaFeatures.dissonance, 2)}
                />
              )}
          </>
        )}
      </Section>

      {/* 5. Stereo Field */}
      <Section id="section-meas-stereo" number={5} title="Stereo Field">
        <MetricRow label="Stereo Width" value={formatNumber(phase1.stereoWidth, 2)} />
        <MetricRow
          label="Stereo Correlation"
          value={formatNumber(phase1.stereoCorrelation, 2)}
        />
        {phase1.monoCompatible !== undefined && phase1.monoCompatible !== null && (
          <MetricRow
            label="Mono Compatible"
            value={phase1.monoCompatible ? 'Yes' : 'No'}
          />
        )}
        {phase1.stereoDetail && (
          <>
            {phase1.stereoDetail.subBassCorrelation !== undefined &&
              phase1.stereoDetail.subBassCorrelation !== null && (
                <MetricRow
                  label="Sub-Bass Correlation"
                  value={formatNumber(phase1.stereoDetail.subBassCorrelation, 2)}
                />
              )}
            {phase1.stereoDetail.subBassMono !== undefined &&
              phase1.stereoDetail.subBassMono !== null && (
                <MetricRow
                  label="Sub-Bass Mono"
                  value={phase1.stereoDetail.subBassMono ? 'Yes' : 'No'}
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
            <SimpleTable
              data={phase1.segmentStereo}
              columns={[
                {
                  key: 'segmentIndex',
                  label: 'Segment',
                  format: (v) => String(v || '—'),
                },
                {
                  key: 'stereoWidth',
                  label: 'Width',
                  format: (v) => formatNumber(v as number, 2),
                },
                {
                  key: 'stereoCorrelation',
                  label: 'Corr',
                  format: (v) => formatNumber(v as number, 2),
                },
              ]}
            />
          </>
        )}
      </Section>

      {/* 6. Rhythm & Groove */}
      <Section id="section-meas-rhythm" number={6} title="Rhythm & Groove">
        {phase1.rhythmDetail && (
          <>
            <MetricRow
              label="Onset Rate"
              value={formatNumber(phase1.rhythmDetail.onsetRate, 2)}
            />
            <MetricRow
              label="Groove Amount"
              value={formatNumber(phase1.rhythmDetail.grooveAmount, 2)}
            />
            {phase1.rhythmDetail.tempoStability !== undefined &&
              phase1.rhythmDetail.tempoStability !== null && (
                <MetricRow
                  label="Tempo Stability"
                  value={`${(phase1.rhythmDetail.tempoStability * 100).toFixed(1)}%`}
                />
              )}
            {phase1.rhythmDetail.phraseGrid && (
              <>
                <div className="border-t border-border pt-3">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                    Phrase Grid
                  </span>
                </div>
                <MetricRow
                  label="4-Bar Phrases"
                  value={formatNumber(phase1.rhythmDetail.phraseGrid.phrases4Bar.length, 0)}
                />
                <MetricRow
                  label="8-Bar Phrases"
                  value={formatNumber(phase1.rhythmDetail.phraseGrid.phrases8Bar.length, 0)}
                />
                <MetricRow
                  label="16-Bar Phrases"
                  value={formatNumber(phase1.rhythmDetail.phraseGrid.phrases16Bar.length, 0)}
                />
                <MetricRow
                  label="Total Bars"
                  value={formatNumber(phase1.rhythmDetail.phraseGrid.totalBars, 0)}
                />
              </>
            )}
          </>
        )}

        {phase1.grooveDetail && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Groove Detail
              </span>
            </div>
            <MetricRow
              label="Kick Swing"
              value={formatNumber(phase1.grooveDetail.kickSwing, 2)}
            />
            <MetricRow
              label="Hi-Hat Swing"
              value={formatNumber(phase1.grooveDetail.hihatSwing, 2)}
            />
            {phase1.grooveDetail.kickAccent && phase1.grooveDetail.kickAccent.length > 0 && (
              <BarChart
                values={phase1.grooveDetail.kickAccent}
                count={4}
                label="Kick Accents"
              />
            )}
            {phase1.grooveDetail.hihatAccent && phase1.grooveDetail.hihatAccent.length > 0 && (
              <BarChart
                values={phase1.grooveDetail.hihatAccent}
                count={4}
                label="Hi-Hat Accents"
              />
            )}
          </>
        )}

        {phase1.beatsLoudness && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Beats & Loudness
              </span>
            </div>
            <HorizontalDominance
              kickRatio={phase1.beatsLoudness.kickDominantRatio}
              midRatio={phase1.beatsLoudness.midDominantRatio}
              highRatio={phase1.beatsLoudness.highDominantRatio}
            />
            {phase1.beatsLoudness.accentPattern &&
              phase1.beatsLoudness.accentPattern.length > 0 && (
                <BarChart
                  values={phase1.beatsLoudness.accentPattern}
                  count={4}
                  label="Accent Pattern"
                  height="h-5"
                />
              )}
            <MetricRow
              label="Mean Beat Loudness"
              value={formatNumber(phase1.beatsLoudness.meanBeatLoudness, 2)}
            />
            <MetricRow
              label="Beat Loudness Variation"
              value={formatNumber(phase1.beatsLoudness.beatLoudnessVariation, 2)}
            />
            <MetricRow
              label="Beat Count"
              value={formatNumber(phase1.beatsLoudness.beatCount, 0)}
            />
          </>
        )}

        {phase1.danceability && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Danceability
              </span>
            </div>
            <MetricRow
              label="Danceability"
              value={formatNumber(phase1.danceability.danceability, 2)}
            />
            <MetricRow label="DFA" value={formatNumber(phase1.danceability.dfa, 3)} />
          </>
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
                  <div className="mt-2 text-sm text-text-primary break-words">
                    {phase1.chordDetail.progression.join(' → ')}
                  </div>
                </div>
              </>
            )}
            {phase1.chordDetail.chordSequence && phase1.chordDetail.chordSequence.length > 0 && (
              <>
                <div className="border-t border-border pt-3">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                    Chord Sequence
                  </span>
                  <div className="mt-2 text-sm text-text-primary break-words">
                    {phase1.chordDetail.chordSequence.join(' → ')}
                  </div>
                </div>
              </>
            )}
            {phase1.chordDetail.chordStrength !== undefined &&
              phase1.chordDetail.chordStrength !== null && (
                <MetricRow
                  label="Chord Strength"
                  value={formatNumber(phase1.chordDetail.chordStrength, 2)}
                />
              )}
            {phase1.chordDetail.dominantChords && phase1.chordDetail.dominantChords.length > 0 && (
              <>
                <div className="border-t border-border pt-3">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                    Dominant Chords
                  </span>
                  <div className="mt-2 text-sm text-text-primary">
                    {phase1.chordDetail.dominantChords.join(', ')}
                  </div>
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
            <SimpleTable
              data={phase1.segmentKey}
              columns={[
                {
                  key: 'segmentIndex',
                  label: 'Segment',
                  format: (v) => String(v || '—'),
                },
                { key: 'key', label: 'Key' },
                {
                  key: 'keyConfidence',
                  label: 'Confidence',
                  format: (v) => formatNumber(v as number, 2),
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
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Segment Loudness
              </span>
            </div>
            <SimpleTable
              data={phase1.segmentLoudness}
              columns={[
                {
                  key: 'segmentIndex',
                  label: 'Segment',
                  format: (v) => String(v !== undefined ? v : '—'),
                },
                {
                  key: 'start',
                  label: 'Start (s)',
                  format: (v) => formatNumber(v as number, 1),
                },
                {
                  key: 'end',
                  label: 'End (s)',
                  format: (v) => formatNumber(v as number, 1),
                },
                {
                  key: 'lufs',
                  label: 'LUFS',
                  format: (v) => formatNumber(v as number, 1),
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
            <SimpleTable
              data={phase1.segmentSpectral}
              columns={[
                {
                  key: 'segmentIndex',
                  label: 'Segment',
                  format: (v) => String(v !== undefined ? v : '—'),
                },
                {
                  key: 'spectralCentroid',
                  label: 'Centroid (Hz)',
                  format: (v) => formatNumber(v as number, 1),
                },
                {
                  key: 'spectralRolloff',
                  label: 'Rolloff (Hz)',
                  format: (v) => formatNumber(v as number, 1),
                },
                {
                  key: 'stereoWidth',
                  label: 'Width',
                  format: (v) => formatNumber(v as number, 2),
                },
                {
                  key: 'stereoCorrelation',
                  label: 'Corr',
                  format: (v) => formatNumber(v as number, 2),
                },
              ]}
            />
          </>
        )}
      </Section>

      {/* 9. Synthesis & Timbre */}
      <Section id="section-meas-synthesis" number={9} title="Synthesis & Timbre">
        {phase1.synthesisCharacter && (
          <>
            {phase1.synthesisCharacter.inharmonicity !== undefined &&
              phase1.synthesisCharacter.inharmonicity !== null && (
                <MetricRow
                  label="Inharmonicity"
                  value={formatNumber(phase1.synthesisCharacter.inharmonicity, 3)}
                />
              )}
            {phase1.synthesisCharacter.oddToEvenRatio !== undefined &&
              phase1.synthesisCharacter.oddToEvenRatio !== null && (
                <MetricRow
                  label="Odd-to-Even Ratio"
                  value={formatNumber(phase1.synthesisCharacter.oddToEvenRatio, 2)}
                />
              )}
            {phase1.synthesisCharacter.analogLike !== undefined &&
              phase1.synthesisCharacter.analogLike !== null && (
                <MetricRow
                  label="Analog-Like"
                  value={phase1.synthesisCharacter.analogLike ? 'Yes' : 'No'}
                />
              )}
          </>
        )}

        {phase1.perceptual && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Perceptual
              </span>
            </div>
            <MetricRow
              label="Sharpness"
              value={formatNumber(phase1.perceptual.sharpness, 2)}
            />
            <MetricRow
              label="Roughness"
              value={formatNumber(phase1.perceptual.roughness, 2)}
            />
          </>
        )}

        {phase1.sidechainDetail && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Sidechain / Pumping
              </span>
            </div>
            <MetricRow
              label="Pumping Strength"
              value={formatNumber(phase1.sidechainDetail.pumpingStrength, 2)}
            />
            <MetricRow
              label="Pumping Regularity"
              value={formatNumber(phase1.sidechainDetail.pumpingRegularity, 2)}
            />
            {phase1.sidechainDetail.pumpingRate && (
              <MetricRow label="Pumping Rate" value={phase1.sidechainDetail.pumpingRate} />
            )}
            <MetricRow
              label="Pumping Confidence"
              value={formatNumber(phase1.sidechainDetail.pumpingConfidence, 2)}
            />
            {phase1.sidechainDetail.envelopeShape &&
              phase1.sidechainDetail.envelopeShape.length > 0 && (
                <BarChart
                  values={phase1.sidechainDetail.envelopeShape.slice(0, 16)}
                  count={16}
                  label="Pumping Shape"
                  height="h-8"
                />
              )}
          </>
        )}

        {phase1.effectsDetail && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Effects
              </span>
            </div>
            {phase1.effectsDetail.gatingDetected !== undefined &&
              phase1.effectsDetail.gatingDetected !== null && (
                <MetricRow
                  label="Gating Detected"
                  value={phase1.effectsDetail.gatingDetected ? 'Yes' : 'No'}
                />
              )}
            {phase1.effectsDetail.gatingRate !== undefined &&
              phase1.effectsDetail.gatingRate !== null && (
                <MetricRow
                  label="Gating Rate"
                  value={formatNumber(phase1.effectsDetail.gatingRate, 2)}
                />
              )}
            {phase1.effectsDetail.gatingRegularity !== undefined &&
              phase1.effectsDetail.gatingRegularity !== null && (
                <MetricRow
                  label="Gating Regularity"
                  value={formatNumber(phase1.effectsDetail.gatingRegularity, 2)}
                />
              )}
            {phase1.effectsDetail.gatingEventCount !== undefined &&
              phase1.effectsDetail.gatingEventCount !== null && (
                <MetricRow
                  label="Gating Event Count"
                  value={formatNumber(phase1.effectsDetail.gatingEventCount, 0)}
                />
              )}
          </>
        )}

        {phase1.vocalDetail && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Vocals
              </span>
            </div>
            <MetricRow
              label="Vocals Detected"
              value={phase1.vocalDetail.hasVocals ? 'Yes' : 'No'}
            />
            <MetricRow
              label="Vocal Confidence"
              value={formatNumber(phase1.vocalDetail.confidence, 2)}
            />
            <MetricRow
              label="Vocal Energy Ratio"
              value={formatNumber(phase1.vocalDetail.vocalEnergyRatio, 3)}
            />
          </>
        )}

        {phase1.acidDetail && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Acid
              </span>
            </div>
            <MetricRow
              label="Acid Detected"
              value={phase1.acidDetail.isAcid ? 'Yes' : 'No'}
            />
            <MetricRow
              label="Acid Confidence"
              value={formatNumber(phase1.acidDetail.confidence, 2)}
            />
            <MetricRow
              label="Resonance Level"
              value={formatNumber(phase1.acidDetail.resonanceLevel, 3)}
            />
          </>
        )}

        {phase1.supersawDetail && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Supersaw
              </span>
            </div>
            <MetricRow
              label="Supersaw Detected"
              value={phase1.supersawDetail.isSupersaw ? 'Yes' : 'No'}
            />
            <MetricRow
              label="Supersaw Confidence"
              value={formatNumber(phase1.supersawDetail.confidence, 2)}
            />
            <MetricRow
              label="Voice Count"
              value={formatNumber(phase1.supersawDetail.voiceCount, 0)}
            />
            <MetricRow
              label="Avg Detune"
              value={`${formatNumber(phase1.supersawDetail.avgDetuneCents, 1)} cents`}
            />
          </>
        )}

        {phase1.bassDetail && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Bass Character
              </span>
            </div>
            <MetricRow label="Bass Type" value={phase1.bassDetail.type} />
            <MetricRow
              label="Avg Decay"
              value={`${formatNumber(phase1.bassDetail.averageDecayMs, 0)} ms`}
            />
            <MetricRow
              label="Swing"
              value={`${formatNumber(phase1.bassDetail.swingPercent, 1)}%`}
            />
            <MetricRow label="Groove Type" value={phase1.bassDetail.grooveType} />
            {phase1.bassDetail.fundamentalHz != null && (
              <MetricRow
                label="Fundamental"
                value={`${formatNumber(phase1.bassDetail.fundamentalHz, 1)} Hz`}
              />
            )}
          </>
        )}

        {phase1.kickDetail && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Kick
              </span>
            </div>
            <MetricRow
              label="Distorted"
              value={phase1.kickDetail.isDistorted ? 'Yes' : 'No'}
            />
            <MetricRow
              label="THD"
              value={formatNumber(phase1.kickDetail.thd, 3)}
            />
            <MetricRow
              label="Kick Count"
              value={formatNumber(phase1.kickDetail.kickCount, 0)}
            />
            {phase1.kickDetail.fundamentalHz != null && (
              <MetricRow
                label="Fundamental"
                value={`${formatNumber(phase1.kickDetail.fundamentalHz, 1)} Hz`}
              />
            )}
          </>
        )}

        {phase1.reverbDetail && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Reverb
              </span>
            </div>
            <MetricRow
              label="Wet"
              value={phase1.reverbDetail.isWet ? 'Yes' : 'No'}
            />
            {phase1.reverbDetail.rt60 != null && (
              <MetricRow
                label="RT60"
                value={`${formatNumber(phase1.reverbDetail.rt60, 2)} s`}
              />
            )}
            <MetricRow
              label="Measured"
              value={phase1.reverbDetail.measured ? 'Yes' : 'No'}
            />
          </>
        )}
      </Section>
    </div>
  );
}

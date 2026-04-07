import React from 'react';
import type { Phase1Result } from '../types';
import { LaneContainer, LaneRow, StatsBar, TimeRuler } from './MeasurementPrimitives';

interface StructureLanesProps {
  phase1: Phase1Result;
}

const SECTION_PALETTE = [
  '#8a64ff', '#00c896', '#ff8800', '#38bdf8', '#ff5555', '#ffb800', '#e879f9', '#34d399',
];

const fmt = (v: number | null | undefined, d = 2): string =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(d) : '—';

function loudnessColor(lufs: number | null | undefined): string {
  if (typeof lufs !== 'number' || !Number.isFinite(lufs)) return '#555';
  if (lufs >= -8) return '#ff6b00';
  if (lufs >= -12) return '#ffb347';
  if (lufs >= -16) return '#ffd166';
  return '#a3e635';
}

export function StructureLanes({ phase1 }: StructureLanesProps) {
  const segments = phase1.segmentLoudness ?? [];
  const spectral = phase1.segmentSpectral ?? [];
  const arrangement = phase1.arrangementDetail;
  const structure = phase1.structure;
  const duration = phase1.durationSeconds ?? 0;

  const hasSegments = segments.length > 0;
  const hasSpectral = spectral.length > 0;
  const hasNovelty = arrangement &&
    ((arrangement.noveltyCurve && arrangement.noveltyCurve.length > 0) ||
      (arrangement.noveltyPeaks && arrangement.noveltyPeaks.length > 0));

  if (!hasSegments && !hasSpectral && !hasNovelty) {
    return (
      <p className="text-[11px] font-mono text-text-secondary opacity-60">
        No structural data available for this track.
      </p>
    );
  }

  // Compute LUFS range for scaling
  const lufsValues = segments
    .map((s) => s.lufs)
    .filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  const lufsMin = lufsValues.length > 0 ? Math.min(...lufsValues) : -20;
  const lufsMax = lufsValues.length > 0 ? Math.max(...lufsValues) : -8;
  const lufsRange = Math.max(lufsMax - lufsMin, 1);

  // Stats bar items
  const statsItems = [
    ...(structure?.segmentCount != null
      ? [{ label: 'Sections', value: String(structure.segmentCount) }]
      : segments.length > 0
        ? [{ label: 'Segments', value: String(segments.length) }]
        : []),
    ...(arrangement?.noveltyMean != null
      ? [{ label: 'Novelty μ', value: fmt(arrangement.noveltyMean, 2), color: '#ffb800' }]
      : []),
    ...(arrangement?.noveltyStdDev != null
      ? [{ label: 'Novelty σ', value: fmt(arrangement.noveltyStdDev, 2), color: '#ffb800' }]
      : []),
    ...(arrangement?.noveltyPeaks
      ? [{ label: 'Peaks', value: String(arrangement.noveltyPeaks.length) }]
      : []),
    ...(lufsValues.length > 0
      ? [{
          label: 'Range',
          value: `${fmt(lufsMax, 1)} → ${fmt(lufsMin, 1)} LUFS`,
          color: '#00ff9d',
        }]
      : []),
  ];

  return (
    <LaneContainer>
      {/* Time ruler */}
      {duration > 0 && <TimeRuler durationSeconds={duration} />}

      {/* Sections lane */}
      {hasSegments && (
        <LaneRow label="Sections" height="h-8">
          <div className="flex h-full">
            {segments.map((seg, i) => {
              const color = SECTION_PALETTE[i % SECTION_PALETTE.length];
              const start = seg.start ?? 0;
              const end = seg.end ?? start;
              const segDuration = end - start;
              const widthPct = duration > 0 ? (segDuration / duration) * 100 : 100 / segments.length;
              return (
                <div
                  key={`sec-${i}`}
                  className="flex items-center justify-center border-r border-[#333] last:border-r-0 overflow-hidden"
                  style={{
                    width: `${Math.max(widthPct, 4)}%`,
                    backgroundColor: `${color}40`,
                  }}
                  title={`Seg ${i} • ${fmt(seg.lufs, 1)} LUFS`}
                >
                  <span className="text-[9px] font-mono font-semibold truncate px-1" style={{ color }}>
                    {i}
                  </span>
                </div>
              );
            })}
          </div>
        </LaneRow>
      )}

      {/* LUFS lane */}
      {lufsValues.length > 0 && (
        <LaneRow label="LUFS" height="h-[48px]">
          <svg
            className="w-full h-full"
            viewBox={`0 0 ${segments.length * 60} 48`}
            preserveAspectRatio="none"
          >
            {/* Grid lines */}
            <line x1="0" y1="12" x2={segments.length * 60} y2="12" stroke="#252525" strokeWidth="1" />
            <line x1="0" y1="24" x2={segments.length * 60} y2="24" stroke="#2a2a2a" strokeWidth="1" />
            <line x1="0" y1="36" x2={segments.length * 60} y2="36" stroke="#252525" strokeWidth="1" />

            {/* Bars */}
            {segments.map((seg, i) => {
              const lufs = typeof seg.lufs === 'number' ? seg.lufs : lufsMin;
              const heightPct = Math.max(((lufs - lufsMin) / lufsRange) * 40, 2);
              const y = 48 - heightPct;
              const barColor = loudnessColor(seg.lufs);
              return (
                <rect
                  key={`bar-${i}`}
                  x={i * 60 + 4}
                  y={y}
                  width={52}
                  height={heightPct}
                  fill={barColor}
                  fillOpacity={0.45}
                  rx={1}
                />
              );
            })}

            {/* Level line */}
            <polyline
              points={segments
                .map((seg, i) => {
                  const lufs = typeof seg.lufs === 'number' ? seg.lufs : lufsMin;
                  const y = 48 - Math.max(((lufs - lufsMin) / lufsRange) * 40, 2);
                  return `${i * 60 + 30},${y}`;
                })
                .join(' ')}
              fill="none"
              stroke="#00ff9d"
              strokeWidth="1.5"
              opacity="0.7"
            />
          </svg>
          <div className="absolute right-1 top-0.5 text-[7px] font-mono text-[#444]">{fmt(lufsMax, 1)}</div>
          <div className="absolute right-1 bottom-0.5 text-[7px] font-mono text-[#444]">{fmt(lufsMin, 1)}</div>
        </LaneRow>
      )}

      {/* Novelty lane */}
      {hasNovelty && arrangement && (
        <LaneRow label="Novelty" height="h-[36px]">
          <NoveltyLane
            curve={arrangement.noveltyCurve ?? []}
            peaks={arrangement.noveltyPeaks ?? []}
          />
        </LaneRow>
      )}

      {/* Spectral lane */}
      {hasSpectral && (
        <LaneRow label="Spectral" height="h-[36px]">
          <SpectralLane values={spectral.map((s) => s.spectralCentroid ?? 0)} color="#8a64ff" />
          <div className="absolute right-1 top-0.5 text-[7px] font-mono text-[#444]">High</div>
          <div className="absolute right-1 bottom-0.5 text-[7px] font-mono text-[#444]">Low</div>
        </LaneRow>
      )}

      {/* Stereo Width lane */}
      {hasSpectral && spectral.some((s) => s.stereoWidth != null) && (
        <LaneRow label="Width" height="h-7">
          <SpectralLane
            values={spectral.map((s) => s.stereoWidth ?? 0)}
            color="#00c896"
            fillOpacity={0.06}
          />
        </LaneRow>
      )}

      {/* Summary stats */}
      {statsItems.length > 0 && <StatsBar items={statsItems} />}
    </LaneContainer>
  );
}

/* ── Sub-components ──────────────────────────────────────────────────── */

function NoveltyLane({ curve, peaks }: { curve: number[]; peaks: number[] }) {
  if (curve.length === 0 && peaks.length === 0) return null;

  const viewW = 400;
  const viewH = 36;

  if (curve.length > 0) {
    const max = Math.max(...curve, 0.001);
    const step = viewW / (curve.length - 1 || 1);
    const points = curve.map((v, i) => `${i * step},${viewH - (v / max) * (viewH - 4)}`).join(' ');

    const peakIndices = new Set(peaks);
    const peakPoints = curve
      .map((v, i) => (peakIndices.has(i) ? { x: i * step, y: viewH - (v / max) * (viewH - 4) } : null))
      .filter(Boolean) as { x: number; y: number }[];

    return (
      <svg className="w-full h-full" viewBox={`0 0 ${viewW} ${viewH}`} preserveAspectRatio="none">
        <polyline points={points} fill="none" stroke="#ffb800" strokeWidth="1.5" opacity="0.8" />
        {peakPoints.map((p, i) => (
          <React.Fragment key={`peak-${i}`}>
            <line x1={p.x} y1={p.y} x2={p.x} y2={viewH} stroke="#ffb800" strokeWidth="0.5" opacity="0.3" />
            <circle cx={p.x} cy={p.y} r="3" fill="#ffb800" opacity="0.9" />
          </React.Fragment>
        ))}
      </svg>
    );
  }

  // Peaks only (no curve) — render as vertical lines
  if (peaks.length > 0) {
    const maxPeak = Math.max(...peaks, 1);
    return (
      <svg className="w-full h-full" viewBox={`0 0 ${viewW} ${viewH}`} preserveAspectRatio="none">
        {peaks.map((p, i) => {
          const x = (p / maxPeak) * viewW;
          return (
            <React.Fragment key={`peak-line-${i}`}>
              <line x1={x} y1={0} x2={x} y2={viewH} stroke="#ffb800" strokeWidth="1" opacity="0.5" />
              <circle cx={x} cy={viewH / 2} r="3" fill="#ffb800" opacity="0.9" />
            </React.Fragment>
          );
        })}
      </svg>
    );
  }

  return null;
}

function SpectralLane({
  values,
  color,
  fillOpacity = 0.08,
}: {
  values: number[];
  color: string;
  fillOpacity?: number;
}) {
  if (values.length === 0) return null;

  const viewW = 400;
  const viewH = 36;
  const max = Math.max(...values, 0.001);
  const step = viewW / (values.length - 1 || 1);

  const linePoints = values.map((v, i) => `${i * step},${viewH - (v / max) * (viewH - 4)}`).join(' ');
  const fillPoints = `${linePoints} ${viewW},${viewH} 0,${viewH}`;

  return (
    <svg className="w-full h-full" viewBox={`0 0 ${viewW} ${viewH}`} preserveAspectRatio="none">
      <polygon points={fillPoints} fill={color} fillOpacity={fillOpacity} />
      <polyline points={linePoints} fill="none" stroke={color} strokeWidth="1.5" opacity="0.7" />
    </svg>
  );
}

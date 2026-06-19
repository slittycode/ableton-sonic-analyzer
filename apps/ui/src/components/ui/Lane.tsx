import React from 'react';

/**
 * DAW arrangement-lane primitives — the horizontal label-cell + content-row
 * vocabulary used by the harmony and structure lane views. Migrated from the
 * retired MeasurementPrimitives layer onto the design tokens (the lane shades
 * snap to the surface-dark / surface-darker / border-light token ladder).
 */

export function LaneContainer({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-bg-surface-darker border border-border rounded-sm overflow-hidden">
      {children}
    </div>
  );
}

export interface LaneRowProps {
  label: string;
  height?: string;
  children: React.ReactNode;
}

export function LaneRow({ label, height = 'h-8', children }: LaneRowProps) {
  return (
    <div className={`flex ${height} border-b border-border-light last:border-b-0`}>
      <div className="w-[72px] min-w-[72px] bg-bg-surface-dark flex items-center px-2 border-r border-border-light">
        <span className="text-nano font-mono text-text-muted uppercase tracking-[0.5px] truncate">
          {label}
        </span>
      </div>
      <div className="flex-1 relative bg-bg-surface-darker">{children}</div>
    </div>
  );
}

export interface TimeRulerProps {
  durationSeconds: number;
  label?: string;
}

export function TimeRuler({ durationSeconds, label = 'Structure' }: TimeRulerProps) {
  const markerCount = Math.min(Math.max(Math.floor(durationSeconds / 30) + 1, 3), 10);
  const step = durationSeconds / (markerCount - 1);
  const markers = Array.from({ length: markerCount }, (_, i) => {
    const secs = Math.round(i * step);
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  });

  return (
    <div className="flex items-center h-6 bg-bg-surface-dark border-b border-border-light px-2 gap-3">
      <span className="text-micro font-mono text-accent uppercase tracking-[1px]">{label}</span>
      <div className="flex-1 flex justify-between text-nano font-mono text-text-muted">
        {markers.map((m, i) => (
          <span key={i}>{m}</span>
        ))}
      </div>
    </div>
  );
}

export interface StatsBarItem {
  label: string;
  value: React.ReactNode;
  color?: string;
}

export function StatsBar({ items }: { items: StatsBarItem[] }) {
  return (
    <div className="flex h-7 bg-bg-surface-dark border-t border-border-light px-2 items-center gap-4">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-1">
          <span className="text-nano font-mono text-text-muted uppercase">{item.label}</span>
          <span
            className="text-meta font-mono tabular-nums"
            style={{ color: item.color || 'var(--color-text-primary)' }}
          >
            {item.value}
          </span>
        </div>
      ))}
    </div>
  );
}

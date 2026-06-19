import React from 'react';

import { cn } from './cn';

export interface MetricBarProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'color'> {
  value: number | null | undefined;
  min?: number;
  max?: number;
  /** Pre-computed percent override (0-100). Overrides value/min/max. */
  percent?: number;
  /** Any valid CSS color. Defaults to the accent token. */
  color?: string;
  glow?: boolean;
  leftLabel?: string;
  rightLabel?: string;
  /** Tailwind height class for the bar track (e.g. 'h-2'). */
  heightClassName?: string;
}

function clamp(value: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, value));
}

function resolvePercent({
  value,
  min = 0,
  max = 1,
  percent,
}: {
  value: number | null | undefined;
  min?: number;
  max?: number;
  percent?: number;
}): number {
  if (typeof percent === 'number' && Number.isFinite(percent)) {
    return clamp(percent, 0, 100);
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0;
  if (max === min) return 0;
  return clamp(((value - min) / (max - min)) * 100, 0, 100);
}

export const MetricBar = React.forwardRef<HTMLDivElement, MetricBarProps>(function MetricBar(
  {
    value,
    min = 0,
    max = 1,
    percent,
    color = 'var(--color-accent)',
    glow = false,
    leftLabel,
    rightLabel,
    heightClassName = 'h-2',
    className,
    ...rest
  },
  ref,
) {
  const width = resolvePercent({ value, min, max, percent });

  return (
    <div ref={ref} className={cn('space-y-1', className)} {...rest}>
      <div
        className={cn(
          heightClassName,
          'rounded-full border border-border/30 bg-bg-app/80 overflow-hidden',
        )}
      >
        <div
          className={cn(
            heightClassName,
            'rounded-full transition-[width] duration-300 ease-out',
          )}
          style={{
            width: `${width}%`,
            background: `linear-gradient(90deg, ${color}99, ${color})`,
            boxShadow: glow ? `0 0 14px ${color}44` : undefined,
          }}
        />
      </div>
      {(leftLabel || rightLabel) && (
        <div className="flex items-center justify-between text-nano font-mono text-text-secondary/50">
          <span>{leftLabel ?? ''}</span>
          <span>{rightLabel ?? ''}</span>
        </div>
      )}
    </div>
  );
});

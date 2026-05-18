import React from 'react';

import { cn } from './cn';

export interface TimeReadoutProps extends React.HTMLAttributes<HTMLSpanElement> {
  elapsedMs?: number | null;
  estimateMs?: number | null;
  estimateRangeMs?: [number, number] | null;
  /** When true, render placeholder dashes instead of zeros. */
  pending?: boolean;
}

function formatMs(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return '—';
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatRange(range: [number, number] | null | undefined): string {
  if (!range) return '';
  const [lo, hi] = range;
  return `${formatMs(lo)}–${formatMs(hi)}`;
}

export const TimeReadout = React.forwardRef<HTMLSpanElement, TimeReadoutProps>(
  function TimeReadout(
    { elapsedMs, estimateMs, estimateRangeMs, pending, className, ...rest },
    ref,
  ) {
    const elapsedLabel = pending ? '—:——' : formatMs(elapsedMs);
    const estimateLabel = estimateRangeMs
      ? formatRange(estimateRangeMs)
      : formatMs(estimateMs);
    const hasEstimate = Boolean(estimateRangeMs) || estimateMs != null;

    return (
      <span
        ref={ref}
        className={cn(
          'tabular-mono inline-flex items-baseline gap-1.5 text-[11px] text-text-primary',
          className,
        )}
        {...rest}
      >
        <span>{elapsedLabel}</span>
        {hasEstimate && (
          <span className="text-text-muted text-[9px] uppercase tracking-[0.14em]">
            est {estimateLabel}
          </span>
        )}
      </span>
    );
  },
);

import React from 'react';

import { Pill } from './Pill';
import type { Tone } from './variants';

export interface DeltaBadgeProps {
  value: number | null | undefined;
  unit?: string;
  decimals?: number;
  okThreshold: number;
  warnThreshold: number;
  invert?: boolean;
  showSign?: boolean;
  className?: string;
}

function formatSignedNumber(value: number, decimals: number, showSign: boolean): string {
  const abs = Math.abs(value).toFixed(decimals);
  if (!showSign) return value.toFixed(decimals);
  return `${value >= 0 ? '+' : '-'}${abs}`;
}

/**
 * Threshold-driven delta chip. Renders a {@link Pill} whose tone reflects how
 * far `value` sits from zero relative to the ok/warn thresholds (or the inverse
 * when `invert`). Non-finite values render an `n/a` neutral pill. Migrated from
 * the retired MeasurementPrimitives layer onto the canonical token palette.
 */
export function DeltaBadge({
  value,
  unit,
  decimals = 1,
  okThreshold,
  warnThreshold,
  invert = false,
  showSign = true,
  className,
}: DeltaBadgeProps) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return (
      <Pill tone="neutral" size="xs" className={className}>
        n/a
      </Pill>
    );
  }

  const magnitude = Math.abs(value);
  const tone: Tone =
    magnitude <= okThreshold
      ? invert
        ? 'error'
        : 'success'
      : magnitude <= warnThreshold
        ? 'warning'
        : invert
          ? 'success'
          : 'error';
  const label = `${formatSignedNumber(value, decimals, showSign)}${unit ? ` ${unit}` : ''}`;

  return (
    <Pill tone={tone} size="xs" className={className}>
      {label}
    </Pill>
  );
}

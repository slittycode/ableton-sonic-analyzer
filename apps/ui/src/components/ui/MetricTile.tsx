import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from './cn';
import { LedIndicator } from './LedIndicator';

const tileVariants = cva(
  'flex flex-col gap-2 rounded-sm border border-border-light bg-bg-surface-dark p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]',
  {
    variants: {
      accent: {
        none: '',
        accent: 'border-l-2 border-accent',
        success: 'border-l-2 border-success',
        warning: 'border-l-2 border-warning',
        error: 'border-l-2 border-error',
        neutral: 'border-l-2 border-border-light',
      },
    },
    defaultVariants: { accent: 'none' },
  },
);

const valueSizeClass: Record<NonNullable<MetricTileProps['size']>, string> = {
  sm: 'text-base',
  md: 'text-xl',
  lg: 'text-2xl',
  xl: 'text-3xl',
};

const unitSizeClass: Record<NonNullable<MetricTileProps['size']>, string> = {
  sm: 'text-micro',
  md: 'text-meta',
  lg: 'text-eyebrow',
  xl: 'text-xs',
};

export interface MetricTileProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, 'children'>,
    VariantProps<typeof tileVariants> {
  label: React.ReactNode;
  value: React.ReactNode;
  unit?: React.ReactNode;
  icon?: React.ReactNode;
  /** Optional LED indicator on the header row. */
  status?: 'idle' | 'active' | 'success' | 'warning' | 'error';
  /** Right-aligned slot on the header row (badges, source pill, etc.). */
  headerRight?: React.ReactNode;
  /** Optional content below the value (sparkline, confidence band, etc.). */
  footer?: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}

export const MetricTile = React.forwardRef<HTMLDivElement, MetricTileProps>(
  function MetricTile(
    {
      label,
      value,
      unit,
      icon,
      status,
      headerRight,
      footer,
      size = 'md',
      accent,
      className,
      ...rest
    },
    ref,
  ) {
    const resolvedSize = size ?? 'md';
    return (
      <div ref={ref} className={cn(tileVariants({ accent }), className)} {...rest}>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 min-w-0">
            {status && <LedIndicator status={status} />}
            {icon && <span className="text-text-secondary shrink-0">{icon}</span>}
            <span
              data-text-role="eyebrow"
              className="font-mono text-meta uppercase tracking-[0.16em] text-text-secondary truncate"
            >
              {label}
            </span>
          </div>
          {headerRight && <div className="shrink-0">{headerRight}</div>}
        </div>
        <div className="flex items-baseline gap-1.5">
          <span
            data-text-role="value"
            className={cn(
              'font-mono font-medium leading-tight text-text-primary tabular-nums',
              valueSizeClass[resolvedSize],
            )}
          >
            {value}
          </span>
          {unit && (
            <span
              data-text-role="meta"
              className={cn(
                'font-mono uppercase tracking-[0.14em] text-text-muted',
                unitSizeClass[resolvedSize],
              )}
            >
              {unit}
            </span>
          )}
        </div>
        {footer && <div className="mt-0.5">{footer}</div>}
      </div>
    );
  },
);

export { tileVariants as metricTileVariants };

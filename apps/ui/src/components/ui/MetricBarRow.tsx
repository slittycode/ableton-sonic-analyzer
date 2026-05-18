import React from 'react';

import { formatDisplayText, getTextRoleClassName } from '../../utils/displayText';
import { cn } from './cn';
import { MetricBar } from './MetricBar';

export interface MetricBarRowProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'color'> {
  label: string;
  valueLabel: React.ReactNode;
  value: number | null | undefined;
  min?: number;
  max?: number;
  percent?: number;
  color?: string;
  sparkline?: React.ReactNode;
  leftLabel?: string;
  rightLabel?: string;
  monospaceValue?: boolean;
}

export const MetricBarRow = React.forwardRef<HTMLDivElement, MetricBarRowProps>(
  function MetricBarRow(
    {
      label,
      valueLabel,
      value,
      min,
      max,
      percent,
      color,
      sparkline,
      leftLabel,
      rightLabel,
      monospaceValue = true,
      className,
      ...rest
    },
    ref,
  ) {
    return (
      <div ref={ref} className={cn('space-y-1.5', className)} {...rest}>
        <div className="flex items-center justify-between gap-3">
          <span
            data-text-role="eyebrow"
            className={getTextRoleClassName('eyebrow')}
          >
            {formatDisplayText(label, 'eyebrow')}
          </span>
          <div className="flex items-center gap-2">
            {sparkline && <span className="shrink-0">{sparkline}</span>}
            <span
              data-text-role="value"
              className={cn(
                getTextRoleClassName('value'),
                monospaceValue && 'tabular-nums',
              )}
            >
              {valueLabel}
            </span>
          </div>
        </div>
        <MetricBar
          value={value}
          min={min}
          max={max}
          percent={percent}
          color={color}
          glow
          leftLabel={leftLabel}
          rightLabel={rightLabel}
        />
      </div>
    );
  },
);

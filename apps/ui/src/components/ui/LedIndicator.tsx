import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from './cn';

const ledVariants = cva('led-indicator', {
  variants: {
    status: {
      idle: '',
      active: 'led-indicator--active',
      success: 'led-indicator--success',
      warning: 'led-indicator--warning',
      error: 'led-indicator--error',
      pulsing: 'led-indicator--pulsing',
    },
    size: {
      sm: '',
      md: 'led-indicator--md',
    },
  },
  defaultVariants: { status: 'idle', size: 'sm' },
});

export interface LedIndicatorProps
  extends Omit<React.HTMLAttributes<HTMLSpanElement>, 'children'>,
    VariantProps<typeof ledVariants> {
  label?: string;
}

export const LedIndicator = React.forwardRef<HTMLSpanElement, LedIndicatorProps>(
  function LedIndicator({ className, status, size, label, ...rest }, ref) {
    if (label) {
      return (
        <span
          ref={ref}
          className={cn('inline-flex items-center gap-1.5', className)}
          {...rest}
        >
          <span className={ledVariants({ status, size })} aria-hidden />
          <span className="font-mono text-meta uppercase tracking-[0.16em] text-text-secondary">
            {label}
          </span>
        </span>
      );
    }
    return (
      <span
        ref={ref}
        className={cn(ledVariants({ status, size }), className)}
        aria-hidden
        {...rest}
      />
    );
  },
);

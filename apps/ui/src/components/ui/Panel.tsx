import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from './cn';

const panelVariants = cva('', {
  variants: {
    variant: {
      rack: 'device-rack',
      surface: 'rounded-sm border border-border bg-bg-panel',
      ghost: 'rounded-sm border border-border-light bg-bg-card/30',
      inset: 'rounded-sm border border-border/40 bg-bg-app/60',
    },
    padding: {
      none: '',
      sm: 'p-2.5',
      md: 'p-3',
      lg: 'p-4',
    },
    tone: {
      neutral: '',
      active: 'device-rack--active',
      success: 'device-rack--success',
      warning: 'device-rack--warning',
      error: 'device-rack--error',
    },
  },
  defaultVariants: { variant: 'surface', padding: 'none', tone: 'neutral' },
});

export interface PanelProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof panelVariants> {}

export const Panel = React.forwardRef<HTMLDivElement, PanelProps>(function Panel(
  { className, variant, padding, tone, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn(panelVariants({ variant, padding, tone }), className)}
      {...rest}
    />
  );
});

export { panelVariants };

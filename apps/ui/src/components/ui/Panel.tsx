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
      active: '',
      success: '',
      warning: '',
      error: '',
    },
  },
  // Tone styling is variant-aware. The `device-rack--*` modifiers only have
  // effect under a `.device-rack` parent, so non-rack variants get
  // border-tint emphasis instead of the rack glow shadow.
  compoundVariants: [
    { variant: 'rack', tone: 'active', class: 'device-rack--active' },
    { variant: 'rack', tone: 'success', class: 'device-rack--success' },
    { variant: 'rack', tone: 'warning', class: 'device-rack--warning' },
    { variant: 'rack', tone: 'error', class: 'device-rack--error' },
    { variant: 'surface', tone: 'active', class: 'border-accent/50' },
    { variant: 'surface', tone: 'success', class: 'border-success/40' },
    { variant: 'surface', tone: 'warning', class: 'border-warning/40' },
    { variant: 'surface', tone: 'error', class: 'border-error/40' },
    { variant: 'ghost', tone: 'active', class: 'border-accent/40' },
    { variant: 'ghost', tone: 'success', class: 'border-success/30' },
    { variant: 'ghost', tone: 'warning', class: 'border-warning/30' },
    { variant: 'ghost', tone: 'error', class: 'border-error/30' },
    { variant: 'inset', tone: 'active', class: 'border-accent/40' },
    { variant: 'inset', tone: 'success', class: 'border-success/30' },
    { variant: 'inset', tone: 'warning', class: 'border-warning/30' },
    { variant: 'inset', tone: 'error', class: 'border-error/30' },
  ],
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

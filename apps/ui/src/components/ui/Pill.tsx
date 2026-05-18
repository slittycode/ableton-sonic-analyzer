import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from './cn';

const pillVariants = cva(
  'inline-flex items-center gap-1 rounded-sm border font-mono uppercase tracking-[0.16em]',
  {
    variants: {
      tone: {
        accent: '',
        success: '',
        warning: '',
        error: '',
        neutral: '',
      },
      variant: {
        solid: '',
        outline: 'bg-transparent',
        ghost: 'border-transparent',
      },
      size: {
        xs: 'px-1.5 py-0.5 text-[9px]',
        sm: 'px-2 py-0.5 text-[10px]',
      },
    },
    compoundVariants: [
      // SOLID
      { tone: 'accent', variant: 'solid', class: 'bg-accent/10 border-accent/40 text-accent' },
      { tone: 'success', variant: 'solid', class: 'bg-success/20 text-success border-success/30' },
      { tone: 'warning', variant: 'solid', class: 'bg-warning/20 text-warning border-warning/30' },
      { tone: 'error', variant: 'solid', class: 'bg-error/20 text-error border-error/30' },
      { tone: 'neutral', variant: 'solid', class: 'bg-bg-card/40 border-border-light text-text-secondary' },
      // OUTLINE
      { tone: 'accent', variant: 'outline', class: 'border-accent/50 text-accent' },
      { tone: 'success', variant: 'outline', class: 'border-success/40 text-success' },
      { tone: 'warning', variant: 'outline', class: 'border-warning/40 text-warning' },
      { tone: 'error', variant: 'outline', class: 'border-error/40 text-error' },
      { tone: 'neutral', variant: 'outline', class: 'border-border text-text-secondary' },
      // GHOST
      { tone: 'accent', variant: 'ghost', class: 'text-accent' },
      { tone: 'success', variant: 'ghost', class: 'text-success' },
      { tone: 'warning', variant: 'ghost', class: 'text-warning' },
      { tone: 'error', variant: 'ghost', class: 'text-error' },
      { tone: 'neutral', variant: 'ghost', class: 'text-text-secondary' },
    ],
    defaultVariants: { tone: 'neutral', variant: 'solid', size: 'sm' },
  },
);

export interface PillProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof pillVariants> {
  leadingDot?: boolean;
}

export const Pill = React.forwardRef<HTMLSpanElement, PillProps>(function Pill(
  { className, tone, variant, size, leadingDot, children, ...rest },
  ref,
) {
  return (
    <span ref={ref} className={cn(pillVariants({ tone, variant, size }), className)} {...rest}>
      {leadingDot && (
        <span
          aria-hidden
          className={cn(
            'inline-block w-1.5 h-1.5 rounded-full',
            tone === 'accent' && 'bg-accent',
            tone === 'success' && 'bg-success',
            tone === 'warning' && 'bg-warning',
            tone === 'error' && 'bg-error',
            (!tone || tone === 'neutral') && 'bg-text-secondary',
          )}
        />
      )}
      {children}
    </span>
  );
});

export { pillVariants };

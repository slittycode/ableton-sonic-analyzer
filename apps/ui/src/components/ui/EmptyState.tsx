import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from './cn';

const emptyStateVariants = cva(
  'flex flex-col items-center justify-center gap-2 rounded-sm border text-center',
  {
    variants: {
      tone: {
        neutral: 'border-border-light bg-bg-card/30 text-text-secondary',
        warning: 'border-warning/30 bg-warning/5 text-warning',
        error: 'border-error/30 bg-error/5 text-error',
      },
      padding: {
        sm: 'p-3',
        md: 'p-4',
        lg: 'p-6',
      },
    },
    defaultVariants: { tone: 'neutral', padding: 'md' },
  },
);

export interface EmptyStateProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'>,
    VariantProps<typeof emptyStateVariants> {
  icon?: React.ReactNode;
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
}

export const EmptyState = React.forwardRef<HTMLDivElement, EmptyStateProps>(
  function EmptyState(
    { className, tone, padding, icon, title, description, action, children, ...rest },
    ref,
  ) {
    return (
      <div
        ref={ref}
        className={cn(emptyStateVariants({ tone, padding }), className)}
        {...rest}
      >
        {icon && <div className="opacity-70">{icon}</div>}
        {title && (
          <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-text-primary">
            {title}
          </p>
        )}
        {description && (
          <p className="font-mono text-[11px] leading-snug text-text-secondary max-w-prose">
            {description}
          </p>
        )}
        {children}
        {action && <div className="mt-1">{action}</div>}
      </div>
    );
  },
);

export { emptyStateVariants };

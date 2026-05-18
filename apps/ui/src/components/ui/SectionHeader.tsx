import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { getTextRoleClassName, type TextRole } from '../../utils/displayText';
import { cn } from './cn';
import { LedIndicator } from './LedIndicator';
import type { Tone } from './variants';

const sectionHeaderVariants = cva('flex items-center justify-between gap-3', {
  variants: {
    variant: {
      inline: '',
      underline: 'border-b border-border pb-2',
    },
    size: {
      sm: '',
      md: '',
      lg: '',
    },
  },
  defaultVariants: { variant: 'inline', size: 'md' },
});

export interface SectionHeaderProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'>,
    VariantProps<typeof sectionHeaderVariants> {
  title: React.ReactNode;
  eyebrow?: React.ReactNode;
  action?: React.ReactNode;
  ledTone?: Tone;
  titleRole?: TextRole;
  titleClassName?: string;
}

type SizeKey = 'sm' | 'md' | 'lg';

const fallbackTitleClass: Record<SizeKey, string> = {
  sm: 'text-xs font-mono uppercase tracking-wider text-text-secondary',
  md: 'text-sm font-mono uppercase tracking-wider text-text-secondary',
  lg: 'text-base font-mono uppercase tracking-wider text-text-primary',
};

export const SectionHeader = React.forwardRef<HTMLDivElement, SectionHeaderProps>(
  function SectionHeader(
    {
      title,
      eyebrow,
      action,
      ledTone = 'accent',
      titleRole,
      titleClassName,
      variant,
      size = 'md',
      className,
      ...rest
    },
    ref,
  ) {
    const resolvedSize: SizeKey = (size ?? 'md') as SizeKey;
    const titleBase = titleRole
      ? getTextRoleClassName(titleRole)
      : fallbackTitleClass[resolvedSize];

    return (
      <div
        ref={ref}
        className={cn(sectionHeaderVariants({ variant, size: resolvedSize }), className)}
        {...rest}
      >
        <div className="flex flex-col gap-0.5 min-w-0">
          {eyebrow && (
            <span
              data-text-role="eyebrow"
              className={getTextRoleClassName('eyebrow')}
            >
              {eyebrow}
            </span>
          )}
          <h2
            data-text-role={titleRole}
            className={cn(titleBase, 'flex items-center gap-2', titleClassName)}
          >
            <LedIndicator status={ledTone === 'neutral' ? 'idle' : (ledTone as 'active')} />
            {title}
          </h2>
        </div>
        {action ? <div className="flex items-center gap-2 flex-shrink-0">{action}</div> : null}
      </div>
    );
  },
);

export { sectionHeaderVariants };

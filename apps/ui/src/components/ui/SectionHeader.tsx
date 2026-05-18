import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { getTextRoleClassName, type TextRole } from '../../utils/displayText';
import { cn } from './cn';
import { LedIndicator } from './LedIndicator';
import type { Tone } from './variants';

// Mobile-first layout: stack title and action vertically on narrow
// viewports, then break to horizontal at md (768px). This restores the
// pre-D.5a behavior where the Analysis Results header collapsed to
// `flex-col` at 375px so the title wasn't squeezed off-screen by the
// Download buttons. The mobile failure was caught by
// tests/smoke/responsive-layout.spec.ts:192 which asserts the
// "Analysis Results" h2 is visible at 375px — the parent shell's
// overflow-hidden was clipping the overflowing title.
const sectionHeaderVariants = cva('flex flex-col items-start gap-2 md:flex-row md:items-center md:justify-between md:gap-3', {
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

function toneToLedStatus(
  tone: Tone,
): 'idle' | 'active' | 'success' | 'warning' | 'error' {
  if (tone === 'neutral') return 'idle';
  if (tone === 'accent') return 'active';
  return tone;
}

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
    const resolvedTone: Tone = (ledTone ?? 'accent') as Tone;
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
            <LedIndicator status={toneToLedStatus(resolvedTone)} />
            {title}
          </h2>
        </div>
        {action ? <div className="flex items-center gap-2 flex-shrink-0">{action}</div> : null}
      </div>
    );
  },
);

export { sectionHeaderVariants };

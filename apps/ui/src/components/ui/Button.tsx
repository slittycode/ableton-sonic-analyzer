import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from './cn';
import { LedIndicator } from './LedIndicator';

const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-1.5 rounded-sm',
    'font-mono uppercase tracking-[0.16em]',
    'transition-colors',
    'disabled:opacity-40 disabled:cursor-not-allowed',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
  ],
  {
    variants: {
      variant: {
        primary: [
          'bg-bg-panel border border-accent/60 text-accent',
          'hover:bg-accent hover:text-bg-app',
          'shadow-[0_0_10px_rgba(255,136,0,0.15)]',
          'hover:shadow-[0_0_18px_rgba(255,136,0,0.4)]',
        ],
        secondary: [
          'bg-bg-panel border border-border text-text-secondary',
          'hover:border-accent/40 hover:text-text-primary',
        ],
        ghost: [
          'border border-transparent text-text-secondary',
          'hover:text-text-primary hover:bg-bg-card/40',
        ],
        danger: [
          'bg-error/10 border border-error/30 text-error',
          'hover:bg-error/20',
        ],
        link: [
          'border border-transparent text-text-secondary underline-offset-2',
          'hover:text-text-primary hover:underline',
          'normal-case tracking-normal',
        ],
      },
      size: {
        sm: 'px-2 py-1 text-[10px]',
        md: 'px-3 py-1.5 text-[11px]',
        lg: 'px-6 py-2.5 text-[12px]',
      },
      iconOnly: {
        true: '!gap-0',
      },
    },
    compoundVariants: [
      { iconOnly: true, size: 'sm', class: '!px-1.5 !py-1.5' },
      { iconOnly: true, size: 'md', class: '!px-2 !py-2' },
      { iconOnly: true, size: 'lg', class: '!px-2.5 !py-2.5' },
    ],
    defaultVariants: { variant: 'secondary', size: 'md', iconOnly: false },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  leadingIcon?: React.ReactNode;
  trailingIcon?: React.ReactNode;
  ledIndicator?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    className,
    variant,
    size,
    iconOnly,
    leadingIcon,
    trailingIcon,
    ledIndicator,
    children,
    type = 'button',
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(buttonVariants({ variant, size, iconOnly }), className)}
      {...rest}
    >
      {ledIndicator && (
        <LedIndicator status={rest.disabled ? 'idle' : 'pulsing'} />
      )}
      {leadingIcon}
      {children}
      {trailingIcon}
    </button>
  );
});

export { buttonVariants };

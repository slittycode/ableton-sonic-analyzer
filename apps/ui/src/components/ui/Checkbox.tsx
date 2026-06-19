import React from 'react';
import * as RadixCheckbox from '@radix-ui/react-checkbox';
import { Check } from 'lucide-react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from './cn';

const checkboxVariants = cva(
  [
    'inline-flex items-center justify-center',
    'rounded-sm border bg-bg-app/60',
    'transition-colors',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
    'disabled:opacity-40 disabled:cursor-not-allowed',
  ],
  {
    variants: {
      size: {
        sm: 'w-3.5 h-3.5',
        md: 'w-4 h-4',
        lg: 'w-5 h-5',
      },
      checked: {
        true: 'border-accent bg-accent/20 text-accent shadow-[0_0_6px_rgba(255,136,0,0.3)]',
        false: 'border-border hover:border-accent/40',
      },
    },
    defaultVariants: { size: 'md', checked: false },
  },
);

export interface CheckboxProps
  extends Omit<React.ComponentPropsWithoutRef<typeof RadixCheckbox.Root>, 'children'>,
    Omit<VariantProps<typeof checkboxVariants>, 'checked'> {
  label?: React.ReactNode;
  description?: React.ReactNode;
}

export const Checkbox = React.forwardRef<
  React.ElementRef<typeof RadixCheckbox.Root>,
  CheckboxProps
>(function Checkbox(
  { className, size, label, description, checked, defaultChecked, id, ...rest },
  ref,
) {
  // Resolve a stable id so the label can be associated correctly.
  const reactId = React.useId();
  const fieldId = id ?? reactId;
  // `checked` is Radix's CheckedState (`true | false | 'indeterminate'`).
  // Only the strict `true` state should drive the checked visual style; the
  // indeterminate state needs its own dimmed border, not the lit accent ring.
  const resolved = checked ?? defaultChecked ?? false;
  const isStrictlyChecked = resolved === true;

  const box = (
    <RadixCheckbox.Root
      ref={ref}
      id={fieldId}
      checked={checked}
      defaultChecked={defaultChecked}
      className={cn(
        checkboxVariants({ size, checked: isStrictlyChecked }),
        resolved === 'indeterminate' && 'border-accent/40 text-accent/70',
        className,
      )}
      {...rest}
    >
      <RadixCheckbox.Indicator>
        {resolved === 'indeterminate' ? (
          <span className="block w-1.5 h-0.5 bg-current" aria-hidden />
        ) : (
          <Check className="w-3 h-3" strokeWidth={3} />
        )}
      </RadixCheckbox.Indicator>
    </RadixCheckbox.Root>
  );

  if (!label && !description) {
    return box;
  }

  return (
    <label
      htmlFor={fieldId}
      className="inline-flex items-start gap-2 cursor-pointer select-none"
    >
      {box}
      <span className="flex flex-col gap-0.5">
        {label && (
          <span className="font-mono text-eyebrow uppercase tracking-[0.14em] text-text-primary">
            {label}
          </span>
        )}
        {description && (
          <span className="font-mono text-meta text-text-secondary leading-snug">
            {description}
          </span>
        )}
      </span>
    </label>
  );
});

export { checkboxVariants };

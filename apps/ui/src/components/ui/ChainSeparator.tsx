import React from 'react';

import { cn } from './cn';

export type SignalTone = 'idle' | 'active' | 'success';

export interface ChainSeparatorProps extends React.HTMLAttributes<HTMLDivElement> {
  tone?: SignalTone;
  animated?: boolean;
  orientation?: 'horizontal' | 'vertical';
}

export const ChainSeparator = React.forwardRef<HTMLDivElement, ChainSeparatorProps>(
  function ChainSeparator(
    { tone = 'idle', animated = false, orientation = 'horizontal', className, ...rest },
    ref,
  ) {
    if (orientation === 'vertical') {
      // Vertical chain: cable is a thin vertical line, arrow points down.
      const cableTone =
        tone === 'active'
          ? 'bg-[color:var(--color-signal-cable)]'
          : tone === 'success'
            ? 'bg-[color:var(--color-signal-cable-success)]'
            : 'bg-[color:var(--color-signal-cable-idle)]';
      return (
        <div
          ref={ref}
          className={cn('flex flex-col items-center gap-0', className)}
          aria-hidden
          {...rest}
        >
          <div className={cn('w-px h-3 self-center', cableTone)} />
          <div
            className="w-0 h-0"
            style={{
              borderLeft: '4px solid transparent',
              borderRight: '4px solid transparent',
              borderTop: `6px solid ${
                tone === 'active'
                  ? 'var(--color-signal-cable)'
                  : tone === 'success'
                    ? 'var(--color-signal-cable-success)'
                    : 'var(--color-signal-cable-idle)'
              }`,
            }}
          />
        </div>
      );
    }

    return (
      <div
        ref={ref}
        className={cn('flex items-stretch min-w-[1.5rem]', className)}
        aria-hidden
        {...rest}
      >
        <div
          className={cn('signal-cable', animated && 'signal-cable--animated')}
          data-tone={tone}
        />
        <div className="signal-arrow" data-tone={tone} />
      </div>
    );
  },
);

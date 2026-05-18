import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from './cn';
import { LedIndicator } from './LedIndicator';
import type { SignalTone } from './ChainSeparator';

const rackVariants = cva('device-rack', {
  variants: {
    status: {
      idle: '',
      active: 'device-rack--active',
      success: 'device-rack--success',
      warning: 'device-rack--warning',
      error: 'device-rack--error',
    },
  },
  defaultVariants: { status: 'idle' },
});

const bodyVariants = cva('device-rack__body', {
  variants: {
    density: {
      normal: '',
      dense: 'device-rack__body--dense',
    },
  },
  defaultVariants: { density: 'normal' },
});

type RackStatus = 'idle' | 'active' | 'success' | 'warning' | 'error';

function statusToLedTone(
  status: RackStatus,
): 'idle' | 'active' | 'success' | 'warning' | 'error' {
  return status;
}

export interface DeviceRackProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'>,
    VariantProps<typeof rackVariants> {
  /** Title-strip text (e.g. "MEASUREMENT"). */
  name: React.ReactNode;
  /** Optional subtitle after the LED dot ("· 4–5 min"). */
  subtitle?: React.ReactNode;
  /** Right-aligned slot on the title strip (action button, count, etc.). */
  action?: React.ReactNode;
  /** Bottom signal-flow rail: where input arrives from. */
  signalIn?: SignalTone | null;
  /** Bottom signal-flow rail: where output flows to. */
  signalOut?: SignalTone | null;
  /** Free-form right-side content for the rail (e.g. a progress percent). */
  railContent?: React.ReactNode;
  /** Hide the title strip entirely (rare — for inset sub-racks). */
  hideTitleStrip?: boolean;
  /** Body density. Dense uses smaller vertical padding for parameter grids. */
  density?: VariantProps<typeof bodyVariants>['density'];
  children?: React.ReactNode;
}

export const DeviceRack = React.forwardRef<HTMLDivElement, DeviceRackProps>(
  function DeviceRack(
    {
      name,
      subtitle,
      action,
      status = 'idle',
      signalIn,
      signalOut,
      railContent,
      hideTitleStrip,
      density,
      className,
      children,
      ...rest
    },
    ref,
  ) {
    const resolvedStatus: RackStatus = (status ?? 'idle') as RackStatus;
    const showRail = signalIn != null || signalOut != null || railContent != null;

    return (
      <div ref={ref} className={cn(rackVariants({ status: resolvedStatus }), className)} {...rest}>
        {!hideTitleStrip && (
          <div className="device-rack__title-strip">
            <LedIndicator status={statusToLedTone(resolvedStatus)} />
            <span className="truncate">{name}</span>
            {subtitle && (
              <span className="text-text-secondary normal-case tracking-[0.04em] text-[10px] truncate">
                {subtitle}
              </span>
            )}
            {action && <div className="ml-auto flex items-center gap-1">{action}</div>}
          </div>
        )}
        <div className={cn(bodyVariants({ density }))}>{children}</div>
        {showRail && (
          // Three explicit slots so signalIn / railContent / signalOut land
          // left / center / right regardless of which combination is present.
          // (Previously two adjacent `ml-auto` siblings collapsed signalOut
          // next to railContent when all three slots were filled.)
          <div className="device-rack__rail">
            <span className="flex items-center gap-1 min-w-0">
              {signalIn != null && (
                <>
                  <span className="signal-arrow" data-tone={signalIn} />
                  <span>in</span>
                </>
              )}
            </span>
            <span className="flex-1 min-w-0 truncate text-center">
              {railContent}
            </span>
            <span className="flex items-center gap-1 min-w-0 justify-end">
              {signalOut != null && (
                <>
                  <span>out</span>
                  <span className="signal-arrow" data-tone={signalOut} />
                </>
              )}
            </span>
          </div>
        )}
      </div>
    );
  },
);

export { rackVariants as deviceRackVariants };

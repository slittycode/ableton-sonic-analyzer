import React from 'react';

import { cn } from './cn';
import { ChainSeparator, type SignalTone } from './ChainSeparator';
import { DeviceRack } from './DeviceRack';

export type SignalStageStatus =
  | 'idle'
  | 'queued'
  | 'active'
  | 'success'
  | 'warning'
  | 'error';

export interface SignalStage {
  key: string;
  name: React.ReactNode;
  status: SignalStageStatus;
  /** Optional content rendered inside the stage's device body. */
  parameter?: React.ReactNode;
  /** Optional STATUS label rendered inside the stage (e.g. "RUNNING"). */
  statusLabel?: React.ReactNode;
  /** Right-aligned slot on the stage device's title strip. */
  action?: React.ReactNode;
  /** Optional subtitle next to the device name. */
  subtitle?: React.ReactNode;
}

export interface SignalChainProps extends React.HTMLAttributes<HTMLDivElement> {
  stages: SignalStage[];
  orientation?: 'horizontal' | 'vertical';
  /** Animate cables between active stages. */
  animated?: boolean;
}

function stageStatusToRack(
  status: SignalStageStatus,
): 'idle' | 'active' | 'success' | 'warning' | 'error' {
  if (status === 'queued') return 'idle';
  return status;
}

function cableToneForTransition(
  prev: SignalStageStatus,
  next: SignalStageStatus,
): SignalTone {
  // Cable shows the "data is flowing from prev to next" state.
  // If prev completed, the cable carries data into next.
  if (prev === 'success' && next === 'active') return 'active';
  if (prev === 'success' && next === 'success') return 'success';
  if (prev === 'active') return 'active';
  return 'idle';
}

export const SignalChain = React.forwardRef<HTMLDivElement, SignalChainProps>(
  function SignalChain(
    { stages, orientation = 'horizontal', animated = false, className, ...rest },
    ref,
  ) {
    const isVertical = orientation === 'vertical';
    return (
      <div
        ref={ref}
        className={cn(
          isVertical
            ? 'flex flex-col items-stretch gap-0'
            : 'flex items-stretch gap-0',
          className,
        )}
        role="list"
        {...rest}
      >
        {stages.map((stage, i) => {
          const prev = stages[i - 1];
          const cableTone: SignalTone = prev
            ? cableToneForTransition(prev.status, stage.status)
            : 'idle';
          return (
            <React.Fragment key={stage.key}>
              {i > 0 && (
                <ChainSeparator
                  tone={cableTone}
                  animated={animated && cableTone === 'active'}
                  orientation={orientation}
                />
              )}
              <div
                role="listitem"
                className={cn(isVertical ? 'w-full' : 'flex-1 min-w-0')}
              >
                <DeviceRack
                  name={stage.name}
                  subtitle={stage.subtitle}
                  status={stageStatusToRack(stage.status)}
                  action={stage.action}
                  density="dense"
                >
                  <div className="flex items-center justify-between gap-2 min-h-[2rem]">
                    {stage.parameter ?? <span aria-hidden />}
                    {stage.statusLabel && (
                      <span
                        className={cn(
                          'font-mono text-[10px] uppercase tracking-[0.16em] tabular-nums',
                          stage.status === 'success' && 'text-success',
                          stage.status === 'active' && 'text-accent',
                          stage.status === 'queued' && 'text-text-muted',
                          stage.status === 'idle' && 'text-text-muted',
                          stage.status === 'warning' && 'text-warning',
                          stage.status === 'error' && 'text-error',
                        )}
                      >
                        {stage.statusLabel}
                      </span>
                    )}
                  </div>
                </DeviceRack>
              </div>
            </React.Fragment>
          );
        })}
      </div>
    );
  },
);

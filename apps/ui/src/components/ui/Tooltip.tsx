import React from 'react';
import * as RadixTooltip from '@radix-ui/react-tooltip';

import { cn } from './cn';

export interface TooltipProps {
  text?: React.ReactNode;
  content?: React.ReactNode;
  side?: 'top' | 'right' | 'bottom' | 'left';
  align?: 'start' | 'center' | 'end';
  delayDuration?: number;
  className?: string;
  children: React.ReactNode;
}

export function TooltipProvider({
  children,
  delayDuration = 200,
}: {
  children: React.ReactNode;
  delayDuration?: number;
}) {
  return (
    <RadixTooltip.Provider delayDuration={delayDuration}>{children}</RadixTooltip.Provider>
  );
}

export function Tooltip({
  text,
  content,
  side = 'top',
  align = 'center',
  delayDuration,
  className,
  children,
}: TooltipProps) {
  const body = content ?? text;
  if (!body) {
    return <>{children}</>;
  }

  const node = (
    <RadixTooltip.Root delayDuration={delayDuration}>
      <RadixTooltip.Trigger asChild>
        <span className="inline-flex">{children}</span>
      </RadixTooltip.Trigger>
      <RadixTooltip.Portal>
        <RadixTooltip.Content
          side={side}
          align={align}
          sideOffset={6}
          className={cn(
            'z-50 max-w-xs px-3 py-2 rounded-sm border border-border bg-bg-card shadow-md',
            'font-mono text-eyebrow text-text-primary leading-snug',
            'animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0',
            className,
          )}
        >
          {body}
          <RadixTooltip.Arrow className="fill-bg-card" />
        </RadixTooltip.Content>
      </RadixTooltip.Portal>
    </RadixTooltip.Root>
  );

  return node;
}

import React from 'react';

import { cn } from './cn';
import { Pill } from './Pill';
import type { Tone } from './variants';

export interface TokenBadgeListProps {
  items: Array<{ label: string; tone?: Tone }>;
  className?: string;
}

/**
 * A wrapped row of {@link Pill} chips for tag/token lists (genres, instruments,
 * production techniques, …). Migrated from the retired MeasurementPrimitives
 * layer; tones are restricted to the token palette (off-palette tones collapse
 * to `neutral` at the call site).
 */
export function TokenBadgeList({ items, className }: TokenBadgeListProps) {
  return (
    <div className={cn('flex flex-wrap gap-1.5', className)}>
      {items.map((item, index) => (
        <Pill key={`${item.label}-${index}`} tone={item.tone ?? 'neutral'} size="sm">
          {item.label}
        </Pill>
      ))}
    </div>
  );
}

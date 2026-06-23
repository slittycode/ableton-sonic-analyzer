import React from 'react';

import { SectionHeader } from '../ui';
import { getTextRoleClassName, type TextRole } from '../../utils/displayText';

// Shared helpers for the extracted AnalysisResults sections. Moved verbatim out
// of the AnalysisResults monolith (Phase 5 split) so each section component can
// reuse them; AnalysisResults imports them back for the sections still inline.

export function textRoleClassName(role: TextRole, className = ''): string {
  return [getTextRoleClassName(role), className].filter(Boolean).join(' ');
}

export interface ResultsSectionHeaderProps {
  title: React.ReactNode;
  rightSlot?: React.ReactNode;
  titleRole?: TextRole;
  titleClassName?: string;
  className?: string;
}

/**
 * Thin wrapper around the SectionHeader primitive — preserves the
 * (title, rightSlot, titleRole, titleClassName, className) API the rest of
 * AnalysisResults expects while letting the primitive own the actual layout
 * + LED indicator + data-text-role propagation. The static accent dot
 * (`<span class="w-2 h-2 bg-accent rounded-full">`) is upgraded to the
 * pulsing `.led-indicator--active` glyph that every other DeviceRack /
 * SectionHeader in the migration uses.
 */
export function ResultsSectionHeader({
  title,
  rightSlot,
  titleRole,
  titleClassName,
  className,
}: ResultsSectionHeaderProps) {
  return (
    <SectionHeader
      title={title}
      titleRole={titleRole}
      titleClassName={titleClassName}
      action={rightSlot}
      variant="underline"
      size="md"
      ledTone="accent"
      className={className}
    />
  );
}

export interface MetaBadgeItem {
  label: string;
  value?: string | null;
}

export function MetaBadgeList({ items }: { items: MetaBadgeItem[] }) {
  const visibleItems = items.filter((item) => typeof item.value === 'string' && item.value.trim().length > 0);
  if (visibleItems.length === 0) return null;

  // Audit N8: previously each chip rendered as `Family: Native` /
  // `Context: Acid bass` / `Stage: Sound design`. The `Label:` prefix read
  // as a JSON-key column header — engineering-flavour. The chip content
  // alone (`Acid bass`) is enough; we keep `item.label` only for the React
  // key. Tooltip preserves the original label for users who want context.
  return (
    <div className="flex flex-wrap gap-1.5">
      {visibleItems.map((item) => (
        <span
          key={`${item.label}-${item.value}`}
          title={item.label}
          className="text-micro font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary whitespace-nowrap"
        >
          {item.value}
        </span>
      ))}
    </div>
  );
}

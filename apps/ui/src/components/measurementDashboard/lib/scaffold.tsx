import React, { useState } from 'react';

import { EmptyState, Pill } from '../../ui';
import { formatDisplayText, getTextRoleClassName } from '../../../utils/displayText';
import { PILL_TONE_FOR_LEGACY, type LegacyBadgeTone } from './constants';

// Shared scaffolding components for the Measurement Dashboard, moved verbatim
// out of the MeasurementDashboard monolith (Phase 4 split) so the extracted
// panels and the main component share one source.

export function StatusBadge({
  label,
  tone = 'neutral',
  compact = false,
}: {
  label: React.ReactNode;
  tone?: LegacyBadgeTone;
  compact?: boolean;
}) {
  return (
    <Pill tone={PILL_TONE_FOR_LEGACY[tone]} size={compact ? 'xs' : 'sm'}>
      {label}
    </Pill>
  );
}

export function UnavailableMeasurementCard({
  title,
  description,
  detail,
}: {
  title: string;
  description: string;
  detail?: string;
}) {
  // Delegates to the EmptyState primitive — preserves the (title,
  // description, detail) API that the dashboard's two call sites
  // depend on, while folding the visual chrome into the canonical
  // primitive. The optional `detail` line renders as a children slot
  // since EmptyState's prop surface stops at description.
  return (
    <EmptyState
      tone="neutral"
      padding="md"
      title={title}
      description={description}
      className="border-dashed border-border-light/60 bg-bg-surface-dark/40"
    >
      {detail ? (
        <p className="text-meta font-mono uppercase tracking-[0.12em] text-text-secondary/60">
          {detail}
        </p>
      ) : null}
    </EmptyState>
  );
}

export const MetricRow = ({
  label,
  value,
  sparkline,
}: {
  label: string;
  value: React.ReactNode;
  sparkline?: React.ReactNode;
}) => (
  <div className="flex justify-between items-center gap-4">
    <span
      data-text-role="eyebrow"
      className={getTextRoleClassName('eyebrow')}
    >
      {formatDisplayText(label, 'eyebrow')}
    </span>
    <div className="flex items-center gap-2">
      {sparkline && <span className="flex-shrink-0">{sparkline}</span>}
      <span
        data-text-role="value"
        className={getTextRoleClassName('value')}
      >
        {value}
      </span>
    </div>
  </div>
);

/**
 * Numbered, collapsible section toggle used by every Measurement Dashboard
 * sub-section. Structurally distinct from the ui/SectionHeader primitive —
 * this whole component IS the click target (the entire row toggles the
 * section open/closed) whereas the primitive renders a static h2 with an
 * optional action slot. Wrapping the primitive in a <button> would either
 * nest interactive elements or swallow the primitive's accessibility
 * affordances, so the local toggle stays.
 *
 * The two data-text-role attributes (`meta` on the number badge,
 * `section-title` on the title span) are emitted directly here for the
 * same vocabulary as the primitive renders elsewhere.
 */
export const NumberedSectionToggle = ({
  number,
  title,
  isOpen,
  onToggle,
}: {
  number: number;
  title: string;
  isOpen: boolean;
  onToggle: () => void;
}) => (
  <button
    onClick={onToggle}
    aria-expanded={isOpen}
    className="w-full text-left flex items-center gap-2 hover:opacity-80 transition-opacity"
  >
    <span data-text-role="meta" className={getTextRoleClassName('meta')}>
      {number.toString().padStart(2, '0')}
    </span>
    <span
      data-text-role="section-title"
      className={[getTextRoleClassName('section-title'), 'flex-1'].join(' ')}
    >
      {formatDisplayText(title, 'title')}
    </span>
    <span aria-hidden className="text-text-secondary text-sm">{isOpen ? '−' : '+'}</span>
  </button>
);

export const Section = ({
  id,
  testId,
  number,
  title,
  children,
}: {
  id?: string;
  testId?: string;
  number: number;
  title: string;
  children: React.ReactNode;
}) => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div
      id={id}
      data-testid={testId}
      className="bg-bg-card border border-border rounded-sm p-4 space-y-4 scroll-mt-24"
    >
      <NumberedSectionToggle
        number={number}
        title={title}
        isOpen={isOpen}
        onToggle={() => setIsOpen(!isOpen)}
      />
      {isOpen && <div className="space-y-3 pt-2">{children}</div>}
    </div>
  );
};

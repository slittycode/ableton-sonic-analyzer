import React from 'react';
import { AudioWaveform, Check } from 'lucide-react';

import { SectionHeader } from '../ui';
import { getTextRoleClassName, type TextRole } from '../../utils/displayText';
import type { RecommendationContractEntry } from '../../types';
import { formatContractRange, formatContractValue } from '../../services/recommendationsContract';

// Shared helpers for the extracted AnalysisResults sections. Moved verbatim out
// of the AnalysisResults monolith (Phase 5 split) so each section component can
// reuse them; AnalysisResults imports them back for the sections still inline.

export type StyleProfileSectionState = 'ready' | 'dropped' | 'omitted' | 'disabled' | 'pending';

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

const LOW_CONFIDENCE_TITLE = 'Low confidence — treat this as approximate.';

/**
 * Inline ⚠ glyph flagging a low-confidence measurement. Shared between the
 * Measurement Summary tiles and the harmonic-content card in AnalysisResults.
 */
export function lowConfidenceIndicator(show: boolean) {
  if (!show) return null;
  return (
    <span
      className="text-meta font-mono text-warning"
      title={LOW_CONFIDENCE_TITLE}
      aria-label="Low confidence"
    >
      ⚠
    </span>
  );
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

/**
 * Height-animated collapse wrapper. Moved verbatim out of the AnalysisResults
 * monolith (Phase 5 split) — shared by the Sources toggle and the high-coupling
 * Sonic / Arrangement / Mix / Patch card sections. The restyle phase replaces
 * adopters with the `ui/CollapsibleCard` primitive (grid-rows collapse); until
 * then this keeps the existing max-height behaviour byte-for-byte.
 */
export function Collapsible({ isOpen, children }: { isOpen: boolean; children: React.ReactNode }) {
  return (
    <div
      className={`overflow-hidden transition-[max-height,opacity] duration-300 ease-out ${
        isOpen ? 'max-h-[900px] opacity-100' : 'max-h-0 opacity-0'
      }`}
    >
      {children}
    </div>
  );
}

export function groupIcon(groupName: string): React.ReactNode {
  if (groupName.includes('DRUM PROCESSING')) return '🥁';
  // Audit #13: 🫧 (bubbles) is not a bass signifier in any audio
  // convention. Swapped to the monochrome Lucide waveform glyph, which
  // matches the app's icon language. Other groups keep their emoji
  // landmarks for now (smallest blast radius).
  if (groupName.includes('BASS PROCESSING')) {
    return <AudioWaveform className="w-3.5 h-3.5 inline -mt-0.5" aria-hidden="true" />;
  }
  if (groupName.includes('SYNTH / MELODIC')) return '🎹';
  if (groupName.includes('MID PROCESSING')) return '🎚';
  if (groupName.includes('HIGH-END DETAIL')) return '✨';
  if (groupName.includes('MASTER BUS')) return '🧱';
  return '🎛';
}

/**
 * Audit Finding #14: per-card "applied to my session" toggle. Looks like a
 * checkbox to producers who scan top-down through Mix Chain / Patches lists.
 * Renders nothing when no tracker is wired (e.g., file hash unavailable);
 * stops click propagation so toggling doesn't also expand/collapse the card.
 */
export function AppliedCheckbox({
  isApplied,
  onToggle,
  ariaLabel,
}: {
  isApplied: boolean;
  onToggle: () => void;
  ariaLabel: string;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={isApplied}
      aria-label={ariaLabel}
      data-applied={isApplied || undefined}
      data-testid="applied-checkbox"
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
      className={`flex-shrink-0 flex items-center justify-center w-4 h-4 rounded-sm border transition-colors ${
        isApplied
          ? 'border-success/60 bg-success/15 text-success hover:border-success'
          : 'border-border bg-bg-card/40 text-text-secondary/40 hover:border-accent/40 hover:text-accent'
      }`}
      title={isApplied ? 'Applied — click to unmark' : 'Mark as applied'}
    >
      {isApplied ? <Check className="w-3 h-3" /> : null}
    </button>
  );
}

/**
 * "Validated" chip for cards backed by the recommendations.v1 contract
 * (ADR 0003): the backend admitted this card to the schema-validated,
 * citation-gated envelope. Cards without it are exactly the ones the
 * projection refused (typically: no Phase 1 citation), so the badge is the
 * citation gate made visible. Renders nothing when no entries match.
 */
export function ContractValidatedBadge({
  entries,
  testId,
}: {
  entries: RecommendationContractEntry[];
  testId: string;
}) {
  if (entries.length === 0) return null;
  return (
    <span
      data-testid={testId}
      title="Passed the recommendations.v1 contract: schema-validated and citing at least one Phase 1 measurement."
      className="text-micro font-mono uppercase px-1.5 py-0.5 rounded border border-success/40 text-success whitespace-nowrap"
    >
      ✓ Validated
    </span>
  );
}

/**
 * Expanded-card block listing the contract's normalized view of each backing
 * entry: parsed value + unit and the published working range. The range is
 * net-new information (the per-unit tolerance neighborhood the contract
 * derives) — the raw value string already renders in the parameter grid.
 */
export function ContractEntriesBlock({
  entries,
  testId,
}: {
  entries: RecommendationContractEntry[];
  testId: string;
}) {
  if (entries.length === 0) return null;
  return (
    <div data-testid={testId} className="border border-success/20 bg-success/5 rounded-sm px-2 py-2">
      <p className="text-meta font-mono text-success uppercase tracking-wide">
        Validated · recommendations.v1
      </p>
      {entries.map((entry, idx) => {
        const range = formatContractRange(entry);
        return (
          <p key={`${entry.parameter}-${idx}`} className="text-xs font-mono text-text-secondary mt-1">
            {entry.parameter}: <span className="text-text-primary font-bold">{formatContractValue(entry)}</span>
            {range ? ` · working range ${range}` : ''}
          </p>
        );
      })}
    </div>
  );
}

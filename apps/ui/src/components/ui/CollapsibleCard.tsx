import React from 'react';

import { getTextRoleClassName, type TextRole } from '../../utils/displayText';
import { cn } from './cn';
import { LedIndicator } from './LedIndicator';
import { Panel, type PanelProps } from './Panel';
import type { Status, Tone } from './variants';

// Single canonical collapsible-section card. Consolidates two patterns that
// were reimplemented across the results surface:
//   - AnalysisResults' local `Collapsible` (Sonic/Arrangement/Mix/Patch), and
//   - DiagnosticLog's accessible toggle header (`<button aria-expanded>`).
//
// Controlled by design (`open` + `onToggle`) so the parent owns expand state —
// the AnalysisResults sections keep their open-state in the parent component,
// and that's the contract every adopter follows.

function toneToLedStatus(tone: Tone): Status {
  if (tone === 'neutral') return 'idle';
  if (tone === 'accent') return 'active';
  return tone;
}

// Panel's tone vocabulary uses `active` where the shared Tone uses `accent`;
// everything else is shared. Map so a single `tone` prop drives both the LED
// and the Panel border-tint.
function toneToPanelTone(tone: Tone): PanelProps['tone'] {
  return tone === 'accent' ? 'active' : tone;
}

export interface CollapsibleCardProps {
  title: React.ReactNode;
  /** Optional small uppercase label rendered above the title. */
  eyebrow?: React.ReactNode;
  /**
   * Trailing controls (badges, buttons). Rendered as a sibling OUTSIDE the
   * toggle button so nested interactive elements stay valid HTML/a11y.
   */
  action?: React.ReactNode;
  open: boolean;
  onToggle: () => void;
  /** Drives both the header LED and the Panel border-tint. Default neutral — accent is reserved for primary signal. */
  tone?: Tone;
  titleRole?: TextRole;
  variant?: PanelProps['variant'];
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
}

export const CollapsibleCard = React.forwardRef<HTMLDivElement, CollapsibleCardProps>(
  function CollapsibleCard(
    {
      title,
      eyebrow,
      action,
      open,
      onToggle,
      tone = 'neutral',
      titleRole = 'subsection-title',
      variant = 'surface',
      className,
      bodyClassName,
      children,
    },
    ref,
  ) {
    const toggleLabel = typeof title === 'string' ? `Toggle ${title}` : 'Toggle section';

    return (
      <Panel
        ref={ref}
        variant={variant}
        tone={toneToPanelTone(tone)}
        padding="none"
        className={cn('overflow-hidden', className)}
      >
        <div className="flex items-center justify-between gap-3 px-3 py-2.5">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={open}
            aria-label={toggleLabel}
            className="group flex min-w-0 flex-1 items-center gap-2 text-left transition-colors"
          >
            <LedIndicator status={toneToLedStatus(tone)} />
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              {eyebrow ? (
                <span data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
                  {eyebrow}
                </span>
              ) : null}
              <span
                data-text-role={titleRole}
                className={cn(getTextRoleClassName(titleRole), 'truncate')}
              >
                {title}
              </span>
            </span>
            <span
              aria-hidden
              className="ml-1 text-meta text-text-secondary transition-colors group-hover:text-text-primary"
            >
              {open ? '▾' : '▸'}
            </span>
          </button>
          {action ? <div className="flex flex-shrink-0 items-center gap-2">{action}</div> : null}
        </div>
        {/*
          Height-agnostic collapse via the grid-rows 0fr→1fr technique. This
          deliberately replaces the old `max-h-[900px]` clip from AnalysisResults'
          local Collapsible, which silently truncated taller sections (e.g. the
          Mix chain / Patch framework when fully expanded). Children stay mounted
          so the transition can animate.
        */}
        <div
          className={cn(
            'grid transition-[grid-template-rows] duration-300 ease-out motion-reduce:transition-none',
            open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
          )}
        >
          <div
            className={cn(
              'overflow-hidden transition-opacity duration-300 motion-reduce:transition-none',
              open ? 'opacity-100' : 'opacity-0',
            )}
          >
            <div className={cn('px-3 pb-3 pt-1', bodyClassName)}>{children}</div>
          </div>
        </div>
      </Panel>
    );
  },
);

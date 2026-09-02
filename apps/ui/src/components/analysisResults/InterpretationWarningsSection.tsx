import { useMemo } from 'react';
import { getTextRoleClassName } from '../../utils/displayText';

import type { InterpretationValidationWarning } from '../../types';
import {
  formatDroppedValue,
  groupInterpretationWarnings,
} from '../analysisResultsViewModel';
import { textRoleClassName } from './shared';

export function InterpretationWarningsSection({
  validationWarnings,
}: {
  validationWarnings: InterpretationValidationWarning[];
}) {
  const groupedValidationWarnings = useMemo(
    () => groupInterpretationWarnings(validationWarnings),
    [validationWarnings],
  );
  const adjustmentGroups = useMemo(
    () => groupedValidationWarnings.filter((g) => g.tone === 'adjustment'),
    [groupedValidationWarnings],
  );
  const warningGroups = useMemo(
    () => groupedValidationWarnings.filter((g) => g.tone === 'warning'),
    [groupedValidationWarnings],
  );
  const hasAdjustments = adjustmentGroups.length > 0;
  const hasWarnings = warningGroups.length > 0;
  const isMixed = hasAdjustments && hasWarnings;
  const allValidationWarningsAreAdjustments = hasAdjustments && !hasWarnings;
  const adjustmentCount = adjustmentGroups.reduce((sum, g) => sum + g.count, 0);
  const warningCount = warningGroups.reduce((sum, g) => sum + g.count, 0);

  if (groupedValidationWarnings.length === 0) return null;

  return (
    <section
      data-testid="interpretation-warnings"
      className={`space-y-3 rounded-sm border p-4 ${
        isMixed
          ? 'border-border bg-bg-card'
          : allValidationWarningsAreAdjustments
            ? 'border-accent/25 bg-bg-card'
            : 'border-warning/25 bg-bg-card'
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2
            data-text-role="subsection-title"
            className={
              `${getTextRoleClassName('subsection-title')} ${
                isMixed
                  ? 'text-text-primary'
                  : allValidationWarningsAreAdjustments
                    ? 'text-accent'
                    : 'text-warning'
              }`
            }
          >
            {isMixed
              ? 'Interpretation Notes'
              : allValidationWarningsAreAdjustments ? 'Interpretation Adjustments' : 'Interpretation Caution'}
          </h2>
          <p
            className={`text-meta font-mono uppercase tracking-[0.16em] ${
              isMixed
                ? 'text-text-secondary'
                : allValidationWarningsAreAdjustments ? 'text-accent/80' : 'text-warning/80'
            }`}
          >
            {isMixed
              ? 'The backend made auto-corrections and flagged parts that may need review.'
              : allValidationWarningsAreAdjustments
                ? 'The backend kept the result and auto-corrected a few AI-generated labels so they match the detected session structure.'
                : 'The backend kept the result, but flagged parts that may not match the approved Live catalog.'}
          </p>
        </div>
        <span
          className={`text-meta font-mono uppercase px-2 py-1 rounded border ${
            isMixed
              ? 'border-border text-text-secondary'
              : allValidationWarningsAreAdjustments
                ? 'border-accent/30 text-accent'
                : 'border-warning/30 text-warning'
          }`}
        >
          {isMixed
            ? `${adjustmentCount} adjustment${adjustmentCount === 1 ? '' : 's'} · ${warningCount} warning${warningCount === 1 ? '' : 's'}`
            : allValidationWarningsAreAdjustments
              ? `${adjustmentCount} item${adjustmentCount === 1 ? '' : 's'}`
              : `${warningCount} warning${warningCount === 1 ? '' : 's'}`}
        </span>
      </div>
      <div className="space-y-2">
        {(isMixed ? [...adjustmentGroups, ...warningGroups] : groupedValidationWarnings).map((warning) => (
          <div
            key={warning.key}
            className={`rounded-sm border p-3 space-y-2 ${
              warning.tone === 'adjustment'
                ? 'border-accent/20 bg-bg-panel'
                : 'border-warning/20 bg-bg-panel'
            }`}
          >
            <div className="flex flex-wrap gap-1.5">
              {warning.code && (
                <span
                  className={`text-micro font-mono uppercase px-1.5 py-0.5 rounded border ${
                    warning.tone === 'adjustment'
                      ? 'border-accent/30 text-accent'
                      : 'border-warning/30 text-warning'
                  }`}
                >
                  {warning.code}
                </span>
              )}
              {warning.count > 1 && (
                <span
                  className={`text-micro font-mono uppercase px-1.5 py-0.5 rounded border ${
                    warning.tone === 'adjustment'
                      ? 'border-accent/25 text-accent/90'
                      : 'border-warning/25 text-warning/90'
                  }`}
                >
                  {warning.count} items
                </span>
              )}
            </div>
            <div className="space-y-1">
              <p
                className={`text-meta font-mono uppercase tracking-[0.16em] ${
                  warning.tone === 'adjustment' ? 'text-accent/85' : 'text-warning/85'
                }`}
              >
                {warning.title}
              </p>
              <p data-text-role="body" className={textRoleClassName('body')}>
                {warning.message}
              </p>
            </div>
            {warning.mappings.some((m) => m.originalValue || m.coercedValue || m.path) ? (
              <div className="space-y-1">
                {warning.mappings.map((m, mIdx) => (
                  <div
                    key={`${warning.key}-mapping-${mIdx}`}
                    className="flex flex-wrap items-center gap-1.5 text-micro font-mono text-text-secondary"
                  >
                    {(m.originalValue || m.coercedValue) && (
                      <>
                        {/* Audit Finding #1C: render compact human summary
                          for JSON-shaped values (dropped recommendations)
                          instead of dumping the raw object. See
                          `formatDroppedValue` in analysisResultsViewModel.ts. */}
                        <span className="px-1.5 py-0.5 rounded border border-border">
                          {formatDroppedValue(m.originalValue)}
                        </span>
                        <span className="opacity-50">→</span>
                        <span className="px-1.5 py-0.5 rounded border border-border">
                          {formatDroppedValue(m.coercedValue)}
                        </span>
                      </>
                    )}
                    {m.path && (
                      <span className="px-1.5 py-0.5 rounded border border-border opacity-70">
                        {m.path}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                <span className="text-micro font-mono px-1.5 py-0.5 rounded border border-border text-text-secondary">
                  Result-level warning
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

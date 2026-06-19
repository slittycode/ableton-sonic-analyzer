import React from 'react';

import type { ValidationReport, ValidationViolation } from '../services/phase2Validator';

interface Phase2ConsistencyReportProps {
  report: ValidationReport;
  /**
   * When set, suppress the "CONSISTENCY OK" row for a passed/clean report so the
   * results surface shows nothing on a clean run instead of green noise above
   * the recommendations. The Diagnostic Log leaves it unset to keep the
   * affirmative signal for the dev audience.
   */
  hideWhenClean?: boolean;
}

function formatViolationType(type: ValidationViolation['type']): string {
  const normalized = type.toLowerCase().replace(/_/g, ' ');
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function truncateDetail(message: string): string {
  if (message.length <= 120) return message;
  return `${message.slice(0, 117)}...`;
}

function severityClass(severity: ValidationViolation['severity']): string {
  return severity === 'ERROR' ? 'text-error' : 'text-warning';
}

export function Phase2ConsistencyReport({ report, hideWhenClean = false }: Phase2ConsistencyReportProps) {
  // Audit Finding #1E: dev-audience violations (currently NEW_FIELD_UNCITED
  // coverage signals) stay in `report.violations` and `report.summary` so
  // tests and offline analysis see them, but they are suppressed from the
  // user-facing System Diagnostics surface. Header counts are computed from
  // `userVisible` to prevent a "5 warnings shown" header above 0 rows.
  const userVisible = report.violations.filter((v) => v.audience !== 'dev');
  const userErrorCount = userVisible.filter((v) => v.severity === 'ERROR').length;
  const userWarningCount = userVisible.filter((v) => v.severity === 'WARNING').length;

  if (report.passed && userVisible.length === 0) {
    if (hideWhenClean) {
      return null;
    }
    return (
      <div className="text-meta font-mono uppercase tracking-wide text-success/70">
        CONSISTENCY OK
      </div>
    );
  }

  if (userVisible.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <div className="text-meta font-mono uppercase tracking-wide text-text-secondary">
        {userErrorCount} error(s), {userWarningCount} warning(s) across{' '}
        {report.summary.checkedFields} checked fields
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-border">
              {['Severity', 'Type', 'Field', 'Detail'].map((label) => (
                <th
                  key={label}
                  className="px-2 py-1 text-left text-meta font-mono uppercase tracking-wide text-text-secondary font-normal"
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {userVisible.map((violation, rowIndex) => (
              <tr
                key={`${violation.field}-${violation.type}-${rowIndex}`}
                className={`border-b border-border ${
                  rowIndex % 2 === 0 ? 'bg-bg-secondary' : ''
                }`}
              >
                <td className={`px-2 py-1 text-sm font-mono ${severityClass(violation.severity)}`}>
                  {violation.severity}
                </td>
                <td className="px-2 py-1 text-sm text-text-primary">
                  {formatViolationType(violation.type)}
                </td>
                <td className="px-2 py-1 text-sm text-text-primary">{violation.field}</td>
                <td className="px-2 py-1 text-sm text-text-primary">
                  {truncateDetail(violation.message)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

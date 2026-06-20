import React from 'react';

import { DataTable, type DataTableColumn } from './ui';
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

const violationColumns: DataTableColumn<ValidationViolation>[] = [
  {
    key: 'severity',
    label: 'Severity',
    render: (v) => (
      <span className={`font-mono ${severityClass(v.severity)}`}>{v.severity}</span>
    ),
  },
  { key: 'type', label: 'Type', render: (v) => formatViolationType(v.type) },
  { key: 'field', label: 'Field', render: (v) => v.field },
  { key: 'detail', label: 'Detail', render: (v) => truncateDetail(v.message) },
];

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

      <DataTable data={userVisible} columns={violationColumns} />
    </div>
  );
}

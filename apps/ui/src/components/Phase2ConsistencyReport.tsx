import React from 'react';

import type { ValidationReport, ValidationViolation } from '../services/phase2Validator';

interface Phase2ConsistencyReportProps {
  report: ValidationReport;
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

export function Phase2ConsistencyReport({ report }: Phase2ConsistencyReportProps) {
  if (report.passed && report.violations.length === 0) {
    return (
      <div className="text-[10px] font-mono uppercase tracking-wide text-success/70">
        CONSISTENCY OK
      </div>
    );
  }

  if (report.violations.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <div className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
        {report.summary.errorCount} error(s), {report.summary.warningCount} warning(s) across{' '}
        {report.summary.checkedFields} checked fields
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-border">
              {['Severity', 'Type', 'Field', 'Detail'].map((label) => (
                <th
                  key={label}
                  className="px-2 py-1 text-left text-[10px] font-mono uppercase tracking-wide text-text-secondary font-normal"
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {report.violations.map((violation, rowIndex) => (
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

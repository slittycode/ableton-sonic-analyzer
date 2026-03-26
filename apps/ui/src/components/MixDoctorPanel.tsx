import React from 'react';
import type { MixDoctorReport } from '../services/mixDoctor';

interface MixDoctorPanelProps {
  report: MixDoctorReport;
}

const formatNumber = (value: number | null | undefined, decimals = 2): string => {
  if (value === null || value === undefined) return '—';
  return typeof value === 'number' ? value.toFixed(decimals) : '—';
};

const MetricRow = ({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) => (
  <div className="flex justify-between items-center gap-4">
    <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
      {label}
    </span>
    <div className="flex items-center gap-2">
      <span className="text-sm font-display font-bold text-text-primary">
        {value}
      </span>
    </div>
  </div>
);

const SimpleTable = <T extends object>({
  data,
  columns,
}: {
  data: T[];
  columns: { key: string; label: string; format?: (value: unknown) => string }[];
}) => (
  <div className="overflow-x-auto">
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr className="border-b border-border">
          {columns.map((column) => (
            <th
              key={column.key}
              className="px-2 py-1 text-left text-[10px] font-mono uppercase tracking-wide text-text-secondary font-normal"
            >
              {column.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.map((row, rowIndex) => (
          <tr
            key={rowIndex}
            className={`border-b border-border ${
              rowIndex % 2 === 0 ? 'bg-bg-secondary' : ''
            }`}
          >
            {columns.map((column) => (
              <td
                key={`${rowIndex}-${column.key}`}
                className="px-2 py-1 text-sm text-text-primary"
              >
                {(() => {
                  const value = (row as Record<string, unknown>)[column.key];
                  return column.format
                    ? column.format(value)
                    : formatNumber(value as number);
                })()}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export function MixDoctorPanel({ report }: MixDoctorPanelProps) {
  /*
   // TODO: wire delta chart
   // TODO: wire band-issue details
  */
  return (
    <>
      <MetricRow
        label="Target Genre"
        value={`${report.genreName} (${report.genreId})`}
      />
      <MetricRow
        label="Health Score"
        value={`${report.overallScore}/100`}
      />
      <MetricRow
        label="Loudness Offset"
        value={formatNumber(report.loudnessOffset, 2)}
      />

      <div className="border-t border-border pt-3">
        <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
          Advisory Summary
        </span>
        <div className="mt-2 space-y-2 text-sm text-text-primary">
          <div>
            <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mr-2">
              Dynamics
            </span>
            {report.dynamicsAdvice.message}
          </div>
          <div>
            <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mr-2">
              Loudness
            </span>
            {report.loudnessAdvice.message}
          </div>
          <div>
            <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mr-2">
              Stereo
            </span>
            {report.stereoAdvice.message}
          </div>
        </div>
      </div>

      <div className="border-t border-border pt-3">
        <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
          Band Diagnostics
        </span>
        <div className="mt-2">
          <SimpleTable
            data={report.advice}
            columns={[
              { key: 'band', label: 'Band', format: (value) => String(value ?? '—') },
              {
                key: 'normalizedDb',
                label: 'Norm dB',
                format: (value) => formatNumber(value as number, 1),
              },
              {
                key: 'targetOptimalDb',
                label: 'Target dB',
                format: (value) => formatNumber(value as number, 1),
              },
              {
                key: 'diffDb',
                label: 'Delta dB',
                format: (value) => formatNumber(value as number, 1),
              },
              { key: 'issue', label: 'Issue', format: (value) => String(value ?? '—') },
            ]}
          />
        </div>
      </div>
    </>
  );
}

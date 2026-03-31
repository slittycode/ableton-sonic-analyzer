import React from 'react';
import type { MixDoctorReport, MixDynamicsIssue, MixIssue } from '../services/mixDoctor';
import {
  DeltaBadge,
  StatusBadge,
  StyledDataTable,
} from './MeasurementPrimitives';
import { formatDisplayText, getTextRoleClassName } from '../utils/displayText';

interface MixDoctorPanelProps {
  report: MixDoctorReport;
}

const formatNumber = (value: number | null | undefined, decimals = 2): string => {
  if (value === null || value === undefined) return '—';
  return typeof value === 'number' ? value.toFixed(decimals) : '—';
};

const toneForScore = (score: number): 'success' | 'warning' | 'error' => {
  if (score >= 80) return 'success';
  if (score >= 60) return 'warning';
  return 'error';
};

const toneForMixIssue = (issue: MixIssue): 'success' | 'warning' | 'error' => {
  if (issue === 'optimal') return 'success';
  if (issue === 'too-quiet') return 'warning';
  return 'error';
};

const toneForDynamicsIssue = (issue: MixDynamicsIssue): 'success' | 'warning' | 'error' => {
  if (issue === 'optimal') return 'success';
  if (issue === 'too-dynamic') return 'warning';
  return 'error';
};

const toneForStereoAdvice = (
  report: MixDoctorReport,
): 'success' | 'warning' | 'error' => {
  if (report.stereoAdvice.monoCompatible === false) return 'error';
  if (
    (report.stereoAdvice.correlation !== null && report.stereoAdvice.correlation < 0.2) ||
    ((report.stereoAdvice.correlation ?? 0) > 0.95 &&
      (report.stereoAdvice.width ?? 1) < 0.05)
  ) {
    return 'warning';
  }
  return 'success';
};

export function MixDoctorPanel({ report }: MixDoctorPanelProps) {
  const stereoTone = toneForStereoAdvice(report);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="rounded-sm border border-border-light border-l-2 border-accent bg-bg-surface-dark p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
          <span data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
            Target Genre
          </span>
          <div data-text-role="item-title" className={`mt-3 ${getTextRoleClassName('item-title')}`}>
            {formatDisplayText(report.genreName, 'title')}
          </div>
          <div className="mt-2">
            <StatusBadge label={report.genreId} tone="muted" compact />
          </div>
        </div>

        <div className="rounded-sm border border-border-light border-l-2 border-accent bg-bg-surface-dark p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
          <span data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
            Health Score
          </span>
          <div className="mt-3">
            <StatusBadge
              label={`${report.overallScore}/100`}
              tone={toneForScore(report.overallScore)}
            />
          </div>
        </div>

        <div className="rounded-sm border border-border-light border-l-2 border-accent bg-bg-surface-dark p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
          <span data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
            Loudness Offset
          </span>
          <div className="mt-3">
            <DeltaBadge
              value={report.loudnessOffset}
              decimals={1}
              okThreshold={0.5}
              warnThreshold={1.5}
              unit="dB"
            />
          </div>
        </div>
      </div>

      <div className="border-t border-border pt-3">
        <span data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
          Advisory Summary
        </span>
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
          {[
            {
              label: 'Dynamics',
              tone: toneForDynamicsIssue(report.dynamicsAdvice.issue),
              message: report.dynamicsAdvice.message,
            },
            {
              label: 'Loudness',
              tone: toneForMixIssue(report.loudnessAdvice.issue),
              message: report.loudnessAdvice.message,
            },
            {
              label: 'Stereo',
              tone: stereoTone,
              message: report.stereoAdvice.message,
            },
          ].map((item) => (
            <div
              key={item.label}
              className="rounded-sm border border-border-light bg-bg-card/35 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
            >
              <StatusBadge label={item.label} tone={item.tone} compact />
              <p className="mt-2 text-sm leading-5 text-text-primary">{item.message}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-border pt-3">
        <span data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
          Band Diagnostics
        </span>
        <div className="mt-3">
          <StyledDataTable
            data={report.advice}
            columns={[
              {
                key: 'band',
                label: 'Band',
                displayCase: 'eyebrow',
                textRole: 'eyebrow',
                render: (row) => row.band,
              },
              {
                key: 'normalizedDb',
                label: 'Norm dB',
                align: 'right',
                monospace: true,
                render: (row) => formatNumber(row.normalizedDb, 1),
              },
              {
                key: 'targetOptimalDb',
                label: 'Target dB',
                align: 'right',
                monospace: true,
                render: (row) => formatNumber(row.targetOptimalDb, 1),
              },
              {
                key: 'diffDb',
                label: 'Delta dB',
                render: (row) => (
                  <div className="flex justify-end">
                    <DeltaBadge
                      value={row.diffDb}
                      decimals={1}
                      okThreshold={0.5}
                      warnThreshold={1.5}
                      unit="dB"
                    />
                  </div>
                ),
              },
              {
                key: 'issue',
                label: 'Issue',
                render: (row) => (
                  <div className="flex justify-start">
                    <StatusBadge label={row.issue} tone={toneForMixIssue(row.issue)} compact />
                  </div>
                ),
              },
            ]}
          />
        </div>
      </div>
    </div>
  );
}

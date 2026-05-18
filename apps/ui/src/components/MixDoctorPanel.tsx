import React from 'react';
import type { MixDoctorReport, MixDynamicsIssue, MixIssue } from '../services/mixDoctor';
import {
  DeltaBadge,
  StatusBadge,
} from './MeasurementPrimitives';
import { DataTable, MetricTile, Panel } from './ui';
import { getTextRoleClassName } from '../utils/displayText';

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
        <MetricTile
          size="md"
          accent="accent"
          label="Target Genre"
          value={report.genreName}
          footer={<StatusBadge label={report.genreId} tone="muted" compact />}
        />
        <MetricTile
          size="md"
          accent="accent"
          label="Health Score"
          value={
            <StatusBadge
              label={`${report.overallScore}/100`}
              tone={toneForScore(report.overallScore)}
            />
          }
        />
        <MetricTile
          size="md"
          accent="accent"
          label="Loudness Offset"
          value={
            <DeltaBadge
              value={report.loudnessOffset}
              decimals={1}
              okThreshold={0.5}
              warnThreshold={1.5}
              unit="dB"
            />
          }
        />
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
            <Panel key={item.label} variant="surface" padding="md">
              <StatusBadge label={item.label} tone={item.tone} compact />
              <p className="mt-2 text-sm leading-5 text-text-primary">{item.message}</p>
            </Panel>
          ))}
        </div>
      </div>

      <div className="border-t border-border pt-3">
        <span data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
          Band Diagnostics
        </span>
        <div className="mt-3">
          <DataTable
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
                // Audit quick-hit: previously rendered just the optimal dB
                // (e.g. "-22.0"). Without the per-band range, producers
                // couldn't tell why a +5.6 dB Delta on Sub Bass reads
                // "too-loud" while a +5.5 dB Delta on Low Mids reads
                // "optimal" — the Issue is determined by absolute thresholds
                // (target.minDb / maxDb), not by the diff-from-optimal. Show
                // the range alongside the optimal so the verdict is legible
                // at a glance.
                key: 'targetOptimalDb',
                label: 'Target (range)',
                align: 'right',
                monospace: true,
                render: (row) =>
                  `${formatNumber(row.targetOptimalDb, 1)} (${formatNumber(row.targetMinDb, 0)} to ${formatNumber(row.targetMaxDb, 0)})`,
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

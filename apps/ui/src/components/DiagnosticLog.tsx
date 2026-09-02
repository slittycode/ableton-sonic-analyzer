import React, { useEffect, useState } from 'react';

import { Phase2ConsistencyReport } from './Phase2ConsistencyReport';
import { DeviceRack, Pill } from './ui';
import { BackendTimingDiagnostics, DiagnosticLogEntry, DiagnosticLogStatus } from '../types';
import { assertNever } from '../utils/assertNever';

interface DiagnosticLogProps {
  logs: DiagnosticLogEntry[];
  defaultExpanded?: boolean;
}

function statusLabel(status: DiagnosticLogStatus | undefined): string {
  return (status ?? 'success').toUpperCase();
}

function statusPillTone(
  status: DiagnosticLogStatus | undefined,
): React.ComponentProps<typeof Pill>['tone'] {
  if (status === undefined) return 'success';
  switch (status) {
    case 'running':
      return 'accent';
    case 'error':
      return 'error';
    case 'skipped':
      return 'warning';
    case 'success':
      return 'success';
    default:
      return assertNever(status);
  }
}

function formatEstimateRange(lowMs?: number, highMs?: number): string | null {
  if (typeof lowMs !== 'number' || typeof highMs !== 'number') return null;
  return `${Math.round(lowMs / 1000)}s-${Math.round(highMs / 1000)}s`;
}

function formatTimingValue(value: number): string {
  return value.toFixed(2).replace(/\.?0+$/, '');
}

function formatTimings(timings: BackendTimingDiagnostics): string {
  const flagsLabel = timings.flagsUsed.length > 0 ? timings.flagsUsed.join(' ') : 'none';
  const msPerSecondLabel =
    timings.msPerSecondOfAudio === null ? 'N/A' : formatTimingValue(timings.msPerSecondOfAudio);

  return [
    `TOTAL: ${formatTimingValue(timings.totalMs)}ms`,
    `ANALYSIS: ${formatTimingValue(timings.analysisMs)}ms`,
    `OVERHEAD: ${formatTimingValue(timings.serverOverheadMs)}ms`,
    `FLAGS: ${flagsLabel}`,
    `${msPerSecondLabel} ms/s of audio`,
  ].join(' | ');
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 min-w-0">
      <span className="text-text-muted shrink-0">{label}</span>
      <span className="text-text-primary truncate text-right">{value}</span>
    </div>
  );
}

export function DiagnosticLog({ logs, defaultExpanded }: DiagnosticLogProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded ?? true);

  useEffect(() => {
    if (defaultExpanded) setIsExpanded(true);
  }, [defaultExpanded]);

  if (logs.length === 0) return null;

  const showRunningCursor = logs.some((log) => (log.status ?? 'success') === 'running');
  const rackStatus = showRunningCursor
    ? 'active'
    : logs.some((log) => log.status === 'error')
      ? 'error'
      : 'success';

  return (
    // W1-05: terminal diagnostics as DeviceRack — flat face, mono log density,
    // Live title strip (no soft cards / left accent stripes).
    <div className="mt-6" data-testid="system-diagnostics">
      <DeviceRack
        name="System Diagnostics"
        status={rackStatus}
        density="dense"
        action={
          <button
            type="button"
            onClick={() => setIsExpanded((prev) => !prev)}
            className="text-meta font-mono uppercase tracking-[0.14em] text-text-muted hover:text-text-primary transition-colors"
            aria-expanded={isExpanded}
            aria-label="Toggle diagnostic log"
          >
            {isExpanded ? '▾' : '▸'} {logs.length} {logs.length === 1 ? 'entry' : 'entries'}
          </button>
        }
      >
        {/* Keep visible label for smoke that searches "System Diagnostics" in page;
            title strip already has it; action is collapse only. */}
        {!isExpanded ? (
          <button
            type="button"
            onClick={() => setIsExpanded(true)}
            className="w-full text-left text-meta font-mono uppercase tracking-[0.14em] text-text-muted hover:text-text-secondary py-1"
          >
            Expand log
          </button>
        ) : (
          <div className="bg-bg-surface-darker border border-border font-mono text-meta overflow-x-auto">
            <div className="divide-y divide-border/80">
              {logs.map((log, idx) => {
                const estimateRange = formatEstimateRange(log.estimateLowMs, log.estimateHighMs);
                return (
                  <div key={idx} className="px-3 py-2.5 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2 text-accent">
                      <span className="text-text-muted">
                        [{new Date(log.timestamp).toLocaleTimeString()}]
                      </span>
                      <span className="font-medium tracking-wide uppercase text-text-primary">
                        &gt;&gt; {log.phase}
                      </span>
                      <Pill tone={statusPillTone(log.status)} size="xs">
                        {statusLabel(log.status)}
                      </Pill>
                    </div>
                    {log.message && (
                      <p className="text-text-secondary leading-relaxed whitespace-pre-line">
                        {log.message}
                      </p>
                    )}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-0.5 text-body-sm">
                      <MetaRow label="MODEL:" value={log.model} />
                      <MetaRow
                        label="EXEC_TIME:"
                        value={(log.status ?? 'success') === 'running' ? '--' : `${log.durationMs}ms`}
                      />
                      <MetaRow label="TOKENS_IN:" value={log.promptLength} />
                      <MetaRow label="TOKENS_OUT:" value={log.responseLength} />
                      {log.requestId && (
                        <div className="sm:col-span-2">
                          <MetaRow label="REQUEST_ID:" value={log.requestId} />
                        </div>
                      )}
                      {log.errorCode && <MetaRow label="ERROR_CODE:" value={log.errorCode} />}
                      {estimateRange && <MetaRow label="ESTIMATE:" value={estimateRange} />}
                      {idx === 0 && (
                        <>
                          <div className="sm:col-span-2">
                            <MetaRow label="FILE:" value={log.audioMetadata.name} />
                          </div>
                          <MetaRow
                            label="SIZE:"
                            value={`${(log.audioMetadata.size / 1024).toFixed(1)} KB`}
                          />
                          <MetaRow label="TYPE:" value={log.audioMetadata.type} />
                        </>
                      )}
                    </div>
                    {log.timings && (
                      <p className="text-text-muted whitespace-nowrap overflow-x-auto">
                        <span className="text-text-muted">TIMINGS:</span>{' '}
                        <span className="text-text-secondary">{formatTimings(log.timings)}</span>
                      </p>
                    )}
                    {log.stageKey === 'interpretation' && log.validationReport && (
                      <div className="pt-1">
                        <Phase2ConsistencyReport report={log.validationReport} />
                      </div>
                    )}
                    {log.stageKey === 'interpretation' && log.validationError && (
                      <div className="text-meta font-mono uppercase tracking-wide text-error">
                        CONSISTENCY CHECK FAILED: {log.validationError}
                      </div>
                    )}
                  </div>
                );
              })}
              {showRunningCursor && (
                <div className="px-3 py-1 text-accent/60 animate-pulse">_</div>
              )}
            </div>
          </div>
        )}
      </DeviceRack>
    </div>
  );
}

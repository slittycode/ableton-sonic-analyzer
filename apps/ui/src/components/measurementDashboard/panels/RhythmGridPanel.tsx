import { useEffect, useMemo, useState } from 'react';

import type { Phase1Result } from '../../../types';
import { clamp, formatNumber, isAssumedMeter } from '../lib/formatters';

export const RhythmGridPanel = ({ phase1 }: { phase1: Phase1Result }) => {
  const rhythmTimeline = phase1.rhythmTimeline;
  const availableWindows = useMemo(
    () => (rhythmTimeline?.windows ?? []).slice().sort((left, right) => left.bars - right.bars),
    [rhythmTimeline],
  );
  const defaultWindowBars = availableWindows.find((window) => window.bars === 8)?.bars
    ?? availableWindows[0]?.bars
    ?? null;
  const [selectedWindowBars, setSelectedWindowBars] = useState<number | null>(defaultWindowBars);

  useEffect(() => {
    setSelectedWindowBars(defaultWindowBars);
  }, [defaultWindowBars]);

  const selectedWindow = useMemo(() => {
    if (availableWindows.length === 0) return null;
    return availableWindows.find((window) => window.bars === selectedWindowBars) ?? availableWindows[0];
  }, [availableWindows, selectedWindowBars]);

  if (!rhythmTimeline || !selectedWindow) return null;

  const beatsPerBar = Math.max(1, rhythmTimeline.beatsPerBar || 4);
  const stepsPerBeat = Math.max(1, rhythmTimeline.stepsPerBeat || 4);
  const stepsPerBar = beatsPerBar * stepsPerBeat;
  const barNumbers = Array.from(
    { length: selectedWindow.bars },
    (_, index) => selectedWindow.startBar + index,
  );
  const barCellWidth = stepsPerBar * 12 + (stepsPerBar - 1) * 2 + 8;
  const lanes = [
    {
      label: 'LOW BAND',
      helper: 'kick-weighted proxy',
      values: selectedWindow.lowBandSteps,
      rgb: '255, 68, 68',
      labelColor: '#ff6b6b',
    },
    {
      label: 'MID BAND',
      helper: 'snare-range proxy',
      values: selectedWindow.midBandSteps,
      rgb: '245, 158, 11',
      labelColor: '#fbbf24',
    },
    {
      label: 'HIGH BAND',
      helper: 'hat-range proxy',
      values: selectedWindow.highBandSteps,
      rgb: '96, 165, 250',
      labelColor: '#93c5fd',
    },
    {
      label: 'OVERALL ACCENT',
      helper: 'summed band energy',
      values: selectedWindow.overallSteps,
      rgb: '52, 211, 153',
      labelColor: '#6ee7b7',
    },
  ];

  return (
    <div
      data-testid="rhythm-grid-panel"
      className="rounded-sm border border-border bg-bg-surface-dark p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]"
    >
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">
            Rhythm Grid
          </span>
          {isAssumedMeter(phase1) && (
            <span className="inline-flex items-center rounded-sm border border-[#3a2b1c] bg-[#20160c] px-2 py-1 text-meta font-mono uppercase tracking-[0.14em] text-[#d8a15d]">
              Assumed 4/4
            </span>
          )}
          {availableWindows.length > 1 && (
            <div className="ml-1 inline-flex items-center gap-1">
              {availableWindows.map((window) => {
                const isActive = selectedWindow.bars === window.bars;
                return (
                  <button
                    key={window.bars}
                    type="button"
                    onClick={() => setSelectedWindowBars(window.bars)}
                    data-testid={`rhythm-grid-window-${window.bars}`}
                    className={`rounded-sm border px-2 py-1 text-meta font-mono uppercase tracking-[0.14em] transition-colors ${
                      isActive
                        ? 'border-accent/50 bg-accent/10 text-accent'
                        : 'border-[#2a2a2a] bg-[#111111] text-text-secondary hover:border-accent/30 hover:text-text-primary'
                    }`}
                  >
                    {window.bars} BAR
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <p className="max-w-[360px] text-meta font-mono uppercase tracking-[0.14em] text-[#6d6d6d]">
          DSP band-energy lanes. Frequency-band proxies, not isolated stems.
        </p>
      </div>

      <div className="mt-4 overflow-x-auto pb-1">
        <div className="min-w-max">
          <div className="flex items-center gap-3">
            <div className="w-[136px] shrink-0" />
            {barNumbers.map((barNumber) => (
              <div
                key={`bar-header-${barNumber}`}
                data-testid={`rhythm-grid-bar-${barNumber}`}
                className="rounded-sm border border-border-light bg-bg-surface-dark px-2 py-2 text-center text-meta font-mono text-text-secondary"
                style={{ width: `${barCellWidth}px` }}
              >
                {barNumber}
              </div>
            ))}
          </div>

          <div className="mt-2 space-y-2">
            {lanes.map((lane) => (
              <div key={lane.label} className="flex items-start gap-3">
                <div className="flex min-h-[42px] w-[136px] shrink-0 flex-col justify-center rounded-sm border border-border bg-bg-surface-dark px-3 py-2">
                  <span
                    className="text-meta font-mono uppercase tracking-[0.12em]"
                    style={{ color: lane.labelColor }}
                  >
                    {lane.label}
                  </span>
                  <span className="mt-1 text-nano font-mono uppercase tracking-[0.12em] text-[#5f5f5f]">
                    {lane.helper}
                  </span>
                </div>

                <div className="flex gap-3">
                  {barNumbers.map((barNumber, barIndex) => {
                    const startIndex = barIndex * stepsPerBar;
                    const barSteps = lane.values.slice(startIndex, startIndex + stepsPerBar);
                    return (
                      <div
                        key={`${lane.label}-bar-${barNumber}`}
                        className="rounded-sm border border-border bg-bg-surface-dark p-1"
                        style={{ width: `${barCellWidth}px` }}
                      >
                        <div
                          className="grid gap-[2px]"
                          style={{ gridTemplateColumns: `repeat(${stepsPerBar}, minmax(0, 1fr))` }}
                        >
                          {barSteps.map((value, stepIndex) => {
                            const clampedValue = clamp(value ?? 0, 0, 1);
                            const isActive = clampedValue > 0.02;
                            const isBeatBoundary = stepIndex % stepsPerBeat === 0;
                            const borderOpacity = isBeatBoundary ? 0.15 : 0.08;
                            const fillOpacity = isActive ? Math.max(0.14, clampedValue * 0.92) : 0.04;
                            return (
                              <div
                                key={`${lane.label}-${barNumber}-${stepIndex}`}
                                className="h-5 rounded-[2px] border transition-colors"
                                title={`${lane.label} bar ${barNumber} step ${stepIndex + 1}: ${formatNumber(clampedValue, 2)}`}
                                style={{
                                  borderColor: `rgba(255,255,255,${borderOpacity})`,
                                  backgroundColor: isActive
                                    ? `rgba(${lane.rgb}, ${fillOpacity})`
                                    : 'rgba(255,255,255,0.035)',
                                  boxShadow: isActive && clampedValue >= 0.55
                                    ? `inset 0 0 0 1px rgba(${lane.rgb}, 0.55), 0 0 8px rgba(${lane.rgb}, 0.14)`
                                    : undefined,
                                }}
                              />
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

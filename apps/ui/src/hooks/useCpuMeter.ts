import { useEffect, useState } from 'react';

const ACTIVE_RANGE = { min: 60, max: 95 };
const IDLE_RANGE = { min: 2, max: 8 };

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function nextMeterValue(current: number, isAnalyzing: boolean): number {
  const range = isAnalyzing ? ACTIVE_RANGE : IDLE_RANGE;
  const midpoint = (range.min + range.max) / 2;
  const jitter = (Math.random() - 0.5) * (isAnalyzing ? 18 : 4);
  const spike = isAnalyzing && Math.random() > 0.88 ? Math.random() * 10 : 0;
  const target = clamp(midpoint + jitter + spike, range.min, range.max);

  return clamp(current * 0.55 + target * 0.45, range.min, range.max);
}

export function useCpuMeter(isAnalyzing: boolean): number {
  const [value, setValue] = useState(() => (isAnalyzing ? 72 : 4));

  useEffect(() => {
    setValue((current) => nextMeterValue(current, isAnalyzing));

    const intervalId = window.setInterval(() => {
      setValue((current) => nextMeterValue(current, isAnalyzing));
    }, isAnalyzing ? 140 : 220);

    return () => window.clearInterval(intervalId);
  }, [isAnalyzing]);

  return Math.round(value);
}

import React from 'react';
import { dbToColor } from '../utils/colorScales';

interface MiniHeatmapRow {
  label: string;
  values: number[];
}

interface MiniHeatmapProps {
  rows: MiniHeatmapRow[];
  cellLabels?: string[];
  title: string;
  colorFn?: (t: number) => string;
  rowHeight?: number;
}

export function MiniHeatmap({
  rows,
  cellLabels,
  title,
  colorFn = dbToColor,
  rowHeight = 28,
}: MiniHeatmapProps) {
  return (
    <div className="space-y-1">
      <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
        {title}
      </span>
      <div className="space-y-px">
        {rows.map((row) => {
          const maxVal = Math.max(...row.values, 1e-10);
          const minVal = Math.min(...row.values);
          const range = maxVal - minVal || 1;
          return (
            <div key={row.label} className="flex items-center gap-1">
              <span className="text-[8px] font-mono text-text-secondary/60 w-14 text-right shrink-0 uppercase">
                {row.label}
              </span>
              <div className="flex gap-px flex-1">
                {row.values.map((val, i) => {
                  const normalized = (val - minVal) / range;
                  return (
                    <div
                      key={i}
                      className="flex-1 rounded-sm transition-opacity hover:opacity-80"
                      style={{
                        height: `${rowHeight}px`,
                        backgroundColor: colorFn(normalized),
                      }}
                      title={`${cellLabels?.[i] ?? `B${i + 1}`}: ${val.toFixed(3)}`}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
      {cellLabels && (
        <div className="flex gap-px" style={{ marginLeft: 'calc(3.5rem + 4px)' }}>
          {cellLabels.map((label) => (
            <span
              key={label}
              className="flex-1 text-center text-[7px] font-mono text-text-secondary/40"
            >
              {label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

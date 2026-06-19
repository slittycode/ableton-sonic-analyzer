// Quantize grid + swing slider — shared between the stem-note draft block and
// the melody contour block. Each block owns its own QuantizeOptions state so
// the two grids are independent. This component is purely controlled.

import React from 'react';
import { Grid3X3, SlidersHorizontal } from 'lucide-react';
import { gridLabel } from '../../services/midi/quantization';
import type { QuantizeGrid, QuantizeOptions } from '../../services/midi/types';

const GRID_OPTIONS: QuantizeGrid[] = ['off', '1/4', '1/8', '1/16', '1/32'];

interface QuantizeControlsProps {
  value: QuantizeOptions;
  onChange: (next: QuantizeOptions) => void;
  disabled?: boolean;
}

export function QuantizeControls({ value, onChange, disabled = false }: QuantizeControlsProps) {
  const swingDisabled = disabled || value.grid === 'off';
  return (
    <div className="flex flex-wrap items-center gap-4 p-3 border border-border rounded-sm bg-bg-panel/40">
      <div className="flex items-center gap-2">
        <Grid3X3 className="w-3.5 h-3.5 text-text-secondary" />
        <span className="text-meta font-mono uppercase text-text-secondary">Quantize</span>
      </div>

      <div className="flex items-center gap-1">
        {GRID_OPTIONS.map((grid) => (
          <button
            key={grid}
            onClick={() => onChange({ ...value, grid })}
            disabled={disabled}
            className={`px-2 py-1 text-meta font-mono rounded border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
              value.grid === grid
                ? 'border-accent text-accent bg-accent/10'
                : 'border-border text-text-secondary bg-bg-card hover:bg-bg-panel'
            }`}
          >
            {gridLabel(grid)}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2 ml-auto">
        <SlidersHorizontal className="w-3.5 h-3.5 text-text-secondary" />
        <span className="text-meta font-mono uppercase text-text-secondary">Swing</span>
        <input
          type="range"
          min={0}
          max={100}
          value={value.swing}
          onChange={(event) => onChange({ ...value, swing: Number(event.target.value) })}
          disabled={swingDisabled}
          className="w-20 h-1 accent-accent disabled:opacity-30"
        />
        <span className="text-meta font-mono text-text-secondary w-8 text-right">
          {value.swing}%
        </span>
      </div>
    </div>
  );
}

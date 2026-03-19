import React, { useMemo } from 'react';
import { motion } from 'motion/react';
import type { ChromaViewModel } from './analysisResultsViewModel';

interface ChromaDisplayProps {
  viewModel: ChromaViewModel;
}

// SVG layout constants
const SVG_WIDTH = 400;
const SVG_HEIGHT = 160;
const BAR_AREA_TOP = 12;
const BAR_AREA_BOTTOM = 130;
const BAR_HEIGHT_MAX = BAR_AREA_BOTTOM - BAR_AREA_TOP;
const LABEL_Y = 148;
const BAR_WIDTH = 24;
const BAR_GAP = 9;
const TOTAL_BARS_WIDTH = 12 * BAR_WIDTH + 11 * BAR_GAP;
const BAR_START_X = (SVG_WIDTH - TOTAL_BARS_WIDTH) / 2;
const GRID_Y = BAR_AREA_TOP + BAR_HEIGHT_MAX / 2;

export function ChromaDisplay({ viewModel }: ChromaDisplayProps) {
  const pitchClasses = viewModel.pitchClasses;

  const ariaDescription = useMemo(() => {
    const parts = pitchClasses.map((pitchClass) => {
      const pct = Math.round(pitchClass.energy * 100);
      return `${pitchClass.name}: ${pct}%`;
    });
    return `Pitch class energy distribution. ${parts.join(', ')}`;
  }, [pitchClasses]);

  const prefersReducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  return (
    <div className="bg-bg-card border border-border rounded-sm p-4">
      <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-3">
        Pitch Class Energy
      </p>

      <svg
        viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
        role="img"
        aria-label={ariaDescription}
        className="w-full"
      >
        <line
          x1={BAR_START_X}
          y1={GRID_Y}
          x2={BAR_START_X + TOTAL_BARS_WIDTH}
          y2={GRID_Y}
          stroke="currentColor"
          strokeOpacity={0.1}
          strokeWidth={1}
          strokeDasharray="4 3"
        />

        {pitchClasses.map((pitchClass, i) => {
          const x = BAR_START_X + i * (BAR_WIDTH + BAR_GAP);
          const energy = pitchClass.energy;
          const barHeight = Math.max(energy * BAR_HEIGHT_MAX, 4);
          const y = BAR_AREA_BOTTOM - barHeight;
          const opacity = 0.45 + energy * 0.55;

          return (
            <g key={pitchClass.name}>
              <title>{`${pitchClass.name}: ${(energy * 100).toFixed(0)}% energy`}</title>

              <motion.rect
                x={x}
                y={prefersReducedMotion ? y : BAR_AREA_BOTTOM}
                width={BAR_WIDTH}
                height={prefersReducedMotion ? barHeight : 0}
                rx={2}
                fill="#ff8800"
                fillOpacity={opacity}
                stroke={pitchClass.isInScale ? '#ff8800' : 'none'}
                strokeWidth={pitchClass.isInScale ? 1.5 : 0}
                strokeOpacity={1}
                {...(!prefersReducedMotion && {
                  animate: { y, height: barHeight },
                  transition: {
                    duration: 0.2,
                    delay: i * 0.03,
                    ease: 'easeOut',
                  },
                })}
              />

              <text
                x={x + BAR_WIDTH / 2}
                y={LABEL_Y}
                textAnchor="middle"
                className="fill-text-secondary"
                fontSize={10}
                fontFamily="monospace"
              >
                {pitchClass.name}
              </text>
            </g>
          );
        })}
      </svg>

      {viewModel.interpretation && (
        <p className="text-xs font-mono text-text-secondary mt-3 leading-relaxed">
          {viewModel.interpretation}
        </p>
      )}
    </div>
  );
}

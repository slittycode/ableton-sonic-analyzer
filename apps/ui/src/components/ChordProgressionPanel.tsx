import React, { useMemo } from 'react';
import { motion } from 'motion/react';
import type { ChordDetail } from '../types';
import { PhaseSourceBadge } from './PhaseSourceBadge';
import {
  buildChordProgressionViewModel,
  truncateAtSentenceBoundary,
} from './analysisResultsViewModel';

interface ChordProgressionPanelProps {
  chordDetail: ChordDetail | null | undefined;
  detectedKey: string | null;
  keyConfidence: number;
  durationSeconds: number;
}

const SVG_WIDTH = 700;
const SVG_HEIGHT = 80;
const LABEL_AREA_HEIGHT = 16;
const BLOCK_HEIGHT = SVG_HEIGHT - LABEL_AREA_HEIGHT;
const BLOCK_GAP = 1;
const MIN_LABEL_WIDTH_PERCENT = 4;

function isMinorChordLabel(chord: string): boolean {
  const trimmed = chord.trim();
  // Parse past root (1 or 2 chars)
  const PITCH_ROOTS: Record<string, boolean> = {
    "C#": true, "Db": true, "D#": true, "Eb": true, "F#": true,
    "Gb": true, "G#": true, "Ab": true, "A#": true, "Bb": true, "Cb": true, "Fb": true,
  };
  const rootLen = (trimmed.length >= 2 && PITCH_ROOTS[trimmed.slice(0, 2)]) ? 2 : 1;
  const suffix = trimmed.slice(rootLen).toLowerCase();
  return suffix.startsWith("m") && !suffix.startsWith("maj");
}

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0s";
  const rounded = Math.round(seconds * 10) / 10;
  return `${rounded}s`;
}

export function ChordProgressionPanel({
  chordDetail,
  detectedKey,
  keyConfidence,
  durationSeconds,
}: ChordProgressionPanelProps) {
  const vm = useMemo(
    () => buildChordProgressionViewModel(chordDetail, detectedKey, keyConfidence, durationSeconds),
    [chordDetail, detectedKey, keyConfidence, durationSeconds],
  );

  if (!vm) return null;

  const prefersReducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  return (
    <div className="space-y-4">
      {/* Section header */}
      <div className="flex items-center justify-between border-b border-border pb-2">
        <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
          <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
          Chord Progression
        </h2>
        <span className="text-[10px] font-mono bg-bg-panel border border-border px-2 py-1 rounded font-bold text-text-secondary">
          PHASE 1
        </span>
      </div>

      {/* SVG Chord Timeline */}
      <div className="bg-bg-card border border-border rounded-sm p-4">
        <svg
          viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
          className="w-full"
          role="img"
          aria-label="Chord progression timeline"
        >
          {vm.blocks.map((block, index) => {
            const x = (block.startPercent / 100) * SVG_WIDTH + BLOCK_GAP / 2;
            const blockWidth = Math.max(
              (block.widthPercent / 100) * SVG_WIDTH - BLOCK_GAP,
              2,
            );
            const isMinor = isMinorChordLabel(block.label);
            const lightness = isMinor ? 35 : 50;
            const fill = `hsl(${block.colorHue}, 70%, ${lightness}%)`;
            const showLabel = block.widthPercent > MIN_LABEL_WIDTH_PERCENT;

            const motionProps = prefersReducedMotion
              ? {}
              : {
                  initial: { opacity: 0, scaleY: 0 } as const,
                  animate: { opacity: 1, scaleY: 1 } as const,
                  transition: {
                    delay: index * 0.04,
                    duration: 0.2,
                    ease: 'easeOut' as const,
                  },
                };

            return (
              <motion.g
                key={`${block.label}-${index}`}
                style={{ transformOrigin: `${x + blockWidth / 2}px ${BLOCK_HEIGHT}px` }}
                {...motionProps}
              >
                <rect
                  x={x}
                  y={0}
                  width={blockWidth}
                  height={BLOCK_HEIGHT}
                  rx={2}
                  ry={2}
                  fill={fill}
                >
                  <title>{block.label}</title>
                </rect>
                {showLabel && (
                  <text
                    x={x + blockWidth / 2}
                    y={BLOCK_HEIGHT / 2 + 4}
                    textAnchor="middle"
                    fill="#fff"
                    fontSize={blockWidth > 50 ? 11 : 9}
                    fontFamily="monospace"
                    fontWeight="bold"
                  >
                    {block.label}
                  </text>
                )}
              </motion.g>
            );
          })}

          {/* Time scale */}
          <text
            x={2}
            y={SVG_HEIGHT - 2}
            fill="currentColor"
            className="text-text-secondary"
            fontSize={9}
            fontFamily="monospace"
            opacity={0.6}
          >
            0s
          </text>
          <text
            x={SVG_WIDTH - 2}
            y={SVG_HEIGHT - 2}
            textAnchor="end"
            fill="currentColor"
            className="text-text-secondary"
            fontSize={9}
            fontFamily="monospace"
            opacity={0.6}
          >
            {formatDuration(durationSeconds)}
          </text>
        </svg>
      </div>

      {/* Harmonic Summary */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <PhaseSourceBadge source="measured" />
          {vm.isApproximate && (
            <span
              className="text-[10px] font-mono text-warning"
              title="Low confidence — treat this as approximate."
              aria-label="Low confidence"
            >
              Chord detection confidence is low — treat as estimated
            </span>
          )}
        </div>

        <div className="space-y-2">
          <p className="text-xs font-mono text-text-primary">
            <span className="text-text-secondary">Primary chords: </span>
            {vm.dominantChords.join(", ")}
          </p>
          <p className="text-xs font-mono text-text-secondary">
            {vm.harmonicCharacter}
          </p>
          <p className="text-xs font-mono text-text-secondary">
            {vm.keyRelationship}
          </p>
        </div>

        {/* Ableton Pro Tip */}
        <div className="border border-accent/20 bg-accent/5 rounded-sm px-2 py-2">
          <p className="text-[10px] font-mono text-accent uppercase tracking-wide">PRO TIP</p>
          <p className="text-xs font-mono text-text-secondary mt-1 leading-relaxed">
            {truncateAtSentenceBoundary(vm.abletonTip, 320)}
          </p>
        </div>
      </div>
    </div>
  );
}

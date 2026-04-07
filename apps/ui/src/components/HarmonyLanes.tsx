import React from 'react';
import type { Phase1Result } from '../types';
import { LaneContainer, LaneRow, StatsBar } from './MeasurementPrimitives';
import { analyzeChord, deduplicateChords, getChordColor } from '../utils/chordTheory';

interface HarmonyLanesProps {
  phase1: Phase1Result;
}

const formatNum = (v: number | null | undefined, d = 2): string =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(d) : '—';

export function HarmonyLanes({ phase1 }: HarmonyLanesProps) {
  const chord = phase1.chordDetail;
  const keyStr = phase1.key ?? null;
  const hasChord = chord &&
    ((chord.progression && chord.progression.length > 0) ||
      (chord.dominantChords && chord.dominantChords.length > 0));
  const hasSegmentKeys = phase1.segmentKey && phase1.segmentKey.length > 0;
  const hasPitch = phase1.pitchDetail?.stems && Object.keys(phase1.pitchDetail.stems).length > 0;

  if (!hasChord && !hasSegmentKeys && !hasPitch) {
    return (
      <p className="text-[11px] font-mono text-text-secondary opacity-60">
        No harmonic data available for this track.
      </p>
    );
  }

  const palette = chord
    ? deduplicateChords([
        ...(chord.progression ?? []),
        ...(chord.dominantChords ?? []),
      ])
    : [];
  const progression = chord?.progression ?? chord?.chordSequence ?? [];
  const uniqueCount = palette.length;
  const strengthPct =
    typeof chord?.chordStrength === 'number'
      ? `${Math.round(chord.chordStrength * 100)}%`
      : '—';

  const statsItems = [
    ...(keyStr ? [{ label: 'Key', value: keyStr }] : []),
    { label: 'Strength', value: strengthPct, color: '#ff8800' },
    { label: 'Chords', value: String(uniqueCount || '—') },
  ];

  return (
    <LaneContainer>
      {/* Header stats */}
      <StatsBar items={statsItems} />

      {/* Chord Palette lane */}
      {palette.length > 0 && (
        <LaneRow label="Palette" height="h-[52px]">
          <div className="flex items-center gap-1.5 px-3 h-full overflow-x-auto">
            {palette.map((c, i) => {
              const color = getChordColor(c, keyStr);
              const analysis = analyzeChord(c, keyStr);
              return (
                <div
                  key={`${c}-${i}`}
                  className="border rounded-sm px-3 py-1 text-center min-w-[48px] flex-shrink-0"
                  style={{
                    backgroundColor: `${color}12`,
                    borderColor: `${color}40`,
                  }}
                >
                  <div className="text-sm font-mono font-bold" style={{ color }}>
                    {c}
                  </div>
                  {analysis && (
                    <div className="text-[7px] font-mono text-[#666] uppercase">
                      {analysis.numeral}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </LaneRow>
      )}

      {/* Progression lane */}
      {progression.length > 0 && (
        <LaneRow label="Progr." height="h-8">
          <div className="flex h-full">
            {progression.map((c, i) => {
              const color = getChordColor(c, keyStr);
              return (
                <div
                  key={`prog-${i}`}
                  className="flex-1 flex items-center justify-center border-r border-[#333] last:border-r-0"
                  style={{ backgroundColor: `${color}26` }}
                >
                  <span className="text-[11px] font-mono font-semibold" style={{ color }}>
                    {c}
                  </span>
                </div>
              );
            })}
          </div>
        </LaneRow>
      )}

      {/* Key Map lane (segment keys) */}
      {hasSegmentKeys && phase1.segmentKey && (
        <LaneRow label="Key Map" height="h-6">
          <div className="flex h-full">
            {phase1.segmentKey.map((seg, i) => {
              const segKey = seg.key ?? '—';
              const color = seg.key ? getChordColor(seg.key, keyStr) : '#555';
              const conf = seg.keyConfidence;
              return (
                <div
                  key={`seg-${i}`}
                  className="flex-1 flex items-center justify-center border-r border-[#2a2a2a] last:border-r-0"
                  style={{ backgroundColor: `${color}18` }}
                >
                  <span className="text-[8px] font-mono" style={{ color }}>
                    {segKey}
                    {typeof conf === 'number' && (
                      <span className="opacity-50"> · {formatNum(conf, 2)}</span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        </LaneRow>
      )}

      {/* Pitch lane */}
      {hasPitch && phase1.pitchDetail && (
        <LaneRow label="Pitch" height="h-7">
          <div className="flex items-center gap-4 px-3 h-full overflow-x-auto">
            {Object.entries(phase1.pitchDetail.stems).map(([name, stem]) => (
              <div key={name} className="flex items-center gap-1 flex-shrink-0">
                <span className="text-[8px] font-mono text-[#555] uppercase">{name}</span>
                <span className="text-[9px] font-mono text-[#aaa]">
                  {stem.medianPitchHz !== null ? `${stem.medianPitchHz} Hz` : '—'}
                </span>
                {stem.pitchRangeLowHz !== null && stem.pitchRangeHighHz !== null && (
                  <span className="text-[7px] font-mono text-[#444]">
                    {stem.pitchRangeLowHz}–{stem.pitchRangeHighHz}
                  </span>
                )}
                {typeof stem.voicedFramePercent === 'number' && (
                  <span className="text-[9px] font-mono text-[#00ff9d]">
                    {stem.voicedFramePercent}%
                  </span>
                )}
              </div>
            ))}
          </div>
        </LaneRow>
      )}
    </LaneContainer>
  );
}

import React, { useState } from 'react';
import { Phase1Result, Phase2Result } from '../types';
import {
  Activity,
  ChevronDown,
  ChevronRight,
  Clock,
  Disc,
  FileJson,
  FileText,
  Music,
  Settings2,
  Sliders,
  Sparkles,
} from 'lucide-react';
import { motion } from 'motion/react';
import { downloadFile, generateMarkdown } from '../utils/exportUtils';
import { SessionMusicianPanel } from './SessionMusicianPanel';
import {
  buildArrangementViewModel,
  buildMixChainGroups,
  buildPatchCards,
  buildSonicElementCards,
  calculateStereoBandStyle,
  toConfidenceBadges,
  truncateAtSentenceBoundary,
  truncateBySentenceCount,
} from './analysisResultsViewModel';

interface AnalysisResultsProps {
  phase1: Phase1Result | null;
  phase2: Phase2Result | null;
  sourceFileName?: string | null;
}

export function toggleOpenKeySet(previous: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(previous);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  return next;
}

export function characterToggleLabel(isExpanded: boolean): string {
  return isExpanded ? '▲ LESS' : '▼ MORE';
}

function Collapsible({ isOpen, children }: { isOpen: boolean; children: React.ReactNode }) {
  return (
    <div
      className={`overflow-hidden transition-[max-height,opacity] duration-300 ease-out ${
        isOpen ? 'max-h-[900px] opacity-100' : 'max-h-0 opacity-0'
      }`}
    >
      {children}
    </div>
  );
}

function confidenceClass(level: string): string {
  if (level === 'High') return 'text-green-500 bg-green-500/10 border-green-500/20';
  if (level === 'Moderate') return 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20';
  return 'text-red-500 bg-red-500/10 border-red-500/20';
}

function groupIcon(groupName: string): string {
  switch (groupName) {
    case 'DRUM PROCESSING':
      return '🥁';
    case 'BASS PROCESSING':
      return '🫧';
    case 'SYNTH / MELODIC':
      return '🎹';
    case 'MID PROCESSING':
      return '🎚';
    case 'HIGH-END DETAIL':
      return '✨';
    case 'MASTER BUS':
      return '🧱';
    default:
      return '🎛';
  }
}

const QUIET_SEGMENT_COLOR = '#8b5a00';
const LOUD_SEGMENT_COLOR = '#f5a623';
const TRACK_AVERAGE_LUFS = -7.5;

function clamp01(value: number): number {
  if (value <= 0) return 0;
  if (value >= 1) return 1;
  return value;
}

function hexToRgb(hexColor: string): [number, number, number] {
  const normalized = hexColor.replace('#', '');
  const value = Number.parseInt(normalized, 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function rgbToHex(r: number, g: number, b: number): string {
  const toHex = (value: number) => value.toString(16).padStart(2, '0');
  return `#${toHex(Math.round(r))}${toHex(Math.round(g))}${toHex(Math.round(b))}`;
}

function interpolateHexColor(startHex: string, endHex: string, t: number): string {
  const [r1, g1, b1] = hexToRgb(startHex);
  const [r2, g2, b2] = hexToRgb(endHex);
  const ratio = clamp01(t);
  return rgbToHex(
    r1 + (r2 - r1) * ratio,
    g1 + (g2 - g1) * ratio,
    b1 + (b2 - b1) * ratio,
  );
}

export function AnalysisResults({ phase1, phase2, sourceFileName = null }: AnalysisResultsProps) {
  const [openArrangement, setOpenArrangement] = useState<Record<string, boolean>>({});
  const [openSonic, setOpenSonic] = useState<Set<string>>(new Set());
  const [openMix, setOpenMix] = useState<Record<string, boolean>>({});
  const [openPatch, setOpenPatch] = useState<Record<string, boolean>>({});
  const [isCharacterExpanded, setIsCharacterExpanded] = useState(false);

  if (!phase1) return null;

  const handleExportJSON = () => {
    const data = {
      phase1,
      phase2,
      exportedAt: new Date().toISOString(),
    };
    downloadFile(JSON.stringify(data, null, 2), 'track-analysis.json', 'application/json');
  };

  const handleExportMD = () => {
    const markdown = generateMarkdown(phase1, phase2);
    downloadFile(markdown, 'track-analysis.md', 'text/markdown');
  };

  const toggleArrangement = (id: string) => {
    setOpenArrangement((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleSonic = (id: string) => {
    setOpenSonic((prev) => toggleOpenKeySet(prev, id));
  };

  const toggleMix = (id: string) => {
    setOpenMix((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const togglePatch = (id: string) => {
    setOpenPatch((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const finalBpm = Math.round(phase1.bpm);
  const finalKey = phase1.key ?? 'Unknown';

  const confidenceBadges = toConfidenceBadges(phase2?.confidenceNotes);
  const arrangement = buildArrangementViewModel(phase1, phase2?.arrangementOverview);
  const sonicCards = buildSonicElementCards(phase1, phase2?.sonicElements);
  const mixGroups = buildMixChainGroups(phase1, phase2?.mixAndMasterChain, phase2?.sonicElements);
  const patchCards = buildPatchCards(phase1, phase2);

  const trackCharacterText = phase2?.trackCharacter?.trim() || 'SCANNING...';
  const segmentLufsValues = arrangement?.segments
    .map((segment) => segment.lufs)
    .filter((lufs): lufs is number => typeof lufs === 'number' && Number.isFinite(lufs));
  const minSegmentLufs = segmentLufsValues && segmentLufsValues.length > 0 ? Math.min(...segmentLufsValues) : null;
  const maxSegmentLufs = segmentLufsValues && segmentLufsValues.length > 0 ? Math.max(...segmentLufsValues) : null;

  const getSegmentColor = (lufs: number | null): string => {
    if (lufs === null || minSegmentLufs === null || maxSegmentLufs === null) {
      return interpolateHexColor(QUIET_SEGMENT_COLOR, LOUD_SEGMENT_COLOR, 0.5);
    }
    if (minSegmentLufs === maxSegmentLufs) {
      return interpolateHexColor(QUIET_SEGMENT_COLOR, LOUD_SEGMENT_COLOR, 0.5);
    }
    const normalized = (lufs - minSegmentLufs) / (maxSegmentLufs - minSegmentLufs);
    return interpolateHexColor(QUIET_SEGMENT_COLOR, LOUD_SEGMENT_COLOR, normalized);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="space-y-12"
    >
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 pb-6 border-b border-border relative">
        <div>
          <h1 className="text-2xl font-display font-bold tracking-tight text-text-primary uppercase flex items-center">
            <Activity className="w-6 h-6 mr-3 text-accent" />
            Analysis Results
          </h1>
          <p className="text-text-secondary font-mono text-xs mt-1 tracking-wider uppercase opacity-70">
            SESSION ID: {new Date().getTime().toString(36).toUpperCase()} // PHASE COMPLETE
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleExportJSON}
            className="flex items-center gap-2 px-4 py-2 bg-bg-panel border border-border rounded text-xs font-mono uppercase tracking-wider hover:bg-bg-card-hover hover:border-accent/50 transition-all group"
          >
            <FileJson className="w-3 h-3 text-text-secondary group-hover:text-accent" />
            <span>JSON_DATA</span>
          </button>
          <button
            onClick={handleExportMD}
            className="flex items-center gap-2 px-4 py-2 bg-accent/10 border border-accent/50 text-accent rounded text-xs font-mono uppercase tracking-wider hover:bg-accent/20 transition-all shadow-[0_0_10px_rgba(255,85,0,0.1)]"
          >
            <FileText className="w-3 h-3" />
            <span>REPORT_MD</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 auto-rows-fr">
        <div className="bg-bg-panel border border-border rounded-sm p-1 relative group overflow-hidden">
          <div className="absolute inset-0 bg-accent/5 opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div className="bg-bg-card h-full min-h-[170px] p-4 rounded-sm flex flex-col items-center justify-center text-center border border-border/50 relative z-10 overflow-hidden">
            <div className="w-full flex justify-between items-start mb-2 opacity-50">
              <Activity className="w-4 h-4 text-accent" />
              <span className="text-[10px] font-mono uppercase">TEMPO</span>
            </div>
            <div className="w-full flex items-baseline justify-center space-x-1 overflow-hidden">
              <p className="text-3xl font-display font-bold text-text-primary truncate">{finalBpm}</p>
              <span className="text-xs font-mono text-text-secondary flex-shrink-0">BPM</span>
            </div>

            <div className="w-full bg-bg-app h-1 mt-3 overflow-hidden border border-border/30">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${phase1.bpmConfidence * 100}%` }}
                className="h-full bg-accent shadow-[0_0_5px_#ff9500]"
              />
            </div>
            <p className="text-[10px] font-mono text-text-secondary mt-1 opacity-70">
              CONF: {Math.min(Math.round(phase1.bpmConfidence * 100), 100) + '%'}
            </p>
          </div>
        </div>

        <div className="bg-bg-panel border border-border rounded-sm p-1 relative group overflow-hidden">
          <div className="absolute inset-0 bg-accent/5 opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div className="bg-bg-card h-full min-h-[170px] p-4 rounded flex flex-col items-center justify-center text-center border border-border/50 relative z-10 overflow-hidden">
            <div className="w-full flex justify-between items-start mb-2 opacity-50">
              <Music className="w-4 h-4 text-accent" />
              <span className="text-[10px] font-mono uppercase">KEY SIG</span>
            </div>
            <div className="w-full overflow-hidden">
              <p className="text-3xl font-display font-bold text-text-primary truncate">{finalKey}</p>
            </div>

            <div className="w-full bg-bg-app h-1 mt-3 overflow-hidden border border-border/30">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${phase1.keyConfidence * 100}%` }}
                className="h-full bg-accent shadow-[0_0_5px_#ff9500]"
              />
            </div>
            <p className="text-[10px] font-mono text-text-secondary mt-1 opacity-70">
              CONF: {(phase1.keyConfidence * 100).toFixed(0)}%
            </p>
          </div>
        </div>

        <div className="bg-bg-panel border border-border rounded-sm p-1 relative group overflow-hidden">
          <div className="absolute inset-0 bg-accent/5 opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div className="bg-bg-card h-full min-h-[170px] p-4 rounded flex flex-col items-center justify-center text-center border border-border/50 relative z-10 overflow-hidden">
            <div className="w-full flex justify-between items-start mb-2 opacity-50">
              <Clock className="w-4 h-4 text-accent" />
              <span className="text-[10px] font-mono uppercase">METER</span>
            </div>
            <p className="text-3xl font-display font-bold text-text-primary mt-1 w-full truncate">{phase1.timeSignature}</p>
            <p className="text-[10px] font-mono text-text-secondary mt-auto opacity-70">DETECTED</p>
          </div>
        </div>

        <div className="bg-bg-panel border border-border rounded-sm p-1 relative group col-span-1 md:col-span-1 self-start">
          <div className="absolute inset-0 bg-accent/5 opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div
            className={`bg-bg-card min-h-[170px] p-4 rounded-sm flex flex-col border border-border/50 relative z-10 ${
              isCharacterExpanded ? 'h-auto items-start text-left' : 'h-full items-center justify-center text-center'
            }`}
          >
            <div className="w-full flex justify-between items-start mb-2 opacity-50">
              <Disc className="w-4 h-4 text-accent" />
              <span className="text-[10px] font-mono uppercase">CHARACTER</span>
            </div>
            <p
              className={`text-xs font-mono text-text-primary mt-1 w-full px-1 text-left ${
                isCharacterExpanded ? '' : 'line-clamp-2'
              }`}
            >
              {trackCharacterText}
            </p>
            <button
              onClick={() => setIsCharacterExpanded((prev) => !prev)}
              className="text-[9px] font-mono text-text-secondary mt-2 pt-1 hover:text-text-primary transition-colors"
            >
              {characterToggleLabel(isCharacterExpanded)}
            </button>
          </div>
        </div>
      </div>

      {confidenceBadges.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 px-1">
          {confidenceBadges.map((badge, idx) => (
            <span
              key={`${badge.label}-${idx}`}
              className={`px-2 py-1 rounded-sm border text-[10px] font-mono uppercase tracking-wide ${confidenceClass(badge.level)}`}
            >
              {badge.label}: {badge.level}
            </span>
          ))}
        </div>
      )}

      {Array.isArray(phase2?.detectedCharacteristics) && phase2.detectedCharacteristics.length > 0 && (
        <div className="space-y-6">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Detected Characteristics
            </h2>
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">PHASE 2</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {phase2.detectedCharacteristics.map((item, idx) => (
              <div
                key={idx}
                className="bg-bg-card border rounded-sm p-4 flex flex-col transition-all hover:border-accent/40 group relative overflow-hidden border-accent/30"
              >
                <div className="absolute top-0 left-0 w-1 h-full bg-accent"></div>
                <div className="flex items-center justify-between mb-3 pl-2">
                  <h3 className="font-bold tracking-wide text-sm truncate pr-2">{item.name}</h3>
                  <span
                    className={`flex items-center text-[10px] font-mono font-bold px-2 py-1 rounded-sm border ${
                      item.confidence === 'HIGH'
                        ? 'text-green-500 bg-green-500/10 border-green-500/20'
                        : item.confidence === 'MED'
                          ? 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20'
                          : 'text-red-500 bg-red-500/10 border-red-500/20'
                    }`}
                  >
                    {item.confidence}
                  </span>
                </div>
                <p className="text-xs text-text-secondary leading-relaxed font-mono opacity-80 border-t border-border/50 pt-2 mt-2 pl-2">
                  {truncateAtSentenceBoundary(item.explanation, 600)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {arrangement && (
        <div className="space-y-6">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Arrangement Overview
            </h2>
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">TIMELINE</span>
          </div>

          {arrangement.summary && (
            <p className="text-xs text-text-secondary font-mono leading-relaxed opacity-80">
              {arrangement.summary}
            </p>
          )}

          <div className="bg-bg-card border border-border rounded-sm p-4 space-y-4">
            <div className="relative pt-6">
              <div className="relative h-14 border border-border rounded-sm overflow-hidden bg-bg-app">
                {arrangement.segments.map((segment) => (
                  <div
                    key={segment.id}
                    className="absolute top-0 bottom-0 px-2 py-1 border-r border-bg-app/30 text-[10px] font-mono text-white flex items-center justify-center text-center overflow-hidden"
                    style={{
                      left: `${segment.leftPercent}%`,
                      width: `${segment.widthPercent}%`,
                      backgroundColor: getSegmentColor(segment.lufs),
                    }}
                    title={`${segment.name} • ${segment.lufsLabel}`}
                  >
                    <span className="truncate">{segment.name} • {segment.lufsLabel}</span>
                  </div>
                ))}

                {arrangement.noveltyMarkers.map((marker, idx) => (
                  <div
                    key={`marker-${idx}`}
                    className="absolute top-0 bottom-0 pointer-events-none"
                    style={{ left: `${marker.leftPercent}%` }}
                  >
                    <div className="absolute -top-5 -translate-x-1/2 bg-bg-panel border border-border rounded px-1 py-[1px] text-[9px] font-mono text-text-secondary whitespace-nowrap">
                      {marker.label}
                    </div>
                    <div className="h-full w-px bg-accent/90" />
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between mt-2 text-[10px] font-mono text-text-secondary">
                <span>0s</span>
                <span>{arrangement.totalDuration.toFixed(1)}s</span>
              </div>
            </div>

            {arrangement.noveltyNotes && (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <div className="h-px bg-border/60 flex-1" />
                  <span className="text-[9px] font-mono uppercase tracking-widest text-text-secondary/80">
                    NOVELTY EVENTS
                  </span>
                  <div className="h-px bg-border/60 flex-1" />
                </div>
                <p className="text-xs text-text-secondary font-mono leading-relaxed">
                  {arrangement.noveltyNotes}
                </p>
              </div>
            )}

            <div className="space-y-2">
              {arrangement.segments.map((segment) => {
                const isOpen = !!openArrangement[segment.id];
                const lufsDelta = segment.lufs !== null ? segment.lufs - TRACK_AVERAGE_LUFS : null;
                const lufsDeltaLabel =
                  lufsDelta === null
                    ? null
                    : `${lufsDelta >= 0 ? '▲' : '▼'} ${lufsDelta >= 0 ? '+' : ''}${lufsDelta.toFixed(1)} dB`;
                const lufsDeltaClass =
                  lufsDelta === null
                    ? ''
                    : lufsDelta > 0
                      ? 'text-green-400 border-green-500/30 bg-green-500/10'
                      : lufsDelta < 0
                        ? 'text-red-400 border-red-500/30 bg-red-500/10'
                        : 'text-text-secondary border-border bg-bg-panel/40';
                return (
                  <div key={`${segment.id}-detail`} className="border border-border rounded-sm overflow-hidden bg-bg-panel/40">
                    <button
                      onClick={() => toggleArrangement(segment.id)}
                      className="w-full flex items-center justify-between gap-3 px-3 py-2 text-left hover:bg-bg-card transition-colors"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-xs">{isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}</span>
                        <span className="text-xs font-mono text-text-primary truncate">
                          {segment.name} • {segment.lufsLabel}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {lufsDeltaLabel && (
                          <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border whitespace-nowrap ${lufsDeltaClass}`}>
                            {lufsDeltaLabel}
                          </span>
                        )}
                        <span className="text-[10px] font-mono text-text-secondary whitespace-nowrap">
                          {segment.startTime.toFixed(1)}s - {segment.endTime.toFixed(1)}s
                        </span>
                      </div>
                    </button>

                    <Collapsible isOpen={isOpen}>
                      <div className="px-3 pb-3 pt-1 space-y-2 border-t border-border/60">
                        <p className="text-xs text-text-secondary font-mono leading-relaxed">
                          {truncateBySentenceCount(segment.description, 4)}
                        </p>
                        {segment.spectralNote && (
                          <div className="border border-border/70 rounded-sm bg-bg-panel/50 px-2 py-2 space-y-1">
                            <span className="inline-flex text-[9px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded border border-accent/40 text-accent">
                              SPECTRAL NOTE
                            </span>
                            <p className="text-[11px] text-text-secondary/90 font-mono leading-relaxed">
                              {segment.spectralNote}
                            </p>
                          </div>
                        )}
                      </div>
                    </Collapsible>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <SessionMusicianPanel phase1={phase1} sourceFileName={sourceFileName} />

      {sonicCards.length > 0 && (
        <div className="space-y-6">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Sonic Elements & Reconstruction
            </h2>
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">COLLAPSIBLE</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
            {sonicCards.map((card) => {
              const isOpen = openSonic.has(card.id);
              return (
                <div key={card.id} className="bg-bg-card border border-border rounded-sm overflow-hidden self-start flex flex-col">
                  <button
                    onClick={() => toggleSonic(card.id)}
                    className="w-full px-4 py-3 border-b border-border bg-bg-panel/60 text-left hover:bg-bg-panel transition-colors"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm">{card.icon}</span>
                          <h3 className="text-sm font-bold uppercase tracking-wide truncate">{card.title}</h3>
                          {card.transcriptionDerived && (
                            <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-accent/40 text-accent whitespace-nowrap">
                              Transcription-derived
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-text-secondary font-mono mt-1 truncate">{card.summary}</p>
                      </div>
                      <span className="text-text-secondary">
                        {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                      </span>
                    </div>
                  </button>

                  <Collapsible isOpen={isOpen}>
                    <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <p className="text-xs text-text-secondary font-mono leading-relaxed">
                          {card.description}
                        </p>
                      </div>

                      <div className="space-y-2">
                        {card.measurements.map((measurement, idx) => (
                          <div
                            key={`${card.id}-measurement-${idx}`}
                            className="flex items-center justify-between text-[11px] font-mono border border-border rounded-sm px-2 py-1 bg-bg-panel/40"
                          >
                            <span className="text-text-secondary truncate pr-2">
                              {measurement.icon} {measurement.label}
                            </span>
                            <span className="text-text-primary font-bold whitespace-nowrap">{measurement.value}</span>
                          </div>
                        ))}

                        {card.isWidthAndStereo && (
                          <div className="mt-3 border border-border rounded-sm p-2 bg-bg-panel/40">
                            <div className="flex items-center justify-between text-[10px] font-mono text-text-secondary mb-1">
                              <span>L</span>
                              <span>R</span>
                            </div>
                            <div className="relative h-3 rounded bg-bg-app border border-border overflow-hidden">
                              <div className="absolute inset-y-0 left-1/2 w-px bg-text-secondary/70" />
                              <div
                                className="absolute inset-y-0 bg-accent/50 border border-accent/60 rounded"
                                style={calculateStereoBandStyle(phase1.stereoWidth)}
                              />
                            </div>
                            <p className="text-[10px] font-mono text-text-secondary mt-1">
                              Width band: {phase1.stereoWidth.toFixed(2)} around center
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </Collapsible>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {mixGroups.length > 0 && (
        <div className="space-y-6">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Mix & Master Chain
            </h2>
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">SIGNAL FLOW</span>
          </div>

          <div className="space-y-4">
            {mixGroups
              .filter((group) => group.cards.length > 0)
              .map((group) => (
              <section key={group.name} className="space-y-3">
                <h3 className="text-xs font-mono uppercase tracking-widest text-text-secondary border-b border-border/70 pb-1">
                  {groupIcon(group.name)} {group.name}
                </h3>
                {group.annotation && (
                  <p className="text-[10px] font-mono text-text-secondary/80 uppercase tracking-wide">
                    {group.annotation}
                  </p>
                )}

                <div className="flex flex-wrap gap-4">
                  {group.cards.map((card) => {
                    const isOpen = !!openMix[card.id];
                    return (
                      <div
                        key={card.id}
                        className="bg-bg-card border border-border rounded-sm overflow-hidden self-start flex flex-col flex-1 min-w-[280px] basis-full md:basis-[calc(50%-8px)] max-w-full md:max-w-[calc(50%-8px)]"
                      >
                        <button
                          onClick={() => toggleMix(card.id)}
                          className="w-full text-left px-4 py-3 border-b border-border bg-bg-panel/60 hover:bg-bg-panel transition-colors"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="w-6 h-6 rounded-sm bg-bg-app border border-border text-accent font-mono text-[10px] flex items-center justify-center">
                                  {card.order}
                                </span>
                                <h4 className="text-sm font-bold truncate">{card.device}</h4>
                                <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary whitespace-nowrap">
                                  {card.category}
                                </span>
                              </div>
                              <p className="text-xs font-mono text-text-secondary mt-1 truncate">{card.role}</p>
                            </div>
                            <span className="text-text-secondary flex-shrink-0">
                              {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                            </span>
                          </div>
                        </button>

                        <Collapsible isOpen={isOpen}>
                          <div className="p-4 space-y-3">
                            <p className="text-xs font-mono text-text-secondary leading-relaxed">
                              {truncateAtSentenceBoundary(card.role, 320)}
                            </p>

                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                              {card.parameters.map((parameter, idx) => (
                                <div
                                  key={`${card.id}-parameter-${idx}`}
                                  className="border border-border rounded-sm px-2 py-1 bg-bg-panel/40"
                                >
                                  <p className="text-[10px] font-mono uppercase text-text-secondary">{parameter.label}</p>
                                  <p className="text-xs font-mono text-text-primary font-bold">{parameter.value}</p>
                                </div>
                              ))}
                            </div>

                            <div className="border border-accent/20 bg-accent/5 rounded-sm px-2 py-2">
                              <p className="text-[10px] font-mono text-accent uppercase tracking-wide">PRO TIP</p>
                              <p className="text-xs font-mono text-text-secondary mt-1 leading-relaxed">
                                {truncateAtSentenceBoundary(card.proTip, 320)}
                              </p>
                            </div>
                          </div>
                        </Collapsible>
                      </div>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        </div>
      )}

      {patchCards.length > 0 && (
        <div className="space-y-6">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Patch Framework
            </h2>
            <Sliders className="w-4 h-4 text-accent opacity-70" />
          </div>

          <div className="flex flex-wrap gap-4">
            {patchCards.map((patch) => {
              const isOpen = !!openPatch[patch.id];
              return (
                <div
                  key={patch.id}
                  className="bg-bg-card border border-border rounded-sm overflow-hidden self-start flex flex-col flex-1 min-w-[280px] basis-full md:basis-[calc(50%-8px)] max-w-full md:max-w-[calc(50%-8px)]"
                >
                  <button
                    onClick={() => togglePatch(patch.id)}
                    className="w-full text-left px-4 py-3 border-b border-border bg-bg-panel/60 hover:bg-bg-panel transition-colors"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Settings2 className="w-4 h-4 text-accent" />
                          <h4 className="text-sm font-bold truncate">{patch.device}</h4>
                          {patch.transcriptionDerived && (
                            <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-accent/40 text-accent whitespace-nowrap">
                              Transcription-derived
                            </span>
                          )}
                          <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary whitespace-nowrap">
                            {patch.category}
                          </span>
                        </div>
                        <p className="text-xs font-mono text-text-secondary mt-1 truncate">{patch.patchRole}</p>
                      </div>
                      <span className="text-text-secondary flex-shrink-0">
                        {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                      </span>
                    </div>
                  </button>

                  <Collapsible isOpen={isOpen}>
                    <div className="p-4 space-y-3">
                      <p className="text-xs font-mono text-text-secondary leading-relaxed">
                        {truncateAtSentenceBoundary(patch.whyThisWorks, 600)}
                      </p>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {patch.parameters.map((parameter, idx) => (
                          <div
                            key={`${patch.id}-parameter-${idx}`}
                            className="border border-border rounded-sm px-2 py-1 bg-bg-panel/40"
                          >
                            <p className="text-[10px] font-mono uppercase text-text-secondary">{parameter.label}</p>
                            <p className="text-xs font-mono text-text-primary font-bold">{parameter.value}</p>
                          </div>
                        ))}
                      </div>

                      <div className="border border-accent/20 bg-accent/5 rounded-sm px-2 py-2">
                        <p className="text-[10px] font-mono text-accent uppercase tracking-wide">PRO TIP</p>
                        <p className="text-xs font-mono text-text-secondary mt-1 leading-relaxed">
                          {truncateAtSentenceBoundary(patch.proTip, 320)}
                        </p>
                      </div>
                    </div>
                  </Collapsible>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {phase2?.secretSauce && (
        <div className="relative overflow-hidden bg-bg-card border border-accent/30 rounded-sm p-0 group">
          <div className="bg-accent/10 p-4 border-b border-accent/20 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="bg-accent text-bg-app p-1.5 rounded-sm">
                <Sparkles className="w-4 h-4" />
              </div>
              <h2 className="text-sm font-bold tracking-wide uppercase text-accent">Secret Sauce Protocol</h2>
            </div>
            <span className="text-[10px] font-mono bg-accent/20 text-accent px-2 py-1 rounded-sm border border-accent/30">
              CONFIDENTIAL
            </span>
          </div>

          <div className="p-6 relative">
            <div className="absolute top-0 right-0 p-8 opacity-5 pointer-events-none">
              <Sparkles className="w-32 h-32 text-accent" />
            </div>

            <div className="relative z-10 space-y-6">
              <div className="space-y-2">
                <h3 className="text-lg font-bold text-text-primary">{phase2.secretSauce.title}</h3>
                <p className="text-sm font-mono text-text-secondary leading-relaxed max-w-3xl border-l-2 border-accent/30 pl-4">
                  {truncateAtSentenceBoundary(phase2.secretSauce.explanation, 600)}
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-border/50">
                {(Array.isArray(phase2.secretSauce.implementationSteps)
                  ? phase2.secretSauce.implementationSteps
                  : []
                ).map((step, idx) => (
                  <div key={idx} className="flex space-x-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-sm bg-bg-panel border border-border flex items-center justify-center text-accent font-mono text-xs">
                      {idx + 1}
                    </span>
                    <p className="text-xs text-text-secondary leading-relaxed font-mono pt-1">
                      {truncateAtSentenceBoundary(step, 260)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </motion.div>
  );
}

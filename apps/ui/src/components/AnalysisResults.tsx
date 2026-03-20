import React, { useMemo, useState } from 'react';
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
import { INTERPRETATION_LABEL } from '../services/phaseLabels';
import { MeasurementDashboard } from './MeasurementDashboard';
import { SessionMusicianPanel } from './SessionMusicianPanel';
import { PhaseSourceBadge } from './PhaseSourceBadge';
import { StickyNav, type StickyNavSection } from './StickyNav';
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

export interface AnalysisResultsProps {
  phase1: Phase1Result | null;
  phase2: Phase2Result | null;
  phase2StatusMessage?: string | null;
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

function SourcesToggle({ sources, showSources, onToggle }: { sources?: string[]; showSources: boolean; onToggle: () => void }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div className="mt-3">
      <button
        onClick={onToggle}
        className="text-[10px] font-mono uppercase tracking-wide text-accent hover:text-accent/80 transition-colors flex items-center gap-1"
      >
        {showSources ? '▼' : '▶'} Sources
      </button>
      <Collapsible isOpen={showSources}>
        <div className="mt-2 text-xs text-text-secondary/70 font-mono">
          <span className="text-[10px] uppercase tracking-wide text-text-secondary/50">Based on:</span>
          <ul className="mt-1 space-y-0.5">
            {sources.map((source, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <span className="text-accent/60">•</span>
                <span>{source}</span>
              </li>
            ))}
          </ul>
        </div>
      </Collapsible>
    </div>
  );
}

function confidenceClass(level: string): string {
  if (level === 'High') return 'text-success bg-success/10 border-success/20';
  if (level === 'Moderate') return 'text-warning bg-warning/10 border-warning/20';
  return 'text-error bg-error/10 border-error/20';
}

function shortenCharacteristicName(name: string): string {
  return name.trim().split(/\s+/).slice(0, 2).join(' ');
}

function characteristicPillClass(confidence: string): string {
  const normalized = String(confidence).trim().toUpperCase();
  if (normalized === 'HIGH') {
    return 'bg-success/20 text-success border-success/30';
  }
  if (normalized === 'MED' || normalized === 'MODERATE') {
    return 'bg-warning/20 text-warning border-warning/30';
  }
  return 'bg-error/20 text-error border-error/30';
}

function groupIcon(groupName: string): string {
  if (groupName.includes('DRUM PROCESSING')) return '🥁';
  if (groupName.includes('BASS PROCESSING')) return '🫧';
  if (groupName.includes('SYNTH / MELODIC')) return '🎹';
  if (groupName.includes('MID PROCESSING')) return '🎚';
  if (groupName.includes('HIGH-END DETAIL')) return '✨';
  if (groupName.includes('MASTER BUS')) return '🧱';
  return '🎛';
}

const SEGMENT_ORDER_PALETTE = ['#e05c00', '#c44b8a', '#2d9cdb', '#27ae60'] as const;
const TRACK_AVERAGE_LUFS = -7.5;

function getSegmentPaletteColor(segmentIndex: number): string {
  return SEGMENT_ORDER_PALETTE[segmentIndex % SEGMENT_ORDER_PALETTE.length];
}

function withAlpha(hexColor: string, alphaHex: string): string {
  return `${hexColor}${alphaHex}`;
}

const LOW_CONFIDENCE_TITLE = "Low confidence — treat this as approximate.";

function lowConfidenceIndicator(show: boolean) {
  if (!show) return null;
  return (
    <span
      className="text-[10px] font-mono text-warning"
      title={LOW_CONFIDENCE_TITLE}
      aria-label="Low confidence"
    >
      ⚠
    </span>
  );
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function getChordStrength(phase1: Phase1Result): number | null {
  const chordDetail = phase1.chordDetail;
  if (!chordDetail || typeof chordDetail !== 'object' || Array.isArray(chordDetail)) {
    return null;
  }

  return toFiniteNumber((chordDetail as Record<string, unknown>).chordStrength);
}

export function AnalysisResults({
  phase1,
  phase2,
  phase2StatusMessage = null,
  sourceFileName = null,
}: AnalysisResultsProps) {
  const [openArrangement, setOpenArrangement] = useState<Record<string, boolean>>({});
  const [openSonic, setOpenSonic] = useState<Set<string>>(new Set());
  const [openMix, setOpenMix] = useState<Record<string, boolean>>({});
  const [openPatch, setOpenPatch] = useState<Record<string, boolean>>({});
  const [showSources, setShowSources] = useState<Record<string, boolean>>({});

  const sessionId = useMemo(() => new Date().getTime().toString(36).toUpperCase(), []);

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
    const markdown = generateMarkdown(phase1, phase2, phase2StatusMessage);
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

  const toggleSources = (id: string) => {
    setShowSources((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const finalBpm = Math.round(phase1.bpm);
  const finalKey = phase1.key ?? 'Unknown';

  const confidenceBadges = toConfidenceBadges(phase2?.confidenceNotes);
  const arrangement = buildArrangementViewModel(phase1, phase2?.arrangementOverview);
  const sonicCards = buildSonicElementCards(phase1, phase2?.sonicElements);
  const mixGroups = buildMixChainGroups(phase1, phase2?.mixAndMasterChain, phase2?.sonicElements);
  const patchCards = buildPatchCards(phase1, phase2);
  const characteristicPills = Array.isArray(phase2?.detectedCharacteristics)
    ? phase2.detectedCharacteristics.slice(0, 4)
    : [];
  const keyIsApproximate = phase1.keyConfidence <= 0.6;
  const chordStrength = getChordStrength(phase1);
  const chordsAreApproximate = chordStrength !== null && chordStrength <= 0.7;
  const hasRenderablePhase2Content =
    confidenceBadges.length > 0 ||
    characteristicPills.length > 0 ||
    arrangement !== null ||
    sonicCards.length > 0 ||
    mixGroups.length > 0 ||
    patchCards.length > 0;
  const navSections: StickyNavSection[] = [
    { id: 'section-meas-core', label: 'Core' },
    { id: 'section-meas-loudness', label: 'Loudness' },
    { id: 'section-meas-spectral', label: 'Spectral' },
    { id: 'section-meas-stereo', label: 'Stereo' },
    { id: 'section-meas-rhythm', label: 'Rhythm' },
    { id: 'section-meas-harmony', label: 'Harmony' },
    { id: 'section-meas-structure', label: 'Structure' },
    { id: 'section-meas-synthesis', label: 'Synthesis' },
    arrangement ? { id: 'section-arrangement', label: 'Arrangement' } : null,
    { id: 'section-session', label: 'Session' },
    sonicCards.length > 0 ? { id: 'section-sonic-elements', label: 'Sonic' } : null,
    mixGroups.length > 0 ? { id: 'section-mix-chain', label: 'Mix Chain' } : null,
    patchCards.length > 0 ? { id: 'section-patches', label: 'Patches' } : null,
  ].filter((section): section is StickyNavSection => section !== null);

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
            SESSION ID: {sessionId} // PHASE COMPLETE
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

      <StickyNav sections={navSections} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 auto-rows-fr">
        <div className="bg-bg-panel border border-border rounded-sm p-1 relative group overflow-hidden">
          <div className="absolute inset-0 bg-accent/5 opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div className="bg-bg-card h-full min-h-[170px] p-4 rounded-sm flex flex-col items-center justify-center text-center border border-border/50 relative z-10 overflow-hidden">
            <div className="w-full flex justify-between items-start mb-2 opacity-50">
              <Activity className="w-4 h-4 text-accent" />
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono uppercase">TEMPO</span>
                <PhaseSourceBadge source="measured" />
              </div>
            </div>
            <div className="w-full flex items-baseline justify-center space-x-1 overflow-hidden">
              <p className="text-3xl font-display font-bold text-text-primary truncate">{finalBpm}</p>
              <span className="text-xs font-mono text-text-secondary flex-shrink-0">BPM</span>
            </div>

            <div className="w-full bg-bg-app h-1 mt-3 overflow-hidden border border-border/30">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${phase1.bpmConfidence * 100}%` }}
                className="h-full bg-accent shadow-[0_0_5px_var(--color-accent)]"
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
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono uppercase">KEY SIG</span>
                <PhaseSourceBadge source="measured" />
                {lowConfidenceIndicator(keyIsApproximate)}
              </div>
            </div>
            <div className="w-full overflow-hidden">
              <p className="text-3xl font-display font-bold text-text-primary truncate">{finalKey}</p>
            </div>

            <div className="w-full bg-bg-app h-1 mt-3 overflow-hidden border border-border/30">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${phase1.keyConfidence * 100}%` }}
                className="h-full bg-accent shadow-[0_0_5px_var(--color-accent)]"
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
          <div className="bg-bg-card h-full min-h-[170px] p-4 rounded-sm flex flex-col border border-border/50 relative z-10">
            <div className="w-full flex justify-between items-start mb-2 opacity-50">
              <Disc className="w-4 h-4 text-accent" />
              <span className="text-[10px] font-mono uppercase">CHARACTER</span>
            </div>
            {characteristicPills.length > 0 ? (
              <div className="w-full flex flex-wrap gap-1 mt-1">
                {characteristicPills.map((item, idx) => (
                  <span
                    key={`${item.name}-${idx}`}
                    className={`inline-flex items-center px-2 py-1 rounded-sm border text-[10px] font-mono uppercase tracking-wide ${characteristicPillClass(item.confidence)}`}
                  >
                    {shortenCharacteristicName(item.name)}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs font-mono text-text-secondary mt-1 opacity-70">SCANNING...</p>
            )}
          </div>
        </div>
      </div>

      <MeasurementDashboard phase1={phase1} />

      <div className="space-y-2">
        <div className="flex items-center justify-between border-b border-border pb-2">
          <h2 className="text-sm font-mono uppercase tracking-wider flex items-center gap-2 text-text-secondary">
            <span className="w-2 h-2 bg-accent rounded-full"></span>
            {INTERPRETATION_LABEL}
            <PhaseSourceBadge source="advisory" />
          </h2>
        </div>
        <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
          Interpretive guidance generated from DSP measurements. Not a ground-truth measurement.
        </p>
        {phase2StatusMessage && !phase2 && (
          <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
            {phase2StatusMessage}
          </p>
        )}
        {!hasRenderablePhase2Content && !phase2StatusMessage && (
          <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
            Draft — AI interpretation is incomplete or unavailable.
          </p>
        )}
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
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">AI INTERP</span>
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
                        ? 'text-success bg-success/10 border-success/20'
                        : item.confidence === 'MED'
                          ? 'text-warning bg-warning/10 border-warning/20'
                          : 'text-error bg-error/10 border-error/20'
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
        <section id="section-arrangement" className="space-y-6 scroll-mt-24">
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
                {arrangement.segments.map((segment, segmentIndex) => (
                  <div
                    key={segment.id}
                    className="absolute top-0 bottom-0 px-2 py-1 border-r border-bg-app/30 text-[10px] font-mono text-white flex items-center justify-center text-center overflow-hidden"
                    style={{
                      left: `${segment.leftPercent}%`,
                      width: `${segment.widthPercent}%`,
                      backgroundColor: getSegmentPaletteColor(segmentIndex),
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
              {arrangement.segments.map((segment, segmentIndex) => {
                const isOpen = !!openArrangement[segment.id];
                const segmentColor = getSegmentPaletteColor(segmentIndex);
                const lufsDelta = segment.lufs !== null ? segment.lufs - TRACK_AVERAGE_LUFS : null;
                const lufsDeltaLabel =
                  lufsDelta === null
                    ? null
                    : `${lufsDelta >= 0 ? '▲' : '▼'} ${lufsDelta >= 0 ? '+' : ''}${lufsDelta.toFixed(1)} dB`;
                const lufsDeltaClass =
                  lufsDelta === null
                    ? ''
                    : lufsDelta > 0
                      ? 'text-success border-success/30 bg-success/10'
                      : lufsDelta < 0
                        ? 'text-error border-error/30 bg-error/10'
                        : 'text-text-secondary border-border bg-bg-panel/40';
                return (
                  <div
                    key={`${segment.id}-detail`}
                    className="border border-border border-l-2 rounded-sm overflow-hidden bg-bg-panel/40"
                    style={{ borderLeftColor: segmentColor }}
                  >
                    <button
                      onClick={() => toggleArrangement(segment.id)}
                      className="w-full flex items-center justify-between gap-3 px-3 py-2 text-left hover:bg-bg-card transition-colors"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-xs">{isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}</span>
                        <span className="text-xs font-mono text-text-primary truncate">{segment.name}</span>
                        <span
                          className="text-[10px] font-mono px-1.5 py-0.5 rounded border whitespace-nowrap"
                          style={{
                            backgroundColor: withAlpha(segmentColor, '22'),
                            borderColor: withAlpha(segmentColor, '66'),
                            color: segmentColor,
                          }}
                        >
                          {segment.lufsLabel}
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
        </section>
      )}

      <div id="section-session" className="scroll-mt-24">
        <SessionMusicianPanel phase1={phase1} sourceFileName={sourceFileName} />
      </div>

      {sonicCards.length > 0 && (
        <section id="section-sonic-elements" className="space-y-6 scroll-mt-24">
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
                <div
                  key={card.id}
                  className="bg-bg-card border border-border rounded-sm overflow-hidden self-start flex flex-col transition-colors hover:border-accent/40 hover:bg-bg-card-hover/70"
                >
                  <button
                    onClick={() => toggleSonic(card.id)}
                    className="w-full px-4 py-3 border-b border-border bg-bg-panel/60 text-left hover:bg-bg-panel transition-colors"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm">{card.icon}</span>
                          <h3 className="text-sm font-bold uppercase tracking-wide truncate">{card.title}</h3>
                          {card.id === 'harmonicContent' && lowConfidenceIndicator(chordsAreApproximate)}
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
        </section>
      )}

      {mixGroups.length > 0 && (
        <section id="section-mix-chain" className="space-y-6 scroll-mt-24">
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

                <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
                  {group.cards.map((card) => {
                    const isOpen = !!openMix[card.id];
                    return (
                      <div
                        key={card.id}
                        className="bg-bg-card border border-border rounded-sm overflow-hidden self-start transition-colors hover:border-accent/40 hover:bg-bg-card-hover/70"
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
        </section>
      )}

      {patchCards.length > 0 && (
        <section id="section-patches" className="space-y-6 scroll-mt-24">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Patch Framework
            </h2>
            <Sliders className="w-4 h-4 text-accent opacity-70" />
          </div>

          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
            {patchCards.map((patch) => {
              const isOpen = !!openPatch[patch.id];
              return (
                <div
                  key={patch.id}
                  className="bg-bg-card border border-border rounded-sm overflow-hidden self-start transition-colors hover:border-accent/40 hover:bg-bg-card-hover/70"
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
        </section>
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

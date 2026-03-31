import React, { useMemo, useState } from 'react';
import {
  InterpretationSchemaVersion,
  InterpretationValidationWarning,
  MeasurementAvailabilityContext,
  Phase1Result,
  Phase2Result,
  SpectralArtifacts,
  StemSummaryResult,
} from '../types';
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
import {
  AccentMetricCard,
  MetricBar,
  StatusBadge,
  TokenBadgeList,
} from './MeasurementPrimitives';
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
  stemSummary?: StemSummaryResult | null;
  phase2SchemaVersion?: InterpretationSchemaVersion | null;
  phase2ValidationWarnings?: InterpretationValidationWarning[] | null;
  phase2StatusMessage?: string | null;
  sourceFileName?: string | null;
  spectralArtifacts?: SpectralArtifacts | null;
  measurementAvailability?: MeasurementAvailabilityContext;
  apiBaseUrl?: string;
  runId?: string;
}

const LOW_CHORD_CONFIDENCE_THRESHOLD = 0.5;

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

interface MetaBadgeItem {
  label: string;
  value?: string | null;
}

function MetaBadgeList({ items }: { items: MetaBadgeItem[] }) {
  const visibleItems = items.filter((item) => typeof item.value === 'string' && item.value.trim().length > 0);
  if (visibleItems.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {visibleItems.map((item) => (
        <span
          key={`${item.label}-${item.value}`}
          className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary whitespace-nowrap"
        >
          {item.label}: {item.value}
        </span>
      ))}
    </div>
  );
}

function GroundingBadgeList({
  phase1Fields,
  segmentIndexes,
}: {
  phase1Fields: string[];
  segmentIndexes?: number[];
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {phase1Fields.map((field) => (
        <span
          key={field}
          className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-accent/30 bg-accent/5 text-accent"
        >
          {field}
        </span>
      ))}
      {Array.isArray(segmentIndexes) &&
        segmentIndexes.map((segmentIndex) => (
          <span
            key={`segment-${segmentIndex}`}
            className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-border text-text-secondary"
          >
            Segment {segmentIndex}
          </span>
        ))}
    </div>
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

function isAssumedMeter(phase1: Phase1Result): boolean {
  return phase1.timeSignatureSource === 'assumed_four_four' || (phase1.timeSignatureConfidence ?? 1) <= 0;
}

function meterStatusLabel(phase1: Phase1Result): string {
  return isAssumedMeter(phase1) ? 'ASSUMED' : 'DETECTED';
}

function formatBpmScore(value: number): string {
  return `SCORE ${value.toFixed(2).replace(/\.?0+$/, '')}`;
}

export function AnalysisResults({
  phase1,
  phase2,
  stemSummary = null,
  phase2SchemaVersion = null,
  phase2ValidationWarnings = null,
  phase2StatusMessage = null,
  sourceFileName = null,
  spectralArtifacts = null,
  measurementAvailability,
  apiBaseUrl,
  runId,
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
  const isPhase2V2 = phase2SchemaVersion === 'interpretation.v2';
  const validationWarnings = Array.isArray(phase2ValidationWarnings) ? phase2ValidationWarnings : [];

  const confidenceBadges = toConfidenceBadges(phase2?.confidenceNotes);
  const arrangement = buildArrangementViewModel(phase1, phase2?.arrangementOverview);
  const sonicCards = buildSonicElementCards(phase1, phase2?.sonicElements);
  const mixGroups = buildMixChainGroups(phase1, phase2?.mixAndMasterChain, phase2?.sonicElements);
  const patchCards = buildPatchCards(phase1, phase2);
  const projectSetup = isPhase2V2 ? phase2?.projectSetup ?? null : null;
  const trackLayout = isPhase2V2 && Array.isArray(phase2?.trackLayout) ? phase2.trackLayout : [];
  const routingBlueprint = isPhase2V2 ? phase2?.routingBlueprint ?? null : null;
  const warpGuide = isPhase2V2 ? phase2?.warpGuide ?? null : null;
  const audioObservations = phase2?.audioObservations ?? null;
  const stemSummaryStems = Array.isArray(stemSummary?.stems) ? stemSummary.stems : [];
  const stemSummaryFlags = Array.isArray(stemSummary?.uncertaintyFlags) ? stemSummary.uncertaintyFlags : [];
  const hasStemSummaryContent = stemSummaryStems.length > 0;
  const warpTargets = warpGuide
    ? [
        { label: 'Full Track', target: warpGuide.fullTrack },
        { label: 'Drums', target: warpGuide.drums },
        { label: 'Bass', target: warpGuide.bass },
        { label: 'Melodic', target: warpGuide.melodic },
        ...(warpGuide.vocals ? [{ label: 'Vocals', target: warpGuide.vocals }] : []),
      ]
    : [];
  const characteristicPills = Array.isArray(phase2?.detectedCharacteristics)
    ? phase2.detectedCharacteristics.slice(0, 4)
    : [];
  const keyIsApproximate = phase1.keyConfidence <= 0.6;
  const chordStrength = getChordStrength(phase1);
  const chordsAreApproximate =
    chordStrength !== null && chordStrength <= LOW_CHORD_CONFIDENCE_THRESHOLD;
  const hasRenderablePhase2Content =
    Boolean(phase2?.trackCharacter?.trim()) ||
    confidenceBadges.length > 0 ||
    characteristicPills.length > 0 ||
    Boolean(projectSetup) ||
    trackLayout.length > 0 ||
    Boolean(routingBlueprint) ||
    Boolean(warpGuide) ||
    Boolean(audioObservations) ||
    arrangement !== null ||
    sonicCards.length > 0 ||
    mixGroups.length > 0 ||
    patchCards.length > 0 ||
    Boolean(phase2?.secretSauce);
  const navSections: StickyNavSection[] = [
    { id: 'section-meas-core', label: 'Core' },
    { id: 'section-meas-loudness', label: 'Loudness' },
    { id: 'section-meas-mixdoctor', label: 'MixDoctor' },
    { id: 'section-meas-spectral', label: 'Spectral' },
    { id: 'section-meas-stereo', label: 'Stereo' },
    { id: 'section-meas-rhythm', label: 'Rhythm' },
    { id: 'section-meas-harmony', label: 'Harmony' },
    { id: 'section-meas-structure', label: 'Structure' },
    { id: 'section-meas-synthesis', label: 'Synthesis' },
    projectSetup ? { id: 'section-project-setup', label: 'Setup' } : null,
    trackLayout.length > 0 ? { id: 'section-track-layout', label: 'Layout' } : null,
    routingBlueprint ? { id: 'section-routing-blueprint', label: 'Routing' } : null,
    warpGuide ? { id: 'section-warp-guide', label: 'Warp' } : null,
    audioObservations ? { id: 'section-audio-observations', label: 'Audio' } : null,
    arrangement ? { id: 'section-arrangement', label: 'Arrangement' } : null,
    { id: 'section-session', label: 'Session' },
    hasStemSummaryContent ? { id: 'section-stem-summary', label: 'Stem Summary' } : null,
    sonicCards.length > 0 ? { id: 'section-sonic-elements', label: 'Sonic' } : null,
    mixGroups.length > 0 ? { id: 'section-mix-chain', label: 'Mix Chain' } : null,
    patchCards.length > 0 ? { id: 'section-patches', label: 'Patches' } : null,
  ].filter((section): section is StickyNavSection => section !== null);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      data-testid="analysis-results-root"
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
            data-testid="analysis-export-json"
            className="flex items-center gap-2 px-4 py-2 bg-bg-panel border border-border rounded text-xs font-mono uppercase tracking-wider hover:bg-bg-card-hover hover:border-accent/50 transition-all group"
          >
            <FileJson className="w-3 h-3 text-text-secondary group-hover:text-accent" />
            <span>JSON_DATA</span>
          </button>
          <button
            onClick={handleExportMD}
            data-testid="analysis-export-markdown"
            className="flex items-center gap-2 px-4 py-2 bg-accent/10 border border-accent/50 text-accent rounded text-xs font-mono uppercase tracking-wider hover:bg-accent/20 transition-all shadow-[0_0_10px_rgba(255,85,0,0.1)]"
          >
            <FileText className="w-3 h-3" />
            <span>REPORT_MD</span>
          </button>
        </div>
      </div>

      <StickyNav sections={navSections} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {/* TEMPO */}
        <AccentMetricCard
          label={
            <span className="flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-accent/60" />
              <span>TEMPO</span>
            </span>
          }
          value={finalBpm}
          unit="BPM"
          headerRight={<PhaseSourceBadge source="measured" />}
          footer={
            <div className="space-y-2">
              <StatusBadge
                label={formatBpmScore(phase1.bpmConfidence)}
                tone="accent"
                compact
              />
              {phase1.bpmSource && (
                <span className="block text-[8px] font-mono uppercase tracking-wide text-text-secondary/50">
                  {phase1.bpmSource.replace(/_/g, ' ')}
                </span>
              )}
            </div>
          }
        />

        {/* KEY SIG */}
        <AccentMetricCard
          label={
            <span className="flex items-center gap-1.5">
              <Music className="w-3.5 h-3.5 text-accent/60" />
              <span>KEY SIG</span>
            </span>
          }
          value={<span className="truncate block">{finalKey}</span>}
          headerRight={
            <div className="flex items-center gap-1">
              <PhaseSourceBadge source="measured" />
              {lowConfidenceIndicator(keyIsApproximate)}
            </div>
          }
          footer={
            <div className="space-y-1.5">
              <MetricBar
                value={phase1.keyConfidence}
                color="var(--color-accent)"
                glow
              />
              <span className="block text-[8px] font-mono uppercase tracking-wide text-text-secondary/60 tabular-nums">
                CONF {(phase1.keyConfidence * 100).toFixed(0)}%
              </span>
            </div>
          }
        />

        {/* METER */}
        <AccentMetricCard
          label={
            <span className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-accent/60" />
              <span>METER</span>
            </span>
          }
          value={phase1.timeSignature}
          footer={<StatusBadge label={meterStatusLabel(phase1)} tone="muted" compact />}
        />

        {/* CHARACTER — genre primary, characteristic pills secondary */}
        {phase1.genreDetail ? (
          <AccentMetricCard
            label={
              <span className="flex items-center gap-1.5">
                <Disc className="w-3.5 h-3.5 text-accent/60" />
                <span>CHARACTER</span>
              </span>
            }
            value={<span className="truncate block capitalize text-[1.5rem]">{phase1.genreDetail.genre}</span>}
            headerRight={<PhaseSourceBadge source="measured" />}
            footer={
              <div className="space-y-2">
                <TokenBadgeList
                  items={[
                    { label: phase1.genreDetail.genreFamily.toUpperCase(), tone: 'accent' },
                    ...(phase1.genreDetail.secondaryGenre
                      ? [{ label: phase1.genreDetail.secondaryGenre.toUpperCase(), tone: 'muted' as const }]
                      : []),
                  ]}
                />
                <MetricBar
                  value={phase1.genreDetail.confidence}
                  color="var(--color-accent)"
                  glow
                />
                <span className="block text-[8px] font-mono uppercase tracking-wide text-text-secondary/60 tabular-nums">
                  CONF {Math.round(phase1.genreDetail.confidence * 100)}%
                </span>
              </div>
            }
          />
        ) : (
          <AccentMetricCard
            label={
              <span className="flex items-center gap-1.5">
                <Disc className="w-3.5 h-3.5 text-accent/60" />
                <span>CHARACTER</span>
              </span>
            }
            value={<span className="text-base font-mono uppercase tracking-wide text-text-secondary/60">SCANNING...</span>}
            footer={
              characteristicPills.length > 0 ? (
                <div className="w-full flex flex-wrap gap-1">
                  {characteristicPills.map((item, idx) => (
                    <span
                      key={`${item.name}-${idx}`}
                      className={`inline-flex items-center px-2 py-1 rounded-sm border text-[9px] font-mono uppercase tracking-wide ${characteristicPillClass(item.confidence)}`}
                    >
                      {shortenCharacteristicName(item.name)}
                    </span>
                  ))}
                </div>
              ) : undefined
            }
          />
        )}
      </div>

      <MeasurementDashboard
        phase1={phase1}
        spectralArtifacts={spectralArtifacts}
        measurementAvailability={measurementAvailability}
        apiBaseUrl={apiBaseUrl}
        runId={runId}
      />

      <section data-testid="interpretation-panel" className="space-y-2">
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
      </section>

      {validationWarnings.length > 0 && (
        <section className="space-y-3 rounded-sm border border-warning/30 bg-warning/10 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-mono uppercase tracking-wider text-warning">
                Interpretation Caution
              </h2>
              <p className="text-[10px] font-mono uppercase tracking-[0.16em] text-warning/80">
                The backend kept the result, but flagged parts that may not match the approved Live catalog.
              </p>
            </div>
            <span className="text-[10px] font-mono uppercase px-2 py-1 rounded border border-warning/30 text-warning">
              {validationWarnings.length} warning{validationWarnings.length === 1 ? '' : 's'}
            </span>
          </div>
          <div className="space-y-2">
            {validationWarnings.map((warning, index) => (
              <div
                key={`${warning.code ?? 'warning'}-${warning.path ?? index}`}
                className="rounded-sm border border-warning/20 bg-bg-panel/60 p-3 space-y-1"
              >
                <div className="flex flex-wrap gap-1.5">
                  {warning.code && (
                    <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-warning/30 text-warning">
                      {warning.code}
                    </span>
                  )}
                  {warning.path && (
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-border text-text-secondary">
                      {warning.path}
                    </span>
                  )}
                </div>
                <p className="text-xs font-mono text-text-secondary leading-relaxed">
                  {truncateAtSentenceBoundary(warning.message, 240)}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

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

      {phase2?.trackCharacter && (
        <section className="space-y-3">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Track Character
            </h2>
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">AI INTERP</span>
          </div>
          <p className="text-xs text-text-secondary font-mono leading-relaxed opacity-80">
            {truncateAtSentenceBoundary(phase2.trackCharacter, 900)}
          </p>
        </section>
      )}

      {audioObservations && (
        <section id="section-audio-observations" className="space-y-6 scroll-mt-24">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Audio Observations
            </h2>
            <span className="text-[10px] font-mono bg-bg-panel border border-border text-text-secondary px-2 py-1 rounded font-bold">
              Perceptual / Audio-Derived
            </span>
          </div>

          <div className="rounded-sm border border-accent/20 bg-accent/5 p-4 space-y-2">
            <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-accent">
              Sound Design Fingerprint
            </p>
            <p className="text-xs font-mono text-text-secondary leading-relaxed">
              {truncateAtSentenceBoundary(audioObservations.soundDesignFingerprint, 320)}
            </p>
          </div>

          {audioObservations.elementCharacter.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {audioObservations.elementCharacter.map((item, index) => (
                <div
                  key={`${item.element}-${index}`}
                  className="rounded-sm border border-border bg-bg-card p-4 space-y-2"
                >
                  <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
                    {item.element}
                  </p>
                  <p className="text-xs font-mono text-text-secondary leading-relaxed">
                    {truncateAtSentenceBoundary(item.description, 220)}
                  </p>
                </div>
              ))}
            </div>
          )}

          {audioObservations.productionSignatures.length > 0 && (
            <div className="space-y-2">
              <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
                Production Signatures
              </p>
              <div className="flex flex-wrap gap-1.5">
                {audioObservations.productionSignatures.map((signature, index) => (
                  <span
                    key={`${signature}-${index}`}
                    className="text-[10px] font-mono rounded-sm border border-accent/30 bg-accent/5 px-2 py-1 text-accent"
                  >
                    {truncateAtSentenceBoundary(signature, 140)}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="rounded-sm border border-border bg-bg-card p-4 space-y-2">
            <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
              Mix Context
            </p>
            <p className="text-xs font-mono text-text-secondary leading-relaxed">
              {truncateAtSentenceBoundary(audioObservations.mixContext, 280)}
            </p>
          </div>
        </section>
      )}

      {projectSetup && (
        <section id="section-project-setup" className="space-y-6 scroll-mt-24">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Project Setup
            </h2>
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">
              LIVE 12 V2
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <AccentMetricCard label="Tempo" value={projectSetup.tempoBpm} unit="BPM" />
            <AccentMetricCard label="Meter" value={projectSetup.timeSignature} />
            <AccentMetricCard label="Sample Rate" value={`${projectSetup.sampleRate} Hz`} />
            <AccentMetricCard label="Bit Depth" value={`${projectSetup.bitDepth}-bit`} />
            <AccentMetricCard label="Headroom" value={projectSetup.headroomTarget} />
          </div>

          <div className="rounded-sm border border-border bg-bg-card p-4">
            <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
              Session Goal
            </p>
            <p className="mt-2 text-xs font-mono text-text-secondary leading-relaxed">
              {truncateAtSentenceBoundary(projectSetup.sessionGoal, 320)}
            </p>
          </div>
        </section>
      )}

      {trackLayout.length > 0 && (
        <section id="section-track-layout" className="space-y-6 scroll-mt-24">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Track Layout
            </h2>
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">
              SCAFFOLD
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {trackLayout.map((item) => (
              <div key={`${item.order}-${item.name}`} className="rounded-sm border border-border bg-bg-card p-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="w-6 h-6 rounded-sm bg-bg-panel border border-border text-accent font-mono text-[10px] flex items-center justify-center">
                      {item.order}
                    </span>
                    <div className="min-w-0">
                      <h3 className="text-sm font-bold text-text-primary truncate">{item.name}</h3>
                      <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                        {item.type}
                      </p>
                    </div>
                  </div>
                </div>
                <p className="text-xs font-mono text-text-secondary leading-relaxed">
                  {truncateAtSentenceBoundary(item.purpose, 220)}
                </p>
                <div className="space-y-2">
                  <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
                    Grounding
                  </p>
                  <GroundingBadgeList
                    phase1Fields={item.grounding.phase1Fields}
                    segmentIndexes={item.grounding.segmentIndexes}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {routingBlueprint && (
        <section id="section-routing-blueprint" className="space-y-6 scroll-mt-24">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Routing Blueprint
            </h2>
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">
              SIGNAL MAP
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="rounded-sm border border-border bg-bg-card p-4 space-y-2">
              <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">Sidechain Source</p>
              <p className="text-sm font-bold text-text-primary">{routingBlueprint.sidechainSource ?? 'Not specified'}</p>
            </div>
            <div className="rounded-sm border border-border bg-bg-card p-4 space-y-2 md:col-span-2">
              <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">Sidechain Targets</p>
              <div className="flex flex-wrap gap-1.5">
                {routingBlueprint.sidechainTargets.map((target) => (
                  <span
                    key={target}
                    className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-accent/30 bg-accent/5 text-accent"
                  >
                    {target}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {routingBlueprint.returns.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {routingBlueprint.returns.map((returnTrack) => (
                <div key={returnTrack.name} className="rounded-sm border border-border bg-bg-card p-4 space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-sm font-bold text-text-primary">{returnTrack.name}</h3>
                    <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary">
                      {returnTrack.deviceFocus}
                    </span>
                  </div>
                  <p className="text-xs font-mono text-text-secondary leading-relaxed">
                    {truncateAtSentenceBoundary(returnTrack.purpose, 220)}
                  </p>
                  <MetaBadgeList
                    items={[
                      { label: 'Sends', value: returnTrack.sendSources.join(', ') },
                      { label: 'Level', value: returnTrack.levelGuidance },
                    ]}
                  />
                </div>
              ))}
            </div>
          )}

          {routingBlueprint.notes.length > 0 && (
            <div className="rounded-sm border border-border bg-bg-card p-4 space-y-2">
              <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">Routing Notes</p>
              {routingBlueprint.notes.map((note, index) => (
                <p key={`${note}-${index}`} className="text-xs font-mono text-text-secondary leading-relaxed">
                  {truncateAtSentenceBoundary(note, 220)}
                </p>
              ))}
            </div>
          )}
        </section>
      )}

      {warpGuide && (
        <section id="section-warp-guide" className="space-y-6 scroll-mt-24">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Warp Guide
            </h2>
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">
              CLIP PREP
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            {warpTargets.map(({ label, target }) => (
              <div key={label} className="rounded-sm border border-border bg-bg-card p-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">{label}</p>
                  <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-accent/30 bg-accent/5 text-accent">
                    {target.warpMode}
                  </span>
                </div>
                {target.settings && (
                  <p className="text-[10px] font-mono text-text-secondary uppercase tracking-wide">
                    {target.settings}
                  </p>
                )}
                <p className="text-xs font-mono text-text-secondary leading-relaxed">
                  {truncateAtSentenceBoundary(target.reason, 220)}
                </p>
              </div>
            ))}
          </div>

          <div className="rounded-sm border border-border bg-bg-card p-4">
            <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">Why These Modes</p>
            <p className="mt-2 text-xs font-mono text-text-secondary leading-relaxed">
              {truncateAtSentenceBoundary(warpGuide.rationale, 320)}
            </p>
          </div>
        </section>
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
                  <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
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
                        {isPhase2V2 && (segment.sceneName || segment.abletonAction || segment.automationFocus) && (
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                            {segment.sceneName && (
                              <div className="border border-border/70 rounded-sm bg-bg-panel/50 px-2 py-2 space-y-1">
                                <span className="inline-flex text-[9px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded border border-border text-text-secondary">
                                  Scene
                                </span>
                                <p className="text-[11px] text-text-secondary/90 font-mono leading-relaxed">
                                  {segment.sceneName}
                                </p>
                              </div>
                            )}
                            {segment.abletonAction && (
                              <div className="border border-border/70 rounded-sm bg-bg-panel/50 px-2 py-2 space-y-1">
                                <span className="inline-flex text-[9px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded border border-border text-text-secondary">
                                  Ableton Action
                                </span>
                                <p className="text-[11px] text-text-secondary/90 font-mono leading-relaxed">
                                  {segment.abletonAction}
                                </p>
                              </div>
                            )}
                            {segment.automationFocus && (
                              <div className="border border-border/70 rounded-sm bg-bg-panel/50 px-2 py-2 space-y-1">
                                <span className="inline-flex text-[9px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded border border-border text-text-secondary">
                                  Automation Focus
                                </span>
                                <p className="text-[11px] text-text-secondary/90 font-mono leading-relaxed">
                                  {segment.automationFocus}
                                </p>
                              </div>
                            )}
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

      {hasStemSummaryContent && (
        <section id="section-stem-summary" className="space-y-6 scroll-mt-24">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              AI stem summary for musical understanding
            </h2>
            <span className="text-[10px] font-mono bg-bg-panel border border-accent/30 text-accent px-2 py-1 rounded font-bold">
              BEST EFFORT
            </span>
          </div>

          <div className="rounded-sm border border-accent/20 bg-accent/5 p-4 space-y-2">
            <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-accent">
              What this is for
            </p>
            <p className="text-xs font-mono text-text-secondary leading-relaxed">
              This is a plain-language musical summary of the separated stems. It is useful for understanding the role of the bass and upper material, not for exact MIDI truth.
            </p>
            {stemSummary?.summary && (
              <p className="text-xs font-mono text-text-secondary leading-relaxed">
                {truncateAtSentenceBoundary(stemSummary.summary, 320)}
              </p>
            )}
          </div>

          {stemSummaryFlags.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {stemSummaryFlags.map((flag, index) => (
                <span
                  key={`${flag}-${index}`}
                  className="text-[10px] font-mono rounded-sm border border-warning/30 bg-warning/10 px-2 py-1 text-warning"
                >
                  {flag}
                </span>
              ))}
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {stemSummaryStems.map((stem) => (
              <div
                key={stem.stem}
                className="rounded-sm border border-border bg-bg-card p-4 space-y-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-bold uppercase tracking-wide text-text-primary">
                      {stem.label}
                    </h3>
                    <p className="mt-2 text-xs font-mono text-text-secondary leading-relaxed">
                      {truncateAtSentenceBoundary(stem.summary, 220)}
                    </p>
                  </div>
                  <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-accent/30 bg-accent/5 text-accent">
                    {stem.stem}
                  </span>
                </div>

                <div className="grid grid-cols-1 gap-3">
                  {stem.bars.map((bar, index) => (
                    <div
                      key={`${stem.stem}-bar-${bar.barStart}-${index}`}
                      className="rounded-sm border border-border/80 bg-bg-panel/50 p-3 space-y-2"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
                          Bars {bar.barStart}-{bar.barEnd}
                        </span>
                        <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary">
                          {bar.uncertaintyLevel} certainty
                        </span>
                      </div>
                      {bar.noteHypotheses.length > 0 && (
                        <p className="text-xs font-mono text-text-secondary leading-relaxed">
                          Notes: {bar.noteHypotheses.join(', ')}
                        </p>
                      )}
                      {bar.scaleDegreeHypotheses.length > 0 && (
                        <p className="text-xs font-mono text-text-secondary leading-relaxed">
                          Scale degrees: {bar.scaleDegreeHypotheses.join(', ')}
                        </p>
                      )}
                      <p className="text-xs font-mono text-text-secondary leading-relaxed">
                        Rhythm: {truncateAtSentenceBoundary(bar.rhythmicPattern, 180)}
                      </p>
                      <p className="text-xs font-mono text-warning leading-relaxed">
                        Uncertainty: {truncateAtSentenceBoundary(bar.uncertaintyReason, 180)}
                      </p>
                    </div>
                  ))}
                </div>

                <div className="space-y-2">
                  <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
                    Global pattern
                  </p>
                  <div className="space-y-1">
                    <p className="text-xs font-mono text-text-secondary leading-relaxed">
                      Bass role: {truncateAtSentenceBoundary(stem.globalPatterns.bassRole, 180)}
                    </p>
                    <p className="text-xs font-mono text-text-secondary leading-relaxed">
                      Musical role: {truncateAtSentenceBoundary(stem.globalPatterns.melodicRole, 180)}
                    </p>
                    <p className="text-xs font-mono text-text-secondary leading-relaxed">
                      Movement: {truncateAtSentenceBoundary(stem.globalPatterns.pumpingOrModulation, 180)}
                    </p>
                  </div>
                </div>

                {stem.uncertaintyFlags.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {stem.uncertaintyFlags.map((flag, index) => (
                      <span
                        key={`${stem.stem}-flag-${index}`}
                        className="text-[10px] font-mono rounded-sm border border-warning/30 bg-warning/10 px-2 py-1 text-warning"
                      >
                        {flag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

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
                              <div className="mt-2">
                                <MetaBadgeList
                                  items={[
                                    { label: 'Family', value: card.deviceFamily },
                                    { label: 'Context', value: card.trackContext },
                                    { label: 'Stage', value: card.workflowStage },
                                  ]}
                                />
                              </div>
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
                        <div className="mt-2">
                          <MetaBadgeList
                            items={[
                              { label: 'Family', value: patch.deviceFamily },
                              { label: 'Context', value: patch.trackContext },
                              { label: 'Stage', value: patch.workflowStage },
                            ]}
                          />
                        </div>
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

              {isPhase2V2 && Array.isArray(phase2.secretSauce.workflowSteps) && phase2.secretSauce.workflowSteps.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-border/50">
                  {phase2.secretSauce.workflowSteps.map((step) => (
                    <div key={step.step} className="rounded-sm border border-border bg-bg-panel/40 p-4 space-y-3">
                      <div className="flex items-center gap-3">
                        <span className="flex-shrink-0 w-6 h-6 rounded-sm bg-bg-panel border border-border flex items-center justify-center text-accent font-mono text-xs">
                          {step.step}
                        </span>
                        <div className="min-w-0">
                          <p className="text-sm font-bold text-text-primary truncate">{step.device}</p>
                          <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                            {step.parameter}: {step.value}
                          </p>
                        </div>
                      </div>
                      <MetaBadgeList
                        items={[
                          { label: 'Context', value: step.trackContext },
                          { label: 'Device', value: step.device },
                        ]}
                      />
                      <p className="text-xs text-text-secondary leading-relaxed font-mono">
                        {truncateAtSentenceBoundary(step.instruction, 220)}
                      </p>
                      <div className="border border-accent/20 bg-accent/5 rounded-sm px-2 py-2">
                        <p className="text-[10px] font-mono text-accent uppercase tracking-wide">
                          Measurement Reason
                        </p>
                        <p className="text-xs font-mono text-text-secondary mt-1 leading-relaxed">
                          {truncateAtSentenceBoundary(step.measurementJustification, 220)}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
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
              )}
            </div>
          </div>
        </div>
      )}
    </motion.div>
  );
}

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AnalysisStageStatus,
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
  AudioWaveform,
  Check,
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
import { assertNever } from '../utils/assertNever';
import { downloadFile, generateMarkdown } from '../utils/exportUtils';
import { INTERPRETATION_LABEL } from '../services/phaseLabels';
import type { ValidationReport } from '../services/phase2Validator';
import { Phase2ConsistencyReport } from './Phase2ConsistencyReport';
import { isBrowserLoudnessConfigEnabled } from '../config';
import { BrowserLoudnessPanel } from './BrowserLoudnessPanel';
import { MeasurementDashboard } from './MeasurementDashboard';
import { SamplePlayback } from './SamplePlayback';
import { SessionMusicianPanel } from './SessionMusicianPanel';
import { TranscriptionPianorollBlock } from './TranscriptionPianorollBlock';
import { Mt3TranscriptionPanel } from './Mt3TranscriptionPanel';
import { StemListeningNotesPanel } from './StemListeningNotesPanel';
import { hasStemListeningNotesContent } from '../services/sessionMusician';
import {
  AccentMetricCard,
  MetricBar,
  StatusBadge,
  TokenBadgeList,
} from './MeasurementPrimitives';
import { Button, DeviceRack, MetricTile, Pill, SectionHeader } from './ui';
import { PhaseSourceBadge } from './PhaseSourceBadge';
import { StickyNav, type StickyNavSection } from './StickyNav';
import { CitationBlock, CitationHeadline } from './CitationBlock';
import { ConfidenceBandBadge } from './sessionMusician/ConfidenceBandBadge';
import { RecommendationVerificationBadge } from './RecommendationVerificationBadge';
import { toConfidenceBand } from '../services/sessionMusician/confidenceBand';
import { loadAppliedIds, toggleAppliedId } from '../services/appliedRecommendations';
import {
  buildArrangementViewModel,
  buildMixChainGroups,
  buildPatchCards,
  buildPatchGroups,
  buildSonicElementCards,
  calculateStereoBandStyle,
  toConfidenceBadges,
  truncateAtSentenceBoundary,
  truncateBySentenceCount,
} from './analysisResultsViewModel';
import {
  formatDisplayText,
  getTextRoleClassName,
  type TextRole,
} from '../utils/displayText';

export interface AnalysisResultsProps {
  phase1: Phase1Result | null;
  phase2: Phase2Result | null;
  stemSummary?: StemSummaryResult | null;
  phase2SchemaVersion?: InterpretationSchemaVersion | null;
  phase2ValidationWarnings?: InterpretationValidationWarning[] | null;
  /**
   * Frontend-computed chain-of-custody report (BPM/key/LUFS drift, citation
   * completeness, hedging). Rendered alongside the backend-projected
   * `phase2ValidationWarnings` so both consistency channels read as one surface.
   */
  phase2ConsistencyReport?: ValidationReport | null;
  phase2StatusMessage?: string | null;
  sourceFileName?: string | null;
  /** The uploaded source File, retained for the in-browser loudness readout (WS3c). */
  audioFile?: File | null;
  spectralArtifacts?: SpectralArtifacts | null;
  measurementAvailability?: MeasurementAvailabilityContext;
  apiBaseUrl?: string;
  runId?: string;
  pitchNoteMode?: 'stem_notes' | 'off' | null;
  /**
   * Current status of the interpretation stage, used to label the results
   * header honestly (e.g. "AI interpretation in progress…" vs "Recommendations
   * ready" vs "AI interpretation failed"). Pass `null`/`undefined` to fall
   * back to the neutral subtitle. Decouples the header text from a hardcoded
   * "PHASE COMPLETE" string that previously rendered regardless of state.
   */
  interpretationStatus?: AnalysisStageStatus | null;
  /**
   * Click handler for the "Re-analyze with stem-aware pipeline" button that
   * Block A renders in its legacy render state. App owns the run-creation
   * primitives; pass `undefined` to hide the button (e.g. while an analysis
   * is already in flight or no source File is loaded).
   */
  onReanalyzeWithStemAware?: () => void;
  /**
   * Audit Finding #14 + #15: SHA-256 of the source audio content. Used to key
   * the per-file applied-recommendations tracker so producers can check off
   * Mix Chain / Patches cards as they wire them into Live and have that
   * progress survive both a page reload and a re-analysis of the same file
   * (rename-resilient because hash is content-based, not name-based).
   * Pass `null`/`undefined` to disable the tracker (no checkboxes shown).
   */
  audioContentHash?: string | null;
}

const LOW_CHORD_CONFIDENCE_THRESHOLD = 0.5;

/**
 * Maps the interpretation stage status to a subtitle string for the results
 * header. Returns null for statuses that shouldn't surface in the header
 * (e.g. unknown values). Centralised so the header never lies about
 * Phase 2's actual state.
 */
export function getInterpretationSubtitle(
  status: AnalysisStageStatus | null | undefined,
): string | null {
  if (!status) return null;
  switch (status) {
    case 'completed':
      return 'Recommendations ready';
    case 'running':
      return 'AI interpretation in progress…';
    case 'queued':
    case 'ready':
    case 'blocked':
      return 'AI interpretation pending';
    case 'failed':
      return 'AI interpretation failed — retry from progress panel';
    case 'interrupted':
      return 'AI interpretation stopped';
    case 'not_requested':
      return 'Measurements only';
    default:
      return assertNever(status);
  }
}

/**
 * Audit Finding #6 (streaming reveal): tooltip text for the disabled StickyNav
 * pills that correspond to Phase 2 sections (Sonic / Mix Chain / Patches).
 * Used to live as a hardcoded "Recommendations not produced this run" which
 * lied during the 4–5 minute mid-run window where Phase 1 had streamed in
 * but Phase 2 was still working.
 *
 * Mirrors `getInterpretationSubtitle` but phrased as a nav-pill tooltip
 * ("AI interpretation in progress…" reads naturally in the header subtitle
 * AND in a pill hover), so a future copy refactor can collapse the two
 * helpers if desired.
 */
export function getPhase2NavDisabledReason(
  status: AnalysisStageStatus | null | undefined,
): string {
  // `completed` with no cards = Phase 2 returned nothing actionable. Falls
  // back to the legacy phrasing alongside null/undefined so an empty result
  // still reads honest.
  if (status == null) return 'Recommendations not produced this run';
  switch (status) {
    case 'completed':
      return 'Recommendations not produced this run';
    case 'running':
      return 'AI interpretation in progress…';
    case 'queued':
    case 'ready':
    case 'blocked':
      return 'AI interpretation pending — waiting to start';
    case 'not_requested':
      return 'AI interpretation off for this run';
    case 'failed':
      return 'AI interpretation failed — retry from progress panel';
    case 'interrupted':
      return 'AI interpretation stopped';
    default:
      return assertNever(status);
  }
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

/**
 * Audit Finding #14: per-card "applied to my session" toggle. Looks like a
 * checkbox to producers who scan top-down through Mix Chain / Patches lists.
 * Renders nothing when no tracker is wired (e.g., file hash unavailable);
 * stops click propagation so toggling doesn't also expand/collapse the card.
 */
function AppliedCheckbox({
  isApplied,
  onToggle,
  ariaLabel,
}: {
  isApplied: boolean;
  onToggle: () => void;
  ariaLabel: string;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={isApplied}
      aria-label={ariaLabel}
      data-applied={isApplied || undefined}
      data-testid="applied-checkbox"
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
      className={`flex-shrink-0 flex items-center justify-center w-4 h-4 rounded-sm border transition-colors ${
        isApplied
          ? 'border-success/60 bg-success/15 text-success hover:border-success'
          : 'border-border bg-bg-card/40 text-text-secondary/40 hover:border-accent/40 hover:text-accent'
      }`}
      title={isApplied ? 'Applied — click to unmark' : 'Mark as applied'}
    >
      {isApplied ? <Check className="w-3 h-3" /> : null}
    </button>
  );
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
      <Button
        variant="link"
        size="sm"
        onClick={onToggle}
        className="!text-accent hover:!text-accent/80 !normal-case !tracking-wide uppercase"
      >
        {showSources ? '▼' : '▶'} Sources
      </Button>
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

// Audit Finding #4: `confidenceClass` was the tone mapper for the legacy
// three-level Confidence Notes chips. Retired — chips now route through
// `ConfidenceBandBadge` with the canonical four-band ladder.

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

function groupIcon(groupName: string): React.ReactNode {
  if (groupName.includes('DRUM PROCESSING')) return '🥁';
  // Audit #13: 🫧 (bubbles) is not a bass signifier in any audio
  // convention. Swapped to the monochrome Lucide waveform glyph, which
  // matches the app's icon language. Other groups keep their emoji
  // landmarks for now (smallest blast radius).
  if (groupName.includes('BASS PROCESSING')) {
    return <AudioWaveform className="w-3.5 h-3.5 inline -mt-0.5" aria-hidden="true" />;
  }
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

function textRoleClassName(role: TextRole, className = ''): string {
  return [getTextRoleClassName(role), className].filter(Boolean).join(' ');
}

interface ResultsSectionHeaderProps {
  title: React.ReactNode;
  rightSlot?: React.ReactNode;
  titleRole?: TextRole;
  titleClassName?: string;
  className?: string;
}

/**
 * Thin wrapper around the SectionHeader primitive — preserves the
 * (title, rightSlot, titleRole, titleClassName, className) API the rest of
 * AnalysisResults expects while letting the primitive own the actual layout
 * + LED indicator + data-text-role propagation. The static accent dot
 * (`<span class="w-2 h-2 bg-accent rounded-full">`) is upgraded to the
 * pulsing `.led-indicator--active` glyph that every other DeviceRack /
 * SectionHeader in the migration uses.
 */
function ResultsSectionHeader({
  title,
  rightSlot,
  titleRole,
  titleClassName,
  className,
}: ResultsSectionHeaderProps) {
  return (
    <SectionHeader
      title={title}
      titleRole={titleRole}
      titleClassName={titleClassName}
      action={rightSlot}
      variant="underline"
      size="md"
      ledTone="accent"
      className={className}
    />
  );
}

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

interface InterpretationWarningMapping {
  originalValue?: string;
  coercedValue?: string;
  path?: string;
}

interface GroupedInterpretationWarning {
  key: string;
  code?: string;
  count: number;
  tone: 'adjustment' | 'warning';
  title: string;
  message: string;
  paths: string[];
  mappings: InterpretationWarningMapping[];
}

type StyleProfileSectionState = 'ready' | 'dropped' | 'omitted' | 'disabled' | 'pending';

function MetaBadgeList({ items }: { items: MetaBadgeItem[] }) {
  const visibleItems = items.filter((item) => typeof item.value === 'string' && item.value.trim().length > 0);
  if (visibleItems.length === 0) return null;

  // Audit N8: previously each chip rendered as `Family: Native` /
  // `Context: Acid bass` / `Stage: Sound design`. The `Label:` prefix read
  // as a JSON-key column header — engineering-flavour. The chip content
  // alone (`Acid bass`) is enough; we keep `item.label` only for the React
  // key. Tooltip preserves the original label for users who want context.
  return (
    <div className="flex flex-wrap gap-1.5">
      {visibleItems.map((item) => (
        <span
          key={`${item.label}-${item.value}`}
          title={item.label}
          className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary whitespace-nowrap"
        >
          {item.value}
        </span>
      ))}
    </div>
  );
}

// Audit Finding #2: `GroundingBadgeList` (9px monospace field-path pills) was
// retired in favor of the structured `CitationBlock` primitive. The component
// previously lived here and rendered raw field paths like `bpmConfidence` as
// orange-accent pills. Track Layout — its only call site — now uses
// CitationBlock with the segmentIndexes routed through the `extraRows` prop.

// Audit Finding #1C: the Interpretation Caution panel used to render the
// backend's `originalValue` / `coercedValue` strings verbatim inside small
// badges. For dropped Phase 2 recommendations, the backend JSON-dumps the
// whole AbletonRecommendation object into `originalValue` (see
// `_stringify_warning_value` / `_build_phase2_validation_warning` in
// `apps/backend/server_phase2.py`). The producer would see a literal
// `{"advancedTip":"…","device":"$Saturator","phase1Fields":[...],…}` string
// inside the panel — engine output leaking through.
//
// `formatDroppedValue` keeps the backend contract intact and renders a
// compact human summary for JSON-shaped values: parse, pick a few headline
// keys (device, parameter, value, …), join as "k: v · k: v". Non-JSON
// strings pass through. Invalid JSON falls back to a truncated raw string.
const FORMAT_DROPPED_VALUE_HEADLINE_KEYS = [
  'device',
  'parameter',
  'value',
  'category',
  'name',
  'field',
] as const;
const FORMAT_DROPPED_VALUE_MAX_CHARS = 80;

function formatDroppedValue(raw: unknown): string {
  if (raw === null || raw === undefined) return '—';
  const str = String(raw).trim();
  if (str.length === 0) return '—';
  const looksLikeJson = str.startsWith('{') || str.startsWith('[');
  if (!looksLikeJson) {
    return str.length > FORMAT_DROPPED_VALUE_MAX_CHARS
      ? `${str.slice(0, FORMAT_DROPPED_VALUE_MAX_CHARS - 1)}…`
      : str;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(str);
  } catch {
    return str.length > FORMAT_DROPPED_VALUE_MAX_CHARS
      ? `${str.slice(0, FORMAT_DROPPED_VALUE_MAX_CHARS - 1)}…`
      : str;
  }

  if (Array.isArray(parsed)) {
    const n = parsed.length;
    const noun = `${n} item${n === 1 ? '' : 's'}`;
    const first = parsed[0];
    if (first && typeof first === 'object' && !Array.isArray(first)) {
      const firstRec = first as Record<string, unknown>;
      const label =
        (typeof firstRec.device === 'string' && firstRec.device) ||
        (typeof firstRec.name === 'string' && firstRec.name) ||
        null;
      if (label) return `${noun} (${label}${n > 1 ? ', …' : ''})`;
    }
    return noun;
  }

  if (parsed && typeof parsed === 'object') {
    const record = parsed as Record<string, unknown>;
    const parts: string[] = [];
    for (const key of FORMAT_DROPPED_VALUE_HEADLINE_KEYS) {
      if (parts.length >= 3) break;
      const value = record[key];
      if (value === null || value === undefined || value === '') continue;
      const valueStr = typeof value === 'string' ? value : JSON.stringify(value);
      if (!valueStr) continue;
      parts.push(`${key}: ${valueStr}`);
    }
    if (parts.length === 0) {
      const entries = Object.entries(record).filter(
        ([, v]) => v !== null && v !== undefined && v !== '',
      );
      for (const [k, v] of entries.slice(0, 2)) {
        const valueStr = typeof v === 'string' ? v : JSON.stringify(v);
        parts.push(`${k}: ${valueStr}`);
      }
    }
    if (parts.length === 0) return '—';
    const joined = parts.join(' · ');
    return joined.length > FORMAT_DROPPED_VALUE_MAX_CHARS
      ? `${joined.slice(0, FORMAT_DROPPED_VALUE_MAX_CHARS - 1)}…`
      : joined;
  }

  // Primitive that happened to start with `{` / `[` (very unlikely after the
  // JSON.parse succeeded into an object, but defensive).
  return str.length > FORMAT_DROPPED_VALUE_MAX_CHARS
    ? `${str.slice(0, FORMAT_DROPPED_VALUE_MAX_CHARS - 1)}…`
    : str;
}

function describeInterpretationWarning(
  warning: InterpretationValidationWarning,
): Pick<GroupedInterpretationWarning, 'tone' | 'title' | 'message'> {
  if (warning.code === 'COERCED_TRACK_CONTEXT') {
    // Two distinct repair reasons produce different titles so they stay as separate rows.
    // "to match the required" → _normalize_track_context_value (format repair)
    // "by matching against declared" → _repair_return_track_context (blueprint match)
    const isFormatRepair = warning.message?.includes('to match the required') ?? true;
    const title = isFormatRepair ? 'Reformatted routing label' : 'Matched routing label to declared return';
    const originalValue = warning.originalValue ? `"${warning.originalValue}"` : 'the AI-generated routing label';
    const coercedValue = warning.coercedValue ? `"${warning.coercedValue}"` : 'the detected return-track label';
    return {
      tone: 'adjustment',
      title,
      message: `The backend kept the result and corrected ${originalValue} to ${coercedValue} so the routing labels match the detected session structure.`,
    };
  }

  return {
    tone: 'warning',
    title: warning.code ? warning.code.replace(/_/g, ' ') : 'Validation warning',
    message: truncateAtSentenceBoundary(warning.message, 240),
  };
}

function groupInterpretationWarnings(
  warnings: InterpretationValidationWarning[],
): GroupedInterpretationWarning[] {
  const grouped = new Map<string, GroupedInterpretationWarning>();

  warnings.forEach((warning, index) => {
    const description = describeInterpretationWarning(warning);
    // Key on code + tone + title only: multiple instances of the same repair reason
    // collapse into one row; different repair reasons (different titles) stay separate.
    const key = [warning.code ?? 'warning', description.tone, description.title].join('::');
    const existing = grouped.get(key);

    const mapping: InterpretationWarningMapping = {
      originalValue: warning.originalValue,
      coercedValue: warning.coercedValue,
      path: warning.path,
    };

    if (existing) {
      existing.count += 1;
      if (warning.path) {
        existing.paths.push(warning.path);
      }
      existing.mappings.push(mapping);
      return;
    }

    grouped.set(key, {
      key: `${key}::${index}`,
      code: warning.code,
      count: 1,
      tone: description.tone,
      title: description.title,
      message: description.message,
      paths: warning.path ? [warning.path] : [],
      mappings: [mapping],
    });
  });

  return Array.from(grouped.values()).map((warning) => ({
    ...warning,
    paths: Array.from(new Set(warning.paths)),
  }));
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

// Audit Finding #4: `formatBpmScore` retired — the BPM card now renders
// the canonical band pill via ConfidenceBandBadge, same vocabulary as
// every other confidence surface.

export function AnalysisResults({
  phase1,
  phase2,
  stemSummary = null,
  phase2SchemaVersion = null,
  phase2ValidationWarnings = null,
  phase2ConsistencyReport = null,
  phase2StatusMessage = null,
  sourceFileName = null,
  audioFile = null,
  spectralArtifacts = null,
  measurementAvailability,
  apiBaseUrl,
  runId,
  pitchNoteMode = null,
  interpretationStatus = null,
  onReanalyzeWithStemAware,
  audioContentHash = null,
}: AnalysisResultsProps) {
  const [openArrangement, setOpenArrangement] = useState<Record<string, boolean>>({});
  const [openSonic, setOpenSonic] = useState<Set<string>>(new Set());
  const [openMix, setOpenMix] = useState<Record<string, boolean>>({});
  const [openPatch, setOpenPatch] = useState<Record<string, boolean>>({});
  const [showSources, setShowSources] = useState<Record<string, boolean>>({});

  // Audit Finding #14 + #15: applied-recommendation set, lazy-initialized
  // from localStorage on first render (keyed by the audio content hash).
  // When the hash changes (new file uploaded), useEffect below re-hydrates
  // the set from storage; we don't keep stale checks across files.
  const [appliedIds, setAppliedIds] = useState<Set<string>>(() =>
    loadAppliedIds(audioContentHash),
  );
  useEffect(() => {
    setAppliedIds(loadAppliedIds(audioContentHash));
  }, [audioContentHash]);

  const toggleApplied = useCallback(
    (cardId: string) => {
      if (!audioContentHash) return;
      const next = toggleAppliedId(audioContentHash, cardId, {
        filename: sourceFileName ?? undefined,
      });
      setAppliedIds(next);
    },
    [audioContentHash, sourceFileName],
  );

  const interpretationSubtitle = getInterpretationSubtitle(interpretationStatus);
  const headerSubtitle = [sourceFileName, interpretationSubtitle]
    .filter((part): part is string => Boolean(part))
    .join(' · ');

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
  const styleProfileDropped = validationWarnings.some(
    (warning) => warning.code === 'DROPPED_INVALID_STYLE_PROFILE',
  );
  const groupedValidationWarnings = useMemo(
    () => groupInterpretationWarnings(validationWarnings),
    [validationWarnings],
  );
  const adjustmentGroups = useMemo(
    () => groupedValidationWarnings.filter((g) => g.tone === 'adjustment'),
    [groupedValidationWarnings],
  );
  const warningGroups = useMemo(
    () => groupedValidationWarnings.filter((g) => g.tone === 'warning'),
    [groupedValidationWarnings],
  );
  const hasAdjustments = adjustmentGroups.length > 0;
  const hasWarnings = warningGroups.length > 0;
  const isMixed = hasAdjustments && hasWarnings;
  const allValidationWarningsAreAdjustments = hasAdjustments && !hasWarnings;
  const adjustmentCount = adjustmentGroups.reduce((sum, g) => sum + g.count, 0);
  const warningCount = warningGroups.reduce((sum, g) => sum + g.count, 0);

  const confidenceBadges = toConfidenceBadges(phase2?.confidenceNotes);
  const arrangement = buildArrangementViewModel(phase1, phase2?.arrangementOverview);
  const sonicCards = buildSonicElementCards(phase1, phase2?.sonicElements);
  const mixGroups = buildMixChainGroups(phase1, phase2?.mixAndMasterChain, phase2?.sonicElements);
  // Audit Finding #14: per-section applied counts, derived from the
  // appliedIds Set + the rendered card lists. Keeps the progress chip in the
  // section header in sync with the per-card checkboxes without a second
  // source of truth.
  const mixCardCount = mixGroups.reduce((sum, group) => sum + group.cards.length, 0);
  const mixAppliedCount = mixGroups.reduce(
    (sum, group) => sum + group.cards.filter((card) => appliedIds.has(card.id)).length,
    0,
  );
  const patchCards = buildPatchCards(phase1, phase2);
  // Audit follow-up: patches render grouped by Mix Chain's processing-stage
  // heuristic. `patchCards` (flat list) is retained for the length checks the
  // StickyNav and gating already use.
  const patchGroups = buildPatchGroups(phase1, phase2);
  const patchAppliedCount = patchCards.filter((card) => appliedIds.has(card.id)).length;
  const projectSetup = isPhase2V2 ? phase2?.projectSetup ?? null : null;
  const trackLayout = isPhase2V2 && Array.isArray(phase2?.trackLayout) ? phase2.trackLayout : [];
  const routingBlueprint = isPhase2V2 ? phase2?.routingBlueprint ?? null : null;
  const warpGuide = isPhase2V2 ? phase2?.warpGuide ?? null : null;
  const audioObservations = phase2?.audioObservations ?? null;
  const styleProfile = phase2?.styleProfile ?? null;
  const styleProfileSectionState: StyleProfileSectionState = styleProfile
    ? 'ready'
    : phase2
      ? styleProfileDropped
        ? 'dropped'
        : 'omitted'
      : phase2StatusMessage
        ? 'disabled'
        : 'pending';
  const hasStemSummaryContent = hasStemListeningNotesContent(stemSummary);
  // Optional MT3 polyphonic-transcription result, projected onto
  // `phase1.transcription.mt3` only when the MT3 stage completed with a
  // non-null result (see projectPhase1FromRun in analysisRunsClient.ts).
  // Additive to Phase 1 — never overrides a measured value (PURPOSE.md #1).
  const mt3Transcription =
    phase1.transcription?.mt3 && phase1.transcription.mt3.tracks.length > 0
      ? phase1.transcription.mt3
      : null;
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
    Boolean(styleProfile) ||
    arrangement !== null ||
    sonicCards.length > 0 ||
    mixGroups.length > 0 ||
    patchCards.length > 0 ||
    Boolean(phase2?.secretSauce);
  // Audit Finding #1: nav order inverted so the producer hits Style → Sonic →
  // Mix Chain → Patches → Session before the 9 measurement panels. The 9
  // `section-meas-*` pills are collapsed into a single `Measurements` entry
  // that scrolls to the (now bottom-of-page) MeasurementDashboard wrapper;
  // within the dashboard the 9 sub-sections still have their own ids and
  // remain individually scrollable via direct hash links if needed.
  const navEntries: Array<StickyNavSection | null> = [
    { id: 'section-style-profile', label: 'Style' },
    projectSetup ? { id: 'section-project-setup', label: 'Setup' } : null,
    trackLayout.length > 0 ? { id: 'section-track-layout', label: 'Layout' } : null,
    routingBlueprint ? { id: 'section-routing-blueprint', label: 'Routing' } : null,
    warpGuide ? { id: 'section-warp-guide', label: 'Warp' } : null,
    audioObservations ? { id: 'section-audio-observations', label: 'Audio' } : null,
    arrangement ? { id: 'section-arrangement', label: 'Arrangement' } : null,
    { id: 'section-session', label: 'Session' },
    mt3Transcription ? { id: 'section-mt3', label: 'MT3 MIDI' } : null,
    hasStemSummaryContent ? { id: 'section-stem-summary', label: 'Stem Notes' } : null,
    // Audit N1 sibling + Finding #6 (streaming reveal): keep Phase 2 nav
    // entries visible even when their sections haven't populated yet.
    // Previously the disabled reason was a hardcoded "not produced this run"
    // that lied during the 4–5 minute mid-run window between Phase 1
    // streaming in and Phase 2 completing. The reason now derives from
    // `interpretationStatus` so a hover during mid-run reads "in progress…"
    // and only a real failure / no-op reads "not produced this run".
    {
      id: 'section-sonic-elements',
      label: 'Sonic',
      disabled: sonicCards.length === 0,
      disabledReason: sonicCards.length === 0
        ? getPhase2NavDisabledReason(interpretationStatus)
        : undefined,
    },
    {
      id: 'section-mix-chain',
      label: 'Mix Chain',
      disabled: mixGroups.length === 0,
      disabledReason: mixGroups.length === 0
        ? getPhase2NavDisabledReason(interpretationStatus)
        : undefined,
    },
    {
      id: 'section-patches',
      label: 'Patches',
      disabled: patchCards.length === 0,
      disabledReason: patchCards.length === 0
        ? getPhase2NavDisabledReason(interpretationStatus)
        : undefined,
    },
    { id: 'section-measurements', label: 'Measurements' },
  ];
  const navSections: StickyNavSection[] = navEntries.filter(
    (section): section is StickyNavSection => section !== null,
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      data-testid="analysis-results-root"
      className="space-y-12"
    >
      <div className="flex flex-col gap-2 pb-6 border-b border-border relative">
        <SectionHeader
          size="lg"
          variant="inline"
          eyebrow="ASA Results"
          titleRole="page-title"
          ledTone="accent"
          title={formatDisplayText('Analysis Results', 'title')}
          action={
            <>
              <Button
                variant="secondary"
                size="md"
                leadingIcon={<FileJson className="w-3 h-3" />}
                onClick={handleExportJSON}
                data-testid="analysis-export-json"
              >
                Download data
              </Button>
              <Button
                variant="primary"
                size="md"
                leadingIcon={<FileText className="w-3 h-3" />}
                onClick={handleExportMD}
                data-testid="analysis-export-markdown"
              >
                Download report
              </Button>
            </>
          }
        />
        {headerSubtitle && (
          <p
            data-text-role="meta"
            data-testid="analysis-results-subtitle"
            className={textRoleClassName('meta', 'opacity-70 pl-4')}
          >
            {headerSubtitle}
          </p>
        )}
      </div>

      <StickyNav sections={navSections} />

      <DeviceRack name="Measurement Summary" density="dense" status="success">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {/* TEMPO */}
          <MetricTile
            size="lg"
            accent="accent"
            icon={<Activity className="w-3.5 h-3.5 text-accent/60" />}
            label="TEMPO"
            value={finalBpm}
            unit="BPM"
            headerRight={<PhaseSourceBadge source="measured" />}
            footer={
              <div className="space-y-2">
                {/* Audit Finding #4: `SCORE 0.86` badge retired in favor of the
                    canonical band pill — same vocabulary as Key, Character, and
                    every other confidence surface. */}
                <ConfidenceBandBadge variant="compact" confidence={phase1.bpmConfidence} />
                {phase1.bpmSource && (
                  <span className="block text-[8px] font-mono uppercase tracking-wide text-text-secondary/50">
                    {phase1.bpmSource.replace(/_/g, ' ')}
                  </span>
                )}
              </div>
            }
          />

          {/* KEY SIG */}
          <MetricTile
            size="lg"
            accent="accent"
            icon={<Music className="w-3.5 h-3.5 text-accent/60" />}
            label="KEY SIG"
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
                {/* Audit Finding #4: `CONF 62%` text replaced with the canonical
                    band pill so every confidence reads in the same vocabulary. */}
                <ConfidenceBandBadge variant="compact" confidence={phase1.keyConfidence} />
              </div>
            }
          />

          {/* METER */}
          <MetricTile
            size="lg"
            accent="accent"
            icon={<Clock className="w-3.5 h-3.5 text-accent/60" />}
            label="METER"
            value={phase1.timeSignature}
            footer={<StatusBadge label={meterStatusLabel(phase1)} tone="muted" compact />}
          />

          {/* CHARACTER — genre primary, characteristic pills secondary */}
          {phase1.genreDetail ? (
            <MetricTile
              size="lg"
              accent="accent"
              icon={<Disc className="w-3.5 h-3.5 text-accent/60" />}
              label="CHARACTER"
              value={<span className="truncate block capitalize">{phase1.genreDetail.genre}</span>}
              headerRight={<PhaseSourceBadge source="measured" />}
              footer={
                <div className="space-y-2">
                  <TokenBadgeList
                    items={[
                      { label: phase1.genreDetail.genreFamily, tone: 'accent' },
                      ...(phase1.genreDetail.secondaryGenre
                        ? [{ label: phase1.genreDetail.secondaryGenre, tone: 'muted' as const }]
                        : []),
                    ]}
                  />
                  <MetricBar
                    value={phase1.genreDetail.confidence}
                    color="var(--color-accent)"
                    glow
                  />
                  {/* Audit Finding #4: `CONF X%` replaced with the canonical
                      band pill — same vocabulary across every confidence. */}
                  <ConfidenceBandBadge
                    variant="compact"
                    confidence={phase1.genreDetail.confidence}
                  />
                </div>
              }
            />
          ) : (
            <MetricTile
              size="lg"
              accent="accent"
              icon={<Disc className="w-3.5 h-3.5 text-accent/60" />}
              label="CHARACTER"
              value={
                <span className="text-base font-mono uppercase tracking-wide text-text-secondary/60">
                  SCANNING...
                </span>
              }
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
      </DeviceRack>

      {/* Audit Finding #1: MeasurementDashboard was here at the top of the
          results scroll, ahead of Style / Sonic Elements / Mix Chain / Patches.
          That ordering serves a DSP engineer auditing the tool, not a producer
          asking "how do I make something that sounds like this?". The dashboard
          now renders at the bottom (search for `section-measurements` below
          Patches/Secret Sauce) so the actionable Phase 2 content reads first
          and the measurement evidence reads as drill-down. */}

      <section data-testid="interpretation-panel" className="space-y-3">
        <ResultsSectionHeader
          title={
            <>
              {INTERPRETATION_LABEL}
              <PhaseSourceBadge source="advisory" />
            </>
          }
        />
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

      {phase2ConsistencyReport &&
        phase2ConsistencyReport.violations.some((v) => v.audience !== 'dev') && (
          <section
            data-testid="consistency-report"
            className="space-y-3 rounded-sm border border-border bg-bg-card p-4"
          >
            <h2 className="text-sm font-mono uppercase tracking-wider text-text-primary">
              Chain-of-Custody Check
            </h2>
            <Phase2ConsistencyReport report={phase2ConsistencyReport} hideWhenClean />
          </section>
        )}

      {groupedValidationWarnings.length > 0 && (
        <section
          data-testid="interpretation-warnings"
          className={`space-y-3 rounded-sm border p-4 ${
            isMixed
              ? 'border-border bg-bg-card'
              : allValidationWarningsAreAdjustments
                ? 'border-accent/25 bg-bg-card'
                : 'border-warning/25 bg-bg-card'
          }`}
        >
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2
                className={`text-sm font-mono uppercase tracking-wider ${
                  isMixed
                    ? 'text-text-primary'
                    : allValidationWarningsAreAdjustments ? 'text-accent' : 'text-warning'
                }`}
              >
                {isMixed
                  ? 'Interpretation Notes'
                  : allValidationWarningsAreAdjustments ? 'Interpretation Adjustments' : 'Interpretation Caution'}
              </h2>
              <p
                className={`text-[10px] font-mono uppercase tracking-[0.16em] ${
                  isMixed
                    ? 'text-text-secondary'
                    : allValidationWarningsAreAdjustments ? 'text-accent/80' : 'text-warning/80'
                }`}
              >
                {isMixed
                  ? 'The backend made auto-corrections and flagged parts that may need review.'
                  : allValidationWarningsAreAdjustments
                    ? 'The backend kept the result and auto-corrected a few AI-generated labels so they match the detected session structure.'
                    : 'The backend kept the result, but flagged parts that may not match the approved Live catalog.'}
              </p>
            </div>
            <span
              className={`text-[10px] font-mono uppercase px-2 py-1 rounded border ${
                isMixed
                  ? 'border-border text-text-secondary'
                  : allValidationWarningsAreAdjustments
                    ? 'border-accent/30 text-accent'
                    : 'border-warning/30 text-warning'
              }`}
            >
              {isMixed
                ? `${adjustmentCount} adjustment${adjustmentCount === 1 ? '' : 's'} · ${warningCount} warning${warningCount === 1 ? '' : 's'}`
                : allValidationWarningsAreAdjustments
                  ? `${adjustmentCount} item${adjustmentCount === 1 ? '' : 's'}`
                  : `${warningCount} warning${warningCount === 1 ? '' : 's'}`}
            </span>
          </div>
          <div className="space-y-2">
            {(isMixed ? [...adjustmentGroups, ...warningGroups] : groupedValidationWarnings).map((warning) => (
              <div
                key={warning.key}
                className={`rounded-sm border p-3 space-y-2 ${
                  warning.tone === 'adjustment'
                    ? 'border-accent/20 bg-bg-panel'
                    : 'border-warning/20 bg-bg-panel'
                }`}
              >
                <div className="flex flex-wrap gap-1.5">
                  {warning.code && (
                    <span
                      className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border ${
                        warning.tone === 'adjustment'
                          ? 'border-accent/30 text-accent'
                          : 'border-warning/30 text-warning'
                      }`}
                    >
                      {warning.code}
                    </span>
                  )}
                  {warning.count > 1 && (
                    <span
                      className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border ${
                        warning.tone === 'adjustment'
                          ? 'border-accent/25 text-accent/90'
                          : 'border-warning/25 text-warning/90'
                      }`}
                    >
                      {warning.count} items
                    </span>
                  )}
                </div>
                <div className="space-y-1">
                  <p
                    className={`text-[10px] font-mono uppercase tracking-[0.16em] ${
                      warning.tone === 'adjustment' ? 'text-accent/85' : 'text-warning/85'
                    }`}
                  >
                    {warning.title}
                  </p>
                  <p className="text-xs font-mono text-text-secondary leading-relaxed">
                    {warning.message}
                  </p>
                </div>
                {warning.mappings.some((m) => m.originalValue || m.coercedValue || m.path) ? (
                  <div className="space-y-1">
                    {warning.mappings.map((m, mIdx) => (
                      <div
                        key={`${warning.key}-mapping-${mIdx}`}
                        className="flex flex-wrap items-center gap-1.5 text-[9px] font-mono text-text-secondary"
                      >
                        {(m.originalValue || m.coercedValue) && (
                          <>
                            {/* Audit Finding #1C: render compact human summary
                              for JSON-shaped values (dropped recommendations)
                              instead of dumping the raw object. See
                              `formatDroppedValue` near the top of the file. */}
                            <span className="px-1.5 py-0.5 rounded border border-border">
                              {formatDroppedValue(m.originalValue)}
                            </span>
                            <span className="opacity-50">→</span>
                            <span className="px-1.5 py-0.5 rounded border border-border">
                              {formatDroppedValue(m.coercedValue)}
                            </span>
                          </>
                        )}
                        {m.path && (
                          <span className="px-1.5 py-0.5 rounded border border-border opacity-70">
                            {m.path}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-border text-text-secondary">
                      Result-level warning
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {confidenceBadges.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 px-1">
          {/* Audit Finding #4: chips used to render "{label}: High|Moderate|Low"
            with bespoke success/warning/error tones. Now route through the
            canonical band ladder so the same vocabulary (Solid / Workable /
            Rough / Unreliable) appears across every confidence surface.
            Filter null bands (unparseable values) rather than render a
            misleading default. */}
          {confidenceBadges.map((badge, idx) =>
            badge.band ? (
              <span key={`${badge.label}-${idx}`} className="inline-flex items-center gap-2">
                <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary/80">
                  {badge.label}:
                </span>
                <ConfidenceBandBadge variant="compact" band={badge.band} />
              </span>
            ) : null,
          )}
        </div>
      )}

      {phase2?.trackCharacter && (
        <section className="space-y-3">
          <ResultsSectionHeader
            title={formatDisplayText('Track Character', 'title')}
            titleRole="section-title"
            rightSlot={
              <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">AI INTERP</span>
            }
          />
          <p data-text-role="body" className={textRoleClassName('body', 'opacity-80')}>
            {truncateAtSentenceBoundary(phase2.trackCharacter, 900)}
          </p>
        </section>
      )}

      <section id="section-style-profile" className="space-y-6 scroll-mt-24">
        <ResultsSectionHeader
          title="Style Profile"
          rightSlot={
            styleProfileSectionState === 'ready' ? (
              <span className="text-[10px] font-mono bg-bg-panel border border-accent/30 text-accent px-2 py-1 rounded font-bold">
                STRUCTURED
              </span>
            ) : (
              <span className="text-[10px] font-mono bg-bg-panel border border-border text-text-secondary px-2 py-1 rounded font-bold">
                {styleProfileSectionState === 'disabled'
                  ? 'DISABLED'
                  : styleProfileSectionState === 'pending'
                    ? 'PENDING'
                    : styleProfileSectionState === 'omitted'
                      ? 'NOT RETURNED'
                      : 'DROPPED'}
              </span>
            )
          }
        />

        {styleProfile ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <AccentMetricCard
                label="Tempo"
                value={styleProfile.authoritativeMeasurements.bpm ?? '—'}
                unit={styleProfile.authoritativeMeasurements.bpm != null ? 'BPM' : undefined}
              />
              <AccentMetricCard
                label="Key"
                value={styleProfile.authoritativeMeasurements.key ?? '—'}
              />
              <AccentMetricCard
                label="Meter"
                value={styleProfile.authoritativeMeasurements.timeSignature ?? '—'}
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="rounded-sm border border-border bg-bg-card p-4 space-y-3">
                <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
                  Genre
                </p>
                <div className="flex flex-wrap gap-1.5">
                  <span className="text-[10px] font-mono rounded-sm border border-accent/30 bg-accent/5 px-2 py-1 text-accent">
                    {styleProfile.genre}
                  </span>
                  {styleProfile.subGenre && (
                    <span className="text-[10px] font-mono rounded-sm border border-border px-2 py-1 text-text-secondary">
                      {styleProfile.subGenre}
                    </span>
                  )}
                </div>
                {styleProfile.mood.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
                      Mood
                    </p>
                    <TokenBadgeList
                      items={styleProfile.mood.map((item) => ({ label: item, tone: 'accent' as const }))}
                    />
                  </div>
                )}
              </div>

              <div className="rounded-sm border border-border bg-bg-card p-4 space-y-3">
                {styleProfile.instruments.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
                      Instruments
                    </p>
                    <TokenBadgeList
                      items={styleProfile.instruments.map((item) => ({ label: item, tone: 'muted' as const }))}
                    />
                  </div>
                )}
                {styleProfile.productionTechniques.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
                      Production Techniques
                    </p>
                    <TokenBadgeList
                      items={styleProfile.productionTechniques.map((item) => ({ label: item, tone: 'violet' as const }))}
                    />
                  </div>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="rounded-sm border border-border bg-bg-card p-4 space-y-2">
                <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary">
                  Style Read
                </p>
                <p className="text-xs font-mono text-text-secondary leading-relaxed">
                  {truncateAtSentenceBoundary(styleProfile.description, 320)}
                </p>
              </div>
              <div className="rounded-sm border border-accent/20 bg-accent/5 p-4 space-y-2">
                <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-accent">
                  Reusable Prompt
                </p>
                <p className="text-xs font-mono text-text-secondary leading-relaxed">
                  {truncateAtSentenceBoundary(styleProfile.generationPrompt, 320)}
                </p>
              </div>
            </div>
          </>
        ) : (
          <div className="rounded-sm border border-border bg-bg-card p-4 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary">
                {styleProfileSectionState === 'disabled'
                  ? 'DISABLED'
                  : styleProfileSectionState === 'pending'
                    ? 'PENDING'
                    : styleProfileSectionState === 'omitted'
                      ? 'NOT RETURNED'
                      : 'DROPPED'}
              </span>
            </div>
            <p className="text-xs font-mono text-text-secondary leading-relaxed">
              {styleProfileSectionState === 'disabled'
                ? 'AI interpretation was disabled for this run, so no style profile was generated.'
                : styleProfileSectionState === 'pending'
                  ? 'Style profile is not ready yet. AI interpretation is still running or did not finish with a usable result.'
                  : styleProfileSectionState === 'omitted'
                    ? 'AI interpretation completed, but this run did not return a structured style profile.'
                    : 'The model returned an invalid style profile, so ASA ignored it. See interpretation warnings above.'}
            </p>
            {styleProfileSectionState === 'disabled' && phase2StatusMessage && (
              <p className="text-[10px] font-mono uppercase tracking-[0.16em] text-text-secondary/80">
                {phase2StatusMessage}
              </p>
            )}
          </div>
        )}
      </section>

      {audioObservations && (
        <section id="section-audio-observations" className="space-y-6 scroll-mt-24">
          <ResultsSectionHeader
            title="Audio Observations"
            rightSlot={
              <span className="text-[10px] font-mono bg-bg-panel border border-border text-text-secondary px-2 py-1 rounded font-bold">
                Perceptual / Audio-Derived
              </span>
            }
          />

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
          <ResultsSectionHeader
            title="Project Setup"
            rightSlot={
              <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">
                LIVE 12 V2
              </span>
            }
          />

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
          <ResultsSectionHeader
            title="Track Layout"
            rightSlot={
              <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">
                SCAFFOLD
              </span>
            }
          />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {trackLayout.map((item) => (
              <div key={`${item.order}-${item.name}`} className="rounded-sm border border-border bg-bg-card p-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="w-6 h-6 rounded-sm bg-bg-panel border border-border text-accent font-mono text-[10px] flex items-center justify-center">
                      {item.order}
                    </span>
                    <div className="min-w-0">
                      <h3
                        data-text-role="item-title"
                        className={textRoleClassName('item-title', 'truncate')}
                      >
                        {item.name}
                      </h3>
                      <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
                        {item.type}
                      </p>
                    </div>
                  </div>
                </div>
                <p data-text-role="body" className={textRoleClassName('body')}>
                  {truncateAtSentenceBoundary(item.purpose, 220)}
                </p>
                {/* Audit Finding #2: replaced the legacy GroundingBadgeList
                    (9px field-path pills) with the structured CitationBlock
                    primitive, finishing the chain-of-custody visual treatment
                    that already lands on Mix Chain / Patches / Sonic cards.
                    Segment indexes (Track Layout-only) ride as a synthetic
                    extra row at the bottom of the block. */}
                <CitationBlock
                  phase1={phase1}
                  fields={item.grounding.phase1Fields}
                  extraRows={
                    Array.isArray(item.grounding.segmentIndexes) &&
                    item.grounding.segmentIndexes.length > 0
                      ? [
                          {
                            label: 'Active in segments',
                            value: item.grounding.segmentIndexes.join(' · '),
                          },
                        ]
                      : undefined
                  }
                  testId={`track-layout-citation-${item.order ?? 0}-${item.name}`}
                />
              </div>
            ))}
          </div>
        </section>
      )}

      {routingBlueprint && (
        <section id="section-routing-blueprint" className="space-y-6 scroll-mt-24">
          <ResultsSectionHeader
            title="Routing Blueprint"
            rightSlot={
              <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">
                SIGNAL MAP
              </span>
            }
          />

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="rounded-sm border border-border bg-bg-card p-4 space-y-2">
              <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>Sidechain Source</p>
              <p data-text-role="item-title" className={getTextRoleClassName('item-title')}>
                {routingBlueprint.sidechainSource ?? 'Not specified'}
              </p>
            </div>
            <div className="rounded-sm border border-border bg-bg-card p-4 space-y-2 md:col-span-2">
              <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>Sidechain Targets</p>
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
                    <h3 data-text-role="item-title" className={getTextRoleClassName('item-title')}>
                      {returnTrack.name}
                    </h3>
                    <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary">
                      {returnTrack.deviceFocus}
                    </span>
                  </div>
                  <p data-text-role="body" className={textRoleClassName('body')}>
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
          <ResultsSectionHeader
            title="Warp Guide"
            rightSlot={
              <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">
                CLIP PREP
              </span>
            }
          />

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
          <ResultsSectionHeader
            title="Detected Characteristics"
            rightSlot={
              <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">AI INTERP</span>
            }
          />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {phase2.detectedCharacteristics.map((item, idx) => (
              <div
                key={idx}
                className="bg-bg-card border rounded-sm p-4 flex flex-col transition-all hover:border-accent/40 group relative overflow-hidden border-accent/30"
              >
                <div className="absolute top-0 left-0 w-1 h-full bg-accent"></div>
                <div className="flex items-center justify-between mb-3 pl-2">
                  <h3
                    data-text-role="item-title"
                    className={textRoleClassName('item-title', 'truncate pr-2')}
                  >
                    {item.name}
                  </h3>
                  {/* Audit Finding #4: Detected Characteristics cards used
                    to render a HIGH/MED/LOW string pill with bespoke
                    success/warning/error tones. Replaced with the canonical
                    ConfidenceBandBadge so the same vocabulary (Solid /
                    Workable / Rough / Unreliable) reads across every
                    confidence surface in the UI. toConfidenceBand maps
                    Gemini's HIGH→solid (0.9), MED→workable (0.6),
                    LOW→rough (0.3) — middle of each band so the percent
                    label reads as an honest hedge. */}
                  {(() => {
                    const band = toConfidenceBand(item.confidence);
                    return band ? (
                      <ConfidenceBandBadge variant="compact" band={band} />
                    ) : null;
                  })()}
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
          <ResultsSectionHeader
            title="Arrangement Overview"
            rightSlot={
              <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">TIMELINE</span>
            }
          />

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

      {/* Pair the note-draft panel and the Gemini stem listening notes visually.
          The parent motion container uses space-y-12; this local space-y-4 wrapper
          tightens the gap between Session Musician and Stem Notes so they read
          as a paired suite. The StickyNav anchor IDs stay on the inner divs. */}
      <div id="section-musician-suite" className="space-y-4">
        <div id="section-session" className="scroll-mt-24">
          <SessionMusicianPanel
            phase1={phase1}
            sourceFileName={sourceFileName}
            pitchNoteMode={pitchNoteMode}
            hasStemListeningNotes={hasStemSummaryContent}
            onReanalyzeWithStemAware={onReanalyzeWithStemAware}
          />
        </div>

        {apiBaseUrl &&
          runId &&
          phase1.transcriptionDetail &&
          phase1.transcriptionDetail.noteCount > 0 && (
            <div id="section-pianoroll" className="scroll-mt-24">
              <TranscriptionPianorollBlock apiBaseUrl={apiBaseUrl} runId={runId} />
            </div>
          )}

        {apiBaseUrl && runId && mt3Transcription && (
          <div id="section-mt3" className="scroll-mt-24">
            <Mt3TranscriptionPanel
              result={mt3Transcription}
              apiBaseUrl={apiBaseUrl}
              runId={runId}
            />
          </div>
        )}

        {hasStemSummaryContent && (
          <div id="section-stem-summary" className="scroll-mt-24">
            <StemListeningNotesPanel stemSummary={stemSummary} />
          </div>
        )}
      </div>

      {sonicCards.length > 0 && (
        <section id="section-sonic-elements" className="space-y-6 scroll-mt-24">
          <ResultsSectionHeader
            title={formatDisplayText('Sonic Elements & Reconstruction', 'title')}
            titleRole="section-title"
            rightSlot={
              <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">COLLAPSIBLE</span>
            }
          />

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
                          <h3
                            data-text-role="item-title"
                            className={textRoleClassName('item-title', 'truncate')}
                          >
                            {card.title}
                          </h3>
                          {card.id === 'harmonicContent' && lowConfidenceIndicator(chordsAreApproximate)}
                          {card.transcriptionDerived && (
                            <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-accent/40 text-accent whitespace-nowrap">
                              Transcription-derived
                            </span>
                          )}
                        </div>
                        {/* Audit Finding #3: primary citation visible in the
                          collapsed header. Mirrors the Mix Chain / Patch
                          placement so all three card types feel parallel. */}
                        {card.phase1Fields.length > 0 && (
                          <div className="mt-1 flex min-w-0">
                            <CitationHeadline
                              phase1={phase1}
                              field={card.phase1Fields[0]}
                              testId={`sonic-headline-${card.id}`}
                            />
                          </div>
                        )}
                        <p data-text-role="body" className={textRoleClassName('body', 'mt-1 truncate')}>
                          {card.summary}
                        </p>
                      </div>
                      <span className="text-text-secondary">
                        {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                      </span>
                    </div>
                  </button>

                  <Collapsible isOpen={isOpen}>
                    <div className="p-4 space-y-3">
                      {/* Audit Finding #2 + #3: chain-of-custody block at the
                          TOP of the expanded card so the producer sees the
                          measurements + worst-confidence band BEFORE reading
                          the prose description. */}
                      <CitationBlock
                        phase1={phase1}
                        fields={card.phase1Fields}
                        testId={`sonic-citation-${card.id}`}
                      />

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <p data-text-role="body" className={textRoleClassName('body')}>
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
          <ResultsSectionHeader
            title={formatDisplayText('Mix & Master Chain', 'title')}
            titleRole="section-title"
            rightSlot={
              <div className="flex items-center gap-2">
                {/* Audit Finding #14: section-level progress glance. Only
                    surfaces when the tracker is wired (audioContentHash
                    available) AND at least one card has been applied —
                    avoids leading with a "0 of N" on first view. */}
                {audioContentHash && mixAppliedCount > 0 && (
                  <Pill
                    tone="success"
                    size="sm"
                    data-testid="mix-chain-applied-progress"
                  >
                    {mixAppliedCount} of {mixCardCount} applied
                  </Pill>
                )}
                <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">SIGNAL FLOW</span>
              </div>
            }
          />

          <div className="space-y-4">
            {mixGroups
              .filter((group) => group.cards.length > 0)
              .map((group) => (
              <DeviceRack
                key={group.name}
                // The DeviceRack title strip carries the group name. The
                // emoji-or-SVG from groupIcon() + uppercase group.name
                // ("DRUM PROCESSING" etc.) are preserved verbatim so
                // analysisResultsUi.test.ts:441-450 selectors (toContain
                // ('🥁 DRUM PROCESSING')) AND the BASS PROCESSING test at
                // :448 which expects a `lucide-audio-waveform` SVG class
                // nearby both pass. The name must be a React fragment —
                // template-literal coercion turns the AudioWaveform JSX
                // node into "[object Object]" and the SVG is lost.
                name={
                  <>
                    {groupIcon(group.name)} {group.name}
                  </>
                }
                status="idle"
              >
                {/* Audit-preserved annotation paragraph kept here so
                    data-text-role="body" presence assertions
                    (analysisResultsUi.test.ts:474) stay green. */}
                {group.annotation && (
                  <p
                    data-text-role="meta"
                    className={textRoleClassName('meta', 'mb-3')}
                  >
                    {group.annotation}
                  </p>
                )}

                {/* Keep this exact className — the brittle assertion
                    analysisResultsUi.test.ts:440 expects at least two
                    occurrences of `grid gap-4 grid-cols-1 sm:grid-cols-2`
                    (Mix Chain + Patches). */}
                <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
                  {group.cards.map((card) => {
                    const isOpen = !!openMix[card.id];
                    const isApplied = appliedIds.has(card.id);
                    return (
                      <div
                        key={card.id}
                        data-applied={isApplied || undefined}
                        className={`bg-bg-card border border-border rounded-sm overflow-hidden self-start transition-colors hover:border-accent/40 hover:bg-bg-card-hover/70 ${
                          isApplied ? 'border-l-2 border-l-success' : ''
                        }`}
                      >
                        <button
                          onClick={() => toggleMix(card.id)}
                          className="w-full text-left px-4 py-3 border-b border-border bg-bg-panel/60 hover:bg-bg-panel transition-colors"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="min-w-0">
                              {/* Audit quick-hit: order badges (`{card.order}`)
                                used to render as small numbered chips next to
                                each device. Because the cards are grouped by
                                processing stage AFTER ordering, the numbers
                                appeared out-of-order within each group ("1, 6,
                                8, 9 / 2, 4 / 5, 7 / 3 / 10"), which read as
                                a presentation bug. The visual sequence within
                                each group is already meaningful — the badge
                                added confusion without information. Dropped. */}
                              <div className="flex items-center gap-2">
                                <h4
                                  data-text-role="item-title"
                                  className={textRoleClassName('item-title', 'truncate')}
                                >
                                  {card.device}
                                </h4>
                                <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary whitespace-nowrap">
                                  {card.category}
                                </span>
                                <RecommendationVerificationBadge
                                  trackContext={card.trackContext}
                                  category={card.category}
                                />
                              </div>
                              {/* Audit Finding #3: primary citation visible in
                                the collapsed header so the chain-of-custody
                                evidence isn't gated behind expansion. The
                                expanded CitationBlock below still carries the
                                full multi-row list. */}
                              {card.phase1Fields.length > 0 && (
                                <div className="mt-1 flex min-w-0">
                                  <CitationHeadline
                                    phase1={phase1}
                                    field={card.phase1Fields[0]}
                                    testId={`mix-chain-headline-${card.id}`}
                                  />
                                </div>
                              )}
                              <p data-text-role="body" className={textRoleClassName('body', 'mt-1 truncate')}>
                                {card.role}
                              </p>
                              <div className="mt-2">
                                <MetaBadgeList
                                  items={[
                                    // Audit N3/N8: drop `Family: Native` from
                                    // the collapsed card. `deviceFamily` is
                                    // almost always `NATIVE`; keeping it
                                    // burns chip-row real estate without
                                    // adding signal. Surfaces only the two
                                    // chips that actually vary per card.
                                    { label: 'Context', value: card.trackContext },
                                    { label: 'Stage', value: card.workflowStage },
                                  ]}
                                />
                              </div>
                            </div>
                            <div className="flex items-center gap-2 flex-shrink-0">
                              {audioContentHash && (
                                <AppliedCheckbox
                                  isApplied={isApplied}
                                  onToggle={() => toggleApplied(card.id)}
                                  ariaLabel={`Mark ${card.device} as applied`}
                                />
                              )}
                              <span className="text-text-secondary">
                                {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                              </span>
                            </div>
                          </div>
                        </button>

                        <Collapsible isOpen={isOpen}>
                          <div className="p-4 space-y-3">
                            {/* Audit Finding #2 + #3: structured chain-of-custody
                                evidence at the top of the expanded card. */}
                            <CitationBlock
                              phase1={phase1}
                              fields={card.phase1Fields}
                              testId={`mix-chain-citation-${card.id}`}
                            />
                            <p data-text-role="body" className={textRoleClassName('body')}>
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
              </DeviceRack>
            ))}
          </div>
        </section>
      )}

      {patchCards.length > 0 && (
        <section id="section-patches" className="space-y-6 scroll-mt-24">
          <ResultsSectionHeader
            title={formatDisplayText('Patch Framework', 'title')}
            titleRole="section-title"
            rightSlot={
              <div className="flex items-center gap-2">
                {audioContentHash && patchAppliedCount > 0 && (
                  <Pill
                    tone="success"
                    size="sm"
                    data-testid="patches-applied-progress"
                  >
                    {patchAppliedCount} of {patchCards.length} applied
                  </Pill>
                )}
                <Sliders className="w-4 h-4 text-accent opacity-70" />
              </div>
            }
          />

          {/* Audit follow-up: cards grouped by processing stage (Drum / Bass /
              Synth / Mid / High-end / Master) using the same heuristic and
              emoji eyebrows as Mix Chain above. Producers can now jump to the
              bass patch without scanning all 8 cards. */}
          <div className="space-y-4">
            {patchGroups.map((group) => (
              <DeviceRack
                key={group.name}
                // Mirror Mix Chain's D.5b shape. JSX fragment (not template
                // literal) so groupIcon's BASS PROCESSING return value (an
                // <AudioWaveform> SVG) renders as a real React node — the
                // template-literal version stringifies it to "[object
                // Object]" and analysisResultsUi.test.ts:448 fails.
                name={
                  <>
                    {groupIcon(group.name)} {group.name}
                  </>
                }
                status="idle"
              >
                {/* Keep the exact className — analysisResultsUi.test.ts:440
                    expects ≥2 occurrences of `grid gap-4 grid-cols-1
                    sm:grid-cols-2` across Mix Chain + Patches. */}
                <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
                  {group.cards.map((patch) => {
                    const isOpen = !!openPatch[patch.id];
                    const isApplied = appliedIds.has(patch.id);
                    return (
                      <div
                        key={patch.id}
                        data-applied={isApplied || undefined}
                        className={`bg-bg-card border border-border rounded-sm overflow-hidden self-start transition-colors hover:border-accent/40 hover:bg-bg-card-hover/70 ${
                          isApplied ? 'border-l-2 border-l-success' : ''
                        }`}
                      >
                        <button
                          onClick={() => togglePatch(patch.id)}
                          className="w-full text-left px-4 py-3 border-b border-border bg-bg-panel/60 hover:bg-bg-panel transition-colors"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <Settings2 className="w-4 h-4 text-accent" />
                                <h4
                                  data-text-role="item-title"
                                  className={textRoleClassName('item-title', 'truncate')}
                                >
                                  {patch.device}
                                </h4>
                                {patch.transcriptionDerived && (
                                  <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-accent/40 text-accent whitespace-nowrap">
                                    Transcription-derived
                                  </span>
                                )}
                                <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-border text-text-secondary whitespace-nowrap">
                                  {patch.category}
                                </span>
                                <RecommendationVerificationBadge
                                  trackContext={patch.trackContext}
                                  category={patch.category}
                                />
                              </div>
                              {/* Audit Finding #3: primary citation in the
                                collapsed header so the chain-of-custody
                                evidence is visible without expanding. */}
                              {patch.phase1Fields.length > 0 && (
                                <div className="mt-1 flex min-w-0">
                                  <CitationHeadline
                                    phase1={phase1}
                                    field={patch.phase1Fields[0]}
                                    testId={`patch-headline-${patch.id}`}
                                  />
                                </div>
                              )}
                              {/* Audit Finding #1B: the per-card patchRole
                                paragraph used to render a duplicated
                                category-keyed placeholder ("Primary tone
                                generator" on every SYNTHESIS card). It has been
                                removed; the category chip above carries the
                                bucket and `whyThisWorks` (inside the expanded
                                card body) carries the actionable explanation. */}
                              <div className="mt-2">
                                <MetaBadgeList
                                  items={[
                                    // Same Family-chip drop as Mix Chain cards (audit N3/N8).
                                    { label: 'Context', value: patch.trackContext },
                                    { label: 'Stage', value: patch.workflowStage },
                                  ]}
                                />
                              </div>
                            </div>
                            <div className="flex items-center gap-2 flex-shrink-0">
                              {audioContentHash && (
                                <AppliedCheckbox
                                  isApplied={isApplied}
                                  onToggle={() => toggleApplied(patch.id)}
                                  ariaLabel={`Mark ${patch.device} patch as applied`}
                                />
                              )}
                              <span className="text-text-secondary">
                                {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                              </span>
                            </div>
                          </div>
                        </button>

                        <Collapsible isOpen={isOpen}>
                          <div className="p-4 space-y-3">
                            {/* Audit Finding #2 + #3: chain-of-custody block
                                at the top of the expanded patch card. */}
                            <CitationBlock
                              phase1={phase1}
                              fields={patch.phase1Fields}
                              testId={`patch-citation-${patch.id}`}
                            />
                            <p data-text-role="body" className={textRoleClassName('body')}>
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
              </DeviceRack>
            ))}
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
              <h2
                data-text-role="section-title"
                className={textRoleClassName('section-title', 'text-accent')}
              >
                {formatDisplayText('Secret Sauce Protocol', 'title')}
              </h2>
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
                <h3
                  data-text-role="item-title"
                  className={[getTextRoleClassName('item-title'), 'text-lg'].join(' ')}
                >
                  {phase2.secretSauce.title}
                </h3>
                <p data-text-role="body" className={textRoleClassName('body', 'max-w-3xl border-l-2 border-accent/30 pl-4')}>
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
                          <p
                            data-text-role="item-title"
                            className={textRoleClassName('item-title', 'truncate')}
                          >
                            {step.device}
                          </p>
                          <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
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

      {/* Audit Finding #1: measurements section moved to the end of the scroll.
          Wrapped in a single anchorable <section> so the StickyNav can target
          it with one pill ("Measurements") instead of nine pills. The internal
          MeasurementDashboard still renders its 9 numbered sub-sections, each
          with their own scroll anchor; only the top-level nav collapses. */}
      <section
        id="section-measurements"
        data-testid="measurements-section"
        className="space-y-6 scroll-mt-24"
      >
        <MeasurementDashboard
          phase1={phase1}
          spectralArtifacts={spectralArtifacts}
          measurementAvailability={measurementAvailability}
          apiBaseUrl={apiBaseUrl}
          runId={runId}
        />
      </section>
      {apiBaseUrl && runId && (
        <SamplePlayback
          runId={runId}
          apiBaseUrl={apiBaseUrl}
          measurementCompleted={Boolean(phase1)}
        />
      )}
      {isBrowserLoudnessConfigEnabled() && phase1 && (
        <BrowserLoudnessPanel phase1={phase1} audioFile={audioFile} className="mt-6" />
      )}
    </motion.div>
  );
}

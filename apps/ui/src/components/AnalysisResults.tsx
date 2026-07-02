import React, { useCallback, useEffect, useState } from 'react';
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
import { FileJson, FileText } from 'lucide-react';
import { motion } from 'motion/react';
import { assertNever } from '../utils/assertNever';
import { downloadFile, generateMarkdown } from '../utils/exportUtils';
import type { ValidationReport } from '../services/phase2Validator';
import { Phase2ConsistencyReport } from './Phase2ConsistencyReport';
import { isBrowserLoudnessConfigEnabled } from '../config';
import { BrowserLoudnessPanel } from './BrowserLoudnessPanel';
import { MeasurementDashboard } from './MeasurementDashboard';
import { ReconstructionContractPanel } from './ReconstructionContractPanel';
import { PatchSmithPanel } from './PatchSmithPanel';
import { SamplePlayback } from './SamplePlayback';
import { SessionMusicianPanel } from './SessionMusicianPanel';
import { TranscriptionPianorollBlock } from './TranscriptionPianorollBlock';
import { Mt3TranscriptionPanel } from './Mt3TranscriptionPanel';
import { StemListeningNotesPanel } from './StemListeningNotesPanel';
import { hasStemListeningNotesContent } from '../services/sessionMusician';
import { Button, SectionHeader } from './ui';
import { StickyNav, type StickyNavSection } from './StickyNav';
import { ConfidenceBandBadge } from './sessionMusician/ConfidenceBandBadge';
import { loadAppliedIds, toggleAppliedId } from '../services/appliedRecommendations';
import {
  buildArrangementViewModel,
  buildMixChainGroups,
  buildPatchCards,
  buildPatchGroups,
  buildSonicElementCards,
  toConfidenceBadges,
} from './analysisResultsViewModel';
import {
  formatDisplayText,
  getTextRoleClassName,
  type TextRole,
} from '../utils/displayText';
import { Collapsible, textRoleClassName, type StyleProfileSectionState } from './analysisResults/shared';
import { NotableFindingsSection } from './analysisResults/NotableFindingsSection';
import { ReconstructionBriefSection } from './analysisResults/ReconstructionBriefSection';
import { MeasurementSummarySection } from './analysisResults/MeasurementSummarySection';
import { AudioObservationsSection } from './analysisResults/AudioObservationsSection';
import { ProjectSetupSection } from './analysisResults/ProjectSetupSection';
import { TrackLayoutSection } from './analysisResults/TrackLayoutSection';
import { RoutingBlueprintSection } from './analysisResults/RoutingBlueprintSection';
import { WarpGuideSection } from './analysisResults/WarpGuideSection';
import { DetectedCharacteristicsSection } from './analysisResults/DetectedCharacteristicsSection';
import { InterpretationPanel } from './analysisResults/InterpretationPanel';
import { ConfidencePillRow } from './analysisResults/ConfidencePillRow';
import { TrackCharacterSection } from './analysisResults/TrackCharacterSection';
import { SecretSauceSection } from './analysisResults/SecretSauceSection';
import { StyleProfileSection } from './analysisResults/StyleProfileSection';
import { InterpretationWarningsSection } from './analysisResults/InterpretationWarningsSection';
import { SonicElementsSection } from './analysisResults/SonicElementsSection';
import { ArrangementOverviewSection } from './analysisResults/ArrangementOverviewSection';
import { MixChainSection } from './analysisResults/MixChainSection';
import { PatchFrameworkSection } from './analysisResults/PatchFrameworkSection';

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
          <span className="text-meta uppercase tracking-wide text-text-secondary/50">Based on:</span>
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

// Audit Finding #2: `GroundingBadgeList` (9px monospace field-path pills) was
// retired in favor of the structured `CitationBlock` primitive. The component
// previously lived here and rendered raw field paths like `bpmConfidence` as
// orange-accent pills. Track Layout — its only call site — now uses
// CitationBlock with the segmentIndexes routed through the `extraRows` prop.

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

  const confidenceBadges = toConfidenceBadges(phase2?.confidenceNotes);
  const arrangement = buildArrangementViewModel(phase1, phase2?.arrangementOverview);
  const sonicCards = buildSonicElementCards(phase1, phase2?.sonicElements);
  const mixGroups = buildMixChainGroups(
    phase1,
    phase2?.mixAndMasterChain,
    phase2?.sonicElements,
    phase2?.recommendations,
  );
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

      <NotableFindingsSection phase1={phase1} />

      <ReconstructionBriefSection phase1={phase1} />

      <MeasurementSummarySection
        phase1={phase1}
        finalBpm={finalBpm}
        finalKey={finalKey}
        keyIsApproximate={keyIsApproximate}
        characteristicPills={characteristicPills}
      />

      {/* Audit Finding #1: MeasurementDashboard was here at the top of the
          results scroll, ahead of Style / Sonic Elements / Mix Chain / Patches.
          That ordering serves a DSP engineer auditing the tool, not a producer
          asking "how do I make something that sounds like this?". The dashboard
          now renders at the bottom (search for `section-measurements` below
          Patches/Secret Sauce) so the actionable Phase 2 content reads first
          and the measurement evidence reads as drill-down. */}

      <InterpretationPanel
        phase2StatusMessage={phase2StatusMessage}
        hasPhase2={Boolean(phase2)}
        hasRenderablePhase2Content={hasRenderablePhase2Content}
      />

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

      <InterpretationWarningsSection validationWarnings={validationWarnings} />

      {confidenceBadges.length > 0 && (
        <ConfidencePillRow confidenceBadges={confidenceBadges} />
      )}

      {phase2?.trackCharacter && (
        <TrackCharacterSection trackCharacter={phase2.trackCharacter} />
      )}

      <StyleProfileSection
        styleProfile={styleProfile}
        styleProfileSectionState={styleProfileSectionState}
        phase2StatusMessage={phase2StatusMessage}
      />

      {audioObservations && (
        <AudioObservationsSection audioObservations={audioObservations} />
      )}

      {projectSetup && (
        <ProjectSetupSection projectSetup={projectSetup} />
      )}

      {trackLayout.length > 0 && (
        <TrackLayoutSection trackLayout={trackLayout} phase1={phase1} />
      )}

      {routingBlueprint && (
        <RoutingBlueprintSection routingBlueprint={routingBlueprint} />
      )}

      {warpGuide && (
        <WarpGuideSection warpGuide={warpGuide} />
      )}

      {Array.isArray(phase2?.detectedCharacteristics) && phase2.detectedCharacteristics.length > 0 && (
        <DetectedCharacteristicsSection characteristics={phase2.detectedCharacteristics} />
      )}

      {arrangement && (
        <ArrangementOverviewSection
          arrangement={arrangement}
          openArrangement={openArrangement}
          onToggle={toggleArrangement}
          isPhase2V2={isPhase2V2}
        />
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
        <SonicElementsSection
          sonicCards={sonicCards}
          openSonic={openSonic}
          onToggle={toggleSonic}
          phase1={phase1}
          chordsAreApproximate={chordsAreApproximate}
        />
      )}

      {mixGroups.length > 0 && (
        <MixChainSection
          mixGroups={mixGroups}
          mixAppliedCount={mixAppliedCount}
          mixCardCount={mixCardCount}
          audioContentHash={audioContentHash}
          openMix={openMix}
          onToggle={toggleMix}
          appliedIds={appliedIds}
          onToggleApplied={toggleApplied}
          phase1={phase1}
        />
      )}

      {patchCards.length > 0 && (
        <PatchFrameworkSection
          patchGroups={patchGroups}
          patchAppliedCount={patchAppliedCount}
          patchTotalCount={patchCards.length}
          audioContentHash={audioContentHash}
          openPatch={openPatch}
          onToggle={togglePatch}
          appliedIds={appliedIds}
          onToggleApplied={toggleApplied}
          phase1={phase1}
        />
      )}

      {phase2?.secretSauce && (
        <SecretSauceSection secretSauce={phase2.secretSauce} isPhase2V2={isPhase2V2} />
      )}

      {isPhase2V2 && <ReconstructionContractPanel contract={phase2?.recommendations} />}

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
      {phase1 && <PatchSmithPanel phase1={phase1} className="mt-6" />}
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

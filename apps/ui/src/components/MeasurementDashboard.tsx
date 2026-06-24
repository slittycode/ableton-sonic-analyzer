import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import {
  ChromaInteractiveData,
  MeasurementAvailabilityContext,
  OnsetStrengthData,
  Phase1Result,
  SpectralArtifacts,
  SpectralTimeSeriesData,
} from '../types';
import { generateMixDoctorReport } from '../services/mixDoctor';
import {
  fetchChromaInteractiveData,
  fetchOnsetStrengthData,
  fetchSpectralTimeSeries,
  generateSpectralEnhancement,
  SpectralEnhancementKind,
} from '../services/spectralArtifactsClient';
import { getAnalysisRun } from '../services/analysisRunsClient';
import { SpectrogramViewer } from './SpectrogramViewer';
import { SpectralEvolutionChart } from './SpectralEvolutionChart';
import { ChromaHeatmap } from './ChromaHeatmap';
import { MiniHeatmap } from './MiniHeatmap';
import { ConfidenceBandBadge } from './sessionMusician/ConfidenceBandBadge';
import { MixDoctorPanel } from './MixDoctorPanel';
import {
  Button,
  DataTable,
  DeltaBadge,
  DeviceRack,
  MetricBar,
  MetricBarRow,
  MetricTile,
  TokenBadgeList,
} from './ui';
import { Sparkline } from './Sparkline';
import { SpectralCursorProvider } from '../hooks/useSpectralCursorBus';
import { formatDisplayText, getTextRoleClassName } from '../utils/displayText';
import { HarmonyLanes } from './HarmonyLanes';
import { StructureLanes } from './StructureLanes';
import {
  LUFS_METER_GRADIENT,
  PILL_TONE_FOR_LEGACY,
  PLATFORM_REFS,
  SPECTRAL_BALANCE_PALETTE,
  SPECTRAL_ROW_CONFIG,
  type LegacyBadgeTone,
} from './measurementDashboard/lib/constants';
import {
  buildDynamicsTextureCopy,
  formatDuration,
  formatNumber,
  isAssumedMeter,
  isDynamicCharacterObject,
  isTextureCharacterObject,
  lufsToPercent,
  resolveBarCount,
} from './measurementDashboard/lib/formatters';
import {
  MetricRow,
  Section,
  StatusBadge,
  UnavailableMeasurementCard,
} from './measurementDashboard/lib/scaffold';
import {
  BarChart,
  BreathingBpmPulse,
  ComparativeMetricTile,
  HorizontalDominance,
} from './measurementDashboard/lib/charts';
import { RhythmGridPanel } from './measurementDashboard/panels/RhythmGridPanel';
import { SidechainEnvelope } from './measurementDashboard/panels/SidechainEnvelope';
import { EffectsFieldPanel } from './measurementDashboard/panels/EffectsFieldPanel';
import { PhraseStructureTimeline } from './measurementDashboard/panels/PhraseStructureTimeline';

interface MeasurementDashboardProps {
  phase1: Phase1Result;
  spectralArtifacts?: SpectralArtifacts | null;
  measurementAvailability?: MeasurementAvailabilityContext;
  apiBaseUrl?: string;
  runId?: string;
}

export function MeasurementDashboard({
  phase1,
  spectralArtifacts,
  measurementAvailability,
  apiBaseUrl,
  runId,
}: MeasurementDashboardProps) {
  const mixDoctorReport = useMemo(() => generateMixDoctorReport(phase1), [phase1]);

  // Local copy of spectral artifacts — updated after enhancement generation.
  const [localArtifacts, setLocalArtifacts] = useState(spectralArtifacts);
  useEffect(() => setLocalArtifacts(spectralArtifacts), [spectralArtifacts]);

  const [spectralTimeSeries, setSpectralTimeSeries] =
    useState<SpectralTimeSeriesData | null>(null);
  const [onsetData, setOnsetData] = useState<OnsetStrengthData | null>(null);
  const [chromaData, setChromaData] = useState<ChromaInteractiveData | null>(null);
  const [generating, setGenerating] = useState<Set<SpectralEnhancementKind>>(new Set());
  const dynamicCharacter = isDynamicCharacterObject(phase1.dynamicCharacter)
    ? phase1.dynamicCharacter
    : null;
  const textureCharacter = isTextureCharacterObject(phase1.textureCharacter)
    ? phase1.textureCharacter
    : null;
  const dynamicsTextureFallback = useMemo(
    () =>
      buildDynamicsTextureCopy(
        dynamicCharacter || textureCharacter
          ? dynamicCharacter
            ? 'texture'
            : 'dynamics'
          : 'both',
        measurementAvailability,
      ),
    [dynamicCharacter, measurementAvailability, textureCharacter],
  );
  const spectralBalanceStats = useMemo(() => {
    const values = SPECTRAL_ROW_CONFIG.map((row) => phase1.spectralBalance[row.key]);
    return {
      min: Math.min(...values),
      max: Math.max(...values),
    };
  }, [phase1.spectralBalance]);

  // Fetch spectral time-series
  useEffect(() => {
    if (!localArtifacts?.timeSeries || !apiBaseUrl || !runId) {
      setSpectralTimeSeries(null);
      return;
    }
    const controller = new AbortController();
    fetchSpectralTimeSeries(
      apiBaseUrl,
      runId,
      localArtifacts.timeSeries.artifactId,
      { signal: controller.signal },
    )
      .then(setSpectralTimeSeries)
      .catch(() => {});
    return () => controller.abort();
  }, [localArtifacts, apiBaseUrl, runId]);

  // Fetch onset strength data when artifact appears
  useEffect(() => {
    if (!localArtifacts?.onsetStrength || !apiBaseUrl || !runId) {
      setOnsetData(null);
      return;
    }
    const controller = new AbortController();
    fetchOnsetStrengthData(apiBaseUrl, runId, localArtifacts.onsetStrength.artifactId, { signal: controller.signal })
      .then(setOnsetData)
      .catch(() => {});
    return () => controller.abort();
  }, [localArtifacts?.onsetStrength, apiBaseUrl, runId]);

  // Fetch interactive chroma data when artifact appears
  useEffect(() => {
    if (!localArtifacts?.chromaInteractive || !apiBaseUrl || !runId) {
      setChromaData(null);
      return;
    }
    const controller = new AbortController();
    fetchChromaInteractiveData(apiBaseUrl, runId, localArtifacts.chromaInteractive.artifactId, { signal: controller.signal })
      .then(setChromaData)
      .catch(() => {});
    return () => controller.abort();
  }, [localArtifacts?.chromaInteractive, apiBaseUrl, runId]);

  const handleGenerate = useCallback(async (kind: SpectralEnhancementKind) => {
    if (!apiBaseUrl || !runId || generating.has(kind)) return;
    setGenerating((prev) => new Set(prev).add(kind));
    try {
      await generateSpectralEnhancement(apiBaseUrl, runId, kind);
      // Re-fetch the run snapshot to get updated artifact refs
      const snapshot = await getAnalysisRun(runId, { apiBaseUrl });
      if (snapshot.artifacts.spectral) {
        setLocalArtifacts(snapshot.artifacts.spectral);
      }
    } catch {
      // Silently handle — button returns to available state
    } finally {
      setGenerating((prev) => {
        const next = new Set(prev);
        next.delete(kind);
        return next;
      });
    }
  }, [apiBaseUrl, runId, generating]);

  return (
    <DeviceRack name="Measurements" density="dense" status="success">
      <div data-testid="measurement-dashboard" className="space-y-4">
      {/* 1. Core Metrics */}
      <Section id="section-meas-core" number={1} title="Core Metrics">
        {/* Hero Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {/* BPM Tile */}
          {/* Audit N2: reconciled with the executive-summary card above (which
              uses Math.round(phase1.bpm) → integer). Showing the same value
              twice at different precisions ("157" up top, "156.6" here) inside
              one scroll region read as a measurement disagreement to producers.
              Precision is preserved in the Percival sub-label below. */}
          <MetricTile size="xl"
            label="Tempo"
            value={Math.round(phase1.bpm)}
            unit="BPM"
            footer={
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  {/* Audit Finding #4: `SCORE 0.86` badge retired — band pill
                      shows the same hedge in the canonical vocabulary.
                      Cross-Check is an agreement signal (do multiple BPM
                      detectors agree?), orthogonal to confidence — left as-is. */}
                  <ConfidenceBandBadge variant="compact" confidence={phase1.bpmConfidence} />
                  {phase1.bpmAgreement !== undefined && phase1.bpmAgreement !== null && (
                    <StatusBadge
                      label={phase1.bpmAgreement ? 'Cross-Check ✓' : 'Cross-Check ✗'}
                      tone={phase1.bpmAgreement ? 'success' : 'error'}
                      compact
                    />
                  )}
                </div>
                {phase1.bpmDoubletime === true && phase1.bpmRawOriginal != null && (
                  <span className="block text-nano font-mono uppercase tracking-wide text-warning/80">
                    corrected from {formatNumber(phase1.bpmRawOriginal, 1)}
                  </span>
                )}
                {phase1.bpmPercival !== undefined && phase1.bpmPercival !== null && (
                  <span className="block text-nano font-mono uppercase tracking-wide text-text-secondary/50">
                    Percival {formatNumber(phase1.bpmPercival, 1)}
                  </span>
                )}
                {phase1.bpmSource != null && phase1.bpmSource !== 'rhythm_extractor' && (
                  <span className="block text-nano font-mono uppercase tracking-wide text-text-secondary/50">
                    Source {phase1.bpmSource.replace(/_/g, ' ')}
                  </span>
                )}
              </div>
            }
          />

          {/* Key Tile */}
          <MetricTile size="xl"
            label="Key Signature"
            value={<span className="truncate block">{phase1.key || '—'}</span>}
            footer={
              <div className="space-y-2">
                {phase1.keyProfile && (
                  <span className="block text-nano font-mono uppercase tracking-wide text-text-secondary/50">
                    Profile {phase1.keyProfile}
                  </span>
                )}
                <MetricBar value={phase1.keyConfidence} color="var(--color-accent)" glow />
                {/* Audit Finding #4: `CONF X%` retired in favor of the canonical
                    band pill. Same vocabulary as the AnalysisResults Key card. */}
                <ConfidenceBandBadge variant="compact" confidence={phase1.keyConfidence} />
              </div>
            }
          />

          {/* Duration / Format Tile */}
          <MetricTile size="xl"
            label="Duration"
            value={formatDuration(phase1.durationSeconds)}
            unit={phase1.timeSignature}
            footer={(() => {
              const totalBars = resolveBarCount(phase1);
              const gridSegments = Math.min(Math.ceil(totalBars / 4), 24);
              const fullSegments = Math.floor(totalBars / 4);
              const remainder = (totalBars % 4) / 4;
              const meterStatus = isAssumedMeter(phase1) ? 'ASSUMED' : 'DETECTED';
              return (
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <StatusBadge label={meterStatus} tone="muted" compact />
                    <StatusBadge label={`${totalBars} BARS`} tone="accent" compact />
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-nano font-mono uppercase tracking-wide text-text-secondary/60">
                        Arrangement
                      </span>
                      {phase1.sampleRate !== undefined && phase1.sampleRate !== null && (
                        <span className="text-nano font-mono uppercase tracking-wide text-text-secondary/50 tabular-nums">
                          {(phase1.sampleRate / 1000).toFixed(1)} kHz
                        </span>
                      )}
                    </div>
                    <div className="flex gap-[3px] rounded-sm border border-border/30 bg-bg-app/70 p-1">
                      {Array.from({ length: gridSegments }).map((_, i) => (
                        <div
                          key={i}
                          className="h-2 flex-1 rounded-[2px]"
                          style={{
                            background:
                              i < fullSegments
                                ? `linear-gradient(90deg, rgba(255,107,0,${0.42 + (i / Math.max(gridSegments, 1)) * 0.28}), rgba(249,115,22,${0.58 + (i / Math.max(gridSegments, 1)) * 0.22}))`
                                : i === fullSegments && remainder > 0
                                  ? 'linear-gradient(90deg, rgba(255,107,0,0.28), rgba(249,115,22,0.18))'
                                  : 'rgba(255,255,255,0.04)',
                            opacity: i === fullSegments && remainder > 0 ? remainder : 1,
                          }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              );
            })()}
          />
        </div>

        {/* Genre Banner */}
        {phase1.genreDetail && (
          <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <div className={`w-2 h-2 rounded-full bg-accent ${phase1.genreDetail.confidence > 0.8 ? 'animate-pulse' : ''}`} />
                  <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">Genre Classification</span>
                </div>
                <span className="text-lg font-display font-bold text-text-primary capitalize block truncate">
                  {phase1.genreDetail.genre}
                </span>
                <TokenBadgeList
                  className="mt-2"
                  items={[
                    { label: phase1.genreDetail.genreFamily, tone: 'accent' },
                    ...(phase1.genreDetail.secondaryGenre
                      ? [{ label: phase1.genreDetail.secondaryGenre, tone: 'neutral' as const }]
                      : []),
                  ]}
                />
              </div>
              <div className="shrink-0 text-right">
                <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">Conf</span>
                <span className="text-sm font-display font-bold text-text-primary ml-1.5 tabular-nums">
                  {Math.round(phase1.genreDetail.confidence * 100)}%
                </span>
              </div>
            </div>

            {/* Genre fingerprint — top scores as horizontal bars */}
            {phase1.genreDetail.topScores && phase1.genreDetail.topScores.length > 0 && (
              <div className="mt-3 pt-3 border-t border-border/50 space-y-1.5">
                <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">Genre Fingerprint</span>
                <div className="space-y-1">
                  {phase1.genreDetail.topScores.slice(0, 5).map((score, i) => {
                    const maxScore = phase1.genreDetail!.topScores[0]?.score || 1;
                    const pct = (score.score / maxScore) * 100;
                    const color = ['#ff6b00', '#fb923c', '#f59e0b', '#fdba74', '#fed7aa'][i] ?? '#fb923c';
                    return (
                      <div key={`${score.genre}-${i}`} className="flex items-center gap-2">
                        <span className="text-nano font-mono text-text-secondary/70 w-20 truncate text-right capitalize">
                          {score.genre}
                        </span>
                        <MetricBar
                          value={score.score}
                          min={0}
                          max={maxScore}
                          color={color}
                          glow={i === 0}
                          className="flex-1"
                          heightClassName="h-2"
                        />
                        <span className="text-nano font-mono text-text-secondary/50 tabular-nums w-8 text-right">
                          {(score.score * 100).toFixed(0)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tuning Detail */}
        {(phase1.tuningFrequency !== undefined && phase1.tuningFrequency !== null) && (
          <div className="flex items-center gap-3 px-1 flex-wrap">
            <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">Tuning</span>
            <span className="text-micro font-mono text-text-secondary/70 tabular-nums">
              {formatNumber(phase1.tuningFrequency, 1)} Hz
            </span>
            {phase1.tuningCents !== undefined && phase1.tuningCents !== null && (
              <DeltaBadge
                value={phase1.tuningCents}
                unit="cents"
                decimals={1}
                okThreshold={5}
                warnThreshold={12}
              />
            )}
          </div>
        )}
      </Section>

      {/* 2. Loudness & Dynamics */}
      <Section id="section-meas-loudness" number={2} title="Loudness & Dynamics">
        {/* Zone 1 — LUFS Meter Strip */}
        <div className="space-y-2">
          {/* Main meter */}
          <div className="relative h-8 bg-bg-surface-darker border border-border rounded-sm overflow-hidden">
            {/* Platform reference markers */}
            {PLATFORM_REFS.map((ref) => (
              <div
                key={ref.label}
                className="absolute top-0 bottom-0 border-l border-dashed border-text-secondary/25 z-10"
                style={{ left: `${lufsToPercent(ref.lufs)}%` }}
              >
                <span className="absolute -top-0.5 left-0.5 text-pico font-mono text-text-secondary/40 leading-none">
                  {ref.label}
                </span>
              </div>
            ))}
            {/* Meter fill */}
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${lufsToPercent(phase1.lufsIntegrated)}%` }}
              transition={{ duration: 0.6, ease: 'easeOut' }}
              className="absolute inset-y-0 left-0 rounded-sm"
              style={{ background: LUFS_METER_GRADIENT }}
            />
            {/* Value badge */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3, delay: 0.5 }}
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-bg-card/90 border border-border rounded-sm px-1.5 py-0.5 z-20"
            >
              <span className="text-sm font-mono font-bold text-text-primary tabular-nums">
                {formatNumber(phase1.lufsIntegrated, 1)}
              </span>
              <span className="text-pico font-mono text-text-secondary/50 ml-1">LUFS</span>
            </motion.div>
          </div>

          {/* Loudness hierarchy bars */}
          <div className="space-y-1">
            {[
              { label: 'MOM MAX', value: phase1.lufsMomentaryMax, color: '#ff6b00' },
              { label: 'ST MAX', value: phase1.lufsShortTermMax, color: '#fb923c' },
              { label: 'INTEGRATED', value: phase1.lufsIntegrated, color: '#ffd166' },
            ].filter((row) => row.value !== undefined && row.value !== null).map((row) => (
              <div key={row.label}>
                <MetricBarRow
                  label={row.label}
                  value={row.value}
                  min={-60}
                  max={0}
                  color={row.color}
                  valueLabel={`${formatNumber(row.value!, 1)} LUFS`}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Zone 2 — Headroom & Dynamics Panel */}
        <div className="border-t border-border pt-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Left — Headroom Diagram */}
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 flex flex-col items-center shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
              <span className="mb-3 self-start text-meta font-mono uppercase tracking-wide text-text-secondary">
                Headroom
              </span>
              <div className="relative w-8 bg-bg-panel border border-border/30 rounded-sm" style={{ height: 180 }}>
                {[
                  { label: '0 dB', value: 0 },
                  { label: '-6 dB', value: -6 },
                  { label: '-12 dB', value: -12 },
                  { label: '-18 dB', value: -18 },
                  { label: '-24 dB', value: -24 },
                ].map((tick) => (
                  <div
                    key={tick.label}
                    className="absolute left-0 right-0 border-t border-dashed border-text-secondary/18"
                    style={{ top: `${((3 - tick.value) / 51) * 100}%` }}
                  >
                    <span className="absolute -left-11 -top-1.5 text-pico font-mono text-text-secondary/35">
                      {tick.label}
                    </span>
                  </div>
                ))}
                {/* True Peak marker (omitted for silence — no defined dBTP) */}
                {phase1.truePeak !== null && (
                  <div
                    className="absolute left-0 right-0 border-t-2 border-error/70 z-10"
                    style={{ top: `${Math.max(0, Math.min(100, ((3 - phase1.truePeak) / 51) * 100))}%` }}
                  >
                    <span className="absolute left-7 -top-1.5 text-pico font-mono text-error/70 whitespace-nowrap">
                      TP {formatNumber(phase1.truePeak, 1)}
                    </span>
                  </div>
                )}
                {/* Integrated LUFS marker */}
                <div
                  className="absolute left-0 right-0 border-t-2 border-accent/70 z-10"
                  style={{ top: `${Math.max(0, Math.min(100, ((3 - phase1.lufsIntegrated) / 51) * 100))}%` }}
                >
                  <span className="absolute left-7 -top-1.5 text-pico font-mono text-accent/70 whitespace-nowrap">
                    INT {formatNumber(phase1.lufsIntegrated, 1)}
                  </span>
                </div>
                {/* PLR gap fill (spans true-peak → integrated; omitted for silence) */}
                {phase1.truePeak !== null && (
                  <div
                    className="absolute left-0 right-0 bg-accent/10"
                    style={{
                      top: `${Math.max(0, Math.min(100, ((3 - phase1.truePeak) / 51) * 100))}%`,
                      bottom: `${100 - Math.max(0, Math.min(100, ((3 - phase1.lufsIntegrated) / 51) * 100))}%`,
                    }}
                  />
                )}
                {/* PLR annotation */}
                {phase1.plr !== undefined && phase1.plr !== null && phase1.truePeak !== null && (
                  <div
                    className="absolute left-8 flex items-center z-20"
                    style={{
                      top: `${Math.max(0, Math.min(100, ((3 - phase1.truePeak) / 51) * 100))}%`,
                      bottom: `${100 - Math.max(0, Math.min(100, ((3 - phase1.lufsIntegrated) / 51) * 100))}%`,
                    }}
                  >
                    <span className="text-micro font-mono text-accent font-bold whitespace-nowrap">
                      PLR {formatNumber(phase1.plr, 1)}
                    </span>
                  </div>
                )}
                <span className="absolute left-1/2 bottom-1 -translate-x-1/2 text-pico font-mono uppercase tracking-wide text-text-secondary/35">
                  floor
                </span>
              </div>
            </div>

            {/* Right — Dynamics Metric Tiles */}
            <div className="grid grid-cols-2 gap-2 content-start">
              {[
                { label: 'Crest Factor', value: phase1.crestFactor, suffix: 'dB', decimals: 2 },
                { label: 'Dynamic Spread', value: phase1.dynamicSpread, suffix: '', decimals: 2 },
                { label: 'LUFS Range', value: phase1.lufsRange, suffix: 'LU', decimals: 1 },
                { label: 'True Peak', value: phase1.truePeak, suffix: 'dBTP', decimals: 2 },
              ].filter((tile) => tile.value !== undefined && tile.value !== null).map((tile) => (
                <div key={tile.label}>
                  <MetricTile size="xl"
                    label={tile.label}
                    value={formatNumber(tile.value!, tile.decimals)}
                    unit={tile.suffix ? <span className="text-nano font-mono text-text-secondary/45">{tile.suffix}</span> : undefined}
                    className="min-h-[110px]"
                  />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Zone 3 — Dynamics & Texture */}
        <div className="border-t border-border pt-3">
          <span data-text-role="subsection-title" className={[getTextRoleClassName('subsection-title'), 'block mb-3'].join(' ')}>
            Dynamics & Texture
          </span>
          {dynamicCharacter && textureCharacter ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="space-y-3 rounded-sm border border-border-light/60 bg-bg-surface-dark/70 p-4">
                <span data-text-role="subsection-title" className={[getTextRoleClassName('subsection-title'), 'block'].join(' ')}>
                  Dynamics
                </span>
                <MetricBarRow
                  label="Complexity"
                  value={dynamicCharacter.dynamicComplexity}
                  valueLabel={formatNumber(dynamicCharacter.dynamicComplexity, 3)}
                  min={0}
                  max={6}
                  color="#ff6b00"
                />
                <MetricBarRow
                  label="Estimated Loudness"
                  value={dynamicCharacter.loudnessDb}
                  valueLabel={`${formatNumber(dynamicCharacter.loudnessDb, 2)} dB`}
                  min={-30}
                  max={-6}
                  color="#fb923c"
                />
                <MetricBarRow
                  label="Log Attack Time"
                  value={dynamicCharacter.logAttackTime}
                  valueLabel={formatNumber(dynamicCharacter.logAttackTime, 3)}
                  min={-5}
                  max={-1.5}
                  color="#38bdf8"
                />
                <MetricBarRow
                  label="Attack Time Std Dev"
                  value={dynamicCharacter.attackTimeStdDev}
                  valueLabel={`${formatNumber(dynamicCharacter.attackTimeStdDev, 4)} s`}
                  min={0}
                  max={0.1}
                  color="#a78bfa"
                />
              </div>
              <div className="space-y-3 rounded-sm border border-border-light/60 bg-bg-surface-dark/70 p-4">
                <span data-text-role="subsection-title" className={[getTextRoleClassName('subsection-title'), 'block'].join(' ')}>
                  Texture
                </span>
                <MetricBarRow
                  label="Texture Score"
                  value={textureCharacter.textureScore}
                  valueLabel={formatNumber(textureCharacter.textureScore, 3)}
                  min={0}
                  max={1}
                  color="#f97316"
                />
                <MetricBarRow
                  label="Low-Band Flatness"
                  value={textureCharacter.lowBandFlatness}
                  valueLabel={formatNumber(textureCharacter.lowBandFlatness, 3)}
                  min={0}
                  max={1}
                  color="#facc15"
                />
                <MetricBarRow
                  label="Mid-Band Flatness"
                  value={textureCharacter.midBandFlatness}
                  valueLabel={formatNumber(textureCharacter.midBandFlatness, 3)}
                  min={0}
                  max={1}
                  color="#14b8a6"
                />
                <MetricBarRow
                  label="High-Band Flatness"
                  value={textureCharacter.highBandFlatness}
                  valueLabel={formatNumber(textureCharacter.highBandFlatness, 3)}
                  min={0}
                  max={1}
                  color="#60a5fa"
                />
                <MetricBarRow
                  label="Inharmonicity"
                  value={textureCharacter.inharmonicity}
                  valueLabel={formatNumber(textureCharacter.inharmonicity, 3)}
                  min={0}
                  max={0.25}
                  color="#f472b6"
                />
              </div>
            </div>
          ) : dynamicCharacter || textureCharacter ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {dynamicCharacter ? (
                <div className="space-y-3 rounded-sm border border-border-light/60 bg-bg-surface-dark/70 p-4">
                  <span className="text-meta font-mono uppercase tracking-[0.16em] text-text-secondary block">
                    Dynamics
                  </span>
                  <MetricBarRow
                    label="Complexity"
                    value={dynamicCharacter.dynamicComplexity}
                    valueLabel={formatNumber(dynamicCharacter.dynamicComplexity, 3)}
                    min={0}
                    max={6}
                    color="#ff6b00"
                  />
                  <MetricBarRow
                    label="Estimated Loudness"
                    value={dynamicCharacter.loudnessDb}
                    valueLabel={`${formatNumber(dynamicCharacter.loudnessDb, 2)} dB`}
                    min={-30}
                    max={-6}
                    color="#fb923c"
                  />
                  <MetricBarRow
                    label="Log Attack Time"
                    value={dynamicCharacter.logAttackTime}
                    valueLabel={formatNumber(dynamicCharacter.logAttackTime, 3)}
                    min={-5}
                    max={-1.5}
                    color="#38bdf8"
                  />
                  <MetricBarRow
                    label="Attack Time Std Dev"
                    value={dynamicCharacter.attackTimeStdDev}
                    valueLabel={`${formatNumber(dynamicCharacter.attackTimeStdDev, 4)} s`}
                    min={0}
                    max={0.1}
                    color="#a78bfa"
                  />
                </div>
              ) : (
                <UnavailableMeasurementCard
                  title={dynamicsTextureFallback.title}
                  description={dynamicsTextureFallback.description}
                  detail={dynamicsTextureFallback.detail}
                />
              )}
              {textureCharacter ? (
                <div className="space-y-3 rounded-sm border border-border-light/60 bg-bg-surface-dark/70 p-4">
                  <span className="text-meta font-mono uppercase tracking-[0.16em] text-text-secondary block">
                    Texture
                  </span>
                  <MetricBarRow
                    label="Texture Score"
                    value={textureCharacter.textureScore}
                    valueLabel={formatNumber(textureCharacter.textureScore, 3)}
                    min={0}
                    max={1}
                    color="#f97316"
                  />
                  <MetricBarRow
                    label="Low-Band Flatness"
                    value={textureCharacter.lowBandFlatness}
                    valueLabel={formatNumber(textureCharacter.lowBandFlatness, 3)}
                    min={0}
                    max={1}
                    color="#facc15"
                  />
                  <MetricBarRow
                    label="Mid-Band Flatness"
                    value={textureCharacter.midBandFlatness}
                    valueLabel={formatNumber(textureCharacter.midBandFlatness, 3)}
                    min={0}
                    max={1}
                    color="#14b8a6"
                  />
                  <MetricBarRow
                    label="High-Band Flatness"
                    value={textureCharacter.highBandFlatness}
                    valueLabel={formatNumber(textureCharacter.highBandFlatness, 3)}
                    min={0}
                    max={1}
                    color="#60a5fa"
                  />
                  <MetricBarRow
                    label="Inharmonicity"
                    value={textureCharacter.inharmonicity}
                    valueLabel={formatNumber(textureCharacter.inharmonicity, 3)}
                    min={0}
                    max={0.25}
                    color="#f472b6"
                  />
                </div>
              ) : (
                <UnavailableMeasurementCard
                  title={dynamicsTextureFallback.title}
                  description={dynamicsTextureFallback.description}
                  detail={dynamicsTextureFallback.detail}
                />
              )}
            </div>
          ) : (
            <MetricTile size="xl"
              label="Dynamics & Texture"
              value={dynamicsTextureFallback.title}
              unit={<span className="text-nano font-mono uppercase tracking-wide text-text-secondary/45">Unavailable</span>}
              accent="warning"
              footer={
                <div className="space-y-2">
                  <p className="text-meta font-mono uppercase tracking-[0.14em] text-text-secondary/70">
                    {dynamicsTextureFallback.description}
                  </p>
                  {dynamicsTextureFallback.detail ? (
                    <p className="text-meta font-mono uppercase tracking-[0.12em] text-text-secondary/55">
                      {dynamicsTextureFallback.detail}
                    </p>
                  ) : null}
                </div>
              }
            />
          )}
        </div>
      </Section>

      {/* 3. Mix Doctor (audit quick-hit: was "MixDoctor" — formatWord in
        `utils/displayText.ts` case-normalizes single-token CamelCase to
        sentence case, so "MixDoctor" was rendering as "Mixdoctor" with
        a lowercase 'd'. Renaming to two words ("Mix Doctor") matches
        every other section name's pattern and renders cleanly through
        the existing pipeline.) */}
      <Section id="section-meas-mixdoctor" number={3} title="Mix Doctor">
        <MixDoctorPanel report={mixDoctorReport} />
      </Section>

      {/* 4. Spectral */}
      <Section id="section-meas-spectral" testId="spectral-section" number={4} title="Spectral">
        <div className="space-y-3">
          <div>
            <span data-text-role="subsection-title" className={getTextRoleClassName('subsection-title')}>
              Spectral Balance
            </span>
            <div className="mt-2 space-y-3">
              {SPECTRAL_ROW_CONFIG.map((row) => (
                <div key={row.key}>
                  <MetricBarRow
                    label={row.label}
                    value={phase1.spectralBalance[row.key]}
                    valueLabel={`${formatNumber(phase1.spectralBalance[row.key], 2)} dB`}
                    min={spectralBalanceStats.min}
                    max={spectralBalanceStats.max}
                    color={SPECTRAL_BALANCE_PALETTE[row.key]}
                  />
                </div>
              ))}
            </div>
          </div>
          {phase1.spectralDetail && (
            <div className="border-t border-border/30 pt-2 mt-2 space-y-3">
              {phase1.spectralDetail.spectralCentroidMean !== undefined &&
                phase1.spectralDetail.spectralCentroidMean !== null && (
                  <MetricBarRow
                    label="Centroid Mean"
                    value={phase1.spectralDetail.spectralCentroidMean}
                    min={0}
                    max={12000}
                    color={SPECTRAL_BALANCE_PALETTE.highs}
                    valueLabel={`${formatNumber(phase1.spectralDetail.spectralCentroidMean, 1)} Hz`}
                    sparkline={
                      spectralTimeSeries?.spectralCentroid &&
                      spectralTimeSeries.spectralCentroid.length > 1 && (
                        <Sparkline values={spectralTimeSeries.spectralCentroid} color={SPECTRAL_BALANCE_PALETTE.highs} />
                      )
                    }
                  />
                )}
              {phase1.spectralDetail.spectralRolloffMean !== undefined &&
                phase1.spectralDetail.spectralRolloffMean !== null && (
                  <MetricBarRow
                    label="Rolloff Mean"
                    value={phase1.spectralDetail.spectralRolloffMean}
                    min={0}
                    max={22050}
                    color={SPECTRAL_BALANCE_PALETTE.brilliance}
                    valueLabel={`${formatNumber(phase1.spectralDetail.spectralRolloffMean, 1)} Hz`}
                    sparkline={
                      spectralTimeSeries?.spectralRolloff &&
                      spectralTimeSeries.spectralRolloff.length > 1 && (
                        <Sparkline values={spectralTimeSeries.spectralRolloff} color={SPECTRAL_BALANCE_PALETTE.brilliance} />
                      )
                    }
                  />
                )}
              {phase1.spectralDetail.spectralBandwidthMean !== undefined &&
                phase1.spectralDetail.spectralBandwidthMean !== null && (
                  <MetricBarRow
                    label="Bandwidth Mean"
                    value={phase1.spectralDetail.spectralBandwidthMean}
                    min={0}
                    max={12000}
                    color={SPECTRAL_BALANCE_PALETTE.upperMids}
                    valueLabel={`${formatNumber(phase1.spectralDetail.spectralBandwidthMean, 1)} Hz`}
                    sparkline={
                      spectralTimeSeries?.spectralBandwidth &&
                      spectralTimeSeries.spectralBandwidth.length > 1 && (
                        <Sparkline values={spectralTimeSeries.spectralBandwidth} color={SPECTRAL_BALANCE_PALETTE.upperMids} />
                      )
                    }
                  />
                )}
              {phase1.spectralDetail.spectralFlatnessMean !== undefined &&
                phase1.spectralDetail.spectralFlatnessMean !== null && (
                  <MetricBarRow
                    label="Flatness Mean"
                    value={phase1.spectralDetail.spectralFlatnessMean}
                    min={0}
                    max={1}
                    color={SPECTRAL_BALANCE_PALETTE.lowMids}
                    valueLabel={formatNumber(phase1.spectralDetail.spectralFlatnessMean, 6)}
                    sparkline={
                      spectralTimeSeries?.spectralFlatness &&
                      spectralTimeSeries.spectralFlatness.length > 1 && (
                        <Sparkline values={spectralTimeSeries.spectralFlatness} color={SPECTRAL_BALANCE_PALETTE.lowMids} />
                      )
                    }
                  />
                )}
            </div>
          )}
        </div>

        {/* Enhancement Toolbar */}
        {apiBaseUrl && runId && (
          <div data-testid="spectral-enhancements-toolbar" className="border-t border-border pt-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-meta font-mono uppercase tracking-wide text-text-secondary mr-1">
                Enhancements
              </span>
              {([
                { kind: 'cqt' as SpectralEnhancementKind, label: 'CQT', done: localArtifacts?.spectrograms.some((s) => s.kind === 'spectrogram_cqt') },
                { kind: 'hpss' as SpectralEnhancementKind, label: 'HPSS', done: localArtifacts?.spectrograms.some((s) => s.kind === 'spectrogram_harmonic') },
                { kind: 'onset' as SpectralEnhancementKind, label: 'Onset', done: !!localArtifacts?.onsetStrength },
                { kind: 'chroma_interactive' as SpectralEnhancementKind, label: 'Chroma', done: !!localArtifacts?.chromaInteractive },
              ]).map(({ kind, label, done }) =>
                done ? (
                  <React.Fragment key={kind}>
                    <StatusBadge
                      label={`${label} ✓`}
                      tone="success"
                      compact
                    />
                  </React.Fragment>
                ) : (
                  <React.Fragment key={kind}>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handleGenerate(kind)}
                      disabled={generating.has(kind)}
                    >
                      {generating.has(kind) ? `${label}...` : `Generate ${label}`}
                    </Button>
                  </React.Fragment>
                ),
              )}
            </div>
          </div>
        )}

        <SpectralCursorProvider>
          {localArtifacts && apiBaseUrl && runId && localArtifacts.spectrograms.length > 0 && (
            <div data-testid="spectral-visualizations-panel" className="border-t border-border pt-3">
              <SpectrogramViewer
                spectrograms={localArtifacts.spectrograms}
                apiBaseUrl={apiBaseUrl}
                runId={runId}
                durationSeconds={phase1.durationSeconds}
              />
            </div>
          )}

          {spectralTimeSeries && (
            <div className="border-t border-border pt-3">
              <SpectralEvolutionChart data={spectralTimeSeries} onsetStrength={onsetData} />
            </div>
          )}

          {chromaData && (
            <div className="border-t border-border pt-3">
              <ChromaHeatmap data={chromaData} />
            </div>
          )}
        </SpectralCursorProvider>

        {phase1.spectralDetail && (
          <>
            {phase1.spectralDetail.mfcc && phase1.spectralDetail.mfcc.length > 0 && (
              <BarChart
                values={phase1.spectralDetail.mfcc.slice(0, 8)}
                count={8}
                label="MFCC (first 8)"
              />
            )}
            {phase1.spectralDetail.chroma && phase1.spectralDetail.chroma.length > 0 && (
              <BarChart
                values={phase1.spectralDetail.chroma}
                count={12}
                label="Chroma (12 pitches)"
              />
            )}
            {phase1.spectralDetail.barkBands && phase1.spectralDetail.barkBands.length > 0 && (
              <BarChart
                values={phase1.spectralDetail.barkBands.slice(0, 16)}
                count={16}
                label="Bark Bands"
              />
            )}
            {phase1.spectralDetail.erbBands && phase1.spectralDetail.erbBands.length > 0 && (
              <BarChart
                values={phase1.spectralDetail.erbBands.slice(0, 16)}
                count={16}
                label="ERB Bands"
              />
            )}
            {phase1.spectralDetail.spectralContrast &&
              phase1.spectralDetail.spectralContrast.length > 0 && (
                <MiniHeatmap
                  title="Spectral Contrast"
                  rows={[
                    { label: 'Contrast', values: phase1.spectralDetail.spectralContrast.slice(0, 7) },
                    ...(phase1.spectralDetail.spectralValley && phase1.spectralDetail.spectralValley.length > 0
                      ? [{ label: 'Valley', values: phase1.spectralDetail.spectralValley.slice(0, 7) }]
                      : []),
                  ]}
                  cellLabels={['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7']}
                />
              )}
          </>
        )}

        {phase1.essentiaFeatures && (
          <>
            <div className="border-t border-border pt-3">
              <span data-text-role="subsection-title" className={getTextRoleClassName('subsection-title')}>
                Essentia Features
              </span>
            </div>
            {phase1.essentiaFeatures.zeroCrossingRate !== undefined &&
              phase1.essentiaFeatures.zeroCrossingRate !== null && (
                <MetricBarRow
                  label="Zero Crossing Rate"
                  value={phase1.essentiaFeatures.zeroCrossingRate}
                  min={0}
                  max={0.5}
                  color="#ff8c42"
                  valueLabel={formatNumber(phase1.essentiaFeatures.zeroCrossingRate, 3)}
                />
              )}
            {phase1.essentiaFeatures.hfc !== undefined && phase1.essentiaFeatures.hfc !== null && (
              <MetricBarRow
                label="High Frequency Content"
                value={phase1.essentiaFeatures.hfc}
                min={0}
                max={1}
                color="#38bdf8"
                valueLabel={formatNumber(phase1.essentiaFeatures.hfc, 2)}
              />
            )}
            {phase1.essentiaFeatures.spectralComplexity !== undefined &&
              phase1.essentiaFeatures.spectralComplexity !== null && (
                <MetricBarRow
                  label="Spectral Complexity"
                  value={phase1.essentiaFeatures.spectralComplexity}
                  min={0}
                  max={60}
                  color="#a78bfa"
                  valueLabel={formatNumber(phase1.essentiaFeatures.spectralComplexity, 2)}
                />
              )}
            {phase1.essentiaFeatures.dissonance !== undefined &&
              phase1.essentiaFeatures.dissonance !== null && (
                <MetricBarRow
                  label="Dissonance"
                  value={phase1.essentiaFeatures.dissonance}
                  min={0}
                  max={1}
                  color="#ef4444"
                  valueLabel={formatNumber(phase1.essentiaFeatures.dissonance, 2)}
                />
              )}
          </>
        )}
      </Section>

      {/* 5. Stereo Field */}
      <Section id="section-meas-stereo" number={5} title="Stereo Field">
        <MetricBarRow
          label="Stereo Width"
          value={phase1.stereoWidth}
          min={0}
          max={1}
          color="#38bdf8"
          leftLabel="narrow"
          rightLabel="wide"
          valueLabel={formatNumber(phase1.stereoWidth, 2)}
        />
        <MetricBarRow
          label="Stereo Correlation"
          value={phase1.stereoCorrelation}
          min={-1}
          max={1}
          color="#ff6b00"
          leftLabel="anti-phase"
          rightLabel="mono"
          valueLabel={formatNumber(phase1.stereoCorrelation, 2)}
        />
        {phase1.monoCompatible !== undefined && phase1.monoCompatible !== null && (
          <MetricRow
            label="Mono Compatible"
            value={<StatusBadge label={phase1.monoCompatible ? 'Yes' : 'No'} tone={phase1.monoCompatible ? 'success' : 'error'} compact />}
          />
        )}
        {phase1.stereoDetail && (
          <>
            {phase1.stereoDetail.subBassCorrelation !== undefined &&
              phase1.stereoDetail.subBassCorrelation !== null && (
                <MetricBarRow
                  label="Sub-Bass Correlation"
                  value={phase1.stereoDetail.subBassCorrelation}
                  min={-1}
                  max={1}
                  color="#14b8a6"
                  leftLabel="anti-phase"
                  rightLabel="mono"
                  valueLabel={formatNumber(phase1.stereoDetail.subBassCorrelation, 2)}
                />
              )}
            {phase1.stereoDetail.subBassMono !== undefined &&
              phase1.stereoDetail.subBassMono !== null && (
                <MetricRow
                  label="Sub-Bass Mono"
                  value={<StatusBadge label={phase1.stereoDetail.subBassMono ? 'Yes' : 'No'} tone={phase1.stereoDetail.subBassMono ? 'success' : 'error'} compact />}
                />
              )}
          </>
        )}
        {phase1.segmentStereo && phase1.segmentStereo.length > 0 && (
          <>
            <div className="border-t border-border pt-3 mt-3">
              <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">
                Segment Stereo
              </span>
            </div>
            <DataTable
              data={phase1.segmentStereo}
              columns={[
                {
                  key: 'segmentIndex',
                  label: 'Segment',
                  monospace: true,
                  render: (row) => String(row.segmentIndex ?? '—'),
                },
                {
                  key: 'width',
                  label: 'Width',
                  render: (row) => (
                    <div className="space-y-1">
                      <div className="text-right font-mono tabular-nums text-text-primary">
                        {formatNumber(row.stereoWidth, 2)}
                      </div>
                      <MetricBar
                        value={row.stereoWidth}
                        min={0}
                        max={1}
                        color="#38bdf8"
                        heightClassName="h-1.5"
                      />
                    </div>
                  ),
                },
                {
                  key: 'corr',
                  label: 'Corr',
                  render: (row) => (
                    <div className="space-y-1">
                      <div className="text-right font-mono tabular-nums text-text-primary">
                        {formatNumber(row.stereoCorrelation, 2)}
                      </div>
                      <MetricBar
                        value={row.stereoCorrelation}
                        min={-1}
                        max={1}
                        color="#ff6b00"
                        heightClassName="h-1.5"
                      />
                    </div>
                  ),
                },
              ]}
            />
          </>
        )}
      </Section>

      {/* 6. Rhythm & Groove */}
      <Section id="section-meas-rhythm" number={6} title="Rhythm & Groove">
        <div className="flex flex-col gap-4 md:flex-row md:items-stretch">
          <BreathingBpmPulse bpm={phase1.bpm} bpmSource={phase1.bpmSource} />
          <div className="flex-1 grid grid-cols-1 gap-2 md:grid-cols-2">
            {phase1.rhythmDetail && (
              <>
                <ComparativeMetricTile
                  metricKey="groove"
                  value={phase1.rhythmDetail.grooveAmount}
                  delay={0}
                />
                <ComparativeMetricTile
                  metricKey="stability"
                  value={
                    (phase1.rhythmDetail.tempoStability ??
                      1 - phase1.rhythmDetail.grooveAmount) * 100
                  }
                  delay={0.08}
                />
              </>
            )}
            {phase1.danceability && (
              <ComparativeMetricTile
                metricKey="danceability"
                value={phase1.danceability.danceability}
                delay={0.16}
              />
            )}
            {phase1.rhythmDetail && (
              <ComparativeMetricTile
                metricKey="onsetRate"
                value={phase1.rhythmDetail.onsetRate}
                delay={0.24}
              />
            )}
          </div>
        </div>

        {phase1.rhythmTimeline?.windows && phase1.rhythmTimeline.windows.length > 0 && (
          <div className="border-t border-border pt-3">
            <RhythmGridPanel phase1={phase1} />
          </div>
        )}

        {(phase1.grooveDetail || phase1.beatsLoudness) && (
          <div className="border-t border-border pt-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {phase1.grooveDetail && (
                <div className="bg-bg-surface-dark border border-border rounded-sm p-3">
                  <div className="text-meta font-mono uppercase tracking-wide text-text-secondary mb-3">
                    Swing
                  </div>
                  <div className="space-y-3">
                    {[
                      { label: 'KICK', value: phase1.grooveDetail.kickSwing, color: '#ff4444' },
                      { label: 'HH', value: phase1.grooveDetail.hihatSwing, color: '#60a5fa' },
                    ].map((s) => (
                      <div key={s.label}>
                        <div className="mb-1.5 flex items-center justify-between gap-3">
                          <span
                            className="text-meta font-mono uppercase tracking-[0.12em]"
                            style={{ color: `${s.color}80` }}
                          >
                            {s.label}
                          </span>
                          <span
                            className="text-meta font-mono font-bold"
                            style={{ color: s.color }}
                          >
                            {formatNumber(s.value, 2)}
                          </span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-sm border border-[#202020] bg-[#1a1a1a]">
                          <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${s.value * 100}%` }}
                            transition={{ duration: 0.5, ease: 'easeOut' }}
                            className="h-full rounded-sm"
                            style={{ background: s.color, opacity: 0.7 }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {phase1.beatsLoudness && (
                <div className="bg-bg-surface-dark border border-border rounded-sm p-3">
                  <HorizontalDominance
                    kickRatio={phase1.beatsLoudness.kickDominantRatio}
                    midRatio={phase1.beatsLoudness.midDominantRatio}
                    highRatio={phase1.beatsLoudness.highDominantRatio}
                  />
                  <div className="mt-3 grid grid-cols-3 gap-3">
                    <div>
                      <span className="block text-meta font-mono text-text-secondary">Beat Count</span>
                      <span className="text-sm font-display font-bold text-text-primary">
                        {formatNumber(phase1.beatsLoudness.beatCount, 0)}
                      </span>
                    </div>
                    <div>
                      <span className="block text-meta font-mono text-text-secondary">Mean Loud</span>
                      <span className="text-sm font-display font-bold text-text-primary">
                        {formatNumber(phase1.beatsLoudness.meanBeatLoudness, 2)}
                      </span>
                    </div>
                    <div>
                      <span className="block text-meta font-mono text-text-secondary">Variation</span>
                      <span className="text-sm font-display font-bold text-text-primary">
                        {formatNumber(phase1.beatsLoudness.beatLoudnessVariation, 2)}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {(phase1.sidechainDetail ||
          (phase1.effectsDetail && phase1.effectsDetail.gatingDetected)) && (
          <div className="border-t border-border pt-3 space-y-2">
            <span className="text-meta font-mono uppercase tracking-wide text-text-secondary block">
              Sidechain & Effects
            </span>
            <div className="rounded-sm border border-border bg-bg-surface-dark p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
              <div className="grid gap-3 lg:grid-cols-[minmax(0,1.35fr)_minmax(260px,0.9fr)]">
                <SidechainEnvelope
                  envelopeShape={phase1.sidechainDetail?.envelopeShape}
                  pumpingRate={phase1.sidechainDetail?.pumpingRate}
                  pumpingStrength={phase1.sidechainDetail?.pumpingStrength}
                  pumpingRegularity={phase1.sidechainDetail?.pumpingRegularity}
                  pumpingConfidence={phase1.sidechainDetail?.pumpingConfidence}
                />
                <EffectsFieldPanel
                  gatingDetected={phase1.effectsDetail?.gatingDetected}
                  gatingRate={phase1.effectsDetail?.gatingRate ?? null}
                  gatingRegularity={phase1.effectsDetail?.gatingRegularity ?? null}
                  gatingEventCount={phase1.effectsDetail?.gatingEventCount ?? null}
                  pumpingStrength={phase1.sidechainDetail?.pumpingStrength ?? null}
                  pumpingRegularity={phase1.sidechainDetail?.pumpingRegularity ?? null}
                  pumpingConfidence={phase1.sidechainDetail?.pumpingConfidence ?? null}
                />
              </div>
            </div>
          </div>
        )}

        {phase1.rhythmDetail?.downbeatSource && (
          <div className="border-t border-border pt-3">
            <MetricRow
              label="Downbeat (bar 1) detection"
              value={
                phase1.rhythmDetail.downbeatSource === 'kick_accent'
                  ? `kick-accent · confidence ${formatNumber(
                      phase1.rhythmDetail.downbeatConfidence ?? 0,
                      2,
                    )}`
                  : 'assumed (4/4 stride — phase unverified)'
              }
            />
          </div>
        )}

        {phase1.rhythmDetail?.phraseGrid && (
          <div className="border-t border-border pt-3">
            <PhraseStructureTimeline phraseGrid={phase1.rhythmDetail.phraseGrid} />
          </div>
        )}

        {phase1.danceability && (
          <div className="border-t border-border pt-3">
            <MetricRow
              label="DFA (Rhythmic Complexity)"
              value={formatNumber(phase1.danceability.dfa, 3)}
            />
          </div>
        )}
      </Section>

      {/* 7. Harmony */}
      <Section id="section-meas-harmony" number={7} title="Harmony">
        <HarmonyLanes phase1={phase1} />
      </Section>

      {/* 8. Structure & Arrangement */}
      <Section id="section-meas-structure" number={8} title="Structure & Arrangement">
        <StructureLanes phase1={phase1} />
      </Section>

      {/* 9. Synthesis & Timbre */}
      <Section id="section-meas-synthesis" number={9} title="Synthesis & Timbre">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {phase1.synthesisCharacter && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span data-text-role="subsection-title" className={getTextRoleClassName('subsection-title')}>
                  Synthesis Character
                </span>
                {phase1.synthesisCharacter.analogLike !== undefined &&
                  phase1.synthesisCharacter.analogLike !== null && (
                    <StatusBadge
                      label={phase1.synthesisCharacter.analogLike ? 'Analog-Like' : 'Digital-Like'}
                      tone={phase1.synthesisCharacter.analogLike ? 'success' : 'muted'}
                      compact
                    />
                  )}
              </div>
              {phase1.synthesisCharacter.inharmonicity !== undefined &&
                phase1.synthesisCharacter.inharmonicity !== null && (
                  <MetricBarRow
                    label="Inharmonicity"
                    value={phase1.synthesisCharacter.inharmonicity}
                    min={0}
                    max={1}
                    color="#ff6b00"
                    valueLabel={formatNumber(phase1.synthesisCharacter.inharmonicity, 3)}
                  />
                )}
              {phase1.synthesisCharacter.oddToEvenRatio !== undefined &&
                phase1.synthesisCharacter.oddToEvenRatio !== null && (
                  <MetricBarRow
                    label="Odd-to-Even Ratio"
                    value={phase1.synthesisCharacter.oddToEvenRatio}
                    min={0}
                    max={3}
                    color="#f59e0b"
                    valueLabel={formatNumber(phase1.synthesisCharacter.oddToEvenRatio, 2)}
                  />
                )}
            </div>
          )}

          {phase1.perceptual && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <span data-text-role="subsection-title" className={getTextRoleClassName('subsection-title')}>
                Perceptual
              </span>
              <MetricBarRow
                label="Sharpness"
                value={phase1.perceptual.sharpness}
                min={0}
                max={1}
                color="#38bdf8"
                valueLabel={formatNumber(phase1.perceptual.sharpness, 2)}
              />
              <MetricBarRow
                label="Roughness"
                value={phase1.perceptual.roughness}
                min={0}
                max={1}
                color="#ef4444"
                valueLabel={formatNumber(phase1.perceptual.roughness, 2)}
              />
            </div>
          )}

          {phase1.sidechainDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span data-text-role="subsection-title" className={getTextRoleClassName('subsection-title')}>
                  Sidechain / Pumping
                </span>
                {phase1.sidechainDetail.pumpingRate && (
                  <StatusBadge label={phase1.sidechainDetail.pumpingRate} tone="info" compact />
                )}
              </div>
              <MetricBarRow
                label="Pumping Strength"
                value={phase1.sidechainDetail.pumpingStrength}
                min={0}
                max={1}
                color="#a78bfa"
                valueLabel={formatNumber(phase1.sidechainDetail.pumpingStrength, 2)}
              />
              <MetricBarRow
                label="Pumping Regularity"
                value={phase1.sidechainDetail.pumpingRegularity}
                min={0}
                max={1}
                color="#60a5fa"
                valueLabel={formatNumber(phase1.sidechainDetail.pumpingRegularity, 2)}
              />
              <MetricBarRow
                label="Pumping Confidence"
                value={phase1.sidechainDetail.pumpingConfidence}
                min={0}
                max={1}
                color="#34d399"
                valueLabel={formatNumber(phase1.sidechainDetail.pumpingConfidence, 2)}
              />
              {phase1.sidechainDetail.envelopeShape &&
                phase1.sidechainDetail.envelopeShape.length > 0 && (
                  <BarChart
                    values={phase1.sidechainDetail.envelopeShape.slice(0, 16)}
                    count={16}
                    label="Pumping Shape"
                    height="h-8"
                    colors={['#a78bfa', '#c084fc', '#60a5fa', '#34d399']}
                  />
                )}
            </div>
          )}

          {phase1.effectsDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">
                  Effects
                </span>
                {phase1.effectsDetail.gatingDetected !== undefined &&
                  phase1.effectsDetail.gatingDetected !== null && (
                    <StatusBadge
                      label={phase1.effectsDetail.gatingDetected ? 'Yes' : 'No'}
                      tone={phase1.effectsDetail.gatingDetected ? 'success' : 'error'}
                      compact
                    />
                  )}
              </div>
              {phase1.effectsDetail.gatingRate !== undefined &&
                phase1.effectsDetail.gatingRate !== null && (
                  <MetricRow
                    label="Gating Rate"
                    value={
                      <span className="font-mono tabular-nums">
                        {phase1.effectsDetail.gatingRate}
                      </span>
                    }
                  />
                )}
              {phase1.effectsDetail.gatingRegularity !== undefined &&
                phase1.effectsDetail.gatingRegularity !== null && (
                  <MetricBarRow
                    label="Gating Regularity"
                    value={phase1.effectsDetail.gatingRegularity}
                    min={0}
                    max={1}
                    color="#ffd166"
                    valueLabel={formatNumber(phase1.effectsDetail.gatingRegularity, 2)}
                  />
                )}
              {phase1.effectsDetail.gatingEventCount !== undefined &&
                phase1.effectsDetail.gatingEventCount !== null && (
                  <MetricRow
                    label="Gating Event Count"
                    value={<span className="font-mono tabular-nums">{formatNumber(phase1.effectsDetail.gatingEventCount, 0)}</span>}
                  />
                )}
            </div>
          )}

          {phase1.vocalDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">
                  Vocals
                </span>
                <StatusBadge
                  label={phase1.vocalDetail.hasVocals ? 'Yes' : 'No'}
                  tone={phase1.vocalDetail.hasVocals ? 'success' : 'error'}
                  compact
                />
              </div>
              <MetricBarRow
                label="Confidence"
                value={phase1.vocalDetail.confidence}
                min={0}
                max={1}
                color="#ff6b00"
                valueLabel={formatNumber(phase1.vocalDetail.confidence, 2)}
              />
              <MetricBarRow
                label="Vocal Energy Ratio"
                value={phase1.vocalDetail.vocalEnergyRatio}
                min={0}
                max={1}
                color="#38bdf8"
                valueLabel={formatNumber(phase1.vocalDetail.vocalEnergyRatio, 3)}
              />
              <MetricRow
                label="Formant Strength"
                value={<span className="font-mono tabular-nums">{formatNumber(phase1.vocalDetail.formantStrength, 3)}</span>}
              />
            </div>
          )}

          {phase1.acidDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">
                  Acid
                </span>
                <StatusBadge
                  label={phase1.acidDetail.isAcid ? 'Yes' : 'No'}
                  tone={phase1.acidDetail.isAcid ? 'success' : 'error'}
                  compact
                />
              </div>
              <MetricBarRow
                label="Confidence"
                value={phase1.acidDetail.confidence}
                min={0}
                max={1}
                color="#f97316"
                valueLabel={formatNumber(phase1.acidDetail.confidence, 2)}
              />
              <MetricBarRow
                label="Resonance Level"
                value={phase1.acidDetail.resonanceLevel}
                min={0}
                max={1}
                color="#ef4444"
                valueLabel={formatNumber(phase1.acidDetail.resonanceLevel, 3)}
              />
              <MetricRow
                label="Bass Rhythm Density"
                value={<span className="font-mono tabular-nums">{formatNumber(phase1.acidDetail.bassRhythmDensity, 3)}</span>}
              />
            </div>
          )}

          {phase1.supersawDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">
                  Supersaw
                </span>
                <StatusBadge
                  label={phase1.supersawDetail.isSupersaw ? 'Yes' : 'No'}
                  tone={phase1.supersawDetail.isSupersaw ? 'success' : 'error'}
                  compact
                />
              </div>
              <MetricBarRow
                label="Confidence"
                value={phase1.supersawDetail.confidence}
                min={0}
                max={1}
                color="#a78bfa"
                valueLabel={formatNumber(phase1.supersawDetail.confidence, 2)}
              />
              <MetricRow
                label="Voice Count"
                value={<span className="font-mono tabular-nums">{formatNumber(phase1.supersawDetail.voiceCount, 0)}</span>}
              />
              <MetricRow
                label="Avg Detune"
                value={
                  <span className="font-mono tabular-nums">
                    {formatNumber(phase1.supersawDetail.avgDetuneCents, 1)}
                    <span className="ml-1 text-meta text-text-secondary/50">cents</span>
                  </span>
                }
              />
            </div>
          )}

          {phase1.bassDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">
                  Bass Character
                </span>
                <StatusBadge label={phase1.bassDetail.type} tone="accent" compact />
              </div>
              <MetricRow
                label="Avg Decay"
                value={
                  <span className="font-mono tabular-nums">
                    {formatNumber(phase1.bassDetail.averageDecayMs, 0)}
                    <span className="ml-1 text-meta text-text-secondary/50">ms</span>
                  </span>
                }
              />
              <MetricBarRow
                label="Swing"
                value={phase1.bassDetail.swingPercent}
                min={0}
                max={100}
                color="#ff6b00"
                valueLabel={`${formatNumber(phase1.bassDetail.swingPercent, 1)}%`}
              />
              <MetricRow label="Groove Type" value={phase1.bassDetail.grooveType} />
              {phase1.bassDetail.fundamentalHz != null && (
                <MetricRow
                  label="Fundamental"
                  value={
                    <span className="font-mono tabular-nums">
                      {formatNumber(phase1.bassDetail.fundamentalHz, 1)}
                      <span className="ml-1 text-meta text-text-secondary/50">Hz</span>
                    </span>
                  }
                />
              )}
            </div>
          )}

          {phase1.kickDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">
                  Kick
                </span>
                <StatusBadge
                  label={phase1.kickDetail.isDistorted ? 'Yes' : 'No'}
                  tone={phase1.kickDetail.isDistorted ? 'warning' : 'success'}
                  compact
                />
              </div>
              <MetricRow
                label="THD"
                value={<span className="font-mono tabular-nums">{formatNumber(phase1.kickDetail.thd, 3)}</span>}
              />
              <MetricRow
                label="Kick Count"
                value={<span className="font-mono tabular-nums">{formatNumber(phase1.kickDetail.kickCount, 0)}</span>}
              />
              {phase1.kickDetail.fundamentalHz != null && (
                <MetricRow
                  label="Fundamental"
                  value={
                    <span className="font-mono tabular-nums">
                      {formatNumber(phase1.kickDetail.fundamentalHz, 1)}
                      <span className="ml-1 text-meta text-text-secondary/50">Hz</span>
                    </span>
                  }
                />
              )}
            </div>
          )}

          {phase1.reverbDetail && (
            <div className="bg-bg-surface-dark border border-border-light border-l-2 border-accent rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
              <div className="flex items-start justify-between gap-3">
                <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">
                  Reverb
                </span>
                <StatusBadge
                  label={phase1.reverbDetail.isWet ? 'Yes' : 'No'}
                  tone={phase1.reverbDetail.isWet ? 'success' : 'error'}
                  compact
                />
              </div>
              {phase1.reverbDetail.rt60 != null && (
                <MetricBarRow
                  label="RT60"
                  value={phase1.reverbDetail.rt60}
                  min={0}
                  max={8}
                  color="#38bdf8"
                  leftLabel="dry"
                  rightLabel="spacious"
                  valueLabel={`${formatNumber(phase1.reverbDetail.rt60, 2)} s`}
                />
              )}
              <MetricRow
                label="Measured"
                value={<StatusBadge label={phase1.reverbDetail.measured ? 'Yes' : 'No'} tone={phase1.reverbDetail.measured ? 'success' : 'muted'} compact />}
              />
            </div>
          )}
        </div>
      </Section>
      </div>
    </DeviceRack>
  );
}

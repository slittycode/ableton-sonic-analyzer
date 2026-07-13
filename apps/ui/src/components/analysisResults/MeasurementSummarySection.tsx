import { Activity, Clock, Disc, Music } from 'lucide-react';

import type { Phase1Result, Phase2Result } from '../../types';
import { ConfidenceBandBadge } from '../sessionMusician/ConfidenceBandBadge';
import { PhaseSourceBadge } from '../PhaseSourceBadge';
import { DeviceRack, MetricBar, MetricTile, Pill, TokenBadgeList } from '../ui';
import { lowConfidenceIndicator } from './shared';

// Helpers exclusive to the Measurement Summary tiles — moved verbatim out of the
// AnalysisResults monolith (Phase 5 split) alongside the section they serve.

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

function isAssumedMeter(phase1: Phase1Result): boolean {
  return phase1.timeSignatureSource === 'assumed_four_four' || (phase1.timeSignatureConfidence ?? 1) <= 0;
}

function meterStatusLabel(phase1: Phase1Result): string {
  return isAssumedMeter(phase1) ? 'ASSUMED' : 'DETECTED';
}

type PillTone = React.ComponentProps<typeof Pill>['tone'];

function fundamentalsTone(status: string | null | undefined): PillTone {
  if (status === 'authoritative') return 'success';
  if (status === 'failed') return 'error';
  if (status === 'ambiguous') return 'warning';
  return 'neutral';
}

function fundamentalsLabel(status: string | null | undefined): string {
  if (status === 'authoritative') return 'LOCAL';
  if (status === 'failed') return 'FAILED';
  if (status === 'ambiguous') return 'CHECK';
  return 'NOT RUN';
}

const FUNDAMENTALS_PILLS = [
  ['Tempo', 'tempo'],
  ['Beat', 'beatGrid'],
  ['Meter', 'meter'],
  ['Key', 'key'],
  ['Chords', 'chords'],
  ['Drums', 'percussion'],
  ['Notes', 'transcription'],
] as const;

export function MeasurementSummarySection({
  phase1,
  finalBpm,
  finalKey,
  keyIsApproximate,
  characteristicPills,
}: {
  phase1: Phase1Result;
  finalBpm: number;
  finalKey: string;
  keyIsApproximate: boolean;
  characteristicPills: Phase2Result['detectedCharacteristics'];
}) {
  return (
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
                <span className="block text-nano font-mono uppercase tracking-wide text-text-secondary/50">
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
          footer={<Pill tone="neutral" size="xs">{meterStatusLabel(phase1)}</Pill>}
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
                      ? [{ label: phase1.genreDetail.secondaryGenre, tone: 'neutral' as const }]
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
                      className={`inline-flex items-center px-2 py-1 rounded-sm border text-micro font-mono uppercase tracking-wide ${characteristicPillClass(item.confidence)}`}
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
      {phase1.fundamentalsQuality && (
        <div
          className="mt-3 flex flex-wrap items-center gap-1.5"
          data-testid="fundamentals-quality-summary"
        >
          <span className="text-nano font-mono uppercase tracking-[0.16em] text-text-muted">
            Local fundamentals
          </span>
          <Pill
            tone={fundamentalsTone(phase1.fundamentalsQuality.overallStatus)}
            size="xs"
            title="Overall local-measurement trust across all fundamentals that ran."
          >
            Overall {fundamentalsLabel(phase1.fundamentalsQuality.overallStatus)}
          </Pill>
          {FUNDAMENTALS_PILLS.map(([label, domainKey]) => {
            const domain = phase1.fundamentalsQuality?.domains[domainKey];
            if (!domain) return null;
            return (
              <Pill
                key={domainKey}
                tone={fundamentalsTone(domain.status)}
                size="xs"
                title={domain.plainEnglish}
              >
                {label} {fundamentalsLabel(domain.status)}
              </Pill>
            );
          })}
        </div>
      )}
    </DeviceRack>
  );
}

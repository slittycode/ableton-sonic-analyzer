import React, { useState } from 'react';
import { Phase1Result } from '../types';

interface MeasurementDashboardProps {
  phase1: Phase1Result;
}

const formatNumber = (value: number | null | undefined, decimals = 2): string => {
  if (value === null || value === undefined) return '—';
  return typeof value === 'number' ? value.toFixed(decimals) : '—';
};

const formatDuration = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const MetricRow = ({ label, value }: { label: string; value: React.ReactNode }) => (
  <div className="flex justify-between items-baseline gap-4">
    <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
      {label}
    </span>
    <span className="text-sm font-display font-bold text-text-primary">
      {value}
    </span>
  </div>
);

const SectionHeader = ({
  number,
  title,
  isOpen,
  onToggle,
}: {
  number: number;
  title: string;
  isOpen: boolean;
  onToggle: () => void;
}) => (
  <button
    onClick={onToggle}
    className="w-full text-left flex items-center gap-2 hover:opacity-80 transition-opacity"
  >
    <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
      {number.toString().padStart(2, '0')}
    </span>
    <span className="text-lg font-display font-bold text-text-primary flex-1">
      {title}
    </span>
    <span className="text-text-secondary text-sm">{isOpen ? '−' : '+'}</span>
  </button>
);

const Section = ({
  id,
  number,
  title,
  children,
}: {
  id?: string;
  number: number;
  title: string;
  children: React.ReactNode;
}) => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div id={id} className="bg-bg-card border border-border rounded-sm p-4 space-y-4 scroll-mt-24">
      <SectionHeader
        number={number}
        title={title}
        isOpen={isOpen}
        onToggle={() => setIsOpen(!isOpen)}
      />
      {isOpen && <div className="space-y-3 pt-2">{children}</div>}
    </div>
  );
};

const BarChart = ({
  values,
  count,
  label,
  height = 'h-6',
}: {
  values: number[];
  count: number;
  label: string;
  height?: string;
}) => {
  const padding = Math.max(0, count - values.length);
  const displayValues = [...values, ...Array(padding).fill(0)];

  return (
    <div className="space-y-1">
      <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
        {label}
      </span>
      <div className="flex gap-1 items-end">
        {displayValues.slice(0, count).map((val, i) => {
          const maxVal = Math.max(...displayValues.slice(0, count), 1);
          const percent = (val / maxVal) * 100;
          return (
            <div
              key={i}
              className={`flex-1 bg-gradient-to-t from-blue-500 to-blue-400 rounded-sm`}
              style={{
                height: `calc(${height} * ${percent / 100})`,
                minHeight: val > 0 ? '4px' : '2px',
                opacity: val > 0 ? 1 : 0.2,
              }}
              title={formatNumber(val, 3)}
            />
          );
        })}
      </div>
    </div>
  );
};

const HorizontalDominance = ({
  kickRatio,
  midRatio,
  highRatio,
}: {
  kickRatio: number;
  midRatio: number;
  highRatio: number;
}) => {
  const total = kickRatio + midRatio + highRatio || 1;
  const kickPercent = (kickRatio / total) * 100;
  const midPercent = (midRatio / total) * 100;
  const highPercent = (highRatio / total) * 100;

  return (
    <div className="space-y-1">
      <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
        Beat Dominance
      </span>
      <div className="flex h-5 gap-px overflow-hidden rounded-sm">
        <div
          className="bg-red-500"
          style={{ width: `${kickPercent}%` }}
          title={`Kick: ${formatNumber(kickRatio, 2)}`}
        />
        <div
          className="bg-yellow-500"
          style={{ width: `${midPercent}%` }}
          title={`Mid: ${formatNumber(midRatio, 2)}`}
        />
        <div
          className="bg-blue-500"
          style={{ width: `${highPercent}%` }}
          title={`High: ${formatNumber(highRatio, 2)}`}
        />
      </div>
      <div className="flex justify-between text-[9px] text-text-secondary gap-1">
        <span>K {formatNumber(kickRatio, 2)}</span>
        <span>M {formatNumber(midRatio, 2)}</span>
        <span>H {formatNumber(highRatio, 2)}</span>
      </div>
    </div>
  );
};

const SimpleTable = <T extends object>({
  data,
  columns,
}: {
  data: T[];
  columns: { key: string; label: string; format?: (v: unknown) => string }[];
}) => (
  <div className="overflow-x-auto">
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr className="border-b border-border">
          {columns.map((col) => (
            <th
              key={col.key}
              className="px-2 py-1 text-left text-[10px] font-mono uppercase tracking-wide text-text-secondary font-normal"
            >
              {col.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.map((row, idx) => (
          <tr
            key={idx}
            className={`border-b border-border ${
              idx % 2 === 0 ? 'bg-bg-secondary' : ''
            }`}
          >
            {columns.map((col) => (
              <td
                key={`${idx}-${col.key}`}
                className="px-2 py-1 text-sm text-text-primary"
              >
                {(() => {
                  const value = (row as Record<string, unknown>)[col.key];
                  return col.format
                    ? col.format(value)
                    : formatNumber(value as number);
                })()}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export function MeasurementDashboard({
  phase1,
}: MeasurementDashboardProps) {
  return (
    <div className="space-y-4">
      {/* 1. Core Metrics */}
      <Section id="section-meas-core" number={1} title="Core Metrics">
        <MetricRow label="BPM" value={formatNumber(phase1.bpm, 1)} />
        <MetricRow
          label="BPM Confidence"
          value={formatNumber(phase1.bpmConfidence, 2)}
        />
        {phase1.bpmPercival !== undefined && phase1.bpmPercival !== null && (
          <MetricRow label="BPM Percival" value={formatNumber(phase1.bpmPercival, 1)} />
        )}
        {phase1.bpmAgreement !== undefined && phase1.bpmAgreement !== null && (
          <MetricRow
            label="BPM Agreement"
            value={phase1.bpmAgreement ? '✓' : '✗'}
          />
        )}
        <MetricRow label="Key" value={phase1.key || '—'} />
        <MetricRow
          label="Key Confidence"
          value={formatNumber(phase1.keyConfidence, 2)}
        />
        {phase1.keyProfile && (
          <MetricRow label="Key Profile" value={phase1.keyProfile} />
        )}
        {phase1.tuningFrequency !== undefined && phase1.tuningFrequency !== null && (
          <MetricRow
            label="Tuning Frequency"
            value={formatNumber(phase1.tuningFrequency, 1)}
          />
        )}
        {phase1.tuningCents !== undefined && phase1.tuningCents !== null && (
          <MetricRow
            label="Tuning Cents"
            value={formatNumber(phase1.tuningCents, 2)}
          />
        )}
        <MetricRow label="Time Signature" value={phase1.timeSignature} />
        <MetricRow
          label="Duration"
          value={formatDuration(phase1.durationSeconds)}
        />
        {phase1.sampleRate !== undefined && phase1.sampleRate !== null && (
          <MetricRow
            label="Sample Rate"
            value={`${(phase1.sampleRate / 1000).toFixed(1)} kHz`}
          />
        )}
      </Section>

      {/* 2. Loudness & Dynamics */}
      <Section id="section-meas-loudness" number={2} title="Loudness & Dynamics">
        <MetricRow label="LUFS (Integrated)" value={formatNumber(phase1.lufsIntegrated, 1)} />
        {phase1.lufsRange !== undefined && phase1.lufsRange !== null && (
          <MetricRow label="LUFS Range" value={formatNumber(phase1.lufsRange, 1)} />
        )}
        {phase1.lufsMomentaryMax !== undefined && phase1.lufsMomentaryMax !== null && (
          <MetricRow label="LUFS Momentary Max" value={formatNumber(phase1.lufsMomentaryMax, 1)} />
        )}
        {phase1.lufsShortTermMax !== undefined && phase1.lufsShortTermMax !== null && (
          <MetricRow label="LUFS Short-Term Max" value={formatNumber(phase1.lufsShortTermMax, 1)} />
        )}
        <MetricRow label="True Peak" value={formatNumber(phase1.truePeak, 2)} />
        {phase1.crestFactor !== undefined && phase1.crestFactor !== null && (
          <MetricRow label="Crest Factor" value={formatNumber(phase1.crestFactor, 2)} />
        )}
        {phase1.dynamicSpread !== undefined && phase1.dynamicSpread !== null && (
          <MetricRow label="Dynamic Spread" value={formatNumber(phase1.dynamicSpread, 2)} />
        )}
        {phase1.dynamicCharacter && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Dynamic Character
              </span>
            </div>
            <MetricRow
              label="Complexity"
              value={formatNumber(phase1.dynamicCharacter.dynamicComplexity, 2)}
            />
            <MetricRow
              label="Loudness Variation"
              value={formatNumber(phase1.dynamicCharacter.loudnessVariation, 2)}
            />
            <MetricRow
              label="Spectral Flatness"
              value={formatNumber(phase1.dynamicCharacter.spectralFlatness, 2)}
            />
            <MetricRow
              label="Log Attack Time"
              value={formatNumber(phase1.dynamicCharacter.logAttackTime, 2)}
            />
            <MetricRow
              label="Attack Time Std Dev"
              value={formatNumber(phase1.dynamicCharacter.attackTimeStdDev, 2)}
            />
          </>
        )}
      </Section>

      {/* 3. Spectral */}
      <Section id="section-meas-spectral" number={3} title="Spectral">
        <div className="space-y-3">
          <div>
            <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
              Spectral Balance
            </span>
            <div className="mt-2 space-y-1.5">
              <MetricRow
                label="Sub Bass"
                value={formatNumber(phase1.spectralBalance.subBass, 2)}
              />
              <MetricRow
                label="Low Bass"
                value={formatNumber(phase1.spectralBalance.lowBass, 2)}
              />
              <MetricRow label="Mids" value={formatNumber(phase1.spectralBalance.mids, 2)} />
              <MetricRow
                label="Upper Mids"
                value={formatNumber(phase1.spectralBalance.upperMids, 2)}
              />
              <MetricRow label="Highs" value={formatNumber(phase1.spectralBalance.highs, 2)} />
              <MetricRow
                label="Brilliance"
                value={formatNumber(phase1.spectralBalance.brilliance, 2)}
              />
            </div>
          </div>
        </div>

        {phase1.spectralDetail && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Spectral Detail
              </span>
            </div>
            {phase1.spectralDetail.spectralCentroidMean !== undefined &&
              phase1.spectralDetail.spectralCentroidMean !== null && (
                <MetricRow
                  label="Spectral Centroid Mean"
                  value={formatNumber(phase1.spectralDetail.spectralCentroidMean, 1)}
                />
              )}
            {phase1.spectralDetail.spectralRolloffMean !== undefined &&
              phase1.spectralDetail.spectralRolloffMean !== null && (
                <MetricRow
                  label="Spectral Rolloff Mean"
                  value={formatNumber(phase1.spectralDetail.spectralRolloffMean, 1)}
                />
              )}
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
                <BarChart
                  values={phase1.spectralDetail.spectralContrast}
                  count={Math.min(7, phase1.spectralDetail.spectralContrast.length)}
                  label="Spectral Contrast"
                />
              )}
            {phase1.spectralDetail.spectralValley &&
              phase1.spectralDetail.spectralValley.length > 0 && (
                <BarChart
                  values={phase1.spectralDetail.spectralValley}
                  count={Math.min(7, phase1.spectralDetail.spectralValley.length)}
                  label="Spectral Valley"
                />
              )}
          </>
        )}

        {phase1.essentiaFeatures && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Essentia Features
              </span>
            </div>
            {phase1.essentiaFeatures.zeroCrossingRate !== undefined &&
              phase1.essentiaFeatures.zeroCrossingRate !== null && (
                <MetricRow
                  label="Zero Crossing Rate"
                  value={formatNumber(phase1.essentiaFeatures.zeroCrossingRate, 3)}
                />
              )}
            {phase1.essentiaFeatures.hfc !== undefined && phase1.essentiaFeatures.hfc !== null && (
              <MetricRow
                label="High Frequency Content"
                value={formatNumber(phase1.essentiaFeatures.hfc, 2)}
              />
            )}
            {phase1.essentiaFeatures.spectralComplexity !== undefined &&
              phase1.essentiaFeatures.spectralComplexity !== null && (
                <MetricRow
                  label="Spectral Complexity"
                  value={formatNumber(phase1.essentiaFeatures.spectralComplexity, 2)}
                />
              )}
            {phase1.essentiaFeatures.dissonance !== undefined &&
              phase1.essentiaFeatures.dissonance !== null && (
                <MetricRow
                  label="Dissonance"
                  value={formatNumber(phase1.essentiaFeatures.dissonance, 2)}
                />
              )}
          </>
        )}
      </Section>

      {/* 4. Stereo Field */}
      <Section id="section-meas-stereo" number={4} title="Stereo Field">
        <MetricRow label="Stereo Width" value={formatNumber(phase1.stereoWidth, 2)} />
        <MetricRow
          label="Stereo Correlation"
          value={formatNumber(phase1.stereoCorrelation, 2)}
        />
        {phase1.stereoDetail && (
          <>
            {phase1.stereoDetail.subBassCorrelation !== undefined &&
              phase1.stereoDetail.subBassCorrelation !== null && (
                <MetricRow
                  label="Sub-Bass Correlation"
                  value={formatNumber(phase1.stereoDetail.subBassCorrelation, 2)}
                />
              )}
            {phase1.stereoDetail.subBassMono !== undefined &&
              phase1.stereoDetail.subBassMono !== null && (
                <MetricRow
                  label="Sub-Bass Mono"
                  value={phase1.stereoDetail.subBassMono ? 'Yes' : 'No'}
                />
              )}
          </>
        )}
        {phase1.segmentStereo && phase1.segmentStereo.length > 0 && (
          <>
            <div className="border-t border-border pt-3 mt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Segment Stereo
              </span>
            </div>
            <SimpleTable
              data={phase1.segmentStereo}
              columns={[
                {
                  key: 'segmentIndex',
                  label: 'Segment',
                  format: (v) => String(v || '—'),
                },
                {
                  key: 'stereoWidth',
                  label: 'Width',
                  format: (v) => formatNumber(v as number, 2),
                },
                {
                  key: 'stereoCorrelation',
                  label: 'Corr',
                  format: (v) => formatNumber(v as number, 2),
                },
              ]}
            />
          </>
        )}
      </Section>

      {/* 5. Rhythm & Groove */}
      <Section id="section-meas-rhythm" number={5} title="Rhythm & Groove">
        {phase1.rhythmDetail && (
          <>
            <MetricRow
              label="Onset Rate"
              value={formatNumber(phase1.rhythmDetail.onsetRate, 2)}
            />
            <MetricRow
              label="Groove Amount"
              value={formatNumber(phase1.rhythmDetail.grooveAmount, 2)}
            />
            {phase1.rhythmDetail.tempoStability !== undefined &&
              phase1.rhythmDetail.tempoStability !== null && (
                <MetricRow
                  label="Tempo Stability"
                  value={`${(phase1.rhythmDetail.tempoStability * 100).toFixed(1)}%`}
                />
              )}
            {phase1.rhythmDetail.phraseGrid && (
              <>
                <div className="border-t border-border pt-3">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                    Phrase Grid
                  </span>
                </div>
                <MetricRow
                  label="4-Bar Phrases"
                  value={formatNumber(phase1.rhythmDetail.phraseGrid.phrases4Bar.length, 0)}
                />
                <MetricRow
                  label="8-Bar Phrases"
                  value={formatNumber(phase1.rhythmDetail.phraseGrid.phrases8Bar.length, 0)}
                />
                <MetricRow
                  label="16-Bar Phrases"
                  value={formatNumber(phase1.rhythmDetail.phraseGrid.phrases16Bar.length, 0)}
                />
                <MetricRow
                  label="Total Bars"
                  value={formatNumber(phase1.rhythmDetail.phraseGrid.totalBars, 0)}
                />
              </>
            )}
          </>
        )}

        {phase1.grooveDetail && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Groove Detail
              </span>
            </div>
            <MetricRow
              label="Kick Swing"
              value={formatNumber(phase1.grooveDetail.kickSwing, 2)}
            />
            <MetricRow
              label="Hi-Hat Swing"
              value={formatNumber(phase1.grooveDetail.hihatSwing, 2)}
            />
            {phase1.grooveDetail.kickAccent && phase1.grooveDetail.kickAccent.length > 0 && (
              <BarChart
                values={phase1.grooveDetail.kickAccent}
                count={4}
                label="Kick Accents"
              />
            )}
            {phase1.grooveDetail.hihatAccent && phase1.grooveDetail.hihatAccent.length > 0 && (
              <BarChart
                values={phase1.grooveDetail.hihatAccent}
                count={4}
                label="Hi-Hat Accents"
              />
            )}
          </>
        )}

        {phase1.beatsLoudness && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Beats & Loudness
              </span>
            </div>
            <HorizontalDominance
              kickRatio={phase1.beatsLoudness.kickDominantRatio}
              midRatio={phase1.beatsLoudness.midDominantRatio}
              highRatio={phase1.beatsLoudness.highDominantRatio}
            />
            {phase1.beatsLoudness.accentPattern &&
              phase1.beatsLoudness.accentPattern.length > 0 && (
                <BarChart
                  values={phase1.beatsLoudness.accentPattern}
                  count={4}
                  label="Accent Pattern"
                  height="h-5"
                />
              )}
            <MetricRow
              label="Mean Beat Loudness"
              value={formatNumber(phase1.beatsLoudness.meanBeatLoudness, 2)}
            />
            <MetricRow
              label="Beat Loudness Variation"
              value={formatNumber(phase1.beatsLoudness.beatLoudnessVariation, 2)}
            />
            <MetricRow
              label="Beat Count"
              value={formatNumber(phase1.beatsLoudness.beatCount, 0)}
            />
          </>
        )}

        {phase1.danceability && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Danceability
              </span>
            </div>
            <MetricRow
              label="Danceability"
              value={formatNumber(phase1.danceability.danceability, 2)}
            />
            <MetricRow label="DFA" value={formatNumber(phase1.danceability.dfa, 3)} />
          </>
        )}
      </Section>

      {/* 6. Harmony */}
      <Section id="section-meas-harmony" number={6} title="Harmony">
        {phase1.chordDetail && (
          <>
            {phase1.chordDetail.progression && phase1.chordDetail.progression.length > 0 && (
              <>
                <div>
                  <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                    Chord Progression
                  </span>
                  <div className="mt-2 text-sm text-text-primary break-words">
                    {phase1.chordDetail.progression.join(' → ')}
                  </div>
                </div>
              </>
            )}
            {phase1.chordDetail.chordSequence && phase1.chordDetail.chordSequence.length > 0 && (
              <>
                <div className="border-t border-border pt-3">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                    Chord Sequence
                  </span>
                  <div className="mt-2 text-sm text-text-primary break-words">
                    {phase1.chordDetail.chordSequence.join(' → ')}
                  </div>
                </div>
              </>
            )}
            {phase1.chordDetail.chordStrength !== undefined &&
              phase1.chordDetail.chordStrength !== null && (
                <MetricRow
                  label="Chord Strength"
                  value={formatNumber(phase1.chordDetail.chordStrength, 2)}
                />
              )}
            {phase1.chordDetail.dominantChords && phase1.chordDetail.dominantChords.length > 0 && (
              <>
                <div className="border-t border-border pt-3">
                  <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                    Dominant Chords
                  </span>
                  <div className="mt-2 text-sm text-text-primary">
                    {phase1.chordDetail.dominantChords.join(', ')}
                  </div>
                </div>
              </>
            )}
          </>
        )}
        {phase1.segmentKey && phase1.segmentKey.length > 0 && (
          <>
            <div className={`${phase1.chordDetail ? 'border-t border-border pt-3 mt-3' : ''}`}>
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Segment Keys
              </span>
            </div>
            <SimpleTable
              data={phase1.segmentKey}
              columns={[
                {
                  key: 'segmentIndex',
                  label: 'Segment',
                  format: (v) => String(v || '—'),
                },
                { key: 'key', label: 'Key' },
                {
                  key: 'keyConfidence',
                  label: 'Confidence',
                  format: (v) => formatNumber(v as number, 2),
                },
              ]}
            />
          </>
        )}
      </Section>

      {/* 7. Structure & Arrangement */}
      <Section id="section-meas-structure" number={7} title="Structure & Arrangement">
        {phase1.structure && (
          <>
            {phase1.structure.segmentCount !== undefined &&
              phase1.structure.segmentCount !== null && (
                <MetricRow
                  label="Segment Count"
                  value={formatNumber(phase1.structure.segmentCount, 0)}
                />
              )}
          </>
        )}
        {phase1.arrangementDetail && (
          <>
            {phase1.arrangementDetail.noveltyMean !== undefined &&
              phase1.arrangementDetail.noveltyMean !== null && (
                <MetricRow
                  label="Novelty Mean"
                  value={formatNumber(phase1.arrangementDetail.noveltyMean, 2)}
                />
              )}
            {phase1.arrangementDetail.noveltyStdDev !== undefined &&
              phase1.arrangementDetail.noveltyStdDev !== null && (
                <MetricRow
                  label="Novelty Std Dev"
                  value={formatNumber(phase1.arrangementDetail.noveltyStdDev, 2)}
                />
              )}
            {phase1.arrangementDetail.sectionCount !== undefined &&
              phase1.arrangementDetail.sectionCount !== null && (
                <MetricRow
                  label="Section Count"
                  value={formatNumber(phase1.arrangementDetail.sectionCount, 0)}
                />
              )}
          </>
        )}
        {phase1.segmentLoudness && phase1.segmentLoudness.length > 0 && (
          <>
            <div className="border-t border-border pt-3 mt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Segment Loudness
              </span>
            </div>
            <SimpleTable
              data={phase1.segmentLoudness}
              columns={[
                {
                  key: 'segmentIndex',
                  label: 'Segment',
                  format: (v) => String(v !== undefined ? v : '—'),
                },
                {
                  key: 'start',
                  label: 'Start (s)',
                  format: (v) => formatNumber(v as number, 1),
                },
                {
                  key: 'end',
                  label: 'End (s)',
                  format: (v) => formatNumber(v as number, 1),
                },
                {
                  key: 'lufs',
                  label: 'LUFS',
                  format: (v) => formatNumber(v as number, 1),
                },
              ]}
            />
          </>
        )}
      </Section>

      {/* 8. Synthesis & Timbre */}
      <Section id="section-meas-synthesis" number={8} title="Synthesis & Timbre">
        {phase1.synthesisCharacter && (
          <>
            {phase1.synthesisCharacter.inharmonicity !== undefined &&
              phase1.synthesisCharacter.inharmonicity !== null && (
                <MetricRow
                  label="Inharmonicity"
                  value={formatNumber(phase1.synthesisCharacter.inharmonicity, 3)}
                />
              )}
            {phase1.synthesisCharacter.oddToEvenRatio !== undefined &&
              phase1.synthesisCharacter.oddToEvenRatio !== null && (
                <MetricRow
                  label="Odd-to-Even Ratio"
                  value={formatNumber(phase1.synthesisCharacter.oddToEvenRatio, 2)}
                />
              )}
            {phase1.synthesisCharacter.analogLike !== undefined &&
              phase1.synthesisCharacter.analogLike !== null && (
                <MetricRow
                  label="Analog-Like"
                  value={phase1.synthesisCharacter.analogLike ? 'Yes' : 'No'}
                />
              )}
          </>
        )}

        {phase1.perceptual && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Perceptual
              </span>
            </div>
            <MetricRow
              label="Sharpness"
              value={formatNumber(phase1.perceptual.sharpness, 2)}
            />
            <MetricRow
              label="Roughness"
              value={formatNumber(phase1.perceptual.roughness, 2)}
            />
          </>
        )}

        {phase1.sidechainDetail && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Sidechain / Pumping
              </span>
            </div>
            <MetricRow
              label="Pumping Strength"
              value={formatNumber(phase1.sidechainDetail.pumpingStrength, 2)}
            />
            <MetricRow
              label="Pumping Regularity"
              value={formatNumber(phase1.sidechainDetail.pumpingRegularity, 2)}
            />
            {phase1.sidechainDetail.pumpingRate && (
              <MetricRow label="Pumping Rate" value={phase1.sidechainDetail.pumpingRate} />
            )}
            <MetricRow
              label="Pumping Confidence"
              value={formatNumber(phase1.sidechainDetail.pumpingConfidence, 2)}
            />
            {phase1.sidechainDetail.envelopeShape &&
              phase1.sidechainDetail.envelopeShape.length > 0 && (
                <BarChart
                  values={phase1.sidechainDetail.envelopeShape.slice(0, 16)}
                  count={16}
                  label="Pumping Shape"
                  height="h-8"
                />
              )}
          </>
        )}

        {phase1.effectsDetail && (
          <>
            <div className="border-t border-border pt-3">
              <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
                Effects
              </span>
            </div>
            {phase1.effectsDetail.gatingDetected !== undefined &&
              phase1.effectsDetail.gatingDetected !== null && (
                <MetricRow
                  label="Gating Detected"
                  value={phase1.effectsDetail.gatingDetected ? 'Yes' : 'No'}
                />
              )}
            {phase1.effectsDetail.gatingRate !== undefined &&
              phase1.effectsDetail.gatingRate !== null && (
                <MetricRow
                  label="Gating Rate"
                  value={formatNumber(phase1.effectsDetail.gatingRate, 2)}
                />
              )}
            {phase1.effectsDetail.gatingRegularity !== undefined &&
              phase1.effectsDetail.gatingRegularity !== null && (
                <MetricRow
                  label="Gating Regularity"
                  value={formatNumber(phase1.effectsDetail.gatingRegularity, 2)}
                />
              )}
            {phase1.effectsDetail.gatingEventCount !== undefined &&
              phase1.effectsDetail.gatingEventCount !== null && (
                <MetricRow
                  label="Gating Event Count"
                  value={formatNumber(phase1.effectsDetail.gatingEventCount, 0)}
                />
              )}
          </>
        )}
      </Section>
    </div>
  );
}

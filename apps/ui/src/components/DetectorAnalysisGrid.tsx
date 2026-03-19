import React from 'react';
import type { MeasurementResult } from '../types';
import {
  describeSidechain,
  describeAcid,
  describeReverb,
  describeBassCharacter,
  describeKick,
  describeSupersaw,
  describeVocal,
  describeGenre,
  describeSynthesis,
} from '../services/detectorMusicalContext';

interface DetectorAnalysisGridProps {
  measurement: MeasurementResult;
}

function DetectorContextText({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <div className="mt-3 border-l-2 border-accent bg-accent/5 px-2 py-2 rounded-sm">
      <p className="text-[10px] font-mono text-accent uppercase tracking-wide">PRO TIP</p>
      <p className="text-xs font-mono text-text-secondary mt-1 leading-relaxed">{text}</p>
    </div>
  );
}

export function DetectorAnalysisGrid({ measurement }: DetectorAnalysisGridProps) {
  const {
    acidDetail,
    reverbDetail,
    vocalDetail,
    supersawDetail,
    bassDetail,
    kickDetail,
    genreDetail,
    sidechainDetail,
    synthesisCharacter,
  } = measurement;

  const hasAny = acidDetail || reverbDetail || vocalDetail || supersawDetail ||
    bassDetail || kickDetail || genreDetail || sidechainDetail || synthesisCharacter;
  if (!hasAny) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between border-b border-border pb-2">
        <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
          <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
          Detector Analysis
        </h2>
        <span className="text-[10px] font-mono bg-bg-panel border border-border px-2 py-1 rounded font-bold text-text-secondary">
          PHASE 1
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {acidDetail && (
          <div className="bg-bg-card border border-border rounded-sm p-4">
            <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-2">Acid Bass</p>
            <p className="text-xl font-display font-bold text-text-primary">{acidDetail.isAcid ? 'DETECTED' : 'NOT DETECTED'}</p>
            <p className="text-xs font-mono text-text-secondary mt-1">Confidence: {(acidDetail.confidence * 100).toFixed(0)}%</p>
            {acidDetail.isAcid && (
              <p className="text-xs font-mono text-text-secondary">Resonance: {acidDetail.resonanceLevel.toFixed(2)}</p>
            )}
            <DetectorContextText text={describeAcid(acidDetail)} />
          </div>
        )}
        {reverbDetail && (
          <div className="bg-bg-card border border-border rounded-sm p-4">
            <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-2">Reverb</p>
            <p className="text-xl font-display font-bold text-text-primary">{reverbDetail.isWet ? 'WET' : 'DRY'}</p>
            {reverbDetail.measured && reverbDetail.rt60 !== null ? (
              <p className="text-xs font-mono text-text-secondary mt-1">RT60: {reverbDetail.rt60.toFixed(2)}s</p>
            ) : (
              <p className="text-xs font-mono text-text-secondary mt-1 opacity-50">RT60: N/A</p>
            )}
            <DetectorContextText text={describeReverb(reverbDetail)} />
          </div>
        )}
        {vocalDetail && (
          <div className="bg-bg-card border border-border rounded-sm p-4">
            <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-2">Vocals</p>
            <p className="text-xl font-display font-bold text-text-primary">{vocalDetail.hasVocals ? 'PRESENT' : 'ABSENT'}</p>
            <p className="text-xs font-mono text-text-secondary mt-1">Confidence: {(vocalDetail.confidence * 100).toFixed(0)}%</p>
            <DetectorContextText text={describeVocal(vocalDetail)} />
          </div>
        )}
        {supersawDetail && (
          <div className="bg-bg-card border border-border rounded-sm p-4">
            <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-2">Supersaw</p>
            <p className="text-xl font-display font-bold text-text-primary">{supersawDetail.isSupersaw ? 'DETECTED' : 'NOT DETECTED'}</p>
            <p className="text-xs font-mono text-text-secondary mt-1">Confidence: {(supersawDetail.confidence * 100).toFixed(0)}%</p>
            {supersawDetail.isSupersaw && (
              <p className="text-xs font-mono text-text-secondary">Voices: {supersawDetail.voiceCount}</p>
            )}
            <DetectorContextText text={describeSupersaw(supersawDetail)} />
          </div>
        )}
        {bassDetail && (
          <div className="bg-bg-card border border-border rounded-sm p-4">
            <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-2">Bass Character</p>
            <p className="text-xl font-display font-bold text-text-primary uppercase">{bassDetail.type}</p>
            <p className="text-xs font-mono text-text-secondary mt-1">Decay: {bassDetail.averageDecayMs.toFixed(0)}ms</p>
            <p className="text-xs font-mono text-text-secondary">Groove: {bassDetail.grooveType}</p>
            <DetectorContextText text={describeBassCharacter(bassDetail)} />
          </div>
        )}
        {kickDetail && (
          <div className="bg-bg-card border border-border rounded-sm p-4">
            <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-2">Kick</p>
            <p className="text-xl font-display font-bold text-text-primary">{kickDetail.kickCount} HITS</p>
            <p className="text-xs font-mono text-text-secondary mt-1">Fundamental: {kickDetail.fundamentalHz.toFixed(0)}Hz</p>
            {kickDetail.isDistorted && (
              <p className="text-xs font-mono text-accent mt-1">DISTORTED</p>
            )}
            <DetectorContextText text={describeKick(kickDetail)} />
          </div>
        )}
        {genreDetail && (
          <div className="bg-bg-card border border-border rounded-sm p-4">
            <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-2">Genre Classification</p>
            <p className="text-xl font-display font-bold text-text-primary">
              {genreDetail.genre.replace(/-/g, ' ').toUpperCase()}
            </p>
            <p className="text-xs font-mono text-text-secondary mt-1">
              Confidence: {(genreDetail.confidence * 100).toFixed(0)}%
              {genreDetail.confidence < 0.5 && <span className="text-accent ml-1">(uncertain)</span>}
            </p>
            <p className="text-xs font-mono text-text-secondary">Family: {genreDetail.genreFamily}</p>
            {genreDetail.secondaryGenre && (
              <p className="text-xs font-mono text-text-secondary">
                Secondary: {genreDetail.secondaryGenre.replace(/-/g, ' ')}
              </p>
            )}
            <DetectorContextText text={describeGenre(genreDetail)} />
          </div>
        )}
        {sidechainDetail && (
          <div className="bg-bg-card border border-border rounded-sm p-4">
            <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-2">Sidechain</p>
            <p className="text-xl font-display font-bold text-text-primary">
              {(sidechainDetail.pumpingStrength * 100).toFixed(0)}% PUMP
            </p>
            {sidechainDetail.pumpingRate && (
              <p className="text-xs font-mono text-text-secondary mt-1">Rate: {sidechainDetail.pumpingRate}</p>
            )}
            <p className="text-xs font-mono text-text-secondary">
              Confidence: {(sidechainDetail.pumpingConfidence * 100).toFixed(0)}%
            </p>
            <DetectorContextText text={describeSidechain(sidechainDetail)} />
          </div>
        )}
        {synthesisCharacter && (() => {
          const synthLabel = synthesisCharacter.inharmonicity > 0.25 ? 'WAVETABLE / NOISE'
            : synthesisCharacter.inharmonicity >= 0.10 ? 'FM / ACID'
            : 'CLEAN SUBTRACTIVE';
          const waveLabel = synthesisCharacter.oddToEvenRatio > 1.5 ? 'Saw / Square'
            : synthesisCharacter.oddToEvenRatio < 0.8 ? 'Sine / Triangle'
            : 'Mixed Harmonics';
          return (
            <div className="bg-bg-card border border-border rounded-sm p-4">
              <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-2">Synthesis Character</p>
              <p className="text-xl font-display font-bold text-text-primary">{synthLabel}</p>
              <p className="text-xs font-mono text-text-secondary mt-1">
                Inharmonicity: {synthesisCharacter.inharmonicity.toFixed(3)}
              </p>
              <p className="text-xs font-mono text-text-secondary">Waveform: {waveLabel}</p>
              <p className="text-xs font-mono text-text-secondary">
                Odd/Even Ratio: {synthesisCharacter.oddToEvenRatio.toFixed(2)}
              </p>
              <DetectorContextText text={describeSynthesis(synthesisCharacter)} />
            </div>
          );
        })()}
      </div>
    </div>
  );
}

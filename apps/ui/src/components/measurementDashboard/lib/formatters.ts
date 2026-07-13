import type { MeasurementAvailabilityContext, Phase1Result } from '../../../types';

// Pure formatting / math / predicate helpers for the Measurement Dashboard,
// moved verbatim out of the MeasurementDashboard monolith (Phase 4 split) so
// the extracted panels and the main component share one source.

export const formatNumber = (value: number | null | undefined, decimals = 2): string => {
  if (value === null || value === undefined) return '—';
  return typeof value === 'number' ? value.toFixed(decimals) : '—';
};

export const formatDuration = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

export const isAssumedMeter = (phase1: Phase1Result): boolean =>
  phase1.timeSignatureSource === 'assumed_four_four' || (phase1.timeSignatureConfidence ?? 1) <= 0;

export const resolveBarCount = (phase1: Phase1Result): number => {
  const phraseGridBars = phase1.rhythmDetail?.phraseGrid?.totalBars;
  if (typeof phraseGridBars === 'number' && Number.isFinite(phraseGridBars) && phraseGridBars > 0) {
    return phraseGridBars;
  }

  const beatsPerBar = parseInt(phase1.timeSignature?.split('/')[0] || '4', 10) || 4;
  const totalBeats = (phase1.durationSeconds / 60) * phase1.bpm;
  return Math.floor(totalBeats / beatsPerBar);
};

export const lufsToPercent = (value: number, min = -60, max = 0): number =>
  Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));

export const asFiniteNumber = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  return null;
};

export const clamp = (value: number, min: number, max: number): number =>
  Math.max(min, Math.min(max, value));

export const normalizePercent = (value: number, min: number, max: number): number => {
  if (max === min) return 0;
  return clamp(((value - min) / (max - min)) * 100, 0, 100);
};

export const formatAnalysisModeLabel = (
  analysisMode?: MeasurementAvailabilityContext['analysisMode'],
): string => {
  if (analysisMode === 'full') return 'full run';
  if (analysisMode === 'standard') return 'standard run';
  return 'run';
};

export const buildDynamicsTextureCopy = (
  kind: 'both' | 'dynamics' | 'texture',
  measurementAvailability?: MeasurementAvailabilityContext,
): {
  title: string;
  description: string;
  detail?: string;
} => {
  if (!measurementAvailability?.hasRunContext) {
    if (kind === 'both') {
      return {
        title: 'Measurements unavailable',
        description: 'This payload does not include dynamics or texture detail.',
      };
    }

    return {
      title: `${kind === 'dynamics' ? 'Dynamics' : 'Texture'} unavailable`,
      description: `This payload does not include ${kind} measurements.`,
    };
  }

  const runLabel = formatAnalysisModeLabel(measurementAvailability.analysisMode);

  if (kind === 'both') {
    return {
      title: 'Measurements not included in this run',
      description: `This ${runLabel} completed without dynamics or texture detail.`,
      detail: 'This usually means an older backend or partial measurement output.',
    };
  }

  return {
    title: `${kind === 'dynamics' ? 'Dynamics' : 'Texture'} unavailable`,
    description: `This ${runLabel} did not include ${kind} measurements.`,
    detail: 'This usually means an older backend or partial measurement output.',
  };
};

export const correlationPercent = (value: number | null | undefined): number =>
  typeof value === 'number' ? normalizePercent(value, -1, 1) : 0;

export const isDynamicCharacterObject = (
  value: Phase1Result['dynamicCharacter'],
): value is NonNullable<Phase1Result['dynamicCharacter']> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export const isTextureCharacterObject = (
  value: Phase1Result['textureCharacter'],
): value is NonNullable<Phase1Result['textureCharacter']> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export const chordToneForLabel = (
  chord: string,
): 'accent' | 'violet' | 'error' | 'warning' | 'muted' => {
  const normalized = chord.trim().toLowerCase();
  if (!normalized) return 'muted';
  if (/(dim|°|o)(?![a-z])/.test(normalized)) return 'error';
  if (/(aug|\+)/.test(normalized)) return 'warning';
  if (/(^|[^a-z])m(?!aj)/.test(normalized) || /min/.test(normalized)) return 'violet';
  if (/[a-g](maj|sus|add|7|9|11|13)?/.test(normalized)) return 'accent';
  return 'muted';
};

export const loudnessToneColor = (value: number | null | undefined): string => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'var(--color-text-secondary)';
  if (value >= -8) return '#ff6b00';
  if (value >= -12) return '#ffb347';
  if (value >= -16) return '#ffd166';
  return '#a3e635';
};

export const formatSigned = (value: number | null | undefined, decimals = 1): string => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}`;
};

import type { Phase1Result } from '../../../types';
import type { Tone } from '../../ui';

// Shared constants for the Measurement Dashboard, moved verbatim out of the
// MeasurementDashboard monolith (Phase 4 split) so the extracted panels and
// the main component can share one source.

export type LegacyBadgeTone = Tone | 'muted' | 'info' | 'violet';

// Local adapter palette for the dashboard's StatusBadge sugar over ui/Pill —
// maps the legacy off-palette tones (muted/info/violet, still emitted by
// chordToneForLabel) onto the canonical token palette in one spot.
export const PILL_TONE_FOR_LEGACY: Record<LegacyBadgeTone, Tone> = {
  accent: 'accent',
  success: 'success',
  warning: 'warning',
  error: 'error',
  neutral: 'neutral',
  muted: 'neutral',
  info: 'neutral',
  violet: 'neutral',
};

export const LUFS_METER_GRADIENT = `linear-gradient(to right,
  rgba(0,255,157,0.7) 0%,
  rgba(0,255,157,0.7) 60%,
  rgba(255,184,0,0.7) 60%,
  rgba(255,184,0,0.7) 76.7%,
  rgba(255,136,0,0.8) 76.7%,
  rgba(255,136,0,0.8) 90%,
  rgba(255,51,51,0.8) 90%,
  rgba(255,51,51,0.8) 100%
)`;

export const PLATFORM_REFS = [
  { lufs: -14, label: 'SPOT' },
  { lufs: -16, label: 'APPL' },
  { lufs: -23, label: 'BDCST' },
];

export const SPECTRAL_BALANCE_PALETTE: Record<
  keyof Phase1Result['spectralBalance'],
  string
> = {
  subBass: '#ff6b00',
  lowBass: '#fb923c',
  lowMids: '#f59e0b',
  mids: '#facc15',
  upperMids: '#14b8a6',
  highs: '#38bdf8',
  brilliance: '#a78bfa',
};

export const SPECTRAL_ROW_CONFIG: Array<{
  key: keyof Phase1Result['spectralBalance'];
  label: string;
}> = [
  { key: 'subBass', label: 'Sub Bass' },
  { key: 'lowBass', label: 'Low Bass' },
  { key: 'lowMids', label: 'Low Mids' },
  { key: 'mids', label: 'Mids' },
  { key: 'upperMids', label: 'Upper Mids' },
  { key: 'highs', label: 'Highs' },
  { key: 'brilliance', label: 'Brilliance' },
];

export const SPECTRAL_CHART_PALETTE = [
  '#ff6b00',
  '#ff8c42',
  '#f59e0b',
  '#facc15',
  '#14b8a6',
  '#38bdf8',
  '#60a5fa',
  '#a78bfa',
];

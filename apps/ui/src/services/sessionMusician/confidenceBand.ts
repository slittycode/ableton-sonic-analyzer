// Confidence-band semantics for the Session Musician panel.
//
// The four bands translate a raw 0-1 confidence number into producer action:
// what the label is, what to do with the data, and the audit-friendly percent.
// Both the stem note draft (Block A) and the melody contour (Block B) use the
// same ladder; the block's subtitle establishes which signal the band applies
// to.

export type ConfidenceBandId = 'solid' | 'workable' | 'rough' | 'unreliable';

export interface ConfidenceBand {
  id: ConfidenceBandId;
  label: string;
  copy: string;
  minInclusive: number;
}

// Sorted descending by minInclusive so the first match wins. The last entry
// has minInclusive: 0 so any finite number lands somewhere.
const BANDS: readonly ConfidenceBand[] = [
  {
    id: 'solid',
    label: 'Solid scaffold',
    copy: "Notes look reliable. Expect light cleanup in Ableton's piano roll.",
    minInclusive: 0.8,
  },
  {
    id: 'workable',
    label: 'Workable draft',
    copy: 'Most notes are in the right ballpark. Plan to redraw the trickiest bars.',
    minInclusive: 0.5,
  },
  {
    id: 'rough',
    label: 'Rough sketch',
    copy: 'Pitch tracking caught the general shape. Treat this as a rhythm grid more than note truth.',
    minInclusive: 0.25,
  },
  {
    id: 'unreliable',
    label: 'Unreliable',
    copy: "The pitch detector wasn't confident. Use the pitch range and most-played notes as scale hints — don't trust specific notes.",
    minInclusive: 0,
  },
];

export function getConfidenceBand(confidence: number): ConfidenceBand {
  const safe = Number.isFinite(confidence) ? confidence : 0;
  for (const band of BANDS) {
    if (safe >= band.minInclusive) return band;
  }
  // Defensive fallback. Unreachable because the last band has minInclusive: 0.
  return BANDS[BANDS.length - 1];
}

export function formatBandPillLabel(band: ConfidenceBand, confidence: number): string {
  const safe = Number.isFinite(confidence) ? confidence : 0;
  const percent = Math.max(0, Math.min(100, Math.round(safe * 100)));
  return `${band.label} · ${percent}%`;
}

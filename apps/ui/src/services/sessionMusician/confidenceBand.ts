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

// Audit Finding #4: every site that today expresses confidence as a string
// enum (HIGH/MED/LOW), a 0-100 percent, or a plain 0-1 scalar can route
// through this normalizer to land on the canonical four-band ladder. Each
// string enum maps to the middle of its target band so `formatBandPillLabel`
// reads as an honest percentage (HIGH → 0.9 → "Solid scaffold · 90%",
// not a band-boundary value like 0.8 → "Solid scaffold · 80%" which would
// imply a precision the string enum doesn't carry).
//
// Returns `null` when input is unparseable so callers can choose a fallback
// rather than render a misleading "Unreliable" band on bad data.
export function toConfidenceBand(
  value: number | string | null | undefined,
): ConfidenceBand | null {
  if (value === null || value === undefined) return null;

  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return null;
    const clamped =
      value > 1 && value <= 100
        ? value / 100
        : Math.max(0, Math.min(1, value));
    return getConfidenceBand(clamped);
  }

  const trimmed = value.trim();
  if (trimmed.length === 0) return null;
  const lower = trimmed.toLowerCase();

  if (lower.includes('high')) return getConfidenceBand(0.9);
  if (lower === 'med' || lower.includes('medium') || lower.includes('moderate')) {
    return getConfidenceBand(0.6);
  }
  if (lower.includes('low')) return getConfidenceBand(0.3);

  // Fall through: try to parse as a scalar (handles "62%", "0.62", "62").
  const cleaned = trimmed.replace(/%\s*$/, '');
  const parsed = Number.parseFloat(cleaned);
  if (!Number.isFinite(parsed)) return null;
  return toConfidenceBand(parsed);
}

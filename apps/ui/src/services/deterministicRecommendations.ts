import {
  getFXRecommendations,
  getInstrumentRecommendations,
  getSecretSauce,
  type AudioFeatures,
  type SpectralBandEnergy,
} from '../data/abletonDevices';
import type { Phase1Result, Phase2Result } from '../types';
import type { AnalysisStageStatus } from '../types/backend';

// Product adapter for the deterministic Live 12 recommendation engine
// (`src/data/abletonDevices.ts`) — the Phase-2-off fallback wired by the
// 2026-07-02 reversal of the 2026-06-11 demotion decision. Unlike the eval
// bridge (`apps/backend/scripts/emit_deterministic_recs.ts`, uncited by
// design), every card emitted here carries the Phase 1 field(s) that
// triggered it (PURPOSE.md invariant #2); a card whose driving measurement
// is weak is hedged or skipped (invariant #4), and a card whose trigger has
// no citation mapping is dropped rather than rendered uncited.

export interface DeterministicCard {
  id: string;
  kind: 'instrument' | 'fx' | 'secretSauce';
  /** Exact Live 12 device the card is anchored on. */
  device: string;
  title: string;
  detail: string;
  /** Phase 1 citation paths — always at least one. */
  phase1Fields: string[];
  /** Invariant-#4 disclosures appended when a driving measurement is weak. */
  hedges: string[];
}

/**
 * Show the fallback only once interpretation is settled and produced nothing
 * displayable — never while Phase 2 is pending, so the section doesn't flash
 * mid-run and vanish when recommendations land. `completed` with a null
 * phase2 means interpretation terminally produced nothing renderable.
 */
export function shouldShowDeterministicFallback(
  phase2: Phase2Result | null,
  interpretationStatus: AnalysisStageStatus | null | undefined,
): boolean {
  if (phase2) return false;
  return (
    interpretationStatus == null ||
    interpretationStatus === 'not_requested' ||
    interpretationStatus === 'failed' ||
    interpretationStatus === 'interrupted' ||
    interpretationStatus === 'completed'
  );
}

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

// Engine band vocabulary ↔ spectralBalance camelCase keys and JSON_SCHEMA.md
// band edges. Order matches the backend's 7-band contract.
const BANDS: Array<{ name: string; key: keyof Phase1Result['spectralBalance']; rangeHz: [number, number] }> = [
  { name: 'Sub Bass', key: 'subBass', rangeHz: [20, 80] },
  { name: 'Low Bass', key: 'lowBass', rangeHz: [80, 250] },
  { name: 'Low Mids', key: 'lowMids', rangeHz: [250, 500] },
  { name: 'Mids', key: 'mids', rangeHz: [500, 2000] },
  { name: 'Upper Mids', key: 'upperMids', rangeHz: [2000, 5000] },
  { name: 'Highs', key: 'highs', rangeHz: [5000, 10000] },
  { name: 'Brilliance', key: 'brilliance', rangeHz: [10000, 20000] },
];

const BAND_KEY_BY_NAME = new Map(BANDS.map((b) => [b.name, b.key]));

// spectralBalance is dB *relative* to an arbitrary reference (JSON_SCHEMA.md),
// so dominance is judged against the median of the 7 bands rather than any
// absolute level: ≥ +3 dB over median is a defining element, within 12 dB is
// present, further down is absent.
const DOMINANT_OVER_MEDIAN_DB = 3;
const ABSENT_UNDER_MEDIAN_DB = -12;

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

export function classifySpectralBands(phase1: Phase1Result): SpectralBandEnergy[] {
  const balance = phase1.spectralBalance;
  if (!balance) return [];
  const present = BANDS.filter(({ key }) => finite(balance[key]));
  if (present.length === 0) return [];
  const mid = median(present.map(({ key }) => balance[key]));

  return present.map(({ name, key, rangeHz }) => {
    const averageDb = Math.round(balance[key] * 10) / 10;
    const series = phase1.spectralBalanceTimeSeries;
    const seriesValues = (series ?? [])
      .map((point) => point[key])
      .filter((value): value is number => finite(value));
    const peakDb = seriesValues.length > 0
      ? Math.round(Math.max(...seriesValues) * 10) / 10
      : averageDb;
    const delta = balance[key] - mid;
    const dominance: SpectralBandEnergy['dominance'] =
      delta >= DOMINANT_OVER_MEDIAN_DB ? 'dominant' : delta >= ABSENT_UNDER_MEDIAN_DB ? 'present' : 'absent';
    return { name, rangeHz, averageDb, peakDb, dominance };
  });
}

export function projectAudioFeatures(phase1: Phase1Result): AudioFeatures {
  // NaN sentinels make the engine's numeric comparisons all fail on
  // fast-mode payloads that null these out, cleanly skipping those rules.
  const keyText = typeof phase1.key === 'string' ? phase1.key.trim() : '';
  const spaceIndex = keyText.indexOf(' ');
  const root = spaceIndex > 0 ? keyText.slice(0, spaceIndex) : keyText;
  const scale = spaceIndex > 0 ? keyText.slice(spaceIndex + 1).toLowerCase() : '';

  return {
    bpm: phase1.bpm,
    key: { root: root || '?', scale },
    crestFactor: finite(phase1.crestFactor) ? phase1.crestFactor : NaN,
    onsetDensity: finite(phase1.rhythmDetail?.onsetRate) ? phase1.rhythmDetail.onsetRate : NaN,
    duration: phase1.durationSeconds,
    bpmConfidence: finite(phase1.bpmConfidence) ? Math.min(1, Math.max(0, phase1.bpmConfidence)) : 0,
    spectralBands: classifySpectralBands(phase1),
    spectralCentroidMean: finite(phase1.spectralDetail?.spectralCentroidMean)
      ? phase1.spectralDetail.spectralCentroidMean
      : NaN,
  };
}

// Citation maps keyed on the engine's exact rule-output strings. An engine
// rule with no entry here produces an UNCITED card, which we refuse to render
// — the coverage tests in deterministicRecommendations.test.ts sweep every
// rule so drift fails loudly instead of silently dropping advice.
const FX_ARTIFACT_MAP: Record<string, { slug: string; device: string; fields: string[] }> = {
  'Heavy dynamic compression detected (low crest factor)': {
    slug: 'crest-low', device: 'Glue Compressor', fields: ['crestFactor'],
  },
  'Moderate compression / controlled dynamics': {
    slug: 'crest-moderate', device: 'Compressor', fields: ['crestFactor'],
  },
  'High dynamic range — minimal compression': {
    slug: 'crest-high', device: 'Glue Compressor', fields: ['crestFactor'],
  },
  'Dominant sub-bass energy detected': {
    slug: 'sub-dominant', device: 'Saturator', fields: ['spectralBalance.subBass'],
  },
  'Bright overall spectrum — high spectral centroid': {
    slug: 'bright', device: 'EQ Eight', fields: ['spectralDetail.spectralCentroidMean'],
  },
  'Dark overall spectrum — low spectral centroid': {
    slug: 'dark', device: 'EQ Eight', fields: ['spectralDetail.spectralCentroidMean'],
  },
  'High rhythmic density detected (many transients)': {
    slug: 'dense', device: 'Drum Buss', fields: ['rhythmDetail.onsetRate'],
  },
  'Low transient density — sustained/ambient content': {
    slug: 'sparse', device: 'Reverb', fields: ['rhythmDetail.onsetRate', 'durationSeconds'],
  },
};

// Sauce tricks embed dynamic values ("… at 128 BPM"), so match on prefix.
const SAUCE_TRICK_MAP: Array<{ prefix: string; device: string; fields: (phase1: Phase1Result, bands: SpectralBandEnergy[]) => string[] }> = [
  {
    prefix: 'Wall-of-Sound Layering',
    device: 'Glue Compressor',
    fields: (_phase1, bands) => [
      ...bands.filter((b) => b.dominance === 'dominant')
        .map((b) => `spectralBalance.${BAND_KEY_BY_NAME.get(b.name) ?? ''}`)
        .filter((f) => !f.endsWith('.')),
      'crestFactor',
    ],
  },
  {
    prefix: 'Tight Rhythmic Programming',
    device: 'Drum Rack',
    fields: () => ['rhythmDetail.onsetRate', 'bpm', 'bpmConfidence'],
  },
  {
    prefix: 'Air and Presence Engineering',
    device: 'EQ Eight',
    fields: () => ['spectralDetail.spectralCentroidMean', 'spectralBalance.brilliance'],
  },
  {
    prefix: 'Sub Bass Design and Low-End Control',
    device: 'Operator',
    fields: () => ['spectralBalance.subBass'],
  },
  {
    prefix: 'Balanced Mix Architecture',
    device: 'EQ Eight',
    fields: () => ['bpm', 'key'],
  },
];

interface FundamentalHedge {
  hedge: string | null;
  skip: boolean;
}

function fundamentalHedge(
  phase1: Phase1Result,
  domainKey: 'tempo' | 'key',
  scalarConfidence: number | null,
): FundamentalHedge {
  const domain = phase1.fundamentalsQuality?.domains?.[domainKey];
  if (domain?.status === 'failed') return { hedge: null, skip: true };
  const weakScalar = scalarConfidence !== null && scalarConfidence <= 0.6;
  const weakDomain = domain != null && domain.status !== 'authoritative';
  if (weakDomain && domain.plainEnglish) return { hedge: domain.plainEnglish, skip: false };
  if (weakScalar) {
    return {
      hedge: domainKey === 'tempo'
        ? 'Tempo confidence is low — verify the BPM by ear before building on this.'
        : 'Key confidence is low — confirm the key by ear before committing.',
      skip: false,
    };
  }
  return { hedge: null, skip: false };
}

function cardHedges(phase1: Phase1Result, fields: string[]): { hedges: string[]; skip: boolean } {
  const hedges: string[] = [];
  if (fields.includes('bpm') || fields.includes('bpmConfidence')) {
    const { hedge, skip } = fundamentalHedge(
      phase1,
      'tempo',
      finite(phase1.bpmConfidence) ? phase1.bpmConfidence : null,
    );
    if (skip) return { hedges, skip: true };
    if (hedge) hedges.push(hedge);
  }
  if (fields.includes('key')) {
    if (typeof phase1.key !== 'string' || phase1.key.length === 0) return { hedges, skip: true };
    const { hedge, skip } = fundamentalHedge(
      phase1,
      'key',
      finite(phase1.keyConfidence) ? phase1.keyConfidence : null,
    );
    if (skip) return { hedges, skip: true };
    if (hedge) hedges.push(hedge);
  }
  return { hedges, skip: false };
}

export function buildDeterministicAdvice(phase1: Phase1Result): DeterministicCard[] {
  const features = projectAudioFeatures(phase1);
  const cards: DeterministicCard[] = [];

  for (const inst of getInstrumentRecommendations(features.spectralBands)) {
    const bandName = inst.element.replace(/ Element$/, '');
    const bandKey = BAND_KEY_BY_NAME.get(bandName);
    if (!bandKey) continue; // unknown band — refuse to render uncited
    const [device] = inst.abletonDevice.split(' — ');
    const fields = [`spectralBalance.${bandKey}`];
    if ((phase1.spectralBalanceTimeSeries?.length ?? 0) > 0) {
      fields.push('spectralBalanceTimeSeries');
    }
    cards.push({
      id: `det.band.${bandKey}`,
      kind: 'instrument',
      device: device?.trim() ?? inst.abletonDevice,
      title: `${inst.element} · ${inst.frequency}`,
      detail: `${inst.timbre} ${inst.abletonDevice}`,
      phase1Fields: fields,
      hedges: [],
    });
  }

  for (const fx of getFXRecommendations(features)) {
    const mapping = FX_ARTIFACT_MAP[fx.artifact];
    if (!mapping) continue; // unmapped rule — refuse to render uncited
    cards.push({
      id: `det.fx.${mapping.slug}`,
      kind: 'fx',
      device: mapping.device,
      title: fx.artifact,
      detail: fx.recommendation,
      phase1Fields: mapping.fields,
      hedges: [],
    });
  }

  const sauce = getSecretSauce(features);
  const sauceMapping = SAUCE_TRICK_MAP.find((entry) => sauce.trick.startsWith(entry.prefix));
  if (sauceMapping) {
    const fields = sauceMapping.fields(phase1, features.spectralBands);
    const { hedges, skip } = cardHedges(phase1, fields);
    if (!skip && fields.length > 0) {
      cards.push({
        id: 'det.sauce',
        kind: 'secretSauce',
        device: sauceMapping.device,
        title: sauce.trick,
        detail: sauce.execution,
        phase1Fields: fields,
        hedges,
      });
    }
  }

  // Apply tempo/key hedges to the non-sauce cards that cite them (none today
  // — FX/instrument rules are spectrum/dynamics-driven — but the pass keeps
  // the invariant local if a future rule cites a fundamental).
  return cards.map((card) => {
    if (card.kind === 'secretSauce') return card;
    const { hedges, skip } = cardHedges(phase1, card.phase1Fields);
    if (skip) return null;
    return hedges.length > 0 ? { ...card, hedges: [...card.hedges, ...hedges] } : card;
  }).filter((card): card is DeterministicCard => card !== null);
}

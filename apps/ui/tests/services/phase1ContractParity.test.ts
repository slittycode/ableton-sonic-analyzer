/**
 * Cross-boundary Phase 1 contract gate — kills the silent-field-drop bug class.
 *
 * The Phase 1 contract lives in three hand-maintained forms (analyze.py output,
 * JSON_SCHEMA.md, src/types/measurement.ts) and the parser in
 * backendPhase1Client.ts reconstructs the payload field-by-field, so a field
 * added or renamed on the backend but missed in the parser enumeration simply
 * vanishes — no type error, no runtime error (CLAUDE.md tripwires #3/#4; the
 * 2026-05-30 full review lost reverbDetail.perBandRt60/preDelayMs and
 * vocalDetail.stemEnergyRatio/stemOtherCorrelation exactly this way).
 *
 * This suite makes the boundary executable, against the backend's committed
 * golden snapshot (apps/backend/tests/fixtures/golden/phase1_default.json):
 *
 *   Gate A1 — every golden top-level key exists (non-null) in the canonical
 *             frontend fixture, so Gate B exercises every parser branch.
 *   Gate A2 — every fixture top-level key is a golden key or a declared
 *             envelope addition (catches fixture rot on backend deletions).
 *   Gate A3 — when the golden carries a `keyTree` (nested-structure snapshot),
 *             every nested key the backend emitted exists in the fixture.
 *             Auto-arms on the next golden re-baseline; skipped (visibly) on
 *             goldens that predate keyTree.
 *   Gate B  — the fixture survives the REAL parsePhase1Result with every
 *             non-null input path still present: no silent drops.
 *   Gate C  — the canonical run path (parseAnalysisRunSnapshot →
 *             parseCanonicalMeasurementResult) strips exactly the declared
 *             keys (transcriptionDetail) and nothing else.
 *
 * When a gate fails: forward the field in
 * apps/ui/src/services/backendPhase1Client.ts, declare it in
 * src/types/measurement.ts, document it in apps/backend/JSON_SCHEMA.md, and
 * add it to tests/fixtures/phase1FullPayload.ts — or, for an intentional
 * transform, extend the declared map below WITH a backend citation.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { parsePhase1Result } from '../../src/services/backendPhase1Client';
import { getAnalysisRun } from '../../src/services/analysisRunsClient';
import { phase1EnvelopeFixture } from '../fixtures/phase1FullPayload';

type UnknownRecord = Record<string, unknown>;

const goldenPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../backend/tests/fixtures/golden/phase1_default.json',
);

const golden = JSON.parse(readFileSync(goldenPath, 'utf8')) as {
  topLevelKeys: string[];
  topLevelTypes: Record<string, string>;
  keyTree?: Record<string, unknown>;
};

// ---------------------------------------------------------------------------
// Declared raw→envelope transform map. The backend normalizes raw analyze.py
// output before the frontend parser ever sees it; these constants are the
// executable mirror of that normalization. Extend ONLY with a citation — an
// undeclared server transform must fail this suite, never pass silently.
// ---------------------------------------------------------------------------

// apps/backend/server_phase1.py `_build_phase1`: stereoWidth/stereoCorrelation
// are hoisted to the top level from stereoDetail.
const ENVELOPE_ADDED_KEYS = new Set(['stereoWidth', 'stereoCorrelation']);

// apps/backend/server_phase1.py `_normalize_spectral_detail`: raw spectral
// keys are renamed to their `*Mean` forms. Applied at exactly two sites:
// `spectralDetail.*` and `stemAnalysis.<stem>.spectralDetail.*`
// (`_normalize_stem_analysis`).
const SPECTRAL_RENAMES: Record<string, string> = {
  spectralCentroid: 'spectralCentroidMean',
  spectralRolloff: 'spectralRolloffMean',
  spectralBandwidth: 'spectralBandwidthMean',
  spectralFlatness: 'spectralFlatnessMean',
};

// apps/backend/analysis_runtime.py `complete_measurement`: transcriptionDetail
// is popped out of measurement.result on the staged path — it lives on
// stages.pitchNoteTranslation instead (MeasurementResult omits it by type).
const CANONICAL_PATH_STRIPS = new Set(['transcriptionDetail']);

// Intentional parser drops, keyed by dotted path, each with a citation.
// Empty today — parsePhase1Result is expected to carry everything it is fed.
const EXPECTED_PARSER_DROPS: Record<string, string> = {};

// ---------------------------------------------------------------------------
// Walk helpers
// ---------------------------------------------------------------------------

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const toDotted = (segments: Array<string | number>): string =>
  segments
    .map((segment, index) =>
      typeof segment === 'number' ? `[${segment}]` : index === 0 ? segment : `.${segment}`,
    )
    .join('');

/**
 * Gate B walk: record every input path whose non-null value does not resolve
 * to a defined, non-null value in the parsed output.
 *
 * Semantics (matched to the parser's legitimate normalizations):
 * - `null`/`undefined` inputs assert nothing — there is nothing to drop.
 * - Arrays of objects recurse per element, index-preserving (the parser keeps
 *   valid entries 1:1 and the fixture is pre-sorted/valid by construction).
 * - Any other array is a leaf: the parser may slice/pad/dedupe scalar arrays
 *   (accent patterns, step grids, dominantNotes), and scalar elements carry
 *   no droppable keys.
 * - A missing subtree is reported once at its root, not per descendant.
 */
function collectDroppedPaths(
  input: unknown,
  output: unknown,
  segments: Array<string | number> = [],
  dropped: string[] = [],
): string[] {
  if (input === null || input === undefined) return dropped;

  if (Array.isArray(input)) {
    if (input.length === 0 || !input.every(isRecord)) return dropped;
    if (!Array.isArray(output)) {
      dropped.push(`${toDotted(segments)} (array of objects did not survive as an array)`);
      return dropped;
    }
    input.forEach((entry, index) => {
      collectDroppedPaths(entry, output[index], [...segments, index], dropped);
    });
    return dropped;
  }

  if (isRecord(input)) {
    for (const [key, value] of Object.entries(input)) {
      if (value === null || value === undefined) continue;
      const childSegments = [...segments, key];
      const dotted = toDotted(childSegments);
      const outputChild = isRecord(output) ? output[key] : undefined;
      if (outputChild === undefined || outputChild === null) {
        if (!(dotted in EXPECTED_PARSER_DROPS)) dropped.push(dotted);
        continue;
      }
      collectDroppedPaths(value, outputChild, childSegments, dropped);
    }
  }

  return dropped;
}

/**
 * Gate A3 walk: every key in the golden `keyTree` (the backend's recursive
 * nested-structure snapshot) must exist, non-null, in the fixture — after
 * applying the declared SPECTRAL_RENAMES at their two declared sites.
 *
 * keyTree encoding (mirrors `_key_tree` in
 * apps/backend/tests/test_phase1_golden.py):
 * - object node                → dict: recurse per key
 * - `{"[]": <subtree>}` node   → list of objects: compare against the union
 *                                of the fixture's element keys
 * - `"list"` leaf              → scalar/empty list: presence already checked
 * - `"pruned"` leaf            → backend-declared unstable subtree: skip
 * - other string leaf          → scalar type category: presence already checked
 */
function collectMissingKeyTreePaths(
  tree: unknown,
  fixture: unknown,
  segments: Array<string | number> = [],
  parentKey: string | null = null,
  missing: string[] = [],
): string[] {
  if (typeof tree === 'string') return missing; // scalar / "list" / "pruned" leaf

  if (!isRecord(tree)) return missing;

  if ('[]' in tree) {
    if (!Array.isArray(fixture) || fixture.length === 0) {
      missing.push(`${toDotted(segments)} (fixture needs a non-empty array of objects here)`);
      return missing;
    }
    const union: UnknownRecord = {};
    for (const entry of fixture) {
      if (!isRecord(entry)) continue;
      for (const [key, value] of Object.entries(entry)) {
        if (!(key in union) || union[key] == null) union[key] = value;
      }
    }
    return collectMissingKeyTreePaths(tree['[]'], union, [...segments, '[]' as string], parentKey, missing);
  }

  for (const [goldenKey, subtree] of Object.entries(tree)) {
    if (subtree === 'pruned') continue;
    // Declared rename sites: spectralDetail.* (top-level and per-stem).
    const fixtureKey =
      parentKey === 'spectralDetail' && goldenKey in SPECTRAL_RENAMES
        ? SPECTRAL_RENAMES[goldenKey]
        : goldenKey;
    const childSegments = [...segments, fixtureKey];
    const value = isRecord(fixture) ? fixture[fixtureKey] : undefined;
    if (value === undefined || value === null) {
      missing.push(toDotted(childSegments));
      continue;
    }
    collectMissingKeyTreePaths(subtree, value, childSegments, goldenKey, missing);
  }

  return missing;
}

const remediation = (paths: string[], where: string): string =>
  [
    `${paths.length} Phase 1 path(s) failed the cross-boundary contract gate (${where}):`,
    ...paths.map((path) => `  - ${path}`),
    'Remediation: forward the field in apps/ui/src/services/backendPhase1Client.ts,',
    'declare it in src/types/measurement.ts, document it in apps/backend/JSON_SCHEMA.md,',
    'and add a representative value to tests/fixtures/phase1FullPayload.ts.',
    'For an INTENTIONAL backend transform, extend the declared map in this file',
    'with a server_phase1.py / analysis_runtime.py citation instead.',
  ].join('\n');

// ---------------------------------------------------------------------------
// Gates
// ---------------------------------------------------------------------------

describe('phase1 cross-boundary contract parity', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sanity: the backend golden snapshot parsed and looks like the real contract', () => {
    // Tests are excluded from `npm run lint` type-checking; guard against a
    // silently-moved fixture or reshaped golden making every gate vacuous.
    expect(Array.isArray(golden.topLevelKeys)).toBe(true);
    expect(golden.topLevelKeys.length).toBeGreaterThan(60);
    expect(golden.topLevelKeys).toContain('bpm');
    expect(golden.topLevelTypes.bpm).toBe('number');
  });

  it('Gate A1: every backend golden top-level key is present (non-null) in the frontend fixture', () => {
    const fixture = phase1EnvelopeFixture as UnknownRecord;
    const missing = golden.topLevelKeys.filter(
      (key) => fixture[key] === undefined || fixture[key] === null,
    );
    expect(missing, remediation(missing, 'golden topLevelKeys → fixture')).toEqual([]);
  });

  it('Gate A2: every fixture top-level key is a golden key or a declared envelope addition', () => {
    const allowed = new Set([...golden.topLevelKeys, ...ENVELOPE_ADDED_KEYS]);
    const unknown = Object.keys(phase1EnvelopeFixture).filter((key) => !allowed.has(key));
    expect(
      unknown,
      `${unknown.length} fixture key(s) are not in the backend golden topLevelKeys: ` +
        `${unknown.join(', ')}. Either the backend removed the field (delete it from ` +
        'tests/fixtures/phase1FullPayload.ts) or a new envelope-level addition needs ' +
        'declaring in ENVELOPE_ADDED_KEYS with a server_phase1.py citation.',
    ).toEqual([]);
  });

  // Auto-arming nested gate: requires the golden to carry a keyTree, which the
  // backend writes on the next `UPDATE_PHASE1_GOLDEN=1` re-baseline. Until
  // then this is a visible skip, not silent coverage loss.
  it.skipIf(!golden.keyTree)(
    'Gate A3: every nested key the backend emits is present in the frontend fixture (golden keyTree)',
    () => {
      const missing: string[] = [];
      for (const [key, subtree] of Object.entries(golden.keyTree as UnknownRecord)) {
        // Subtrees the golden run observed as null have no recorded shape.
        if (golden.topLevelTypes[key] === 'null') continue;
        collectMissingKeyTreePaths(
          subtree,
          (phase1EnvelopeFixture as UnknownRecord)[key],
          [key],
          key,
          missing,
        );
      }
      expect(missing, remediation(missing, 'golden keyTree → fixture')).toEqual([]);
    },
  );

  it('Gate B: no key silently vanishes through the real parsePhase1Result', () => {
    const parsed = parsePhase1Result(phase1EnvelopeFixture);
    const dropped = collectDroppedPaths(phase1EnvelopeFixture, parsed);
    expect(dropped, remediation(dropped, 'fixture → parsePhase1Result output')).toEqual([]);
  });

  it('Gate C: the canonical run path strips exactly the declared keys and nothing else', async () => {
    const runSnapshot = {
      runId: 'run_parity',
      requestedStages: {
        pitchNoteMode: 'off',
        pitchNoteBackend: 'auto',
        interpretationMode: 'off',
        interpretationProfile: 'producer_summary',
      },
      artifacts: {
        sourceAudio: {
          artifactId: 'artifact_parity',
          filename: 'track.flac',
          mimeType: 'audio/flac',
          sizeBytes: 1024,
          contentSha256: 'parity-sha',
        },
      },
      stages: {
        measurement: {
          status: 'completed',
          authoritative: true,
          result: phase1EnvelopeFixture,
          provenance: null,
          diagnostics: null,
          error: null,
        },
        pitchNoteTranslation: {
          status: 'not_requested',
          authoritative: false,
          preferredAttemptId: null,
          attemptsSummary: [],
          result: null,
          provenance: null,
          diagnostics: null,
          error: null,
        },
        interpretation: {
          status: 'not_requested',
          authoritative: false,
          preferredAttemptId: null,
          attemptsSummary: [],
          result: null,
          provenance: null,
          diagnostics: null,
          error: null,
        },
      },
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        statusText: 'OK',
        json: () => Promise.resolve(runSnapshot),
      } as Response),
    );

    const snapshot = await getAnalysisRun('run_parity', { apiBaseUrl: 'http://127.0.0.1:8100' });
    const measurement = snapshot.stages.measurement.result as UnknownRecord | null;
    expect(measurement).not.toBeNull();

    // The declared strips must be ABSENT as keys (toEqual cannot tell
    // `undefined` from missing, so check ownership explicitly).
    for (const key of CANONICAL_PATH_STRIPS) {
      expect(
        Object.prototype.hasOwnProperty.call(measurement, key),
        `expected the canonical path to strip "${key}" from measurement.result`,
      ).toBe(false);
    }

    // …and NOTHING else may differ from the legacy parse: canonical parse
    // result === parsePhase1Result(fixture) minus exactly the declared strips.
    const expected = { ...parsePhase1Result(phase1EnvelopeFixture) } as UnknownRecord;
    for (const key of CANONICAL_PATH_STRIPS) delete expected[key];
    expect(measurement).toEqual(expected);
  });
});

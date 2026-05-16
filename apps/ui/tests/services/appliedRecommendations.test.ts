/**
 * Locks in the per-file applied-recommendations tracker (audit Finding #14 + #15):
 * - localStorage-backed, keyed by audio content SHA256
 * - empty sets are removed (no orphan keys)
 * - corrupted JSON falls back to empty (defensive)
 * - all functions safe when storage is unavailable (SSR / private mode)
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  APPLIED_RECOMMENDATIONS_STORAGE_KEY,
  MAX_TRACKED_FILES,
  clearAppliedForFile,
  loadAppliedIds,
  saveAppliedIds,
  toggleAppliedId,
} from '../../src/services/appliedRecommendations';

// Minimal in-memory storage stand-in. Mirrors the Storage API surface the
// service actually touches; deliberately doesn't extend the full DOM
// `Storage` interface because the service typing is structural.
function makeMemoryStorage(seed: Record<string, string> = {}) {
  const store = new Map<string, string>(Object.entries(seed));
  return {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    snapshot: () => Object.fromEntries(store),
  };
}

let storage: ReturnType<typeof makeMemoryStorage>;
beforeEach(() => {
  storage = makeMemoryStorage();
});

afterEach(() => {
  // No global state to reset — each test creates its own storage.
});

describe('loadAppliedIds', () => {
  it('returns empty set for null/undefined/empty hash', () => {
    expect(loadAppliedIds(null, storage).size).toBe(0);
    expect(loadAppliedIds(undefined, storage).size).toBe(0);
    expect(loadAppliedIds('', storage).size).toBe(0);
  });

  it('returns empty set when no record exists', () => {
    expect(loadAppliedIds('abc123', storage).size).toBe(0);
  });

  it('reads back persisted ids', () => {
    saveAppliedIds('abc123', new Set(['card-1', 'card-2']), { storage });
    const result = loadAppliedIds('abc123', storage);
    expect(result.size).toBe(2);
    expect(result.has('card-1')).toBe(true);
    expect(result.has('card-2')).toBe(true);
  });

  it('returns empty set when storage payload is corrupted JSON', () => {
    storage.setItem(APPLIED_RECOMMENDATIONS_STORAGE_KEY, '{not valid json');
    expect(loadAppliedIds('abc123', storage).size).toBe(0);
  });

  it('returns empty set when storage payload is not an object', () => {
    storage.setItem(APPLIED_RECOMMENDATIONS_STORAGE_KEY, '42');
    expect(loadAppliedIds('abc123', storage).size).toBe(0);
  });

  it('returns empty set when record has malformed appliedIds', () => {
    storage.setItem(
      APPLIED_RECOMMENDATIONS_STORAGE_KEY,
      JSON.stringify({ abc123: { appliedIds: 'not-an-array' } }),
    );
    expect(loadAppliedIds('abc123', storage).size).toBe(0);
  });

  it('is defensive when storage is unavailable', () => {
    expect(loadAppliedIds('abc123', undefined).size).toBe(0);
  });
});

describe('saveAppliedIds', () => {
  it('persists a non-empty set', () => {
    saveAppliedIds('abc123', new Set(['card-1']), { storage });
    expect(loadAppliedIds('abc123', storage).has('card-1')).toBe(true);
  });

  it('accepts a readonly array as well as a Set', () => {
    saveAppliedIds('abc123', ['card-a', 'card-b'], { storage });
    const result = loadAppliedIds('abc123', storage);
    expect(result.size).toBe(2);
  });

  it('deletes the record when the set becomes empty', () => {
    saveAppliedIds('abc123', new Set(['card-1']), { storage });
    saveAppliedIds('abc123', new Set(), { storage });
    const raw = storage.getItem(APPLIED_RECOMMENDATIONS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    expect(parsed.abc123).toBeUndefined();
  });

  it('captures filename when provided', () => {
    saveAppliedIds('abc123', new Set(['card-1']), {
      storage,
      filename: 'demo.mp3',
    });
    const parsed = JSON.parse(storage.getItem(APPLIED_RECOMMENDATIONS_STORAGE_KEY)!);
    expect(parsed.abc123.filename).toBe('demo.mp3');
  });

  it('stamps updatedAt on each save', () => {
    saveAppliedIds('abc123', new Set(['card-1']), { storage });
    const parsed = JSON.parse(storage.getItem(APPLIED_RECOMMENDATIONS_STORAGE_KEY)!);
    expect(typeof parsed.abc123.updatedAt).toBe('number');
    expect(parsed.abc123.updatedAt).toBeGreaterThan(0);
  });

  it('keeps records for other files when saving one file', () => {
    saveAppliedIds('abc123', new Set(['card-1']), { storage });
    saveAppliedIds('def456', new Set(['card-7']), { storage });
    expect(loadAppliedIds('abc123', storage).has('card-1')).toBe(true);
    expect(loadAppliedIds('def456', storage).has('card-7')).toBe(true);
  });
});

describe('toggleAppliedId', () => {
  it('adds an id when not present, returns new set', () => {
    const result = toggleAppliedId('abc123', 'card-1', { storage });
    expect(result.has('card-1')).toBe(true);
    expect(loadAppliedIds('abc123', storage).has('card-1')).toBe(true);
  });

  it('removes an id when already present', () => {
    saveAppliedIds('abc123', new Set(['card-1', 'card-2']), { storage });
    const result = toggleAppliedId('abc123', 'card-1', { storage });
    expect(result.has('card-1')).toBe(false);
    expect(result.has('card-2')).toBe(true);
  });

  it('toggling the last id deletes the record', () => {
    saveAppliedIds('abc123', new Set(['card-1']), { storage });
    toggleAppliedId('abc123', 'card-1', { storage });
    const parsed = JSON.parse(
      storage.getItem(APPLIED_RECOMMENDATIONS_STORAGE_KEY) || '{}',
    );
    expect(parsed.abc123).toBeUndefined();
  });
});

describe('saveAppliedIds (max-entries pruning)', () => {
  // Seeds N records directly into the underlying store, each with a distinct
  // updatedAt so prune order is deterministic. Bypasses saveAppliedIds for
  // setup so we can preload an over-capacity store and observe the next save
  // triggering eviction.
  function seedStoreWithAges(count: number) {
    const records: Record<string, { appliedIds: string[]; updatedAt: number }> = {};
    for (let i = 0; i < count; i++) {
      records[`hash-${i.toString().padStart(3, '0')}`] = {
        appliedIds: [`card-${i}`],
        updatedAt: 1_000_000 + i,
      };
    }
    storage.setItem(APPLIED_RECOMMENDATIONS_STORAGE_KEY, JSON.stringify(records));
  }

  it('keeps store at or below MAX_TRACKED_FILES after a save that pushes it over', () => {
    seedStoreWithAges(MAX_TRACKED_FILES);
    saveAppliedIds('hash-new', new Set(['card-new']), { storage });
    const parsed = JSON.parse(storage.getItem(APPLIED_RECOMMENDATIONS_STORAGE_KEY)!);
    expect(Object.keys(parsed).length).toBe(MAX_TRACKED_FILES);
    // The new entry survived.
    expect(parsed['hash-new']).toBeTruthy();
    // The oldest seeded entry (hash-000, lowest updatedAt) was evicted.
    expect(parsed['hash-000']).toBeUndefined();
  });

  it('evicts records by ascending updatedAt, not insertion order', () => {
    // Seed 51 entries — the boundary case where MAX_TRACKED_FILES+1 must
    // shed exactly one record.
    seedStoreWithAges(MAX_TRACKED_FILES);
    // Re-save the oldest record with a fresh timestamp so it bubbles up the
    // recency order; the next-oldest (hash-001) should be evicted instead.
    saveAppliedIds('hash-000', new Set(['card-0-touched']), { storage });
    saveAppliedIds('hash-new', new Set(['card-new']), { storage });
    const parsed = JSON.parse(storage.getItem(APPLIED_RECOMMENDATIONS_STORAGE_KEY)!);
    expect(parsed['hash-000']).toBeTruthy();
    expect(parsed['hash-001']).toBeUndefined();
    expect(parsed['hash-new']).toBeTruthy();
  });

  it('does not prune when store is at or below MAX_TRACKED_FILES', () => {
    seedStoreWithAges(MAX_TRACKED_FILES - 1);
    saveAppliedIds('hash-new', new Set(['card-new']), { storage });
    const parsed = JSON.parse(storage.getItem(APPLIED_RECOMMENDATIONS_STORAGE_KEY)!);
    expect(Object.keys(parsed).length).toBe(MAX_TRACKED_FILES);
    // Nothing should have been evicted — every seeded hash is still there.
    expect(parsed['hash-000']).toBeTruthy();
  });
});

describe('clearAppliedForFile', () => {
  it('removes the record for the given hash', () => {
    saveAppliedIds('abc123', new Set(['card-1']), { storage });
    saveAppliedIds('def456', new Set(['card-2']), { storage });
    clearAppliedForFile('abc123', storage);
    expect(loadAppliedIds('abc123', storage).size).toBe(0);
    expect(loadAppliedIds('def456', storage).has('card-2')).toBe(true);
  });

  it('is a no-op when no record exists', () => {
    expect(() => clearAppliedForFile('never-existed', storage)).not.toThrow();
  });
});

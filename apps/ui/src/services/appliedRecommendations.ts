/**
 * Audit Finding #14 + #15: producers running ASA mid-session need a way to
 * track which Mix Chain / Patches recommendations they've already applied in
 * their DAW. Without it, every card looks identical regardless of whether
 * it's already been wired into Live or not — and re-uploading the same file
 * tomorrow starts the cross-referencing exercise from scratch.
 *
 * This service maintains a per-file set of "applied" recommendation card ids
 * in localStorage. Key shape (`asa:applied-recommendations:v1`):
 *
 *   {
 *     "<contentSha256>": {
 *       appliedIds: ["1-Drum Buss-0", "patch-2-Operator", ...],
 *       updatedAt: 1747268400000,
 *       filename: "demo.mp3"     // captured opportunistically for debug surfaces
 *     },
 *     ...
 *   }
 *
 * Keying by file content hash (not name) means the producer can rename
 * `demo.mp3` → `track-final.mp3` without losing their progress; the backend
 * already exposes `contentSha256` on every analysis run's source audio
 * artifact (`AnalysisRunArtifact.contentSha256`), so the frontend just reads
 * it through. If Phase 2 emits different card ids on re-analysis, the
 * applied state from the previous run becomes orphaned — that's acceptable
 * for V1 per the audit's "lowest priority finding" rank on persistence.
 */

interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem?(key: string): void;
}

export const APPLIED_RECOMMENDATIONS_STORAGE_KEY = 'asa:applied-recommendations:v1';

interface AppliedRecord {
  appliedIds: string[];
  updatedAt: number;
  filename?: string;
}

interface AppliedStore {
  [fileHash: string]: AppliedRecord;
}

function getDefaultStorage(): StorageLike | undefined {
  if (typeof window === 'undefined') return undefined;
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

function readStore(storage: StorageLike | undefined): AppliedStore {
  if (!storage) return {};
  try {
    const raw = storage.getItem(APPLIED_RECOMMENDATIONS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return {};
    return parsed as AppliedStore;
  } catch {
    // Corrupted JSON or quota error — treat as empty rather than throw.
    return {};
  }
}

function writeStore(storage: StorageLike | undefined, store: AppliedStore): void {
  if (!storage) return;
  try {
    storage.setItem(APPLIED_RECOMMENDATIONS_STORAGE_KEY, JSON.stringify(store));
  } catch {
    // Quota exceeded / private-mode storage rejected. Failing the toggle
    // would be more confusing than silently keeping the in-memory set.
  }
}

/**
 * Read the applied set for the given file hash. Returns an empty Set when
 * the hash is null/empty, when no record exists, or when storage isn't
 * available (server-side render, private-mode disabled storage).
 */
export function loadAppliedIds(
  fileHash: string | null | undefined,
  storage: StorageLike | undefined = getDefaultStorage(),
): Set<string> {
  if (!fileHash) return new Set();
  const store = readStore(storage);
  const record = store[fileHash];
  if (!record || !Array.isArray(record.appliedIds)) return new Set();
  return new Set(record.appliedIds);
}

/**
 * Persist the applied set for the given file hash. When the set is empty,
 * the record is deleted instead of stored as an empty array — keeps
 * localStorage clean of orphan keys for files that were toggled then untoggled.
 */
export function saveAppliedIds(
  fileHash: string,
  appliedIds: Set<string> | readonly string[],
  options: { filename?: string; storage?: StorageLike } = {},
): void {
  const storage = options.storage ?? getDefaultStorage();
  if (!storage) return;
  const ids = appliedIds instanceof Set ? Array.from(appliedIds) : [...appliedIds];

  const store = readStore(storage);
  if (ids.length === 0) {
    if (fileHash in store) {
      delete store[fileHash];
      writeStore(storage, store);
    }
    return;
  }

  store[fileHash] = {
    appliedIds: ids,
    updatedAt: Date.now(),
    ...(options.filename ? { filename: options.filename } : {}),
  };
  writeStore(storage, store);
}

/**
 * Toggle a single card id in the applied set and persist. Returns the new
 * set so the caller can update React state without re-reading storage.
 */
export function toggleAppliedId(
  fileHash: string,
  cardId: string,
  options: { filename?: string; storage?: StorageLike } = {},
): Set<string> {
  const storage = options.storage ?? getDefaultStorage();
  const current = loadAppliedIds(fileHash, storage);
  const next = new Set(current);
  if (next.has(cardId)) {
    next.delete(cardId);
  } else {
    next.add(cardId);
  }
  saveAppliedIds(fileHash, next, { filename: options.filename, storage });
  return next;
}

/**
 * Drop the applied record for a single file. Useful for a future "clear
 * progress" action; not wired into UI yet.
 */
export function clearAppliedForFile(
  fileHash: string,
  storage: StorageLike | undefined = getDefaultStorage(),
): void {
  if (!storage) return;
  const store = readStore(storage);
  if (!(fileHash in store)) return;
  delete store[fileHash];
  writeStore(storage, store);
}

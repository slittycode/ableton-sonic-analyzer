const DEFAULT_PHASE2_REQUESTED = true;

export const PHASE2_PREFERENCE_STORAGE_KEY = 'sonic-analyzer.phase2-requested';

interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

function getDefaultStorage(): StorageLike | undefined {
  if (typeof window === 'undefined') {
    return undefined;
  }

  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

export function loadPhase2RequestedPreference(storage: StorageLike | undefined = getDefaultStorage()): boolean {
  if (!storage) {
    return DEFAULT_PHASE2_REQUESTED;
  }

  const rawValue = storage.getItem(PHASE2_PREFERENCE_STORAGE_KEY);
  if (rawValue === 'false') {
    return false;
  }
  if (rawValue === 'true') {
    return true;
  }
  return DEFAULT_PHASE2_REQUESTED;
}

export function savePhase2RequestedPreference(
  requested: boolean,
  storage: StorageLike | undefined = getDefaultStorage(),
) {
  try {
    storage?.setItem(PHASE2_PREFERENCE_STORAGE_KEY, requested ? 'true' : 'false');
  } catch {
    // Ignore browser storage failures. The toggle should still work for the current session.
  }
}

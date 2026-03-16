import { describe, expect, it, vi } from 'vitest';

import {
  PHASE2_PREFERENCE_STORAGE_KEY,
  loadPhase2RequestedPreference,
  savePhase2RequestedPreference,
} from '../../src/utils/phase2Preference';

interface MockStorage {
  getItem: ReturnType<typeof vi.fn>;
  setItem: ReturnType<typeof vi.fn>;
}

function createStorage(initialValue: string | null): MockStorage {
  let currentValue = initialValue;

  return {
    getItem: vi.fn((key: string) => (key === PHASE2_PREFERENCE_STORAGE_KEY ? currentValue : null)),
    setItem: vi.fn((key: string, value: string) => {
      if (key === PHASE2_PREFERENCE_STORAGE_KEY) {
        currentValue = value;
      }
    }),
  };
}

describe('phase2Preference', () => {
  it('defaults to on when there is no saved preference', () => {
    const storage = createStorage(null);

    expect(loadPhase2RequestedPreference(storage)).toBe(true);
    expect(storage.getItem).toHaveBeenCalledWith(PHASE2_PREFERENCE_STORAGE_KEY);
  });

  it('restores a saved off preference from storage', () => {
    const storage = createStorage('false');

    expect(loadPhase2RequestedPreference(storage)).toBe(false);
  });

  it('persists the requested value back to storage', () => {
    const storage = createStorage(null);

    savePhase2RequestedPreference(false, storage);

    expect(storage.setItem).toHaveBeenCalledWith(PHASE2_PREFERENCE_STORAGE_KEY, 'false');
    expect(loadPhase2RequestedPreference(storage)).toBe(false);
  });
});

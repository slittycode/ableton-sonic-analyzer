import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildMt3MidiFileName, fetchMt3TrackMidiBlob } from '../../src/services/mt3Client';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('buildMt3MidiFileName', () => {
  it('builds a prefixed .mid filename for a canonical stem', () => {
    expect(buildMt3MidiFileName('bass')).toBe('mt3-bass.mid');
    expect(buildMt3MidiFileName('other')).toBe('mt3-other.mid');
  });

  it('sanitizes spaces and unsafe characters, collapsing runs to a single underscore', () => {
    expect(buildMt3MidiFileName('lead synth')).toBe('mt3-lead_synth.mid');
    expect(buildMt3MidiFileName('drums/kit #2')).toBe('mt3-drums_kit_2.mid');
  });

  it('falls back to a generic name when the instrument is empty or all-unsafe', () => {
    expect(buildMt3MidiFileName('')).toBe('mt3-track.mid');
    expect(buildMt3MidiFileName('   ')).toBe('mt3-track.mid');
    expect(buildMt3MidiFileName('***')).toBe('mt3-track.mid');
  });
});

describe('fetchMt3TrackMidiBlob', () => {
  it('fetches the artifact URL through authenticated fetch and returns the blob', async () => {
    const midiBlob = new Blob([new Uint8Array([0x4d, 0x54, 0x68, 0x64])], {
      type: 'audio/midi',
    });
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(midiBlob, { status: 200 }));

    const result = await fetchMt3TrackMidiBlob(
      'https://asa.example.com',
      'run_123',
      'artifact_mid_456',
      { headers: { 'X-ASA-User-Id': 'beta-user-123' } },
    );

    expect(fetchMock).toHaveBeenCalledWith(
      'https://asa.example.com/api/analysis-runs/run_123/artifacts/artifact_mid_456',
      expect.objectContaining({
        headers: { 'X-ASA-User-Id': 'beta-user-123' },
      }),
    );
    expect(result).toBeInstanceOf(Blob);
    expect(result.size).toBe(4);
  });

  it('throws with the status code when the artifact fetch is not ok', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('not found', { status: 404 }),
    );

    await expect(
      fetchMt3TrackMidiBlob('https://asa.example.com', 'run_123', 'missing'),
    ).rejects.toThrow('Failed to fetch MT3 MIDI artifact: 404');
  });
});

import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('fetchArtifactImageObjectUrl', () => {
  it('loads artifact images through authenticated fetch and returns a revoker', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(new Blob(['image-bytes'], { type: 'image/png' }), {
          status: 200,
          headers: { 'Content-Type': 'image/png' },
        }),
      );
    const createObjectURL = vi.fn(() => 'blob:https://asa.example.com/spectrogram');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal(
      'URL',
      Object.assign(URL, {
        createObjectURL,
        revokeObjectURL,
      }),
    );

    const { fetchArtifactImageObjectUrl } =
      await vi.importActual<typeof import('../../src/services/spectralArtifactsClient')>(
        '../../src/services/spectralArtifactsClient',
      );

    const loaded = await fetchArtifactImageObjectUrl(
      'https://asa.example.com',
      'run_123',
      'artifact_456',
      {
        headers: { 'X-ASA-User-Id': 'beta-user-123' },
      },
    );

    expect(fetchMock).toHaveBeenCalledWith(
      'https://asa.example.com/api/analysis-runs/run_123/artifacts/artifact_456',
      expect.objectContaining({
        headers: {
          'X-ASA-User-Id': 'beta-user-123',
        },
      }),
    );
    expect(loaded.url).toBe('blob:https://asa.example.com/spectrogram');
    loaded.revoke();
    expect(revokeObjectURL).toHaveBeenCalledWith(
      'blob:https://asa.example.com/spectrogram',
    );
  });
});

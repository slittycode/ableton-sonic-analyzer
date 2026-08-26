import { describe, expect, it } from 'vitest';

import {
  planPdfPageSlices,
  shouldSkipCaptureNode,
} from '../../src/utils/uiCapture';
import { buildExportFileName } from '../../src/utils/exportUtils';

describe('planPdfPageSlices', () => {
  it('returns empty for invalid dimensions', () => {
    expect(planPdfPageSlices(0, 100)).toEqual([]);
    expect(planPdfPageSlices(100, 0)).toEqual([]);
  });

  it('fits a short image on a single page', () => {
    const slices = planPdfPageSlices(800, 400);
    expect(slices).toHaveLength(1);
    expect(slices[0]).toEqual({ sliceTop: 0, sliceHeight: 400 });
  });

  it('splits a tall image into ordered non-overlapping slices covering full height', () => {
    const imageWidth = 1200;
    const imageHeight = 10_000;
    const slices = planPdfPageSlices(imageWidth, imageHeight);
    expect(slices.length).toBeGreaterThan(1);

    let covered = 0;
    for (const slice of slices) {
      expect(slice.sliceTop).toBe(covered);
      expect(slice.sliceHeight).toBeGreaterThan(0);
      covered += slice.sliceHeight;
    }
    expect(covered).toBe(imageHeight);
  });
});

describe('shouldSkipCaptureNode', () => {
  it('skips sticky nav / canvas / spectrogram stubs without jsdom', () => {
    const sticky = {
      tagName: 'DIV',
      dataset: { testid: 'sticky-nav' },
      classList: { contains: () => false },
    } as unknown as Node;
    expect(shouldSkipCaptureNode(sticky)).toBe(true);

    const canvas = {
      tagName: 'CANVAS',
      dataset: {},
      classList: { contains: () => false },
    } as unknown as Node;
    expect(shouldSkipCaptureNode(canvas)).toBe(true);

    const spectro = {
      tagName: 'DIV',
      dataset: { testid: 'spectrogram-viewer' },
      classList: { contains: () => false },
    } as unknown as Node;
    expect(shouldSkipCaptureNode(spectro)).toBe(true);

    const normal = {
      tagName: 'SECTION',
      dataset: {},
      classList: { contains: () => false },
    } as unknown as Node;
    expect(shouldSkipCaptureNode(normal)).toBe(false);
  });
});

describe('buildExportFileName for UI captures', () => {
  it('names UI exports with -ui suffix', () => {
    expect(
      buildExportFileName('pdf', {
        filename: 'VTSS-Cant-Catch-Me.mp3',
        analyzedAt: '2026-07-18T12:00:00.000Z',
      }),
    ).toBe('track-analysis-VTSS-Cant-Catch-Me-2026-07-18-ui.pdf');
    expect(
      buildExportFileName('png', {
        filename: 'mix.wav',
        analyzedAt: '2026-01-02T00:00:00.000Z',
      }),
    ).toBe('track-analysis-mix-2026-01-02-ui.png');
  });
});

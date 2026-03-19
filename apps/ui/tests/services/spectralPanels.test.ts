import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { SpectralBalanceCurve } from '../../src/components/SpectralBalanceCurve';
import { SegmentSpectralProfile } from '../../src/components/SegmentSpectralProfile';
import type { Phase1Result, SegmentSpectralEntry } from '../../src/types';

const spectralBalance: Phase1Result['spectralBalance'] = {
  subBass: -1.1,
  lowBass: 0.7,
  mids: -0.4,
  upperMids: 0.3,
  highs: 1.0,
  brilliance: 0.6,
};

function makeSegment(index: number, values: number[]): SegmentSpectralEntry {
  return {
    segmentIndex: index,
    barkBands: values,
    spectralCentroid: null,
    spectralRolloff: null,
    stereoWidth: null,
    stereoCorrelation: null,
  };
}

describe('SpectralBalanceCurve', () => {
  it('prefers bark-band mode when bark data is available', () => {
    const bark = Array.from({ length: 24 }, (_, i) => -20 + i * 0.4);

    const html = renderToStaticMarkup(
      React.createElement(SpectralBalanceCurve, {
        spectralBalance,
        barkBands: bark,
      }),
    );

    expect(html).toContain('24-band Bark global average');
    expect(html).toContain('Bark-scale center frequency (Hz)');
    expect(html).not.toContain('6-band aggregate fallback');
    expect(html).not.toMatch(/ d="[^"]*C /);
  });

  it('falls back to 6-band aggregate mode when bark data is unavailable', () => {
    const html = renderToStaticMarkup(
      React.createElement(SpectralBalanceCurve, {
        spectralBalance,
        barkBands: null,
      }),
    );

    expect(html).toContain('6-band aggregate fallback');
    expect(html).toContain('Sub/Low/Mid/Upper Mid/High/Air bands');
    expect(html).toContain('>Sub<');
    expect(html).not.toMatch(/ d="[^"]*C /);
  });
});

describe('SegmentSpectralProfile', () => {
  it('uses per-section profile labeling for 3-column data', () => {
    const segments = [
      makeSegment(0, Array.from({ length: 24 }, (_, i) => -22 + i * 0.2)),
      makeSegment(1, Array.from({ length: 24 }, (_, i) => -21 + i * 0.2)),
      makeSegment(2, Array.from({ length: 24 }, (_, i) => -20 + i * 0.2)),
    ];

    const html = renderToStaticMarkup(
      React.createElement(SegmentSpectralProfile, {
        segmentSpectral: segments,
        segmentLoudness: [
          { segmentIndex: 0, start: 0, end: 40 },
          { segmentIndex: 1, start: 40, end: 80 },
          { segmentIndex: 2, start: 80, end: 120 },
        ],
      }),
    );

    expect(html).toContain('Per-section spectral profile');
    expect(html).toContain('3 x 24');
    expect(html).toContain('S1');
    expect(html).toContain('0.0s–40s');
  });

  it('truncates to shared bark band count when segment lengths differ', () => {
    const segments = [
      makeSegment(0, Array.from({ length: 24 }, (_, i) => -15 - i)),
      makeSegment(1, Array.from({ length: 23 }, (_, i) => -14 - i)),
      makeSegment(2, Array.from({ length: 22 }, (_, i) => -13 - i)),
    ];

    const html = renderToStaticMarkup(
      React.createElement(SegmentSpectralProfile, {
        segmentSpectral: segments,
        segmentLoudness: null,
      }),
    );

    expect(html).toContain('3 x 22');
  });

  it('handles equal-value normalization without NaN/Infinity output', () => {
    const segments = [
      makeSegment(0, Array.from({ length: 24 }, () => -12)),
      makeSegment(1, Array.from({ length: 24 }, () => -12)),
      makeSegment(2, Array.from({ length: 24 }, () => -12)),
    ];

    const html = renderToStaticMarkup(
      React.createElement(SegmentSpectralProfile, {
        segmentSpectral: segments,
        segmentLoudness: null,
      }),
    );

    expect(html).not.toContain('NaN');
    expect(html).not.toContain('Infinity');
  });
});

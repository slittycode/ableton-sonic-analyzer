import { describeAcid, describeSidechain } from '../../src/services/detectorMusicalContext';
import type { SidechainDetail } from '../../src/types';

describe('detectorMusicalContext', () => {
  it('uses detected sidechain rate in subtle pump wording', () => {
    const detail: SidechainDetail = {
      pumpingStrength: 0.35,
      pumpingRegularity: 0.4,
      pumpingRate: 'eighth',
      pumpingConfidence: 0.9,
    };

    const text = describeSidechain(detail);
    expect(text).toContain('Subtle eighth-note pump');
    expect(text).not.toContain('quarter-note');
  });

  it('uses tempo-synced phrasing when sidechain rate is unavailable', () => {
    const detail: SidechainDetail = {
      pumpingStrength: 0.35,
      pumpingRegularity: 0.4,
      pumpingRate: null,
      pumpingConfidence: 0.9,
    };

    const text = describeSidechain(detail);
    expect(text).toContain('Subtle tempo-synced pump');
    expect(text).not.toContain('Rate:');
  });

  it('uses edition-safe acid guidance without Analog-only wording', () => {
    const text = describeAcid({
      isAcid: true,
      confidence: 0.8,
      resonanceLevel: 0.66,
      centroidOscillationHz: 4.2,
      bassRhythmDensity: 5.1,
    });

    expect(text).toContain('works in Intro/Standard/Suite');
    expect(text).not.toContain('Try Ableton Analog');
  });
});

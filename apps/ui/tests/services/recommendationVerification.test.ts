import { describe, it, expect } from 'vitest';

import {
  inferRecommendationDomain,
  verificationForDomain,
  verificationForRecommendation,
} from '../../src/services/recommendationVerification';
import {
  RECOMMENDATION_VERIFICATION,
  type RecommendationVerificationArtifact,
} from '../../src/data/recommendationVerification';

describe('inferRecommendationDomain', () => {
  it('prefers track context over category', () => {
    expect(inferRecommendationDomain('Kick bus', 'DYNAMICS')).toBe('kick');
    expect(inferRecommendationDomain('Bass', 'SYNTHESIS')).toBe('bass');
    expect(inferRecommendationDomain('Pluck lead', 'SYNTHESIS')).toBe('melody');
    expect(inferRecommendationDomain('Master bus', 'EQ')).toBe('master');
  });

  it('falls back to category when context is silent', () => {
    expect(inferRecommendationDomain(null, 'STEREO')).toBe('stereo');
    expect(inferRecommendationDomain(undefined, 'MASTERING')).toBe('master');
  });

  it('returns null when nothing is attributable', () => {
    expect(inferRecommendationDomain(null, null)).toBeNull();
    expect(inferRecommendationDomain('', 'EQ')).toBeNull();
  });
});

describe('verificationForDomain', () => {
  it('reads the per-domain entry', () => {
    const entry = verificationForDomain('kick');
    expect(entry).not.toBeNull();
    expect(entry?.confidence).toBe('NONE'); // pre-render corpus state
  });

  it('returns null for a null domain', () => {
    expect(verificationForDomain(null)).toBeNull();
  });
});

describe('verificationForRecommendation', () => {
  it('degrades to NONE (graceful) with the empty pre-render artifact', () => {
    const v = verificationForRecommendation({ trackContext: 'Kick', category: 'SYNTHESIS' });
    expect(v?.confidence).toBe('NONE');
  });

  it('returns null when the card has no inferable domain', () => {
    expect(verificationForRecommendation({ trackContext: null, category: null })).toBeNull();
  });

  it('surfaces a confident band once the corpus carries evidence', () => {
    const populated: RecommendationVerificationArtifact = {
      ...RECOMMENDATION_VERIFICATION,
      fixtures: 6,
      sources: ['gemini'],
      perDomain: {
        ...RECOMMENDATION_VERIFICATION.perDomain,
        kick: { support: 6, meanRecall: 0.9, meanScore: 0.82, confidence: 'HIGH' },
      },
    };
    const v = verificationForRecommendation({ trackContext: 'Kick', category: 'SYNTHESIS' }, populated);
    expect(v?.confidence).toBe('HIGH');
    expect(v?.meanRecall).toBeCloseTo(0.9);
  });
});

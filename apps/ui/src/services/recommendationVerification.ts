/**
 * Maps a recommendation to its corpus-verification status for the UI badge
 * (GOAL.md sub-goal 4). Pure logic — node-environment testable (no DOM).
 *
 * Domain inference mirrors `recommendation_evaluation.infer_domain` in the
 * backend scorer so the badge attributes a card to the same domain the harness
 * scored it under: track context wins (it is specific — "Kick bus", "Bass",
 * "Master"), then category, else no domain (→ no badge).
 */

import {
  RECOMMENDATION_VERIFICATION,
  type DomainVerification,
  type RecommendationDomain,
  type RecommendationVerificationArtifact,
} from '../data/recommendationVerification';

// Keyword -> domain, mirroring the backend's _DOMAIN_KEYWORDS ordering (longer /
// more specific phrases first).
const DOMAIN_KEYWORDS: ReadonlyArray<readonly [string, RecommendationDomain]> = [
  ['kick', 'kick'],
  ['sub bass', 'bass'],
  ['bassline', 'bass'],
  ['bass', 'bass'],
  ['808', 'bass'],
  ['lead', 'melody'],
  ['melod', 'melody'],
  ['arp', 'melody'],
  ['pluck', 'melody'],
  ['chord', 'melody'],
  ['pad', 'melody'],
  ['synth', 'melody'],
  ['harmon', 'melody'],
  ['hi-hat', 'groove'],
  ['hihat', 'groove'],
  ['hat', 'groove'],
  ['perc', 'groove'],
  ['snare', 'groove'],
  ['clap', 'groove'],
  ['drum', 'groove'],
  ['groove', 'groove'],
  ['width', 'stereo'],
  ['stereo', 'stereo'],
  ['pan', 'stereo'],
  ['imaging', 'stereo'],
  ['master', 'master'],
  ['mix bus', 'master'],
];

const CATEGORY_DOMAIN: Readonly<Record<string, RecommendationDomain>> = {
  STEREO: 'stereo',
  MASTERING: 'master',
  MIDI: 'groove',
};

/**
 * Best-effort production-domain inference for a recommendation. Returns null
 * when the card cannot be attributed (the badge then renders nothing).
 */
export function inferRecommendationDomain(
  trackContext?: string | null,
  category?: string | null,
): RecommendationDomain | null {
  if (trackContext) {
    const low = trackContext.toLowerCase();
    for (const [keyword, domain] of DOMAIN_KEYWORDS) {
      if (low.includes(keyword)) return domain;
    }
  }
  if (category) {
    const mapped = CATEGORY_DOMAIN[category.toUpperCase()];
    if (mapped) return mapped;
  }
  return null;
}

/** Verification entry for a domain, or null if the artifact has no entry. */
export function verificationForDomain(
  domain: RecommendationDomain | null,
  artifact: RecommendationVerificationArtifact = RECOMMENDATION_VERIFICATION,
): DomainVerification | null {
  if (!domain) return null;
  return artifact.perDomain[domain] ?? null;
}

/**
 * Resolve a recommendation card to its verification entry. Returns null when the
 * card has no inferable domain — the badge degrades to rendering nothing.
 */
export function verificationForRecommendation(
  rec: { trackContext?: string | null; category?: string | null },
  artifact: RecommendationVerificationArtifact = RECOMMENDATION_VERIFICATION,
): DomainVerification | null {
  const domain = inferRecommendationDomain(rec.trackContext, rec.category);
  return verificationForDomain(domain, artifact);
}

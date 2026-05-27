/**
 * Corpus-verification artifact — the data source for the per-recommendation
 * verification badge (GOAL.md sub-goal 4).
 *
 * GENERATED. Regenerate after scoring the corpus:
 *   ./venv/bin/python apps/backend/scripts/evaluate_recommendations.py \
 *     --source gemini --verification-artifact /tmp/verification.json
 *
 * ⚠️ The current values are from SYNTHETIC PROXY renders (not Ableton) scored
 * against the live Gemini source — see apps/backend/RECOMMENDATION_VERDICT.md.
 * Re-generate from real Live renders for authoritative bands. Confidence factors
 * BOTH corpus support and observed match quality (invariant #4): a domain the
 * corpus exercised but where recs rarely matched stays NONE/LOW, never confident.
 */

export type VerificationConfidence = 'NONE' | 'LOW' | 'MED' | 'HIGH';

/** The seven production domains (PURPOSE.md invariant #5). */
export type RecommendationDomain =
  | 'kick'
  | 'bass'
  | 'melody'
  | 'groove'
  | 'fx'
  | 'stereo'
  | 'master';

export interface DomainVerification {
  support: number;
  meanRecall: number;
  meanScore: number;
  confidence: VerificationConfidence;
}

export interface RecommendationVerificationArtifact {
  fixtures: number;
  sources: string[];
  perDomain: Record<RecommendationDomain, DomainVerification>;
}

export const RECOMMENDATION_VERIFICATION: RecommendationVerificationArtifact = {
  fixtures: 5,
  sources: ["gemini"],
  perDomain: {
    kick: { support: 5, meanRecall: 0.0, meanScore: 0.0, confidence: "NONE" },
    bass: { support: 5, meanRecall: 0.2, meanScore: 0.11, confidence: "LOW" },
    melody: { support: 5, meanRecall: 0.6, meanScore: 0.325, confidence: "LOW" },
    groove: { support: 5, meanRecall: 0.0, meanScore: 0.0, confidence: "NONE" },
    fx: { support: 5, meanRecall: 0.0, meanScore: 0.0, confidence: "NONE" },
    stereo: { support: 5, meanRecall: 0.0, meanScore: 0.0, confidence: "NONE" },
    master: { support: 5, meanRecall: 0.5, meanScore: 0.5504, confidence: "MED" },
  },
};

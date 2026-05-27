/**
 * Per-recommendation corpus-verification badge (GOAL.md sub-goal 4).
 *
 * Shows whether a recommendation type has been validated against the
 * ground-truth corpus, and how strongly, grounded in
 * `aggregate_corpus_verification`'s per-domain match rate + support. Honest per
 * PURPOSE.md invariant #4: support drives the band, and the no-evidence case
 * (confidence NONE — the current pre-render state for the whole corpus) renders
 * nothing rather than implying a verification that does not exist.
 *
 * Built on the `ui/` Pill primitive + tokens (no one-off styled boxes). The
 * hover detail uses the native `title` attribute to avoid a Radix tooltip
 * provider dependency on the recommendation card.
 */

import { Pill } from './ui/Pill';
import type { VerificationConfidence } from '../data/recommendationVerification';
import { verificationForRecommendation } from '../services/recommendationVerification';

type Tone = 'success' | 'warning';
type Variant = 'solid' | 'outline';

const PRESENTATION: Record<
  Exclude<VerificationConfidence, 'NONE'>,
  { tone: Tone; variant: Variant; label: string }
> = {
  HIGH: { tone: 'success', variant: 'solid', label: 'Corpus-verified' },
  MED: { tone: 'success', variant: 'outline', label: 'Corpus-checked' },
  LOW: { tone: 'warning', variant: 'outline', label: 'Lightly checked' },
};

export interface RecommendationVerificationBadgeProps {
  trackContext?: string | null;
  category?: string | null;
}

export function RecommendationVerificationBadge({
  trackContext,
  category,
}: RecommendationVerificationBadgeProps) {
  const verification = verificationForRecommendation({ trackContext, category });
  if (!verification || verification.confidence === 'NONE') {
    // Graceful degradation: no corpus evidence for this card -> no badge.
    return null;
  }
  const { tone, variant, label } = PRESENTATION[verification.confidence];
  const recallPct = Math.round(verification.meanRecall * 100);
  const title =
    `Corpus support: ${verification.support} fixture(s); ` +
    `mean device-role recall ${recallPct}%.` +
    (verification.confidence === 'LOW'
      ? ' Low corpus support — treat as tentative.'
      : '');

  return (
    <Pill
      tone={tone}
      variant={variant}
      size="xs"
      leadingDot
      title={title}
      className="whitespace-nowrap"
      data-testid="rec-verification-badge"
    >
      {label}
    </Pill>
  );
}

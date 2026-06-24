import { toConfidenceBadges } from '../analysisResultsViewModel';
import { ConfidenceBandBadge } from '../sessionMusician/ConfidenceBandBadge';

export function ConfidencePillRow({
  confidenceBadges,
}: {
  confidenceBadges: ReturnType<typeof toConfidenceBadges>;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 px-1">
      {/* Audit Finding #4: chips used to render "{label}: High|Moderate|Low"
        with bespoke success/warning/error tones. Now route through the
        canonical band ladder so the same vocabulary (Solid / Workable /
        Rough / Unreliable) appears across every confidence surface.
        Filter null bands (unparseable values) rather than render a
        misleading default. */}
      {confidenceBadges.map((badge, idx) =>
        badge.band ? (
          <span key={`${badge.label}-${idx}`} className="inline-flex items-center gap-2">
            <span className="text-meta font-mono uppercase tracking-wide text-text-secondary/80">
              {badge.label}:
            </span>
            <ConfidenceBandBadge variant="compact" band={badge.band} />
          </span>
        ) : null,
      )}
    </div>
  );
}

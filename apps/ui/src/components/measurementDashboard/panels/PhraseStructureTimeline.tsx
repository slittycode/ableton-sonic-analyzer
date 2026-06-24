import type { PhraseGrid } from '../../../types';

export const PhraseStructureTimeline = ({ phraseGrid }: { phraseGrid: PhraseGrid }) => {
  const total = phraseGrid.totalBars || 1;
  const tiers = [
    { label: '16', items: phraseGrid.phrases16Bar, color: '#a78bfa', size: 16 },
    { label: '8', items: phraseGrid.phrases8Bar, color: '#fbbf24', size: 8 },
    { label: '4', items: phraseGrid.phrases4Bar, color: '#60a5fa', size: 4 },
  ];

  return (
    <div className="rounded-sm border border-border bg-bg-surface-dark px-4 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">
          Phrase Structure
        </span>
        <span className="text-nano font-mono uppercase tracking-[0.18em] text-[#666]">
          {total} bars
        </span>
      </div>
      <div className="space-y-2.5">
        {tiers.map((tier) => {
          if (!tier.items.length) return null;
          const segCount = tier.items.length;
          return (
            <div
              key={tier.label}
              className="grid grid-cols-[28px_minmax(0,1fr)] items-center gap-2"
            >
              <span
                className="text-micro font-mono font-bold uppercase tracking-[0.18em]"
                style={{ color: `${tier.color}bb` }}
              >
                {tier.label}
              </span>
              <div
                className="flex gap-1"
                style={{ height: tier.size === 16 ? 18 : tier.size === 8 ? 14 : 12 }}
              >
                {Array.from({ length: segCount }, (_, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-center rounded-[2px]"
                    style={{
                      flex: tier.size,
                      background: `linear-gradient(90deg, ${tier.color}22, ${tier.color}12)`,
                      border: `1px solid ${tier.color}45`,
                      boxShadow: `inset 0 1px 0 ${tier.color}18`,
                    }}
                  >
                    <span
                      className="font-mono"
                      style={{ fontSize: 8, color: `${tier.color}80` }}
                    >
                      {tier.label}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

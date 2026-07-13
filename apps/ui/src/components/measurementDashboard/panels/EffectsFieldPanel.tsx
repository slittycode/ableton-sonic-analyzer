export const EffectsFieldPanel = ({
  gatingDetected,
  gatingRate,
  gatingRegularity,
  gatingEventCount,
  pumpingStrength,
  pumpingRegularity,
  pumpingConfidence,
}: {
  gatingDetected?: boolean | null;
  gatingRate?: 'quarter' | '8th' | '16th' | null;
  gatingRegularity?: number | null;
  gatingEventCount?: number | null;
  pumpingStrength?: number | null;
  pumpingRegularity?: number | null;
  pumpingConfidence?: number | null;
}) => {
  const rateLabel = gatingRate ?? 'n/a';

  if (gatingDetected) {
    const pulseStride =
      gatingRate === '16th' ? 1 : gatingRate === '8th' ? 2 : gatingRate === 'quarter' ? 4 : 3;
    const pulseCells = Array.from({ length: 16 }, (_, index) => index % pulseStride === 0);

    return (
      <div className="flex h-full flex-col rounded-sm border border-border-light bg-bg-surface-dark px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <span className="block text-meta font-mono uppercase tracking-wide text-text-secondary">
              Effects Field
            </span>
            <span className="mt-1 block text-eyebrow font-mono uppercase tracking-[0.2em] text-[#fbbf24]">
              Gate Active
            </span>
          </div>
          <span className="text-nano font-mono text-[#fbbf2480]">{rateLabel}</span>
        </div>

        <div className="mt-4 grid grid-cols-8 gap-1.5">
          {pulseCells.map((active, index) => (
            <div
              key={index}
              className="rounded-sm border border-border-light bg-bg-surface-dark"
              style={{
                height: active ? 24 : 12,
                opacity: active ? 0.85 : 0.45,
                boxShadow: active ? '0 0 10px rgba(251,191,36,0.12)' : undefined,
              }}
            >
              <div
                className="h-full rounded-sm bg-gradient-to-t from-[#f59e0b] via-[#fbbf24] to-[#fde68a]"
                style={{ opacity: active ? 0.85 : 0.2 }}
              />
            </div>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-sm border border-border-light bg-bg-surface-dark px-3 py-2">
            <span className="block text-meta font-mono uppercase tracking-wide text-text-secondary">
              Gate Events
            </span>
            <span className="mt-1 block text-sm font-display font-bold text-text-primary">
              {gatingEventCount ?? 'n/a'}
            </span>
          </div>
          <div className="rounded-sm border border-border-light bg-bg-surface-dark px-3 py-2">
            <span className="block text-meta font-mono uppercase tracking-wide text-text-secondary">
              Gate Regularity
            </span>
            <div className="mt-2 h-[6px] rounded-full bg-[#1c1a12]">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[#f59e0b] to-[#fbbf24]"
                style={{ width: `${(gatingRegularity ?? 0) * 100}%`, opacity: 0.9 }}
              />
            </div>
          </div>
        </div>
      </div>
    );
  }

  const fallbackRows = [
    { label: 'Pump Strength', value: pumpingStrength ?? 0, color: '#a78bfa' },
    { label: 'Pump Regularity', value: pumpingRegularity ?? 0, color: '#60a5fa' },
    { label: 'Pump Confidence', value: pumpingConfidence ?? 0, color: '#34d399' },
  ];

  return (
    <div className="flex h-full flex-col rounded-sm border border-border-light bg-bg-surface-dark px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="block text-meta font-mono uppercase tracking-wide text-text-secondary">
            Pump Matrix
          </span>
          <span className="mt-1 block text-eyebrow font-mono uppercase tracking-[0.2em] text-[#a78bfa]">
            No Gating Effect
          </span>
        </div>
        <span className="text-nano font-mono text-[#8c8c8c]">{rateLabel}</span>
      </div>

      <div className="mt-4 space-y-3">
        {fallbackRows.map((row) => (
          <div key={row.label}>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">
                {row.label}
              </span>
              <span className="text-nano font-mono" style={{ color: `${row.color}cc` }}>
                {Math.round(row.value * 100)}%
              </span>
            </div>
            <div className="h-[6px] rounded-full bg-[#181818]">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${row.value * 100}%`,
                  background: `linear-gradient(90deg, ${row.color}66, ${row.color})`,
                  boxShadow: `0 0 10px ${row.color}24`,
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

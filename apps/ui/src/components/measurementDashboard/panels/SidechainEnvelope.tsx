import { formatNumber } from '../lib/formatters';

export const SidechainEnvelope = ({
  envelopeShape,
  pumpingRate,
  pumpingStrength,
  pumpingRegularity,
  pumpingConfidence,
}: {
  envelopeShape?: number[] | null;
  pumpingRate?: string | null;
  pumpingStrength?: number | null;
  pumpingRegularity?: number | null;
  pumpingConfidence?: number | null;
}) => {
  const resolvedStrength = pumpingStrength ?? 0;
  const resolvedRegularity = pumpingRegularity ?? 0;
  const resolvedConfidence = pumpingConfidence ?? 0;
  const contour =
    envelopeShape && envelopeShape.length > 0
      ? envelopeShape
      : Array.from({ length: 16 }, (_, index) => {
          const phase = (index / 15) * Math.PI * 3;
          const duck = Math.max(0, Math.sin(phase)) * (0.38 + resolvedStrength * 0.42);
          const stepAccent = index % 4 === 0 ? resolvedRegularity * 0.22 : 0;
          return 0.34 + duck + stepAccent;
        });

  const max = Math.max(...contour, 0.001);
  const w = 360;
  const h = 88;
  const pad = 6;

  const points = contour.map((v, i) => ({
    x: (i / (contour.length - 1)) * w,
    y: pad + (1 - v / max) * (h - pad * 2),
  }));

  let d = `M${points[0].x},${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const curr = points[i];
    const cpx = (prev.x + curr.x) / 2;
    d += ` C${cpx},${prev.y} ${cpx},${curr.y} ${curr.x},${curr.y}`;
  }
  const fillD = d + ` L${w},${h} L0,${h} Z`;

  const strengthLabel =
    resolvedStrength >= 0.7 ? 'heavy' : resolvedStrength >= 0.4 ? 'moderate' : 'subtle';

  return (
    <div className="flex h-full flex-col rounded-sm border border-border-light bg-bg-surface-dark px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
      <div className="flex items-start justify-between gap-3">
        <span className="text-meta font-mono uppercase tracking-wide text-text-secondary">
          Sidechain Envelope
        </span>
        <span className="text-nano font-mono text-[#a78bfa75]">
          {pumpingRate ?? 'n/a'} · {strengthLabel}
        </span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="mt-3 h-[88px] w-full">
        <defs>
          <linearGradient id="sc-grad-panel" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#a78bfa" stopOpacity="0.3" />
            <stop offset="1" stopColor="#a78bfa" stopOpacity="0.02" />
          </linearGradient>
          <linearGradient id="sc-stroke-panel" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#8d72ee" stopOpacity="0.7" />
            <stop offset="0.55" stopColor="#b493ff" stopOpacity="0.95" />
            <stop offset="1" stopColor="#8d72ee" stopOpacity="0.7" />
          </linearGradient>
        </defs>
        {[0, 4, 8, 12].map((pos) => (
          <line
            key={pos}
            x1={(pos / 15) * w}
            y1="0"
            x2={(pos / 15) * w}
            y2={h}
            stroke="#1e1e1e"
            strokeWidth="0.5"
          />
        ))}
        <path d={fillD} fill="url(#sc-grad-panel)" />
        <path d={d} fill="none" stroke="url(#sc-stroke-panel)" strokeWidth="2.2" opacity="0.95" />
      </svg>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <div className="rounded-sm border border-border-light bg-bg-surface-dark px-3 py-2">
          <span className="block text-meta font-mono uppercase tracking-wide text-text-secondary">
            Confidence
          </span>
          <span className="mt-1 block text-sm font-display font-bold text-text-primary">
            {Math.round(resolvedConfidence * 100)}%
          </span>
        </div>
        <div className="rounded-sm border border-border-light bg-bg-surface-dark px-3 py-2">
          <span className="block text-meta font-mono uppercase tracking-wide text-text-secondary">
            Regularity
          </span>
          <span className="mt-1 block text-sm font-display font-bold text-text-primary">
            {formatNumber(resolvedRegularity, 2)}
          </span>
        </div>
      </div>
    </div>
  );
};

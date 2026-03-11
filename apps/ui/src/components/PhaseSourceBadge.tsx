import React from "react";

interface PhaseSourceBadgeProps {
  source: "measured" | "advisory";
  className?: string;
}

export function PhaseSourceBadge({ source, className = "" }: PhaseSourceBadgeProps) {
  const label = source === "measured" ? "DSP" : "AI";
  const toneClass =
    source === "measured"
      ? "border-accent/40 bg-accent/10 text-accent"
      : "border-border bg-bg-panel/40 text-text-secondary";

  return (
    <span
      className={`inline-flex items-center rounded-sm border px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-[0.2em] ${toneClass} ${className}`.trim()}
    >
      {label}
    </span>
  );
}

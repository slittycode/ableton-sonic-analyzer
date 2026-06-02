import React, { useMemo, useState } from "react";

import type { Phase1Result } from "../types";
import {
  buildPatch,
  patchFileName,
  serializeVital,
  type PatchConfidence,
  type PatchSmithResult,
} from "../services/patchSmith";
import { Button, DeviceRack, Pill, type Tone } from "./ui";

type RackStatus = "idle" | "active" | "success" | "warning";

const CONFIDENCE_TONE: Record<PatchConfidence, Tone> = {
  HIGH: "success",
  MED: "accent",
  LOW: "neutral",
};

const CONFIDENCE_LABEL: Record<PatchConfidence, string> = {
  HIGH: "High confidence",
  MED: "Medium confidence",
  LOW: "Low confidence",
};

function rackStatus(result: PatchSmithResult): RackStatus {
  if (result.manifest.citations.length === 0) return "idle";
  switch (result.manifest.overallConfidence) {
    case "HIGH":
      return "success";
    case "MED":
      return "active";
    default:
      return "warning";
  }
}

function downloadVital(result: PatchSmithResult): void {
  const blob = new Blob([serializeVital(result.preset)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = patchFileName(result.manifest.presetName);
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

export interface PatchSmithPanelProps {
  phase1: Phase1Result;
  className?: string;
}

/**
 * Client-side Vital (`.vital`) patch generator. patchSmith derives the preset
 * deterministically from Phase 1 synthesis measurements; this panel surfaces the
 * cited-parameter manifest + hedges (invariants #2/#4) and offers the download.
 * Gated behind an explicit "Generate" press so untracked tracks don't auto-fill
 * the results surface.
 */
export function PatchSmithPanel({ phase1, className }: PatchSmithPanelProps) {
  const result = useMemo(() => buildPatch(phase1), [phase1]);
  const [generated, setGenerated] = useState(false);

  const { manifest } = result;
  const hasCues = manifest.citations.length > 0;
  const citationCount = manifest.citations.length;

  return (
    <DeviceRack
      name="SYNTH PATCH (VITAL)"
      subtitle="· patchSmith"
      status={generated ? rackStatus(result) : "idle"}
      aria-label="Vital synth patch generator"
      className={className}
      action={
        generated && (
          <Button variant="link" size="sm" onClick={() => downloadVital(result)}>
            Download .vital
          </Button>
        )
      }
    >
      <div className="space-y-3">
        <p className="max-w-xl font-mono text-[11px] leading-snug text-text-secondary">
          A Vital preset derived from this track&apos;s measured synthesis character —
          every parameter cites the Phase 1 measurement behind it. A starting point
          to load and play, not an exact reconstruction.
        </p>

        {!generated && (
          <Button
            variant="primary"
            size="md"
            ledIndicator
            onClick={() => setGenerated(true)}
          >
            Generate Vital patch
          </Button>
        )}

        {generated && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-text-primary">{manifest.presetName}</span>
              <Pill tone={CONFIDENCE_TONE[manifest.overallConfidence]} variant="outline">
                {CONFIDENCE_LABEL[manifest.overallConfidence]}
              </Pill>
              <span className="font-mono text-[10px] text-text-secondary">
                {citationCount} cited parameter{citationCount === 1 ? "" : "s"}
              </span>
            </div>

            {hasCues ? (
              <ul className="space-y-2">
                {manifest.citations.map((c) => (
                  <li key={c.vitalParam} className="border-l-2 border-border-light pl-3">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="font-mono text-[11px] text-text-primary">{c.label}</span>
                      <span className="font-mono text-[11px] text-accent">{c.display}</span>
                      <Pill tone={CONFIDENCE_TONE[c.confidence]} variant="outline">
                        {c.confidence}
                      </Pill>
                    </div>
                    <p className="font-mono text-[10px] leading-snug text-text-secondary">
                      {c.rationale}
                    </p>
                    <p className="font-mono text-[9px] text-text-secondary/70">
                      cites {c.phase1Fields.join(", ")}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="font-mono text-[11px] text-text-secondary">
                No strong synthesis cues were measured — the preset is a neutral
                single-oscillator starting point.
              </p>
            )}

            {manifest.hedges.length > 0 && (
              <ul className="space-y-1" aria-label="patch confidence notes">
                {manifest.hedges.map((hedge, index) => (
                  <li
                    key={index}
                    className="font-mono text-[10px] leading-snug text-warning"
                  >
                    ⚠ {hedge}
                  </li>
                ))}
              </ul>
            )}

            <Button
              variant="primary"
              size="md"
              ledIndicator
              onClick={() => downloadVital(result)}
            >
              Download .vital preset
            </Button>
          </div>
        )}
      </div>
    </DeviceRack>
  );
}

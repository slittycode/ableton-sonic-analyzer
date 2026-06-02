import React, { useState } from "react";

import type { Phase1Result } from "../types";
import { decodeWavPcm } from "../services/browserLoudness/wavDecoder";
import {
  computeLoudnessParity,
  type LoudnessParityReport,
} from "../services/browserLoudness/parity";
import {
  loadBrowserLoudnessModule,
  measureWithModule,
} from "../services/browserLoudness/loader";
import { Button, DeviceRack, Pill } from "./ui";

type PanelState =
  | { kind: "idle" }
  | { kind: "measuring" }
  | { kind: "done"; report: LoudnessParityReport }
  | { kind: "unsupported" } // not a decodable WAV
  | { kind: "unavailable" } // WASM core not built/served
  | { kind: "error"; message: string };

function fmtLufs(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}

export interface BrowserLoudnessPanelProps {
  phase1: Phase1Result;
  audioFile: File | null;
  className?: string;
}

/**
 * WS3c: in-browser loudness parity readout. Decodes the uploaded WAV at its
 * native rate and measures it with the asa-dsp (WASM core), comparing the LUFS
 * scalars against the authoritative Phase 1 Essentia values. Additive and
 * flag-gated; Phase 1 stays authoritative. WAV-only and true-peak-free by
 * design (see the service modules).
 */
export function BrowserLoudnessPanel({ phase1, audioFile, className }: BrowserLoudnessPanelProps) {
  const [state, setState] = useState<PanelState>({ kind: "idle" });

  async function handleMeasure(): Promise<void> {
    if (!audioFile) {
      setState({ kind: "error", message: "No source file is available to measure." });
      return;
    }
    setState({ kind: "measuring" });
    try {
      const decoded = decodeWavPcm(await audioFile.arrayBuffer());
      if (!decoded) {
        setState({ kind: "unsupported" });
        return;
      }
      const module = await loadBrowserLoudnessModule();
      if (!module) {
        setState({ kind: "unavailable" });
        return;
      }
      const reading = measureWithModule(module, decoded);
      setState({ kind: "done", report: computeLoudnessParity(reading, phase1) });
    } catch (err) {
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : "Browser loudness measurement failed.",
      });
    }
  }

  return (
    <DeviceRack
      name="BROWSER LOUDNESS"
      subtitle="· parity (experimental)"
      status={state.kind === "done" ? "active" : "idle"}
      aria-label="Browser loudness parity"
      className={className}
    >
      <div className="space-y-3">
        <p className="max-w-xl font-mono text-[11px] leading-snug text-text-secondary">
          Measures this track&apos;s LUFS in your browser (asa-dsp / WASM) and compares
          it to the authoritative Phase 1 Essentia reading. A parity diagnostic —
          Phase 1 stays the source of truth. WAV input only; true peak is omitted
          (it diverges on broadband content).
        </p>

        {state.kind !== "done" && (
          <Button
            variant="primary"
            size="md"
            ledIndicator
            onClick={handleMeasure}
            disabled={state.kind === "measuring" || !audioFile}
          >
            {state.kind === "measuring" ? "Measuring…" : "Measure in browser"}
          </Button>
        )}

        {state.kind === "unsupported" && (
          <p className="font-mono text-[11px] text-text-secondary">
            Browser loudness currently decodes WAV only. This source isn&apos;t a WAV
            (FLAC/MP3 decoding is a planned follow-up), so there&apos;s nothing to compare.
          </p>
        )}

        {state.kind === "unavailable" && (
          <p className="font-mono text-[11px] text-text-secondary">
            The browser loudness core isn&apos;t available. Build
            <span className="text-text-primary"> packages/loudness-spectro-wasm</span> and set
            <span className="text-text-primary"> VITE_BROWSER_LOUDNESS_WASM_URL</span> to enable it.
          </p>
        )}

        {state.kind === "error" && (
          <p className="font-mono text-[11px] text-error" role="alert">
            {state.message}
          </p>
        )}

        {state.kind === "done" && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[11px] text-text-secondary">
                Integrated delta (browser − Essentia):
              </span>
              <Pill
                tone={state.report.integratedWithinTolerance ? "success" : "warning"}
                variant="outline"
              >
                {state.report.integratedDelta === null
                  ? "n/a"
                  : `${state.report.integratedDelta >= 0 ? "+" : ""}${state.report.integratedDelta.toFixed(2)} LU`}
              </Pill>
              <span className="font-mono text-[10px] text-text-secondary/70">
                tolerance ±{state.report.toleranceLu} LU
              </span>
            </div>

            <table className="w-full font-mono text-[11px]">
              <thead>
                <tr className="text-text-secondary/60">
                  <th className="text-left font-normal">Metric</th>
                  <th className="text-right font-normal">Essentia</th>
                  <th className="text-right font-normal">Browser</th>
                  <th className="text-right font-normal">Δ LU</th>
                </tr>
              </thead>
              <tbody>
                {state.report.rows.map((row) => (
                  <tr key={row.phase1Field}>
                    <td className="text-text-primary">{row.label}</td>
                    <td className="text-right text-text-secondary">{fmtLufs(row.essentia)}</td>
                    <td className="text-right text-accent">{fmtLufs(row.browser)}</td>
                    <td
                      className={`text-right ${
                        row.withinTolerance === false ? "text-warning" : "text-text-secondary"
                      }`}
                    >
                      {row.delta === null ? "—" : `${row.delta >= 0 ? "+" : ""}${row.delta.toFixed(2)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DeviceRack>
  );
}

/**
 * Browser-loudness ↔ Phase 1 (Essentia) parity computation (WS3c).
 *
 * Compares the in-browser asa-dsp (WASM core) LUFS reading against the
 * authoritative Phase 1 Essentia values and reports per-field deltas. Phase 1
 * stays authoritative (PURPOSE.md invariant #1) — this is an additive readout,
 * never a replacement.
 *
 * Scope is the LUFS scalars only. True peak is deliberately excluded: the #129
 * parity report found asa-dsp's true peak diverges materially from Essentia's on
 * broadband content (~0.6 dBTP), so exposing a browser true-peak readout would
 * mislead until that divergence is gated. (See essentia-parity-report.md.)
 */

import type { Phase1Result } from "../../types";

/** The four LUFS scalars the WASM core can produce. */
export interface BrowserLoudnessReading {
  integrated: number | null;
  range: number | null;
  momentaryMax: number | null;
  shortTermMax: number | null;
}

export interface LoudnessParityRow {
  label: string;
  /** Phase 1 field this row compares against (chain of custody). */
  phase1Field: string;
  browser: number | null;
  essentia: number | null;
  /** browser − essentia, rounded; null when either side is missing. */
  delta: number | null;
  /** |delta| ≤ tolerance; null when not comparable. */
  withinTolerance: boolean | null;
}

export interface LoudnessParityReport {
  rows: LoudnessParityRow[];
  /** The integrated-LUFS delta — the headline parity number. */
  integratedDelta: number | null;
  integratedWithinTolerance: boolean | null;
  toleranceLu: number;
}

/** EBU integrated-loudness agreement target (mirrors the native harness gate). */
export const PARITY_TOLERANCE_LU = 0.1;

type Phase1Loudness = Pick<
  Phase1Result,
  "lufsIntegrated" | "lufsRange" | "lufsMomentaryMax" | "lufsShortTermMax"
>;

function finite(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function buildRow(
  label: string,
  phase1Field: string,
  browser: number | null,
  essentia: number | null,
  toleranceLu: number,
): LoudnessParityRow {
  const b = finite(browser);
  const e = finite(essentia);
  const delta = b !== null && e !== null ? Math.round((b - e) * 1000) / 1000 : null;
  return {
    label,
    phase1Field,
    browser: b,
    essentia: e,
    delta,
    withinTolerance: delta === null ? null : Math.abs(delta) <= toleranceLu,
  };
}

export function computeLoudnessParity(
  browser: BrowserLoudnessReading,
  phase1: Phase1Loudness,
  toleranceLu: number = PARITY_TOLERANCE_LU,
): LoudnessParityReport {
  const rows: LoudnessParityRow[] = [
    buildRow("Integrated", "lufsIntegrated", browser.integrated, phase1.lufsIntegrated, toleranceLu),
    buildRow("Range (LRA)", "lufsRange", browser.range, phase1.lufsRange ?? null, toleranceLu),
    buildRow(
      "Momentary max",
      "lufsMomentaryMax",
      browser.momentaryMax,
      phase1.lufsMomentaryMax ?? null,
      toleranceLu,
    ),
    buildRow(
      "Short-term max",
      "lufsShortTermMax",
      browser.shortTermMax,
      phase1.lufsShortTermMax ?? null,
      toleranceLu,
    ),
  ];

  const integrated = rows[0];
  return {
    rows,
    integratedDelta: integrated.delta,
    integratedWithinTolerance: integrated.withinTolerance,
    toleranceLu,
  };
}

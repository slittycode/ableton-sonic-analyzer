import { describe, expect, it } from "vitest";
import {
  computeLoudnessParity,
  PARITY_TOLERANCE_LU,
} from "../../../src/services/browserLoudness/parity";
import type { Phase1Result } from "../../../src/types";

const phase1 = {
  lufsIntegrated: -9.3,
  lufsRange: 5.2,
  lufsMomentaryMax: -7.1,
  lufsShortTermMax: -8.0,
} as unknown as Phase1Result;

describe("computeLoudnessParity", () => {
  it("builds rows for the four LUFS scalars with browser−essentia deltas", () => {
    const report = computeLoudnessParity(
      { integrated: -9.35, range: 5.2, momentaryMax: -7.0, shortTermMax: -8.05 },
      phase1,
    );
    expect(report.rows.map((r) => r.phase1Field)).toEqual([
      "lufsIntegrated",
      "lufsRange",
      "lufsMomentaryMax",
      "lufsShortTermMax",
    ]);
    const integrated = report.rows[0];
    expect(integrated.delta).toBeCloseTo(-0.05, 3);
    expect(integrated.withinTolerance).toBe(true);
    expect(report.integratedDelta).toBeCloseTo(-0.05, 3);
    expect(report.integratedWithinTolerance).toBe(true);
  });

  it("excludes true peak (withheld per the #129 parity report)", () => {
    const report = computeLoudnessParity(
      { integrated: -9.3, range: null, momentaryMax: null, shortTermMax: null },
      phase1,
    );
    expect(report.rows.some((r) => r.phase1Field.toLowerCase().includes("truepeak"))).toBe(false);
    expect(report.rows).toHaveLength(4);
  });

  it("flags an out-of-tolerance integrated delta", () => {
    const report = computeLoudnessParity(
      { integrated: -9.0, range: null, momentaryMax: null, shortTermMax: null },
      phase1,
    );
    expect(report.integratedDelta).toBeCloseTo(0.3, 3); // -9.0 − (-9.3)
    expect(report.integratedWithinTolerance).toBe(false);
  });

  it("marks a row not-comparable when either side is null", () => {
    const sparse = {
      lufsIntegrated: -9.3,
      lufsRange: null,
      lufsMomentaryMax: null,
      lufsShortTermMax: null,
    } as unknown as Phase1Result;
    const report = computeLoudnessParity(
      { integrated: -9.3, range: 5.0, momentaryMax: null, shortTermMax: null },
      sparse,
    );
    const range = report.rows[1];
    expect(range.delta).toBeNull();
    expect(range.withinTolerance).toBeNull();
  });

  it("defaults to the ±0.1 LU tolerance", () => {
    expect(PARITY_TOLERANCE_LU).toBe(0.1);
  });
});

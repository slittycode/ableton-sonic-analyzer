/**
 * patchSmith: measurement → Vital preset mapping, citation provenance,
 * honest-uncertainty hedging, and .vital re-parse (the machine-verifiable gate).
 */
import { describe, expect, it } from "vitest";
import {
  buildPatch,
  serializeVital,
  patchFileName,
  secondsToEnvValue,
  hzToCutoffSemitone,
  detuneCentsToVital,
  type PatchParameterCitation,
} from "../../src/services/patchSmith";
import type { Phase1Result } from "../../src/types";

// Minimal Phase1 shape; buildPatch only reads the synthesis-relevant fields.
function makePhase1(overrides: Record<string, unknown> = {}): Phase1Result {
  return {
    bpm: 128,
    key: "F minor",
    spectralBalance: {
      subBass: 0.0,
      lowBass: 0.0,
      lowMids: 0.0,
      mids: 0.0,
      upperMids: 0.0,
      highs: 0.0,
      brilliance: 0.0,
    },
    ...overrides,
  } as unknown as Phase1Result;
}

const richSupersaw = makePhase1({
  genreDetail: { genre: "Trance", confidence: 0.8 },
  supersawDetail: {
    isSupersaw: true,
    confidence: 0.82,
    voiceCount: 7,
    avgDetuneCents: 35,
    spectralComplexity: 0.7,
  },
  spectralBalance: {
    // Absolute band energy in dB (~ -100..0), as real Phase 1 emits. subBass
    // sits ~10 dB above the 7-band mean (-18), so the sub-osc mapping engages.
    subBass: -8.0,
    lowBass: -10.0,
    lowMids: -22.0,
    mids: -26.0,
    upperMids: -20.0,
    highs: -16.0,
    brilliance: -24.0,
  },
});

describe("unit mappers", () => {
  it("secondsToEnvValue inverts Vital's seconds = value^4", () => {
    expect(secondsToEnvValue(1)).toBeCloseTo(1.0, 3); // default decay 1.0 == 1 s
    expect(secondsToEnvValue(0.2)).toBeCloseTo(0.2 ** 0.25, 3);
    expect(secondsToEnvValue(100)).toBeCloseTo(2.378, 3); // clamped to 32 s max
    expect(secondsToEnvValue(0)).toBe(0);
    expect(secondsToEnvValue(-1)).toBe(0);
  });

  it("hzToCutoffSemitone maps Hz to Vital's semitone range", () => {
    expect(hzToCutoffSemitone(261.63)).toBeCloseTo(60.0, 1); // middle C ≈ 60
    expect(hzToCutoffSemitone(20000)).toBeLessThanOrEqual(136);
    expect(hzToCutoffSemitone(20)).toBeGreaterThanOrEqual(8);
    expect(hzToCutoffSemitone(0)).toBe(60.0); // invalid → default
  });

  it("detuneCentsToVital is monotonic and clamped to 0..10", () => {
    expect(detuneCentsToVital(0)).toBe(0);
    expect(detuneCentsToVital(35)).toBeGreaterThan(detuneCentsToVital(20));
    expect(detuneCentsToVital(1000)).toBeLessThanOrEqual(10);
  });
});

function citation(result: ReturnType<typeof buildPatch>, vitalParam: string): PatchParameterCitation | undefined {
  return result.manifest.citations.find((c) => c.vitalParam === vitalParam);
}

describe("buildPatch — mapping & citations", () => {
  it("maps a confident supersaw to unison voices + detune, each cited", () => {
    const result = buildPatch(richSupersaw);
    const voices = citation(result, "osc_1_unison_voices");
    const detune = citation(result, "osc_1_unison_detune");

    expect(voices?.value).toBe(7);
    expect(voices?.confidence).toBe("HIGH");
    expect(voices?.phase1Fields).toContain("supersawDetail.voiceCount");
    expect(detune?.phase1Fields).toContain("supersawDetail.avgDetuneCents");
    // Settings actually carry the value.
    expect(result.preset.settings.osc_1_unison_voices).toBe(7);
  });

  it("enables a sub oscillator when measured sub energy is strong, citing subBass", () => {
    const result = buildPatch(richSupersaw);
    const sub = citation(result, "osc_2_on");
    expect(sub?.value).toBe(1.0);
    expect(sub?.phase1Fields).toEqual(["spectralBalance.subBass"]);
    expect(result.preset.settings.osc_2_transpose).toBe(-12.0);
    // The octave + level are cited too, so the manifest accounts for every
    // osc_2 value the preset carries (review follow-up).
    expect(citation(result, "osc_2_transpose")?.value).toBe(-12.0);
    expect(citation(result, "osc_2_transpose")?.phase1Fields).toEqual(["spectralBalance.subBass"]);
    expect(citation(result, "osc_2_level")?.value).toBe(0.5);
  });

  it("maps acid character to a resonant filter with a spectral-placed cutoff", () => {
    const result = buildPatch(
      makePhase1({
        acidDetail: {
          isAcid: true,
          confidence: 0.75,
          resonanceLevel: 0.8,
          centroidOscillationHz: 5,
          bassRhythmDensity: 0.6,
        },
        spectralBalance: {
          // Absolute dB; highs/brilliance sit ~10 dB above the mix average,
          // so the cutoff opens well above the 200 Hz floor.
          subBass: -30,
          lowBass: -28,
          lowMids: -22,
          mids: -18,
          upperMids: -12,
          highs: -6,
          brilliance: -10,
        },
      }),
    );
    expect(citation(result, "filter_1_on")?.value).toBe(1.0);
    const res = citation(result, "filter_1_resonance");
    expect(res?.value).toBeGreaterThan(0.5);
    expect(res?.phase1Fields).toContain("acidDetail.resonanceLevel");
    const cutoff = citation(result, "filter_1_cutoff");
    expect(cutoff?.phase1Fields).toContain("spectralBalance.highs");
    expect(cutoff?.value).toBeGreaterThanOrEqual(8);
    expect(cutoff?.value).toBeLessThanOrEqual(136);
  });

  it("maps bass decay to the amp envelope, cited from averageDecayMs", () => {
    const result = buildPatch(
      makePhase1({
        bassDetail: {
          averageDecayMs: 180,
          type: "punchy",
          transientRatio: 0.6,
          fundamentalHz: 55,
          transientCount: 32,
          swingPercent: 0,
          grooveType: "straight",
        },
      }),
    );
    const decay = citation(result, "env_1_decay");
    expect(decay?.phase1Fields).toEqual(["bassDetail.averageDecayMs"]);
    expect(decay?.value).toBeCloseTo(secondsToEnvValue(0.18), 4);
    // punchy → low sustain
    expect(citation(result, "env_1_sustain")?.value).toBeLessThan(0.3);
  });

  it("every cited parameter carries at least one Phase 1 field (invariant #2)", () => {
    const result = buildPatch(richSupersaw);
    expect(result.manifest.citations.length).toBeGreaterThan(0);
    for (const c of result.manifest.citations) {
      expect(c.phase1Fields.length).toBeGreaterThan(0);
    }
  });
});

describe("buildPatch — spectralBalance read relative to the mix average", () => {
  // Regression for the v1 calibration bug: spectralBalance bands are ABSOLUTE
  // dB (~ -100..0), not relative to the mix. The old guards compared raw
  // absolute values against small thresholds and so never fired on real input.
  it("engages the sub oscillator when sub is prominent vs the mix average (realistic absolute dB)", () => {
    const result = buildPatch(
      makePhase1({
        spectralBalance: {
          subBass: -8, lowBass: -10, lowMids: -22, mids: -26,
          upperMids: -20, highs: -16, brilliance: -24,
        },
      }),
    );
    // subBass (-8) sits ~10 dB above the 7-band mean (-18) → sub layer engages.
    expect(citation(result, "osc_2_on")?.value).toBe(1.0);
    expect(citation(result, "osc_2_on")?.rationale).toMatch(/above the mix average/);
  });

  it("skips the sub oscillator when sub sits below the mix average (golden-like absolute dB)", () => {
    const result = buildPatch(
      makePhase1({
        spectralBalance: {
          subBass: -41.6, lowBass: -4.9, lowMids: -6.1, mids: -41.0,
          upperMids: -53.4, highs: -62.2, brilliance: -64.7,
        },
      }),
    );
    // Real golden track: sub is far below the dominant low-bass body → no sub osc.
    expect(citation(result, "osc_2_on")).toBeUndefined();
  });

  it("opens the acid cutoff above the 200 Hz floor when the top is relatively bright", () => {
    const result = buildPatch(
      makePhase1({
        acidDetail: { isAcid: true, confidence: 0.8, resonanceLevel: 0.7 } as never,
        // A dark overall mix whose top is still the brightest part: absolute
        // highs/brilliance are low but ABOVE the mix mean. The old absolute
        // formula pinned the cutoff to 200 Hz; the relative one opens it.
        spectralBalance: {
          subBass: -50, lowBass: -52, lowMids: -55, mids: -58,
          upperMids: -54, highs: -45, brilliance: -48,
        },
      }),
    );
    // 200 Hz floor ≈ semitone 55; a responsive cutoff sits clearly above it.
    expect(citation(result, "filter_1_cutoff")?.value).toBeGreaterThan(70);
  });
});

describe("buildPatch — honest uncertainty (invariant #4)", () => {
  it("hedges a low-confidence supersaw and marks the params LOW", () => {
    const result = buildPatch(
      makePhase1({
        supersawDetail: {
          isSupersaw: false,
          confidence: 0.3,
          voiceCount: 5,
          avgDetuneCents: 20,
          spectralComplexity: 0.4,
        },
      }),
    );
    expect(citation(result, "osc_1_unison_voices")?.confidence).toBe("LOW");
    expect(result.manifest.hedges.join(" ")).toMatch(/low-confidence supersaw/i);
    expect(result.manifest.overallConfidence).toBe("LOW");
  });

  it("skips the sub oscillator when sub energy is not elevated", () => {
    const result = buildPatch(makePhase1()); // flat spectral balance
    expect(citation(result, "osc_2_on")).toBeUndefined();
    expect(result.preset.settings.osc_2_on).toBe(0.0); // stays at init default
  });

  it("emits no citations and a neutral hedge when nothing is detected", () => {
    const result = buildPatch(makePhase1());
    expect(result.manifest.citations).toHaveLength(0);
    expect(result.manifest.overallConfidence).toBe("LOW");
    expect(result.manifest.hedges.join(" ")).toMatch(/neutral.*starting patch/i);
  });

  it("is deterministic: same input yields identical output", () => {
    expect(buildPatch(richSupersaw)).toEqual(buildPatch(richSupersaw));
  });
});

describe("serializeVital — .vital re-parse gate", () => {
  it("produces JSON that re-parses with the expected Vital shape and in-range values", () => {
    const { preset } = buildPatch(richSupersaw);
    const text = serializeVital(preset);

    const parsed = JSON.parse(text);
    expect(parsed.synth_version).toBe("1.5.5");
    expect(typeof parsed.preset_name).toBe("string");
    expect(parsed.author).toBe("ASA patchSmith");
    expect(typeof parsed.settings).toBe("object");

    // Every settings value is a finite number (Vital reads a float control map).
    for (const [key, value] of Object.entries(parsed.settings)) {
      expect(typeof value, key).toBe("number");
      expect(Number.isFinite(value as number), key).toBe(true);
    }
    // Spot-check the controls we set are within Vital's documented ranges.
    expect(parsed.settings.osc_1_unison_voices).toBeGreaterThanOrEqual(1);
    expect(parsed.settings.osc_1_unison_voices).toBeLessThanOrEqual(16);
    expect(parsed.settings.osc_1_unison_detune).toBeGreaterThanOrEqual(0);
    expect(parsed.settings.osc_1_unison_detune).toBeLessThanOrEqual(10);
    expect(parsed.settings.osc_1_level).toBeGreaterThanOrEqual(0);
    expect(parsed.settings.osc_1_level).toBeLessThanOrEqual(1);
  });

  it("derives a filesystem-safe .vital filename", () => {
    expect(patchFileName("ASA Trance F minor")).toBe("ASA_Trance_F_minor.vital");
    expect(patchFileName("")).toBe("ASA_Patch.vital");
  });
});

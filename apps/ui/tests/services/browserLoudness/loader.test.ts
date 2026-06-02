import { describe, expect, it, vi } from "vitest";
import {
  adaptWasmLoudness,
  measureWithModule,
} from "../../../src/services/browserLoudness/loader";

describe("adaptWasmLoudness", () => {
  it("maps snake_case wasm fields and releases the wasm-owned result", () => {
    const free = vi.fn();
    const reading = adaptWasmLoudness({
      integrated_lufs: -14.7,
      loudness_range: 6.0,
      momentary_max_lufs: -12.5,
      short_term_max_lufs: -13.2,
      free,
    });
    expect(reading).toEqual({
      integrated: -14.7,
      range: 6.0,
      momentaryMax: -12.5,
      shortTermMax: -13.2,
    });
    expect(free).toHaveBeenCalledOnce();
  });

  it("normalizes NaN to null (the WASM core's 'no gated block' signal)", () => {
    const reading = adaptWasmLoudness({
      integrated_lufs: NaN,
      loudness_range: NaN,
      momentary_max_lufs: -12.5,
      short_term_max_lufs: NaN,
    });
    expect(reading.integrated).toBeNull();
    expect(reading.range).toBeNull();
    expect(reading.momentaryMax).toBe(-12.5);
    expect(reading.shortTermMax).toBeNull();
  });
});

describe("measureWithModule", () => {
  it("invokes measureLoudness with decoded PCM and adapts the result", () => {
    const measureLoudness = vi.fn(() => ({
      integrated_lufs: -10.0,
      loudness_range: 4.0,
      momentary_max_lufs: -8.0,
      short_term_max_lufs: -9.0,
    }));
    const decoded = { samples: new Float32Array([0, 0.5, -0.5, 0]), channels: 2, sampleRate: 48000 };

    const out = measureWithModule({ measureLoudness }, decoded);

    expect(measureLoudness).toHaveBeenCalledWith(decoded.samples, 2, 48000);
    expect(out.integrated).toBe(-10.0);
    expect(out.shortTermMax).toBe(-9.0);
  });
});

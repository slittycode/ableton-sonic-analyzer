/**
 * Guarded loader + result adapter for the browser loudness WASM core (WS3c).
 *
 * The `@asa/loudness-spectro-wasm` package is NOT a build dependency of the UI
 * (its `pkg/` is gitignored and not built in CI), so we never statically import
 * it — that would break the production build. Instead we dynamically import the
 * built web glue from a runtime URL (`VITE_BROWSER_LOUDNESS_WASM_URL`), guarded
 * so any failure degrades to "unavailable" rather than crashing.
 *
 * Activation (documented, off by default): build the web target in
 * `packages/loudness-spectro-wasm` (`npm run build`), serve `pkg/`, and point
 * `VITE_BROWSER_LOUDNESS_WASM_URL` at its entry JS. Until then the loader
 * returns null and the panel shows the unavailable state.
 */

import type { BrowserLoudnessReading } from "./parity";
import type { DecodedWavPcm } from "./wavDecoder";

/** The raw shape the WASM `measureLoudness` returns (snake_case from Rust). */
export interface RawWasmLoudness {
  integrated_lufs: number;
  loudness_range: number;
  momentary_max_lufs: number;
  short_term_max_lufs: number;
  free?: () => void;
}

export interface LoudnessWasmModule {
  /** wasm-bindgen init (idempotent). */
  default?: () => Promise<unknown>;
  measureLoudness: (samples: Float32Array, channels: number, sampleRate: number) => RawWasmLoudness;
}

function toFinite(value: number): number | null {
  // The WASM core returns NaN when a value is undefined (no gated block).
  return Number.isFinite(value) ? value : null;
}

/**
 * Map a raw WASM result to our reading, normalizing NaN→null and releasing the
 * wasm-owned object. Pure and unit-testable (the part worth pinning); the
 * dynamic import below is the thin, environment-bound piece.
 */
export function adaptWasmLoudness(raw: RawWasmLoudness): BrowserLoudnessReading {
  const reading: BrowserLoudnessReading = {
    integrated: toFinite(raw.integrated_lufs),
    range: toFinite(raw.loudness_range),
    momentaryMax: toFinite(raw.momentary_max_lufs),
    shortTermMax: toFinite(raw.short_term_max_lufs),
  };
  raw.free?.();
  return reading;
}

/** Measure a decoded clip with an already-loaded module (testable with a mock). */
export function measureWithModule(
  module: LoudnessWasmModule,
  decoded: DecodedWavPcm,
): BrowserLoudnessReading {
  const raw = module.measureLoudness(decoded.samples, decoded.channels, decoded.sampleRate);
  return adaptWasmLoudness(raw);
}

function wasmModuleUrl(): string | null {
  const env = (import.meta as { env?: Record<string, string | undefined> }).env;
  const url = env?.VITE_BROWSER_LOUDNESS_WASM_URL?.trim();
  return url ? url : null;
}

let modulePromise: Promise<LoudnessWasmModule | null> | null = null;

/**
 * Dynamically load + init the WASM module, memoized. Returns null when no URL is
 * configured or the import/init fails — never throws into the UI. The
 * `@vite-ignore` keeps the build from trying to resolve the (unbuilt) package.
 */
export function loadBrowserLoudnessModule(): Promise<LoudnessWasmModule | null> {
  if (modulePromise) return modulePromise;
  const url = wasmModuleUrl();
  if (!url) return Promise.resolve(null);

  modulePromise = (async () => {
    try {
      const module = (await import(/* @vite-ignore */ url)) as LoudnessWasmModule;
      if (typeof module.default === "function") {
        await module.default();
      }
      return typeof module.measureLoudness === "function" ? module : null;
    } catch {
      return null;
    }
  })();
  return modulePromise;
}

/** Test hook: reset the memoized module promise. */
export function resetBrowserLoudnessModuleForTests(): void {
  modulePromise = null;
}

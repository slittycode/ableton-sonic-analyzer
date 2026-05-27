/**
 * Deterministic recommendation source bridge (GOAL.md sub-goal 3 inner loop).
 *
 * EVAL / RESEARCH ONLY. Wraps the product's deterministic recommendation engine
 * (`apps/ui/src/data/abletonDevices.ts`) and emits the scorer's normalized rec
 * shape so `scripts/evaluate_recommendations.py --source deterministic` can grade
 * the *free* path without a Gemini call. Importing the real module keeps a single
 * source of truth — no Python re-port to drift from the TS.
 *
 * Runs on Node 23+ native TypeScript type-stripping (no bundler, no `npm install`
 * needed — abletonDevices.ts is import-pure):
 *
 *   node apps/backend/scripts/emit_deterministic_recs.ts <audio_features.json> \
 *     > tests/fixtures/recommendation_tracks/<slug>/recommendations.deterministic.json
 *
 * Input is an `AudioFeatures` JSON (bpm, key{root,scale}, crestFactor,
 * onsetDensity, duration, bpmConfidence, spectralCentroidMean, spectralBands[]).
 * Projecting a real Phase 1 fingerprint into `AudioFeatures` is the app's own job
 * (analyzer.ts) and is render-gated — see apps/backend/NEEDS.md. This bridge is
 * the faithful, drift-free half that turns engine output into normalized recs;
 * the deterministic path is uncited by design, so every rec carries empty
 * citations (the scorer's custody penalty then reflects that real difference vs
 * the cited Gemini path).
 */

import { readFileSync } from "node:fs";
import {
  getFXRecommendations,
  getInstrumentRecommendations,
  type AudioFeatures,
} from "../../ui/src/data/abletonDevices.ts";

interface NormalizedRec {
  domain: string;
  device: string;
  parameter: string | null;
  value: string | null;
  citations: string[];
  family: string | null;
}

// Spectral-band element -> production domain. The deterministic engine is
// band-centric, so attribution is coarse (it has no explicit kick/stereo/master
// instrument recs — those arrive via the FX rules below).
const BAND_DOMAIN: Record<string, string> = {
  "Sub Bass": "bass",
  "Low Bass": "bass",
  "Low Mids": "melody",
  Mids: "melody",
  "Upper Mids": "melody",
  Highs: "groove",
  Brilliance: "groove",
};

// FX-rule text -> domain by keyword, else a sensible default.
function fxDomain(text: string): string {
  const low = text.toLowerCase();
  if (/\bbass\b/.test(low)) return "bass";
  if (/drum|transient|hi-hat|hat|percuss/.test(low)) return "groove";
  if (/master|bus group|bus compression|cohesion/.test(low)) return "master";
  if (/reverb|chorus|width|stereo|ambient|space/.test(low)) return "fx";
  return "fx";
}

function loadCatalogDeviceNames(): string[] {
  const url = new URL("../prompts/live12_device_catalog.json", import.meta.url);
  const raw = JSON.parse(readFileSync(url, "utf-8")) as {
    devices: Array<{ name: string }>;
  };
  // Longest names first so "Glue Compressor" wins over "Compressor".
  return raw.devices.map((d) => d.name).sort((a, b) => b.length - a.length);
}

function firstCatalogDevice(text: string, names: string[]): string | null {
  for (const name of names) {
    if (text.includes(name)) return name;
  }
  return null;
}

function main(): void {
  const inputPath = process.argv[2];
  if (!inputPath) {
    console.error("usage: node emit_deterministic_recs.ts <audio_features.json>");
    process.exit(2);
  }
  const features = JSON.parse(readFileSync(inputPath, "utf-8")) as AudioFeatures;
  const catalogNames = loadCatalogDeviceNames();
  const recs: NormalizedRec[] = [];

  // Instrument recs: parse "Device — Preset: settings" -> device + raw settings.
  for (const inst of getInstrumentRecommendations(features.spectralBands ?? [])) {
    const bandName = inst.element.replace(/ Element$/, "");
    const domain = BAND_DOMAIN[bandName] ?? "melody";
    const device = inst.abletonDevice.split(" — ")[0]?.trim() ?? inst.abletonDevice;
    const settings = inst.abletonDevice.split(": ").slice(1).join(": ") || null;
    recs.push({
      domain,
      device,
      parameter: null,
      value: settings,
      citations: [], // deterministic path is uncited by design
      family: null,
    });
  }

  // FX recs: extract the first named catalog device from the prose.
  for (const fx of getFXRecommendations(features)) {
    const device = firstCatalogDevice(fx.recommendation, catalogNames);
    if (!device) continue;
    recs.push({
      domain: fxDomain(`${fx.artifact} ${fx.recommendation}`),
      device,
      parameter: null,
      value: null,
      citations: [],
      family: null,
    });
  }

  process.stdout.write(JSON.stringify(recs, null, 2) + "\n");
}

main();

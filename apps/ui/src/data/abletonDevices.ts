/**
 * Ableton Live 12 Device Knowledge Base
 *
 * Maps spectral characteristics to specific Ableton device recommendations.
 * This is deterministic — no hallucination possible.
 */

export interface DeviceRecommendation {
  device: string;
  preset: string;
  settings: string;
}

export interface BandDeviceMap {
  dominant: DeviceRecommendation;
  present: DeviceRecommendation;
}

export interface SpectralBandEnergy {
  name: string;
  rangeHz: [number, number];
  averageDb: number;
  peakDb: number;
  dominance: 'absent' | 'present' | 'dominant';
}

export interface AudioFeatures {
  bpm: number;
  key: {
    root: string;
    scale: string;
  };
  crestFactor: number;
  onsetDensity: number;
  duration: number;
  bpmConfidence: number;
  spectralBands: SpectralBandEnergy[];
  spectralCentroidMean: number;
}

const BAND_DEVICES: Record<string, BandDeviceMap> = {
  'Sub Bass': {
    dominant: {
      device: 'Operator',
      preset: 'Sine Sub Bass',
      settings:
        'Osc A: Sine, Coarse 0, Level 100%. Filter: LP 24dB, Freq 80Hz. Amp Env: A 0ms, D 0ms, S 100%, R 50ms.',
    },
    present: {
      device: 'Wavetable',
      preset: 'Sub Warmth',
      settings:
        'Osc 1: Basic Shapes > Sine/Triangle blend. Filter 1: LP 12dB @ 120Hz. Sub Osc: On, -12st.',
    },
  },
  'Low Bass': {
    dominant: {
      device: 'Wavetable',
      preset: 'Analog Bass',
      settings:
        'Osc 1: Basic Shapes > Saw. Osc 2: Square -12st. Filter 1: LP 18dB @ 250Hz, Res 20%. Drive: 15%.',
    },
    present: {
      device: 'Operator',
      preset: 'FM Bass',
      settings:
        'Algorithm 1. Osc A: Sine. Osc B: Sine, Coarse 1, Fine 0, Level 40%. Filter: LP 12dB @ 300Hz.',
    },
  },
  'Low Mids': {
    dominant: {
      device: 'Analog',
      preset: 'Warm Pad',
      settings:
        'Osc 1: Saw. Osc 2: Square, Fine +5. Filter: LP 12dB @ 500Hz, Res 15%. Chorus: On.',
    },
    present: {
      device: 'Wavetable',
      preset: 'Body Synth',
      settings:
        'Osc 1: Spectral > Formant. Filter 1: BP 12dB @ 400Hz, Res 25%.',
    },
  },
  Mids: {
    dominant: {
      device: 'Wavetable',
      preset: 'Lead Synth',
      settings:
        'Osc 1: Basic Shapes > Saw. Unison: 4 voices, Amount 30%. Filter 1: LP 24dB @ 3kHz. Amp Env: A 5ms, D 200ms, S 70%, R 100ms.',
    },
    present: {
      device: 'Operator',
      preset: 'Electric Keys',
      settings:
        'Algorithm 2. Osc A: Sine. Osc B: Sine, Coarse 2, Level 30%. Osc C: Sine, Coarse 3, Level 15%. Amp Env: A 2ms, D 800ms, S 40%, R 200ms.',
    },
  },
  'Upper Mids': {
    dominant: {
      device: 'Wavetable',
      preset: 'Pluck Lead',
      settings:
        'Osc 1: Basic Shapes > Saw. Filter 1: BP 12dB @ 3.5kHz, Res 30%. Amp Env: A 1ms, D 300ms, S 20%, R 150ms.',
    },
    present: {
      device: 'Operator',
      preset: 'Bright Stab',
      settings:
        'Algorithm 4. Osc A: Saw. Osc B: Square, Coarse 1, Level 50%. Filter: HP 6dB @ 1kHz + LP 12dB @ 6kHz.',
    },
  },
  Highs: {
    dominant: {
      device: 'Simpler',
      preset: 'Hi-Hat / Cymbal Layer',
      settings:
        'Load a noise sample. Filter: HP 18dB @ 6kHz. Amp Env: A 0ms, D 80ms, S 0%, R 50ms. Spread: 80%.',
    },
    present: {
      device: 'Operator',
      preset: 'Noise Texture',
      settings:
        'Osc D: Noise, Level 60%. Filter: BP 12dB @ 8kHz, Res 10%. Amp Env: A 0ms, D 150ms, S 15%, R 100ms.',
    },
  },
  Brilliance: {
    dominant: {
      device: 'Operator',
      preset: 'Shimmer Air',
      settings:
        'Osc A: Sine, Coarse 0. Osc B: Noise, Level 20%. Filter: HP 12dB @ 10kHz. Reverb Send: 60%.',
    },
    present: {
      device: 'Wavetable',
      preset: 'Airy Texture',
      settings:
        'Osc 1: Spectral > Breathy. Filter 1: HP 12dB @ 8kHz. Chorus: On, Rate 0.3Hz.',
    },
  },
};

// FX recommendations based on detected audio characteristics
interface FXRule {
  condition: (features: AudioFeatures) => boolean;
  artifact: string;
  recommendation: string;
}

const FX_RULES: FXRule[] = [
  {
    condition: (f) => f.crestFactor < 6,
    artifact: 'Heavy dynamic compression detected (low crest factor)',
    recommendation:
      'Ableton Glue Compressor: Threshold -15dB, Ratio 4:1, Attack 0.1ms, Release Auto. Makeup +3dB. Or Drum Buss for parallel compression.',
  },
  {
    condition: (f) => f.crestFactor >= 6 && f.crestFactor < 12,
    artifact: 'Moderate compression / controlled dynamics',
    recommendation:
      'Ableton Compressor: Threshold -12dB, Ratio 3:1, Attack 10ms, Release 100ms. Use on bus groups for glue.',
  },
  {
    condition: (f) => f.crestFactor >= 12,
    artifact: 'High dynamic range — minimal compression',
    recommendation:
      'Consider light bus compression: Glue Compressor, Ratio 2:1, Attack 30ms, Release Auto. Subtle gain reduction (1-3dB) for cohesion.',
  },
  {
    condition: (f) => {
      const sub = f.spectralBands.find((b) => b.name === 'Sub Bass');
      return sub?.dominance === 'dominant';
    },
    artifact: 'Dominant sub-bass energy detected',
    recommendation:
      'Ableton Saturator on bass bus: Drive 5dB, Soft Clip mode. Adds harmonics that translate on small speakers. Follow with EQ Eight: HP at 30Hz to control rumble.',
  },
  {
    condition: (f) => f.spectralCentroidMean > 3000,
    artifact: 'Bright overall spectrum — high spectral centroid',
    recommendation:
      'If harshness: EQ Eight, cut 2-4kHz by 2-3dB with wide Q. Ableton Channel EQ on master: reduce Highs by 1-2dB for smoother top end.',
  },
  {
    condition: (f) => f.spectralCentroidMean < 1000,
    artifact: 'Dark overall spectrum — low spectral centroid',
    recommendation:
      'Add presence: EQ Eight, boost 3-5kHz by 2-3dB with a gentle Q. Ableton Exciter on master: Freq 3kHz, Drive 10-15%.',
  },
  {
    condition: (f) => f.onsetDensity > 8,
    artifact: 'High rhythmic density detected (many transients)',
    recommendation:
      'Use Ableton Drum Buss for punch: Crunch 20%, Damp 8kHz, Comp Medium. Gate or sidechain to prevent mud from overlapping transients.',
  },
  {
    condition: (f) => f.onsetDensity < 2 && f.duration > 5,
    artifact: 'Low transient density — sustained/ambient content',
    recommendation:
      'Ableton Reverb: Decay 3-5s, Size 80, Diffusion Network On. Or Hybrid Reverb with convolution IR for natural space. Chorus for width.',
  },
];

/**
 * Generate instrument recommendations from spectral band analysis.
 */
export function getInstrumentRecommendations(bands: SpectralBandEnergy[]): {
  element: string;
  timbre: string;
  frequency: string;
  abletonDevice: string;
}[] {
  const instruments: {
    element: string;
    timbre: string;
    frequency: string;
    abletonDevice: string;
  }[] = [];

  for (const band of bands) {
    if (band.dominance === 'absent') continue;

    const deviceMap = BAND_DEVICES[band.name];
    if (!deviceMap) continue;

    const level = band.dominance === 'dominant' ? 'dominant' : 'present';
    const rec = deviceMap[level];

    const timbreDesc =
      band.dominance === 'dominant'
        ? `Strong presence in the ${band.name.toLowerCase()} range (${band.averageDb} dB avg). This is a defining element of the mix.`
        : `Moderate activity in the ${band.name.toLowerCase()} range (${band.averageDb} dB avg). Supports the mix character.`;

    instruments.push({
      element: `${band.name} Element`,
      timbre: timbreDesc,
      frequency: `${band.rangeHz[0]}–${band.rangeHz[1]} Hz (peak: ${band.peakDb} dB)`,
      abletonDevice: `${rec.device} — ${rec.preset}: ${rec.settings}`,
    });
  }

  return instruments;
}

/**
 * Generate FX chain recommendations from audio features.
 */
export function getFXRecommendations(
  features: AudioFeatures
): { artifact: string; recommendation: string }[] {
  return FX_RULES.filter((rule) => rule.condition(features)).map((rule) => ({
    artifact: rule.artifact,
    recommendation: rule.recommendation,
  }));
}

/**
 * Generate the "secret sauce" section from the most interesting feature.
 */
export function getSecretSauce(features: AudioFeatures): {
  trick: string;
  execution: string;
} {
  // Find the most notable characteristic
  const dominantBands = features.spectralBands.filter(
    (b) => b.dominance === 'dominant'
  );
  const isDense = features.onsetDensity > 6;
  const isCompressed = features.crestFactor < 8;
  const isBright = features.spectralCentroidMean > 2500;

  if (dominantBands.length >= 3 && isCompressed) {
    return {
      trick: 'Wall-of-Sound Layering with Bus Compression',
      execution: `Multiple frequency bands are saturated (${dominantBands.map((b) => b.name).join(', ')}), with a crest factor of ${features.crestFactor} dB indicating aggressive bus compression. In Ableton: 1) Group all elements into a single bus. 2) Add Glue Compressor: 4:1, Attack 0.01ms, Release 0.1s, Makeup to taste. 3) Follow with Saturator (Soft Clip) at Drive 3-5dB. 4) Use Utility to check mono compatibility — dense mixes risk phase cancellation.`,
    };
  }

  if (isDense && features.bpmConfidence > 0.7) {
    return {
      trick: `Tight Rhythmic Programming at ${features.bpm} BPM`,
      execution: `High onset density (${features.onsetDensity}/s) with strong tempo lock suggests carefully programmed rhythms. In Ableton: 1) Set project to ${features.bpm} BPM. 2) Use Groove Pool with 16th note groove at 60-70% to add human feel. 3) Layer transient-rich elements (hi-hats, percussion) and use Drum Rack's choke groups for realistic interplay. 4) Sidechain kick to bass with Compressor (Fast Attack, Release ~200ms).`,
    };
  }

  if (
    isBright &&
    features.spectralBands.find((b) => b.name === 'Brilliance')?.dominance !==
      'absent'
  ) {
    return {
      trick: 'Air and Presence Engineering',
      execution: `High spectral centroid (${features.spectralCentroidMean} Hz) with energy in the brilliance range. In Ableton: 1) Use EQ Eight with a wide +2dB shelf at 10kHz on lead elements. 2) Add Chorus-Ensemble with Rate 0.2Hz for subtle shimmer. 3) Reverb (Hybrid Reverb) with short decay (0.5-1s) and HP filter at 2kHz for airy reflections only. 4) Use Utility > Width at 120% on the reverb return for spatial enhancement.`,
    };
  }

  const subBand = features.spectralBands.find((b) => b.name === 'Sub Bass');
  if (subBand?.dominance === 'dominant') {
    return {
      trick: 'Sub Bass Design and Low-End Control',
      execution: `Dominant sub-bass energy (${subBand.averageDb} dB avg) anchors the mix. In Ableton: 1) Use Operator with a pure sine oscillator at the fundamental. 2) Add Saturator (Medium Curve) with Drive 5-8dB to generate harmonics for speaker translation. 3) Sidechain to kick with Compressor (Ratio 4:1, Attack 0.01ms, Release 150ms). 4) EQ Eight: surgical cut at 30Hz (rumble) and at the kick's fundamental for separation.`,
    };
  }

  // Generic fallback
  return {
    trick: `Balanced Mix Architecture at ${features.bpm} BPM in ${features.key.root} ${features.key.scale}`,
    execution: `This track shows balanced spectral energy with a tempo of ${features.bpm} BPM. In Ableton: 1) Set up your session in ${features.key.root} ${features.key.scale}. 2) Use a reference track on a dedicated return and A/B with Utility (phase flip trick). 3) Start with gain staging: aim for -6dB peak on each track, -3dB on busses. 4) Apply EQ Eight on every channel — cut before you boost. Use the analyzer to find masking frequencies between competing elements.`,
  };
}

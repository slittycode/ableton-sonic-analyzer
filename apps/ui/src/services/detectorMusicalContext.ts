import type { Phase1Result, SidechainDetail, SynthesisCharacter } from '../types';

/**
 * Maps DSP measurement data to producer-friendly musical descriptions
 * with Ableton Live production tips. All functions are pure.
 */

export function describeSidechain(detail: SidechainDetail): string {
  const pct = Math.round(detail.pumpingStrength * 100);
  const rate = detail.pumpingRate;
  const rateLabel = rate ? `${rate}-note` : 'tempo-synced';
  let desc: string;

  if (detail.pumpingStrength < 0.2) {
    desc = `Minimal ${rateLabel} sidechain pump (${pct}%). May be volume automation rather than compression. In Ableton: light Compressor sidechain from kick if desired.`;
  } else if (detail.pumpingStrength < 0.5) {
    desc = `Subtle ${rateLabel} pump (${pct}%). In Ableton: Compressor sidechain from kick, ~3:1 ratio, fast attack, medium release.`;
  } else if (detail.pumpingStrength < 0.7) {
    desc = `Moderate ${rateLabel} pump effect (${pct}%). In Ableton: Compressor sidechain, 4:1 ratio, 0.1ms attack, ~150ms release. Or try Shaper on a send.`;
  } else {
    desc = `Heavy ${rateLabel} pump (${pct}%). This is a defining groove element. Consider LFO Tool or Kickstart for precise rhythmic ducking.`;
  }

  if (detail.pumpingConfidence < 0.5) {
    desc += ` (Low confidence: ${Math.round(detail.pumpingConfidence * 100)}% -- measurement may be unreliable.)`;
  }

  return desc;
}

export function describeAcid(detail: Phase1Result['acidDetail']): string | null {
  if (!detail) return null;

  if (detail.isAcid) {
    return `Strong 303-style resonance (resonance: ${detail.resonanceLevel.toFixed(2)}). Use a resonant low-pass in Auto Filter or your synth filter, with env amount around 60% and accent via velocity modulation (works in Intro/Standard/Suite).`;
  }

  if (detail.confidence > 0.3) {
    return 'Mild filter movement detected but below acid threshold. A subtle resonant filter sweep could add character.';
  }

  return 'No significant acid character detected.';
}

export function describeReverb(detail: Phase1Result['reverbDetail']): string | null {
  if (!detail) return null;

  if (detail.isWet && detail.rt60 !== null) {
    const rt = detail.rt60.toFixed(1);
    if (detail.rt60 < 0.5) {
      return `Tight ambience (RT60: ${rt}s). Use a short plate or room reverb on a send at ~15% wet.`;
    }
    if (detail.rt60 < 1.5) {
      return `Medium room/hall space (RT60: ${rt}s). Use a reverb send at ~25% with matched decay.`;
    }
    if (detail.rt60 < 3.0) {
      return `Spacious reverb (RT60: ${rt}s). Use a hall reverb send at ~30%, consider pre-delay 20-40ms for clarity.`;
    }
    return `Very long reverb tail (RT60: ${rt}s). Atmospheric wash effect. Use a large hall with heavy damping.`;
  }

  if (detail.isWet) {
    return 'Wet signal detected but decay time could not be measured precisely.';
  }

  return 'Dry mix -- minimal reverb detected. Production is front-and-center.';
}

export function describeBassCharacter(detail: Phase1Result['bassDetail']): string | null {
  if (!detail) return null;

  const { type, averageDecayMs, fundamentalHz, grooveType } = detail;
  const decayStr = Math.round(averageDecayMs);
  const fundStr = Math.round(fundamentalHz);
  const grooveLabel = grooveType.replace(/-/g, ' ');

  let desc = `${titleCase(type)} bass with ${decayStr}ms decay at ${fundStr}Hz fundamental, ${grooveLabel} groove.`;

  if (type === 'punchy') {
    desc += ' Tight sub with fast compressor release.';
  } else if (type === 'rolling') {
    desc += ' Use a longer compressor release (200-400ms) to preserve the rolling motion.';
  } else if (type === 'sustained') {
    desc += ' Consider sidechain compression to keep space for the kick.';
  } else {
    desc += ' Balanced decay suits most mix approaches.';
  }

  return desc;
}

export function describeKick(detail: Phase1Result['kickDetail']): string | null {
  if (!detail) return null;

  const { kickCount, fundamentalHz, isDistorted } = detail;
  const fundStr = Math.round(fundamentalHz);

  let desc: string;
  if (isDistorted) {
    desc = `Distorted kick at ${fundStr}Hz fundamental, ${kickCount} hits. Add a Saturator before the compressor for controlled grit, or tame with a gentle high shelf cut above 8kHz.`;
  } else {
    desc = `Clean kick at ${fundStr}Hz fundamental, ${kickCount} hits. Standard four-on-floor pattern.`;
  }

  return desc;
}

export function describeSupersaw(detail: Phase1Result['supersawDetail']): string | null {
  if (!detail) return null;

  if (detail.isSupersaw) {
    const voices = detail.voiceCount;
    const detune = Math.round(detail.avgDetuneCents);
    return `~${voices} voice unison, ${detune} cents detune. In Wavetable: saw osc, ${voices} voices, ${detune}ct spread. Or Serum: 2 saw oscs, unison ${voices}v, detune ${detune}ct.`;
  }

  return 'No significant supersaw character. Lead sound uses fewer unison voices or different synthesis.';
}

export function describeVocal(detail: Phase1Result['vocalDetail']): string | null {
  if (!detail) return null;

  const confPct = Math.round(detail.confidence * 100);

  if (detail.hasVocals && detail.confidence > 0.7) {
    return `Prominent vocals detected (${confPct}% confidence). Consider vocal presence in arrangement -- may need EQ carving around 2-5kHz for clarity.`;
  }

  if (detail.hasVocals) {
    return `Possible vocal content (${confPct}% confidence). Could be vocal samples or pitched melodic content.`;
  }

  return 'No significant vocal content detected.';
}

export function describeGenre(detail: Phase1Result['genreDetail']): string | null {
  if (!detail) return null;

  const genreName = titleCase(detail.genre.replace(/-/g, ' '));
  const confPct = Math.round(detail.confidence * 100);
  const secondary = detail.secondaryGenre
    ? titleCase(detail.secondaryGenre.replace(/-/g, ' '))
    : null;

  const familyNotes: Record<string, string> = {
    techno: 'driving rhythm, heavy compression, minimal melodic elements',
    house: 'groovy feel, prominent bass, four-on-floor foundation',
    dnb: 'breakbeat patterns, fast tempo, heavy sub bass',
    trance: 'layered pads, progressive builds, euphoric melodic lines',
    ambient: 'textural focus, wide stereo field, reverb-heavy',
    dubstep: 'heavy bass design, half-time feel, aggressive sound design',
    breaks: 'breakbeat grooves, syncopated patterns, varied dynamics',
  };

  const familyNote = familyNotes[detail.genreFamily];
  let desc = `${genreName} (${confPct}% confidence, ${detail.genreFamily} family).`;

  if (secondary) {
    desc += ` Secondary: ${secondary}.`;
  }

  if (familyNote) {
    desc += ` Character: ${familyNote}.`;
  }

  return desc;
}

export function describeSynthesis(detail: SynthesisCharacter): string | null {
  if (!detail) return null;

  const inh = detail.inharmonicity;
  const oer = detail.oddToEvenRatio;
  const inhStr = inh.toFixed(3);
  const parts: string[] = [];

  if (inh > 0.25) {
    parts.push(`Wavetable/noise character (inharmonicity: ${inhStr}). Complex harmonic content suggests Wavetable or granular synthesis.`);
  } else if (inh >= 0.10) {
    parts.push(`FM/acid character (inharmonicity: ${inhStr}). Try Operator or FM8 with moderate feedback for similar texture.`);
  } else {
    parts.push(`Clean subtractive character (inharmonicity: ${inhStr}). Standard analog modeling -- Analog or Diva with minimal modulation.`);
  }

  if (oer > 1.5) {
    parts.push('Saw/square waveform dominance.');
  } else if (oer >= 0.8) {
    parts.push('Mixed harmonic content.');
  } else {
    parts.push('Sine/triangle waveform character -- smooth, rounded tone.');
  }

  return parts.join(' ');
}

function titleCase(str: string): string {
  return str.replace(/\b\w/g, c => c.toUpperCase());
}

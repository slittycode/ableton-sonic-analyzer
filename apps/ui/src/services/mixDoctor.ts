import type { Phase1Result, GenreProfile, SpectralTarget, PlrAdvice, MixAdvice, DynamicsAdvice, LoudnessAdvice, StereoAdvice, MixDoctorReport } from '../types';
export type { MixAdvice, MixDoctorReport } from '../types';

export function findProfileByIdOrFamily(
  profiles: GenreProfile[],
  genreId: string | null,
  genreFamily: string | null,
): string | null {
  if (genreId) {
    const exact = profiles.find(p => p.id === genreId);
    if (exact) return exact.id;
  }
  if (genreFamily) {
    const familyMatch = profiles.find(p =>
      p.id === genreFamily || p.name.toLowerCase().includes(genreFamily),
    );
    if (familyMatch) return familyMatch.id;
  }
  return null;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
}

type BandKey = keyof Phase1Result['spectralBalance'];
type ProfileBandKey = keyof GenreProfile['spectralTargets'];

const BAND_MAP: { key: BandKey; profileKey: ProfileBandKey; label: string }[] = [
  { key: 'subBass', profileKey: 'subBass', label: 'Sub Bass' },
  { key: 'lowBass', profileKey: 'lowBass', label: 'Low Bass' },
  { key: 'mids', profileKey: 'mids', label: 'Mids' },
  { key: 'upperMids', profileKey: 'upperMids', label: 'Upper Mids' },
  { key: 'highs', profileKey: 'highs', label: 'Highs' },
  { key: 'brilliance', profileKey: 'brilliance', label: 'Brilliance' },
];

function scoreBand(
  currentDb: number,
  target: SpectralTarget,
): number {
  const diffToOptimal = currentDb - target.optimalDb;
  const inRange = currentDb >= target.minDb && currentDb <= target.maxDb;
  let score: number;
  if (inRange) {
    const rangeHalf = (target.maxDb - target.minDb) / 2;
    const normalizedDiff = rangeHalf > 0 ? Math.abs(diffToOptimal) / rangeHalf : 0;
    score = 100 - normalizedDiff * 20;
  } else {
    const overshoot = currentDb > target.maxDb
      ? currentDb - target.maxDb
      : target.minDb - currentDb;
    score = 80 - overshoot * 5;
  }
  return Math.max(0, Math.min(100, score));
}

function bandAdviceMessage(
  label: string,
  currentDb: number,
  target: SpectralTarget,
  profileName: string,
): { issue: MixAdvice['issue']; message: string } {
  if (currentDb > target.maxDb) {
    const exceed = (currentDb - target.maxDb).toFixed(1);
    let message: string;
    switch (label) {
      case 'Sub Bass':
        message = `Muddy/overpowering subs. Highpass non-bass elements or turn down the sub layer by ~${exceed}dB.`;
        break;
      case 'Low Mids':
        message = `Boxy or muddy. Cut around 300-400Hz to clear space for kick/bass.`;
        break;
      case 'Highs':
        message = `Harsh and piercing. De-ess vocals or cut 6-8kHz.`;
        break;
      default:
        message = `Too prominent. Reduce by ~${exceed}dB to match commercial ${profileName} tracks.`;
    }
    return { issue: 'too-loud', message };
  }
  if (currentDb < target.minDb) {
    const deficit = (target.minDb - currentDb).toFixed(1);
    let message: string;
    switch (label) {
      case 'Sub Bass':
        message = `Weak low end. Add sub harmonics or boost <80Hz by ~${deficit}dB.`;
        break;
      case 'Mids':
        message = `Hollow mix. Boost fundamentals of synths/vocals to add body.`;
        break;
      case 'Brilliance':
        message = `Lacking 'air' and width. Apply a high shelf boost > 10kHz.`;
        break;
      default:
        message = `Lacking energy. Boost by ~${deficit}dB.`;
    }
    return { issue: 'too-quiet', message };
  }
  return { issue: 'optimal', message: 'Balanced.' };
}

export function generateMixReport(
  phase1: Phase1Result,
  profile: GenreProfile,
): MixDoctorReport {
  const spectral = phase1.spectralBalance;

  // Compute loudness offset to normalize for mastering level
  const offsets: number[] = [];
  for (const { key, profileKey } of BAND_MAP) {
    const target = profile.spectralTargets[profileKey];
    if (!target) continue;
    offsets.push(spectral[key] - target.optimalDb);
  }
  const loudnessOffset = offsets.length >= 3 ? median(offsets) : 0;

  // Evaluate each spectral band
  const advice: MixAdvice[] = [];
  let scoreAccumulator = 0;
  let bandsEvaluated = 0;

  for (const { key, profileKey, label } of BAND_MAP) {
    const target = profile.spectralTargets[profileKey];
    if (!target) continue;

    const currentDb = spectral[key] - loudnessOffset;
    const diffToOptimal = currentDb - target.optimalDb;
    const bandScore = scoreBand(currentDb, target);
    scoreAccumulator += bandScore;
    bandsEvaluated++;

    const { issue, message } = bandAdviceMessage(label, currentDb, target, profile.name);
    advice.push({ band: label, issue, message, diffDb: Math.round(diffToOptimal * 10) / 10 });
  }

  // Evaluate dynamics (crest factor)
  let dynamicsIssue: DynamicsAdvice['issue'] = 'optimal';
  let dynamicsMsg = 'Solid dynamic range. Fits the genre well.';
  let dynamicsPenalty = 0;
  const crest = phase1.crestFactor ?? 10;

  const [minCrest, maxCrest] = profile.targetCrestFactorRange;
  if (crest < minCrest) {
    dynamicsIssue = 'too-compressed';
    dynamicsMsg = `Crest factor ${crest.toFixed(1)} dB is below the ${minCrest}–${maxCrest} dB target for ${profile.name}. The mix is over-compressed — ease off the master limiter or reduce bus compression to recover transient punch.`;
    dynamicsPenalty = Math.min(15, (minCrest - crest) * 2.5);
  } else if (crest > maxCrest) {
    dynamicsIssue = 'too-dynamic';
    dynamicsMsg = `Crest factor ${crest.toFixed(1)} dB exceeds the ${minCrest}–${maxCrest} dB target for ${profile.name}. Wide dynamic range — add bus compression or saturation to glue the mix.`;
    dynamicsPenalty = Math.min(15, (crest - maxCrest) * 2.5);
  }

  // Evaluate PLR (Peak-to-Loudness Ratio)
  let plrAdvice: PlrAdvice | undefined;
  let plrPenalty = 0;
  const plr = phase1.truePeak - phase1.lufsIntegrated;
  const [minPlr, maxPlr] = profile.targetPlrRange;

  if (plr < minPlr) {
    plrAdvice = {
      issue: 'too-crushed',
      message: `PLR ${plr.toFixed(1)} dB is below ${minPlr}–${maxPlr} dB target for ${profile.name}. Peak headroom is too tight — reduce limiting to restore transient definition.`,
      actualPlr: Math.round(plr * 10) / 10,
    };
    plrPenalty = Math.min(10, (minPlr - plr) * 2);
  } else if (plr > maxPlr) {
    plrAdvice = {
      issue: 'too-open',
      message: `PLR ${plr.toFixed(1)} dB exceeds ${minPlr}–${maxPlr} dB target for ${profile.name}. Plenty of headroom — you could push the limiter harder if needed.`,
      actualPlr: Math.round(plr * 10) / 10,
    };
    plrPenalty = Math.min(10, (plr - maxPlr) * 2);
  } else {
    plrAdvice = {
      issue: 'optimal',
      message: `PLR ${plr.toFixed(1)} dB is within the ${minPlr}–${maxPlr} dB target. Good transient-to-loudness balance.`,
      actualPlr: Math.round(plr * 10) / 10,
    };
  }

  // Evaluate LUFS loudness
  let loudnessAdvice: LoudnessAdvice | undefined;
  let loudnessPenalty = 0;

  const lufs = phase1.lufsIntegrated;
  const tp = phase1.truePeak;
  const [minLufs, maxLufs] = profile.targetLufsRange;

  let loudnessIssue: LoudnessAdvice['issue'] = 'optimal';
  let loudnessMsg = `Loudness is on target at ${lufs.toFixed(1)} LUFS. Good for streaming platforms.`;

  if (lufs > maxLufs) {
    loudnessIssue = 'too-loud';
    loudnessMsg = `Too loud at ${lufs.toFixed(1)} LUFS (target: ${maxLufs} LUFS max for ${profile.name}). Streaming platforms will turn it down — reduce limiter gain.`;
    loudnessPenalty = Math.min(10, (lufs - maxLufs) * 2);
  } else if (lufs < minLufs) {
    loudnessIssue = 'too-quiet';
    loudnessMsg = `Quiet at ${lufs.toFixed(1)} LUFS (target: ${minLufs} LUFS min for ${profile.name}). Consider adding gain or a limiter to bring up overall level.`;
    loudnessPenalty = Math.min(10, (minLufs - lufs) * 2);
  }

  if (tp > -1) {
    loudnessMsg += ` True peak at ${tp.toFixed(1)} dBTP — risk of clipping on codec conversion. Target -1 dBTP ceiling.`;
    loudnessPenalty += 3;
  }

  loudnessAdvice = {
    issue: loudnessIssue,
    message: loudnessMsg,
    actualLufs: Math.round(lufs * 10) / 10,
    truePeak: Math.round(tp * 10) / 10,
  };

  // Evaluate stereo field
  let stereoAdvice: StereoAdvice | undefined;
  let stereoPenalty = 0;

  const corr = phase1.stereoCorrelation;
  const width = phase1.stereoWidth;
  const stereoRec = phase1.stereoDetail as Record<string, unknown> | null;
  const subBassMono = stereoRec?.subBassMono === true;
  const subBassCorr = typeof stereoRec?.subBassCorrelation === 'number' ? stereoRec.subBassCorrelation : null;
  const mono = subBassMono || (subBassCorr !== null && subBassCorr > 0.5);

  let stereoMsg = `Stereo field looks good — correlation ${corr.toFixed(2)}, width ${Math.round(width * 100)}%.`;

  if (!mono && subBassCorr !== null && subBassCorr < 0.3) {
    stereoMsg = `Phase cancellation detected in low frequencies. Bass will lose energy on mono playback (PA systems, phone speakers). Narrow your sub bass to mono.`;
    stereoPenalty = 5;
  } else if (corr < 0.2) {
    stereoMsg = `Very wide stereo image (correlation ${corr.toFixed(2)}). May sound thin when summed to mono. Consider narrowing bass and mid elements.`;
    stereoPenalty = 3;
  } else if (corr > 0.95 && width < 0.05) {
    stereoMsg = `Nearly mono — very narrow stereo image. Consider widening with stereo delay, chorus, or panning elements.`;
    stereoPenalty = 2;
  }

  stereoAdvice = { correlation: corr, width, monoCompatible: mono, message: stereoMsg };

  // Final score
  let overallScore = bandsEvaluated > 0 ? scoreAccumulator / bandsEvaluated : 0;
  overallScore -= dynamicsPenalty;
  overallScore -= plrPenalty;
  overallScore -= loudnessPenalty;
  overallScore -= stereoPenalty;
  overallScore = Math.round(Math.max(0, Math.min(100, overallScore)));

  return {
    genreName: profile.name,
    profileId: profile.id,
    advice,
    dynamicsAdvice: {
      issue: dynamicsIssue,
      message: dynamicsMsg,
      actualCrest: Math.round(crest * 10) / 10,
    },
    plrAdvice,
    loudnessAdvice,
    stereoAdvice,
    overallScore,
  };
}

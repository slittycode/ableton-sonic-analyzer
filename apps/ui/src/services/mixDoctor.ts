import { getAllGenreIds, getEnhancedProfile, mapLegacyToEnhanced, type GenreProfile } from "../data/genreProfiles";
import { type Phase1Result } from "../types";

export type MixIssue = "too-loud" | "too-quiet" | "optimal";
export type MixDynamicsIssue = "too-compressed" | "too-dynamic" | "optimal";

export interface MixAdvice {
  band: "Sub Bass" | "Low Bass" | "Low Mids" | "Mids" | "Upper Mids" | "Highs" | "Brilliance";
  issue: MixIssue;
  message: string;
  diffDb: number;
  measuredDb: number;
  normalizedDb: number;
  targetMinDb: number;
  targetMaxDb: number;
  targetOptimalDb: number;
}

export interface MixDoctorReport {
  genreId: string;
  genreName: string;
  targetProfile: GenreProfile;
  advice: MixAdvice[];
  loudnessOffset: number;
  dynamicsAdvice: {
    issue: MixDynamicsIssue;
    message: string;
    actualCrest: number | null;
    actualPlr: number | null;
  };
  loudnessAdvice: {
    issue: MixIssue;
    message: string;
    actualLufs: number | null;
    truePeak: number | null;
  };
  stereoAdvice: {
    correlation: number | null;
    width: number | null;
    monoCompatible: boolean | null;
    message: string;
  };
  overallScore: number;
}

const DEFAULT_GENRE_ID = "edm";
const KNOWN_GENRE_IDS = new Set(getAllGenreIds());

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function roundTo(value: number, decimals: number): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

function asFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

function normalizeGenreToken(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\/_]+/g, " ")
    .replace(/\s+/g, "-");
}

function resolveGenreCandidates(phase1: Phase1Result): string[] {
  const candidates: string[] = [];
  const fromGenre = phase1.genreDetail?.genre ?? "";
  const fromFamily = phase1.genreDetail?.genreFamily ?? "";

  if (fromGenre) {
    const normalized = normalizeGenreToken(fromGenre);
    candidates.push(normalized);
    mapLegacyToEnhanced(normalized).forEach((mapped) => candidates.push(mapped));
  }

  if (fromFamily) {
    const normalized = normalizeGenreToken(fromFamily);
    candidates.push(normalized);
    mapLegacyToEnhanced(normalized).forEach((mapped) => candidates.push(mapped));
  }

  candidates.push(DEFAULT_GENRE_ID);
  return candidates;
}

export function resolveMixDoctorGenreId(phase1: Phase1Result): string {
  for (const candidate of resolveGenreCandidates(phase1)) {
    if (KNOWN_GENRE_IDS.has(candidate)) return candidate;
  }
  return DEFAULT_GENRE_ID;
}

function estimatePlr(phase1: Phase1Result): number | null {
  const explicit = asFiniteNumber(phase1.plr);
  if (explicit !== null) return roundTo(explicit, 2);
  const lufs = asFiniteNumber(phase1.lufsIntegrated);
  const truePeak = asFiniteNumber(phase1.truePeak);
  if (lufs === null || truePeak === null) return null;
  return roundTo(truePeak - lufs, 2);
}

function estimateMonoCompatible(phase1: Phase1Result): boolean | null {
  if (phase1.monoCompatible === true || phase1.monoCompatible === false) {
    return phase1.monoCompatible;
  }
  const subBassMono = phase1.stereoDetail?.subBassMono;
  if (subBassMono === true || subBassMono === false) return subBassMono;
  return null;
}

export function generateMixDoctorReport(
  phase1: Phase1Result,
  requestedGenreId?: string | null,
): MixDoctorReport {
  const genreId = requestedGenreId && KNOWN_GENRE_IDS.has(requestedGenreId)
    ? requestedGenreId
    : resolveMixDoctorGenreId(phase1);
  const profile = getEnhancedProfile(genreId);

  const bandValues: MixAdvice["band"][] = [
    "Sub Bass",
    "Low Bass",
    "Low Mids",
    "Mids",
    "Upper Mids",
    "Highs",
    "Brilliance",
  ];
  const measuredByBand: Record<MixAdvice["band"], number> = {
    "Sub Bass": phase1.spectralBalance.subBass,
    "Low Bass": phase1.spectralBalance.lowBass,
    "Low Mids": phase1.spectralBalance.lowMids,
    Mids: phase1.spectralBalance.mids,
    "Upper Mids": phase1.spectralBalance.upperMids,
    Highs: phase1.spectralBalance.highs,
    Brilliance: phase1.spectralBalance.brilliance,
  };

  const offsets = bandValues.map((band) => {
    const target = profile.spectralTargets[band];
    return measuredByBand[band] - target.optimalDb;
  });
  const loudnessOffset = offsets.length >= 3 ? median(offsets) : 0;

  const advice: MixAdvice[] = [];
  let scoreAccumulator = 0;
  let bandsEvaluated = 0;

  for (const band of bandValues) {
    const target = profile.spectralTargets[band];
    const measuredDb = measuredByBand[band];
    const normalizedDb = measuredDb - loudnessOffset;
    const diffToOptimal = normalizedDb - target.optimalDb;
    const inRange = normalizedDb >= target.minDb && normalizedDb <= target.maxDb;

    let bandScore: number;
    if (inRange) {
      const halfRange = (target.maxDb - target.minDb) / 2;
      const normalizedDiff = halfRange > 0 ? Math.abs(diffToOptimal) / halfRange : 0;
      bandScore = 100 - normalizedDiff * 20;
    } else {
      const overshoot = normalizedDb > target.maxDb ? normalizedDb - target.maxDb : target.minDb - normalizedDb;
      bandScore = 80 - overshoot * 5;
    }
    bandScore = Math.max(0, Math.min(100, bandScore));
    scoreAccumulator += bandScore;
    bandsEvaluated += 1;

    let issue: MixIssue = "optimal";
    let message = "Balanced.";
    if (normalizedDb > target.maxDb) {
      issue = "too-loud";
      const exceed = roundTo(normalizedDb - target.maxDb, 1);
      switch (band) {
        case "Sub Bass":
          message = `Sub-bass is heavy by ~${exceed} dB. Pull down subs or high-pass non-bass layers.`;
          break;
        case "Low Mids":
          message = "Low mids are boxy. Cut around 250-450 Hz to open mix clarity.";
          break;
        case "Highs":
          message = "High band is harsh. Control 6-10 kHz with EQ or de-essing.";
          break;
        default:
          message = `${band} is over target by ~${exceed} dB.`;
          break;
      }
    } else if (normalizedDb < target.minDb) {
      issue = "too-quiet";
      const deficit = roundTo(target.minDb - normalizedDb, 1);
      switch (band) {
        case "Sub Bass":
          message = `Sub-bass is light by ~${deficit} dB. Add low-end weight under 80 Hz.`;
          break;
        case "Mids":
          message = "Midrange is recessed. Add body in 500 Hz–2 kHz.";
          break;
        case "Brilliance":
          message = "Top air is lacking. Consider a gentle shelf above 10 kHz.";
          break;
        default:
          message = `${band} is under target by ~${deficit} dB.`;
          break;
      }
    }

    advice.push({
      band,
      issue,
      message,
      diffDb: roundTo(diffToOptimal, 1),
      measuredDb: roundTo(measuredDb, 1),
      normalizedDb: roundTo(normalizedDb, 1),
      targetMinDb: target.minDb,
      targetMaxDb: target.maxDb,
      targetOptimalDb: target.optimalDb,
    });
  }

  const crest = asFiniteNumber(phase1.crestFactor);
  const plr = estimatePlr(phase1);
  let dynamicsIssue: MixDynamicsIssue = "optimal";
  let dynamicsMessage = "Dynamics are on target for the selected profile.";
  let dynamicsPenalty = 0;

  if (plr !== null) {
    const [minPlr, maxPlr] = profile.targetPlrRange;
    if (plr < minPlr) {
      dynamicsIssue = "too-compressed";
      dynamicsMessage = `PLR ${plr} dB is below ${minPlr}-${maxPlr} dB target. Ease limiter/bus compression to recover punch.`;
      dynamicsPenalty = Math.min(15, (minPlr - plr) * 2.5);
    } else if (plr > maxPlr) {
      dynamicsIssue = "too-dynamic";
      dynamicsMessage = `PLR ${plr} dB exceeds ${minPlr}-${maxPlr} dB target. Add gentle bus glue or saturation.`;
      dynamicsPenalty = Math.min(15, (plr - maxPlr) * 2.5);
    }
  } else if (crest !== null) {
    const [minCrest, maxCrest] = profile.targetCrestFactorRange;
    if (crest < minCrest) {
      dynamicsIssue = "too-compressed";
      dynamicsMessage = "Crest factor is low for profile target. Back off compression to restore transients.";
      dynamicsPenalty = Math.min(15, (minCrest - crest) * 2.5);
    } else if (crest > maxCrest) {
      dynamicsIssue = "too-dynamic";
      dynamicsMessage = "Crest factor is high for profile target. Add bus control for cohesion.";
      dynamicsPenalty = Math.min(15, (crest - maxCrest) * 2.5);
    }
  }

  const lufs = asFiniteNumber(phase1.lufsIntegrated);
  const truePeak = asFiniteNumber(phase1.truePeak);
  const [minLufs, maxLufs] = profile.targetLufsRange;
  let loudnessIssue: MixIssue = "optimal";
  let loudnessMessage = lufs !== null
    ? `Loudness is in profile range at ${lufs} LUFS.`
    : "Loudness unavailable.";
  let loudnessPenalty = 0;

  if (lufs !== null) {
    if (lufs > maxLufs) {
      loudnessIssue = "too-loud";
      loudnessMessage = `Track is louder than target (${lufs} LUFS vs max ${maxLufs}). Expect streaming turn-down.`;
      loudnessPenalty = Math.min(10, (lufs - maxLufs) * 2);
    } else if (lufs < minLufs) {
      loudnessIssue = "too-quiet";
      loudnessMessage = `Track is quieter than target (${lufs} LUFS vs min ${minLufs}).`;
      loudnessPenalty = Math.min(10, (minLufs - lufs) * 2);
    }
    if (truePeak !== null && truePeak > -1.0) {
      loudnessMessage += ` True peak ${truePeak} exceeds -1 dBTP safety ceiling.`;
      loudnessPenalty += 3;
    }
  }

  const correlation = asFiniteNumber(phase1.stereoCorrelation);
  const width = asFiniteNumber(phase1.stereoWidth);
  const monoCompatible = estimateMonoCompatible(phase1);
  let stereoMessage = "Stereo image appears stable.";
  let stereoPenalty = 0;

  if (monoCompatible === false) {
    stereoMessage = "Low-frequency mono compatibility issue detected. Collapse sub bass to mono.";
    stereoPenalty = 5;
  } else if (correlation !== null && correlation < 0.2) {
    stereoMessage = `Stereo correlation ${roundTo(correlation, 2)} is very wide. Check mono collapse.`;
    stereoPenalty = 3;
  } else if (correlation !== null && width !== null && correlation > 0.95 && width < 0.05) {
    stereoMessage = "Stereo image is nearly mono. Consider widening selected non-bass elements.";
    stereoPenalty = 2;
  }

  let overallScore = bandsEvaluated > 0 ? scoreAccumulator / bandsEvaluated : 0;
  overallScore -= dynamicsPenalty;
  overallScore -= loudnessPenalty;
  overallScore -= stereoPenalty;
  overallScore = Math.round(Math.max(0, Math.min(100, overallScore)));

  return {
    genreId,
    genreName: profile.name,
    targetProfile: profile,
    advice,
    loudnessOffset: roundTo(loudnessOffset, 2),
    dynamicsAdvice: {
      issue: dynamicsIssue,
      message: dynamicsMessage,
      actualCrest: crest !== null ? roundTo(crest, 1) : null,
      actualPlr: plr,
    },
    loudnessAdvice: {
      issue: loudnessIssue,
      message: loudnessMessage,
      actualLufs: lufs !== null ? roundTo(lufs, 1) : null,
      truePeak: truePeak !== null ? roundTo(truePeak, 1) : null,
    },
    stereoAdvice: {
      correlation: correlation !== null ? roundTo(correlation, 2) : null,
      width: width !== null ? roundTo(width, 2) : null,
      monoCompatible,
      message: stereoMessage,
    },
    overallScore,
  };
}

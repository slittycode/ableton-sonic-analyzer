import type { FundamentalsQualityDomain, Phase1Result } from '../types';
import { getConfidenceBand, type ConfidenceBand } from './sessionMusician/confidenceBand';

// Plain-English reconstruction brief built purely from Phase 1 measurements
// (plus the local-only fundamentalsQuality trust layer). Deterministic — no
// AI involved — so it renders even when Phase 2 is disabled or fails. Every
// line cites the Phase 1 field(s) it was derived from (PURPOSE.md invariant
// #2), and a line whose driving measurement is absent is omitted rather than
// guessed (invariant #4). Fast-mode payloads null out rhythmDetail /
// spectralBalance / stereoDetail / spectralDetail despite the optimistic TS
// types, so every read is guarded.

export type BriefDomain =
  | 'key'
  | 'tempo'
  | 'meter'
  | 'groove'
  | 'loudness'
  | 'stereo'
  | 'spectral'
  | 'dynamics';

export interface BriefLine {
  domain: BriefDomain;
  label: string;
  /** Deterministic plain-English sentence, hedged when confidence is weak. */
  text: string;
  /** 0-1 scalar when the measurement carries one; null for pure DSP scalars. */
  confidence: number | null;
  band: ConfidenceBand | null;
  /** Phase 1 citation paths — always at least one. */
  phase1Fields: string[];
}

const APPROXIMATE_KEY_CONFIDENCE = 0.6; // mirrors AnalysisResults keyIsApproximate

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function fmt(value: number, digits = 1): string {
  return value.toFixed(digits);
}

function domainOf(phase1: Phase1Result, key: string): FundamentalsQualityDomain | null {
  return phase1.fundamentalsQuality?.domains?.[key] ?? null;
}

/** Append the fundamentals domain's own plainEnglish hedge when it is not authoritative. */
function withDomainHedge(text: string, domain: FundamentalsQualityDomain | null): string {
  if (!domain || domain.status === 'authoritative') return text;
  if (!domain.plainEnglish) return text;
  return `${text} ${domain.plainEnglish}`;
}

function line(
  domain: BriefDomain,
  label: string,
  text: string,
  confidence: number | null,
  phase1Fields: string[],
): BriefLine {
  return {
    domain,
    label,
    text,
    confidence,
    band: confidence !== null ? getConfidenceBand(confidence) : null,
    phase1Fields,
  };
}

function keyLine(phase1: Phase1Result): BriefLine | null {
  if (typeof phase1.key !== 'string' || phase1.key.length === 0) return null;
  const quality = domainOf(phase1, 'key');
  const confidence = quality?.confidence ?? (finite(phase1.keyConfidence) ? phase1.keyConfidence : null);
  let text = `The track reads as ${phase1.key}.`;
  if (finite(phase1.keyConfidence) && phase1.keyConfidence <= APPROXIMATE_KEY_CONFIDENCE) {
    text += ' Treat the key as approximate — confirm by ear against a sustained pad before committing.';
  }
  return line('key', 'Key', withDomainHedge(text, quality), confidence, ['key', 'keyConfidence']);
}

function tempoLine(phase1: Phase1Result): BriefLine | null {
  if (!finite(phase1.bpm)) return null;
  const quality = domainOf(phase1, 'tempo');
  const confidence = quality?.confidence ?? (finite(phase1.bpmConfidence) ? phase1.bpmConfidence : null);
  const text = `Set your Live set to ${fmt(phase1.bpm)} BPM.`;
  return line('tempo', 'Tempo', withDomainHedge(text, quality), confidence, ['bpm', 'bpmConfidence']);
}

function meterLine(phase1: Phase1Result): BriefLine | null {
  if (typeof phase1.timeSignature !== 'string' || phase1.timeSignature.length === 0) return null;
  const quality = domainOf(phase1, 'meter');
  const assumed = phase1.timeSignatureSource === 'assumed_four_four';
  const text = assumed
    ? `Meter was not measured — ${phase1.timeSignature} is assumed (safe for most electronic tracks).`
    : `Measured meter: ${phase1.timeSignature}.`;
  // The routine "assumed 4/4" hedge already says everything the meter domain's
  // ambiguous plainEnglish would; only layer the domain text on failure.
  const hedged = quality?.status === 'failed' ? withDomainHedge(text, quality) : text;
  return line('meter', 'Meter', hedged, quality?.confidence ?? null, ['timeSignature']);
}

function grooveLine(phase1: Phase1Result): BriefLine | null {
  const rhythm = phase1.rhythmDetail;
  if (!rhythm || !finite(rhythm.onsetRate)) return null;

  const fields = ['rhythmDetail.onsetRate'];
  const parts: string[] = [`About ${fmt(rhythm.onsetRate)} rhythmic events per second.`];

  // Prefer the measured swing percentage (Groove-Pool-ready) when available;
  // fall back to the older loudness-interval swing proxy otherwise.
  const swing = rhythm.swingDetail;
  if (swing && swing.direction === 'swung' && finite(swing.swingPercent)) {
    parts.push(`The groove swings at about ${Math.round(swing.swingPercent)}% — set the Groove Pool swing to match.`);
    fields.push('rhythmDetail.swingDetail.swingPercent');
  } else if (swing && swing.direction === 'straight') {
    parts.push('The groove sits on a straight, quantized grid.');
    fields.push('rhythmDetail.swingDetail.swingPercent');
  } else {
    const kickSwing = phase1.grooveDetail?.kickSwing;
    const hihatSwing = phase1.grooveDetail?.hihatSwing;
    if (finite(kickSwing) && finite(hihatSwing)) {
      const maxSwing = Math.max(kickSwing, hihatSwing);
      const feel = maxSwing > 0.3 ? 'a noticeably swung feel — reach for the Groove Pool' : maxSwing > 0.1 ? 'a light swing' : 'a straight, quantized grid';
      parts.push(`The drums have ${feel}.`);
      fields.push('grooveDetail.kickSwing', 'grooveDetail.hihatSwing');
    }
  }

  const sidechain = phase1.sidechainDetail;
  if (sidechain && sidechain.pumpingRate !== null && finite(sidechain.pumpingConfidence) && sidechain.pumpingConfidence >= 0.5) {
    parts.push(`Sidechain-style pumping detected at a ${sidechain.pumpingRate}-note rate.`);
    fields.push('sidechainDetail.pumpingRate', 'sidechainDetail.pumpingConfidence');
  }

  const quality = domainOf(phase1, 'beatGrid');
  return line('groove', 'Groove', withDomainHedge(parts.join(' '), quality), quality?.confidence ?? null, fields);
}

function loudnessLine(phase1: Phase1Result): BriefLine | null {
  if (!finite(phase1.lufsIntegrated)) return null;
  const fields = ['lufsIntegrated'];
  const lufs = phase1.lufsIntegrated;
  const character = lufs > -8 ? 'a loud, club-style master' : lufs <= -14 ? 'a conservative, streaming-friendly level' : 'a moderately loud master';
  const parts = [`Integrated loudness is ${fmt(lufs)} LUFS — ${character}.`];
  if (finite(phase1.lufsRange)) {
    parts.push(`Loudness range is ${fmt(phase1.lufsRange)} LU.`);
    fields.push('lufsRange');
  }
  if (finite(phase1.truePeak)) {
    parts.push(`True peak ${fmt(phase1.truePeak)} dBTP${phase1.truePeak > 0 ? ' — inter-sample overs; pull the ceiling down' : ''}.`);
    fields.push('truePeak');
  }
  return line('loudness', 'Loudness', parts.join(' '), null, fields);
}

function stereoLine(phase1: Phase1Result): BriefLine | null {
  if (!finite(phase1.stereoWidth) || !finite(phase1.stereoCorrelation)) return null;
  const fields = ['stereoWidth', 'stereoCorrelation'];
  const width = phase1.stereoWidth;
  const widthWord = width > 0.5 ? 'wide' : width < 0.2 ? 'narrow, mostly mono' : 'moderately wide';
  const parts = [`The stereo image is ${widthWord} (width ${fmt(width, 2)}).`];
  if (phase1.stereoCorrelation < 0) {
    parts.push(`L/R correlation is ${fmt(phase1.stereoCorrelation, 2)} — check mono compatibility.`);
  }
  if (phase1.stereoDetail?.subBassMono === true) {
    parts.push('Sub-bass is mono — good for club playback; keep yours mono below ~120 Hz.');
    fields.push('stereoDetail.subBassMono');
  }
  return line('stereo', 'Stereo', parts.join(' '), null, fields);
}

const BAND_LABELS: Array<[key: keyof Phase1Result['spectralBalance'], label: string]> = [
  ['subBass', 'sub bass'],
  ['lowBass', 'low bass'],
  ['lowMids', 'low mids'],
  ['mids', 'mids'],
  ['upperMids', 'upper mids'],
  ['highs', 'highs'],
  ['brilliance', 'brilliance'],
];

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function spectralLine(phase1: Phase1Result): BriefLine | null {
  const balance = phase1.spectralBalance;
  if (!balance) return null;
  const entries = BAND_LABELS.filter(([key]) => finite(balance[key]));
  if (entries.length === 0) return null;

  const mid = median(entries.map(([key]) => balance[key]));
  const emphasized = entries.filter(([key]) => balance[key] - mid >= 3);
  const recessed = entries.filter(([key]) => balance[key] - mid <= -3);

  const parts: string[] = [];
  const fields: string[] = [];
  if (emphasized.length > 0) {
    parts.push(`Energy is concentrated in the ${emphasized.map(([, label]) => label).join(', ')}.`);
    fields.push(...emphasized.map(([key]) => `spectralBalance.${key}`));
  }
  if (recessed.length > 0) {
    parts.push(`The ${recessed.map(([, label]) => label).join(', ')} ${recessed.length === 1 ? 'sits' : 'sit'} well below the rest.`);
    fields.push(...recessed.map(([key]) => `spectralBalance.${key}`));
  }
  if (parts.length === 0) {
    parts.push('Spectral energy is fairly even across the bands — no single range dominates.');
    fields.push('spectralBalance.subBass', 'spectralBalance.brilliance');
  }
  return line('spectral', 'Spectrum', parts.join(' '), null, fields);
}

function dynamicsLine(phase1: Phase1Result): BriefLine | null {
  // Mirror mixDoctor's precedence: PLR when measured, crest factor as fallback.
  if (finite(phase1.plr)) {
    const plr = phase1.plr;
    const word = plr < 6 ? 'heavily limited — expect a dense, compressed sound' : plr <= 10 ? 'controlled — typical of a finished electronic master' : 'dynamic — transients are left to breathe';
    return line('dynamics', 'Dynamics', `Peak-to-loudness ratio is ${fmt(plr)} dB: ${word}.`, null, ['plr']);
  }
  if (finite(phase1.crestFactor)) {
    const crest = phase1.crestFactor;
    const word = crest < 6 ? 'heavily compressed' : crest < 12 ? 'moderately compressed' : 'wide open';
    return line('dynamics', 'Dynamics', `Crest factor is ${fmt(crest)} dB — the dynamics are ${word}.`, null, ['crestFactor']);
  }
  return null;
}

export function buildReconstructionBrief(phase1: Phase1Result): BriefLine[] {
  return [
    keyLine(phase1),
    tempoLine(phase1),
    meterLine(phase1),
    grooveLine(phase1),
    loudnessLine(phase1),
    stereoLine(phase1),
    spectralLine(phase1),
    dynamicsLine(phase1),
  ].filter((entry): entry is BriefLine => entry !== null);
}

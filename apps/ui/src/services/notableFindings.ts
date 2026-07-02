import type { Phase1Result } from '../types';
import { loudnessDefectsDemandingAction, type LoudnessDefect } from './loudnessGuardrails';
import { generateMixDoctorReport } from './mixDoctor';

export type FindingSeverity = 'critical' | 'warning' | 'info';

export interface NotableFinding {
  id: string;
  severity: FindingSeverity;
  domain: string;
  title: string;
  detail: string;
  phase1Field?: string;
}

const SEVERITY_ORDER: Record<FindingSeverity, number> = { critical: 0, warning: 1, info: 2 };

// loudnessGuardrails' LoudnessDefect carries no human text, so generate it here.
function loudnessDefectFinding(defect: LoudnessDefect): NotableFinding {
  if (defect.kind === 'CLIPPING') {
    return {
      id: 'loudness.clipping',
      severity: 'critical',
      domain: 'Loudness',
      title: 'Master is clipping',
      detail: `${defect.value} clipped sample${defect.value === 1 ? '' : 's'} detected — pull the master gain down or add a limiter.`,
      phase1Field: defect.field,
    };
  }
  return {
    id: 'loudness.truePeakOver',
    severity: 'critical',
    domain: 'Loudness',
    title: 'Inter-sample peak over 0 dBTP',
    detail: `True peak is ${defect.value} dBTP — leave ~1 dB of true-peak headroom.`,
    phase1Field: defect.field,
  };
}

// fundamentalsQuality: reuse the domain's plainEnglish text.
// Meter is intentionally excluded from the ambiguous->warning rule: its routine
// "assumed 4/4" reading is ambiguous on nearly every track, so flagging it would
// be constant noise. Meter still surfaces when it FAILED to measure.
const FUNDAMENTAL_DOMAIN_META: Record<string, { label: string; field: string }> = {
  tempo: { label: 'Tempo', field: 'bpm' },
  beatGrid: { label: 'Beat grid', field: 'rhythmDetail.beatGrid' },
  downbeats: { label: 'Downbeats', field: 'rhythmDetail.downbeats' },
  meter: { label: 'Meter', field: 'timeSignature' },
  key: { label: 'Key', field: 'key' },
  chords: { label: 'Chords', field: 'chordDetail' },
  percussion: { label: 'Percussion', field: 'kickDetail' },
  transcription: { label: 'Notes', field: 'transcriptionDetail' },
};

function fundamentalsFindings(phase1: Phase1Result): NotableFinding[] {
  const domains = phase1.fundamentalsQuality?.domains;
  if (!domains) return [];
  const out: NotableFinding[] = [];
  for (const [key, meta] of Object.entries(FUNDAMENTAL_DOMAIN_META)) {
    const domain = domains[key];
    if (!domain) continue;
    if (domain.status === 'failed') {
      out.push({
        id: `fundamentals.${key}.failed`,
        severity: 'critical',
        domain: meta.label,
        title: `${meta.label} could not be measured`,
        detail: domain.plainEnglish,
        phase1Field: meta.field,
      });
    } else if (domain.status === 'ambiguous' && key !== 'meter') {
      out.push({
        id: `fundamentals.${key}.ambiguous`,
        severity: 'warning',
        domain: meta.label,
        title: `${meta.label} is uncertain`,
        detail: domain.plainEnglish,
        phase1Field: meta.field,
      });
    }
  }
  return out;
}

const BAND_TO_KEY: Record<string, string> = {
  'Sub Bass': 'subBass',
  'Low Bass': 'lowBass',
  'Low Mids': 'lowMids',
  Mids: 'mids',
  'Upper Mids': 'upperMids',
  Highs: 'highs',
  Brilliance: 'brilliance',
};

function mixDoctorFindings(phase1: Phase1Result): NotableFinding[] {
  // generateMixDoctorReport dereferences phase1.spectralBalance.* directly, so
  // it throws on a fast-mode payload where spectralBalance is null. Skip it.
  if (!phase1.spectralBalance) return [];

  const report = generateMixDoctorReport(phase1);
  const out: NotableFinding[] = [];

  if (report.loudnessAdvice.issue !== 'optimal') {
    out.push({
      id: 'mix.loudness',
      severity: 'warning',
      domain: 'Loudness',
      title: report.loudnessAdvice.issue === 'too-loud'
        ? 'Master is louder than the genre target'
        : 'Master is quieter than the genre target',
      detail: report.loudnessAdvice.message,
      phase1Field: 'lufsIntegrated',
    });
  }

  if (report.dynamicsAdvice.issue !== 'optimal') {
    out.push({
      id: 'mix.dynamics',
      severity: 'warning',
      domain: 'Dynamics',
      title: report.dynamicsAdvice.issue === 'too-compressed'
        ? 'Dynamics are heavily compressed'
        : 'Dynamics are unusually wide',
      detail: report.dynamicsAdvice.message,
      phase1Field: typeof phase1.plr === 'number' ? 'plr' : 'crestFactor',
    });
  }

  if (report.stereoAdvice.monoCompatible === false) {
    out.push({
      id: 'mix.stereo.mono',
      severity: 'warning',
      domain: 'Stereo',
      title: 'Sub-bass may not be mono-compatible',
      detail: report.stereoAdvice.message,
      // Mirror mixDoctor.estimateMonoCompatible's precedence for the citation.
      phase1Field: phase1.monoCompatible === true || phase1.monoCompatible === false
        ? 'monoCompatible'
        : 'stereoDetail.subBassMono',
    });
  }

  for (const band of report.advice) {
    if (band.issue === 'optimal') continue;
    const key = BAND_TO_KEY[band.band] ?? band.band;
    out.push({
      id: `mix.band.${key}`,
      severity: 'info',
      domain: 'Balance',
      title: `${band.band} ${band.issue === 'too-loud' ? 'over' : 'under'} target`,
      detail: band.message,
      phase1Field: `spectralBalance.${key}`,
    });
  }

  return out;
}

function dedup(findings: NotableFinding[]): NotableFinding[] {
  const hasLoudnessCritical = findings.some((f) => f.domain === 'Loudness' && f.severity === 'critical');
  return findings.filter((f) => !(f.id === 'mix.loudness' && hasLoudnessCritical));
}

export function collectNotableFindings(phase1: Phase1Result): NotableFinding[] {
  const findings: NotableFinding[] = [
    ...loudnessDefectsDemandingAction(phase1).map(loudnessDefectFinding),
    ...fundamentalsFindings(phase1),
    ...mixDoctorFindings(phase1),
  ];
  // Array.prototype.sort is stable, so equal-severity findings keep insertion
  // order (loudness, then fundamentals, then mixDoctor).
  return dedup(findings).sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
}

import type { Phase1Result } from '../types';
import { loudnessDefectsDemandingAction, type LoudnessDefect } from './loudnessGuardrails';

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

export function collectNotableFindings(phase1: Phase1Result): NotableFinding[] {
  const findings: NotableFinding[] = [
    ...loudnessDefectsDemandingAction(phase1).map(loudnessDefectFinding),
    ...fundamentalsFindings(phase1),
  ];
  // Array.prototype.sort is stable, so equal-severity findings keep insertion
  // order (loudness, then fundamentals, then — added in Task 2 — mixDoctor).
  return findings.sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
}

/**
 * Multi-model decision-gate comparator.
 *
 * Loads /tmp/decision_gate_<model>.json for each Gemini variant we tested
 * against demo.mp3, runs the validator on each, and emits a side-by-side
 * markdown comparison so we can see whether prompt fixes are universal or
 * the weakest model is the bottleneck.
 *
 * Skips when no snapshots are present, so the suite stays clean elsewhere.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import path from 'node:path';
import { validatePhase2Consistency } from '../src/services/phase2Validator';
import type { Phase1Result, Phase2Result } from '../src/types';

const MODELS = [
  'gemini-2.5-flash',
  'gemini-3-flash-preview',
  'gemini-3-pro-preview',
  'gemini-3.1-flash-preview',
  'gemini-3.1-pro-preview',
];

const REPORTS_DIR = path.resolve(__dirname, '../../backend/.runtime/reports');

interface ModelGate {
  model: string;
  snapshotPath: string;
  ok: boolean;
  reason?: string;
  bpm?: number | string;
  key?: string | null;
  recCounts?: { mmc: number; ar: number; ws: number; total: number };
  violationsByType?: Record<string, number>;
  topMissingCitation?: string[];
  topNewFieldUncited?: string[];
  topSalvaged?: string[];
  gateCriteria?: Record<string, boolean>;
  gatePassed?: boolean;
  newFieldsCitedAt?: string[];
  invalidWorkflowStage?: boolean;
  interpretationStatus?: string;
  errorCode?: string;
}

function gateFor(model: string): ModelGate {
  const snapshotPath = `/tmp/decision_gate_${model}.json`;
  if (!existsSync(snapshotPath)) {
    return { model, snapshotPath, ok: false, reason: 'snapshot not present' };
  }
  let snap: any;
  try {
    snap = JSON.parse(readFileSync(snapshotPath, 'utf8'));
  } catch (exc) {
    return { model, snapshotPath, ok: false, reason: `parse error: ${exc}` };
  }
  const interpretation = snap?.stages?.interpretation ?? {};
  const interpretationStatus = interpretation.status;
  const measurement = snap?.stages?.measurement?.result;
  const phase1 = (measurement?.phase1 ?? measurement) as Phase1Result | undefined;
  const phase2 = (interpretation?.result ?? interpretation?.attemptsSummary?.[0]?.result) as Phase2Result | undefined;
  if (!phase1) {
    return { model, snapshotPath, ok: false, reason: 'no phase1', interpretationStatus };
  }
  if (!phase2) {
    const errCode = interpretation?.error?.code;
    return {
      model, snapshotPath, ok: false,
      reason: errCode || 'no phase2 result',
      interpretationStatus, errorCode: errCode,
      bpm: phase1?.bpm, key: phase1?.key,
    };
  }
  const validationWarnings = interpretation?.diagnostics?.validationWarnings ?? [];
  const report = validatePhase2Consistency(phase1, phase2, { warnings: validationWarnings });
  const byType: Record<string, number> = {};
  const samplesByType: Record<string, string[]> = {};
  for (const v of report.violations) {
    byType[v.type] = (byType[v.type] || 0) + 1;
    samplesByType[v.type] = samplesByType[v.type] || [];
    if (samplesByType[v.type].length < 3) {
      samplesByType[v.type].push(`${v.field}: ${v.message.slice(0, 110)}…`);
    }
  }
  const mmc = (phase2 as any)?.mixAndMasterChain || [];
  const ar = (phase2 as any)?.abletonRecommendations || [];
  const ws = (phase2 as any)?.secretSauce?.workflowSteps || [];
  const recCounts = { mmc: mmc.length, ar: ar.length, ws: ws.length, total: mmc.length + ar.length + ws.length };

  const allRecs = [...mmc, ...ar, ...ws];
  const citedPaths = new Set<string>();
  for (const rec of allRecs) {
    for (const f of (rec?.phase1Fields || [])) citedPaths.add(String(f));
  }
  const NEW_FIELDS = [
    'lufsCurve',
    'lufsCurve.shortTerm',
    'lufsCurve.momentary',
    'spectralBalanceTimeSeries',
    'rhythmDetail.tempoCurve',
    'stereoDetail.correlationCurve',
    'arrangementDetail.noveltyCurve',
  ];
  const newFieldsCitedAt = NEW_FIELDS.filter((p) => citedPaths.has(p) || Array.from(citedPaths).some((c) => p.startsWith(`${c}.`)));

  const invalidWorkflowStage = validationWarnings.some(
    (w: any) => typeof w?.dropReason === 'string' && w.dropReason.toLowerCase().includes('workflowstage'),
  );

  // Gate #4 is permissive: PASS as long as Gemini cites at least one new
  // field OR no new field has useful density. We fail only when >=1 dense
  // new fields exist AND zero are cited — the "Gemini ignored the depth
  // family" case.
  const usefulUncited = byType['NEW_FIELD_UNCITED'] ?? 0;
  const totalNewCited = newFieldsCitedAt.length;
  const newFieldsOK = usefulUncited === 0 || totalNewCited >= 1;

  const gateCriteria = {
    '1. zero RECOMMENDATION_SALVAGED': (byType['RECOMMENDATION_SALVAGED'] ?? 0) === 0,
    '2. zero MISSING_CITATION': (byType['MISSING_CITATION'] ?? 0) === 0,
    '3. citation diversity OK': (byType['TRIVIAL_CITATIONS'] ?? 0) === 0,
    '4. at least one new Phase 1.A field cited (or none meaningful)': newFieldsOK,
    '5. low-confidence text hedged': (byType['LOW_CONFIDENCE_NOT_HEDGED'] ?? 0) === 0,
  };
  const gatePassed = Object.values(gateCriteria).every(Boolean);

  return {
    model, snapshotPath, ok: true,
    bpm: phase1?.bpm, key: phase1?.key,
    recCounts,
    violationsByType: byType,
    topMissingCitation: samplesByType['MISSING_CITATION'] ?? [],
    topNewFieldUncited: samplesByType['NEW_FIELD_UNCITED'] ?? [],
    topSalvaged: samplesByType['RECOMMENDATION_SALVAGED'] ?? [],
    gateCriteria, gatePassed,
    newFieldsCitedAt,
    invalidWorkflowStage,
    interpretationStatus,
  };
}

describe('decision-gate (multi-model)', () => {
  const anySnapshot = MODELS.some((m) => existsSync(`/tmp/decision_gate_${m}.json`));
  if (!anySnapshot) {
    it.skip('skipped — no /tmp/decision_gate_<model>.json snapshots present', () => { /* noop */ });
    return;
  }

  it('compares validator output across Gemini variants and writes a markdown table', () => {
    const gates = MODELS.map(gateFor);
    const ok = gates.filter((g) => g.ok);
    expect(ok.length).toBeGreaterThan(0);

    const lines: string[] = [];
    lines.push(`# Phase 1.A Decision Gate — Multi-model comparison`);
    lines.push(`Generated: ${new Date().toISOString()}`);
    lines.push('');
    lines.push(`Track: \`apps/ui/public/demo.mp3\` (1.2s synthetic demo). Profile: \`producer_summary\`. No stems, no transcription.`);
    lines.push('');
    lines.push('## Verdict summary');
    lines.push('');
    lines.push('| Model | Status | Total recs | Errors | Warnings | Salvaged | Missing cite | New-fld uncited | New-fld cited | Gate |');
    lines.push('|---|---|---|---|---|---|---|---|---|---|');
    for (const g of gates) {
      if (!g.ok) {
        lines.push(`| ${g.model} | ${g.reason ?? 'n/a'} | — | — | — | — | — | — | — | ✗ |`);
        continue;
      }
      const v = g.violationsByType!;
      const total = g.recCounts!.total;
      const newCited = g.newFieldsCitedAt!.length;
      const verdict = g.gatePassed ? '✓ PASS' : '✗ FAIL';
      lines.push(
        `| ${g.model} | ${g.interpretationStatus} | ${total} (mmc=${g.recCounts!.mmc} ar=${g.recCounts!.ar} ws=${g.recCounts!.ws}) | ${v['MISSING_CITATION']??0 + (v['LOW_CONFIDENCE_NOT_HEDGED']??0) + (v['RECOMMENDATION_SALVAGED']??0)} | ${Object.entries(v).filter(([k])=>!['MISSING_CITATION','LOW_CONFIDENCE_NOT_HEDGED','RECOMMENDATION_SALVAGED'].includes(k)).reduce((s,[,n])=>s+n,0)} | ${v['RECOMMENDATION_SALVAGED']??0} | ${v['MISSING_CITATION']??0} | ${v['NEW_FIELD_UNCITED']??0}/7 | ${newCited}/7 (${g.newFieldsCitedAt!.join(', ')||'none'}) | ${verdict} |`,
      );
    }
    lines.push('');
    lines.push('## Failure patterns by model');
    lines.push('');
    for (const g of gates) {
      lines.push(`### ${g.model}`);
      if (!g.ok) {
        lines.push(`- skipped: ${g.reason ?? 'n/a'}${g.errorCode ? ` (\`${g.errorCode}\`)` : ''}`);
        lines.push('');
        continue;
      }
      lines.push(`- gate: **${g.gatePassed ? 'PASS' : 'FAIL'}**`);
      lines.push(`- recommendation counts: \`mmc=${g.recCounts!.mmc} ar=${g.recCounts!.ar} ws=${g.recCounts!.ws}\` (total ${g.recCounts!.total})`);
      lines.push(`- invalid workflowStage hallucinated: ${g.invalidWorkflowStage ? 'YES' : 'no'}`);
      lines.push(`- new Phase 1.A fields cited (out of 7 paths): \`${g.newFieldsCitedAt!.join(', ') || 'NONE'}\``);
      if (g.topSalvaged!.length) {
        lines.push(`- RECOMMENDATION_SALVAGED examples:`);
        for (const s of g.topSalvaged!) lines.push(`  - ${s}`);
      }
      if (g.topMissingCitation!.length) {
        lines.push(`- MISSING_CITATION examples (invented paths):`);
        for (const s of g.topMissingCitation!) lines.push(`  - ${s}`);
      }
      lines.push('');
    }

    lines.push('## Cross-model failure pattern table');
    lines.push('');
    const ALL_TYPES = ['RECOMMENDATION_SALVAGED','MISSING_CITATION','NEW_FIELD_UNCITED','TRIVIAL_CITATIONS','LOW_CONFIDENCE_NOT_HEDGED','GENRE_IGNORES_DSP','BOUNDS_VIOLATION','NUMERIC_OVERRIDE'];
    lines.push('| Violation type | ' + ok.map((g) => g.model.replace('gemini-', '').replace('-preview','')).join(' | ') + ' |');
    lines.push('|---|' + ok.map(() => '---').join('|') + '|');
    for (const t of ALL_TYPES) {
      const row = ok.map((g) => g.violationsByType?.[t] ?? 0).join(' | ');
      lines.push(`| ${t} | ${row} |`);
    }
    lines.push('');

    lines.push('## Prompt-change implications');
    lines.push('');
    const issues = [];
    if (ok.some((g) => g.invalidWorkflowStage)) issues.push('- **workflowStage hallucination** appears on at least one model — prompt enum reminder is needed regardless of model.');
    if (ok.every((g) => (g.violationsByType?.['NEW_FIELD_UNCITED'] ?? 0) > 0)) issues.push('- **Every model ignored the new Phase 1.A fields** — they need to be enumerated in the prompt; this is not a model-strength issue.');
    if (ok.every((g) => (g.violationsByType?.['MISSING_CITATION'] ?? 0) > 0)) issues.push('- **Every model invented at least one citation path** — the prompt rule about verifying paths against the payload is not strong enough; needs a "before emitting, the path must resolve" gate.');
    else if (ok.some((g) => (g.violationsByType?.['MISSING_CITATION'] ?? 0) > 0)) issues.push('- **Some models invented citation paths but not all** — model-dependent; the better-model option is to require it via prompt; the weaker-model option is to also add server-side citation validation against the payload schema.');
    if (ok.every((g) => (g.violationsByType?.['RECOMMENDATION_SALVAGED'] ?? 0) > 0)) issues.push('- **Every model triggered salvage** — backend hardening + prompt enum reminders together.');
    else if (ok.some((g) => (g.violationsByType?.['RECOMMENDATION_SALVAGED'] ?? 0) > 0)) issues.push('- **Some models triggered salvage but not all** — primarily a prompt issue; a stronger model would obviate.');
    if (issues.length === 0) issues.push('- No universal failures across models; prompt may be acceptable as-is.');
    for (const i of issues) lines.push(i);
    lines.push('');

    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    mkdirSync(REPORTS_DIR, { recursive: true });
    const out = path.join(REPORTS_DIR, `decision_gate_multi_${stamp}.md`);
    writeFileSync(out, lines.join('\n'), 'utf8');
    console.log(`multi-model report written to ${out}`);
    for (const g of gates) {
      console.log(`  ${g.model}: ${g.ok ? (g.gatePassed ? 'PASS' : 'FAIL') : g.reason}`);
    }
    expect(existsSync(out)).toBe(true);
  });
});

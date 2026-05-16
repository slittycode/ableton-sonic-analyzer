/**
 * Real-track multi-model decision-gate comparator — NO-STEM path.
 *
 * v3.1: shares the PHASE1_NEW_FIELD_PATHS constant and the bidirectional +
 * wildcard `pathCoversTracked` matcher with phase2Validator.ts. Splits report
 * metrics into Phase 1.A vs Phase 1.C/D buckets, matching the stems-mode
 * comparator's shape so v3.1 numbers are directly comparable across modes.
 *
 * Reads /tmp/decision_gate_real_<model>.json snapshots produced by
 * /tmp/decision_gate_real.py (which uses `pitch_note_mode="off"` so
 * `stemAnalysis` is absent — exercising the no-stem path the prompt's STEM
 * AVAILABILITY GATE governs).
 */
import { describe, it, expect } from 'vitest';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import path from 'node:path';
import {
  validatePhase2Consistency,
  pathCoversTracked,
  PHASE1_NEW_FIELD_PATHS,
  PHASE1A_FIELD_PATHS,
  PHASE1_CD_FIELD_PATHS,
} from '../src/services/phase2Validator';
import type { Phase1Result, Phase2Result } from '../src/types';

const MODELS = [
  'gemini-2.5-flash',
  'gemini-3-flash-preview',
  'gemini-3-pro-preview',
  'gemini-3.1-pro-preview',
];
const SNAPSHOT_PREFIX = '/tmp/decision_gate_real_';
const REPORTS_DIR = path.resolve(__dirname, '../../backend/.runtime/reports');

function bucketCited(bucket: readonly string[], cited: Iterable<string>): string[] {
  const out: string[] = [];
  for (const tracked of bucket) {
    for (const c of cited) {
      if (pathCoversTracked(c, tracked)) {
        out.push(tracked);
        break;
      }
    }
  }
  return out;
}

function bucketApplicable(bucket: readonly string[], phase1: any): string[] {
  return bucket.filter((p) => isPathPresentShallow(phase1, p));
}

function isPathPresentShallow(payload: any, p: string): boolean {
  if (p.includes('*')) {
    const parts = p.split('.');
    const starIndex = parts.indexOf('*');
    let cursor: any = payload;
    for (let i = 0; i < starIndex; i++) {
      if (cursor === null || cursor === undefined) return false;
      if (typeof cursor !== 'object') return false;
      const part = parts[i];
      if (!(part in cursor)) return false;
      cursor = cursor[part];
    }
    if (!cursor || typeof cursor !== 'object') return false;
    const remainder = parts.slice(starIndex + 1).join('.');
    if (remainder.length === 0) return Object.keys(cursor).length > 0;
    return Object.values(cursor).some((child) => isPathPresentShallow(child, remainder));
  }
  let cursor: any = payload;
  for (const part of p.split('.')) {
    if (cursor === null || cursor === undefined) return false;
    if (typeof cursor !== 'object') return false;
    if (!(part in cursor)) return false;
    cursor = cursor[part];
  }
  return cursor !== null && cursor !== undefined;
}

describe('decision-gate (multi-model, real track)', () => {
  const anySnapshot = MODELS.some((m) => existsSync(`${SNAPSHOT_PREFIX}${m}.json`));
  if (!anySnapshot) {
    it.skip(`skipped — no ${SNAPSHOT_PREFIX}<model>.json snapshots present`, () => { /* noop */ });
    return;
  }

  it('compares validator output across Gemini variants on Vtss-CantCatchMe.mp3', () => {
    const gates = MODELS.map((model) => {
      const snapshotPath = `${SNAPSHOT_PREFIX}${model}.json`;
      if (!existsSync(snapshotPath)) return { model, ok: false, reason: 'snapshot missing' };
      let snap: any;
      try { snap = JSON.parse(readFileSync(snapshotPath, 'utf8')); }
      catch (exc) { return { model, ok: false, reason: `parse: ${exc}` }; }
      const interpretation = snap?.stages?.interpretation ?? {};
      const measurement = snap?.stages?.measurement?.result;
      const phase1 = (measurement?.phase1 ?? measurement) as Phase1Result | undefined;
      const phase2 = (interpretation?.result ?? interpretation?.attemptsSummary?.[0]?.result) as Phase2Result | undefined;
      if (!phase1 || !phase2) {
        return { model, ok: false, reason: interpretation?.error?.code || 'no phase2', interpretationStatus: interpretation?.status };
      }
      const validationWarnings = interpretation?.diagnostics?.validationWarnings ?? [];
      const report = validatePhase2Consistency(phase1, phase2, { warnings: validationWarnings });
      const byType: Record<string, number> = {};
      const samplesByType: Record<string, string[]> = {};
      for (const v of report.violations) {
        byType[v.type] = (byType[v.type] || 0) + 1;
        samplesByType[v.type] = samplesByType[v.type] || [];
        if (samplesByType[v.type].length < 3) {
          samplesByType[v.type].push(`${v.field}: ${v.message.slice(0, 120)}…`);
        }
      }
      const mmc = (phase2 as any)?.mixAndMasterChain || [];
      const ar = (phase2 as any)?.abletonRecommendations || [];
      const ws = (phase2 as any)?.secretSauce?.workflowSteps || [];
      const allRecs = [...mmc, ...ar, ...ws];
      const cited = new Set<string>();
      for (const rec of allRecs) for (const f of (rec?.phase1Fields || [])) cited.add(String(f));

      // Same shape as the stems comparator: split A vs C/D, use the
      // bidirectional+wildcard matcher, report applicable-vs-cited fractions.
      // For the no-stem path, `stemAnalysis.*` tracked paths will report as
      // "not applicable" (the payload doesn't contain stems) so the gate
      // criterion is automatically gated.
      const newCitedA = bucketCited(PHASE1A_FIELD_PATHS, cited);
      const newCitedCD = bucketCited(PHASE1_CD_FIELD_PATHS, cited);
      const newCited = bucketCited(PHASE1_NEW_FIELD_PATHS, cited);
      const applicableA = bucketApplicable(PHASE1A_FIELD_PATHS, phase1);
      const applicableCD = bucketApplicable(PHASE1_CD_FIELD_PATHS, phase1);
      const stemCited = Array.from(cited).filter((c) => c.startsWith('stemAnalysis.'));
      const stemAnalysisPresent = !!(phase1 as any).stemAnalysis;

      const newFieldsOK_CD = applicableCD.length === 0 || newCitedCD.length >= 1;
      const newFieldsOK_A = applicableA.length === 0 || newCitedA.length >= 1;
      const gateCriteria = {
        '1. zero RECOMMENDATION_SALVAGED': (byType['RECOMMENDATION_SALVAGED'] ?? 0) === 0,
        '2. zero MISSING_CITATION': (byType['MISSING_CITATION'] ?? 0) === 0,
        '3. citation diversity OK': (byType['TRIVIAL_CITATIONS'] ?? 0) === 0,
        '4. Phase 1.A field cited when any are present': newFieldsOK_A,
        '5. low-confidence text hedged': (byType['LOW_CONFIDENCE_NOT_HEDGED'] ?? 0) === 0,
        '6. Phase 1.C/D field cited when any are present': newFieldsOK_CD,
      };
      const gatePassed = Object.values(gateCriteria).every(Boolean);
      return {
        model, ok: true,
        bpm: phase1?.bpm, key: phase1?.key, durationSeconds: phase1?.durationSeconds,
        recCounts: { mmc: mmc.length, ar: ar.length, ws: ws.length, total: allRecs.length },
        violationsByType: byType,
        samples: samplesByType,
        newCited, newCitedCount: newCited.length,
        newCitedA, newCitedCountA: newCitedA.length, applicableA, applicableCountA: applicableA.length,
        newCitedCD, newCitedCountCD: newCitedCD.length, applicableCD, applicableCountCD: applicableCD.length,
        stemCited, stemAnalysisPresent,
        gateCriteria, gatePassed,
        validationWarnings,
        interpretationStatus: interpretation?.status,
      };
    });
    const ok = gates.filter((g: any) => g.ok);
    expect(ok.length).toBeGreaterThan(0);

    const lines: string[] = [];
    lines.push('# Phase 1.B+1.C+1.D Decision Gate v3.1 — NO-STEM path multi-model on real track');
    lines.push(`Generated: ${new Date().toISOString()}`);
    lines.push('');
    const first: any = ok[0];
    lines.push(`Track: \`apps/backend/tests/fixtures/bench_tracks/Vtss-CantCatchMe.mp3\` (~${Math.round(first.durationSeconds)}s, ${first.bpm} BPM, key ${first.key}).`);
    lines.push(`Profile: \`producer_summary\`. Mode: no stems, no transcription (pitch_note_mode=off).`);
    lines.push('');
    lines.push(`Tracked Phase 1 paths: **Phase 1.A** = ${PHASE1A_FIELD_PATHS.length}, **Phase 1.C/D** = ${PHASE1_CD_FIELD_PATHS.length} (combined ${PHASE1_NEW_FIELD_PATHS.length}). Stem-scoped paths (\`stemAnalysis.*.*\`) are correctly absent from "applicable" counts in this no-stem run.`);
    lines.push('');
    lines.push('## Verdict summary');
    lines.push('');
    lines.push('| Model | Status | Recs | Err | Warn | Salvg | Missing | NewUncited | A-cited | C/D-cited | Gate |');
    lines.push('|---|---|---|---|---|---|---|---|---|---|---|');
    for (const g of gates as any[]) {
      if (!g.ok) { lines.push(`| ${g.model} | ${g.reason} | — | — | — | — | — | — | — | — | ✗ |`); continue; }
      const v = g.violationsByType;
      const errors = (v['MISSING_CITATION']??0) + (v['LOW_CONFIDENCE_NOT_HEDGED']??0) + (v['RECOMMENDATION_SALVAGED']??0);
      const warningsCount = Object.entries(v).filter(([k]) => !['MISSING_CITATION','LOW_CONFIDENCE_NOT_HEDGED','RECOMMENDATION_SALVAGED'].includes(k)).reduce((s, [,n]) => s + (n as number), 0);
      const verdict = g.gatePassed ? '✓ PASS' : '✗ FAIL';
      const aFrac = `${g.newCitedCountA}/${g.applicableCountA}`;
      const cdFrac = `${g.newCitedCountCD}/${g.applicableCountCD}`;
      lines.push(`| ${g.model} | ${g.interpretationStatus} | ${g.recCounts.total} | ${errors} | ${warningsCount} | ${v['RECOMMENDATION_SALVAGED']??0} | ${v['MISSING_CITATION']??0} | ${v['NEW_FIELD_UNCITED']??0} | ${aFrac} | ${cdFrac} | ${verdict} |`);
    }
    lines.push('');
    lines.push('## Cross-model failure pattern table');
    lines.push('');
    const ALL_TYPES = ['RECOMMENDATION_SALVAGED','MISSING_CITATION','NEW_FIELD_UNCITED','TRIVIAL_CITATIONS','LOW_CONFIDENCE_NOT_HEDGED','GENRE_IGNORES_DSP','BOUNDS_VIOLATION','NUMERIC_OVERRIDE'];
    lines.push('| Violation type | ' + ok.map((g: any) => g.model.replace('gemini-','').replace('-preview','')).join(' | ') + ' |');
    lines.push('|---|' + ok.map(() => '---').join('|') + '|');
    for (const t of ALL_TYPES) {
      const row = ok.map((g: any) => g.violationsByType[t] ?? 0).join(' | ');
      lines.push(`| ${t} | ${row} |`);
    }
    lines.push('');

    for (const g of ok as any[]) {
      lines.push(`## ${g.model}`);
      lines.push(`- gate: **${g.gatePassed ? 'PASS' : 'FAIL'}**`);
      lines.push(`- Phase 1.A fields cited (${g.newCitedCountA}/${g.applicableCountA}): \`${g.newCitedA.join(', ') || 'NONE'}\``);
      lines.push(`- Phase 1.C/D fields cited (${g.newCitedCountCD}/${g.applicableCountCD}): \`${g.newCitedCD.join(', ') || 'NONE'}\``);
      lines.push(`- Phase 1.C/D paths applicable but uncited: \`${g.applicableCD.filter((p: string) => !g.newCitedCD.includes(p)).join(', ') || 'NONE'}\``);
      if (g.stemCited.length > 0) {
        lines.push(`- ⚠ stemAnalysis paths cited (${g.stemCited.length}) — UNEXPECTED in no-stem mode: \`${g.stemCited.slice(0, 8).join(', ')}\``);
      }
      for (const t of ['RECOMMENDATION_SALVAGED', 'MISSING_CITATION', 'LOW_CONFIDENCE_NOT_HEDGED', 'TRIVIAL_CITATIONS']) {
        const samples = g.samples[t] ?? [];
        if (samples.length === 0) continue;
        lines.push(`- ${t} (${samples.length} shown):`);
        for (const s of samples) lines.push(`  - ${s}`);
      }
      if (g.validationWarnings.length > 0) {
        lines.push(`- backend validationWarnings: ${g.validationWarnings.length}`);
        for (const w of g.validationWarnings.slice(0, 3)) {
          lines.push(`  - **${w.code}** at \`${w.path}\`: ${w.message ?? ''}`);
        }
      }
      lines.push('');
    }

    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    mkdirSync(REPORTS_DIR, { recursive: true });
    const out = path.join(REPORTS_DIR, `decision_gate_real_${stamp}.md`);
    writeFileSync(out, lines.join('\n'), 'utf8');
    console.log(`real-track decision-gate report at ${out}`);
    for (const g of gates as any[]) {
      console.log(`  ${g.model}: ${g.ok ? (g.gatePassed ? 'PASS' : 'FAIL') : g.reason}`);
    }
    expect(existsSync(out)).toBe(true);
  });
});

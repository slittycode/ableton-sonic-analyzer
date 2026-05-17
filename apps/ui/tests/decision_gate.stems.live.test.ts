/**
 * Stem-aware multi-model decision gate comparator (v3).
 *
 * v3 changes vs v2:
 *  - Imports the tracked-paths list directly from `phase2Validator.ts`
 *    (`PHASE1_NEW_FIELD_PATHS`) so the two stay in sync.
 *  - Reports metrics split into Phase 1.A vs Phase 1.C/D buckets, so v3 is
 *    fairly comparable to v2 (v2 only had Phase 1.A fields available).
 *  - `newFieldsOK` is tightened: when Phase 1.C/D fields are present in the
 *    payload, the gate REQUIRES at least one Phase 1.C/D citation rather
 *    than letting "no warnings" trivially pass. The v2 escape hatch
 *    (`usefulUncited === 0 || newCited.length >= 1`) was too easy to satisfy
 *    once the tracked list went stale.
 *  - Uses `pathCoversTracked` for bidirectional + wildcard matching so a
 *    citation to `grooveDetail.perDrumSwing.snare` correctly satisfies the
 *    tracked parent `grooveDetail.perDrumSwing`, and a citation to
 *    `stemAnalysis.drums.reverbDetail.preDelayMs` satisfies
 *    `stemAnalysis.*.reverbDetail`.
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

const MODELS = ['gemini-2.5-flash','gemini-3-flash-preview','gemini-3-pro-preview','gemini-3.1-pro-preview'];
const PREFIX = '/tmp/decision_gate_stems_';
const REPORTS_DIR = path.resolve(__dirname, '../../backend/.runtime/reports');

// Helper: did any citation cover any path in the bucket using the validator's
// own matching rules? Mirrors validateNewFieldCoverage so a citation to a
// leaf/wildcard sub-path counts.
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

// Helper: a tracked path is "applicable" to this run iff the Phase 1 payload
// actually populates it (the validator already does this, but the comparator
// needs to know which paths to expect citations for in the gate criterion).
function bucketApplicable(bucket: readonly string[], phase1: any): string[] {
  return bucket.filter((p) => isPathPresentShallow(phase1, p));
}

function isPathPresentShallow(payload: any, p: string): boolean {
  // Mirror of phase2Validator.isPathPresentAndUseful, but lighter — we only
  // care whether the path navigates somewhere non-null. The full
  // density-aware check lives in the validator; here it suffices that the
  // analyzer EMITTED the field for this track so a citation would be valid.
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

describe('decision-gate (multi-model, stem-aware, real track)', () => {
  const anySnapshot = MODELS.some((m) => existsSync(`${PREFIX}${m}.json`));
  if (!anySnapshot) {
    it.skip(`skipped — no ${PREFIX}<model>.json snapshots present`, () => { /* noop */ });
    return;
  }

  it('compares per-model validator output with stemAnalysis populated', () => {
    const gates = MODELS.map((model) => {
      const p = `${PREFIX}${model}.json`;
      if (!existsSync(p)) return { model, ok: false, reason: 'missing' };
      const snap = JSON.parse(readFileSync(p,'utf8'));
      const interpretation = snap?.stages?.interpretation ?? {};
      const measurement = snap?.stages?.measurement?.result;
      const phase1 = (measurement?.phase1 ?? measurement) as Phase1Result | undefined;
      const phase2 = (interpretation?.result ?? interpretation?.attemptsSummary?.[0]?.result) as Phase2Result | undefined;
      if (!phase1 || !phase2) return { model, ok: false, reason: interpretation?.error?.code || 'no phase2' };

      const validationWarnings = interpretation?.diagnostics?.validationWarnings ?? [];
      const report = validatePhase2Consistency(phase1, phase2, { warnings: validationWarnings });
      const byType: Record<string, number> = {};
      const samples: Record<string, string[]> = {};
      for (const v of report.violations) {
        byType[v.type] = (byType[v.type] || 0) + 1;
        samples[v.type] = samples[v.type] || [];
        if (samples[v.type].length < 3) samples[v.type].push(`${v.field}: ${v.message.slice(0,110)}…`);
      }
      const mmc = (phase2 as any)?.mixAndMasterChain || [];
      const ar = (phase2 as any)?.abletonRecommendations || [];
      const ws = (phase2 as any)?.secretSauce?.workflowSteps || [];
      const allRecs = [...mmc,...ar,...ws];
      const cited = new Set<string>();
      for (const r of allRecs) for (const f of (r?.phase1Fields || [])) cited.add(String(f));

      // Split the tracked-paths citation tally into Phase 1.A vs Phase 1.C/D
      // buckets so v3 vs v2 is fairly comparable (v2 only had Phase 1.A fields
      // available to be cited). Uses pathCoversTracked so leaf citations
      // satisfy parent tracked paths and stem-scoped wildcards work.
      const newCitedA = bucketCited(PHASE1A_FIELD_PATHS, cited);
      const newCitedCD = bucketCited(PHASE1_CD_FIELD_PATHS, cited);
      const newCited = bucketCited(PHASE1_NEW_FIELD_PATHS, cited);
      const applicableCD = bucketApplicable(PHASE1_CD_FIELD_PATHS, phase1);
      const applicableA = bucketApplicable(PHASE1A_FIELD_PATHS, phase1);
      const stemCited = Array.from(cited).filter((c) => c.startsWith('stemAnalysis.'));
      const stemAnalysisPresent = !!(phase1 as any).stemAnalysis;

      // Tightened gate criterion: when Phase 1.C/D fields are actually
      // populated in the payload, the gate REQUIRES at least one Phase 1.C/D
      // citation — the "no warnings = pass" escape hatch is removed. If no
      // Phase 1.C/D fields are populated (e.g. degenerate fixture), the
      // criterion no-ops and the rest of the gate still runs.
      const newFieldsOK_CD = applicableCD.length === 0 || newCitedCD.length >= 1;
      // Phase 1.A criterion preserved for backward-compat (used to be the only
      // one — kept for the report's diff against v2).
      const usefulUncited = byType['NEW_FIELD_UNCITED'] ?? 0;
      const newFieldsOK_A = usefulUncited === 0 || newCited.length >= 1;

      const stemsOK = !stemAnalysisPresent || stemCited.length >= 1; // when stems exist, expect at least 1 stem citation
      const gateCriteria = {
        '1. zero RECOMMENDATION_SALVAGED': (byType['RECOMMENDATION_SALVAGED'] ?? 0) === 0,
        '2. zero MISSING_CITATION': (byType['MISSING_CITATION'] ?? 0) === 0,
        '3. citation diversity OK': (byType['TRIVIAL_CITATIONS'] ?? 0) === 0,
        '4. new Phase 1.A field cited (or none meaningful)': newFieldsOK_A,
        '5. low-confidence text hedged': (byType['LOW_CONFIDENCE_NOT_HEDGED'] ?? 0) === 0,
        '6. stemAnalysis paths cited when available': stemsOK,
        '7. Phase 1.C/D field cited when any are present': newFieldsOK_CD,
      };
      const gatePassed = Object.values(gateCriteria).every(Boolean);
      return {
        model, ok: true,
        bpm: phase1?.bpm, key: phase1?.key, duration: phase1?.durationSeconds,
        recs: { mmc: mmc.length, ar: ar.length, ws: ws.length, total: allRecs.length },
        byType, samples,
        newCited, newCitedCount: newCited.length,
        newCitedA, newCitedCountA: newCitedA.length, applicableA, applicableCountA: applicableA.length,
        newCitedCD, newCitedCountCD: newCitedCD.length, applicableCD, applicableCountCD: applicableCD.length,
        stemCited, stemCitedCount: stemCited.length,
        stemAnalysisPresent,
        gateCriteria, gatePassed,
        validationWarnings,
        interpretationStatus: interpretation?.status,
      };
    });
    const ok = gates.filter((g: any) => g.ok);
    expect(ok.length).toBeGreaterThan(0);

    const lines: string[] = [];
    lines.push('# Phase 1.B+1.C+1.D Decision Gate v3 — Stem-aware multi-model on real track');
    lines.push(`Generated: ${new Date().toISOString()}`);
    lines.push('');
    const first: any = ok[0];
    lines.push(`Track: \`Vtss-CantCatchMe.mp3\` (~${Math.round(first.duration)}s, ${first.bpm} BPM, key ${first.key}). Mode: full + stem_notes (separation).`);
    lines.push('');
    lines.push(`Tracked Phase 1 paths: **Phase 1.A** = ${PHASE1A_FIELD_PATHS.length} paths, **Phase 1.C/D** = ${PHASE1_CD_FIELD_PATHS.length} paths (combined ${PHASE1_NEW_FIELD_PATHS.length}). Matching is bidirectional with \`*\` wildcard support — see \`pathCoversTracked\` in phase2Validator.ts.`);
    lines.push('');
    lines.push('## Verdict summary');
    lines.push('');
    lines.push('| Model | Status | Recs | Err | Warn | Salvg | Missing | NewUncited | A-cited | C/D-cited | StemCited | StemPresent | Gate |');
    lines.push('|---|---|---|---|---|---|---|---|---|---|---|---|---|');
    for (const g of gates as any[]) {
      if (!g.ok) { lines.push(`| ${g.model} | ${g.reason} | — | — | — | — | — | — | — | — | — | — | ✗ |`); continue; }
      const v = g.byType;
      const errors = (v['MISSING_CITATION']??0) + (v['LOW_CONFIDENCE_NOT_HEDGED']??0) + (v['RECOMMENDATION_SALVAGED']??0);
      const warnings = Object.entries(v).filter(([k]) => !['MISSING_CITATION','LOW_CONFIDENCE_NOT_HEDGED','RECOMMENDATION_SALVAGED'].includes(k)).reduce((s, [,n]) => s + (n as number), 0);
      const verdict = g.gatePassed ? '✓ PASS' : '✗ FAIL';
      const cdFrac = `${g.newCitedCountCD}/${g.applicableCountCD}`;
      const aFrac = `${g.newCitedCountA}/${g.applicableCountA}`;
      lines.push(`| ${g.model} | ${g.interpretationStatus} | ${g.recs.total} | ${errors} | ${warnings} | ${v['RECOMMENDATION_SALVAGED']??0} | ${v['MISSING_CITATION']??0} | ${v['NEW_FIELD_UNCITED']??0} | ${aFrac} | ${cdFrac} | ${g.stemCitedCount} | ${g.stemAnalysisPresent?'yes':'no'} | ${verdict} |`);
    }
    lines.push('');
    lines.push('A-cited / C/D-cited columns are "tracked paths cited / tracked paths applicable to this run" — applicable = the path is actually populated in this Phase 1 payload. A higher ratio means Gemini is using more of the available depth.');
    lines.push('');
    lines.push('## Cross-model violations');
    lines.push('');
    const TYPES = ['RECOMMENDATION_SALVAGED','MISSING_CITATION','NEW_FIELD_UNCITED','TRIVIAL_CITATIONS','LOW_CONFIDENCE_NOT_HEDGED','GENRE_IGNORES_DSP','BOUNDS_VIOLATION'];
    lines.push('| Type | ' + ok.map((g: any) => g.model.replace('gemini-','').replace('-preview','')).join(' | ') + ' |');
    lines.push('|---|' + ok.map(() => '---').join('|') + '|');
    for (const t of TYPES) {
      const row = ok.map((g: any) => g.byType[t] ?? 0).join(' | ');
      lines.push(`| ${t} | ${row} |`);
    }
    lines.push('');

    for (const g of ok as any[]) {
      lines.push(`## ${g.model}`);
      lines.push(`- gate: **${g.gatePassed ? 'PASS' : 'FAIL'}**`);
      lines.push(`- Phase 1.A fields cited (${g.newCitedCountA}/${g.applicableCountA}): \`${g.newCitedA.join(', ') || 'NONE'}\``);
      lines.push(`- Phase 1.C/D fields cited (${g.newCitedCountCD}/${g.applicableCountCD}): \`${g.newCitedCD.join(', ') || 'NONE'}\``);
      lines.push(`- Phase 1.C/D paths applicable but uncited: \`${g.applicableCD.filter((p: string) => !g.newCitedCD.includes(p)).join(', ') || 'NONE'}\``);
      lines.push(`- stemAnalysis paths cited: ${g.stemCitedCount} → \`${g.stemCited.slice(0, 8).join(', ') || 'NONE'}\``);
      for (const t of ['RECOMMENDATION_SALVAGED','MISSING_CITATION','LOW_CONFIDENCE_NOT_HEDGED']) {
        const s = g.samples[t] ?? [];
        if (!s.length) continue;
        lines.push(`- ${t}:`);
        for (const x of s) lines.push(`  - ${x}`);
      }
      if (g.validationWarnings.length > 0) {
        lines.push(`- validation warnings: ${g.validationWarnings.length} — codes: ${g.validationWarnings.slice(0,5).map((w: any) => w.code).join(', ')}`);
      }
      lines.push('');
    }
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    mkdirSync(REPORTS_DIR, { recursive: true });
    const out = path.join(REPORTS_DIR, `decision_gate_stems_${stamp}.md`);
    writeFileSync(out, lines.join('\n'), 'utf8');
    console.log(`stem-aware report at ${out}`);
    for (const g of gates as any[]) console.log(`  ${g.model}: ${g.ok ? (g.gatePassed ? 'PASS' : 'FAIL') : g.reason}`);
    expect(existsSync(out)).toBe(true);
  });
});

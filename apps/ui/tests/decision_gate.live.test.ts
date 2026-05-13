/**
 * One-shot decision-gate runner.
 *
 * Reads a live Phase 2 snapshot from /tmp/decision_gate_snapshot.json, runs
 * the production validator (phase2Validator.ts) over it, and writes a
 * markdown report under .runtime/reports/. This file is intentionally
 * scoped to a single Phase 1.A gate run — delete after the gate has been
 * adjudicated or convert to a permanent harness if useful.
 *
 * Skip-gates if the snapshot file is missing so the suite still runs clean
 * on machines without the snapshot.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import path from 'node:path';
import { validatePhase2Consistency } from '../src/services/phase2Validator';
import type { Phase1Result, Phase2Result } from '../src/types';

const SNAPSHOT_PATH = '/tmp/decision_gate_snapshot.json';
const REPORTS_DIR = path.resolve(__dirname, '../../backend/.runtime/reports');

describe('decision-gate (live snapshot)', () => {
  if (!existsSync(SNAPSHOT_PATH)) {
    it.skip(`skipped — ${SNAPSHOT_PATH} not present`, () => { /* noop */ });
    return;
  }

  it('runs the validator on the live Phase 2 snapshot and writes a markdown report', () => {
    const snap = JSON.parse(readFileSync(SNAPSHOT_PATH, 'utf8'));
    const measurement = snap.stages?.measurement?.result;
    const phase1 = (measurement?.phase1 ?? measurement) as Phase1Result;
    const interpretation = snap.stages?.interpretation;
    const phase2 = (interpretation?.result ?? interpretation?.attemptsSummary?.[0]?.result) as Phase2Result;
    const validationWarnings = interpretation?.diagnostics?.validationWarnings ?? [];

    expect(phase1).toBeTruthy();
    expect(phase2).toBeTruthy();

    const report = validatePhase2Consistency(phase1, phase2, { warnings: validationWarnings });

    const byType: Record<string, typeof report.violations> = {};
    for (const v of report.violations) {
      byType[v.type] = byType[v.type] || [];
      byType[v.type].push(v);
    }

    const recCounts = {
      mixAndMasterChain: (phase2 as any)?.mixAndMasterChain?.length ?? 0,
      abletonRecommendations: (phase2 as any)?.abletonRecommendations?.length ?? 0,
      workflowSteps: (phase2 as any)?.secretSauce?.workflowSteps?.length ?? 0,
    };

    // Gate #4 is permissive — see decision_gate.multi.live.test.ts for the
    // rationale.
    const allRecs = [
      ...((phase2 as any)?.mixAndMasterChain ?? []),
      ...((phase2 as any)?.abletonRecommendations ?? []),
      ...((phase2 as any)?.secretSauce?.workflowSteps ?? []),
    ];
    const citedSet = new Set<string>();
    for (const rec of allRecs) for (const f of (rec?.phase1Fields ?? [])) citedSet.add(String(f));
    const NEW_FIELDS = [
      'lufsCurve', 'lufsCurve.shortTerm', 'lufsCurve.momentary',
      'spectralBalanceTimeSeries', 'rhythmDetail.tempoCurve',
      'stereoDetail.correlationCurve', 'arrangementDetail.noveltyCurve',
    ];
    const newCitedCount = NEW_FIELDS.filter(
      (p) => citedSet.has(p) || Array.from(citedSet).some((c) => p.startsWith(`${c}.`))
    ).length;
    const usefulUncited = (byType['NEW_FIELD_UNCITED'] ?? []).length;
    const newFieldsOK = usefulUncited === 0 || newCitedCount >= 1;

    const gateCriteria = {
      '1. zero RECOMMENDATION_SALVAGED': (byType['RECOMMENDATION_SALVAGED'] ?? []).length === 0,
      '2. zero MISSING_CITATION': (byType['MISSING_CITATION'] ?? []).length === 0,
      '3. non-trivial citation diversity (no TRIVIAL_CITATIONS)': (byType['TRIVIAL_CITATIONS'] ?? []).length === 0,
      '4. at least one new Phase 1.A field cited (or none meaningful)': newFieldsOK,
      '5. low-confidence text is hedged (no LOW_CONFIDENCE_NOT_HEDGED)': (byType['LOW_CONFIDENCE_NOT_HEDGED'] ?? []).length === 0,
    };
    const gatePassed = Object.values(gateCriteria).every(Boolean);

    const lines: string[] = [];
    lines.push(`# Phase 1.A Decision Gate — ${new Date().toISOString()}`);
    lines.push('');
    lines.push(`- runId: \`${snap.runId}\``);
    lines.push(`- track: \`apps/ui/public/demo.mp3\` (${phase1?.durationSeconds}s, ${phase1?.bpm} BPM, key ${phase1?.key})`);
    lines.push(`- mode: full DSP + Gemini interpretation (no stem separation, no transcription)`);
    lines.push(`- recommendation counts: \`mixAndMasterChain=${recCounts.mixAndMasterChain} abletonRecommendations=${recCounts.abletonRecommendations} workflowSteps=${recCounts.workflowSteps}\` (total ${recCounts.mixAndMasterChain + recCounts.abletonRecommendations + recCounts.workflowSteps})`);
    lines.push('');
    lines.push('## Gate verdict');
    lines.push('');
    lines.push(gatePassed ? '**PASSED** ✓ all five criteria met.' : '**FAILED** — one or more gate criteria failed (see below).');
    lines.push('');
    lines.push('| # | Criterion | Result |');
    lines.push('|---|---|---|');
    Object.entries(gateCriteria).forEach(([k, ok]) => {
      lines.push(`| ${k.split('.')[0]} | ${k.split('.').slice(1).join('.').trim()} | ${ok ? '✓ pass' : '✗ fail'} |`);
    });
    lines.push('');
    lines.push(`## Validator summary`);
    lines.push('');
    lines.push(`- total violations: **${report.violations.length}** (errors=${report.summary.errorCount}, warnings=${report.summary.warningCount})`);
    lines.push(`- backend validationWarnings on the run: **${validationWarnings.length}**`);
    lines.push('');
    lines.push('## Violations by type');
    lines.push('');
    for (const [type, vs] of Object.entries(byType).sort()) {
      lines.push(`### ${type} (${vs.length})`);
      lines.push('');
      for (const v of vs.slice(0, 8)) {
        lines.push(`- **${v.severity}** \`${v.field}\` — ${v.message}`);
      }
      if (vs.length > 8) lines.push(`- ...and ${vs.length - 8} more`);
      lines.push('');
    }
    if (validationWarnings.length > 0) {
      lines.push('## Raw backend validationWarnings');
      lines.push('');
      for (const w of validationWarnings) {
        lines.push(`- **${w.code}** at \`${w.path}\`: ${w.message ?? ''}`);
        if (w.dropReason) lines.push(`  - dropReason: \`${w.dropReason}\``);
      }
      lines.push('');
    }

    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    mkdirSync(REPORTS_DIR, { recursive: true });
    const reportPath = path.join(REPORTS_DIR, `decision_gate_${stamp}.md`);
    writeFileSync(reportPath, lines.join('\n'), 'utf8');
    console.log(`decision-gate report written to ${reportPath}`);
    console.log(`gatePassed=${gatePassed}; violations=${report.violations.length}`);

    // Don't fail the test on a gate fail — this is a diagnostic runner. The
    // assertion just ensures the runner produced a report.
    expect(existsSync(reportPath)).toBe(true);
  });
});

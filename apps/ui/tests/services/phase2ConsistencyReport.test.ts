import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Phase2ConsistencyReport } from '../../src/components/Phase2ConsistencyReport';
import type { ValidationReport } from '../../src/services/phase2Validator';

function buildReport(overrides: Partial<ValidationReport> = {}): ValidationReport {
  return {
    violations: [],
    passed: true,
    summary: {
      errorCount: 0,
      warningCount: 0,
      checkedFields: 5,
    },
    ...overrides,
  };
}

describe('Phase2ConsistencyReport', () => {
  it('renders a compact success indicator when validation passes with no violations', () => {
    const html = renderToStaticMarkup(
      React.createElement(Phase2ConsistencyReport, {
        report: buildReport(),
      }),
    );

    expect(html).toContain('CONSISTENCY OK');
    expect(html).not.toContain('<table');
  });

  it('renders nothing for a clean report when hideWhenClean is set', () => {
    const html = renderToStaticMarkup(
      React.createElement(Phase2ConsistencyReport, {
        report: buildReport(),
        hideWhenClean: true,
      }),
    );

    expect(html).toBe('');
  });

  it('still renders the table for a failing report when hideWhenClean is set', () => {
    const html = renderToStaticMarkup(
      React.createElement(Phase2ConsistencyReport, {
        report: buildReport({
          passed: false,
          violations: [
            {
              type: 'NUMERIC_OVERRIDE',
              field: 'bpm',
              severity: 'ERROR',
              message: 'BPM contradiction.',
            },
          ],
          summary: { errorCount: 1, warningCount: 0, checkedFields: 5 },
        }),
        hideWhenClean: true,
      }),
    );

    expect(html).toContain('<table');
    expect(html).toContain('BPM contradiction.');
  });

  it('renders an error violation row with the field and detail message', () => {
    const html = renderToStaticMarkup(
      React.createElement(Phase2ConsistencyReport, {
        report: buildReport({
          passed: false,
          violations: [
            {
              type: 'NUMERIC_OVERRIDE',
              field: 'bpm',
              phase1Value: 128,
              phase2Value: 132,
              severity: 'ERROR',
              message: 'Phase 2 trackCharacter mentions BPM 132, which contradicts the DSP measurement.',
            },
          ],
          summary: {
            errorCount: 1,
            warningCount: 0,
            checkedFields: 5,
          },
        }),
      }),
    );

    expect(html).toContain('1 error(s), 0 warning(s) across 5 checked fields');
    expect(html).toContain('<table');
    expect(html).toContain('bpm');
    expect(html).toContain('Phase 2 trackCharacter mentions BPM 132, which contradicts the DSP measurement.');
  });

  it('renders warning violations with the warning severity label and styling token', () => {
    const html = renderToStaticMarkup(
      React.createElement(Phase2ConsistencyReport, {
        report: buildReport({
          passed: true,
          violations: [
            {
              type: 'BOUNDS_VIOLATION',
              field: 'segmentLufs',
              phase1Value: -8.4,
              phase2Value: -15.2,
              severity: 'WARNING',
              message: 'Segment 2 LUFS is outside the expected range.',
            },
          ],
          summary: {
            errorCount: 0,
            warningCount: 1,
            checkedFields: 5,
          },
        }),
      }),
    );

    expect(html).toContain('WARNING');
    expect(html).toContain('text-warning');
  });

  // Audit Finding #1E: dev-audience violations (currently
  // NEW_FIELD_UNCITED coverage signals) stay in the underlying
  // ValidationReport for tests/research, but the user-facing System
  // Diagnostics panel suppresses them from both the rendered table and the
  // header counts to prevent "5 warnings shown" above an empty table.
  it('suppresses dev-audience violations from the rendered table and header counts', () => {
    const html = renderToStaticMarkup(
      React.createElement(Phase2ConsistencyReport, {
        report: buildReport({
          passed: true,
          violations: [
            {
              type: 'BOUNDS_VIOLATION',
              field: 'segmentLufs',
              severity: 'WARNING',
              message: 'User-visible bounds violation worth surfacing.',
            },
            {
              type: 'NEW_FIELD_UNCITED',
              field: 'lufsCurve.shortTerm',
              severity: 'WARNING',
              audience: 'dev',
              message: 'Phase 1 field present but not cited — engine coverage signal.',
            },
            {
              type: 'NEW_FIELD_UNCITED',
              field: 'rhythmDetail.tempoCurve',
              severity: 'WARNING',
              audience: 'dev',
              message: 'Phase 1 field present but not cited — engine coverage signal.',
            },
            {
              type: 'NEW_FIELD_UNCITED',
              field: 'chordDetail.chordTimeline',
              severity: 'WARNING',
              audience: 'dev',
              message: 'Phase 1 field present but not cited — engine coverage signal.',
            },
          ],
          summary: {
            errorCount: 0,
            warningCount: 4,
            checkedFields: 12,
          },
        }),
      }),
    );

    // Header counts derive from userVisible, not the summary object.
    expect(html).toContain('0 error(s), 1 warning(s) across 12 checked fields');
    // Only the user-visible row renders.
    expect(html).toContain('User-visible bounds violation worth surfacing.');
    // None of the dev-audience NEW_FIELD_UNCITED messages leak into the
    // user-facing surface.
    expect(html).not.toContain('engine coverage signal');
    expect(html).not.toContain('lufsCurve.shortTerm');
    expect(html).not.toContain('rhythmDetail.tempoCurve');
    expect(html).not.toContain('chordDetail.chordTimeline');
  });

  it('hides the report entirely when every violation is dev-audience', () => {
    const html = renderToStaticMarkup(
      React.createElement(Phase2ConsistencyReport, {
        report: buildReport({
          passed: true,
          violations: [
            {
              type: 'NEW_FIELD_UNCITED',
              field: 'lufsCurve.shortTerm',
              severity: 'WARNING',
              audience: 'dev',
              message: 'Engine coverage signal.',
            },
          ],
          summary: {
            errorCount: 0,
            warningCount: 1,
            checkedFields: 5,
          },
        }),
      }),
    );

    // Falls through to the success rail because no user-visible violations exist.
    expect(html).toContain('CONSISTENCY OK');
    expect(html).not.toContain('<table');
  });

  it('truncates long detail messages to 120 characters with an ellipsis', () => {
    const longMessage =
      'This detail message is intentionally much longer than one hundred and twenty characters so the table cell must truncate it cleanly.';
    const html = renderToStaticMarkup(
      React.createElement(Phase2ConsistencyReport, {
        report: buildReport({
          passed: false,
          violations: [
            {
              type: 'MISSING_CITATION',
              field: 'genreDetail',
              severity: 'WARNING',
              message: longMessage,
            },
          ],
          summary: {
            errorCount: 0,
            warningCount: 1,
            checkedFields: 5,
          },
        }),
      }),
    );

    expect(html).toContain(`${longMessage.slice(0, 117)}...`);
    expect(html).not.toContain(longMessage);
  });
});

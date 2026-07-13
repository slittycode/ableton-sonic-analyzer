import type { Phase1Result } from '../../types';
import { collectNotableFindings, type FindingSeverity } from '../../services/notableFindings';
import { Pill } from '../ui';

const SEVERITY_TONE: Record<FindingSeverity, 'error' | 'warning' | 'neutral'> = {
  critical: 'error',
  warning: 'warning',
  info: 'neutral',
};

const SEVERITY_LABEL: Record<FindingSeverity, string> = {
  critical: 'CRITICAL',
  warning: 'CHECK',
  info: 'FYI',
};

export function NotableFindingsSection({ phase1 }: { phase1: Phase1Result }) {
  const findings = collectNotableFindings(phase1);
  if (findings.length === 0) return null;

  return (
    <section
      data-testid="notable-findings"
      className="space-y-2 rounded-sm border border-warning/40 bg-bg-card p-4"
    >
      <h2 className="text-sm font-mono uppercase tracking-wider text-text-primary">
        Worth checking
      </h2>
      <ul className="space-y-1.5">
        {findings.map((f) => (
          <li key={f.id} className="flex items-start gap-2">
            <Pill tone={SEVERITY_TONE[f.severity]} size="xs">
              {SEVERITY_LABEL[f.severity]}
            </Pill>
            <div className="min-w-0">
              <span className="text-xs font-mono text-text-primary">
                {f.domain}: {f.title}
              </span>
              <p className="text-micro text-text-secondary">{f.detail}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

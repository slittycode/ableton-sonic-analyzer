import { Sparkles } from 'lucide-react';

import type { Phase2Result } from '../../types';
import { formatDisplayText, getTextRoleClassName } from '../../utils/displayText';
import { truncateAtSentenceBoundary } from '../analysisResultsViewModel';
import { Pill } from '../ui';
import { MetaBadgeList, textRoleClassName } from './shared';

type SecretSauce = NonNullable<Phase2Result['secretSauce']>;

export function SecretSauceSection({
  secretSauce,
  isPhase2V2,
}: {
  secretSauce: SecretSauce;
  isPhase2V2: boolean;
}) {
  return (
    <div className="relative overflow-hidden bg-bg-card border border-accent/30 rounded-sm p-0 group">
      <div className="bg-accent/10 p-4 border-b border-accent/20 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="bg-accent text-bg-app p-1.5 rounded-sm">
            <Sparkles className="w-4 h-4" />
          </div>
          <h2
            data-text-role="section-title"
            className={textRoleClassName('section-title', 'text-accent')}
          >
            {formatDisplayText('Secret Sauce Protocol', 'title')}
          </h2>
        </div>
        <Pill tone="accent" variant="solid" size="sm">
          CONFIDENTIAL
        </Pill>
      </div>

      <div className="p-6 relative">
        <div className="absolute top-0 right-0 p-8 opacity-5 pointer-events-none">
          <Sparkles className="w-32 h-32 text-accent" />
        </div>

        <div className="relative z-10 space-y-6">
          <div className="space-y-2">
            <h3
              data-text-role="item-title"
              className={[getTextRoleClassName('item-title'), 'text-lg'].join(' ')}
            >
              {secretSauce.title}
            </h3>
            <p data-text-role="body" className={textRoleClassName('body', 'max-w-3xl border-l-2 border-accent/30 pl-4')}>
              {truncateAtSentenceBoundary(secretSauce.explanation, 600)}
            </p>
          </div>

          {isPhase2V2 && Array.isArray(secretSauce.workflowSteps) && secretSauce.workflowSteps.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-border/50">
              {secretSauce.workflowSteps.map((step) => (
                <div key={step.step} className="rounded-sm border border-border bg-bg-panel/40 p-4 space-y-3">
                  <div className="flex items-center gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-sm bg-bg-panel border border-border flex items-center justify-center text-accent font-mono text-xs">
                      {step.step}
                    </span>
                    <div className="min-w-0">
                      <p
                        data-text-role="item-title"
                        className={textRoleClassName('item-title', 'truncate')}
                      >
                        {step.device}
                      </p>
                      <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
                        {step.parameter}: {step.value}
                      </p>
                    </div>
                  </div>
                  <MetaBadgeList
                    items={[
                      { label: 'Context', value: step.trackContext },
                      { label: 'Device', value: step.device },
                    ]}
                  />
                  <p className="text-xs text-text-secondary leading-relaxed font-mono">
                    {truncateAtSentenceBoundary(step.instruction, 220)}
                  </p>
                  <div className="border border-accent/20 bg-accent/5 rounded-sm px-2 py-2">
                    <p className="text-meta font-mono text-accent uppercase tracking-wide">
                      Measurement Reason
                    </p>
                    <p className="text-xs font-mono text-text-secondary mt-1 leading-relaxed">
                      {truncateAtSentenceBoundary(step.measurementJustification, 220)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-border/50">
              {(Array.isArray(secretSauce.implementationSteps)
                ? secretSauce.implementationSteps
                : []
              ).map((step, idx) => (
                <div key={idx} className="flex space-x-3">
                  <span className="flex-shrink-0 w-6 h-6 rounded-sm bg-bg-panel border border-border flex items-center justify-center text-accent font-mono text-xs">
                    {idx + 1}
                  </span>
                  <p className="text-xs text-text-secondary leading-relaxed font-mono pt-1">
                    {truncateAtSentenceBoundary(step, 260)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

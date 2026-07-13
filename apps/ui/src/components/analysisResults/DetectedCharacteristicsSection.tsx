import type { Phase2Result } from '../../types';
import { toConfidenceBand } from '../../services/sessionMusician/confidenceBand';
import { truncateAtSentenceBoundary } from '../analysisResultsViewModel';
import { ConfidenceBandBadge } from '../sessionMusician/ConfidenceBandBadge';
import { Panel, Pill } from '../ui';
import { ResultsSectionHeader, textRoleClassName } from './shared';

type DetectedCharacteristics = NonNullable<Phase2Result['detectedCharacteristics']>;

export function DetectedCharacteristicsSection({
  characteristics,
}: {
  characteristics: DetectedCharacteristics;
}) {
  return (
    <div className="space-y-6">
      <ResultsSectionHeader
        title="Detected Characteristics"
        rightSlot={
          <Pill tone="neutral" variant="outline" size="sm">
            AI INTERP
          </Pill>
        }
      />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {characteristics.map((item, idx) => (
          <Panel
            key={idx}
            variant="surface"
            tone="active"
            padding="lg"
            className="flex flex-col transition-all hover:border-accent/40 group relative overflow-hidden"
          >
            <div className="absolute top-0 left-0 w-1 h-full bg-accent"></div>
            <div className="flex items-center justify-between mb-3 pl-2">
              <h3
                data-text-role="item-title"
                className={textRoleClassName('item-title', 'truncate pr-2')}
              >
                {item.name}
              </h3>
              {/* Audit Finding #4: Detected Characteristics cards used
                to render a HIGH/MED/LOW string pill with bespoke
                success/warning/error tones. Replaced with the canonical
                ConfidenceBandBadge so the same vocabulary (Solid /
                Workable / Rough / Unreliable) reads across every
                confidence surface in the UI. toConfidenceBand maps
                Gemini's HIGH→solid (0.9), MED→workable (0.6),
                LOW→rough (0.3) — middle of each band so the percent
                label reads as an honest hedge. */}
              {(() => {
                const band = toConfidenceBand(item.confidence);
                return band ? (
                  <ConfidenceBandBadge variant="compact" band={band} />
                ) : null;
              })()}
            </div>
            <p className="text-xs text-text-secondary leading-relaxed font-mono opacity-80 border-t border-border/50 pt-2 mt-2 pl-2">
              {truncateAtSentenceBoundary(item.explanation, 600)}
            </p>
          </Panel>
        ))}
      </div>
    </div>
  );
}

import type { Phase2Result } from '../../types';
import { truncateAtSentenceBoundary } from '../analysisResultsViewModel';
import { MetricTile, Panel, Pill } from '../ui';
import { ResultsSectionHeader } from './shared';

type ProjectSetup = NonNullable<Phase2Result['projectSetup']>;

export function ProjectSetupSection({ projectSetup }: { projectSetup: ProjectSetup }) {
  return (
    <section id="section-project-setup" className="space-y-6 scroll-mt-24">
      <ResultsSectionHeader
        title="Project Setup"
        rightSlot={
          <Pill tone="neutral" variant="outline" size="sm">
            LIVE 12 V2
          </Pill>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <MetricTile accent="accent" size="xl" label="Tempo" value={projectSetup.tempoBpm} unit="BPM" />
        <MetricTile accent="accent" size="xl" label="Meter" value={projectSetup.timeSignature} />
        <MetricTile accent="accent" size="xl" label="Sample Rate" value={`${projectSetup.sampleRate} Hz`} />
        <MetricTile accent="accent" size="xl" label="Bit Depth" value={`${projectSetup.bitDepth}-bit`} />
        <MetricTile accent="accent" size="xl" label="Headroom" value={projectSetup.headroomTarget} />
      </div>

      <Panel variant="surface" padding="lg">
        <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">
          Session Goal
        </p>
        <p className="mt-2 text-xs font-mono text-text-secondary leading-relaxed">
          {truncateAtSentenceBoundary(projectSetup.sessionGoal, 320)}
        </p>
      </Panel>
    </section>
  );
}

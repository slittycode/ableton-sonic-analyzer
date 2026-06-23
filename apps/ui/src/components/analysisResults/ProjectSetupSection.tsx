import type { Phase2Result } from '../../types';
import { truncateAtSentenceBoundary } from '../analysisResultsViewModel';
import { MetricTile } from '../ui';
import { ResultsSectionHeader } from './shared';

type ProjectSetup = NonNullable<Phase2Result['projectSetup']>;

export function ProjectSetupSection({ projectSetup }: { projectSetup: ProjectSetup }) {
  return (
    <section id="section-project-setup" className="space-y-6 scroll-mt-24">
      <ResultsSectionHeader
        title="Project Setup"
        rightSlot={
          <span className="text-meta font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">
            LIVE 12 V2
          </span>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <MetricTile accent="accent" size="xl" label="Tempo" value={projectSetup.tempoBpm} unit="BPM" />
        <MetricTile accent="accent" size="xl" label="Meter" value={projectSetup.timeSignature} />
        <MetricTile accent="accent" size="xl" label="Sample Rate" value={`${projectSetup.sampleRate} Hz`} />
        <MetricTile accent="accent" size="xl" label="Bit Depth" value={`${projectSetup.bitDepth}-bit`} />
        <MetricTile accent="accent" size="xl" label="Headroom" value={projectSetup.headroomTarget} />
      </div>

      <div className="rounded-sm border border-border bg-bg-card p-4">
        <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">
          Session Goal
        </p>
        <p className="mt-2 text-xs font-mono text-text-secondary leading-relaxed">
          {truncateAtSentenceBoundary(projectSetup.sessionGoal, 320)}
        </p>
      </div>
    </section>
  );
}

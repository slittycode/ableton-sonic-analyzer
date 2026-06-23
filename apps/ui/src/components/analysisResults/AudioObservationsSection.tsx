import type { Phase2Result } from '../../types';
import { truncateAtSentenceBoundary } from '../analysisResultsViewModel';
import { Panel, Pill } from '../ui';
import { ResultsSectionHeader } from './shared';

type AudioObservations = NonNullable<Phase2Result['audioObservations']>;

export function AudioObservationsSection({
  audioObservations,
}: {
  audioObservations: AudioObservations;
}) {
  return (
    <section id="section-audio-observations" className="space-y-6 scroll-mt-24">
      <ResultsSectionHeader
        title="Audio Observations"
        rightSlot={
          <Pill tone="neutral" variant="outline" size="sm">
            Perceptual / Audio-Derived
          </Pill>
        }
      />

      {/* The sound-design fingerprint is the section's primary insight, so it
          keeps the reserved accent (now via the Panel tone) while the rest of
          the cards read as neutral device panels. */}
      <Panel variant="surface" tone="active" padding="lg" className="space-y-2">
        <p className="text-meta font-mono uppercase tracking-[0.18em] text-accent">
          Sound Design Fingerprint
        </p>
        <p className="text-xs font-mono text-text-secondary leading-relaxed">
          {truncateAtSentenceBoundary(audioObservations.soundDesignFingerprint, 320)}
        </p>
      </Panel>

      {audioObservations.elementCharacter.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {audioObservations.elementCharacter.map((item, index) => (
            <Panel
              key={`${item.element}-${index}`}
              variant="surface"
              padding="lg"
              className="space-y-2"
            >
              <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">
                {item.element}
              </p>
              <p className="text-xs font-mono text-text-secondary leading-relaxed">
                {truncateAtSentenceBoundary(item.description, 220)}
              </p>
            </Panel>
          ))}
        </div>
      )}

      {audioObservations.productionSignatures.length > 0 && (
        <div className="space-y-2">
          <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">
            Production Signatures
          </p>
          <div className="flex flex-wrap gap-1.5">
            {audioObservations.productionSignatures.map((signature, index) => (
              <span
                key={`${signature}-${index}`}
                className="text-meta font-mono rounded-sm border border-accent/30 bg-accent/5 px-2 py-1 text-accent"
              >
                {truncateAtSentenceBoundary(signature, 140)}
              </span>
            ))}
          </div>
        </div>
      )}

      <Panel variant="surface" padding="lg" className="space-y-2">
        <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">
          Mix Context
        </p>
        <p className="text-xs font-mono text-text-secondary leading-relaxed">
          {truncateAtSentenceBoundary(audioObservations.mixContext, 280)}
        </p>
      </Panel>
    </section>
  );
}

/**
 * Beat Check — an ear test for the Phase 1 beat grid and bar-1 placement.
 *
 * Shows what Phase 1 measured (tempo, beat grid, downbeats, meter, each with
 * its local trust label) and opens a player that clicks on every measured beat
 * over the producer's own copy of the track, with a higher click on bar 1.
 * It displays measurements; it never re-estimates them.
 *
 * The player half is lazy-loaded so the audio engine (which creates the
 * AudioContext on import) stays out of the static import graph the Node test
 * suite renders — see src/audio/engine.ts.
 */

import { lazy, Suspense, useMemo, useState } from 'react';

import { buildBeatCheckModel, type BeatCheckModel } from '../../services/beatCheck';
import type { FundamentalsTrust } from '../../services/fundamentalsTrust';
import type { Phase1Result } from '../../types';
import { getTextRoleClassName } from '../../utils/displayText';
import { ErrorBoundary } from '../ErrorBoundary';
import { ResultsSectionHeader } from '../analysisResults/shared';
import { Button, Panel, Pill } from '../ui';

const BeatCheckPlayer = lazy(() => import('./BeatCheckPlayer'));

export function BeatCheckPanel({ phase1, audioFile }: { phase1: Phase1Result; audioFile: File | null }) {
  const model = useMemo(() => buildBeatCheckModel(phase1), [phase1]);
  const [open, setOpen] = useState(false);

  const blocker = !model.usable
    ? 'Phase 1 did not report a beat grid for this track, so there is nothing to click along to.'
    : !audioFile
      ? 'Beat Check plays the file you analysed in this session. Load the track again to use it.'
      : null;

  return (
    <section id="section-beat-check" data-testid="beat-check-panel" className="space-y-4 scroll-mt-24">
      <ResultsSectionHeader
        title="Beat Check"
        rightSlot={
          <Pill tone="neutral" variant="outline" size="sm">
            EAR TEST
          </Pill>
        }
      />

      <BeatCheckReadout model={model} />

      <p data-text-role="body" className={getTextRoleClassName('body')}>
        Plays the track with a click on every measured beat and a higher click on bar 1. If the clicks flam or
        drift against the drums, the beat grid is off. If the high click doesn&apos;t land where bar 1 feels like
        it starts, shift it a beat at a time and listen again.
      </p>

      {blocker ? (
        <p data-text-role="meta" className={getTextRoleClassName('meta')} data-testid="beat-check-blocker">
          {blocker}
        </p>
      ) : open && audioFile ? (
        <ErrorBoundary title="Beat Check unavailable">
          <Suspense
            fallback={
              <p data-text-role="meta" className={getTextRoleClassName('meta')}>
                Loading player…
              </p>
            }
          >
            <BeatCheckPlayer model={model} audioFile={audioFile} />
          </Suspense>
        </ErrorBoundary>
      ) : (
        <Button variant="primary" size="md" onClick={() => setOpen(true)} data-testid="beat-check-open">
          Open Beat Check
        </Button>
      )}
    </section>
  );
}

function TrustPill({ trust }: { trust: FundamentalsTrust }) {
  return (
    <Pill tone={trust.tone} variant="outline" size="sm">
      {trust.label}
    </Pill>
  );
}

function BeatCheckReadout({ model }: { model: BeatCheckModel }) {
  const { bpm, trust, beats, timeSignature, meterAssumed, downbeatSource, positionSource } = model;
  const downbeatNote =
    positionSource === 'none'
      ? 'No bar positions measured, so every click sounds the same.'
      : downbeatSource === 'stride'
        ? 'Placed on every 4th beat from the first, not found in the audio. Expect to shift it.'
        : downbeatSource === 'kick_accent'
          ? 'Found from where the kick hits hardest. On four-on-the-floor this is a weak clue.'
          : (trust.downbeats.plainEnglish ?? 'Bar 1 placement as measured.');

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Panel variant="surface" padding="lg" className="space-y-2">
        <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
          Tempo
        </p>
        <p className="font-mono text-value-lg text-text-primary" data-testid="beat-check-bpm">
          {bpm !== null ? bpm.toFixed(bpm % 1 === 0 ? 0 : 1) : '—'}
          <span className="text-value text-text-secondary"> BPM</span>
        </p>
        <TrustPill trust={trust.tempo} />
      </Panel>

      <Panel variant="surface" padding="lg" className="space-y-2">
        <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
          Beat grid
        </p>
        <p className="font-mono text-value-lg text-text-primary">
          {beats.length}
          <span className="text-value text-text-secondary"> beats</span>
        </p>
        <TrustPill trust={trust.beatGrid} />
      </Panel>

      <Panel variant="surface" padding="lg" className="space-y-2">
        <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
          Bar 1
        </p>
        <TrustPill trust={trust.downbeats} />
        <p data-text-role="meta" className={getTextRoleClassName('meta')}>
          {downbeatNote}
        </p>
      </Panel>

      <Panel variant="surface" padding="lg" className="space-y-2">
        <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
          Meter
        </p>
        <p className="font-mono text-value-lg text-text-primary">{timeSignature ?? '—'}</p>
        <div className="flex flex-wrap items-center gap-1.5">
          <TrustPill trust={trust.meter} />
          {meterAssumed && (
            <Pill tone="warning" variant="outline" size="sm">
              ASSUMED
            </Pill>
          )}
        </div>
      </Panel>
    </div>
  );
}

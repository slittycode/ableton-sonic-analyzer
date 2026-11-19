/**
 * Key Check — an ear test for the Phase 1 key measurement.
 *
 * PURPOSE.md asks that the reported key "matches what the user hears when they
 * play along on a keyboard". This panel shows what Phase 1 measured (key,
 * local trust label, profile agreement, tuning) and opens a keyboard that
 * highlights that scale so the producer can play along with the track and
 * judge it by ear. It displays measurements; it never picks a different key.
 *
 * The keyboard half is lazy-loaded: the audio engine module creates an
 * AudioContext on import, so it must stay out of the static import graph that
 * the Node test suite renders (see src/audio/engine.ts).
 */

import { lazy, Suspense, useMemo, useState } from 'react';

import { buildKeyCheckModel, relativeKey, type KeyCheckModel } from '../../services/keyCheck';
import type { Phase1Result } from '../../types';
import { getTextRoleClassName } from '../../utils/displayText';
import { ErrorBoundary } from '../ErrorBoundary';
import { ResultsSectionHeader } from '../analysisResults/shared';
import { Button, Panel, Pill } from '../ui';

const KeyCheckKeyboard = lazy(() => import('./KeyCheckKeyboard'));

export function KeyCheckPanel({ phase1 }: { phase1: Phase1Result }) {
  const model = useMemo(() => buildKeyCheckModel(phase1), [phase1]);
  const [open, setOpen] = useState(false);

  return (
    <section id="section-key-check" data-testid="key-check-panel" className="space-y-4 scroll-mt-24">
      <ResultsSectionHeader
        title="Key Check"
        rightSlot={
          <Pill tone="neutral" variant="outline" size="sm">
            EAR TEST
          </Pill>
        }
      />

      <KeyCheckReadout model={model} />

      <p data-text-role="body" className={getTextRoleClassName('body')}>
        {model.measured
          ? `Play along with the track to hear whether the measured key holds up. Highlighted keys are the measured scale; the ringed key is the tonic. ${model.measured.label} and ${relativeKey(model.measured).label} share every note, so the scale alone cannot separate them — hold the tonic drone under the track and listen for which note feels like home.`
          : 'Phase 1 did not report a usable key for this track, so nothing is highlighted. The keyboard still works for finding notes by ear.'}
      </p>

      {open ? (
        <ErrorBoundary title="Keyboard unavailable">
          <Suspense
            fallback={
              <p data-text-role="meta" className={getTextRoleClassName('meta')}>
                Loading keyboard…
              </p>
            }
          >
            <KeyCheckKeyboard model={model} />
          </Suspense>
        </ErrorBoundary>
      ) : (
        <Button variant="primary" size="md" onClick={() => setOpen(true)} data-testid="key-check-open">
          Open keyboard
        </Button>
      )}
    </section>
  );
}

function KeyCheckReadout({ model }: { model: KeyCheckModel }) {
  const { measured, rawKeyLabel, trust, ensemble, alternates, tuning, isApproximate } = model;
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      <Panel variant="surface" padding="lg" className="space-y-2">
        <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
          Measured key
        </p>
        <p className="font-mono text-value-lg text-text-primary" data-testid="key-check-measured-key">
          {measured?.label ?? rawKeyLabel ?? 'Not measured'}
        </p>
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone={trust.tone} variant="outline" size="sm">
            {trust.label}
          </Pill>
          {isApproximate && measured && (
            <Pill tone="warning" variant="outline" size="sm">
              APPROXIMATE
            </Pill>
          )}
        </div>
        {trust.plainEnglish && (
          <p data-text-role="meta" className={getTextRoleClassName('meta')}>
            {trust.plainEnglish}
          </p>
        )}
      </Panel>

      <Panel variant="surface" padding="lg" className="space-y-2">
        <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
          Key profiles
        </p>
        {ensemble ? (
          <p className="font-mono text-value-lg text-text-primary">
            {ensemble.agreeing}
            <span className="text-value text-text-secondary"> of {ensemble.total} agree</span>
          </p>
        ) : (
          <p className="font-mono text-value text-text-secondary">Not compared</p>
        )}
        {alternates.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-meta uppercase text-text-secondary">Also plausible</span>
            {alternates.map((alt) => (
              <span
                key={alt.label}
                className="rounded border border-border px-1.5 py-0.5 font-mono text-micro text-text-secondary"
              >
                {alt.label}
              </span>
            ))}
          </div>
        ) : (
          <p data-text-role="meta" className={getTextRoleClassName('meta')}>
            {ensemble ? 'No competing key reading.' : 'Profile comparison runs in full analysis mode.'}
          </p>
        )}
      </Panel>

      <Panel variant="surface" padding="lg" className="space-y-2">
        <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
          Tuning
        </p>
        {tuning.source === 'measured' ? (
          <>
            <p className="font-mono text-value-lg text-text-primary">
              {tuning.referenceHz.toFixed(1)}
              <span className="text-value text-text-secondary"> Hz</span>
            </p>
            <p data-text-role="meta" className={getTextRoleClassName('meta')}>
              {formatCents(tuning.cents)} from A440. The keyboard is tuned to match.
            </p>
          </>
        ) : (
          <>
            <p className="font-mono text-value text-text-secondary">Not measured</p>
            <p data-text-role="meta" className={getTextRoleClassName('meta')}>
              {tuning.source === 'rejected'
                ? 'The tuning estimate was out of range, so the keyboard uses A4 = 440 Hz.'
                : 'Tuning is measured in full analysis mode. The keyboard uses A4 = 440 Hz.'}
            </p>
          </>
        )}
      </Panel>
    </div>
  );
}

function formatCents(cents: number | null): string {
  if (cents === null) return '—';
  const rounded = Math.round(cents * 10) / 10;
  if (rounded === 0) return '0 cents';
  return `${rounded > 0 ? '+' : ''}${rounded.toFixed(1)} cents`;
}

import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { SampleRecord, SamplesManifest } from '../types/samples';
import {
  artifactStreamUrl,
  fetchExistingManifest,
  generateSamples,
} from '../services/sampleGenerationClient';
import { BackendClientError } from '../services/backendPhase1Client';
import {
  Button,
  DeviceRack,
  Panel,
  Pill,
  SectionHeader,
} from './ui';
import type { Tone } from './ui';

interface SamplePlaybackProps {
  runId: string | null | undefined;
  apiBaseUrl: string;
  /**
   * If false, the panel renders an explanatory placeholder rather than the
   * generate button. The caller passes false when measurement isn't complete
   * yet — there's nothing to audition against.
   */
  measurementCompleted: boolean;
}

type PanelStatus =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'generating' }
  | { kind: 'error'; message: string };

const CATEGORY_LABELS: Record<SampleRecord['category'], string> = {
  tonal: 'Tonal — key & chord foundation',
  drums: 'Drum kit',
  melody: 'Melody / lead phrase',
};

type RackStatus = 'idle' | 'active' | 'success' | 'warning' | 'error';

function rackStatusFor(
  panelStatus: PanelStatus,
  hasManifest: boolean,
): RackStatus {
  if (panelStatus.kind === 'error') return 'error';
  if (panelStatus.kind === 'generating') return 'active';
  if (hasManifest) return 'success';
  return 'idle';
}

/**
 * Audition panel that renders generated audio clips for the current run.
 *
 * Honest-uncertainty framing is non-negotiable per `PURPOSE.md`: these clips
 * are heuristic reconstructions of the measurement layer, not Ableton-accurate
 * renderings. The panel says so up top, every time.
 */
export function SamplePlayback({
  runId,
  apiBaseUrl,
  measurementCompleted,
}: SamplePlaybackProps): React.ReactElement | null {
  const [manifest, setManifest] = useState<SamplesManifest | null>(null);
  const [status, setStatus] = useState<PanelStatus>({ kind: 'idle' });

  // On mount, see if a manifest already exists for this run.
  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    const abort = new AbortController();
    setStatus({ kind: 'loading' });
    fetchExistingManifest(runId, { apiBaseUrl, signal: abort.signal })
      .then((existing) => {
        if (cancelled) return;
        setManifest(existing);
        setStatus({ kind: 'idle' });
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus({ kind: 'error', message: friendlyError(err) });
      });
    return () => {
      cancelled = true;
      abort.abort();
    };
  }, [runId, apiBaseUrl]);

  const handleGenerate = useCallback(
    async (force: boolean) => {
      if (!runId) return;
      setStatus({ kind: 'generating' });
      try {
        const next = await generateSamples(runId, { apiBaseUrl, force });
        setManifest(next);
        setStatus({ kind: 'idle' });
      } catch (err) {
        setStatus({ kind: 'error', message: friendlyError(err) });
      }
    },
    [runId, apiBaseUrl],
  );

  const groupedSamples = useMemo<
    Array<[SampleRecord['category'], SampleRecord[]]>
  >(() => {
    if (!manifest) return [];
    const groups = new Map<SampleRecord['category'], SampleRecord[]>();
    for (const sample of manifest.samples) {
      const list = groups.get(sample.category) ?? [];
      list.push(sample);
      groups.set(sample.category, list);
    }
    return Array.from(groups.entries());
  }, [manifest]);

  if (!runId) return null;

  const rackStatus = rackStatusFor(status, Boolean(manifest));

  return (
    <DeviceRack
      name="AUDITION SAMPLES"
      subtitle="· Phase 3 heuristic"
      status={rackStatus}
      aria-label="Audition samples"
      className="mt-6"
      action={
        manifest && (
          <Button
            variant="link"
            size="sm"
            onClick={() => handleGenerate(true)}
            disabled={status.kind === 'generating'}
          >
            Regenerate
          </Button>
        )
      }
    >
      <div className="space-y-3">
        <p className="font-mono text-eyebrow leading-snug text-text-secondary max-w-xl">
          Short clips derived from Phase 1 measurements (and Phase 2 context when
          available) so you can ear-check the measurement chain. These are not
          Ableton-accurate reconstructions — follow Phase 2 in Live for the
          production character.
        </p>

        {!measurementCompleted && (
          <p className="font-mono text-eyebrow text-text-secondary">
            Measurements still running — audition samples become available once
            Phase 1 completes.
          </p>
        )}

        {measurementCompleted && !manifest && status.kind !== 'generating' && (
          <Button
            variant="primary"
            size="md"
            ledIndicator
            onClick={() => handleGenerate(false)}
            disabled={status.kind === 'loading'}
          >
            {status.kind === 'loading' ? 'Checking…' : 'Generate audition samples'}
          </Button>
        )}

        {status.kind === 'generating' && (
          <p className="font-mono text-eyebrow text-text-secondary">
            Rendering audition clips…
          </p>
        )}

        {status.kind === 'error' && (
          <p className="font-mono text-eyebrow text-error" role="alert">
            {status.message}
          </p>
        )}

        {manifest && groupedSamples.length > 0 && (
          <div className="space-y-5">
            <ManifestMeta manifest={manifest} />
            {groupedSamples.map(([category, samples]) => (
              <React.Fragment key={category}>
                <SampleGroup
                  category={category}
                  samples={samples}
                  runId={runId}
                  apiBaseUrl={apiBaseUrl}
                />
              </React.Fragment>
            ))}
          </div>
        )}
      </div>
    </DeviceRack>
  );
}

function ManifestMeta({ manifest }: { manifest: SamplesManifest }) {
  const synthesisLabel =
    manifest.synthesisBackend === 'fluidsynth'
      ? 'FluidSynth + GM SoundFont'
      : 'NumPy sine-additive fallback';
  const theoryLabel =
    manifest.theoryBackend === 'pytheory'
      ? 'PyTheory'
      : 'Pure-Python theory fallback';
  return (
    <div className="flex flex-wrap gap-1.5">
      <Pill tone="neutral" leadingDot>Music theory: {theoryLabel}</Pill>
      <Pill tone="neutral" leadingDot>Synthesis: {synthesisLabel}</Pill>
    </div>
  );
}

interface SampleGroupProps {
  category: SampleRecord['category'];
  samples: SampleRecord[];
  runId: string;
  apiBaseUrl: string;
}

function SampleGroup({ category, samples, runId, apiBaseUrl }: SampleGroupProps) {
  return (
    <div className="space-y-2">
      <SectionHeader
        size="sm"
        eyebrow="Group"
        title={CATEGORY_LABELS[category]}
        ledTone="accent"
      />
      <ul className="space-y-2 list-none p-0">
        {samples.map((sample) => (
          <li key={sample.id}>
            <SampleCard sample={sample} runId={runId} apiBaseUrl={apiBaseUrl} />
          </li>
        ))}
      </ul>
    </div>
  );
}

interface SampleCardProps {
  sample: SampleRecord;
  runId: string;
  apiBaseUrl: string;
}

function SampleCard({ sample, runId, apiBaseUrl }: SampleCardProps) {
  const audioUrl = sample.artifactId
    ? artifactStreamUrl(runId, sample.artifactId, apiBaseUrl)
    : null;
  const midiUrl = sample.midiArtifactId
    ? artifactStreamUrl(runId, sample.midiArtifactId, apiBaseUrl)
    : null;

  const tone = confidenceTone(sample.confidence, sample.lowConfidence);
  const label = sample.lowConfidence
    ? 'Low confidence'
    : `${sample.confidence} confidence`;

  return (
    <Panel variant="surface" padding="md">
      <div className="flex items-baseline justify-between gap-3 mb-2">
        <span className="font-mono text-body-sm text-text-primary">{sample.label}</span>
        <Pill tone={tone} size="xs">{label}</Pill>
      </div>
      {audioUrl ? (
        <audio
          controls
          preload="none"
          src={audioUrl}
          className="w-full"
          aria-label={`Audition sample: ${sample.label}`}
        />
      ) : (
        <p className="font-mono text-eyebrow text-text-muted">Audio stream unavailable.</p>
      )}
      <p className="font-mono text-eyebrow text-text-secondary mt-2">
        {sample.cites.rationale}
      </p>
      {sample.cites.phase1Fields.length > 0 && (
        <p className="font-mono text-eyebrow text-text-muted mt-1">
          Cites:{' '}
          {sample.cites.phase1Fields.map((field, idx) => (
            <React.Fragment key={field}>
              {idx > 0 && ', '}
              <code className="text-text-primary bg-bg-app/60 rounded px-1 py-0.5 border border-border/40">
                {field}
              </code>
            </React.Fragment>
          ))}
        </p>
      )}
      {midiUrl && (
        <p className="font-mono text-eyebrow text-text-muted mt-1">
          <a
            href={midiUrl}
            className="text-accent underline underline-offset-2 hover:text-accent/80"
            download={sample.midiFilename ?? `${sample.id}.mid`}
          >
            Download MIDI
          </a>{' '}
          to audition with your own instruments in Ableton.
        </p>
      )}
    </Panel>
  );
}

function confidenceTone(
  confidence: SampleRecord['confidence'],
  lowConfidence: boolean,
): Tone {
  if (lowConfidence || confidence === 'LOW') return 'warning';
  if (confidence === 'MED') return 'neutral';
  return 'success';
}

function friendlyError(err: unknown): string {
  if (err instanceof BackendClientError) return err.message;
  if (err instanceof Error) return err.message;
  return 'Unknown error while talking to the sample generation service.';
}

import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { SampleRecord, SamplesManifest } from '../types/samples';
import {
  artifactStreamUrl,
  fetchExistingManifest,
  generateSamples,
} from '../services/sampleGenerationClient';
import { BackendClientError } from '../services/backendPhase1Client';

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

  return (
    <section
      className="rounded-lg border border-zinc-700 bg-zinc-900/40 p-4 mt-6"
      aria-labelledby="audition-heading"
    >
      <header className="flex items-baseline justify-between gap-3 mb-3">
        <div>
          <h3 id="audition-heading" className="text-base font-semibold text-zinc-100">
            Audition samples (Phase 3 — heuristic)
          </h3>
          <p className="text-xs text-zinc-400 mt-1 max-w-xl">
            Short clips derived from Phase 1 measurements (and Phase 2 context when
            available) so you can ear-check the measurement chain. These are not
            Ableton-accurate reconstructions — follow Phase 2 in Live for the
            production character.
          </p>
        </div>
        {manifest && (
          <button
            type="button"
            onClick={() => handleGenerate(true)}
            disabled={status.kind === 'generating'}
            className="text-xs underline text-zinc-400 hover:text-zinc-200 disabled:opacity-40"
          >
            Regenerate
          </button>
        )}
      </header>

      {!measurementCompleted && (
        <p className="text-sm text-zinc-400">
          Measurements still running — audition samples become available once Phase 1
          completes.
        </p>
      )}

      {measurementCompleted && !manifest && status.kind !== 'generating' && (
        <button
          type="button"
          onClick={() => handleGenerate(false)}
          disabled={status.kind === 'loading'}
          className="px-3 py-2 rounded bg-amber-600 text-zinc-50 text-sm font-medium hover:bg-amber-500 disabled:opacity-40"
        >
          {status.kind === 'loading' ? 'Checking…' : 'Generate audition samples'}
        </button>
      )}

      {status.kind === 'generating' && (
        <p className="text-sm text-zinc-300">Rendering audition clips…</p>
      )}

      {status.kind === 'error' && (
        <p className="text-sm text-red-400" role="alert">
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
    </section>
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
    <div className="flex flex-wrap gap-2 text-xs">
      <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-zinc-300">
        Music theory: {theoryLabel}
      </span>
      <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-zinc-300">
        Synthesis: {synthesisLabel}
      </span>
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
    <div>
      <h4 className="text-sm font-medium text-zinc-200 mb-2">
        {CATEGORY_LABELS[category]}
      </h4>
      <ul className="space-y-3">
        {samples.map((sample) => (
          <React.Fragment key={sample.id}>
            <SampleCard sample={sample} runId={runId} apiBaseUrl={apiBaseUrl} />
          </React.Fragment>
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

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/60 p-3">
      <div className="flex items-baseline justify-between gap-3 mb-2">
        <span className="text-sm text-zinc-100">{sample.label}</span>
        <span
          className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded ${confidenceClassFor(sample.confidence, sample.lowConfidence)}`}
        >
          {sample.lowConfidence ? 'Low confidence' : `${sample.confidence} confidence`}
        </span>
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
        <p className="text-xs text-zinc-500">Audio stream unavailable.</p>
      )}
      <p className="text-xs text-zinc-400 mt-2">{sample.cites.rationale}</p>
      {sample.cites.phase1Fields.length > 0 && (
        <p className="text-xs text-zinc-500 mt-1">
          Cites:{' '}
          {sample.cites.phase1Fields.map((field, idx) => (
            <React.Fragment key={field}>
              {idx > 0 && ', '}
              <code className="text-zinc-300 bg-zinc-800/60 rounded px-1">
                {field}
              </code>
            </React.Fragment>
          ))}
        </p>
      )}
      {midiUrl && (
        <p className="text-xs text-zinc-500 mt-1">
          <a
            href={midiUrl}
            className="underline hover:text-zinc-300"
            download={sample.midiFilename ?? `${sample.id}.mid`}
          >
            Download MIDI
          </a>{' '}
          to audition with your own instruments in Ableton.
        </p>
      )}
    </li>
  );
}

function confidenceClassFor(
  confidence: SampleRecord['confidence'],
  lowConfidence: boolean,
): string {
  if (lowConfidence || confidence === 'LOW') return 'bg-amber-900/40 text-amber-300';
  if (confidence === 'MED') return 'bg-zinc-700 text-zinc-200';
  return 'bg-emerald-900/40 text-emerald-300';
}

function friendlyError(err: unknown): string {
  if (err instanceof BackendClientError) return err.message;
  if (err instanceof Error) return err.message;
  return 'Unknown error while talking to the sample generation service.';
}

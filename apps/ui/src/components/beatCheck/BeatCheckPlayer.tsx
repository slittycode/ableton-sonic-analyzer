/**
 * The audio half of Beat Check, lazy-loaded from BeatCheckPanel. Audio work
 * stays on BeatChecker: this component reads cells/params with useValue,
 * writes params with `.value`, and calls play/stop. The only thing it does
 * with time is read where playback is (engine.core.perceivedTime) to light
 * the beat counter.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useValue } from '@audiorective/react';
import type { EngineState } from '@audiorective/core';

import { EngineProvider, useEngine } from '../../audio/engine';
import type { BeatCheckTrackState, BeatCheckTransport } from '../../audio/beatChecker';
import { beatIndexAt, formatTrackTime, type BeatCheckModel } from '../../services/beatCheck';
import { claimPlaybackFocus, onPlaybackFocusClaimed } from '../../services/playbackFocus';
import { getTextRoleClassName } from '../../utils/displayText';
import { ChoiceButton, ParamSlider, formatPercent, isEditableTarget } from '../audioControls';
import { Button, Panel } from '../ui';

export default function BeatCheckPlayer({ model, audioFile }: { model: BeatCheckModel; audioFile: File }) {
  return (
    <EngineProvider>
      <BeatCheckPlayerInner model={model} audioFile={audioFile} />
    </EngineProvider>
  );
}

function fileKey(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function BeatCheckPlayerInner({ model, audioFile }: { model: BeatCheckModel; audioFile: File }) {
  const { beatCheck, core } = useEngine();
  const engineState = useValue<EngineState>(core.state);
  const track = useValue<BeatCheckTrackState>(beatCheck.cells.track);
  const transport = useValue<BeatCheckTransport>(beatCheck.cells.transport);
  const accentShift = useValue(beatCheck.params.accentShift);

  const [regionId, setRegionId] = useState(model.regions[0]?.id ?? 'whole');
  const [loop, setLoop] = useState(false);
  const region = model.regions.find((entry) => entry.id === regionId) ?? model.regions[0];
  const playing = transport.state === 'playing';

  // Hand the measured beats to the player and decode this session's file.
  useEffect(() => {
    beatCheck.setBeats(model.beats, model.positions, model.meter);
    void beatCheck.loadTrack(audioFile, fileKey(audioFile));
  }, [beatCheck, model, audioFile]);

  // Stop when the panel closes.
  useEffect(() => () => beatCheck.stop(), [beatCheck]);

  const play = (nextRegionId = regionId, nextLoop = loop) => {
    const target = model.regions.find((entry) => entry.id === nextRegionId);
    if (!target) return;
    void core.start(); // idempotent; covers the first press
    // Pause the waveform player first: two unsynchronised copies of the track
    // would sound like the very flamming this test listens for.
    claimPlaybackFocus('beat-check');
    beatCheck.play({ start: target.start, end: target.end, loop: nextLoop });
  };

  // And stop if the waveform player starts the track while Beat Check plays.
  useEffect(
    () =>
      onPlaybackFocusClaimed((owner) => {
        if (owner !== 'beat-check') beatCheck.stop();
      }),
    [beatCheck],
  );

  // Changing region or loop while playing restarts from the new region.
  const selectRegion = (id: string) => {
    setRegionId(id);
    if (playing) play(id, loop);
  };
  const toggleLoop = (next: boolean) => {
    setLoop(next);
    if (playing) play(regionId, next);
  };

  // Space toggles play/stop while this panel is open (outside text inputs).
  const playRef = useRef(play);
  playRef.current = play;
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.code !== 'Space' || event.repeat || isEditableTarget(event.target)) return;
      if (event.target instanceof HTMLButtonElement) return; // let buttons handle Space themselves
      event.preventDefault();
      if (beatCheck.cells.transport.value.state === 'playing') beatCheck.stop();
      else playRef.current();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [beatCheck]);

  const beatIndex = usePlayheadBeat(playing, model.beats, () => beatCheck.trackPositionAt(core.perceivedTime));
  const position = beatIndex >= 0 ? model.positions[beatIndex] : undefined;
  const barNumber = useMemo(() => {
    if (beatIndex < 0 || model.positions.length === 0) return null;
    let bars = 0;
    for (let i = 0; i <= beatIndex; i += 1) if (model.positions[i] === 1) bars += 1;
    return bars;
  }, [beatIndex, model.positions]);

  const shiftOptions = Array.from({ length: model.meter }, (_, shift) => shift);
  const hasPositions = model.positions.length > 0;

  return (
    <div className="space-y-4" data-testid="beat-check-player">
      <Panel variant="surface" padding="lg" className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant={playing ? 'secondary' : 'primary'}
            size="md"
            disabled={track.status !== 'ready'}
            onClick={() => (playing ? beatCheck.stop() : play())}
            data-testid="beat-check-transport"
            aria-pressed={playing}
          >
            {playing ? 'Stop' : 'Play'}
          </Button>

          <label className="flex items-center gap-2 font-mono text-meta uppercase text-text-secondary">
            Region
            <select
              className="rounded-sm border border-border-light bg-bg-surface-dark px-2 py-1 font-mono text-meta text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
              value={region?.id}
              onChange={(event) => selectRegion(event.target.value)}
              data-testid="beat-check-region"
            >
              {model.regions.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 font-mono text-meta uppercase text-text-secondary">
            <input
              type="checkbox"
              className="accent-accent"
              checked={loop}
              onChange={(event) => toggleLoop(event.target.checked)}
            />
            Loop
          </label>

          <TrackStatus track={track} />
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <BeatLeds meter={model.meter} position={playing ? position : undefined} accentShift={accentShift} />
          <p className="font-mono text-value text-text-primary" data-testid="beat-check-counter">
            {playing && barNumber !== null && position !== undefined ? `Bar ${barNumber} · beat ${position}` : '—'}
          </p>
        </div>

        {engineState !== 'running' && (
          <p data-text-role="meta" className={getTextRoleClassName('meta')}>
            Audio starts when you press Play. Space also toggles playback.
          </p>
        )}
      </Panel>

      <Panel variant="surface" padding="lg" className="space-y-4">
        <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label="Bar 1 click">
          <span className="font-mono text-meta uppercase text-text-secondary">Bar 1 click</span>
          {shiftOptions.map((shift) => (
            <ChoiceButton
              key={shift}
              selected={accentShift === shift}
              disabled={!hasPositions}
              onClick={() => {
                beatCheck.params.accentShift.value = shift;
              }}
            >
              {shift === 0 ? 'As measured' : `+${shift} beat${shift > 1 ? 's' : ''}`}
            </ChoiceButton>
          ))}
        </div>
        <p data-text-role="meta" className={getTextRoleClassName('meta')}>
          Shifting moves only the high click. If a shifted click feels more like bar 1, the measured downbeat is
          that many beats early.
        </p>
        <div className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
          <ParamSlider label="Click" param={beatCheck.params.clickVolume} min={0} max={1} format={formatPercent} />
          <ParamSlider label="Track" param={beatCheck.params.trackVolume} min={0} max={1} format={formatPercent} />
        </div>
      </Panel>
    </div>
  );
}

function TrackStatus({ track }: { track: BeatCheckTrackState }) {
  const text =
    track.status === 'decoding'
      ? 'Decoding track…'
      : track.status === 'ready'
        ? `Track ready · ${formatTrackTime(track.duration)}`
        : track.status === 'error'
          ? `Couldn't decode the track: ${track.message}`
          : 'No track loaded';
  return (
    <span
      className={
        track.status === 'error'
          ? 'font-mono text-meta text-error'
          : 'font-mono text-meta text-text-secondary'
      }
      data-testid="beat-check-track-status"
    >
      {text}
    </span>
  );
}

function BeatLeds({
  meter,
  position,
  accentShift,
}: {
  meter: number;
  position: number | undefined;
  accentShift: number;
}) {
  return (
    <div className="flex items-center gap-1.5" aria-hidden data-testid="beat-check-leds">
      {Array.from({ length: meter }, (_, index) => {
        const beat = index + 1;
        const isAccent = ((beat - 1 - accentShift) % meter + meter) % meter === 0;
        const lit = position === beat;
        return (
          <span
            key={beat}
            data-lit={lit}
            className={[
              'h-3 w-3 rounded-full border',
              isAccent ? 'border-accent' : 'border-border-light',
              lit ? (isAccent ? 'bg-accent' : 'bg-text-primary') : 'bg-bg-surface-darker',
            ].join(' ')}
          />
        );
      })}
    </div>
  );
}

/**
 * The beat the listener is hearing, polled once per animation frame while
 * playing. React state changes only when the beat changes.
 */
function usePlayheadBeat(playing: boolean, beats: readonly number[], readPosition: () => number | null): number {
  const [index, setIndex] = useState(-1);
  const readRef = useRef(readPosition);
  readRef.current = readPosition;
  useEffect(() => {
    if (!playing) {
      setIndex(-1);
      return undefined;
    }
    let frame = 0;
    let last = -2;
    const tick = () => {
      const position = readRef.current();
      const next = position === null ? -1 : beatIndexAt(beats, position);
      if (next !== last) {
        last = next;
        setIndex(next);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, beats]);
  return index;
}

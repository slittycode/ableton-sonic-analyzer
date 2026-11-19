/**
 * The audio half of Key Check. Loaded with React.lazy from KeyCheckPanel so the
 * audiorective engine (and its AudioContext) only exists once a producer opens
 * the keyboard — see the client-only note in src/audio/engine.ts.
 *
 * Audio work stays on KeySynth: this component reads params/cells with
 * useValue, writes params with `.value`, and calls synth methods.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useValue } from '@audiorective/react';
import type { EngineState, Param, SchedulableParam } from '@audiorective/core';

import { EngineProvider, useEngine } from '../../audio/engine';
import { KEY_SYNTH_WAVEFORMS, type KeySynthWaveform } from '../../audio/keySynth';
import {
  DEFAULT_REFERENCE_A4,
  OCTAVE_DOWN_CODE,
  OCTAVE_UP_CODE,
  computerKeyToMidi,
  droneMidis,
  type KeyCheckModel,
  type ParsedKey,
} from '../../services/keyCheck';
import { getTextRoleClassName } from '../../utils/displayText';
import { Button, Panel } from '../ui';
// clsx, not ui/cn: tailwind-merge doesn't know ASA's custom text-size tokens
// (text-meta, text-nano, …) and drops them when a text colour is also set.
import { clsx } from 'clsx';
import { PianoKeyboard } from './PianoKeyboard';

const LOWEST_BASE_MIDI = 24; // C1
const HIGHEST_BASE_MIDI = 84; // C6
const DEFAULT_BASE_MIDI = 48; // C3
const KEYBOARD_SPAN = 24; // two octaves + the top C
const NOTE_VELOCITY = 0.8;

type Highlight = { kind: 'measured' } | { kind: 'alternate'; index: number } | { kind: 'none' };

const WAVEFORM_LABELS: Record<KeySynthWaveform, string> = {
  sine: 'Sine',
  triangle: 'Tri',
  sawtooth: 'Saw',
  square: 'Square',
};

export default function KeyCheckKeyboard({ model }: { model: KeyCheckModel }) {
  return (
    <EngineProvider>
      <KeyCheckKeyboardInner model={model} />
    </EngineProvider>
  );
}

function KeyCheckKeyboardInner({ model }: { model: KeyCheckModel }) {
  const { synth, core } = useEngine();
  // Explicit type argument: SignalAccessor is overloaded (read / write), and
  // inference otherwise lands on the write overload's `void`.
  const engineState = useValue<EngineState>(core.state);
  const heldNotes = useValue(synth.cells.heldNotes);
  const droneNotes = useValue(synth.cells.droneNotes);
  const referenceA4 = useValue(synth.params.referenceA4);

  const [highlight, setHighlight] = useState<Highlight>(
    model.measured ? { kind: 'measured' } : { kind: 'none' },
  );
  const [baseMidi, setBaseMidi] = useState(DEFAULT_BASE_MIDI);
  const [qwertyEnabled, setQwertyEnabled] = useState(true);

  const shownKey: ParsedKey | null =
    highlight.kind === 'measured'
      ? model.measured
      : highlight.kind === 'alternate'
        ? (model.alternates[highlight.index] ?? null)
        : null;

  // Tune to the measured A4 when Phase 1 has one; release everything on close.
  useEffect(() => {
    synth.params.referenceA4.value = model.tuning.referenceHz;
    return () => {
      synth.allNotesOff();
      synth.releaseDrone();
    };
  }, [synth, model.tuning.referenceHz]);

  const noteDown = (midi: number) => {
    void core.start(); // idempotent; covers the very first press
    synth.noteOn(midi, NOTE_VELOCITY);
  };
  const noteUp = (midi: number) => synth.noteOff(midi);

  // Computer keyboard, laid out like Live's Computer MIDI Keyboard.
  const baseRef = useRef(baseMidi);
  baseRef.current = baseMidi;
  useEffect(() => {
    if (!qwertyEnabled) return undefined;
    const pressed = new Map<string, number>();
    const releaseAll = () => {
      for (const midi of pressed.values()) synth.noteOff(midi);
      pressed.clear();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.repeat || event.metaKey || event.ctrlKey || event.altKey) return;
      if (isEditableTarget(event.target)) return;
      if (event.code === OCTAVE_DOWN_CODE || event.code === OCTAVE_UP_CODE) {
        event.preventDefault();
        const delta = event.code === OCTAVE_UP_CODE ? 12 : -12;
        setBaseMidi((current) => clampBase(current + delta));
        return;
      }
      const midi = computerKeyToMidi(event.code, baseRef.current);
      if (midi === null) return;
      event.preventDefault();
      pressed.set(event.code, midi);
      void core.start();
      synth.noteOn(midi, NOTE_VELOCITY);
    };
    const onKeyUp = (event: KeyboardEvent) => {
      const midi = pressed.get(event.code);
      if (midi === undefined) return;
      pressed.delete(event.code);
      synth.noteOff(midi);
    };
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    window.addEventListener('blur', releaseAll);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('blur', releaseAll);
      releaseAll();
    };
  }, [qwertyEnabled, synth, core]);

  const selectHighlight = (next: Highlight) => {
    setHighlight(next);
    // Keep an active drone on whichever tonic is being auditioned.
    if (droneNotes.length === 0) return;
    const nextKey =
      next.kind === 'measured' ? model.measured : next.kind === 'alternate' ? model.alternates[next.index] : null;
    if (nextKey) synth.holdDrone(droneMidis(nextKey));
    else synth.releaseDrone();
  };

  const toggleDrone = () => {
    if (droneNotes.length > 0) {
      synth.releaseDrone();
      return;
    }
    if (!shownKey) return;
    void core.start();
    synth.holdDrone(droneMidis(shownKey));
  };

  const heldSet = useMemo(() => new Set(heldNotes), [heldNotes]);
  const droneSet = useMemo(() => new Set(droneNotes), [droneNotes]);
  const usingMeasuredTuning =
    model.tuning.source === 'measured' && Math.abs(referenceA4 - model.tuning.referenceHz) < 1e-6;

  return (
    <div className="space-y-4" data-testid="key-check-instrument">
      <Panel variant="surface" padding="lg" className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary">Highlight</span>
          {model.measured && (
            <ChoiceButton
              selected={highlight.kind === 'measured'}
              onClick={() => selectHighlight({ kind: 'measured' })}
            >
              {model.measured.label} · measured
            </ChoiceButton>
          )}
          {model.alternates.map((alt, index) => (
            <ChoiceButton
              key={alt.label}
              selected={highlight.kind === 'alternate' && highlight.index === index}
              onClick={() => selectHighlight({ kind: 'alternate', index })}
            >
              {alt.label} · alternate
            </ChoiceButton>
          ))}
          <ChoiceButton selected={highlight.kind === 'none'} onClick={() => selectHighlight({ kind: 'none' })}>
            None
          </ChoiceButton>

          <span className="mx-1 h-4 w-px bg-border-light" aria-hidden />

          <Button
            size="sm"
            variant={droneNotes.length > 0 ? 'primary' : 'secondary'}
            disabled={!shownKey}
            aria-pressed={droneNotes.length > 0}
            onClick={toggleDrone}
            data-testid="key-check-drone"
          >
            {droneNotes.length > 0 ? 'Stop drone' : 'Tonic drone'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => synth.panic()}>
            Stop all
          </Button>
        </div>

        <PianoKeyboard
          lowMidi={baseMidi}
          highMidi={baseMidi + KEYBOARD_SPAN}
          scalePcs={shownKey?.scalePcs ?? null}
          tonicPc={shownKey?.tonicPc ?? null}
          preferFlats={shownKey?.preferFlats ?? false}
          activeNotes={heldSet}
          droneNotes={droneSet}
          computerBaseMidi={qwertyEnabled ? baseMidi : null}
          onNoteDown={noteDown}
          onNoteUp={noteUp}
        />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              disabled={baseMidi <= LOWEST_BASE_MIDI}
              onClick={() => setBaseMidi((current) => clampBase(current - 12))}
              aria-label="Octave down"
            >
              Oct −
            </Button>
            <span className="min-w-12 text-center font-mono text-meta text-text-secondary">
              C{Math.floor(baseMidi / 12) - 1}–C{Math.floor((baseMidi + KEYBOARD_SPAN) / 12) - 1}
            </span>
            <Button
              size="sm"
              variant="secondary"
              disabled={baseMidi >= HIGHEST_BASE_MIDI}
              onClick={() => setBaseMidi((current) => clampBase(current + 12))}
              aria-label="Octave up"
            >
              Oct +
            </Button>
          </div>
          <label className="flex items-center gap-2 font-mono text-meta uppercase text-text-secondary">
            <input
              type="checkbox"
              className="accent-accent"
              checked={qwertyEnabled}
              onChange={(event) => setQwertyEnabled(event.target.checked)}
            />
            Computer keys (A–; · Z/X octave)
          </label>
        </div>

        {engineState !== 'running' && (
          <p data-text-role="meta" className={getTextRoleClassName('meta')}>
            Audio starts on your first key press.
          </p>
        )}
      </Panel>

      <Panel variant="surface" padding="lg" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p data-text-role="eyebrow" className={getTextRoleClassName('eyebrow')}>
            Synth
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-meta uppercase text-text-secondary">Tuning</span>
            <ChoiceButton
              selected={usingMeasuredTuning}
              disabled={model.tuning.source !== 'measured'}
              onClick={() => {
                synth.params.referenceA4.value = model.tuning.referenceHz;
              }}
            >
              Measured A4 {model.tuning.source === 'measured' ? `${model.tuning.referenceHz.toFixed(1)} Hz` : '—'}
            </ChoiceButton>
            <ChoiceButton
              selected={!usingMeasuredTuning}
              onClick={() => {
                synth.params.referenceA4.value = DEFAULT_REFERENCE_A4;
              }}
            >
              440 Hz
            </ChoiceButton>
          </div>
        </div>
        <WaveformPicker param={synth.params.waveform} />
        <div className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
          <ParamSlider label="Cutoff" param={synth.params.cutoff} min={80} max={12000} scale="log" format={formatHz} />
          <ParamSlider label="Resonance" param={synth.params.resonance} min={0.1} max={12} format={(v) => v.toFixed(1)} />
          <ParamSlider label="Volume" param={synth.params.volume} min={0} max={1} format={formatPercent} />
          <span aria-hidden className="hidden lg:block" />
          <ParamSlider label="Attack" param={synth.params.attack} min={0.003} max={2} scale="log" format={formatSeconds} />
          <ParamSlider label="Decay" param={synth.params.decay} min={0.01} max={3} scale="log" format={formatSeconds} />
          <ParamSlider label="Sustain" param={synth.params.sustain} min={0} max={1} format={formatPercent} />
          <ParamSlider label="Release" param={synth.params.release} min={0.01} max={4} scale="log" format={formatSeconds} />
        </div>
      </Panel>
    </div>
  );
}

function ChoiceButton({
  selected,
  disabled,
  onClick,
  children,
}: {
  selected: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      onClick={onClick}
      className={clsx(
        // Not uppercased: key names must keep their spelling ("Ab", not "AB").
        'rounded-sm border px-2 py-1 font-mono text-meta tracking-wide transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
        'disabled:cursor-not-allowed disabled:opacity-40',
        selected
          ? 'border-accent/60 bg-accent/10 text-accent'
          : 'border-border-light text-text-secondary hover:border-accent/40 hover:text-text-primary',
      )}
    >
      {children}
    </button>
  );
}

function WaveformPicker({ param }: { param: Param<KeySynthWaveform> }) {
  const waveform = useValue(param);
  return (
    <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label="Waveform">
      <span className="font-mono text-meta uppercase text-text-secondary">Wave</span>
      {KEY_SYNTH_WAVEFORMS.map((option) => (
        <ChoiceButton key={option} selected={waveform === option} onClick={() => (param.value = option)}>
          {WAVEFORM_LABELS[option]}
        </ChoiceButton>
      ))}
    </div>
  );
}

const SLIDER_STEPS = 1000;

function ParamSlider({
  label,
  param,
  min,
  max,
  scale = 'linear',
  format,
}: {
  label: string;
  param: Param<number> | SchedulableParam;
  min: number;
  max: number;
  scale?: 'linear' | 'log';
  format: (value: number) => string;
}) {
  const value = useValue(param);
  const position = valueToPosition(value, min, max, scale);
  return (
    <label className="flex flex-col gap-1">
      <span className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-meta uppercase tracking-wide text-text-secondary">{label}</span>
        <span className="font-mono text-body-sm text-text-primary">{format(value)}</span>
      </span>
      <input
        type="range"
        min={0}
        max={SLIDER_STEPS}
        step={1}
        value={position}
        aria-valuetext={format(value)}
        className="w-full accent-accent"
        onChange={(event) => {
          param.value = positionToValue(Number(event.target.value), min, max, scale);
        }}
      />
    </label>
  );
}

function valueToPosition(value: number, min: number, max: number, scale: 'linear' | 'log'): number {
  const clamped = Math.min(max, Math.max(min, value));
  const t = scale === 'log' ? Math.log(clamped / min) / Math.log(max / min) : (clamped - min) / (max - min);
  return Math.round(t * SLIDER_STEPS);
}

function positionToValue(position: number, min: number, max: number, scale: 'linear' | 'log'): number {
  const t = position / SLIDER_STEPS;
  return scale === 'log' ? min * (max / min) ** t : min + (max - min) * t;
}

function formatHz(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(value >= 10000 ? 1 : 2)} kHz` : `${Math.round(value)} Hz`;
}

function formatSeconds(value: number): string {
  return value >= 1 ? `${value.toFixed(2)} s` : `${Math.round(value * 1000)} ms`;
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function clampBase(midi: number): number {
  return Math.min(HIGHEST_BASE_MIDI, Math.max(LOWEST_BASE_MIDI, midi));
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (target instanceof HTMLInputElement) {
    // Range sliders and checkboxes in this panel shouldn't swallow note keys.
    return !['range', 'checkbox', 'radio', 'button'].includes(target.type);
  }
  return target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement;
}

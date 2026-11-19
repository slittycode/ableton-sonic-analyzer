import { useCallback, useEffect, useMemo, useRef, type PointerEvent as ReactPointerEvent } from 'react';

import { computerKeyLabelFor, isBlackKey, midiNoteName } from '../../services/keyCheck';
// clsx, not ui/cn: tailwind-merge doesn't know ASA's custom text-size tokens
// (text-meta, text-nano, …) and drops them when a text colour is also set.
import { clsx } from 'clsx';

export interface PianoKeyboardProps {
  /** Lowest key; should be a C so the layout starts on a white key. */
  lowMidi: number;
  /** Highest key, inclusive. */
  highMidi: number;
  /** Pitch classes to highlight, or null to show a plain keyboard. */
  scalePcs: readonly number[] | null;
  tonicPc: number | null;
  preferFlats: boolean;
  activeNotes: ReadonlySet<number>;
  droneNotes: ReadonlySet<number>;
  /** When set, draws the computer-key letter on each mapped key. */
  computerBaseMidi: number | null;
  onNoteDown(midi: number): void;
  onNoteUp(midi: number): void;
}

/** Black-key width as a fraction of a white key. */
const BLACK_KEY_WIDTH = 0.62;

/**
 * Presentational piano keyboard. Pointer input supports click-and-hold,
 * dragging across keys (glissando) and multi-touch; it reports notes through
 * onNoteDown / onNoteUp and never touches audio itself.
 */
export function PianoKeyboard({
  lowMidi,
  highMidi,
  scalePcs,
  tonicPc,
  preferFlats,
  activeNotes,
  droneNotes,
  computerBaseMidi,
  onNoteDown,
  onNoteUp,
}: PianoKeyboardProps) {
  const { whites, blacks } = useMemo(() => layoutKeys(lowMidi, highMidi), [lowMidi, highMidi]);
  const scale = useMemo(() => (scalePcs ? new Set(scalePcs) : null), [scalePcs]);

  // pointerId → MIDI note it is holding.
  const pointerNotes = useRef(new Map<number, number>());
  const handlers = useRef({ onNoteDown, onNoteUp });
  handlers.current = { onNoteDown, onNoteUp };

  const press = useCallback((pointerId: number, midi: number) => {
    const held = pointerNotes.current.get(pointerId);
    if (held === midi) return;
    if (held !== undefined) handlers.current.onNoteUp(held);
    pointerNotes.current.set(pointerId, midi);
    handlers.current.onNoteDown(midi);
  }, []);

  const lift = useCallback((pointerId: number) => {
    const held = pointerNotes.current.get(pointerId);
    if (held === undefined) return;
    pointerNotes.current.delete(pointerId);
    handlers.current.onNoteUp(held);
  }, []);

  useEffect(() => {
    const onUp = (event: PointerEvent) => lift(event.pointerId);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    const held = pointerNotes.current;
    return () => {
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      for (const pointerId of [...held.keys()]) lift(pointerId);
    };
  }, [lift]);

  const keyProps = (midi: number) => ({
    onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      event.preventDefault();
      // Touch pointers are captured to the pressed element by default, which
      // would stop pointerenter firing on neighbouring keys during a slide.
      if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      press(event.pointerId, midi);
    },
    onPointerEnter: (event: ReactPointerEvent<HTMLDivElement>) => {
      if (pointerNotes.current.has(event.pointerId)) press(event.pointerId, midi);
    },
  });

  const describe = (midi: number) => {
    const name = midiNoteName(midi, preferFlats);
    const pc = midi % 12;
    if (!scale) return name;
    if (pc === tonicPc) return `${name}, tonic`;
    return scale.has(pc) ? `${name}, in scale` : `${name}, outside scale`;
  };

  const whiteWidth = 100 / whites.length;

  return (
    <div
      role="group"
      aria-label="Piano keyboard"
      data-testid="key-check-keyboard"
      className="relative h-40 w-full select-none touch-none rounded-sm border border-border bg-bg-surface-darker"
      onPointerLeave={(event) => lift(event.pointerId)}
      onContextMenu={(event) => event.preventDefault()}
    >
      <div className="flex h-full">
        {whites.map((midi) => {
          const pc = midi % 12;
          const inScale = !scale || scale.has(pc);
          const isTonic = scale !== null && pc === tonicPc;
          const active = activeNotes.has(midi) || droneNotes.has(midi);
          const letter = computerBaseMidi === null ? null : computerKeyLabelFor(midi, computerBaseMidi);
          return (
            <div
              key={midi}
              role="button"
              tabIndex={-1}
              aria-label={describe(midi)}
              aria-pressed={active}
              data-midi={midi}
              data-in-scale={scale ? inScale : undefined}
              className={clsx(
                'relative flex h-full flex-1 flex-col items-center justify-between border-r border-border pb-1.5 pt-1 last:border-r-0',
                'transition-colors duration-75',
                active ? 'bg-accent' : inScale ? 'bg-text-primary' : 'bg-text-muted',
              )}
              {...keyProps(midi)}
            >
              <span className="font-mono text-pico uppercase text-bg-app/60">{letter ?? ''}</span>
              <KeyMarker
                show={scale !== null && inScale}
                isTonic={isTonic}
                label={pitchLabel(midi, preferFlats, pc === 0)}
                onLight
                active={active}
              />
            </div>
          );
        })}
      </div>

      {blacks.map(({ midi, whiteIndex }) => {
        const pc = midi % 12;
        const inScale = !scale || scale.has(pc);
        const isTonic = scale !== null && pc === tonicPc;
        const active = activeNotes.has(midi) || droneNotes.has(midi);
        const letter = computerBaseMidi === null ? null : computerKeyLabelFor(midi, computerBaseMidi);
        const left = (whiteIndex + 1) * whiteWidth - (whiteWidth * BLACK_KEY_WIDTH) / 2;
        return (
          <div
            key={midi}
            role="button"
            tabIndex={-1}
            aria-label={describe(midi)}
            aria-pressed={active}
            data-midi={midi}
            data-in-scale={scale ? inScale : undefined}
            className={clsx(
              'absolute top-0 z-10 flex h-[60%] flex-col items-center justify-between rounded-b-sm border border-border pb-1 pt-1',
              'transition-colors duration-75',
              active ? 'bg-accent' : inScale ? 'bg-bg-card' : 'bg-bg-surface-dark',
            )}
            style={{ left: `${left}%`, width: `${whiteWidth * BLACK_KEY_WIDTH}%` }}
            {...keyProps(midi)}
          >
            <span className="font-mono text-pico uppercase text-text-secondary">{letter ?? ''}</span>
            <KeyMarker
              show={scale !== null && inScale}
              isTonic={isTonic}
              label={pitchLabel(midi, preferFlats, false)}
              onLight={false}
              active={active}
            />
          </div>
        );
      })}
    </div>
  );
}

function KeyMarker({
  show,
  isTonic,
  label,
  onLight,
  active,
}: {
  show: boolean;
  isTonic: boolean;
  label: string;
  onLight: boolean;
  active: boolean;
}) {
  if (!show) return <span aria-hidden className="h-3" />;
  return (
    <span aria-hidden className="flex flex-col items-center gap-0.5">
      <span
        className={clsx(
          'rounded-full',
          isTonic ? 'h-2.5 w-2.5 ring-2 ring-accent/40' : 'h-1.5 w-1.5',
          active ? 'bg-bg-app' : 'bg-accent',
        )}
      />
      <span
        className={clsx(
          'font-mono text-nano leading-none',
          isTonic ? 'font-bold' : '',
          onLight || active ? 'text-bg-app' : 'text-text-secondary',
        )}
      >
        {label}
      </span>
    </span>
  );
}

/** Pitch name, with the octave number only on Cs to keep the keys readable. */
function pitchLabel(midi: number, preferFlats: boolean, withOctave: boolean): string {
  const full = midiNoteName(midi, preferFlats);
  return withOctave ? full : full.replace(/-?\d+$/, '');
}

function layoutKeys(lowMidi: number, highMidi: number) {
  const whites: number[] = [];
  const blacks: Array<{ midi: number; whiteIndex: number }> = [];
  for (let midi = lowMidi; midi <= highMidi; midi += 1) {
    if (isBlackKey(midi)) {
      // A black key sits on the boundary after the most recent white key.
      if (whites.length > 0) blacks.push({ midi, whiteIndex: whites.length - 1 });
    } else {
      whites.push(midi);
    }
  }
  return { whites, blacks };
}

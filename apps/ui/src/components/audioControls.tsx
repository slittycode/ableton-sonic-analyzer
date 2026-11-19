/**
 * Small controls shared by the ear-test panels (Key Check, Beat Check). They
 * read engine params with useValue and write `.value` directly — no audio
 * logic lives here.
 */

import type { ReactNode } from 'react';
import { useValue } from '@audiorective/react';
import type { Param, SchedulableParam } from '@audiorective/core';
// clsx, not ui/cn: tailwind-merge doesn't know ASA's custom text-size tokens
// (text-meta, text-nano, …) and drops them when a text colour is also set.
import { clsx } from 'clsx';

export function ChoiceButton({
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

const SLIDER_STEPS = 1000;

export function ParamSlider({
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

export function formatHz(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(value >= 10000 ? 1 : 2)} kHz` : `${Math.round(value)} Hz`;
}

export function formatSeconds(value: number): string {
  return value >= 1 ? `${value.toFixed(2)} s` : `${Math.round(value * 1000)} ms`;
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (target instanceof HTMLInputElement) {
    // Range sliders and checkboxes in this panel shouldn't swallow note keys.
    return !['range', 'checkbox', 'radio', 'button'].includes(target.type);
  }
  return target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement;
}

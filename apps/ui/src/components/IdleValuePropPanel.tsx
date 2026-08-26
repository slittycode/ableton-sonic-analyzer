/**
 * Idle Signal Monitor — instrument chrome first, value-prop second.
 *
 * Wave 1 / W1-03: old ASA + Live 12 idle monitors read as meters waiting for
 * signal (AWAITING SIGNAL / NO SIGNAL), not SaaS marketing cards. We keep the
 * audit Finding #5 producer copy (locked by idleValuePropPanel.test.ts) but
 * frame it as a flat device face: mono status, dense facts, no soft panels.
 *
 * Visible only when `!audioFile`. Once a file lands, WaveformPlayer takes over.
 */
import React from 'react';
import { Activity, AudioWaveform, MoveRight, Sliders } from 'lucide-react';

export function IdleValuePropPanel() {
  return (
    <div
      data-testid="idle-value-prop"
      className="h-full flex flex-col min-h-[260px] overflow-hidden bg-bg-surface-darker border border-border p-4 md:p-5"
    >
      {/* Instrument status row — Live-style meter idle */}
      <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="w-1.5 h-1.5 rounded-full bg-led-idle shrink-0"
            aria-hidden
          />
          <p className="text-meta font-mono uppercase tracking-[0.18em] text-text-secondary truncate">
            Awaiting signal
          </p>
        </div>
        <p className="text-meta font-mono uppercase tracking-[0.14em] text-text-muted shrink-0">
          FFT · offline
        </p>
      </div>

      {/* Locked copy (tests): eyebrow + headline */}
      <p className="mt-4 text-meta font-mono uppercase tracking-[0.18em] text-accent">
        Upload a track. Get specific Ableton.
      </p>

      <h2 className="mt-2 text-body font-mono leading-snug text-text-primary tracking-wide">
        Drop a reference, get a measurement-cited rebuild plan for Live 12.
      </h2>

      <p className="mt-3 text-body-sm font-sans leading-relaxed text-text-secondary">
        Local DSP measures around 50 properties of your audio — tempo, key,
        loudness, spectral balance, transient character, stereo behavior. AI
        interpretation maps each one to a specific Ableton Live 12 device with
        parameter starting points and the measurement that justifies it.
      </p>

      <VisualPlaceholder />

      {/* Dense fact rows — closer to Live device param lists than marketing bullets */}
      <dl className="mt-4 space-y-2 text-body-sm font-sans text-text-secondary">
        <div className="flex gap-3 border-t border-border/60 pt-2">
          <dt className="text-meta font-mono uppercase tracking-wider text-text-muted w-16 shrink-0">
            Local
          </dt>
          <dd>
            <span className="text-text-primary">Local measurement in ~30 seconds.</span>{' '}
            AI interpretation typically takes 4–5 minutes.
          </dd>
        </div>
        <div className="flex gap-3 border-t border-border/60 pt-2">
          <dt className="text-meta font-mono uppercase tracking-wider text-text-muted w-16 shrink-0">
            Cite
          </dt>
          <dd>
            <span className="text-text-primary">Every recommendation cites the Phase 1 measurement</span>{' '}
            that grounds it. No vibes-only advice.
          </dd>
        </div>
        <div className="flex gap-3 border-t border-border/60 pt-2">
          <dt className="text-meta font-mono uppercase tracking-wider text-text-muted w-16 shrink-0">
            Live
          </dt>
          <dd>
            <span className="text-text-primary">Native + Max for Live devices only,</span>{' '}
            with specific parameter values instead of vague tutorials.
          </dd>
        </div>
      </dl>

      <p className="mt-auto pt-4 text-meta font-mono uppercase tracking-[0.16em] text-text-muted">
        ← Drop audio in the panel on the left, or click{' '}
        <span className="text-accent">Load Demo Track</span>.
      </p>
    </div>
  );
}

/**
 * Flat signal-path strip (not a dashed marketing card).
 * `data-asset-slot` kept for future GIF/SVG swap.
 */
function VisualPlaceholder() {
  return (
    <div
      data-asset-slot="idle-flow-loop"
      className="mt-4 border border-border bg-bg-app px-4 py-3 flex items-center justify-center gap-3 text-text-secondary"
      aria-label="Flow illustration: audio in, measurements, device chain out"
    >
      <span className="flex flex-col items-center gap-1">
        <AudioWaveform className="w-4 h-4 text-accent" aria-hidden="true" />
        <span className="text-nano font-mono uppercase tracking-wider text-text-muted">Audio</span>
      </span>
      <MoveRight className="w-3 h-3 text-text-muted" aria-hidden="true" />
      <span className="flex flex-col items-center gap-1">
        <Activity className="w-4 h-4 text-accent" aria-hidden="true" />
        <span className="text-nano font-mono uppercase tracking-wider text-text-muted">Measure</span>
      </span>
      <MoveRight className="w-3 h-3 text-text-muted" aria-hidden="true" />
      <span className="flex flex-col items-center gap-1">
        <Sliders className="w-4 h-4 text-accent" aria-hidden="true" />
        <span className="text-nano font-mono uppercase tracking-wider text-text-muted">Live 12</span>
      </span>
    </div>
  );
}

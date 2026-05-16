/**
 * Audit Finding #5: the idle Signal Monitor used to be a 200-pixel canvas of
 * "NO SIGNAL DETECTED" at 30% opacity — atmospheric, but it told a first-time
 * producer nothing about what ASA does, what to expect, or whether it's
 * worth their wait. This panel replaces that idle state with a value-prop
 * read in producer language.
 *
 * Visible only when `!audioFile` (the user hasn't picked a track yet). Once
 * a file lands, `WaveformPlayer` takes over the Signal Monitor area and this
 * panel disappears.
 *
 * Asset placeholder: the visual slot below the body copy is intentionally a
 * styled trio of Lucide icons rather than a GIF, so the panel ships without
 * binary assets in the repo. To replace with a real ~5s loop later, swap the
 * `<VisualPlaceholder />` block for an <img> / <video> referenced from
 * `apps/ui/public/`.
 */
import React from 'react';
import { Activity, AudioWaveform, MoveRight, Sliders } from 'lucide-react';

export function IdleValuePropPanel() {
  return (
    <div
      data-testid="idle-value-prop"
      className="h-full flex flex-col rounded-sm m-2 min-h-[260px] overflow-hidden bg-bg-app/40 border border-border/40 p-5 md:p-6"
    >
      <p className="text-[10px] font-mono uppercase tracking-[0.22em] text-accent">
        Upload a track. Get specific Ableton.
      </p>

      <h2 className="mt-3 text-base font-sans leading-snug text-text-primary">
        Drop a reference, get a measurement-cited rebuild plan for Live 12.
      </h2>

      <p className="mt-3 text-xs font-sans leading-relaxed text-text-secondary">
        Local DSP measures around 50 properties of your audio — tempo, key,
        loudness, spectral balance, transient character, stereo behavior. AI
        interpretation maps each one to a specific Ableton Live 12 device with
        parameter starting points and the measurement that justifies it.
      </p>

      <VisualPlaceholder />

      <ul className="mt-3 space-y-1.5 text-xs font-sans leading-relaxed text-text-secondary">
        {/* Honest pacing — the audit revisions clocked the real wait at ~5 min
            on a non-silent track. Don't promise faster than reality. */}
        <li className="flex items-start gap-2">
          <span className="mt-1 w-1 h-1 rounded-full bg-accent shrink-0" />
          <span>
            <span className="text-text-primary">Local measurement in ~30 seconds.</span>{' '}
            AI interpretation typically takes 4–5 minutes.
          </span>
        </li>
        <li className="flex items-start gap-2">
          <span className="mt-1 w-1 h-1 rounded-full bg-accent shrink-0" />
          <span>
            <span className="text-text-primary">Every recommendation cites the Phase 1 measurement</span>{' '}
            that grounds it. No vibes-only advice.
          </span>
        </li>
        <li className="flex items-start gap-2">
          <span className="mt-1 w-1 h-1 rounded-full bg-accent shrink-0" />
          <span>
            <span className="text-text-primary">Native + Max for Live devices only,</span>{' '}
            with specific parameter values instead of vague tutorials.
          </span>
        </li>
      </ul>

      <p className="mt-auto pt-4 text-[10px] font-mono uppercase tracking-[0.18em] text-text-secondary/70">
        ← Drop audio in the panel on the left, or click <span className="text-accent">Load Demo Track</span>.
      </p>
    </div>
  );
}

/**
 * Intentionally simple visual: three on-brand Lucide icons separated by
 * arrows representing the input → measurement → output flow. Marked as the
 * asset slot so swap-in is a single component substitution later.
 *
 * Marked with a `data-asset-slot` attribute so a real loop GIF / SVG can be
 * dropped in by grepping that attribute and replacing this entire component.
 */
function VisualPlaceholder() {
  return (
    <div
      data-asset-slot="idle-flow-loop"
      className="mt-5 rounded-sm border border-dashed border-border/60 bg-bg-card/30 px-6 py-5 flex items-center justify-center gap-3 text-text-secondary/70"
      aria-label="Flow illustration: audio in, measurements, device chain out"
    >
      <span className="flex flex-col items-center gap-1">
        <AudioWaveform className="w-5 h-5 text-accent/70" aria-hidden="true" />
        <span className="text-[8px] font-mono uppercase tracking-wider">Audio</span>
      </span>
      <MoveRight className="w-3.5 h-3.5 opacity-40" aria-hidden="true" />
      <span className="flex flex-col items-center gap-1">
        <Activity className="w-5 h-5 text-accent/70" aria-hidden="true" />
        <span className="text-[8px] font-mono uppercase tracking-wider">Measure</span>
      </span>
      <MoveRight className="w-3.5 h-3.5 opacity-40" aria-hidden="true" />
      <span className="flex flex-col items-center gap-1">
        <Sliders className="w-5 h-5 text-accent/70" aria-hidden="true" />
        <span className="text-[8px] font-mono uppercase tracking-wider">Live 12</span>
      </span>
    </div>
  );
}

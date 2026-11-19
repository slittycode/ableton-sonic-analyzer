/**
 * Linear ADSR envelope math for KeySynth voices.
 *
 * Kept pure (no Web Audio) so it runs under the Node unit suite. KeySynth uses
 * `envelopeLevelAt` to find where a voice's gain sits at the moment a release
 * is scheduled, then ramps from that exact point — every segment is linear, so
 * ramping to a point on the line reproduces the envelope without a click.
 */

export interface Adsr {
  /** Seconds from note-on to peak. */
  attack: number;
  /** Seconds from peak down to the sustain level. */
  decay: number;
  /** Sustain level as a fraction of peak, 0–1. */
  sustain: number;
  /** Seconds from release to silence. */
  release: number;
}

/** Shorter than ~3 ms and the attack clicks on most material. */
export const MIN_ATTACK_S = 0.003;
export const MIN_DECAY_S = 0.001;
/** Shorter than ~10 ms and note-offs click. */
export const MIN_RELEASE_S = 0.01;

function finiteOr(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback;
}

export function clampAdsr(adsr: Adsr): Adsr {
  return {
    attack: Math.max(MIN_ATTACK_S, finiteOr(adsr.attack, MIN_ATTACK_S)),
    decay: Math.max(MIN_DECAY_S, finiteOr(adsr.decay, MIN_DECAY_S)),
    sustain: Math.min(1, Math.max(0, finiteOr(adsr.sustain, 1))),
    release: Math.max(MIN_RELEASE_S, finiteOr(adsr.release, MIN_RELEASE_S)),
  };
}

/** Level `elapsed` seconds after note-on while the note is still held. */
export function heldLevelAt(elapsed: number, adsr: Adsr, peak: number): number {
  if (elapsed <= 0) return 0;
  if (elapsed < adsr.attack) return (peak * elapsed) / adsr.attack;
  const sustainLevel = peak * adsr.sustain;
  const decayElapsed = elapsed - adsr.attack;
  if (decayElapsed < adsr.decay) {
    return peak + ((sustainLevel - peak) * decayElapsed) / adsr.decay;
  }
  return sustainLevel;
}

/** Everything needed to know a voice's gain at any time. */
export interface EnvelopeState {
  /** Context time of note-on. */
  startTime: number;
  peak: number;
  adsr: Adsr;
  /** Context time the release began, or null while held. */
  releaseAt: number | null;
  /**
   * Gain at `releaseAt`. Stored rather than recomputed because a voice can be
   * released twice (a sequenced note stopped mid-release), and the second ramp
   * starts from the first ramp's line, not from the held envelope.
   */
  releaseLevel: number;
  /** Length of the scheduled release ramp in seconds (may be a fast steal/stop fade). */
  releaseDuration: number;
}

/** Gain of a voice at context time `t`, including any scheduled release. */
export function envelopeLevelAt(state: EnvelopeState, t: number): number {
  const { startTime, peak, adsr, releaseAt, releaseLevel, releaseDuration } = state;
  if (releaseAt === null || t < releaseAt) {
    return heldLevelAt(t - startTime, adsr, peak);
  }
  if (releaseDuration <= 0) return 0;
  const remaining = 1 - (t - releaseAt) / releaseDuration;
  return remaining <= 0 ? 0 : releaseLevel * remaining;
}

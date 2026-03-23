/**
 * Frequency/time conversion utilities for spectrogram hover readouts.
 *
 * Constants match the defaults in `spectral_viz.py` so that pixel
 * positions on the generated PNG images map back to the correct
 * physical values.
 */

// ---------------------------------------------------------------------------
// Constants (matching spectral_viz.py defaults)
// ---------------------------------------------------------------------------

const DEFAULT_SR = 44100;
const N_MELS = 128;
const FMIN_MEL = 0;
const FMAX_MEL = DEFAULT_SR / 2; // 22050

const CQT_N_BINS = 84;
const CQT_BINS_PER_OCTAVE = 12;
const CQT_FMIN = 32.703; // C1, librosa default

// ---------------------------------------------------------------------------
// Mel scale
// ---------------------------------------------------------------------------

/** Convert a mel value to Hz using the HTK formula. */
function melToHz(mel: number): number {
  return 700 * (10 ** (mel / 2595) - 1);
}

/** Convert a frequency in Hz to the mel scale (HTK formula). */
function hzToMel(hz: number): number {
  return 2595 * Math.log10(1 + hz / 700);
}

/**
 * Convert a pixel Y position on a mel spectrogram image to Hz.
 *
 * Y=0 is the top of the image (highest frequency), Y=imageHeight is
 * the bottom (lowest frequency).  The mel axis is linearly spaced in
 * mel units between `fmin` and `fmax`, then converted back to Hz.
 */
export function pixelToFreqMel(
  pixelY: number,
  imageHeight: number,
  nMels = N_MELS,
  fmin = FMIN_MEL,
  fmax = FMAX_MEL,
): number {
  if (imageHeight <= 0) return 0;
  // Fraction from top → 1 = high freq, 0 = low freq
  const frac = 1 - pixelY / imageHeight;
  const melMin = hzToMel(fmin);
  const melMax = hzToMel(fmax);
  const mel = melMin + frac * (melMax - melMin);
  return melToHz(mel);
}

// ---------------------------------------------------------------------------
// CQT scale
// ---------------------------------------------------------------------------

/**
 * Convert a pixel Y position on a CQT spectrogram image to Hz.
 *
 * CQT bins are logarithmically spaced starting from `fmin`.  The
 * lowest bin (bottom of image) corresponds to `fmin`.
 */
export function pixelToFreqCQT(
  pixelY: number,
  imageHeight: number,
  nBins = CQT_N_BINS,
  binsPerOctave = CQT_BINS_PER_OCTAVE,
  fmin = CQT_FMIN,
): number {
  if (imageHeight <= 0) return 0;
  const frac = 1 - pixelY / imageHeight;
  const bin = frac * nBins;
  return fmin * 2 ** (bin / binsPerOctave);
}

// ---------------------------------------------------------------------------
// Linear (STFT) scale
// ---------------------------------------------------------------------------

/**
 * Convert a pixel Y position on a linear STFT spectrogram (e.g.
 * harmonic or percussive) to Hz.
 *
 * The frequency axis runs linearly from 0 Hz (bottom) to sr/2 (top).
 */
export function pixelToFreqLinear(
  pixelY: number,
  imageHeight: number,
  sr = DEFAULT_SR,
): number {
  if (imageHeight <= 0) return 0;
  const frac = 1 - pixelY / imageHeight;
  return frac * (sr / 2);
}

// ---------------------------------------------------------------------------
// Time axis
// ---------------------------------------------------------------------------

/** Convert a pixel X position to time in seconds. */
export function pixelToTime(
  pixelX: number,
  imageWidth: number,
  durationSeconds: number,
): number {
  if (imageWidth <= 0) return 0;
  return (pixelX / imageWidth) * durationSeconds;
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

/** Format a frequency value for display: "440 Hz" or "2.4 kHz". */
export function formatFrequency(hz: number): string {
  if (hz >= 1000) {
    return `${(hz / 1000).toFixed(1)} kHz`;
  }
  return `${Math.round(hz)} Hz`;
}

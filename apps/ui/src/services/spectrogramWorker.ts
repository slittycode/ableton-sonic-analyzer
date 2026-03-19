/// <reference lib="webworker" />

// ---------------------------------------------------------------------------
// Mel-spectrogram Web Worker
//
// Computes a 128-band mel spectrogram from mono PCM data entirely off the
// main thread.  The result Float32Array is transferred (zero-copy) back to
// the caller.
// ---------------------------------------------------------------------------

// ---- Constants ------------------------------------------------------------

const FFT_SIZE = 2048;
const HOP_SIZE = 1024;
const MEL_BANDS = 128;
const MEL_FREQ_MIN = 20;
const MEL_FREQ_MAX_CAP = 16000;
const DB_FLOOR = -80;

// ---- Pre-computed tables (allocated once per worker lifetime) --------------

const hannWindow = new Float64Array(FFT_SIZE);
const bitRev = new Uint32Array(FFT_SIZE);
const twiddleRe = new Float64Array(FFT_SIZE / 2);
const twiddleIm = new Float64Array(FFT_SIZE / 2);

let tablesReady = false;

function initTables(): void {
  // Hann window
  const N = FFT_SIZE;
  for (let n = 0; n < N; n++) {
    hannWindow[n] = 0.5 * (1 - Math.cos((2 * Math.PI * n) / N));
  }

  // Bit-reversal permutation
  const logN = Math.log2(N) | 0;
  for (let i = 0; i < N; i++) {
    let reversed = 0;
    let val = i;
    for (let bit = 0; bit < logN; bit++) {
      reversed = (reversed << 1) | (val & 1);
      val >>= 1;
    }
    bitRev[i] = reversed;
  }

  // Twiddle factors: e^{-j 2 pi k / N} for k = 0 .. N/2-1
  const half = N / 2;
  for (let k = 0; k < half; k++) {
    const angle = (-2 * Math.PI * k) / N;
    twiddleRe[k] = Math.cos(angle);
    twiddleIm[k] = Math.sin(angle);
  }

  tablesReady = true;
}

// ---- Mel filterbank -------------------------------------------------------

function hzToMel(hz: number): number {
  return 2595 * Math.log10(1 + hz / 700);
}

function melToHz(mel: number): number {
  return 700 * (Math.pow(10, mel / 2595) - 1);
}

/**
 * Build a mel filterbank matrix (MEL_BANDS x fftBins).
 * Stored as a sparse representation for speed: for each mel band we keep only
 * the non-zero filter weights and their corresponding FFT-bin indices.
 */
interface MelFilter {
  startBin: number;
  weights: Float64Array;
}

function buildMelFilterbank(sampleRate: number): MelFilter[] {
  const fftBins = FFT_SIZE / 2 + 1;
  const fMax = Math.min(MEL_FREQ_MAX_CAP, sampleRate / 2);
  const melMin = hzToMel(MEL_FREQ_MIN);
  const melMax = hzToMel(fMax);

  // 130 mel-spaced points (128 bands + 2 edge points)
  const nPoints = MEL_BANDS + 2;
  const melPoints = new Float64Array(nPoints);
  const hzPoints = new Float64Array(nPoints);
  const binPoints = new Float64Array(nPoints);

  for (let i = 0; i < nPoints; i++) {
    melPoints[i] = melMin + ((melMax - melMin) * i) / (nPoints - 1);
    hzPoints[i] = melToHz(melPoints[i]);
    binPoints[i] = (hzPoints[i] * FFT_SIZE) / sampleRate;
  }

  const filters: MelFilter[] = new Array(MEL_BANDS);

  for (let m = 0; m < MEL_BANDS; m++) {
    const left = binPoints[m];
    const center = binPoints[m + 1];
    const right = binPoints[m + 2];

    const startBin = Math.max(0, Math.floor(left));
    const endBin = Math.min(fftBins - 1, Math.ceil(right));

    const weights = new Float64Array(endBin - startBin + 1);

    for (let b = startBin; b <= endBin; b++) {
      if (b >= left && b <= center && center !== left) {
        weights[b - startBin] = (b - left) / (center - left);
      } else if (b > center && b <= right && right !== center) {
        weights[b - startBin] = (right - b) / (right - center);
      }
    }

    filters[m] = { startBin, weights };
  }

  return filters;
}

// ---- Radix-2 Cooley-Tukey FFT (in-place) ---------------------------------

function fft(re: Float64Array, im: Float64Array): void {
  const N = FFT_SIZE;

  // Bit-reversal permutation
  for (let i = 0; i < N; i++) {
    const j = bitRev[i];
    if (j > i) {
      const tmpR = re[i];
      const tmpI = im[i];
      re[i] = re[j];
      im[i] = im[j];
      re[j] = tmpR;
      im[j] = tmpI;
    }
  }

  // Butterfly stages
  for (let size = 2; size <= N; size *= 2) {
    const halfSize = size >> 1;
    const step = N / size; // twiddle stride

    for (let start = 0; start < N; start += size) {
      for (let k = 0; k < halfSize; k++) {
        const twIdx = k * step;
        const wr = twiddleRe[twIdx];
        const wi = twiddleIm[twIdx];

        const evenIdx = start + k;
        const oddIdx = start + k + halfSize;

        const tRe = wr * re[oddIdx] - wi * im[oddIdx];
        const tIm = wr * im[oddIdx] + wi * re[oddIdx];

        re[oddIdx] = re[evenIdx] - tRe;
        im[oddIdx] = im[evenIdx] - tIm;
        re[evenIdx] = re[evenIdx] + tRe;
        im[evenIdx] = im[evenIdx] + tIm;
      }
    }
  }
}

// ---- Main computation -----------------------------------------------------

function computeSpectrogram(pcmData: Float32Array, sampleRate: number): void {
  if (!tablesReady) {
    initTables();
  }

  const numSamples = pcmData.length;
  const timeFrames = Math.max(0, Math.floor((numSamples - FFT_SIZE) / HOP_SIZE) + 1);

  if (timeFrames === 0) {
    self.postMessage({ type: 'error', message: 'Audio too short for analysis (need at least 2048 samples)' });
    return;
  }

  const filters = buildMelFilterbank(sampleRate);

  // Allocate mel power buffer (first pass stores linear power)
  const melPower = new Float64Array(timeFrames * MEL_BANDS);

  // Reusable FFT buffers
  const re = new Float64Array(FFT_SIZE);
  const im = new Float64Array(FFT_SIZE);

  // Power spectrum buffer (only need first FFT_SIZE/2 + 1 bins)
  const fftBins = FFT_SIZE / 2 + 1;
  const powerSpectrum = new Float64Array(fftBins);

  let globalMaxPower = 0;
  const progressInterval = Math.max(1, Math.floor(timeFrames * 0.05));

  // ---- First pass: compute mel power values, track global max -------------

  for (let frame = 0; frame < timeFrames; frame++) {
    const offset = frame * HOP_SIZE;

    // Window and load into FFT buffers
    for (let i = 0; i < FFT_SIZE; i++) {
      re[i] = pcmData[offset + i] * hannWindow[i];
      im[i] = 0;
    }

    fft(re, im);

    // Power spectrum: |X(k)|^2
    for (let k = 0; k < fftBins; k++) {
      powerSpectrum[k] = re[k] * re[k] + im[k] * im[k];
    }

    // Apply mel filterbank
    const frameOffset = frame * MEL_BANDS;
    for (let m = 0; m < MEL_BANDS; m++) {
      const filter = filters[m];
      const startBin = filter.startBin;
      const w = filter.weights;
      let sum = 0;
      for (let i = 0; i < w.length; i++) {
        const bin = startBin + i;
        if (bin < fftBins) {
          sum += powerSpectrum[bin] * w[i];
        }
      }
      melPower[frameOffset + m] = sum;
      if (sum > globalMaxPower) {
        globalMaxPower = sum;
      }
    }

    // Progress updates
    if ((frame + 1) % progressInterval === 0 || frame === timeFrames - 1) {
      const percent = Math.round(((frame + 1) / timeFrames) * 100);
      self.postMessage({ type: 'progress', percent });
    }
  }

  // ---- Second pass: convert to dB relative to global max ------------------

  const data = new Float32Array(timeFrames * MEL_BANDS);
  const invMaxPower = globalMaxPower > 0 ? 1 / globalMaxPower : 1;

  for (let i = 0; i < melPower.length; i++) {
    let db = 10 * Math.log10(melPower[i] * invMaxPower + 1e-10);
    if (db < DB_FLOOR) {
      db = DB_FLOOR;
    }
    if (db > 0) {
      db = 0;
    }
    data[i] = db;
  }

  const durationSeconds = numSamples / sampleRate;
  const timeResolution = HOP_SIZE / sampleRate;

  self.postMessage(
    {
      type: 'complete',
      data,
      timeFrames,
      melBands: MEL_BANDS,
      durationSeconds,
      timeResolution,
      sampleRate,
    },
    [data.buffer] as unknown as Transferable[],
  );
}

// ---- Message handler ------------------------------------------------------

self.onmessage = (event: MessageEvent) => {
  const msg = event.data;

  if (msg.type === 'compute') {
    try {
      computeSpectrogram(msg.pcmData as Float32Array, msg.sampleRate as number);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      self.postMessage({ type: 'error', message });
    }
  }
};

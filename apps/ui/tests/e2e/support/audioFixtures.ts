import { promises as fs } from 'node:fs';
import path from 'node:path';

export const INLINE_SIZE_LIMIT = 20_971_520;

const DEFAULT_SAMPLE_RATE = 48_000;
const DEFAULT_CHANNELS = 2;
const DEFAULT_BITS_PER_SAMPLE = 16;
const DEFAULT_DURATION_SECONDS = 12;
const LARGE_SAMPLE_RATE = 96_000;
const LARGE_BITS_PER_SAMPLE = 32;
const DEFAULT_LARGE_TARGET_BYTES = INLINE_SIZE_LIMIT + 2 * 1024 * 1024;
const BPM = 120;
const BEAT_SECONDS = 60 / BPM;
const BAR_SECONDS = BEAT_SECONDS * 4;
const EIGHTH_SECONDS = BEAT_SECONDS / 2;
const MAX_AMPLITUDE = 0.92;

const BASS_PATTERN = [45, 45, 48, 45, 53, 53, 50, 48, 45, 45, 52, 50, 53, 52, 48, 45];
const MELODY_PATTERN = [69, 72, 76, 74, 72, 69, 67, 64, 69, 71, 72, 76, 74, 72, 69, 67];
const CHORD_PATTERN = [
  [57, 60, 64],
  [53, 57, 60],
  [48, 52, 55],
  [55, 59, 62],
];

export interface AudioFixtureSummary {
  filePath: string;
  byteLength: number;
  durationSeconds: number;
  sampleRate: number;
  channels: number;
  bitsPerSample: number;
}

interface WavRenderOptions {
  durationSeconds: number;
  sampleRate: number;
  channels: number;
  bitsPerSample: 16 | 32;
}

function midiToFrequency(midi: number): number {
  return 440 * Math.pow(2, (midi - 69) / 12);
}

function clampSample(value: number): number {
  return Math.max(-MAX_AMPLITUDE, Math.min(MAX_AMPLITUDE, value));
}

function renderFrame(timeSeconds: number): readonly [number, number] {
  const beatIndex = Math.floor(timeSeconds / BEAT_SECONDS);
  const beatTime = timeSeconds - beatIndex * BEAT_SECONDS;
  const barIndex = Math.floor(timeSeconds / BAR_SECONDS);
  const barTime = timeSeconds - barIndex * BAR_SECONDS;
  const eighthIndex = Math.floor(timeSeconds / EIGHTH_SECONDS);
  const eighthTime = timeSeconds - eighthIndex * EIGHTH_SECONDS;

  const kickEnvelope = beatTime < 0.2 ? Math.exp(-beatTime * 28) : 0;
  const kick = kickEnvelope * Math.sin(2 * Math.PI * (48 + 52 * Math.exp(-beatTime * 14)) * beatTime);

  const bassMidi = BASS_PATTERN[beatIndex % BASS_PATTERN.length] ?? 45;
  const bassFrequency = midiToFrequency(bassMidi);
  const bassEnvelope = beatTime < 0.42 ? Math.sin(Math.min(beatTime / 0.05, 1) * Math.PI * 0.5) * Math.exp(-beatTime * 1.6) : 0;
  const bass =
    bassEnvelope *
    (Math.sin(2 * Math.PI * bassFrequency * beatTime) + 0.22 * Math.sin(2 * Math.PI * bassFrequency * 2 * beatTime));

  const chord = CHORD_PATTERN[barIndex % CHORD_PATTERN.length] ?? CHORD_PATTERN[0];
  const chordEnvelope = barTime < 1.85 ? Math.sin(Math.min(barTime / 0.12, 1) * Math.PI * 0.5) * Math.exp(-barTime * 0.22) : 0;
  const sidechainDuck = 1 - 0.48 * Math.exp(-beatTime * 18);
  const chordLeft =
    chordEnvelope *
    sidechainDuck *
    (0.45 * Math.sin(2 * Math.PI * midiToFrequency(chord[0]!) * timeSeconds) +
      0.34 * Math.sin(2 * Math.PI * midiToFrequency(chord[1]!) * timeSeconds + 0.11) +
      0.24 * Math.sin(2 * Math.PI * midiToFrequency(chord[2]!) * timeSeconds + 0.21));
  const chordRight =
    chordEnvelope *
    sidechainDuck *
    (0.31 * Math.sin(2 * Math.PI * midiToFrequency(chord[0]!) * timeSeconds + 0.09) +
      0.39 * Math.sin(2 * Math.PI * midiToFrequency(chord[1]!) * timeSeconds + 0.18) +
      0.29 * Math.sin(2 * Math.PI * midiToFrequency(chord[2]!) * timeSeconds + 0.33));

  const melodyMidi = MELODY_PATTERN[eighthIndex % MELODY_PATTERN.length] ?? 69;
  const melodyFrequency = midiToFrequency(melodyMidi);
  const melodyEnvelope = eighthTime < 0.26 ? Math.sin(Math.min(eighthTime / 0.04, 1) * Math.PI * 0.5) * Math.exp(-eighthTime * 2.6) : 0;
  const melodyCore =
    melodyEnvelope *
    (Math.sin(2 * Math.PI * melodyFrequency * eighthTime) +
      0.18 * Math.sin(2 * Math.PI * melodyFrequency * 2 * eighthTime));

  const hatGate = eighthIndex % 2 === 1 && eighthTime < 0.08 ? Math.exp(-eighthTime * 52) : 0;
  const hatCore =
    hatGate *
    (0.7 * Math.sin(2 * Math.PI * 7_200 * eighthTime) +
      0.4 * Math.sin(2 * Math.PI * 9_600 * eighthTime) +
      0.2 * Math.sin(2 * Math.PI * 11_800 * eighthTime));

  const left = clampSample(0.45 * kick + 0.22 * bass + 0.12 * chordLeft + 0.08 * melodyCore + 0.04 * hatCore);
  const right = clampSample(0.45 * kick + 0.22 * bass + 0.12 * chordRight + 0.1 * melodyCore + 0.05 * hatCore);

  return [left, right] as const;
}

function renderWaveBuffer(options: WavRenderOptions): Buffer {
  const bytesPerSample = options.bitsPerSample / 8;
  const blockAlign = options.channels * bytesPerSample;
  const frameCount = Math.ceil(options.durationSeconds * options.sampleRate);
  const dataBytes = frameCount * blockAlign;
  const byteRate = options.sampleRate * blockAlign;
  const buffer = Buffer.allocUnsafe(44 + dataBytes);

  buffer.write('RIFF', 0);
  buffer.writeUInt32LE(36 + dataBytes, 4);
  buffer.write('WAVE', 8);
  buffer.write('fmt ', 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(options.channels, 22);
  buffer.writeUInt32LE(options.sampleRate, 24);
  buffer.writeUInt32LE(byteRate, 28);
  buffer.writeUInt16LE(blockAlign, 32);
  buffer.writeUInt16LE(options.bitsPerSample, 34);
  buffer.write('data', 36);
  buffer.writeUInt32LE(dataBytes, 40);

  let offset = 44;
  for (let frameIndex = 0; frameIndex < frameCount; frameIndex += 1) {
    const timeSeconds = frameIndex / options.sampleRate;
    const [left, right] = renderFrame(timeSeconds);
    const samples = options.channels === 1 ? [clampSample((left + right) * 0.5)] : [left, right];

    for (const sample of samples) {
      if (options.bitsPerSample === 16) {
        buffer.writeInt16LE(Math.round(sample * 0x7fff), offset);
      } else {
        buffer.writeInt32LE(Math.round(sample * 0x7fffffff), offset);
      }
      offset += bytesPerSample;
    }
  }

  return buffer;
}

async function writeWaveFixture(filePath: string, options: WavRenderOptions): Promise<AudioFixtureSummary> {
  const buffer = renderWaveBuffer(options);
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, buffer);

  return {
    filePath,
    byteLength: buffer.byteLength,
    durationSeconds: Math.ceil(options.durationSeconds * options.sampleRate) / options.sampleRate,
    sampleRate: options.sampleRate,
    channels: options.channels,
    bitsPerSample: options.bitsPerSample,
  };
}

export async function writeMusicalReferenceWav(filePath: string): Promise<AudioFixtureSummary> {
  return writeWaveFixture(filePath, {
    durationSeconds: DEFAULT_DURATION_SECONDS,
    sampleRate: DEFAULT_SAMPLE_RATE,
    channels: DEFAULT_CHANNELS,
    bitsPerSample: DEFAULT_BITS_PER_SAMPLE,
  });
}

export async function writeOversizedMusicalWav(
  filePath: string,
  targetBytes = DEFAULT_LARGE_TARGET_BYTES,
): Promise<AudioFixtureSummary> {
  const blockAlign = DEFAULT_CHANNELS * (LARGE_BITS_PER_SAMPLE / 8);
  const dataBytes = Math.ceil(Math.max(targetBytes - 44, 1) / blockAlign) * blockAlign;
  const durationSeconds = dataBytes / (LARGE_SAMPLE_RATE * blockAlign);

  return writeWaveFixture(filePath, {
    durationSeconds,
    sampleRate: LARGE_SAMPLE_RATE,
    channels: DEFAULT_CHANNELS,
    bitsPerSample: LARGE_BITS_PER_SAMPLE,
  });
}

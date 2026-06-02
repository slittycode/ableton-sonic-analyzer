import { describe, expect, it } from "vitest";
import { decodeWavPcm } from "../../../src/services/browserLoudness/wavDecoder";

function writeStr(dv: DataView, offset: number, str: string): void {
  for (let i = 0; i < str.length; i++) dv.setUint8(offset + i, str.charCodeAt(i));
}

interface BuildWavOptions {
  sampleRate?: number;
  channels?: number;
  bits?: number;
  format?: number; // 1 = PCM int, 3 = IEEE float
  samples: number[]; // interleaved, in [-1, 1]
  extraChunk?: { id: string; bytes: number }; // injected between fmt and data
}

function buildWav(opts: BuildWavOptions): ArrayBuffer {
  const { sampleRate = 48000, channels = 1, bits = 16, format = 1, samples, extraChunk } = opts;
  const bytesPerSample = bits / 8;
  const dataLen = samples.length * bytesPerSample;
  const extraLen = extraChunk ? 8 + extraChunk.bytes : 0;
  const buf = new ArrayBuffer(44 + extraLen + dataLen);
  const dv = new DataView(buf);

  writeStr(dv, 0, "RIFF");
  dv.setUint32(4, 36 + extraLen + dataLen, true);
  writeStr(dv, 8, "WAVE");

  writeStr(dv, 12, "fmt ");
  dv.setUint32(16, 16, true);
  dv.setUint16(20, format, true);
  dv.setUint16(22, channels, true);
  dv.setUint32(24, sampleRate, true);
  dv.setUint32(28, sampleRate * channels * bytesPerSample, true);
  dv.setUint16(32, channels * bytesPerSample, true);
  dv.setUint16(34, bits, true);

  let offset = 36;
  if (extraChunk) {
    writeStr(dv, offset, extraChunk.id.padEnd(4));
    dv.setUint32(offset + 4, extraChunk.bytes, true);
    offset += 8 + extraChunk.bytes;
  }

  writeStr(dv, offset, "data");
  dv.setUint32(offset + 4, dataLen, true);
  let p = offset + 8;
  for (const s of samples) {
    if (format === 3) {
      dv.setFloat32(p, s, true);
      p += 4;
    } else if (bits === 16) {
      dv.setInt16(p, Math.round(s * 32767), true);
      p += 2;
    } else if (bits === 24) {
      const v = Math.round(s * 8388607);
      dv.setUint8(p, v & 0xff);
      dv.setUint8(p + 1, (v >> 8) & 0xff);
      dv.setUint8(p + 2, (v >> 16) & 0xff);
      p += 3;
    } else if (bits === 32) {
      dv.setInt32(p, Math.round(s * 2147483647), true);
      p += 4;
    }
  }
  return buf;
}

// WAVE_FORMAT_EXTENSIBLE has a 40-byte fmt chunk whose real format tag lives in
// the first 2 bytes of the SubFormat GUID at body+24 (so chunkSize must be >=26
// for the decoder to read it). buildWav can't express that, so build it here.
function buildExtensibleWav(opts: {
  sampleRate?: number;
  channels?: number;
  bits?: number;
  subFormat?: number; // real format in the GUID: 1 = PCM int, 3 = IEEE float
  samples: number[];
}): ArrayBuffer {
  const { sampleRate = 48000, channels = 1, bits = 16, subFormat = 1, samples } = opts;
  const bytesPerSample = bits / 8;
  const dataLen = samples.length * bytesPerSample;
  const fmtBody = 40;
  const buf = new ArrayBuffer(12 + 8 + fmtBody + 8 + dataLen);
  const dv = new DataView(buf);

  writeStr(dv, 0, "RIFF");
  dv.setUint32(4, 4 + (8 + fmtBody) + (8 + dataLen), true);
  writeStr(dv, 8, "WAVE");

  writeStr(dv, 12, "fmt ");
  dv.setUint32(16, fmtBody, true);
  dv.setUint16(20, 0xfffe, true); // WAVE_FORMAT_EXTENSIBLE
  dv.setUint16(22, channels, true);
  dv.setUint32(24, sampleRate, true);
  dv.setUint32(28, sampleRate * channels * bytesPerSample, true);
  dv.setUint16(32, channels * bytesPerSample, true);
  dv.setUint16(34, bits, true);
  dv.setUint16(36, 22, true); // cbSize
  dv.setUint16(38, bits, true); // wValidBitsPerSample
  dv.setUint32(40, 0, true); // dwChannelMask
  dv.setUint16(44, subFormat, true); // SubFormat GUID — first 2 bytes carry the real tag

  const dataHeader = 12 + 8 + fmtBody;
  writeStr(dv, dataHeader, "data");
  dv.setUint32(dataHeader + 4, dataLen, true);
  let p = dataHeader + 8;
  for (const s of samples) {
    dv.setInt16(p, Math.round(s * 32767), true);
    p += 2;
  }
  return buf;
}

describe("decodeWavPcm", () => {
  it("decodes 16-bit PCM mono at the native rate", () => {
    const wav = buildWav({ sampleRate: 44100, channels: 1, bits: 16, samples: [0, 0.5, -0.5, 1.0] });
    const out = decodeWavPcm(wav);
    expect(out).not.toBeNull();
    expect(out!.channels).toBe(1);
    expect(out!.sampleRate).toBe(44100);
    expect(out!.samples.length).toBe(4);
    expect(out!.samples[1]).toBeCloseTo(0.5, 2);
    expect(out!.samples[2]).toBeCloseTo(-0.5, 2);
  });

  it("decodes 32-bit float stereo as interleaved samples", () => {
    const wav = buildWav({
      sampleRate: 48000,
      channels: 2,
      bits: 32,
      format: 3,
      samples: [0.1, -0.1, 0.2, -0.2],
    });
    const out = decodeWavPcm(wav);
    expect(out!.channels).toBe(2);
    expect(out!.sampleRate).toBe(48000);
    expect(out!.samples.length).toBe(4);
    expect(out!.samples[0]).toBeCloseTo(0.1, 5);
    expect(out!.samples[3]).toBeCloseTo(-0.2, 5);
  });

  it("decodes 24-bit PCM", () => {
    const wav = buildWav({ channels: 1, bits: 24, samples: [0.25, -0.75] });
    const out = decodeWavPcm(wav);
    expect(out!.samples[0]).toBeCloseTo(0.25, 3);
    expect(out!.samples[1]).toBeCloseTo(-0.75, 3);
  });

  it("walks past an unknown chunk to find data", () => {
    const wav = buildWav({
      channels: 1,
      bits: 16,
      samples: [0.5, -0.5],
      extraChunk: { id: "LIST", bytes: 6 },
    });
    const out = decodeWavPcm(wav);
    expect(out).not.toBeNull();
    expect(out!.samples.length).toBe(2);
    expect(out!.samples[0]).toBeCloseTo(0.5, 2);
  });

  it("decodes WAVE_FORMAT_EXTENSIBLE by reading the SubFormat tag (chunkSize 40 >= 26)", () => {
    const wav = buildExtensibleWav({ channels: 1, bits: 16, subFormat: 1, samples: [0.5, -0.5, 0.25] });
    const out = decodeWavPcm(wav);
    expect(out).not.toBeNull();
    expect(out!.channels).toBe(1);
    expect(out!.sampleRate).toBe(48000);
    expect(out!.samples.length).toBe(3);
    expect(out!.samples[0]).toBeCloseTo(0.5, 2);
    expect(out!.samples[1]).toBeCloseTo(-0.5, 2);
  });

  it("returns null for non-WAV / truncated buffers", () => {
    expect(decodeWavPcm(new ArrayBuffer(10))).toBeNull();
    const notRiff = new ArrayBuffer(64);
    writeStr(new DataView(notRiff), 0, "OggS");
    expect(decodeWavPcm(notRiff)).toBeNull();
  });
});

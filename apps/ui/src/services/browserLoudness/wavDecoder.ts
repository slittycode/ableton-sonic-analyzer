/**
 * Minimal WAV PCM decoder for the browser loudness readout (WS3c).
 *
 * Why not `AudioContext.decodeAudioData`? It resamples to the context rate,
 * which alters the signal and breaks the ±0.1 LU EBU conformance the WASM core
 * is held to (the loudness-spectro-wasm README warns about exactly this). So we
 * read the PCM directly at the file's native rate and hand interleaved f32 to
 * the measurer.
 *
 * Scope: uncompressed WAV only (PCM int 16/24/32 and IEEE float32, including
 * WAVE_FORMAT_EXTENSIBLE). FLAC — ASA's primary format — has no decoder here;
 * the panel reports "WAV only" for anything else rather than guessing. This is
 * the documented WS3c limitation until a FLAC decoder lands.
 */

export interface DecodedWavPcm {
  /** Interleaved f32 PCM in [-1, 1] ([L,R,L,R,...] for stereo). */
  samples: Float32Array;
  channels: number;
  sampleRate: number;
}

const WAVE_FORMAT_PCM = 0x0001;
const WAVE_FORMAT_IEEE_FLOAT = 0x0003;
const WAVE_FORMAT_EXTENSIBLE = 0xfffe;

function readFourCC(view: DataView, offset: number): string {
  return String.fromCharCode(
    view.getUint8(offset),
    view.getUint8(offset + 1),
    view.getUint8(offset + 2),
    view.getUint8(offset + 3),
  );
}

/**
 * Decode an uncompressed WAV ArrayBuffer to interleaved f32 at its native rate.
 * Returns null when the buffer is not a WAV we can decode (caller shows the
 * "WAV only" state rather than throwing into the UI).
 */
export function decodeWavPcm(buffer: ArrayBuffer): DecodedWavPcm | null {
  if (buffer.byteLength < 44) return null;
  const view = new DataView(buffer);

  if (readFourCC(view, 0) !== "RIFF" || readFourCC(view, 8) !== "WAVE") {
    return null;
  }

  let formatTag = 0;
  let channels = 0;
  let sampleRate = 0;
  let bitsPerSample = 0;
  let dataOffset = -1;
  let dataLength = 0;

  // Walk the chunk list (fmt / data may be separated by LIST, fact, etc.).
  let offset = 12;
  while (offset + 8 <= buffer.byteLength) {
    const chunkId = readFourCC(view, offset);
    const chunkSize = view.getUint32(offset + 4, true);
    const body = offset + 8;

    if (chunkId === "fmt ") {
      formatTag = view.getUint16(body, true);
      channels = view.getUint16(body + 2, true);
      sampleRate = view.getUint32(body + 4, true);
      bitsPerSample = view.getUint16(body + 14, true);
      if (formatTag === WAVE_FORMAT_EXTENSIBLE && chunkSize >= 26) {
        // Real format lives in the first 2 bytes of the SubFormat GUID, which
        // starts at body+24 — so the chunk must hold at least bytes 24-25.
        formatTag = view.getUint16(body + 24, true);
      }
    } else if (chunkId === "data") {
      dataOffset = body;
      // Clamp to the actual buffer (some encoders over-declare the size).
      dataLength = Math.min(chunkSize, buffer.byteLength - body);
    }

    // Chunks are word-aligned: an odd size carries a trailing pad byte.
    offset = body + chunkSize + (chunkSize % 2);
  }

  if (
    channels <= 0 ||
    sampleRate <= 0 ||
    dataOffset < 0 ||
    dataLength <= 0 ||
    (formatTag !== WAVE_FORMAT_PCM && formatTag !== WAVE_FORMAT_IEEE_FLOAT)
  ) {
    return null;
  }

  const bytesPerSample = bitsPerSample / 8;
  if (![2, 3, 4].includes(bytesPerSample)) return null;
  const totalSamples = Math.floor(dataLength / bytesPerSample);
  const out = new Float32Array(totalSamples);

  if (formatTag === WAVE_FORMAT_IEEE_FLOAT && bytesPerSample === 4) {
    for (let i = 0; i < totalSamples; i++) {
      out[i] = view.getFloat32(dataOffset + i * 4, true);
    }
  } else if (bytesPerSample === 2) {
    for (let i = 0; i < totalSamples; i++) {
      out[i] = view.getInt16(dataOffset + i * 2, true) / 32768;
    }
  } else if (bytesPerSample === 3) {
    for (let i = 0; i < totalSamples; i++) {
      const p = dataOffset + i * 3;
      // Little-endian 24-bit, sign-extended.
      let v = view.getUint8(p) | (view.getUint8(p + 1) << 8) | (view.getUint8(p + 2) << 16);
      if (v & 0x800000) v |= ~0xffffff;
      out[i] = v / 8388608;
    }
  } else if (bytesPerSample === 4) {
    for (let i = 0; i < totalSamples; i++) {
      out[i] = view.getInt32(dataOffset + i * 4, true) / 2147483648;
    }
  }

  return { samples: out, channels, sampleRate };
}

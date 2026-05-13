import { describe, expect, it } from 'vitest';

import {
  getAudioMimeTypeOrDefault,
  isSupportedAudioFile,
  resolveAudioMimeType,
} from '../../src/services/audioFile';

describe('resolveAudioMimeType', () => {
  it('returns the provided MIME type when it is an audio type', () => {
    expect(resolveAudioMimeType({ name: 'song.mp3', type: 'audio/mpeg' })).toBe('audio/mpeg');
  });

  it('trims and lowercases the MIME type before returning it', () => {
    expect(resolveAudioMimeType({ name: 'song.mp3', type: '  AUDIO/MPEG  ' })).toBe('audio/mpeg');
  });

  it('passes through unfamiliar audio MIME subtypes without enforcing an allowlist', () => {
    // Documents current behavior: any audio/* MIME is trusted so the browser-reported value wins.
    expect(resolveAudioMimeType({ name: 'song.opus', type: 'audio/x-opus' })).toBe('audio/x-opus');
  });

  it('falls back to the filename extension when the MIME type is missing', () => {
    expect(resolveAudioMimeType({ name: 'song.wav' })).toBe('audio/wav');
  });

  it('falls back to the filename extension when the MIME type is null', () => {
    expect(resolveAudioMimeType({ name: 'song.flac', type: null })).toBe('audio/flac');
  });

  it('falls back to the filename extension when the MIME type is empty whitespace', () => {
    expect(resolveAudioMimeType({ name: 'song.mp3', type: '   ' })).toBe('audio/mpeg');
  });

  it('falls back to the filename extension when the MIME type is non-audio', () => {
    expect(resolveAudioMimeType({ name: 'song.mp3', type: 'application/octet-stream' })).toBe(
      'audio/mpeg',
    );
  });

  it('maps .aiff to audio/aiff', () => {
    expect(resolveAudioMimeType({ name: 'song.aiff' })).toBe('audio/aiff');
  });

  it('maps the shorter .aif extension to audio/aiff', () => {
    expect(resolveAudioMimeType({ name: 'song.aif' })).toBe('audio/aiff');
  });

  it('matches extensions case-insensitively', () => {
    expect(resolveAudioMimeType({ name: 'SONG.MP3' })).toBe('audio/mpeg');
    expect(resolveAudioMimeType({ name: 'Track.Wav' })).toBe('audio/wav');
  });

  it('trims surrounding whitespace from the filename before matching', () => {
    expect(resolveAudioMimeType({ name: '  song.flac  ' })).toBe('audio/flac');
  });

  it('returns null when neither the MIME type nor the extension is recognized', () => {
    expect(resolveAudioMimeType({ name: 'notes.txt', type: 'text/plain' })).toBeNull();
  });

  it('returns null when the file has no extension and no MIME type', () => {
    expect(resolveAudioMimeType({ name: 'mystery' })).toBeNull();
  });

  it('returns null for an empty filename with no MIME type', () => {
    expect(resolveAudioMimeType({ name: '' })).toBeNull();
  });

  it('ignores extensions appearing mid-filename (must be the suffix)', () => {
    expect(resolveAudioMimeType({ name: 'song.mp3.backup' })).toBeNull();
  });
});

describe('isSupportedAudioFile', () => {
  it('returns true for files with recognized audio extensions', () => {
    expect(isSupportedAudioFile({ name: 'song.mp3' })).toBe(true);
    expect(isSupportedAudioFile({ name: 'song.wav' })).toBe(true);
    expect(isSupportedAudioFile({ name: 'song.flac' })).toBe(true);
    expect(isSupportedAudioFile({ name: 'song.aiff' })).toBe(true);
    expect(isSupportedAudioFile({ name: 'song.aif' })).toBe(true);
  });

  it('returns true when the MIME type is audio even if the extension is not in the map', () => {
    expect(isSupportedAudioFile({ name: 'capture.ogg', type: 'audio/ogg' })).toBe(true);
  });

  it('returns false for non-audio files', () => {
    expect(isSupportedAudioFile({ name: 'image.png', type: 'image/png' })).toBe(false);
    expect(isSupportedAudioFile({ name: 'notes.txt' })).toBe(false);
  });
});

describe('getAudioMimeTypeOrDefault', () => {
  it('returns the resolved MIME type when one can be determined', () => {
    expect(getAudioMimeTypeOrDefault({ name: 'song.wav' })).toBe('audio/wav');
  });

  it('returns the default fallback (audio/mpeg) when the file cannot be classified', () => {
    expect(getAudioMimeTypeOrDefault({ name: 'mystery' })).toBe('audio/mpeg');
  });

  it('honors a caller-supplied fallback when the file cannot be classified', () => {
    expect(getAudioMimeTypeOrDefault({ name: 'mystery' }, 'application/octet-stream')).toBe(
      'application/octet-stream',
    );
  });

  it('prefers the resolved MIME type over the caller-supplied fallback', () => {
    expect(getAudioMimeTypeOrDefault({ name: 'song.flac' }, 'application/octet-stream')).toBe(
      'audio/flac',
    );
  });
});

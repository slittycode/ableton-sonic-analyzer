const AUDIO_EXTENSION_MIME_TYPES: Record<string, string> = {
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav',
  '.flac': 'audio/flac',
  '.aiff': 'audio/aiff',
  '.aif': 'audio/aiff',
};

interface AudioLikeFile {
  name: string;
  type?: string | null;
}

function normalizeMimeType(type?: string | null): string {
  return typeof type === 'string' ? type.trim().toLowerCase() : '';
}

function inferMimeTypeFromExtension(name: string): string | null {
  const normalizedName = name.trim().toLowerCase();
  const matchingExtension = Object.keys(AUDIO_EXTENSION_MIME_TYPES).find((extension) =>
    normalizedName.endsWith(extension),
  );

  return matchingExtension ? AUDIO_EXTENSION_MIME_TYPES[matchingExtension] : null;
}

export function resolveAudioMimeType(file: AudioLikeFile): string | null {
  const normalizedMimeType = normalizeMimeType(file.type);
  if (normalizedMimeType.startsWith('audio/')) {
    return normalizedMimeType;
  }

  return inferMimeTypeFromExtension(file.name);
}

export function isSupportedAudioFile(file: AudioLikeFile): boolean {
  return resolveAudioMimeType(file) !== null;
}

export function getAudioMimeTypeOrDefault(file: AudioLikeFile, fallback = 'audio/mpeg'): string {
  return resolveAudioMimeType(file) ?? fallback;
}

export type TextRole =
  | 'page-title'
  | 'section-title'
  | 'subsection-title'
  | 'item-title'
  | 'eyebrow'
  | 'body'
  | 'meta'
  | 'value';

export type DisplayTextCase = 'none' | 'title' | 'eyebrow';

const DISPLAY_ACRONYMS = new Set([
  'AI',
  'API',
  'BPM',
  'CPU',
  'DSP',
  'EQ',
  'FX',
  'JSON',
  'LUFS',
  'MIDI',
  'UI',
]);

export function getTextRoleClassName(role: TextRole): string {
  return `text-role-${role}`;
}

function formatWord(word: string): string {
  const normalizedUpper = word.toUpperCase();
  if (DISPLAY_ACRONYMS.has(normalizedUpper)) return normalizedUpper;
  if (/\d/.test(word)) return normalizedUpper;

  const normalizedLower = word.toLowerCase();
  return `${normalizedLower.charAt(0).toUpperCase()}${normalizedLower.slice(1)}`;
}

export function toDisplayTitle(text: string): string {
  const normalized = text.trim();
  if (!normalized) return '';

  const tokens = normalized.match(/[A-Za-z0-9]+|[^A-Za-z0-9]+/g);
  if (!tokens) return normalized;

  return tokens
    .map((token) => (/^[A-Za-z0-9]+$/.test(token) ? formatWord(token) : token))
    .join('');
}

export function formatDisplayText(text: string, displayCase: DisplayTextCase = 'none'): string {
  if (displayCase === 'title') {
    return toDisplayTitle(text);
  }
  if (displayCase === 'eyebrow') {
    return toDisplayTitle(text).toUpperCase();
  }
  return text.trim();
}

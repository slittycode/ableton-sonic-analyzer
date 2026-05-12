// Render-state derivation for the Session Musician note-draft block (Block A).
//
// The precedence-ordered table here is load-bearing. The first rule that
// matches wins — in particular:
//   - Rule 1: an explicit user opt-out trumps every cached transcription.
//     Stale notes must never sneak back onto the screen after the toggle is
//     turned off.
//   - Rule 5: a legacy method (anything not torchcrepe) wins over the
//     full-mix-fallback flag. Re-analyzing the audio is the actionable fix,
//     so the "legacy run" framing should override the fallback framing even
//     when both apply.
//
// The function is pure so it can be unit-tested as a matrix.

import type { TranscriptionDetail } from '../../types';

export type PitchNoteMode = 'stem_notes' | 'off' | null;

export type NoteDraftRenderState =
  | 'stem-aware'
  | 'full-mix-fallback'
  | 'legacy'
  | 'ran-with-no-result'
  | 'requested-but-unavailable'
  | 'absent';

const TORCHCREPE_METHODS: ReadonlySet<string> = new Set([
  'torchcrepe',
  'torchcrepe-viterbi',
]);

export function isLegacyTranscriptionMethod(
  method: string | null | undefined,
): boolean {
  if (typeof method !== 'string') return false;
  const normalized = method.trim().toLowerCase();
  if (!normalized) return false;
  return !TORCHCREPE_METHODS.has(normalized);
}

export function deriveNoteDraftRenderState(
  transcriptionDetail: TranscriptionDetail | null | undefined,
  pitchNoteMode: PitchNoteMode,
): NoteDraftRenderState {
  // Rule 1: explicit opt-out wins, regardless of any stale cached data.
  if (pitchNoteMode === 'off') return 'absent';

  // Rules 2 & 3: missing payload.
  if (!transcriptionDetail) {
    return pitchNoteMode === 'stem_notes' ? 'requested-but-unavailable' : 'absent';
  }

  // Rule 4: payload arrived but contains no actual notes. Use the array length
  // — not the cosmetic noteCount field — because only real notes can be drawn
  // or exported.
  if (!Array.isArray(transcriptionDetail.notes) || transcriptionDetail.notes.length === 0) {
    return 'ran-with-no-result';
  }

  // Rule 5: legacy method wins over fallback. A re-analyze action is what the
  // user actually needs, and "Legacy run" copy is more useful than "Fallback".
  if (isLegacyTranscriptionMethod(transcriptionDetail.transcriptionMethod)) {
    return 'legacy';
  }

  // Rule 6: stem separation didn't run cleanly; pitch came from the full mix.
  if (transcriptionDetail.fullMixFallback === true) {
    return 'full-mix-fallback';
  }

  // Rule 7: nominal stem-aware torchcrepe output.
  return 'stem-aware';
}

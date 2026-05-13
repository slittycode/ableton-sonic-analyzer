// Centralised visibility check for the Gemini stem listening notes section.
//
// Used by AnalysisResults.tsx for three things at once:
//   1. Whether to include the "Stem Notes" entry in the StickyNav
//   2. Whether to render <StemListeningNotesPanel>
//   3. Whether to pass hasStemListeningNotes={true} to <SessionMusicianPanel>
//      so the off-state banner can cross-link to the section
//
// The render gate counts a Gemini envelope as having content when ANY of the
// three populatable fields is non-empty — Gemini sometimes returns a top-line
// summary without per-stem cards, or only uncertainty flags, and the panel
// should still surface what's there.

import type { StemSummaryResult } from '../../types';

export function hasStemListeningNotesContent(
  stemSummary: StemSummaryResult | null | undefined,
): boolean {
  if (!stemSummary) return false;
  if (Array.isArray(stemSummary.stems) && stemSummary.stems.length > 0) return true;
  if (typeof stemSummary.summary === 'string' && stemSummary.summary.trim().length > 0) {
    return true;
  }
  if (
    Array.isArray(stemSummary.uncertaintyFlags) &&
    stemSummary.uncertaintyFlags.length > 0
  ) {
    return true;
  }
  return false;
}

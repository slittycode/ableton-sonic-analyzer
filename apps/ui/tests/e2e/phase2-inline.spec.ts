import { expect, test } from '@playwright/test';

import { INLINE_SIZE_LIMIT } from './support/audioFixtures';
import {
  DEFAULT_PHASE2_MODEL,
  expectNoCommonConnectivityErrors,
  getFileSizeBytes,
  gotoUploadPage,
  openDiagnosticLog,
  resolveLiveTrackPath,
  selectPhase2Model,
  setToggle,
  startAnalysisAndCaptureRunId,
  uploadAudioFile,
  waitForAnalysisResults,
  waitForEstimate,
  waitForRunToReachTerminalState,
} from './support/liveHarness';

test('live Gemini inline path uses inlineData without Files API traffic', async ({ page }) => {
  test.setTimeout(8 * 60 * 1_000);

  const trackPath = resolveLiveTrackPath();
  const trackSizeBytes = await getFileSizeBytes(trackPath);
  test.skip(trackSizeBytes > INLINE_SIZE_LIMIT, 'TEST_FLAC_PATH exceeds the inline upload threshold.');

  await gotoUploadPage(page);
  await uploadAudioFile(page, trackPath);
  await setToggle(page, 'PITCH/NOTE EXTRACTION', false);
  await setToggle(page, 'AI INTERPRETATION', true);
  await selectPhase2Model(page, DEFAULT_PHASE2_MODEL);

  await waitForEstimate(page);
  const runId = await startAnalysisAndCaptureRunId(page);
  const finalSnapshot = await waitForRunToReachTerminalState(runId, { timeoutMs: 8 * 60 * 1_000 });

  await waitForAnalysisResults(page);
  await openDiagnosticLog(page);
  await expectNoCommonConnectivityErrors(page);

  expect(finalSnapshot.stages.measurement.status).toBe('completed');
  expect(finalSnapshot.stages.pitchNoteTranslation.status).toBe('not_requested');
  expect(finalSnapshot.stages.interpretation.status).toBe('completed');

  const timings = ((finalSnapshot.stages.interpretation.diagnostics ?? {}) as Record<string, unknown>)
    .timings as Record<string, unknown> | undefined;
  const flagsUsed = Array.isArray(timings?.flagsUsed) ? timings.flagsUsed : [];
  expect(flagsUsed).toEqual(expect.arrayContaining(['inline']));
  expect(flagsUsed).not.toEqual(expect.arrayContaining(['files-api']));

  await expect(page.getByText(/Phase 2 advisory complete\./)).toBeVisible({ timeout: 8 * 60 * 1_000 });
  await expect(page.getByText(/Phase 2 advisory complete\. Upload:/)).toHaveCount(0);
  await expect(page.getByText(/Draft — Phase 2 output is incomplete or unavailable\./)).toHaveCount(0);
});

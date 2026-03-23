import { expect, test } from '@playwright/test';

import { INLINE_SIZE_LIMIT, writeOversizedMusicalWav } from './support/audioFixtures';
import {
  DEFAULT_PHASE2_MODEL,
  expectNoCommonConnectivityErrors,
  gotoUploadPage,
  openDiagnosticLog,
  selectPhase2Model,
  setToggle,
  startAnalysisAndCaptureRunId,
  uploadAudioFile,
  waitForAnalysisResults,
  waitForEstimate,
  waitForRunToReachTerminalState,
} from './support/liveHarness';

test('live Gemini Files API path uploads, generates, and deletes large audio', async ({ page }, testInfo) => {
  test.setTimeout(12 * 60 * 1_000);

  const fixturePath = testInfo.outputPath('phase2-files-api-reference.wav');
  const fixture = await writeOversizedMusicalWav(fixturePath);
  expect(fixture.byteLength).toBeGreaterThan(INLINE_SIZE_LIMIT);

  await gotoUploadPage(page);
  await uploadAudioFile(page, fixturePath);
  await setToggle(page, 'PITCH/NOTE EXTRACTION', false);
  await setToggle(page, 'AI INTERPRETATION', true);
  await selectPhase2Model(page, DEFAULT_PHASE2_MODEL);

  await waitForEstimate(page, 60_000);
  const runId = await startAnalysisAndCaptureRunId(page);
  const finalSnapshot = await waitForRunToReachTerminalState(runId, { timeoutMs: 12 * 60 * 1_000 });

  await waitForAnalysisResults(page, 12 * 60 * 1_000);
  await openDiagnosticLog(page);
  await expectNoCommonConnectivityErrors(page);

  expect(finalSnapshot.stages.measurement.status).toBe('completed');
  expect(finalSnapshot.stages.pitchNoteTranslation.status).toBe('not_requested');
  expect(finalSnapshot.stages.interpretation.status).toBe('completed');

  const timings = ((finalSnapshot.stages.interpretation.diagnostics ?? {}) as Record<string, unknown>)
    .timings as Record<string, unknown> | undefined;
  const flagsUsed = Array.isArray(timings?.flagsUsed) ? timings.flagsUsed : [];
  expect(flagsUsed).toEqual(expect.arrayContaining(['files-api']));
  expect(flagsUsed).not.toEqual(expect.arrayContaining(['inline']));

  await expect(page.getByText(/Phase 2 advisory complete\. Upload: \d+ms, Generate: \d+ms/)).toBeVisible({
    timeout: 12 * 60 * 1_000,
  });
});

import { expect, test } from '@playwright/test';

import { INLINE_SIZE_LIMIT, writeOversizedMusicalWav } from './support/audioFixtures';
import {
  DEFAULT_PHASE2_MODEL,
  expectNoCommonConnectivityErrors,
  gotoUploadPage,
  observeGeminiTraffic,
  openDiagnosticLog,
  selectPhase2Model,
  setToggle,
  startAnalysis,
  uploadAudioFile,
  waitForAnalysisResults,
  waitForEstimate,
} from './support/liveHarness';

test('live Gemini Files API path uploads, generates, and deletes large audio', async ({ page }, testInfo) => {
  test.setTimeout(12 * 60 * 1_000);

  const fixturePath = testInfo.outputPath('phase2-files-api-reference.wav');
  const fixture = await writeOversizedMusicalWav(fixturePath);
  expect(fixture.byteLength).toBeGreaterThan(INLINE_SIZE_LIMIT);

  const geminiTraffic = observeGeminiTraffic(page);

  await gotoUploadPage(page);
  await uploadAudioFile(page, fixturePath);
  await setToggle(page, 'AI INTERPRETATION', true);
  await selectPhase2Model(page, DEFAULT_PHASE2_MODEL);

  await waitForEstimate(page, 60_000);
  const uploadRequestPromise = geminiTraffic.waitForUploadRequest(12 * 60 * 1_000);
  const generateRequestPromise = geminiTraffic.waitForGenerateRequest(12 * 60 * 1_000);
  const deleteRequestPromise = geminiTraffic.waitForDeleteRequest(12 * 60 * 1_000);

  await startAnalysis(page);

  const uploadRequest = await uploadRequestPromise;
  const generateRequest = await generateRequestPromise;
  const deleteRequest = await deleteRequestPromise;
  const generateBody = generateRequest.postData() ?? '';

  expect(uploadRequest.method()).toBe('POST');
  expect(generateRequest.method()).toBe('POST');
  expect(deleteRequest.method()).toBe('DELETE');
  expect(generateBody).toContain('"fileData"');
  expect(generateBody).toContain('"fileUri"');
  expect(generateBody).not.toContain('"inlineData"');

  const uploadIndex = geminiTraffic.requestOrder.indexOf('upload');
  const generateIndex = geminiTraffic.requestOrder.indexOf('generate');
  const deleteIndex = geminiTraffic.requestOrder.indexOf('delete');
  expect(uploadIndex).toBeGreaterThanOrEqual(0);
  expect(generateIndex).toBeGreaterThan(uploadIndex);
  expect(deleteIndex).toBeGreaterThan(generateIndex);

  await waitForAnalysisResults(page, 12 * 60 * 1_000);
  await openDiagnosticLog(page);
  await expectNoCommonConnectivityErrors(page);
  await expect(page.getByText(/Phase 2 advisory complete\. Upload: \d+ms, Generate: \d+ms/)).toBeVisible({
    timeout: 12 * 60 * 1_000,
  });
});

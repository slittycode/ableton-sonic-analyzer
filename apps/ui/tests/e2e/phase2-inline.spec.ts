import { expect, test } from '@playwright/test';

import { INLINE_SIZE_LIMIT, writeMusicalReferenceWav } from './support/audioFixtures';
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

test('live Gemini inline path uses inlineData without Files API traffic', async ({ page }, testInfo) => {
  test.setTimeout(8 * 60 * 1_000);

  const fixturePath = testInfo.outputPath('phase2-inline-reference.wav');
  const fixture = await writeMusicalReferenceWav(fixturePath);
  expect(fixture.byteLength).toBeLessThanOrEqual(INLINE_SIZE_LIMIT);

  const geminiTraffic = observeGeminiTraffic(page);

  await gotoUploadPage(page);
  await uploadAudioFile(page, fixturePath);
  await setToggle(page, 'PHASE 2 ADVISORY', true);
  await selectPhase2Model(page, DEFAULT_PHASE2_MODEL);

  await waitForEstimate(page);
  const generateRequestPromise = geminiTraffic.waitForGenerateRequest();
  await startAnalysis(page);

  const generateRequest = await generateRequestPromise;
  const generateBody = generateRequest.postData() ?? '';

  expect(generateBody).toContain('"inlineData"');
  expect(generateBody).not.toContain('"fileData"');

  await waitForAnalysisResults(page);
  await openDiagnosticLog(page);
  await expectNoCommonConnectivityErrors(page);

  expect(geminiTraffic.requestOrder).toContain('generate');
  expect(geminiTraffic.requestOrder).not.toContain('upload');
  expect(geminiTraffic.requestOrder).not.toContain('delete');

  await expect(page.getByText(/Phase 2 advisory complete\./)).toBeVisible({ timeout: 8 * 60 * 1_000 });
  await expect(page.getByText(/Phase 2 advisory complete\. Upload:/)).toHaveCount(0);
  await expect(page.getByText(/Draft — Phase 2 output is incomplete or unavailable\./)).toHaveCount(0);
});

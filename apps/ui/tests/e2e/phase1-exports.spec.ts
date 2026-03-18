import { expect, test } from '@playwright/test';

import { writeMusicalReferenceWav } from './support/audioFixtures';
import {
  downloadTextArtifact,
  expectNoCommonConnectivityErrors,
  gotoUploadPage,
  openDiagnosticLog,
  setToggle,
  startAnalysis,
  uploadAudioFile,
  waitForAnalysisResults,
  waitForEstimate,
} from './support/liveHarness';

test('live phase 1 estimate, analysis, and exports succeed against the local backend', async ({ page }, testInfo) => {
  test.setTimeout(6 * 60 * 1_000);

  const fixturePath = testInfo.outputPath('phase1-reference.wav');
  await writeMusicalReferenceWav(fixturePath);

  await gotoUploadPage(page);
  await uploadAudioFile(page, fixturePath);
  await setToggle(page, 'AI INTERPRETATION', false);

  await waitForEstimate(page);
  await startAnalysis(page);
  await waitForAnalysisResults(page);
  await openDiagnosticLog(page);
  await expectNoCommonConnectivityErrors(page);
  await expect(page.getByText(/Local DSP analysis complete/i)).toBeVisible({ timeout: 45_000 });

  const jsonArtifact = await downloadTextArtifact(page, /JSON_DATA/i);
  expect(jsonArtifact.download.suggestedFilename()).toBe('track-analysis.json');
  const parsedJson = JSON.parse(jsonArtifact.text) as {
    phase1?: unknown;
    phase2?: unknown;
    exportedAt?: unknown;
  };
  expect(parsedJson.phase1).toBeTruthy();
  expect(parsedJson).toHaveProperty('phase2');
  expect(typeof parsedJson.exportedAt).toBe('string');

  const markdownArtifact = await downloadTextArtifact(page, /REPORT_MD/i);
  expect(markdownArtifact.download.suggestedFilename()).toBe('track-analysis.md');
  expect(markdownArtifact.text).toContain('# Track Analysis Report');
  expect(markdownArtifact.text).toContain('## Phase 1 Metadata');
  expect(markdownArtifact.text).toContain('## Phase 2');
});

import { expect, test } from '@playwright/test';
import { promises as fs } from 'node:fs';

import { writeMusicalReferenceWav } from './support/audioFixtures';
import {
  expectNoCommonConnectivityErrors,
  gotoUploadPage,
  setToggle,
  startAnalysis,
  uploadAudioFile,
  waitForAnalysisResults,
  waitForEstimate,
} from './support/liveHarness';

test('live transcription and separation render Session Musician and export MIDI', async ({ page }, testInfo) => {
  test.setTimeout(12 * 60 * 1_000);

  const fixturePath = testInfo.outputPath('session-musician-reference.wav');
  await writeMusicalReferenceWav(fixturePath);

  await gotoUploadPage(page);
  await uploadAudioFile(page, fixturePath);
  await setToggle(page, 'MIDI TRANSCRIPTION', true);
  await setToggle(page, 'STEM SEPARATION', true);
  await setToggle(page, 'PHASE 2 ADVISORY', false);

  await waitForEstimate(page, 60_000);
  await startAnalysis(page);
  await waitForAnalysisResults(page, 12 * 60 * 1_000);
  await expectNoCommonConnectivityErrors(page);

  await expect(page.getByText('SESSION MUSICIAN').first()).toBeVisible({ timeout: 12 * 60 * 1_000 });
  await expect(page.getByRole('button', { name: /Download \.mid/i })).toBeEnabled();

  const polyphonicToggle = page.getByRole('button', { name: 'POLYPHONIC' });
  const monophonicToggle = page.getByRole('button', { name: 'MONOPHONIC' });
  if (await polyphonicToggle.count()) {
    await polyphonicToggle.click();
  }
  if (await monophonicToggle.count()) {
    await monophonicToggle.click();
  }

  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: /Download \.mid/i }).click();
  const download = await downloadPromise;
  const downloadPath = await download.path();

  expect(download.suggestedFilename()).toBe('track-analysis.mid');
  expect(downloadPath).not.toBeNull();

  const stats = await fs.stat(downloadPath!);
  expect(stats.size).toBeGreaterThan(0);
});

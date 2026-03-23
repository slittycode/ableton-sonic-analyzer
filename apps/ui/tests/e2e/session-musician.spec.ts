import { expect, test } from '@playwright/test';

import {
  downloadBinaryArtifact,
  expectNoCommonConnectivityErrors,
  gotoUploadPage,
  listRunArtifacts,
  resolveLiveTrackPath,
  setToggle,
  startAnalysisAndCaptureRunId,
  uploadAudioFile,
  waitForAnalysisResults,
  waitForEstimate,
  waitForRunToReachTerminalState,
} from './support/liveHarness';

test('live artifact review generates spectral enhancements and keeps Session Musician exportable', async ({ page }) => {
  test.setTimeout(12 * 60 * 1_000);
  const trackPath = resolveLiveTrackPath();

  await gotoUploadPage(page);
  await uploadAudioFile(page, trackPath);
  await setToggle(page, 'PITCH/NOTE EXTRACTION', true);
  await setToggle(page, 'AI INTERPRETATION', false);

  await waitForEstimate(page, 60_000);
  const runId = await startAnalysisAndCaptureRunId(page);
  const finalSnapshot = await waitForRunToReachTerminalState(runId, { timeoutMs: 12 * 60 * 1_000 });
  await waitForAnalysisResults(page, 12 * 60 * 1_000);
  await expectNoCommonConnectivityErrors(page);

  expect(finalSnapshot.stages.measurement.status).toBe('completed');
  expect(finalSnapshot.stages.pitchNoteTranslation.status).toBe('completed');
  await expect(page.getByTestId('session-musician-panel')).toBeVisible({ timeout: 12 * 60 * 1_000 });
  await expect(page.getByTestId('spectral-section')).toBeVisible();

  const initialArtifacts = await listRunArtifacts(runId);
  const initialKinds = new Set(initialArtifacts.map((artifact) => String(artifact.kind)));
  expect(initialKinds).toContain('source_audio');
  expect(initialKinds).toContain('spectrogram_mel');
  expect(initialKinds).toContain('spectral_time_series');

  const toolbar = page.getByTestId('spectral-enhancements-toolbar');
  await expect(toolbar).toBeVisible();

  const chromaButton = toolbar.getByRole('button', { name: /Generate Chroma/i });
  if (await chromaButton.count()) {
    await chromaButton.click();
  }
  await expect(toolbar.getByText(/Chroma ✓/)).toBeVisible({ timeout: 60_000 });

  const onsetButton = toolbar.getByRole('button', { name: /Generate Onset/i });
  if (await onsetButton.count()) {
    await onsetButton.click();
  }
  await expect(toolbar.getByText(/Onset ✓/)).toBeVisible({ timeout: 60_000 });

  await expect(page.getByTestId('spectral-visualizations-panel')).toBeVisible({ timeout: 60_000 });

  const artifactsAfterEnhancements = await listRunArtifacts(runId);
  const enhancementKinds = new Set(artifactsAfterEnhancements.map((artifact) => String(artifact.kind)));
  expect(enhancementKinds).toContain('chroma_interactive');
  expect(enhancementKinds).toContain('spectrogram_chroma');
  expect(enhancementKinds).toContain('onset_strength');
  expect(enhancementKinds).toContain('spectrogram_onset');

  const midiArtifact = await downloadBinaryArtifact(page, /Download \.mid/i);
  expect(midiArtifact.download.suggestedFilename()).toBe('track-analysis.mid');
  expect(midiArtifact.sizeBytes).toBeGreaterThan(0);
});

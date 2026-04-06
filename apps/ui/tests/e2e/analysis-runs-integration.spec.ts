import { expect, test } from '@playwright/test';

import { writeMusicalReferenceWav } from './support/audioFixtures';
import {
  downloadBinaryArtifact,
  expectNoCommonConnectivityErrors,
  gotoUploadPage,
  listRunArtifacts,
  openDiagnosticLog,
  setToggle,
  startAnalysisAndCaptureRunId,
  uploadAudioFile,
  waitForAnalysisResults,
  waitForEstimate,
  waitForRunToReachTerminalState,
} from './support/liveHarness';

test('local integration flow uses canonical analysis-runs routes without Gemini credentials', async ({
  page,
}, testInfo) => {
  test.setTimeout(12 * 60 * 1_000);

  const fixturePath = testInfo.outputPath('analysis-runs-integration-reference.wav');
  const fixture = await writeMusicalReferenceWav(fixturePath);
  expect(fixture.byteLength).toBeGreaterThan(0);

  await gotoUploadPage(page);
  await expect(page.getByTestId('phase2-status-inline')).toHaveText('INTERPRETATION CONFIG OFF');

  const estimateResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      response.url().includes('/api/analysis-runs/estimate'),
    { timeout: 60_000 },
  );

  await uploadAudioFile(page, fixturePath);

  const estimateResponse = await estimateResponsePromise;
  expect(estimateResponse.ok()).toBeTruthy();

  await setToggle(page, 'PITCH/NOTE TRANSLATION', true);
  await waitForEstimate(page, 60_000);

  const runId = await startAnalysisAndCaptureRunId(page);
  const finalSnapshot = await waitForRunToReachTerminalState(runId, { timeoutMs: 12 * 60 * 1_000 });

  await waitForAnalysisResults(page, 12 * 60 * 1_000);
  await openDiagnosticLog(page);
  await expectNoCommonConnectivityErrors(page);

  await expect(page.getByText(/Measurement complete\./i)).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText(/Pitch\/Note Translation complete\./i)).toBeVisible({ timeout: 45_000 });
  await expect(page.getByTestId('analysis-results-root')).toBeVisible();
  await expect(page.getByTestId('measurement-dashboard')).toBeVisible();
  await expect(page.getByTestId('session-musician-panel')).toBeVisible();

  expect(finalSnapshot.runId).toBe(runId);
  expect(finalSnapshot.stages.measurement.status).toBe('completed');
  expect(finalSnapshot.stages.pitchNoteTranslation.status).toBe('completed');
  expect(finalSnapshot.stages.interpretation.status).toBe('not_requested');
  expect(finalSnapshot.artifacts.sourceAudio.filename).toBeTruthy();
  expect(finalSnapshot.artifacts.spectral?.spectrograms.length ?? 0).toBeGreaterThan(0);
  expect(finalSnapshot.artifacts.spectral?.timeSeries).toBeTruthy();

  const artifacts = await listRunArtifacts(runId);
  const artifactKinds = new Set(artifacts.map((artifact) => String(artifact.kind)));
  expect(artifactKinds).toContain('source_audio');
  expect(artifactKinds).toContain('spectrogram_mel');
  expect(artifactKinds).toContain('spectral_time_series');

  const midiArtifact = await downloadBinaryArtifact(page, /Download \.mid/i);
  expect(midiArtifact.download.suggestedFilename()).toBe('track-analysis.mid');
  expect(midiArtifact.sizeBytes).toBeGreaterThan(0);
});

import { expect, test } from '@playwright/test';

import {
  downloadBinaryArtifact,
  downloadTextArtifact,
  expectNoCommonConnectivityErrors,
  fetchAnalysisRun,
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

test('live golden path uploads the external track and reviews the full analysis output', async ({ page }) => {
  test.setTimeout(12 * 60 * 1_000);
  const trackPath = resolveLiveTrackPath();

  await gotoUploadPage(page);
  await uploadAudioFile(page, trackPath);
  await setToggle(page, 'PITCH/NOTE EXTRACTION', true);
  await setToggle(page, 'AI INTERPRETATION', true);
  await selectPhase2Model(page);

  await waitForEstimate(page, 60_000);
  const runId = await startAnalysisAndCaptureRunId(page);
  const finalSnapshot = await waitForRunToReachTerminalState(runId, { timeoutMs: 12 * 60 * 1_000 });

  await waitForAnalysisResults(page, 12 * 60 * 1_000);
  await openDiagnosticLog(page);
  await expectNoCommonConnectivityErrors(page);
  await expect(page.getByText(/Measurement complete\./i)).toBeVisible({ timeout: 45_000 });
  await expect(page.getByTestId('measurement-dashboard')).toBeVisible();
  await expect(page.getByTestId('interpretation-panel')).toBeVisible();
  await expect(page.getByTestId('session-musician-panel')).toBeVisible();

  expect(finalSnapshot.runId).toBe(runId);
  expect(finalSnapshot.stages.measurement.status).toBe('completed');
  expect(finalSnapshot.stages.pitchNoteTranslation.status).toBe('completed');
  expect(finalSnapshot.stages.interpretation.status).toBe('completed');
  expect(finalSnapshot.artifacts.spectral?.spectrograms.length ?? 0).toBeGreaterThan(0);
  expect(finalSnapshot.artifacts.spectral?.timeSeries).toBeTruthy();

  const jsonArtifact = await downloadTextArtifact(page, /JSON_DATA/i);
  expect(jsonArtifact.download.suggestedFilename()).toBe('track-analysis.json');
  const parsedJson = JSON.parse(jsonArtifact.text) as {
    phase1?: unknown;
    phase2?: unknown;
    exportedAt?: unknown;
  };
  expect(parsedJson.phase1).toBeTruthy();
  expect(parsedJson.phase2).toBeTruthy();
  expect(typeof parsedJson.exportedAt).toBe('string');

  const markdownArtifact = await downloadTextArtifact(page, /REPORT_MD/i);
  expect(markdownArtifact.download.suggestedFilename()).toBe('track-analysis.md');
  expect(markdownArtifact.text).toContain('# Track Analysis Report');
  expect(markdownArtifact.text).toContain('## Phase 1 Metadata');
  expect(markdownArtifact.text).toContain('## Phase 2');

  const midiArtifact = await downloadBinaryArtifact(page, /Download \.mid/i);
  expect(midiArtifact.download.suggestedFilename()).toBe('track-analysis.mid');
  expect(midiArtifact.sizeBytes).toBeGreaterThan(0);

  const latestSnapshot = await fetchAnalysisRun(runId);
  expect(latestSnapshot.stages.interpretation.status).toBe('completed');
});

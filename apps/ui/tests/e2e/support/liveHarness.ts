import { expect, type Download, type Page, type Request } from '@playwright/test';
import { promises as fs } from 'node:fs';

import type { AnalysisRunSnapshot, AnalysisStageStatus } from '../../../src/types';

export const DEFAULT_PHASE2_MODEL = 'gemini-2.5-flash';
export const DEFAULT_ANALYSIS_TIMEOUT_MS = 8 * 60 * 1_000;
const DEFAULT_API_BASE_URL = process.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8100';

function normalizeBaseUrl(apiBaseUrl = DEFAULT_API_BASE_URL): string {
  return apiBaseUrl.replace(/\/+$/, '');
}

function isTerminalStatus(status: AnalysisStageStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'interrupted' || status === 'not_requested';
}

function isRunTerminal(snapshot: AnalysisRunSnapshot): boolean {
  return (
    isTerminalStatus(snapshot.stages.measurement.status) &&
    isTerminalStatus(snapshot.stages.pitchNoteTranslation.status) &&
    isTerminalStatus(snapshot.stages.interpretation.status)
  );
}

export function resolveLiveTrackPath(): string {
  const trackPath = process.env.TEST_FLAC_PATH?.trim();
  if (!trackPath) {
    throw new Error('TEST_FLAC_PATH must be set before running the live E2E suite.');
  }
  return trackPath;
}

export async function getFileSizeBytes(filePath: string): Promise<number> {
  const stats = await fs.stat(filePath);
  return stats.size;
}

export function isGeminiUploadRequest(url: string, method: string): boolean {
  return method === 'POST' && url.includes('generativelanguage.googleapis.com') && url.includes('/upload/') && url.includes('/files');
}

export function isGeminiGenerateRequest(url: string, method: string): boolean {
  return method === 'POST' && url.includes('generativelanguage.googleapis.com') && url.includes(':generateContent');
}

export function isGeminiDeleteRequest(url: string, method: string): boolean {
  return method === 'DELETE' && url.includes('generativelanguage.googleapis.com') && url.includes('/files/');
}

export async function gotoUploadPage(page: Page): Promise<void> {
  await page.goto('/', { waitUntil: 'networkidle' });
}

export async function uploadAudioFile(page: Page, filePath: string): Promise<void> {
  await page.setInputFiles('#audio-upload', filePath);
}

export async function setToggle(page: Page, label: string, checked: boolean): Promise<void> {
  const checkbox = page.getByLabel(label);
  await expect(checkbox).toBeVisible();
  if (checked) {
    await checkbox.check();
  } else {
    await checkbox.uncheck();
  }
}

export async function selectPhase2Model(page: Page, modelName = DEFAULT_PHASE2_MODEL): Promise<void> {
  const desktop = page.getByTestId('phase2-model-desktop');
  if (await desktop.isVisible().catch(() => false)) {
    await desktop.selectOption(modelName);
    await expect(desktop).toHaveValue(modelName);
    return;
  }

  const mobile = page.getByTestId('phase2-model-mobile');
  await expect(mobile).toBeVisible();
  await mobile.selectOption(modelName);
  await expect(mobile).toHaveValue(modelName);
}

export async function waitForEstimate(page: Page, timeout = 45_000): Promise<void> {
  await expect(page.getByText('Estimated local analysis')).toBeVisible({ timeout });
  await expect(page.getByText(/^\d+s-\d+s$/)).toBeVisible({ timeout });
}

export async function startAnalysis(page: Page): Promise<void> {
  const analyzeButton = page.getByRole('button', { name: /Run Analysis/i });
  await expect(analyzeButton).toBeVisible();
  await expect(analyzeButton).toBeEnabled();
  await analyzeButton.click();
}

export async function startAnalysisAndCaptureRunId(page: Page): Promise<string> {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      response.url().includes('/api/analysis-runs'),
    { timeout: DEFAULT_ANALYSIS_TIMEOUT_MS },
  );

  await startAnalysis(page);

  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  const payload = (await response.json()) as { runId?: unknown };
  expect(typeof payload.runId).toBe('string');
  return payload.runId as string;
}

export async function waitForAnalysisResults(
  page: Page,
  timeout = DEFAULT_ANALYSIS_TIMEOUT_MS,
): Promise<void> {
  await expect(page.getByTestId('analysis-results-root')).toBeVisible({ timeout });
  await expect(page.getByText('System Diagnostics')).toBeVisible({ timeout });
}

export async function openDiagnosticLog(page: Page): Promise<void> {
  const toggle = page.getByRole('button', { name: /Toggle diagnostic log/i });
  await expect(toggle).toBeVisible();
  const expanded = await toggle.getAttribute('aria-expanded');
  if (expanded !== 'true') {
    await toggle.click();
  }
}

export async function expectNoCommonConnectivityErrors(page: Page): Promise<void> {
  await expect(page.getByText(/Cannot reach DSP backend/i)).toHaveCount(0);
  await expect(page.getByText(/Unexpected DSP backend error/i)).toHaveCount(0);
  await expect(page.getByText(/Phase 2 advisory is disabled or missing an API key/i)).toHaveCount(0);
}

export async function downloadTextArtifact(
  page: Page,
  buttonName: string | RegExp,
): Promise<{ download: Download; text: string }> {
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: buttonName }).click();
  const download = await downloadPromise;
  const downloadPath = await download.path();
  if (!downloadPath) {
    throw new Error(`Download path was unavailable for ${download.suggestedFilename()}.`);
  }

  return {
    download,
    text: await fs.readFile(downloadPath, 'utf8'),
  };
}

export async function downloadBinaryArtifact(
  page: Page,
  buttonName: string | RegExp,
): Promise<{ download: Download; downloadPath: string; sizeBytes: number }> {
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: buttonName }).click();
  const download = await downloadPromise;
  const downloadPath = await download.path();
  if (!downloadPath) {
    throw new Error(`Download path was unavailable for ${download.suggestedFilename()}.`);
  }

  const stats = await fs.stat(downloadPath);
  return { download, downloadPath, sizeBytes: stats.size };
}

export async function fetchAnalysisRun(
  runId: string,
  apiBaseUrl = DEFAULT_API_BASE_URL,
): Promise<AnalysisRunSnapshot> {
  const response = await fetch(`${normalizeBaseUrl(apiBaseUrl)}/api/analysis-runs/${encodeURIComponent(runId)}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch analysis run ${runId}: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as AnalysisRunSnapshot;
}

export async function listRunArtifacts(
  runId: string,
  kind = '',
  apiBaseUrl = DEFAULT_API_BASE_URL,
): Promise<Array<Record<string, unknown>>> {
  const query = kind ? `?kind=${encodeURIComponent(kind)}` : '';
  const response = await fetch(
    `${normalizeBaseUrl(apiBaseUrl)}/api/analysis-runs/${encodeURIComponent(runId)}/artifacts${query}`,
  );
  if (!response.ok) {
    throw new Error(`Failed to list artifacts for run ${runId}: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as Array<Record<string, unknown>>;
}

export async function waitForRunToReachTerminalState(
  runId: string,
  options?: {
    apiBaseUrl?: string;
    timeoutMs?: number;
    pollIntervalMs?: number;
  },
): Promise<AnalysisRunSnapshot> {
  const timeoutMs = options?.timeoutMs ?? DEFAULT_ANALYSIS_TIMEOUT_MS;
  const pollIntervalMs = options?.pollIntervalMs ?? 1_000;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const snapshot = await fetchAnalysisRun(runId, options?.apiBaseUrl);
    if (isRunTerminal(snapshot)) {
      return snapshot;
    }
    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
  }

  throw new Error(`Run ${runId} did not reach a terminal state within ${timeoutMs}ms.`);
}

export function observeGeminiTraffic(page: Page): {
  requestOrder: string[];
  waitForUploadRequest: (timeout?: number) => Promise<Request>;
  waitForGenerateRequest: (timeout?: number) => Promise<Request>;
  waitForDeleteRequest: (timeout?: number) => Promise<Request>;
} {
  const requestOrder: string[] = [];

  page.on('request', (request) => {
    const url = request.url();
    const method = request.method();
    if (isGeminiUploadRequest(url, method)) requestOrder.push('upload');
    if (isGeminiGenerateRequest(url, method)) requestOrder.push('generate');
    if (isGeminiDeleteRequest(url, method)) requestOrder.push('delete');
  });

  return {
    requestOrder,
    waitForUploadRequest: (timeout = DEFAULT_ANALYSIS_TIMEOUT_MS) =>
      page.waitForRequest((request) => isGeminiUploadRequest(request.url(), request.method()), { timeout }),
    waitForGenerateRequest: (timeout = DEFAULT_ANALYSIS_TIMEOUT_MS) =>
      page.waitForRequest((request) => isGeminiGenerateRequest(request.url(), request.method()), { timeout }),
    waitForDeleteRequest: (timeout = DEFAULT_ANALYSIS_TIMEOUT_MS) =>
      page.waitForRequest((request) => isGeminiDeleteRequest(request.url(), request.method()), { timeout }),
  };
}

import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { parseBackendAnalyzeResponse } from "../../src/services/backendPhase1Client";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const backendBaseUrl = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function backendSupportsPhase1Routes(baseUrl: string): Promise<boolean> {
  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), 2_500);
  try {
    const response = await fetch(`${baseUrl.replace(/\/+$/, "")}/openapi.json`, {
      signal: controller.signal,
    });
    if (!response.ok) return false;

    const spec = (await response.json()) as { paths?: Record<string, unknown> };
    return Boolean(spec.paths?.["/api/analyze"] && spec.paths?.["/api/analyze/estimate"]);
  } catch {
    return false;
  } finally {
    clearTimeout(timeoutHandle);
  }
}

function resolveLiveFixturePath(): string {
  const configuredFlacPath = process.env.TEST_FLAC_PATH;
  if (configuredFlacPath) {
    const resolvedFlacPath = path.resolve(configuredFlacPath);
    if (fs.existsSync(resolvedFlacPath)) {
      return resolvedFlacPath;
    }
  }

  return path.resolve(testDir, "./fixtures/silence.wav");
}

test("live backend phase1 renders results without connectivity errors", async ({ page }) => {
  test.skip(
    !(await backendSupportsPhase1Routes(backendBaseUrl)),
    `Backend at ${backendBaseUrl} does not expose /api/analyze and /api/analyze/estimate.`,
  );

  await page.goto("/", { waitUntil: "networkidle" });

  const fixturePath = resolveLiveFixturePath();
  await page.setInputFiles("#audio-upload", fixturePath);

  const analyzeButton = page.getByRole("button", { name: /Initiate Analysis/i });
  await expect(analyzeButton).toBeVisible();

  const analyzeResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/api/analyze") && response.request().method() === "POST",
    { timeout: 35_000 },
  );

  await analyzeButton.click();

  const analyzeResponse = await analyzeResponsePromise;
  const payload = await analyzeResponse.json();
  const parsedResponse = parseBackendAnalyzeResponse(payload);
  const diagnostics = parsedResponse.diagnostics;

  expect(analyzeResponse.ok()).toBeTruthy();
  expect(parsedResponse.requestId).not.toBe("unknown");
  expect(diagnostics).toBeTruthy();

  if (diagnostics) {
    expect(diagnostics.backendDurationMs).toBeGreaterThan(0);

    if (typeof diagnostics.timeoutSeconds === "number") {
      expect(diagnostics.backendDurationMs).toBeLessThan(diagnostics.timeoutSeconds * 1_000);
    }

    if (typeof diagnostics.estimatedHighMs === "number" && typeof diagnostics.timeoutSeconds === "number") {
      expect(diagnostics.timeoutSeconds * 1_000).toBeGreaterThan(diagnostics.estimatedHighMs);
    }
  }

  await expect(page.getByText("Analysis Results")).toBeVisible({ timeout: 35_000 });
  await expect(page.getByText("System Diagnostics")).toBeVisible();
  await expect(page.getByText(/Cannot reach DSP backend/i)).toHaveCount(0);
});

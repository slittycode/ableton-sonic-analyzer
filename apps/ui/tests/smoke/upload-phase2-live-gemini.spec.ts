import { test, expect } from "@playwright/test";
import { promises as fs } from "node:fs";

const INLINE_SIZE_LIMIT = 104_857_600;
const LIVE_GEMINI_TARGET_BYTES = INLINE_SIZE_LIMIT + 2 * 1024 * 1024;
const backendBaseUrl = process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8100";
const liveGeminiEnabled = process.env.RUN_GEMINI_LIVE_SMOKE === "true";
const geminiPhase2Enabled = process.env.VITE_ENABLE_PHASE2_GEMINI === "true";

async function backendSupportsPhase2Route(baseUrl: string): Promise<boolean> {
  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), 2_500);
  try {
    const response = await fetch(`${baseUrl.replace(/\/+$/, "")}/openapi.json`, {
      signal: controller.signal,
    });
    if (!response.ok) return false;

    const spec = (await response.json()) as { paths?: Record<string, unknown> };
    return Boolean(
      spec.paths?.["/api/analysis-runs/estimate"] &&
      spec.paths?.["/api/analysis-runs"] &&
      spec.paths?.["/api/analysis-runs/{run_id}"],
    );
  } catch {
    return false;
  } finally {
    clearTimeout(timeoutHandle);
  }
}

async function writeOversizedSilentWav(filePath: string, targetBytes = LIVE_GEMINI_TARGET_BYTES): Promise<number> {
  const sampleRate = 48_000;
  const channels = 2;
  const bitsPerSample = 16;
  const bytesPerSample = bitsPerSample / 8;
  const blockAlign = channels * bytesPerSample;
  const byteRate = sampleRate * blockAlign;
  const dataBytes = Math.ceil(targetBytes / blockAlign) * blockAlign;
  const buffer = Buffer.alloc(44 + dataBytes);

  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + dataBytes, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(channels, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(byteRate, 28);
  buffer.writeUInt16LE(blockAlign, 32);
  buffer.writeUInt16LE(bitsPerSample, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(dataBytes, 40);

  await fs.writeFile(filePath, buffer);
  return buffer.byteLength;
}

test("live Gemini Files API path: large audio triggers server-side upload+generate+delete sequence", async ({ page }, testInfo) => {
  test.setTimeout(8 * 60 * 1_000);
  test.skip(!liveGeminiEnabled, "RUN_GEMINI_LIVE_SMOKE must be true to run the live Gemini smoke test.");
  test.skip(!geminiPhase2Enabled, "VITE_ENABLE_PHASE2_GEMINI must be true for the live Gemini smoke test.");
  test.skip(
    !(await backendSupportsPhase2Route(backendBaseUrl)),
    `Backend at ${backendBaseUrl} must expose /api/analysis-runs/estimate, /api/analysis-runs, and /api/analysis-runs/{run_id}.`,
  );

  const largeWavPath = testInfo.outputPath("live-gemini-large-silence.wav");
  const fileSizeBytes = await writeOversizedSilentWav(largeWavPath);
  expect(fileSizeBytes).toBeGreaterThan(INLINE_SIZE_LIMIT);

  const createRunResponsePromise = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().includes("/api/analysis-runs"),
    { timeout: 8 * 60 * 1_000 },
  );

  try {
    await page.goto("/", { waitUntil: "networkidle" });

    const modelSelect = page.getByRole("combobox");
    await expect(modelSelect).toBeVisible();
    await expect(modelSelect).toBeEnabled();
    await page.setInputFiles("#audio-upload", largeWavPath);
    await modelSelect.selectOption("gemini-2.5-flash");
    await expect(modelSelect).toHaveValue("gemini-2.5-flash");
    await expect(page.getByText("PHASE 2 OFF")).toHaveCount(0);

    await page.getByRole("button", { name: /Run Analysis/i }).click();

    const createRunResponse = await createRunResponsePromise;
    expect(createRunResponse.ok()).toBeTruthy();
    const payload = (await createRunResponse.json()) as { runId?: string };
    expect(payload.runId).toBeTruthy();

    await expect(page.getByText("Analysis Results")).toBeVisible({ timeout: 8 * 60 * 1_000 });
    await expect(page.getByText("System Diagnostics")).toBeVisible();

    // Files API path returns a message with upload+generate timings.
    // Inline path returns "Phase 2 advisory complete." without timing breakdown.
    await expect(page.getByText(/Phase 2 advisory complete\. Upload: \d+ms, Generate: \d+ms/)).toBeVisible({
      timeout: 8 * 60 * 1_000,
    });

    const snapshotResponse = await fetch(`${backendBaseUrl.replace(/\/+$/, "")}/api/analysis-runs/${payload.runId}`);
    expect(snapshotResponse.ok).toBeTruthy();
    const snapshot = (await snapshotResponse.json()) as {
      stages: {
        interpretation: {
          status: string;
          diagnostics?: {
            timings?: {
              flagsUsed?: string[];
            };
          };
        };
      };
    };

    expect(snapshot.stages.interpretation.status).toBe("completed");
    expect(snapshot.stages.interpretation.diagnostics?.timings?.flagsUsed ?? []).toContain("files-api");
    await expect(page.getByText(/Unexpected DSP backend error/i)).toHaveCount(0);
    await expect(page.getByText(/Phase 2 advisory is disabled or missing an API key/i)).toHaveCount(0);
  } finally {
    await fs.rm(largeWavPath, { force: true });
  }
});

import { test, expect } from "@playwright/test";
import { promises as fs } from "node:fs";

const INLINE_SIZE_LIMIT = 20_971_520;
const LIVE_GEMINI_TARGET_BYTES = 25 * 1024 * 1024;
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
      spec.paths?.["/api/analyze"] &&
      spec.paths?.["/api/analyze/estimate"] &&
      spec.paths?.["/api/phase2"],
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
    `Backend at ${backendBaseUrl} must expose /api/analyze, /api/analyze/estimate, and /api/phase2.`,
  );

  const largeWavPath = testInfo.outputPath("live-gemini-large-silence.wav");
  const fileSizeBytes = await writeOversizedSilentWav(largeWavPath);
  expect(fileSizeBytes).toBeGreaterThan(INLINE_SIZE_LIMIT);

  // Monitor the browser→backend phase2 request (Gemini calls happen server-side now).
  const phase2RequestPromise = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().includes("/api/phase2"),
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

    await page.getByRole("button", { name: /Initiate Analysis/i }).click();

    const phase2Request = await phase2RequestPromise;
    expect(phase2Request.method()).toBe("POST");
    expect(phase2Request.url()).toContain("/api/phase2");

    await expect(page.getByText("Analysis Results")).toBeVisible({ timeout: 8 * 60 * 1_000 });
    await expect(page.getByText("System Diagnostics")).toBeVisible();

    // Files API path returns a message with upload+generate timings.
    // Inline path returns "Phase 2 advisory complete." without timing breakdown.
    await expect(page.getByText(/Phase 2 advisory complete\. Upload: \d+ms, Generate: \d+ms/)).toBeVisible({
      timeout: 8 * 60 * 1_000,
    });
    await expect(page.getByText(/Unexpected DSP backend error/i)).toHaveCount(0);
    await expect(page.getByText(/Phase 2 advisory is disabled or missing an API key/i)).toHaveCount(0);
  } finally {
    await fs.rm(largeWavPath, { force: true });
  }
});

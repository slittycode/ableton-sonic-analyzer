import { test, expect } from "@playwright/test";
import { promises as fs } from "node:fs";

const INLINE_SIZE_LIMIT = 20_971_520;
const LIVE_GEMINI_TARGET_BYTES = 25 * 1024 * 1024;
const backendBaseUrl = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const liveGeminiEnabled = process.env.RUN_GEMINI_LIVE_SMOKE === "true";
const geminiPhase2Enabled = process.env.VITE_ENABLE_PHASE2_GEMINI === "true";
const geminiApiKey = process.env.VITE_GEMINI_API_KEY?.trim() ?? "";

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

function isGeminiUploadRequest(url: string, method: string): boolean {
  return method === "POST" && url.includes("generativelanguage.googleapis.com") && url.includes("/upload/") && url.includes("/files");
}

function isGeminiGenerateRequest(url: string, method: string): boolean {
  return method === "POST" && url.includes("generativelanguage.googleapis.com") && url.includes(":generateContent");
}

function isGeminiDeleteRequest(url: string, method: string): boolean {
  return method === "DELETE" && url.includes("generativelanguage.googleapis.com") && url.includes("/files/");
}

test("live Gemini Files API path uses file upload, fileData generation, and cleanup for large audio", async ({ page }, testInfo) => {
  test.setTimeout(8 * 60 * 1_000);
  test.skip(!liveGeminiEnabled, "RUN_GEMINI_LIVE_SMOKE must be true to run the live Gemini smoke test.");
  test.skip(!geminiPhase2Enabled, "VITE_ENABLE_PHASE2_GEMINI must be true for the live Gemini smoke test.");
  test.skip(geminiApiKey.length === 0, "VITE_GEMINI_API_KEY must be set for the live Gemini smoke test.");
  test.skip(
    !(await backendSupportsPhase1Routes(backendBaseUrl)),
    `Backend at ${backendBaseUrl} does not expose /api/analyze and /api/analyze/estimate.`,
  );

  const largeWavPath = testInfo.outputPath("live-gemini-large-silence.wav");
  const fileSizeBytes = await writeOversizedSilentWav(largeWavPath);
  expect(fileSizeBytes).toBeGreaterThan(INLINE_SIZE_LIMIT);

  const googleRequestOrder: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    const method = request.method();
    if (isGeminiUploadRequest(url, method)) googleRequestOrder.push("upload");
    if (isGeminiGenerateRequest(url, method)) googleRequestOrder.push("generate");
    if (isGeminiDeleteRequest(url, method)) googleRequestOrder.push("delete");
  });

  const uploadRequestPromise = page.waitForRequest(
    (request) => isGeminiUploadRequest(request.url(), request.method()),
    { timeout: 8 * 60 * 1_000 },
  );
  const generateRequestPromise = page.waitForRequest(
    (request) => isGeminiGenerateRequest(request.url(), request.method()),
    { timeout: 8 * 60 * 1_000 },
  );
  const deleteRequestPromise = page.waitForRequest(
    (request) => isGeminiDeleteRequest(request.url(), request.method()),
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

    const uploadRequest = await uploadRequestPromise;
    const generateRequest = await generateRequestPromise;
    const deleteRequest = await deleteRequestPromise;
    const generateBody = generateRequest.postData() ?? "";

    expect(uploadRequest.method()).toBe("POST");
    expect(uploadRequest.url()).toContain("/upload/");
    expect(generateRequest.method()).toBe("POST");
    expect(generateRequest.url()).toContain(":generateContent");
    expect(generateBody).toContain('"fileData"');
    expect(generateBody).toContain('"fileUri"');
    expect(generateBody).not.toContain('"inlineData"');
    expect(deleteRequest.method()).toBe("DELETE");
    expect(deleteRequest.url()).toContain("/files/");

    const uploadIndex = googleRequestOrder.indexOf("upload");
    const generateIndex = googleRequestOrder.indexOf("generate");
    const deleteIndex = googleRequestOrder.indexOf("delete");
    expect(uploadIndex).toBeGreaterThanOrEqual(0);
    expect(generateIndex).toBeGreaterThan(uploadIndex);
    expect(deleteIndex).toBeGreaterThan(generateIndex);

    await expect(page.getByText("Analysis Results")).toBeVisible({ timeout: 8 * 60 * 1_000 });
    await expect(page.getByText("System Diagnostics")).toBeVisible();
    await expect(page.getByText(/Phase 2 advisory complete\. Upload: \d+ms, Generate: \d+ms/)).toBeVisible({
      timeout: 8 * 60 * 1_000,
    });
    await expect(page.getByText(/Unexpected DSP backend error/i)).toHaveCount(0);
    await expect(page.getByText(/Phase 2 advisory is disabled or missing an API key/i)).toHaveCount(0);
  } finally {
    await fs.rm(largeWavPath, { force: true });
  }
});

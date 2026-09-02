/**
 * Capture a live results DOM subtree as a multi-page PDF.
 *
 * Strategy (fast path):
 *   - Walk top-level sections under the results root
 *   - Rasterize each section separately at pixelRatio=1 (not one giant 2× bitmap)
 *   - Skip sticky nav, canvases, and other heavy viz that explode capture time
 *   - Yield to the main thread between sections so the UI stays responsive
 *
 * Expected duration: ~2–8s for a typical results page. If it exceeds ~20s,
 * something is wrong (huge open spectrogram, browser thrashing).
 */
import { toJpeg } from 'html-to-image';
import { jsPDF } from 'jspdf';

import { buildExportFileName, type ExportSourceMeta } from './exportUtils';

export type UiCaptureFormat = 'pdf' | 'png';

export interface UiCaptureProgress {
  phase: 'prepare' | 'section' | 'pdf' | 'done';
  current: number;
  total: number;
  label: string;
}

export interface UiCaptureOptions {
  /** Root element to capture (defaults to [data-testid=analysis-results-root]). */
  element?: HTMLElement | null;
  source?: ExportSourceMeta | null;
  /** Device pixel ratio. Default 1 — 2× is dramatically slower on tall pages. */
  pixelRatio?: number;
  /** Prefer PDF (paginated) or a single tall PNG of the first pass. */
  format?: UiCaptureFormat;
  /** Background fill behind transparent regions. */
  backgroundColor?: string;
  /** Soft timeout in ms (default 25_000). */
  timeoutMs?: number;
  /** Progress callback for button status text. */
  onProgress?: (progress: UiCaptureProgress) => void;
}

export interface UiCaptureResult {
  format: UiCaptureFormat;
  fileName: string;
  byteLength: number;
  sectionCount: number;
  elapsedMs: number;
}

export class UiCaptureError extends Error {
  constructor(message: string, readonly cause?: unknown) {
    super(message);
    this.name = 'UiCaptureError';
  }
}

/** Split a tall image height into page slice heights (source-pixel units). */
export function planPdfPageSlices(
  imageWidth: number,
  imageHeight: number,
  pageWidthPt = 595.28, // A4
  pageHeightPt = 841.89,
  marginPt = 18,
): { sliceTop: number; sliceHeight: number }[] {
  if (imageWidth <= 0 || imageHeight <= 0) return [];
  const contentWidthPt = pageWidthPt - marginPt * 2;
  const contentHeightPt = pageHeightPt - marginPt * 2;
  const sourcePxPerPt = imageWidth / contentWidthPt;
  const pageSourceHeight = Math.max(1, Math.floor(contentHeightPt * sourcePxPerPt));

  const slices: { sliceTop: number; sliceHeight: number }[] = [];
  let top = 0;
  while (top < imageHeight) {
    const remaining = imageHeight - top;
    const h = Math.min(pageSourceHeight, remaining);
    slices.push({ sliceTop: top, sliceHeight: h });
    top += h;
  }
  return slices;
}

function resolveCaptureRoot(element?: HTMLElement | null): HTMLElement {
  const root =
    element ??
    (typeof document !== 'undefined'
      ? (document.querySelector('[data-testid="analysis-results-root"]') as HTMLElement | null)
      : null);
  if (!root) {
    throw new UiCaptureError('Results panel not found — run an analysis first.');
  }
  return root;
}

function yieldToMain(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(() => resolve());
    } else {
      setTimeout(resolve, 0);
    }
  });
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, label: string): Promise<T> {
  if (!timeoutMs || timeoutMs <= 0) return promise;
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      reject(
        new UiCaptureError(
          `UI capture timed out after ${Math.round(timeoutMs / 1000)}s while ${label}. Try collapsing Measurements spectrograms and retry.`,
        ),
      );
    }, timeoutMs);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timer);
        reject(error);
      },
    );
  });
}

/**
 * Nodes that must never be rasterized — they dominate capture time and often
 * blank or hang (WebGL/canvas spectrograms, sticky chrome, live players).
 */
function asElementLike(node: Node): {
  tagName: string;
  dataset?: DOMStringMap | Record<string, string | undefined>;
  classList?: { contains: (token: string) => boolean };
} | null {
  // Browser path.
  if (typeof HTMLElement !== 'undefined' && node instanceof HTMLElement) {
    return node;
  }
  // Node-env / test stubs shaped like elements.
  if (node && typeof node === 'object' && 'tagName' in node) {
    return node as {
      tagName: string;
      dataset?: Record<string, string | undefined>;
      classList?: { contains: (token: string) => boolean };
    };
  }
  return null;
}

export function shouldSkipCaptureNode(node: Node): boolean {
  const el = asElementLike(node);
  if (!el) return false;
  const testId = (el.dataset?.testid ?? el.dataset?.['testid'] ?? '') as string;
  if (testId === 'sticky-nav') return true;
  if (testId === 'analysis-export-ui-error') return true;
  // Heavy measurement viz: keep the dashboard chrome, skip live spectral widgets.
  if (
    el.tagName === 'CANVAS' ||
    el.tagName === 'VIDEO' ||
    el.tagName === 'AUDIO' ||
    el.classList?.contains('wavesurfer') ||
    el.dataset?.captureSkip === 'true'
  ) {
    return true;
  }
  // Spectrogram / heatmap hosts are multi-MB canvases.
  if (
    testId.includes('spectrogram') ||
    testId.includes('heatmap') ||
    testId.includes('pianoroll') ||
    testId.includes('waveform')
  ) {
    return true;
  }
  return false;
}

/**
 * Collect capture targets: prefer explicit <section> / [data-capture-section],
 * else direct element children of the root that have real layout height.
 */
export function collectCaptureSections(root: HTMLElement): HTMLElement[] {
  const preferred = Array.from(
    root.querySelectorAll<HTMLElement>(
      ':scope > section, :scope > [data-capture-section], :scope > div > section',
    ),
  ).filter((el) => {
    if (shouldSkipCaptureNode(el)) return false;
    const rect = el.getBoundingClientRect();
    return rect.height >= 24 && rect.width >= 24;
  });

  if (preferred.length >= 2) return preferred;

  // Fallback: direct children with measurable height.
  return Array.from(root.children).filter((child): child is HTMLElement => {
    if (!(child instanceof HTMLElement)) return false;
    if (shouldSkipCaptureNode(child)) return false;
    const rect = child.getBoundingClientRect();
    return rect.height >= 24 && rect.width >= 24;
  });
}

async function inlineCrossOriginImages(root: HTMLElement): Promise<() => void> {
  if (typeof window === 'undefined' || typeof fetch !== 'function') {
    return () => undefined;
  }

  const pageOrigin = window.location.origin;
  const images = Array.from(root.querySelectorAll('img')) as HTMLImageElement[];
  const restores: Array<() => void> = [];

  // Cap concurrent fetches — spectrograms can be large.
  const queue = images.slice(0, 24);
  await Promise.all(
    queue.map(async (img) => {
      const src = img.currentSrc || img.src;
      if (!src || src.startsWith('data:') || src.startsWith('blob:')) return;
      let url: URL;
      try {
        url = new URL(src, pageOrigin);
      } catch {
        return;
      }
      if (url.origin === pageOrigin) return;

      try {
        const response = await fetch(src, { mode: 'cors', credentials: 'include' });
        if (!response.ok) return;
        const blob = await response.blob();
        // Skip multi-MB blobs in capture — they are the slow path.
        if (blob.size > 1_500_000) return;
        const objectUrl = URL.createObjectURL(blob);
        const previous = img.getAttribute('src');
        img.src = objectUrl;
        restores.push(() => {
          if (previous === null) img.removeAttribute('src');
          else img.setAttribute('src', previous);
          URL.revokeObjectURL(objectUrl);
        });
      } catch {
        // leave original
      }
    }),
  );

  return () => {
    for (const restore of restores) restore();
  };
}

async function rasterizeSection(
  section: HTMLElement,
  pixelRatio: number,
  backgroundColor: string,
): Promise<{ dataUrl: string; width: number; height: number } | null> {
  const rect = section.getBoundingClientRect();
  if (rect.height < 8 || rect.width < 8) return null;

  // Cap CSS width so we never build a multi-thousand-px wide canvas.
  const cssWidth = Math.min(Math.ceil(rect.width), 1200);
  const cssHeight = Math.ceil(rect.height);
  // Hard safety: skip absurdly tall single sections (open spectrogram racks).
  if (cssHeight > 8_000) {
    return null;
  }

  try {
    const dataUrl = await toJpeg(section, {
      quality: 0.86,
      pixelRatio,
      backgroundColor,
      cacheBust: false,
      width: cssWidth,
      // html-to-image uses scrollHeight; force a sane box.
      height: cssHeight,
      style: {
        // Avoid transforms that produce empty bitmaps.
        transform: 'none',
        width: `${cssWidth}px`,
      },
      filter: (node: Node) => !shouldSkipCaptureNode(node),
    });
    return {
      dataUrl,
      width: Math.round(cssWidth * pixelRatio),
      height: Math.round(cssHeight * pixelRatio),
    };
  } catch {
    return null;
  }
}

function triggerBlobDownload(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  a.rel = 'noopener';
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 2_000);
}

async function dataUrlToImage(dataUrl: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new UiCaptureError('Failed to decode a captured section.'));
    img.src = dataUrl;
  });
}

async function appendSectionToPdf(
  pdf: jsPDF,
  dataUrl: string,
  isFirstPage: { value: boolean },
): Promise<void> {
  const img = await dataUrlToImage(dataUrl);
  const imageWidth = img.naturalWidth || img.width;
  const imageHeight = img.naturalHeight || img.height;
  if (imageWidth <= 0 || imageHeight <= 0) return;

  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const margin = 16;
  const contentWidth = pageWidth - margin * 2;
  const contentHeight = pageHeight - margin * 2;
  const slices = planPdfPageSlices(imageWidth, imageHeight, pageWidth, pageHeight, margin);
  const scale = contentWidth / imageWidth;

  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new UiCaptureError('Canvas is not available in this browser.');

  for (let i = 0; i < slices.length; i += 1) {
    const { sliceTop, sliceHeight } = slices[i];
    canvas.width = imageWidth;
    canvas.height = sliceHeight;
    ctx.fillStyle = '#2b2b2b';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, sliceTop, imageWidth, sliceHeight, 0, 0, imageWidth, sliceHeight);
    const sliceDataUrl = canvas.toDataURL('image/jpeg', 0.88);

    if (!isFirstPage.value) pdf.addPage();
    isFirstPage.value = false;

    const drawHeight = Math.min(sliceHeight * scale, contentHeight);
    pdf.addImage(sliceDataUrl, 'JPEG', margin, margin, contentWidth, drawHeight);
  }
}

/**
 * Capture the analysis results UI and trigger a download.
 * Target: a few seconds, not minutes.
 */
export async function captureAndDownloadResultsUi(
  options: UiCaptureOptions = {},
): Promise<UiCaptureResult> {
  if (typeof document === 'undefined') {
    throw new UiCaptureError('UI capture only works in the browser.');
  }

  const started = performance.now();
  const root = resolveCaptureRoot(options.element);
  const pixelRatio = options.pixelRatio ?? 1;
  const backgroundColor = options.backgroundColor ?? '#2b2b2b';
  const format: UiCaptureFormat = options.format ?? 'pdf';
  const source = options.source ?? null;
  const timeoutMs = options.timeoutMs ?? 25_000;
  const onProgress = options.onProgress;

  const report = (progress: UiCaptureProgress) => {
    try {
      onProgress?.(progress);
    } catch {
      // ignore UI callback errors
    }
  };

  report({ phase: 'prepare', current: 0, total: 0, label: 'Preparing…' });

  try {
    root.scrollIntoView({ block: 'start' });
  } catch {
    // ignore
  }

  const work = (async (): Promise<UiCaptureResult> => {
    const restoreImages = await inlineCrossOriginImages(root);
    try {
      const sections = collectCaptureSections(root);
      if (sections.length === 0) {
        throw new UiCaptureError('No visible results sections to capture.');
      }

      report({
        phase: 'section',
        current: 0,
        total: sections.length,
        label: `Capturing 0/${sections.length}…`,
      });

      const captured: { dataUrl: string; width: number; height: number }[] = [];
      for (let i = 0; i < sections.length; i += 1) {
        report({
          phase: 'section',
          current: i + 1,
          total: sections.length,
          label: `Capturing ${i + 1}/${sections.length}…`,
        });
        await yieldToMain();
        const shot = await rasterizeSection(sections[i], pixelRatio, backgroundColor);
        if (shot) captured.push(shot);
      }

      if (captured.length === 0) {
        throw new UiCaptureError(
          'Capture produced no pages. Collapse heavy Measurement panels and try again.',
        );
      }

      if (format === 'png') {
        // PNG mode: download the tallest/first useful section only (fast preview).
        report({ phase: 'pdf', current: 1, total: 1, label: 'Saving PNG…' });
        const best = captured.reduce((a, b) => (b.height > a.height ? b : a));
        const fileName = buildExportFileName('png', source);
        const response = await fetch(best.dataUrl);
        const blob = await response.blob();
        triggerBlobDownload(blob, fileName);
        const elapsedMs = Math.round(performance.now() - started);
        report({ phase: 'done', current: captured.length, total: captured.length, label: 'Done' });
        return {
          format: 'png',
          fileName,
          byteLength: blob.size,
          sectionCount: captured.length,
          elapsedMs,
        };
      }

      report({
        phase: 'pdf',
        current: 0,
        total: captured.length,
        label: 'Building PDF…',
      });

      const pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'pt',
        format: 'a4',
        compress: true,
      });
      const isFirstPage = { value: true };
      for (let i = 0; i < captured.length; i += 1) {
        report({
          phase: 'pdf',
          current: i + 1,
          total: captured.length,
          label: `PDF page group ${i + 1}/${captured.length}…`,
        });
        await yieldToMain();
        await appendSectionToPdf(pdf, captured[i].dataUrl, isFirstPage);
      }

      const blob = pdf.output('blob');
      const fileName = buildExportFileName('pdf', source);
      triggerBlobDownload(blob, fileName);
      const elapsedMs = Math.round(performance.now() - started);
      report({ phase: 'done', current: captured.length, total: captured.length, label: 'Done' });
      return {
        format: 'pdf',
        fileName,
        byteLength: blob.size,
        sectionCount: captured.length,
        elapsedMs,
      };
    } finally {
      restoreImages();
    }
  })();

  try {
    return await withTimeout(work, timeoutMs, 'rasterizing the results UI');
  } catch (error) {
    if (error instanceof UiCaptureError) throw error;
    throw new UiCaptureError(
      error instanceof Error ? error.message : 'UI capture failed.',
      error,
    );
  }
}

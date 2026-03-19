import React, { useCallback, useEffect, useRef, useState } from 'react';

interface MelSpectrogramProps {
  audioFile: File;
  audioElementRef: React.RefObject<HTMLAudioElement | null>;
  onSeek?: (timeSeconds: number) => void;
  durationSeconds: number;
}

interface SpectrogramData {
  data: Float32Array;
  timeFrames: number;
  melBands: number;
  durationSeconds: number;
  timeResolution: number;
  sampleRate: number;
}

type Status = 'idle' | 'decoding' | 'computing' | 'ready' | 'error';

// ---- Constants --------------------------------------------------------------

const CANVAS_HEIGHT = 256;
const GUTTER_LEFT = 44;
const GUTTER_BOTTOM = 24;
const MINIMAP_HEIGHT = 40;
const LONG_TRACK_THRESHOLD = 120;
const PX_PER_SECOND = 8;
const DB_FLOOR = -80;

// ---- Inferno colormap (256-entry RGB LUT) -----------------------------------

const INFERNO_CONTROL_POINTS: [number, number, number, number][] = [
  [0.0, 0, 0, 4],
  [0.05, 7, 5, 37],
  [0.1, 26, 9, 72],
  [0.15, 49, 9, 96],
  [0.2, 70, 14, 108],
  [0.25, 92, 20, 110],
  [0.3, 113, 27, 104],
  [0.35, 133, 36, 93],
  [0.4, 152, 45, 80],
  [0.45, 170, 56, 66],
  [0.5, 186, 69, 52],
  [0.55, 200, 82, 39],
  [0.6, 212, 97, 29],
  [0.65, 223, 113, 22],
  [0.7, 232, 130, 18],
  [0.75, 240, 149, 16],
  [0.8, 245, 168, 19],
  [0.85, 248, 189, 29],
  [0.9, 249, 210, 48],
  [0.95, 247, 230, 80],
  [1.0, 252, 255, 164],
];

function buildInfernoLUT(): Uint8Array {
  const lut = new Uint8Array(256 * 3);
  for (let i = 0; i < 256; i++) {
    const t = i / 255;
    let lo = 0;
    for (let k = 1; k < INFERNO_CONTROL_POINTS.length; k++) {
      if (INFERNO_CONTROL_POINTS[k][0] >= t) {
        lo = k - 1;
        break;
      }
    }
    const [t0, r0, g0, b0] = INFERNO_CONTROL_POINTS[lo];
    const [t1, r1, g1, b1] = INFERNO_CONTROL_POINTS[lo + 1];
    const frac = t1 === t0 ? 0 : (t - t0) / (t1 - t0);
    lut[i * 3] = Math.round(r0 + (r1 - r0) * frac);
    lut[i * 3 + 1] = Math.round(g0 + (g1 - g0) * frac);
    lut[i * 3 + 2] = Math.round(b0 + (b1 - b0) * frac);
  }
  return lut;
}

const INFERNO_LUT = buildInfernoLUT();

function infernoGradientCSS(): string {
  const stops: string[] = [];
  for (let i = 0; i <= 255; i += 32) {
    const idx = Math.min(i, 255);
    const r = INFERNO_LUT[idx * 3];
    const g = INFERNO_LUT[idx * 3 + 1];
    const b = INFERNO_LUT[idx * 3 + 2];
    stops.push(`rgb(${r},${g},${b}) ${Math.round((idx / 255) * 100)}%`);
  }
  // Ensure we include the final stop
  const r = INFERNO_LUT[255 * 3];
  const g = INFERNO_LUT[255 * 3 + 1];
  const b = INFERNO_LUT[255 * 3 + 2];
  stops.push(`rgb(${r},${g},${b}) 100%`);
  return `linear-gradient(to right, ${stops.join(', ')})`;
}

const GRADIENT_CSS = infernoGradientCSS();

// ---- Frequency helpers ------------------------------------------------------

const FREQ_LABELS = [
  { hz: 50, label: '50' },
  { hz: 200, label: '200' },
  { hz: 1000, label: '1k' },
  { hz: 4000, label: '4k' },
  { hz: 8000, label: '8k' },
  { hz: 16000, label: '16k' },
];

function hzToMel(hz: number): number {
  return 2595 * Math.log10(1 + hz / 700);
}

function melToHz(mel: number): number {
  return 700 * (Math.pow(10, mel / 2595) - 1);
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${m}:${s < 10 ? '0' : ''}${s.toFixed(1)}`;
}

function formatFreq(hz: number): string {
  return hz < 1000 ? `${Math.round(hz)} Hz` : `${(hz / 1000).toFixed(1)} kHz`;
}

// ---- Component --------------------------------------------------------------

export function MelSpectrogram({
  audioFile,
  audioElementRef,
  onSeek,
  durationSeconds,
}: MelSpectrogramProps) {
  const [status, setStatus] = useState<Status>('idle');
  const [progress, setProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const baseCanvasRef = useRef<HTMLCanvasElement>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
  const minimapCanvasRef = useRef<HTMLCanvasElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const spectrogramRef = useRef<SpectrogramData | null>(null);
  const offscreenRef = useRef<HTMLCanvasElement | null>(null);
  const workerRef = useRef<Worker | null>(null);
  const rafRef = useRef<number | null>(null);
  const hoverRef = useRef<{ x: number; y: number } | null>(null);
  const lastDrawnTimeRef = useRef<number>(-1);
  const canvasSizeRef = useRef<{ width: number; height: number }>({ width: 0, height: 0 });
  const scrollOffsetRef = useRef<number>(0);
  const isAutoScrollRef = useRef<boolean>(true);
  const reducedMotionRef = useRef<boolean>(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isScrollingMode = durationSeconds > LONG_TRACK_THRESHOLD;

  // ---- Mel-scale mapping helpers (need melBands for bounds) ----------------

  const melMin = hzToMel(20);
  const melMax = hzToMel(16000);

  function hzToCanvasY(hz: number): number {
    const melNorm = (hzToMel(hz) - melMin) / (melMax - melMin);
    return (1 - melNorm) * CANVAS_HEIGHT;
  }

  function canvasYToHz(y: number): number {
    const melNorm = 1 - y / CANVAS_HEIGHT;
    return melToHz(melMin + melNorm * (melMax - melMin));
  }

  // ---- renderOffscreen: pixel data from spectrogram data -------------------

  const renderOffscreen = useCallback((spect: SpectrogramData) => {
    const { data, timeFrames, melBands } = spect;
    const oc = document.createElement('canvas');
    oc.width = timeFrames;
    oc.height = melBands;
    const ctx = oc.getContext('2d');
    if (!ctx) return;

    const imgData = ctx.createImageData(timeFrames, melBands);
    const pixels = imgData.data;

    for (let frame = 0; frame < timeFrames; frame++) {
      for (let band = 0; band < melBands; band++) {
        const db = data[frame * melBands + band];
        let idx = Math.round(((db - DB_FLOOR) / -DB_FLOOR) * 255);
        if (idx < 0) idx = 0;
        if (idx > 255) idx = 255;

        const pixelY = melBands - 1 - band;
        const offset = (pixelY * timeFrames + frame) * 4;
        pixels[offset] = INFERNO_LUT[idx * 3];
        pixels[offset + 1] = INFERNO_LUT[idx * 3 + 1];
        pixels[offset + 2] = INFERNO_LUT[idx * 3 + 2];
        pixels[offset + 3] = 255;
      }
    }

    ctx.putImageData(imgData, 0, 0);
    offscreenRef.current = oc;
  }, []);

  // ---- renderBaseCanvas: draw offscreen image onto visible canvas -----------

  const renderBaseCanvas = useCallback(() => {
    const base = baseCanvasRef.current;
    const oc = offscreenRef.current;
    const spect = spectrogramRef.current;
    if (!base || !oc || !spect) return;

    const container = containerRef.current;
    if (!container) return;

    const containerWidth = container.clientWidth;
    const canvasWidth = containerWidth;
    const canvasHeight = CANVAS_HEIGHT;
    const dpr = window.devicePixelRatio || 1;

    base.style.width = `${canvasWidth}px`;
    base.style.height = `${canvasHeight}px`;
    base.width = canvasWidth * dpr;
    base.height = canvasHeight * dpr;

    canvasSizeRef.current = { width: canvasWidth, height: canvasHeight };

    const ctx = base.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.imageSmoothingEnabled = false;

    if (!isScrollingMode) {
      ctx.drawImage(oc, 0, 0, spect.timeFrames, spect.melBands, 0, 0, canvasWidth, canvasHeight);
    } else {
      const viewportDuration = canvasWidth / PX_PER_SECOND;
      const scrollSec = scrollOffsetRef.current;
      const startFrame = Math.floor((scrollSec / spect.durationSeconds) * spect.timeFrames);
      const endFrame = Math.min(
        spect.timeFrames,
        Math.ceil(((scrollSec + viewportDuration) / spect.durationSeconds) * spect.timeFrames),
      );
      const srcWidth = endFrame - startFrame;
      if (srcWidth > 0) {
        ctx.drawImage(oc, startFrame, 0, srcWidth, spect.melBands, 0, 0, canvasWidth, canvasHeight);
      }
    }
  }, [isScrollingMode]);

  // ---- renderMinimap --------------------------------------------------------

  const renderMinimap = useCallback(() => {
    const minimap = minimapCanvasRef.current;
    const oc = offscreenRef.current;
    const spect = spectrogramRef.current;
    if (!minimap || !oc || !spect || !isScrollingMode) return;

    const container = containerRef.current;
    if (!container) return;
    const containerWidth = container.clientWidth;
    const dpr = window.devicePixelRatio || 1;

    minimap.style.width = `${containerWidth}px`;
    minimap.style.height = `${MINIMAP_HEIGHT}px`;
    minimap.width = containerWidth * dpr;
    minimap.height = MINIMAP_HEIGHT * dpr;

    const ctx = minimap.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.imageSmoothingEnabled = false;

    ctx.drawImage(oc, 0, 0, spect.timeFrames, spect.melBands, 0, 0, containerWidth, MINIMAP_HEIGHT);

    // Viewport highlight
    const viewportDuration = containerWidth / PX_PER_SECOND;
    const vpLeft = (scrollOffsetRef.current / spect.durationSeconds) * containerWidth;
    const vpWidth = (viewportDuration / spect.durationSeconds) * containerWidth;
    ctx.strokeStyle = 'rgba(255,255,255,0.7)';
    ctx.lineWidth = 1;
    ctx.strokeRect(vpLeft, 0, vpWidth, MINIMAP_HEIGHT);
    ctx.fillStyle = 'rgba(255,255,255,0.08)';
    ctx.fillRect(vpLeft, 0, vpWidth, MINIMAP_HEIGHT);
  }, [isScrollingMode]);

  // ---- Effect 1: Compute spectrogram ----------------------------------------

  useEffect(() => {
    let cancelled = false;
    setStatus('decoding');
    setProgress(0);
    setErrorMessage(null);
    spectrogramRef.current = null;
    offscreenRef.current = null;
    scrollOffsetRef.current = 0;
    isAutoScrollRef.current = true;

    async function run() {
      try {
        const arrayBuffer = await audioFile.arrayBuffer();
        if (cancelled) return;

        const offlineCtx = new OfflineAudioContext(1, 1, 44100);
        const audioBuffer = await offlineCtx.decodeAudioData(arrayBuffer);
        if (cancelled) return;

        // Mix to mono
        let pcmData: Float32Array;
        if (audioBuffer.numberOfChannels === 1) {
          pcmData = audioBuffer.getChannelData(0);
        } else {
          const ch0 = audioBuffer.getChannelData(0);
          const ch1 = audioBuffer.getChannelData(1);
          pcmData = new Float32Array(ch0.length);
          for (let i = 0; i < ch0.length; i++) {
            pcmData[i] = (ch0[i] + ch1[i]) * 0.5;
          }
        }

        setStatus('computing');

        const worker = new Worker(
          new URL('../services/spectrogramWorker.ts', import.meta.url),
          { type: 'module' },
        );
        workerRef.current = worker;

        worker.onmessage = (e: MessageEvent) => {
          if (cancelled) return;
          const msg = e.data;
          if (msg.type === 'progress') {
            setProgress(msg.percent);
          } else if (msg.type === 'complete') {
            const spect: SpectrogramData = {
              data: msg.data,
              timeFrames: msg.timeFrames,
              melBands: msg.melBands,
              durationSeconds: msg.durationSeconds,
              timeResolution: msg.timeResolution,
              sampleRate: msg.sampleRate,
            };
            spectrogramRef.current = spect;
            renderOffscreen(spect);
            setStatus('ready');
          } else if (msg.type === 'error') {
            setErrorMessage(msg.message);
            setStatus('error');
          }
        };

        worker.onerror = () => {
          if (cancelled) return;
          setErrorMessage('Spectrogram worker crashed unexpectedly');
          setStatus('error');
        };

        const transfer = pcmData.buffer;
        worker.postMessage({ type: 'compute', pcmData, sampleRate: audioBuffer.sampleRate }, [transfer]);
      } catch (err) {
        if (cancelled) return;
        setErrorMessage(err instanceof Error ? err.message : String(err));
        setStatus('error');
      }
    }

    run();

    return () => {
      cancelled = true;
      if (workerRef.current) {
        workerRef.current.terminate();
        workerRef.current = null;
      }
    };
  }, [audioFile, renderOffscreen]);

  // ---- Initial base canvas render once status becomes ready -----------------

  useEffect(() => {
    if (status === 'ready') {
      renderBaseCanvas();
      renderMinimap();
    }
  }, [status, renderBaseCanvas, renderMinimap]);

  // ---- Effect 2: rAF loop (playhead + hover tooltip) ------------------------

  useEffect(() => {
    if (status !== 'ready') return;

    reducedMotionRef.current =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function drawOverlay() {
      const overlay = overlayCanvasRef.current;
      const audio = audioElementRef.current;
      const spect = spectrogramRef.current;
      if (!overlay || !spect) return;

      const { width: canvasWidth, height: canvasHeight } = canvasSizeRef.current;
      if (canvasWidth === 0) return;

      const dpr = window.devicePixelRatio || 1;
      if (overlay.width !== canvasWidth * dpr || overlay.height !== canvasHeight * dpr) {
        overlay.style.width = `${canvasWidth}px`;
        overlay.style.height = `${canvasHeight}px`;
        overlay.width = canvasWidth * dpr;
        overlay.height = canvasHeight * dpr;
      }

      const currentTime = audio?.currentTime ?? 0;
      const paused = audio?.paused ?? true;

      if (paused && currentTime === lastDrawnTimeRef.current && !hoverRef.current) {
        rafRef.current = requestAnimationFrame(drawOverlay);
        return;
      }
      lastDrawnTimeRef.current = currentTime;

      // Auto-scroll for scrolling mode
      if (isScrollingMode && !paused && isAutoScrollRef.current) {
        const viewportDuration = canvasWidth / PX_PER_SECOND;
        const center = currentTime - viewportDuration / 2;
        const maxScroll = Math.max(0, spect.durationSeconds - viewportDuration);
        const newOffset = Math.max(0, Math.min(maxScroll, center));
        if (Math.abs(newOffset - scrollOffsetRef.current) > 0.1) {
          scrollOffsetRef.current = newOffset;
          renderBaseCanvas();
          renderMinimap();
        }
      }

      const ctx = overlay.getContext('2d');
      if (!ctx) {
        rafRef.current = requestAnimationFrame(drawOverlay);
        return;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, canvasWidth, canvasHeight);

      // Playhead
      let playheadX: number;
      if (!isScrollingMode) {
        playheadX = durationSeconds > 0 ? (currentTime / durationSeconds) * canvasWidth : 0;
      } else {
        playheadX = (currentTime - scrollOffsetRef.current) * PX_PER_SECOND;
      }
      if (playheadX >= 0 && playheadX <= canvasWidth) {
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.6)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(playheadX, 0);
        ctx.lineTo(playheadX, canvasHeight);
        ctx.stroke();
      }

      // Hover crosshair
      const hover = hoverRef.current;
      if (hover) {
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
        ctx.lineWidth = 0.5;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(hover.x, 0);
        ctx.lineTo(hover.x, canvasHeight);
        ctx.moveTo(0, hover.y);
        ctx.lineTo(canvasWidth, hover.y);
        ctx.stroke();
        ctx.setLineDash([]);

        // Tooltip
        const tip = tooltipRef.current;
        if (tip && spect) {
          let hoverTime: number;
          if (!isScrollingMode) {
            hoverTime = (hover.x / canvasWidth) * durationSeconds;
          } else {
            hoverTime = scrollOffsetRef.current + hover.x / PX_PER_SECOND;
          }
          const hoverHz = canvasYToHz(hover.y);
          const frame = Math.floor((hoverTime / spect.durationSeconds) * spect.timeFrames);
          const bandNorm = 1 - hover.y / canvasHeight;
          const band = Math.floor(bandNorm * spect.melBands);
          let db = DB_FLOOR;
          if (frame >= 0 && frame < spect.timeFrames && band >= 0 && band < spect.melBands) {
            db = spect.data[frame * spect.melBands + band];
          }

          tip.textContent = `${formatFreq(hoverHz)} @ ${formatTime(hoverTime)}: ${db.toFixed(1)} dB`;
          tip.style.display = 'block';
          const tipLeft = Math.min(hover.x + 12, canvasWidth - 160);
          const tipTop = Math.max(hover.y - 28, 0);
          tip.style.left = `${tipLeft}px`;
          tip.style.top = `${tipTop}px`;
        }
      }

      if (!reducedMotionRef.current) {
        rafRef.current = requestAnimationFrame(drawOverlay);
      }
    }

    if (reducedMotionRef.current) {
      intervalRef.current = setInterval(drawOverlay, 200);
    } else {
      rafRef.current = requestAnimationFrame(drawOverlay);
    }

    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [status, durationSeconds, isScrollingMode, audioElementRef, renderBaseCanvas, renderMinimap]);

  // ---- Effect 3: ResizeObserver ---------------------------------------------

  useEffect(() => {
    if (status !== 'ready') return;
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver(() => {
      renderBaseCanvas();
      renderMinimap();
    });
    observer.observe(container);

    return () => observer.disconnect();
  }, [status, renderBaseCanvas, renderMinimap]);

  // ---- Event handlers -------------------------------------------------------

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!onSeek) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const { width: canvasWidth } = canvasSizeRef.current;
      if (canvasWidth === 0) return;

      let clickTime: number;
      if (!isScrollingMode) {
        clickTime = (x / canvasWidth) * durationSeconds;
      } else {
        clickTime = scrollOffsetRef.current + x / PX_PER_SECOND;
      }
      onSeek(Math.max(0, Math.min(durationSeconds, clickTime)));
    },
    [onSeek, durationSeconds, isScrollingMode],
  );

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    hoverRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }, []);

  const handleMouseLeave = useCallback(() => {
    hoverRef.current = null;
    const tip = tooltipRef.current;
    if (tip) tip.style.display = 'none';
  }, []);

  const handleWheel = useCallback(
    (e: React.WheelEvent<HTMLDivElement>) => {
      if (!isScrollingMode) return;
      const spect = spectrogramRef.current;
      if (!spect) return;

      const delta = e.shiftKey ? e.deltaY : e.deltaX;
      const { width: canvasWidth } = canvasSizeRef.current;
      const viewportDuration = canvasWidth / PX_PER_SECOND;
      const maxScroll = Math.max(0, spect.durationSeconds - viewportDuration);
      const scrollDelta = (delta / canvasWidth) * viewportDuration;
      scrollOffsetRef.current = Math.max(0, Math.min(maxScroll, scrollOffsetRef.current + scrollDelta));
      isAutoScrollRef.current = false;
      renderBaseCanvas();
      renderMinimap();
    },
    [isScrollingMode, renderBaseCanvas, renderMinimap],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLCanvasElement>) => {
      if (!onSeek) return;
      const audio = audioElementRef.current;
      if (!audio) return;
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        onSeek(Math.max(0, audio.currentTime - 1));
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        onSeek(Math.min(durationSeconds, audio.currentTime + 1));
      }
    },
    [onSeek, durationSeconds, audioElementRef],
  );

  // ---- Frequency labels (y-axis) --------------------------------------------

  const frequencyLabels = FREQ_LABELS.map(({ hz, label }) => {
    const y = hzToCanvasY(hz);
    return (
      <div
        key={hz}
        className="absolute right-full pr-1 text-[10px] font-mono text-text-secondary"
        style={{ top: y, transform: 'translateY(-50%)' }}
      >
        {label}
      </div>
    );
  });

  // ---- Time labels (x-axis) -------------------------------------------------

  function computeTimeLabels(): { time: number; label: string; left: number }[] {
    const { width: canvasWidth } = canvasSizeRef.current;
    if (canvasWidth === 0) return [];

    if (!isScrollingMode) {
      const count = Math.min(6, Math.max(2, Math.ceil(durationSeconds / 30)));
      const labels: { time: number; label: string; left: number }[] = [];
      for (let i = 0; i <= count; i++) {
        const t = (i / count) * durationSeconds;
        labels.push({ time: t, label: formatTime(t), left: (i / count) * canvasWidth });
      }
      return labels;
    }

    const viewportDuration = canvasWidth / PX_PER_SECOND;
    const startT = scrollOffsetRef.current;
    const endT = startT + viewportDuration;
    const step = Math.max(5, Math.ceil(viewportDuration / 6 / 5) * 5);
    const firstTick = Math.ceil(startT / step) * step;
    const labels: { time: number; label: string; left: number }[] = [];
    for (let t = firstTick; t <= endT; t += step) {
      labels.push({ time: t, label: formatTime(t), left: (t - startT) * PX_PER_SECOND });
    }
    return labels;
  }

  const timeLabels = status === 'ready' ? computeTimeLabels() : [];

  // ---- JSX ------------------------------------------------------------------

  return (
    <div className="space-y-4">
      {/* Section header */}
      <div className="flex items-center justify-between border-b border-border pb-2">
        <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
          <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
          Mel Spectrogram
        </h2>
        <span className="text-[10px] font-mono bg-bg-panel border border-border px-2 py-1 rounded font-bold text-text-secondary">
          CLIENT DSP
        </span>
      </div>

      {/* Loading state */}
      {(status === 'decoding' || status === 'computing') && (
        <div
          className="bg-bg-card border border-border rounded-sm p-6 flex flex-col items-center justify-center"
          style={{ height: CANVAS_HEIGHT }}
        >
          <p className="text-xs font-mono text-text-secondary uppercase tracking-wider mb-3">
            {status === 'decoding' ? 'Decoding audio...' : `Computing spectrogram... ${progress}%`}
          </p>
          <div className="w-48 h-1 bg-bg-app border border-border/30 overflow-hidden">
            <div
              className="h-full bg-accent transition-[width]"
              style={{ width: `${status === 'decoding' ? 20 : progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Error state */}
      {status === 'error' && (
        <div className="bg-error/10 border border-error/30 rounded-sm p-4">
          <p className="text-xs font-mono text-error">{errorMessage}</p>
        </div>
      )}

      {/* Ready state */}
      {status === 'ready' && (
        <>
          {/* Minimap (scrolling mode only) */}
          {isScrollingMode && (
            <div className="relative" style={{ height: MINIMAP_HEIGHT }}>
              <canvas ref={minimapCanvasRef} className="w-full h-full" />
            </div>
          )}

          {/* Main spectrogram area */}
          <div
            ref={containerRef}
            className="relative"
            style={{ paddingLeft: GUTTER_LEFT, paddingBottom: GUTTER_BOTTOM }}
            onWheel={handleWheel}
          >
            {/* Frequency labels */}
            {frequencyLabels}

            {/* Canvas stack */}
            <div
              className="relative"
              style={{ height: CANVAS_HEIGHT }}
              role="img"
              aria-label="Mel spectrogram showing frequency energy distribution over time"
            >
              <canvas ref={baseCanvasRef} className="absolute inset-0 w-full h-full" />
              <canvas
                ref={overlayCanvasRef}
                className="absolute inset-0 w-full h-full cursor-crosshair"
                tabIndex={0}
                onClick={handleClick}
                onMouseMove={handleMouseMove}
                onMouseLeave={handleMouseLeave}
                onKeyDown={handleKeyDown}
              />
            </div>

            {/* Tooltip */}
            <div
              ref={tooltipRef}
              className="absolute pointer-events-none hidden bg-bg-panel border border-border rounded-sm px-2 py-1 text-xs font-mono z-20"
            />

            {/* Time labels */}
            {timeLabels.map((tick) => (
              <div
                key={tick.time}
                className="absolute text-[10px] font-mono text-text-secondary"
                style={{
                  left: GUTTER_LEFT + tick.left,
                  bottom: 0,
                  transform: 'translateX(-50%)',
                }}
              >
                {tick.label}
              </div>
            ))}
          </div>

          {/* Color legend */}
          <div style={{ marginLeft: GUTTER_LEFT }}>
            <div className="h-3 rounded-sm" style={{ background: GRADIENT_CSS }} />
            <div className="flex justify-between mt-1">
              {['-80', '-60', '-40', '-20', '0'].map((tick) => (
                <span key={tick} className="text-[10px] font-mono text-text-secondary">
                  {tick} dB
                </span>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

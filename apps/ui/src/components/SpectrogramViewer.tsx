import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { appConfig } from '../config';
import type { SpectralArtifactRef } from '../types';
import {
  buildArtifactUrl,
  fetchArtifactImageObjectUrl,
} from '../services/spectralArtifactsClient';
import { useSpectralCursor } from '../hooks/useSpectralCursorBus';
import { useImageZoom } from '../hooks/useImageZoom';
import {
  formatFrequency,
  pixelToFreqCQT,
  pixelToFreqLinear,
  pixelToFreqMel,
} from '../utils/spectralScales';

interface SpectrogramViewerProps {
  spectrograms: SpectralArtifactRef[];
  apiBaseUrl: string;
  runId: string;
  durationSeconds?: number;
}

const TAB_LABELS: Record<string, string> = {
  spectrogram_mel: 'Mel',
  spectrogram_chroma: 'Chroma',
  spectrogram_cqt: 'CQT',
  spectrogram_harmonic: 'Harmonic',
  spectrogram_percussive: 'Percussive',
  spectrogram_onset: 'Onset',
};

/** Kinds that have a meaningful frequency axis. */
const FREQ_KINDS: Record<string, (y: number, h: number) => number> = {
  spectrogram_mel: (y, h) => pixelToFreqMel(y, h),
  spectrogram_cqt: (y, h) => pixelToFreqCQT(y, h),
  spectrogram_harmonic: (y, h) => pixelToFreqLinear(y, h),
  spectrogram_percussive: (y, h) => pixelToFreqLinear(y, h),
};

export function SpectrogramViewer({
  spectrograms,
  apiBaseUrl,
  runId,
  durationSeconds,
}: SpectrogramViewerProps) {
  // ---- ALL HOOKS FIRST (before any early return) ----
  const [activeKind, setActiveKind] = useState<string>(
    spectrograms[0]?.kind ?? 'spectrogram_mel',
  );
  const containerRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const cursorTimeRef = useRef<number | null>(null);
  const localHoverRef = useRef<{ mouseX: number; mouseY: number } | null>(null);
  const activeKindRef = useRef(activeKind);
  activeKindRef.current = activeKind;

  const { publish, subscribe } = useSpectralCursor('spectrogram-viewer');
  const { zoomState, isZoomed, handlers: zoomHandlers, controls, visibleRange, wheelRef } = useImageZoom();

  // Merge overlayRef + wheelRef onto the same canvas element
  const canvasRefCallback = useCallback(
    (node: HTMLCanvasElement | null) => {
      overlayRef.current = node;
      wheelRef(node);
    },
    [wheelRef],
  );

  const duration = durationSeconds ?? 0;

  const activeSpec = useMemo(
    () => spectrograms.find((s) => s.kind === activeKind) ?? spectrograms[0] ?? null,
    [spectrograms, activeKind],
  );
  const directImageUrl = useMemo(
    () => (activeSpec ? buildArtifactUrl(apiBaseUrl, runId, activeSpec.artifactId) : ''),
    [activeSpec, apiBaseUrl, runId],
  );
  const [imageUrl, setImageUrl] = useState(directImageUrl);

  useEffect(() => {
    if (!activeSpec) {
      setImageUrl('');
      return;
    }

    if (Object.keys(appConfig.requestHeaders).length === 0) {
      setImageUrl(directImageUrl);
      return;
    }

    const controller = new AbortController();
    let released = false;
    let loadedImage: { url: string; revoke: () => void } | null = null;

    setImageUrl('');

    fetchArtifactImageObjectUrl(
      apiBaseUrl,
      runId,
      activeSpec.artifactId,
      { signal: controller.signal },
    )
      .then((loaded) => {
        if (released) {
          loaded.revoke();
          return;
        }
        loadedImage = loaded;
        setImageUrl(loaded.url);
      })
      .catch(() => {
        if (!released) {
          setImageUrl('');
        }
      });

    return () => {
      released = true;
      controller.abort();
      loadedImage?.revoke();
    };
  }, [activeSpec, apiBaseUrl, directImageUrl, runId]);

  const drawOverlay = useCallback(() => {
    const canvas = overlayRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;
    ctx.clearRect(0, 0, w, h);

    const time = cursorTimeRef.current;
    if (time === null || duration <= 0) return;

    // Map absolute time to pixel X accounting for zoom
    const vStart = visibleRange.start * duration;
    const vDur = (visibleRange.end - visibleRange.start) * duration;
    if (vDur <= 0) return;
    const x = ((time - vStart) / vDur) * w;
    if (x < -1 || x > w + 1) return; // cursor outside visible range

    // Vertical cursor line (always drawn — from bus or local)
    ctx.strokeStyle = 'rgba(255,255,255,0.4)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
    ctx.setLineDash([]);

    // Local hover: horizontal crosshair + frequency readout
    const local = localHoverRef.current;
    const freqFn = FREQ_KINDS[activeKindRef.current];
    const hasFreq = local && freqFn;

    if (local) {
      ctx.strokeStyle = 'rgba(255,255,255,0.25)';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(0, local.mouseY);
      ctx.lineTo(w, local.mouseY);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Tooltip
    const mins = Math.floor(time / 60);
    const secs = (time % 60).toFixed(1);
    const timePart = `${mins}:${secs.padStart(4, '0')}`;
    const freqPart = hasFreq ? ` · ${formatFrequency(freqFn(local.mouseY, h))}` : '';
    const label = `${timePart}${freqPart}`;

    ctx.font = '10px ui-monospace, monospace';
    const textW = ctx.measureText(label).width + 10;
    const tooltipH = 18;
    const flipX = x > w / 2;
    const flipY = local ? local.mouseY < 30 : false;
    const tooltipX = flipX ? x - textW - 6 : x + 6;
    const tooltipY = local ? (flipY ? local.mouseY + 6 : local.mouseY - tooltipH - 6) : 4;

    ctx.fillStyle = 'rgba(0,0,0,0.75)';
    ctx.fillRect(tooltipX, tooltipY, textW, tooltipH);
    ctx.fillStyle = '#e4e4e7';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, tooltipX + 5, tooltipY + tooltipH / 2);
    ctx.textBaseline = 'alphabetic';
  }, [duration, visibleRange]);

  // Keep overlay canvas sized to container
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(() => drawOverlay());
    observer.observe(container);
    return () => observer.disconnect();
  }, [drawOverlay]);

  // Subscribe to external cursor events from sibling visualizations
  useEffect(() => {
    return subscribe((time) => {
      cursorTimeRef.current = time;
      localHoverRef.current = null;
      drawOverlay();
    });
  }, [subscribe, drawOverlay]);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      zoomHandlers.onMouseMove(e);

      if (duration <= 0) return;
      const canvas = overlayRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const vStart = visibleRange.start * duration;
      const vDur = (visibleRange.end - visibleRange.start) * duration;
      const time = Math.max(0, Math.min(duration, vStart + (mouseX / rect.width) * vDur));
      cursorTimeRef.current = time;
      localHoverRef.current = { mouseX, mouseY };
      drawOverlay();
      publish(time);
    },
    [duration, drawOverlay, publish, zoomHandlers, visibleRange],
  );

  const handleMouseLeave = useCallback(() => {
    zoomHandlers.onMouseUp();
    cursorTimeRef.current = null;
    localHoverRef.current = null;
    drawOverlay();
    publish(null);
  }, [drawOverlay, publish, zoomHandlers]);

  const handleDoubleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      zoomHandlers.onDoubleClick(e);
    },
    [zoomHandlers],
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      zoomHandlers.onMouseDown(e);
    },
    [zoomHandlers],
  );

  // ---- EARLY RETURN (after all hooks) ----
  if (spectrograms.length === 0 || !activeSpec) return null;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <span className="text-[10px] font-mono uppercase tracking-wide text-text-secondary">
          Spectrogram
        </span>
        {spectrograms.length > 1 && (
          <div className="flex gap-1">
            {spectrograms.map((spec) => (
              <button
                key={spec.kind}
                onClick={() => setActiveKind(spec.kind)}
                className={`px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide rounded-sm transition-colors ${
                  spec.kind === activeKind
                    ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                    : 'text-text-secondary hover:text-text-primary border border-transparent'
                }`}
              >
                {TAB_LABELS[spec.kind] ?? spec.kind}
              </button>
            ))}
          </div>
        )}
      </div>
      <div
        ref={containerRef}
        className="relative rounded-sm overflow-hidden border border-border bg-bg-panel group"
      >
        <img
          src={imageUrl}
          alt={`${TAB_LABELS[activeSpec.kind] ?? activeSpec.kind} spectrogram`}
          className="w-full h-auto block"
          loading="lazy"
          style={{
            transform: `scale(${zoomState.scale})`,
            transformOrigin: `${zoomState.originX}% ${zoomState.originY}%`,
            transition: 'transform 0.15s ease-out',
          }}
        />
        <canvas
          ref={canvasRefCallback}
          className={`absolute inset-0 w-full h-full ${isZoomed ? 'cursor-grab active:cursor-grabbing' : 'cursor-crosshair'}`}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          onMouseDown={handleMouseDown}
          onMouseUp={zoomHandlers.onMouseUp}
          onDoubleClick={handleDoubleClick}
        />
        {/* Zoom controls — visible on hover or when zoomed */}
        <div
          className={`absolute top-2 right-2 flex gap-1 transition-opacity ${
            isZoomed ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
          }`}
        >
          <button
            onClick={controls.zoomOut}
            className="w-6 h-6 rounded-sm bg-black/60 text-white/70 hover:text-white text-xs font-mono flex items-center justify-center"
            title="Zoom out"
          >
            −
          </button>
          <button
            onClick={controls.resetZoom}
            className="w-6 h-6 rounded-sm bg-black/60 text-white/70 hover:text-white text-xs font-mono flex items-center justify-center"
            title="Reset zoom"
          >
            ⟳
          </button>
          <button
            onClick={controls.zoomIn}
            className="w-6 h-6 rounded-sm bg-black/60 text-white/70 hover:text-white text-xs font-mono flex items-center justify-center"
            title="Zoom in"
          >
            +
          </button>
        </div>
      </div>
    </div>
  );
}

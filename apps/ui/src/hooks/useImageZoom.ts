import React, { useCallback, useEffect, useRef, useState } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ZoomState {
  scale: number;
  originX: number; // 0-100, transform-origin X %
  originY: number; // 0-100, transform-origin Y %
}

interface UseImageZoomReturn {
  zoomState: ZoomState;
  isZoomed: boolean;
  handlers: {
    onDoubleClick: (e: React.MouseEvent) => void;
    onMouseDown: (e: React.MouseEvent) => void;
    onMouseMove: (e: React.MouseEvent) => void;
    onMouseUp: () => void;
  };
  controls: {
    zoomIn: () => void;
    zoomOut: () => void;
    resetZoom: () => void;
  };
  /** Visible time range as fraction of total duration [0-1]. */
  visibleRange: { start: number; end: number };
  /**
   * Attach to the target element to get non-passive wheel handling.
   * Pinch-to-zoom (ctrlKey) zooms the image; regular scroll passes through.
   */
  wheelRef: React.RefCallback<HTMLElement>;
}

// ---------------------------------------------------------------------------
// Scale steps
// ---------------------------------------------------------------------------

const SCALE_STEPS = [1, 1.5, 2, 3, 4];
const MIN_SCALE = SCALE_STEPS[0];
const MAX_SCALE = SCALE_STEPS[SCALE_STEPS.length - 1];

function clampScale(s: number): number {
  return Math.max(MIN_SCALE, Math.min(MAX_SCALE, s));
}

/** Snap to the nearest step above/below for discrete zoom in/out. */
function nextStep(current: number, direction: 1 | -1): number {
  for (let i = 0; i < SCALE_STEPS.length; i++) {
    if (direction === 1 && SCALE_STEPS[i] > current + 0.01) return SCALE_STEPS[i];
    if (direction === -1 && SCALE_STEPS[SCALE_STEPS.length - 1 - i] < current - 0.01)
      return SCALE_STEPS[SCALE_STEPS.length - 1 - i];
  }
  return direction === 1 ? MAX_SCALE : MIN_SCALE;
}

/** Clamp origin so the visible viewport stays within the image. */
function clampOrigin(origin: number, scale: number): number {
  if (scale <= 1) return 50;
  // At scale S the viewport shows 1/S of the image width.
  // origin% sets which part of the image is centred in the viewport.
  // To keep the image from having blank edges:
  //   origin must be in [halfView, 100 - halfView]
  //   where halfView = 50/S
  const halfView = 50 / scale;
  return Math.max(halfView, Math.min(100 - halfView, origin));
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useImageZoom(): UseImageZoomReturn {
  const [zoomState, setZoomState] = useState<ZoomState>({
    scale: 1,
    originX: 50,
    originY: 50,
  });
  const dragging = useRef(false);
  const lastMouse = useRef({ x: 0, y: 0 });

  const isZoomed = zoomState.scale > 1;

  // --- Wheel zoom (native listener for non-passive preventDefault) ---
  // On Mac trackpads: pinch-to-zoom sends wheel events with ctrlKey=true.
  // Regular two-finger scroll sends wheel events without ctrlKey.
  // We only capture pinch gestures; regular scroll passes through to the page.
  const wheelElementRef = useRef<HTMLElement | null>(null);

  const handleNativeWheel = useCallback((e: WheelEvent) => {
    // Only intercept pinch-to-zoom (ctrlKey) or when already zoomed in
    const isPinch = e.ctrlKey || e.metaKey;
    if (!isPinch) {
      // When already zoomed, prevent scroll from moving the page
      // so the user can pan via scroll. Otherwise let it through.
      return;
    }

    e.preventDefault();
    e.stopPropagation();

    const el = e.currentTarget as HTMLElement;
    const rect = el.getBoundingClientRect();
    const cursorX = ((e.clientX - rect.left) / rect.width) * 100;
    const cursorY = ((e.clientY - rect.top) / rect.height) * 100;

    setZoomState((prev) => {
      const direction = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      const newScale = clampScale(prev.scale * direction);
      if (newScale === prev.scale) return prev;
      const blend = newScale > prev.scale ? 0.3 : 0;
      const newOriginX = clampOrigin(prev.originX + (cursorX - prev.originX) * blend, newScale);
      const newOriginY = clampOrigin(prev.originY + (cursorY - prev.originY) * blend, newScale);
      return { scale: newScale, originX: newOriginX, originY: newOriginY };
    });
  }, []);

  // Ref callback: attach/detach native wheel listener with { passive: false }
  const wheelRef = useCallback(
    (node: HTMLElement | null) => {
      if (wheelElementRef.current) {
        wheelElementRef.current.removeEventListener('wheel', handleNativeWheel);
      }
      wheelElementRef.current = node;
      if (node) {
        node.addEventListener('wheel', handleNativeWheel, { passive: false });
      }
    },
    [handleNativeWheel],
  );

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (wheelElementRef.current) {
        wheelElementRef.current.removeEventListener('wheel', handleNativeWheel);
      }
    };
  }, [handleNativeWheel]);

  // --- Double-click toggle ---
  const onDoubleClick = useCallback((e: React.MouseEvent) => {
    setZoomState((prev) => {
      if (prev.scale > 1) return { scale: 1, originX: 50, originY: 50 };
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
      const cursorX = ((e.clientX - rect.left) / rect.width) * 100;
      const cursorY = ((e.clientY - rect.top) / rect.height) * 100;
      const s = 2;
      return {
        scale: s,
        originX: clampOrigin(cursorX, s),
        originY: clampOrigin(cursorY, s),
      };
    });
  }, []);

  // --- Drag to pan ---
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    dragging.current = true;
    lastMouse.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging.current) return;
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const dx = ((e.clientX - lastMouse.current.x) / rect.width) * -100;
    const dy = ((e.clientY - lastMouse.current.y) / rect.height) * -100;
    lastMouse.current = { x: e.clientX, y: e.clientY };

    setZoomState((prev) => {
      if (prev.scale <= 1) return prev;
      return {
        ...prev,
        originX: clampOrigin(prev.originX + dx, prev.scale),
        originY: clampOrigin(prev.originY + dy, prev.scale),
      };
    });
  }, []);

  const onMouseUp = useCallback(() => {
    dragging.current = false;
  }, []);

  // --- Button controls ---
  const zoomIn = useCallback(() => {
    setZoomState((prev) => {
      const s = nextStep(prev.scale, 1);
      return { ...prev, scale: s, originX: clampOrigin(prev.originX, s), originY: clampOrigin(prev.originY, s) };
    });
  }, []);

  const zoomOut = useCallback(() => {
    setZoomState((prev) => {
      const s = nextStep(prev.scale, -1);
      return {
        scale: s,
        originX: clampOrigin(prev.originX, s),
        originY: clampOrigin(prev.originY, s),
      };
    });
  }, []);

  const resetZoom = useCallback(() => {
    setZoomState({ scale: 1, originX: 50, originY: 50 });
  }, []);

  // --- Visible range ---
  const halfView = 50 / zoomState.scale;
  const start = (zoomState.originX - halfView) / 100;
  const end = (zoomState.originX + halfView) / 100;

  return {
    zoomState,
    isZoomed,
    handlers: { onDoubleClick, onMouseDown, onMouseMove, onMouseUp },
    controls: { zoomIn, zoomOut, resetZoom },
    visibleRange: { start: Math.max(0, start), end: Math.min(1, end) },
    wheelRef,
  };
}

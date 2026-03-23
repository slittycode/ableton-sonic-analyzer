/**
 * Ref-based pub/sub bus for synchronising a time-cursor across
 * SpectrogramViewer, SpectralEvolutionChart, and ChromaHeatmap.
 *
 * Why ref-based instead of React state?
 * Three canvas components redraw on every mouse pixel movement.  Using
 * `useState` would trigger React re-renders on every frame for all
 * consumers.  Instead each subscriber stores the time in its own ref
 * and calls its own `draw()` — matching the existing ChromaHeatmap
 * pattern (`tooltipRef.current`).
 *
 * `publish` fires every subscriber except the one whose `id` matches
 * `sourceId`, preventing echo loops.  Dispatch is throttled to one
 * call per `requestAnimationFrame`.
 */

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef } from 'react';

// ---------------------------------------------------------------------------
// Bus core
// ---------------------------------------------------------------------------

type CursorCallback = (time: number | null) => void;

interface SpectralCursorBus {
  subscribe: (id: string, cb: CursorCallback) => () => void;
  publish: (time: number | null, sourceId: string) => void;
}

function createSpectralCursorBus(): SpectralCursorBus {
  const subscribers = new Map<string, CursorCallback>();
  let pendingTime: number | null | undefined;
  let pendingSource: string | null = null;
  let rafId: number | null = null;

  function flush() {
    rafId = null;
    if (pendingTime === undefined) return;
    const time = pendingTime;
    const source = pendingSource;
    pendingTime = undefined;
    pendingSource = null;
    for (const [id, cb] of subscribers) {
      if (id !== source) cb(time);
    }
  }

  return {
    subscribe(id, cb) {
      subscribers.set(id, cb);
      return () => {
        subscribers.delete(id);
      };
    },
    publish(time, sourceId) {
      pendingTime = time;
      pendingSource = sourceId;
      if (rafId === null) {
        rafId = requestAnimationFrame(flush);
      }
    },
  };
}

// ---------------------------------------------------------------------------
// React context + provider
// ---------------------------------------------------------------------------

const SpectralCursorBusContext = createContext<SpectralCursorBus | null>(null);

export function SpectralCursorProvider({ children }: { children: React.ReactNode }) {
  const bus = useMemo(() => createSpectralCursorBus(), []);
  return (
    <SpectralCursorBusContext.Provider value={bus}>
      {children}
    </SpectralCursorBusContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Consumer hook
// ---------------------------------------------------------------------------

/**
 * Hook for consuming the cursor bus.
 *
 * @param componentId  Unique string identifying the caller — used to
 *                     exclude the publisher from receiving its own event.
 */
export function useSpectralCursor(componentId: string) {
  const bus = useContext(SpectralCursorBusContext);

  const publish = useCallback(
    (time: number | null) => {
      bus?.publish(time, componentId);
    },
    [bus, componentId],
  );

  const subscribeRef = useRef<((cb: CursorCallback) => () => void) | null>(null);
  subscribeRef.current = (cb: CursorCallback) => {
    if (!bus) return () => {};
    return bus.subscribe(componentId, cb);
  };

  /** Call inside a useEffect to register a callback. Returns unsubscribe. */
  const subscribe = useCallback(
    (cb: CursorCallback) => subscribeRef.current!(cb),
    [],
  );

  return { publish, subscribe };
}

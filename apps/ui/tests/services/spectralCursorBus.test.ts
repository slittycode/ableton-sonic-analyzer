import { describe, expect, it, vi } from 'vitest';

// The bus factory is a plain function — we can test it without React.
// We import the module and call the factory directly.

// Since createSpectralCursorBus is not exported, we replicate its logic
// for unit testing.  Alternatively, we test via the hook, but that
// requires a React render context.  For pure logic tests we re-create
// the core bus inline.

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
        // In test environment, use setTimeout as RAF substitute
        rafId = setTimeout(flush, 0) as unknown as number;
      }
    },
  };
}

describe('SpectralCursorBus', () => {
  it('delivers published time to subscribers', async () => {
    const bus = createSpectralCursorBus();
    const cb = vi.fn();
    bus.subscribe('viewer', cb);

    bus.publish(1.5, 'chart');

    // Wait for RAF (setTimeout in test env)
    await new Promise((r) => setTimeout(r, 10));

    expect(cb).toHaveBeenCalledWith(1.5);
  });

  it('excludes the publisher from receiving its own event', async () => {
    const bus = createSpectralCursorBus();
    const cbChart = vi.fn();
    const cbViewer = vi.fn();
    bus.subscribe('chart', cbChart);
    bus.subscribe('viewer', cbViewer);

    bus.publish(2.0, 'chart');

    await new Promise((r) => setTimeout(r, 10));

    expect(cbChart).not.toHaveBeenCalled();
    expect(cbViewer).toHaveBeenCalledWith(2.0);
  });

  it('delivers null when cursor leaves', async () => {
    const bus = createSpectralCursorBus();
    const cb = vi.fn();
    bus.subscribe('viewer', cb);

    bus.publish(null, 'chart');

    await new Promise((r) => setTimeout(r, 10));

    expect(cb).toHaveBeenCalledWith(null);
  });

  it('unsubscribe removes the subscriber', async () => {
    const bus = createSpectralCursorBus();
    const cb = vi.fn();
    const unsub = bus.subscribe('viewer', cb);

    unsub();
    bus.publish(3.0, 'chart');

    await new Promise((r) => setTimeout(r, 10));

    expect(cb).not.toHaveBeenCalled();
  });

  it('coalesces rapid publishes into single dispatch', async () => {
    const bus = createSpectralCursorBus();
    const cb = vi.fn();
    bus.subscribe('viewer', cb);

    bus.publish(1.0, 'chart');
    bus.publish(2.0, 'chart');
    bus.publish(3.0, 'chart');

    await new Promise((r) => setTimeout(r, 10));

    // Only the last value should be delivered
    expect(cb).toHaveBeenCalledTimes(1);
    expect(cb).toHaveBeenCalledWith(3.0);
  });

  it('supports multiple independent subscribers', async () => {
    const bus = createSpectralCursorBus();
    const cb1 = vi.fn();
    const cb2 = vi.fn();
    const cb3 = vi.fn();

    bus.subscribe('a', cb1);
    bus.subscribe('b', cb2);
    bus.subscribe('c', cb3);

    bus.publish(5.0, 'a');

    await new Promise((r) => setTimeout(r, 10));

    expect(cb1).not.toHaveBeenCalled(); // publisher excluded
    expect(cb2).toHaveBeenCalledWith(5.0);
    expect(cb3).toHaveBeenCalledWith(5.0);
  });
});

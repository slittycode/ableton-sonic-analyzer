import { describe, it, expect } from 'vitest';

import { ErrorBoundary } from '../../src/components/ErrorBoundary';

// Vitest runs in the `node` environment (no jsdom), so we exercise the
// boundary's capture logic directly rather than rendering it. The fallback UI
// render is covered by tests/smoke/error-boundary.spec.ts, which aborts the
// lazy AnalysisResults chunk and asserts the fallback (alert + actions) renders.
describe('ErrorBoundary', () => {
  it('captures a thrown error into render state via getDerivedStateFromError', () => {
    const error = new Error('AnalysisResults failed to render');
    expect(ErrorBoundary.getDerivedStateFromError(error)).toEqual({ error });
  });

  it('treats a chunk-load failure the same as any other error', () => {
    const chunkError = new Error('Loading chunk 42 failed');
    expect(ErrorBoundary.getDerivedStateFromError(chunkError).error).toBe(chunkError);
  });
});

import { describe, it, expect } from 'vitest';

import { ErrorBoundary } from '../../src/components/ErrorBoundary';

// Vitest runs in the `node` environment (no jsdom), so we exercise the
// boundary's capture logic directly rather than rendering it. The fallback UI
// render itself is NOT exercised by any automated test (smoke flows only cover
// the happy path where AnalysisResults renders); it is checked by the
// type-checker and a ~1-min manual pass (throw inside AnalysisResults, confirm
// the fallback shows with working "Try again" / "Reload page" actions).
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

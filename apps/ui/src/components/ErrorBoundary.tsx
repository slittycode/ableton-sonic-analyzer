import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Optional render-prop fallback. Receives the captured error and a reset callback. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
  /** Heading for the default fallback. */
  title?: string;
  /** Notified when an error is captured (e.g. for diagnostics/telemetry). */
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Catches render and lazy-import failures in its subtree so a single throw (or a
 * chunk-load failure in a lazily-loaded view) cannot blank the entire app.
 *
 * The default fallback is recoverable: "Try again" clears the error state and
 * re-renders the subtree — which recovers a transient *render* error (the lazy
 * module already resolved). It does NOT recover a failed *chunk load*:
 * React.lazy caches the rejected import, so re-rendering re-throws the cached
 * rejection. "Reload page" (a hard reload) is the reliable recovery for a
 * chunk-load failure.
 *
 * Intentionally self-contained (no design-system imports): an error boundary
 * must stay renderable even when the component tree it guards — potentially
 * including shared UI primitives — is what failed.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[ErrorBoundary] subtree render failure', error, info);
    this.props.onError?.(error, info);
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }

    if (this.props.fallback) {
      return this.props.fallback(error, this.reset);
    }

    return (
      <div role="alert" className="space-y-4 rounded-sm border border-error/30 bg-error/5 p-6">
        <div className="space-y-1">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-text-primary">
            {this.props.title ?? 'This view failed to render'}
          </h2>
          <p className="text-sm text-text-secondary">
            Your analysis is safe — retry to re-render it, or reload the page.
          </p>
          {error.message ? (
            <p className="break-words pt-1 font-mono text-xs text-text-secondary">{error.message}</p>
          ) : null}
        </div>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={this.reset}
            className="rounded-sm border border-accent/60 bg-bg-panel px-4 py-2 text-sm text-accent transition-colors hover:bg-accent hover:text-bg-app"
          >
            Try again
          </button>
          <button
            type="button"
            onClick={() => globalThis.location.reload()}
            className="rounded-sm border border-border bg-bg-panel px-4 py-2 text-sm text-text-secondary transition-colors hover:border-accent/40 hover:text-text-primary"
          >
            Reload page
          </button>
        </div>
      </div>
    );
  }
}

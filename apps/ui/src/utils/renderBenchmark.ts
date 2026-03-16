export const BENCHMARK_MARKS = {
  analysisStart: 'sonic-analysis-start',
  analysisResultsReady: 'sonic-analysis-results-ready',
  buildPlanReady: 'sonic-build-plan-ready',
} as const;

type BenchmarkMarkName = (typeof BENCHMARK_MARKS)[keyof typeof BENCHMARK_MARKS];

interface BenchmarkPerformanceLike {
  mark: (name: string) => void;
  clearMarks?: (name?: string) => void;
}

interface BenchmarkWindowLike {
  __SONIC_BENCHMARK__?: boolean;
  performance?: BenchmarkPerformanceLike;
}

function getPerformance(target: BenchmarkWindowLike | undefined): BenchmarkPerformanceLike | null {
  const performanceTarget = target?.performance;
  if (!performanceTarget || typeof performanceTarget.mark !== 'function') {
    return null;
  }
  return performanceTarget;
}

export function isRenderBenchmarkEnabled(target?: BenchmarkWindowLike): boolean {
  return target?.__SONIC_BENCHMARK__ === true;
}

export function startRenderBenchmarkCycle(target?: BenchmarkWindowLike): boolean {
  if (!isRenderBenchmarkEnabled(target)) {
    return false;
  }

  const performanceTarget = getPerformance(target);
  if (!performanceTarget) {
    return false;
  }

  performanceTarget.clearMarks?.(BENCHMARK_MARKS.analysisStart);
  performanceTarget.clearMarks?.(BENCHMARK_MARKS.analysisResultsReady);
  performanceTarget.clearMarks?.(BENCHMARK_MARKS.buildPlanReady);
  performanceTarget.mark(BENCHMARK_MARKS.analysisStart);
  return true;
}

export function markRenderBenchmark(markName: BenchmarkMarkName, target?: BenchmarkWindowLike): boolean {
  if (!isRenderBenchmarkEnabled(target)) {
    return false;
  }

  const performanceTarget = getPerformance(target);
  if (!performanceTarget) {
    return false;
  }

  performanceTarget.mark(markName);
  return true;
}

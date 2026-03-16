export function isSpectrumActive(isPlaying: boolean, isSeeking: boolean): boolean {
  return isPlaying || isSeeking;
}

export function nextPeakValue(previousPeak: number, nextValue: number, dropRate: number): number {
  if (nextValue > previousPeak) {
    return nextValue;
  }

  return Math.max(0, previousPeak - dropRate);
}

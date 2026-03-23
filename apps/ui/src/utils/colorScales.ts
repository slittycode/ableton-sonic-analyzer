/**
 * Shared color-scale utilities for spectral visualizations.
 *
 * The `dbToColor` function maps a normalised 0-1 intensity to a 4-segment
 * color ramp:  dark-blue → cyan → yellow → red.  It is used by
 * ChromaHeatmap, MiniHeatmap, and any future heatmap components.
 */

/** Map a normalised value (0–1) to an RGB color string via a 4-segment ramp. */
export function dbToColor(t: number): string {
  t = Math.max(0, Math.min(1, t));
  if (t < 0.25) {
    const u = t / 0.25;
    return `rgb(${Math.round(u * 10)},${Math.round(u * 20)},${Math.round(40 + u * 80)})`;
  } else if (t < 0.5) {
    const u = (t - 0.25) / 0.25;
    return `rgb(${Math.round(10 + u * 20)},${Math.round(20 + u * 200)},${Math.round(120 + u * 135)})`;
  } else if (t < 0.75) {
    const u = (t - 0.5) / 0.25;
    return `rgb(${Math.round(30 + u * 225)},${Math.round(220 + u * 35)},${Math.round(255 - u * 200)})`;
  } else {
    const u = (t - 0.75) / 0.25;
    return `rgb(${255},${Math.round(255 - u * 140)},${Math.round(55 - u * 55)})`;
  }
}

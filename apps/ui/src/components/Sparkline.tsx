import React, { useEffect, useRef } from 'react';

interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
  className?: string;
}

/**
 * Tiny DPR-aware canvas sparkline — no axes, no labels.
 * Draws a single line path normalised to local min/max.
 */
export const Sparkline = React.memo(function Sparkline({
  values,
  width = 80,
  height = 16,
  color = '#60a5fa',
  className,
}: SparklineProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || values.length < 2) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    let min = Infinity;
    let max = -Infinity;
    for (const v of values) {
      if (v < min) min = v;
      if (v > max) max = v;
    }
    const range = max - min || 1;
    const pad = 1; // 1px vertical padding

    ctx.clearRect(0, 0, width, height);
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.2;
    ctx.lineJoin = 'round';

    for (let i = 0; i < values.length; i++) {
      const x = (i / (values.length - 1)) * width;
      const y = pad + ((1 - (values[i] - min) / range) * (height - pad * 2));
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }, [values, width, height, color]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ width, height, display: 'block' }}
    />
  );
});

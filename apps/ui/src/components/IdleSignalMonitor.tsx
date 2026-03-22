import React, { useEffect, useRef } from 'react';
import { Activity } from 'lucide-react';

export function IdleSignalMonitor() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let startTime: number | null = null;

    const draw = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const elapsed = (timestamp - startTime) / 1000;
      const width = canvas.width;
      const height = canvas.height;
      const centerY = height / 2;

      ctx.fillStyle = '#0a0a0c';
      ctx.fillRect(0, 0, width, height);

      // Faint grid
      ctx.strokeStyle = 'rgba(100, 100, 120, 0.05)';
      ctx.lineWidth = 1;
      for (let y = 0; y < height; y += 20) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }
      for (let x = 0; x < width; x += 40) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }

      // Drifting flat line with subtle glow
      const breathe = 0.15 + Math.sin(elapsed * 0.8) * 0.1;
      ctx.shadowBlur = 6 + Math.sin(elapsed * 0.8) * 4;
      ctx.shadowColor = `rgba(255, 136, 0, ${breathe * 0.3})`;
      ctx.strokeStyle = `rgba(255, 136, 0, ${breathe})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = 0; x < width; x += 2) {
        const drift = Math.sin(x * 0.006 + elapsed * 0.4) * 1.2
          + Math.sin(x * 0.015 + elapsed * 0.7) * 0.5;
        const y = centerY + drift;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Scanlines
      ctx.fillStyle = 'rgba(0, 0, 0, 0.02)';
      for (let y = 0; y < height; y += 2) {
        ctx.fillRect(0, y, width, 1);
      }

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);
    return () => {
      if (animRef.current !== null) cancelAnimationFrame(animRef.current);
    };
  }, []);

  return (
    <div className="h-full flex flex-col rounded-sm m-2 min-h-[150px] overflow-hidden relative">
      <canvas
        ref={canvasRef}
        width={800}
        height={200}
        className="w-full h-full"
      />
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <Activity className="w-6 h-6 mb-2 text-accent/20" />
        <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-text-secondary/30">
          No Signal Detected
        </p>
      </div>
    </div>
  );
}

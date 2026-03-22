import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Radio, Zap, Palette } from 'lucide-react';

// ============================================
// THREE-BAND REACTIVE WAVEFORM VISUALIZER
// ============================================

// Band colors - each frequency band gets its own color
const BAND_COLORS = {
  bass: {
    glow: 'rgba(255, 140, 50, 0.7)',      // Amber/orange
    wave: 'rgba(255, 180, 100, 0.9)',
    core: 'rgba(255, 220, 180, 0.6)',
    name: 'LOW',
  },
  mid: {
    glow: 'rgba(180, 100, 220, 0.7)',      // Violet/purple
    wave: 'rgba(200, 140, 255, 0.9)',
    core: 'rgba(230, 200, 255, 0.6)',
    name: 'MID',
  },
  high: {
    glow: 'rgba(255, 100, 120, 0.7)',      // Sunset/rose
    wave: 'rgba(255, 130, 150, 0.9)',
    core: 'rgba(255, 180, 190, 0.6)',
    name: 'HIGH',
  },
};

type ColorMode = 'three-band' | 'amber' | 'violet' | 'sunset';

interface RetroVisualizerProps {
  analyser: AnalyserNode | null;
  isPlaying: boolean;
  audioBuffer: AudioBuffer | null;
}

export function RetroVisualizer({ analyser, isPlaying, audioBuffer }: RetroVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number | null>(null);
  const beatRef = useRef({ lastBeat: 0, threshold: 0.55, decay: 0 });
  const freqHistoryRef = useRef<number[][]>([]);
  const waveformHistoryRef = useRef<number[][]>([]);
  const frameRef = useRef(0);
  
  const [mode, setMode] = useState<ColorMode>('three-band');
  const modeRef = useRef<ColorMode>('three-band');
  
  // Keep modeRef in sync
  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);
  
  const drawFrame = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const width = canvas.width;
    const height = canvas.height;
    const frame = frameRef.current++;
    const currentMode = modeRef.current;
    
    // Get both frequency and time domain data
    let frequencyData: Uint8Array | null = null;
    let timeData: Uint8Array | null = null;
    
    if (analyser) {
      frequencyData = new Uint8Array(analyser.frequencyBinCount);
      timeData = new Uint8Array(analyser.fftSize);
      analyser.getByteFrequencyData(frequencyData);
      analyser.getByteTimeDomainData(timeData);
    }
    
    // Calculate spectral energy bands
    let bass = 0, mid = 0, high = 0;
    if (frequencyData) {
      const bassRange = frequencyData.slice(0, 6);
      const midRange = frequencyData.slice(6, 24);
      const highRange = frequencyData.slice(24, 48);
      
      bass = bassRange.reduce((a, b) => a + b, 0) / bassRange.length / 255;
      mid = midRange.reduce((a, b) => a + b, 0) / midRange.length / 255;
      high = highRange.reduce((a, b) => a + b, 0) / highRange.length / 255;
      
      // Store frequency history
      freqHistoryRef.current.push(Array.from(frequencyData.slice(0, 48)));
      if (freqHistoryRef.current.length > 60) {
        freqHistoryRef.current.shift();
      }
    }
    
    // Store waveform history
    if (timeData) {
      waveformHistoryRef.current.push(Array.from(timeData));
      if (waveformHistoryRef.current.length > 8) {
        waveformHistoryRef.current.shift();
      }
    }
    
    // Beat detection
    if (bass > beatRef.current.threshold && Date.now() - beatRef.current.lastBeat > 60) {
      beatRef.current.lastBeat = Date.now();
      beatRef.current.decay = 1;
    }
    beatRef.current.decay *= 0.9;
    
    // Clear with fade
    ctx.fillStyle = 'rgba(5, 5, 8, 0.18)';
    ctx.fillRect(0, 0, width, height);
    
    // Draw based on mode (use ref for immediate updates)
    if (currentMode === 'three-band') {
      // Spectral trace background
      drawSpectralTrace(ctx, freqHistoryRef.current, width, height, beatRef.current.decay);
      
      // Three-band waveform layers (back to front: bass, mid, high)
      drawBandWaveform(ctx, timeData, frequencyData, width, height, beatRef.current.decay, frame, 'bass');
      drawBandWaveform(ctx, timeData, frequencyData, width, height, beatRef.current.decay, frame, 'mid');
      drawBandWaveform(ctx, timeData, frequencyData, width, height, beatRef.current.decay, frame, 'high');
    } else {
      // Single-color modes - still band-reactive but unified color
      const theme = getThemeColors(currentMode);
      drawSpectralTrace(ctx, freqHistoryRef.current, width, height, beatRef.current.decay, theme);
      drawWaveformTrails(ctx, waveformHistoryRef.current, width, height, beatRef.current.decay, theme);
      
      // Single-color but band-reactive
      drawBandWaveformUnified(ctx, timeData, frequencyData, width, height, beatRef.current.decay, frame, theme, currentMode);
    }
    
    // CRT effects
    drawCRTEffects(ctx, width, height);
    
    // Draw amplitude scale
    ctx.fillStyle = 'rgba(200, 200, 200, 0.15)';
    ctx.font = '7px monospace';
    ctx.fillText('+100%', 4, 10);
    ctx.fillText('0', 4, height / 2 + 3);
    ctx.fillText('-100%', 4, height - 6);
    
    // Energy indicators with band colors
    ctx.fillStyle = `rgba(255, 140, 50, ${0.3 + bass * 0.5})`;
    ctx.fillText(`LOW:${Math.round(bass * 100)}`, width - 50, 10);
    ctx.fillStyle = `rgba(180, 100, 220, ${0.3 + mid * 0.5})`;
    ctx.fillText(`MID:${Math.round(mid * 100)}`, width - 50, 18);
    ctx.fillStyle = `rgba(255, 100, 120, ${0.3 + high * 0.5})`;
    ctx.fillText(`HIGH:${Math.round(high * 100)}`, width - 50, 26);
    
    // Continue animation
    if (isPlaying) {
      animationRef.current = requestAnimationFrame(drawFrame);
    }
  }, [analyser, isPlaying]);
  
  // Start/stop animation
  useEffect(() => {
    if (isPlaying) {
      if (animationRef.current === null) {
        drawFrame();
      }
    } else {
      if (animationRef.current !== null) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }
    }
    
    return () => {
      if (animationRef.current !== null) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isPlaying, drawFrame]);
  
  // Draw static when not playing
  useEffect(() => {
    if (!isPlaying && canvasRef.current) {
      const ctx = canvasRef.current.getContext('2d');
      if (ctx) {
        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, canvasRef.current.width, canvasRef.current.height);
        
        // Grid
        ctx.strokeStyle = 'rgba(100, 100, 120, 0.08)';
        ctx.lineWidth = 1;
        for (let y = 0; y < canvasRef.current.height; y += 15) {
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(canvasRef.current.width, y);
          ctx.stroke();
        }
        for (let x = 0; x < canvasRef.current.width; x += 30) {
          ctx.beginPath();
          ctx.moveTo(x, 0);
          ctx.lineTo(x, canvasRef.current.height);
          ctx.stroke();
        }
        
        ctx.fillStyle = 'rgba(150, 150, 170, 0.3)';
        ctx.font = '10px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('▶ PLAY TO ACTIVATE', canvasRef.current.width / 2, canvasRef.current.height / 2);
        ctx.textAlign = 'left';
      }
    }
  }, [isPlaying]);
  
  return (
    <div className="bg-bg-card border border-border rounded-sm p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Radio className="w-4 h-4 text-accent" />
          <span className="text-xs font-bold text-text-primary tracking-widest uppercase">Waveform Visualizer</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Zap className={`w-3 h-3 ${isPlaying ? 'text-accent' : 'text-text-secondary/30'}`} />
          <span className="text-[8px] font-mono uppercase tracking-wider text-text-secondary/70">
            {isPlaying ? 'ACTIVE' : 'STANDBY'}
          </span>
        </div>
      </div>
      
      {/* Mode selector */}
      <div className="flex items-center gap-2 mb-2">
        <Palette className="w-3 h-3 text-text-secondary" />
        <div className="flex gap-1">
          <button
            onClick={() => setMode('three-band')}
            className={`px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider rounded-sm border transition-colors ${
              mode === 'three-band'
                ? 'bg-accent text-bg-app border-accent'
                : 'bg-bg-panel text-text-secondary border-border hover:border-accent/40'
            }`}
          >
            3-Band
          </button>
          <button
            onClick={() => setMode('amber')}
            className={`px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider rounded-sm border transition-colors ${
              mode === 'amber'
                ? 'bg-orange-500 text-bg-app border-orange-500'
                : 'bg-bg-panel text-text-secondary border-border hover:border-orange-400'
            }`}
          >
            Amber
          </button>
          <button
            onClick={() => setMode('violet')}
            className={`px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider rounded-sm border transition-colors ${
              mode === 'violet'
                ? 'bg-purple-500 text-bg-app border-purple-500'
                : 'bg-bg-panel text-text-secondary border-border hover:border-purple-400'
            }`}
          >
            Violet
          </button>
          <button
            onClick={() => setMode('sunset')}
            className={`px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider rounded-sm border transition-colors ${
              mode === 'sunset'
                ? 'bg-rose-500 text-bg-app border-rose-500'
                : 'bg-bg-panel text-text-secondary border-border hover:border-rose-400'
            }`}
          >
            Sunset
          </button>
        </div>
      </div>
      
      <div className="relative bg-black rounded-sm overflow-hidden" style={{ height: 120 }}>
        <canvas
          ref={canvasRef}
          width={800}
          height={120}
          className="w-full h-full"
        />
      </div>
    </div>
  );
}

// ============================================
// THREE-BAND WAVEFORM
// ============================================

function drawBandWaveform(
  ctx: CanvasRenderingContext2D,
  timeData: Uint8Array | null,
  frequencyData: Uint8Array | null,
  width: number,
  height: number,
  beatIntensity: number,
  frame: number,
  band: 'bass' | 'mid' | 'high'
) {
  if (!timeData) return;
  
  const colors = BAND_COLORS[band];
  const centerY = height / 2;
  const sliceWidth = width / timeData.length;
  
  // Get band-specific energy from frequency data
  let bandEnergy = 0;
  let bandSmoothed = 0;
  
  if (frequencyData) {
    // Define frequency ranges for each band
    let startBin: number, endBin: number;
    if (band === 'bass') {
      startBin = 0; endBin = 6;  // 0-~200Hz
    } else if (band === 'mid') {
      startBin = 6; endBin = 24; // ~200-2000Hz
    } else {
      startBin = 24; endBin = 48; // 2000Hz+
    }
    
    const bandRange = frequencyData.slice(startBin, endBin);
    bandEnergy = bandRange.reduce((a, b) => a + b, 0) / bandRange.length / 255;
    
    // Smooth the energy a bit
    bandSmoothed = bandEnergy;
  }
  
  // Base amplitude for each band
  const baseAmp = band === 'bass' ? 0.40 : band === 'mid' ? 0.32 : 0.26;
  
  // Amplitude reacts to THIS band's energy (not all bands)
  const amplitude = baseAmp * (0.7 + bandSmoothed * 0.5);
  
  // Create band-specific waveform modulation
  const modulationScale = band === 'bass' ? 1.15 : band === 'mid' ? 1.0 : 0.85;
  
  // Outer glow - size reacts to this band's energy
  const glowSize = 12 + beatIntensity * 20 + bandSmoothed * 25;
  ctx.shadowBlur = glowSize;
  ctx.shadowColor = colors.glow;
  ctx.strokeStyle = colors.wave.replace('0.9', `${0.25 + bandSmoothed * 0.4}`);
  ctx.lineWidth = 3 + beatIntensity * 1.5 + bandSmoothed * 2;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  
  // Draw waveform with band-specific filtering
  ctx.beginPath();
  timeData.forEach((sample, i) => {
    const v = sample / 128.0;
    
    // Apply band-specific modulation
    let modulated = v;
    
    if (band === 'bass') {
      // Bass: smooth, emphasize low-frequency movement
      modulated = v * modulationScale * (1 + bandSmoothed * 0.15);
    } else if (band === 'mid') {
      // Mid: slight offset, emphasize transient content
      modulated = v * modulationScale * (1 + bandSmoothed * 0.1);
    } else {
      // High: faster oscillation, more reactive to high energy
      const shimmer = Math.sin(i * 0.3 + frame * 0.08) * bandSmoothed * 0.15;
      modulated = v * modulationScale + shimmer;
    }
    
    const y = centerY + (modulated - 1) * height * amplitude;
    const x = i * sliceWidth;
    
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  
  // Main wave for this band
  ctx.shadowBlur = 6 + beatIntensity * 10 + bandSmoothed * 8;
  ctx.shadowColor = colors.wave;
  ctx.strokeStyle = colors.wave.replace('0.9', `${0.7 + bandSmoothed * 0.25}`);
  ctx.lineWidth = 1.5 + bandSmoothed * 1;
  
  ctx.beginPath();
  timeData.forEach((sample, i) => {
    const v = sample / 128.0;
    let modulated = v;
    
    if (band === 'bass') {
      modulated = v * modulationScale * (1 + bandSmoothed * 0.15);
    } else if (band === 'mid') {
      modulated = v * modulationScale * (1 + bandSmoothed * 0.1);
    } else {
      const shimmer = Math.sin(i * 0.3 + frame * 0.08) * bandSmoothed * 0.15;
      modulated = v * modulationScale + shimmer;
    }
    
    const y = centerY + (modulated - 1) * height * amplitude;
    const x = i * sliceWidth;
    
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  
  // Bright core - intensity based on this band's energy
  ctx.shadowBlur = 3 + beatIntensity * 5;
  ctx.shadowColor = colors.core;
  ctx.strokeStyle = colors.core.replace('0.6', `${0.2 + bandSmoothed * 0.35}`);
  ctx.lineWidth = 0.5 + bandSmoothed * 0.3;
  
  ctx.beginPath();
  timeData.forEach((sample, i) => {
    const v = sample / 128.0;
    let modulated = v;
    
    if (band === 'bass') {
      modulated = v * modulationScale * (1 + bandSmoothed * 0.15);
    } else if (band === 'mid') {
      modulated = v * modulationScale * (1 + bandSmoothed * 0.1);
    } else {
      const shimmer = Math.sin(i * 0.3 + frame * 0.08) * bandSmoothed * 0.15;
      modulated = v * modulationScale + shimmer;
    }
    
    const y = centerY + (modulated - 1) * height * amplitude;
    const x = i * sliceWidth;
    
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  
  ctx.shadowBlur = 0;
}

// ============================================
// UNIFIED BAND-REACTIVE WAVEFORM (single color)
// ============================================

function drawBandWaveformUnified(
  ctx: CanvasRenderingContext2D,
  timeData: Uint8Array | null,
  frequencyData: Uint8Array | null,
  width: number,
  height: number,
  beatIntensity: number,
  frame: number,
  theme: { glow: string; mainWave: string; mainWaveGlow: string; core: string },
  mode: ColorMode
) {
  if (!timeData || !frequencyData) return;
  
  const centerY = height / 2;
  const sliceWidth = width / timeData.length;
  
  // Get all three band energies
  const bassRange = frequencyData.slice(0, 6);
  const midRange = frequencyData.slice(6, 24);
  const highRange = frequencyData.slice(24, 48);
  
  const bass = bassRange.reduce((a, b) => a + b, 0) / bassRange.length / 255;
  const mid = midRange.reduce((a, b) => a + b, 0) / midRange.length / 255;
  const high = highRange.reduce((a, b) => a + b, 0) / highRange.length / 255;
  
  // Map mode to band: amber=bass, violet=mid, sunset=high
  const bandEnergy = mode === 'amber' ? bass : mode === 'violet' ? mid : high;
  
  // Amplitude varies by this band's energy
  const amplitude = 0.35 + bandEnergy * 0.12;
  
  // Outer glow - reacts to this band's energy
  const glowSize = 18 + beatIntensity * 28 + bandEnergy * 25;
  ctx.shadowBlur = glowSize;
  ctx.shadowColor = theme.glow;
  ctx.strokeStyle = theme.mainWave.replace('0.85', `${0.28 + bandEnergy * 0.3}`);
  ctx.lineWidth = 4 + beatIntensity * 2;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  
  ctx.beginPath();
  timeData.forEach((sample, i) => {
    const v = sample / 128.0;
    
    // Apply modulation based on which band this mode represents
    let modulated: number;
    if (mode === 'amber') {
      // Bass: smooth expansion
      modulated = v * (1 + bandEnergy * 0.18);
    } else if (mode === 'violet') {
      // Mid: medium response
      modulated = v * (1 + bandEnergy * 0.12);
    } else {
      // High: shimmer oscillation
      const shimmer = Math.sin(i * 0.3 + frame * 0.08) * bandEnergy * 0.15;
      modulated = v + shimmer;
    }
    
    const y = centerY + (modulated - 1) * height * amplitude;
    const x = i * sliceWidth;
    
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  
  // Main wave
  ctx.shadowBlur = 8 + beatIntensity * 12;
  ctx.shadowColor = theme.mainWaveGlow;
  ctx.strokeStyle = theme.mainWave;
  ctx.lineWidth = 1.8 + beatIntensity * 1 + bandEnergy * 0.6;
  
  ctx.beginPath();
  timeData.forEach((sample, i) => {
    const v = sample / 128.0;
    let modulated: number;
    if (mode === 'amber') {
      modulated = v * (1 + bandEnergy * 0.18);
    } else if (mode === 'violet') {
      modulated = v * (1 + bandEnergy * 0.12);
    } else {
      const shimmer = Math.sin(i * 0.3 + frame * 0.08) * bandEnergy * 0.15;
      modulated = v + shimmer;
    }
    
    const y = centerY + (modulated - 1) * height * amplitude;
    const x = i * sliceWidth;
    
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  
  // Bright core
  ctx.shadowBlur = 4 + beatIntensity * 6;
  ctx.shadowColor = theme.core;
  ctx.strokeStyle = theme.core;
  ctx.lineWidth = 0.6 + beatIntensity * 0.3 + bandEnergy * 0.25;
  
  ctx.beginPath();
  timeData.forEach((sample, i) => {
    const v = sample / 128.0;
    let modulated: number;
    if (mode === 'amber') {
      modulated = v * (1 + bandEnergy * 0.18);
    } else if (mode === 'violet') {
      modulated = v * (1 + bandEnergy * 0.12);
    } else {
      const shimmer = Math.sin(i * 0.3 + frame * 0.08) * bandEnergy * 0.15;
      modulated = v + shimmer;
    }
    
    const y = centerY + (modulated - 1) * height * amplitude;
    const x = i * sliceWidth;
    
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  
  ctx.shadowBlur = 0;
}

// ============================================
// SINGLE-COLOR MODES
// ============================================

function getThemeColors(mode: ColorMode) {
  const themes = {
    amber: {
      background: 'rgba(15, 8, 0, 0.2)',
      traceHue: 25,
      glow: 'rgba(255, 140, 50, 0.6)',
      mainWave: 'rgba(255, 180, 80, 0.85)',
      mainWaveGlow: '#ff9933',
      core: 'rgba(255, 220, 180, 0.5)',
    },
    violet: {
      background: 'rgba(10, 5, 15, 0.2)',
      traceHue: 280,
      glow: 'rgba(180, 100, 255, 0.6)',
      mainWave: 'rgba(200, 140, 255, 0.85)',
      mainWaveGlow: '#aa66ff',
      core: 'rgba(230, 200, 255, 0.5)',
    },
    sunset: {
      background: 'rgba(12, 5, 8, 0.2)',
      traceHue: 350,
      glow: 'rgba(255, 100, 120, 0.6)',
      mainWave: 'rgba(255, 130, 150, 0.85)',
      mainWaveGlow: '#ff6677',
      core: 'rgba(255, 180, 190, 0.5)',
    },
  };
  return themes[mode as keyof typeof themes] || themes.amber;
}

function drawSpectralTrace(
  ctx: CanvasRenderingContext2D,
  freqHistory: number[][],
  width: number,
  height: number,
  beatIntensity: number,
  theme?: { traceHue: number }
) {
  if (freqHistory.length < 2) return;
  
  const centerY = height / 2;
  const traceHeight = height * 0.28;
  const baseHue = theme?.traceHue ?? 30;
  
  freqHistory.forEach((frame, frameIndex) => {
    const age = frameIndex / freqHistory.length;
    const alpha = age * 0.08;
    const xOffset = width - (freqHistory.length - frameIndex) * (width / freqHistory.length);
    
    frame.forEach((value, bandIndex) => {
      const normalized = value / 255;
      const bandPos = bandIndex / frame.length;
      const y = centerY - traceHeight + bandPos * traceHeight * 2;
      
      const hue = baseHue + bandPos * 50;
      const lightness = 18 + normalized * 28 + beatIntensity * 10;
      
      ctx.fillStyle = `hsla(${hue}, 50%, ${lightness}%, ${alpha * normalized})`;
      ctx.fillRect(xOffset, y, width / freqHistory.length + 1, 2);
    });
  });
}

function drawWaveformTrails(
  ctx: CanvasRenderingContext2D,
  waveformHistory: number[][],
  width: number,
  height: number,
  beatIntensity: number,
  theme: { glow: string }
) {
  if (waveformHistory.length < 2) return;
  
  const centerY = height / 2;
  const sliceWidth = width / (waveformHistory[0]?.length || 1);
  
  waveformHistory.slice(0, -1).forEach((data, trailIndex) => {
    const age = trailIndex / waveformHistory.length;
    const alpha = (1 - age) * 0.04;
    const yOffset = Math.sin(age * Math.PI * 2) * 2;
    
    ctx.strokeStyle = theme.glow.replace('0.6', `${alpha + beatIntensity * 0.01}`);
    ctx.lineWidth = Math.max(0.5, 1.5 - age * 1.5);
    ctx.beginPath();
    
    data.forEach((sample, i) => {
      const v = sample / 128.0;
      const y = centerY + (v - 1) * height * 0.34 + yOffset;
      const x = i * sliceWidth;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    
    ctx.stroke();
  });
}

function drawMainWaveform(
  ctx: CanvasRenderingContext2D,
  timeData: Uint8Array | null,
  width: number,
  height: number,
  bass: number,
  mid: number,
  high: number,
  beatIntensity: number,
  frame: number,
  theme: { glow: string; mainWave: string; mainWaveGlow: string; core: string }
) {
  if (!timeData) return;
  
  const centerY = height / 2;
  const sliceWidth = width / timeData.length;
  const amplitude = 0.32 + (bass + mid) * 0.1;
  
  // Outer glow
  ctx.shadowBlur = 18 + beatIntensity * 25;
  ctx.shadowColor = theme.glow;
  ctx.strokeStyle = theme.mainWave.replace('0.85', `${0.32 + beatIntensity * 0.2}`);
  ctx.lineWidth = 4 + beatIntensity * 2;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  
  ctx.beginPath();
  timeData.forEach((sample, i) => {
    const v = sample / 128.0;
    const y = centerY + (v - 1) * height * amplitude;
    const x = i * sliceWidth;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  
  // Main wave
  ctx.shadowBlur = 8 + beatIntensity * 12;
  ctx.shadowColor = theme.mainWaveGlow;
  ctx.strokeStyle = theme.mainWave;
  ctx.lineWidth = 1.8 + beatIntensity * 1;
  
  ctx.beginPath();
  timeData.forEach((sample, i) => {
    const v = sample / 128.0;
    const y = centerY + (v - 1) * height * amplitude;
    const x = i * sliceWidth;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  
  // Core
  ctx.shadowBlur = 4 + beatIntensity * 6;
  ctx.shadowColor = theme.core;
  ctx.strokeStyle = theme.core;
  ctx.lineWidth = 0.7 + beatIntensity * 0.3;
  
  ctx.beginPath();
  timeData.forEach((sample, i) => {
    const v = sample / 128.0;
    const y = centerY + (v - 1) * height * amplitude;
    const x = i * sliceWidth;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  
  ctx.shadowBlur = 0;
}

// ============================================
// CRT EFFECTS
// ============================================

function drawCRTEffects(ctx: CanvasRenderingContext2D, width: number, height: number) {
  // Scanlines
  ctx.fillStyle = 'rgba(0, 0, 0, 0.025)';
  for (let y = 0; y < height; y += 2) {
    ctx.fillRect(0, y, width, 1);
  }
  
  // Vignette
  const vignetteGradient = ctx.createRadialGradient(
    width / 2, height / 2, height * 0.15,
    width / 2, height / 2, width * 0.6
  );
  vignetteGradient.addColorStop(0, 'rgba(0, 0, 0, 0)');
  vignetteGradient.addColorStop(0.7, 'rgba(0, 0, 0, 0.1)');
  vignetteGradient.addColorStop(1, 'rgba(0, 0, 0, 0.35)');
  ctx.fillStyle = vignetteGradient;
  ctx.fillRect(0, 0, width, height);
}

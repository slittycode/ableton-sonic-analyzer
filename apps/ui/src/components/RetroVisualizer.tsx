import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Zap } from 'lucide-react';

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

const WAVEFORM_DISPLAY_SCALE = 0.75;

type ColorMode = 'three-band' | 'amber' | 'violet' | 'sunset';

interface RetroVisualizerProps {
  analyser: AnalyserNode | null;
  isPlaying: boolean;
  audioBuffer: AudioBuffer | null;
  onBeat?: () => void;
  currentTime?: number;
  duration?: number;
}

export function RetroVisualizer({ analyser, isPlaying, audioBuffer, onBeat, currentTime, duration }: RetroVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number | null>(null);
  const beatRef = useRef({ lastBeat: 0, threshold: 0.55, decay: 0 });
  const freqHistoryRef = useRef<number[][]>([]);
  const waveformHistoryRef = useRef<number[][]>([]);
  const frameRef = useRef(0);
  
  const [mode, setMode] = useState<ColorMode>('three-band');
  const modeRef = useRef<ColorMode>('three-band');
  const onBeatRef = useRef(onBeat);
  const currentTimeRef = useRef(currentTime ?? 0);
  const durationRef = useRef(duration ?? 0);
  
  useEffect(() => { onBeatRef.current = onBeat; }, [onBeat]);
  useEffect(() => { currentTimeRef.current = currentTime ?? 0; }, [currentTime]);
  useEffect(() => { durationRef.current = duration ?? 0; }, [duration]);
  useEffect(() => { modeRef.current = mode; }, [mode]);
  
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
      onBeatRef.current?.();
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
      const theme = getThemeColors(currentMode);
      const selectedBand = currentMode === 'amber' ? 'bass' : currentMode === 'violet' ? 'mid' : 'high';
      drawSpectralTrace(ctx, freqHistoryRef.current, width, height, beatRef.current.decay, theme);
      drawBandWaveform(ctx, timeData, frequencyData, width, height, beatRef.current.decay, frame, selectedBand);
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
    
    // (2) Time readout overlay
    const ct = currentTimeRef.current;
    const dur = durationRef.current;
    if (dur > 0) {
      const fmtTime = (s: number) => `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}`;
      ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
      ctx.font = '9px monospace';
      ctx.textAlign = 'right';
      ctx.fillText(`${fmtTime(ct)} / ${fmtTime(dur)}`, width - 6, height - 6);
      ctx.textAlign = 'left';
    }
    
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
  
  // Idle pulse animation when not playing
  const idleAnimRef = useRef<number | null>(null);
  
  useEffect(() => {
    if (isPlaying) {
      if (idleAnimRef.current !== null) {
        cancelAnimationFrame(idleAnimRef.current);
        idleAnimRef.current = null;
      }
      return;
    }
    
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    let startTime: number | null = null;
    
    const drawIdle = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const elapsed = (timestamp - startTime) / 1000;
      const width = canvas.width;
      const height = canvas.height;
      const centerY = height / 2;
      
      ctx.fillStyle = '#050508';
      ctx.fillRect(0, 0, width, height);
      
      // Grid
      ctx.strokeStyle = 'rgba(100, 100, 120, 0.06)';
      ctx.lineWidth = 1;
      for (let y = 0; y < height; y += 15) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }
      for (let x = 0; x < width; x += 30) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      
      // Breathing center line with glow
      const breathe = 0.3 + Math.sin(elapsed * Math.PI) * 0.25;
      ctx.shadowBlur = 8 + Math.sin(elapsed * Math.PI) * 6;
      ctx.shadowColor = `rgba(255, 136, 0, ${breathe * 0.4})`;
      ctx.strokeStyle = `rgba(255, 136, 0, ${breathe})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = 0; x < width; x += 2) {
        const drift = Math.sin(x * 0.008 + elapsed * 0.5) * 1.5;
        const y = centerY + drift;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.shadowBlur = 0;
      
      // Label
      ctx.fillStyle = `rgba(150, 150, 170, ${0.2 + Math.sin(elapsed * Math.PI) * 0.1})`;
      ctx.font = '9px monospace';
      ctx.textAlign = 'center';
      ctx.fillText('STANDBY', width / 2, centerY + 20);
      ctx.textAlign = 'left';
      
      drawCRTEffects(ctx, width, height);
      
      idleAnimRef.current = requestAnimationFrame(drawIdle);
    };
    
    idleAnimRef.current = requestAnimationFrame(drawIdle);
    
    return () => {
      if (idleAnimRef.current !== null) {
        cancelAnimationFrame(idleAnimRef.current);
        idleAnimRef.current = null;
      }
    };
  }, [isPlaying]);
  
  const COLOR_MODES: { id: ColorMode; css: string; activeCss: string; label: string; icon: string }[] = [
    { id: 'three-band', css: 'border-accent/40', activeCss: 'border-accent bg-accent/20 shadow-[0_0_6px_rgba(255,136,0,0.4)]', label: '3-BND', icon: '|||' },
    { id: 'amber', css: 'border-orange-500/40', activeCss: 'border-orange-500 bg-orange-500/20 shadow-[0_0_6px_rgba(249,115,22,0.4)]', label: 'AMB', icon: '~' },
    { id: 'violet', css: 'border-purple-500/40', activeCss: 'border-purple-500 bg-purple-500/20 shadow-[0_0_6px_rgba(168,85,247,0.4)]', label: 'VIO', icon: '~' },
    { id: 'sunset', css: 'border-rose-500/40', activeCss: 'border-rose-500 bg-rose-500/20 shadow-[0_0_6px_rgba(244,63,94,0.4)]', label: 'SUN', icon: '~' },
  ];
  
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1.5">
          <Zap className={`w-3 h-3 ${isPlaying ? 'text-accent' : 'text-text-secondary/30'}`} />
          <span className="text-[8px] font-mono uppercase tracking-wider text-text-secondary/70">
            {isPlaying ? 'ACTIVE' : 'STANDBY'}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {COLOR_MODES.map((cm) => (
            <button
              key={cm.id}
              onClick={() => setMode(cm.id)}
              title={cm.label}
              className={`px-1.5 py-0.5 rounded-sm border text-[7px] font-mono uppercase tracking-wider transition-all ${
                mode === cm.id
                  ? `${cm.activeCss} text-text-primary`
                  : `${cm.css} bg-transparent text-text-secondary/50 hover:text-text-secondary/80 hover:bg-white/5`
              }`}
            >
              {cm.label}
            </button>
          ))}
        </div>
      </div>
      
      {/* (3) Band legend — live-reactive brightness for LOW/MID/HIGH */}
      <div className="relative bg-black rounded-sm overflow-hidden" style={{ height: 160 }}>
        <canvas
          ref={canvasRef}
          width={800}
          height={160}
          className="w-full h-full"
        />
      </div>
      {mode === 'three-band' && (
        <BandLegend analyser={analyser} isPlaying={isPlaying} />
      )}
    </div>
  );
}

// ============================================
// (3) BAND LEGEND — live-reactive brightness
// ============================================

function BandLegend({ analyser, isPlaying }: { analyser: AnalyserNode | null; isPlaying: boolean }) {
  const [levels, setLevels] = useState({ bass: 0, mid: 0, high: 0 });
  const animRef = useRef<number | null>(null);

  useEffect(() => {
    if (!isPlaying || !analyser) {
      setLevels({ bass: 0, mid: 0, high: 0 });
      if (animRef.current !== null) cancelAnimationFrame(animRef.current);
      animRef.current = null;
      return;
    }

    const buf = new Uint8Array(analyser.frequencyBinCount);
    let prevBass = 0, prevMid = 0, prevHigh = 0;

    const tick = () => {
      analyser.getByteFrequencyData(buf);
      const bassRaw = Array.from(buf.slice(0, 6)).reduce((a, b) => a + b, 0) / 6 / 255;
      const midRaw = Array.from(buf.slice(6, 24)).reduce((a, b) => a + b, 0) / 18 / 255;
      const highRaw = Array.from(buf.slice(24, 48)).reduce((a, b) => a + b, 0) / 24 / 255;
      prevBass += (bassRaw - prevBass) * 0.3;
      prevMid += (midRaw - prevMid) * 0.3;
      prevHigh += (highRaw - prevHigh) * 0.3;
      setLevels({ bass: prevBass, mid: prevMid, high: prevHigh });
      animRef.current = requestAnimationFrame(tick);
    };

    animRef.current = requestAnimationFrame(tick);
    return () => { if (animRef.current !== null) cancelAnimationFrame(animRef.current); };
  }, [analyser, isPlaying]);

  const bands: { key: keyof typeof levels; label: string; color: string; glowColor: string }[] = [
    { key: 'bass', label: 'LOW', color: 'rgb(255, 140, 50)', glowColor: 'rgba(255, 140, 50, 0.5)' },
    { key: 'mid', label: 'MID', color: 'rgb(180, 100, 220)', glowColor: 'rgba(180, 100, 220, 0.5)' },
    { key: 'high', label: 'HIGH', color: 'rgb(255, 100, 120)', glowColor: 'rgba(255, 100, 120, 0.5)' },
  ];

  return (
    <div className="flex items-center gap-3 mt-1.5 px-1">
      {bands.map((b) => {
        const level = levels[b.key];
        const opacity = isPlaying ? 0.3 + level * 0.7 : 0.15;
        return (
          <div key={b.key} className="flex items-center gap-1.5">
            <div
              className="w-1.5 h-1.5 rounded-full transition-opacity duration-75"
              style={{
                backgroundColor: b.color,
                opacity,
                boxShadow: isPlaying && level > 0.3 ? `0 0 4px ${b.glowColor}` : 'none',
              }}
            />
            <span
              className="text-[7px] font-mono uppercase tracking-wider transition-opacity duration-75"
              style={{ color: b.color, opacity }}
            >
              {b.label}
            </span>
            {isPlaying && (
              <span
                className="text-[7px] font-mono tabular-nums transition-opacity duration-75"
                style={{ color: b.color, opacity: opacity * 0.7 }}
              >
                {Math.round(level * 100)}
              </span>
            )}
          </div>
        );
      })}
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
  const amplitude = baseAmp * (0.7 + bandSmoothed * 0.5) * WAVEFORM_DISPLAY_SCALE;
  
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

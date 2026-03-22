import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import WaveSurfer from 'wavesurfer.js';
import { Play, Pause, Loader2, Activity, Radio, Layers, BarChart3, Sparkles } from 'lucide-react';
import { RetroVisualizer } from './RetroVisualizer';

interface AudioVisualizationStackProps {
  audioUrl: string | null;
  audioFile?: File | null;
}

// ============================================
// SHARED AUDIO CONTEXT PROVIDER
// ============================================

interface AudioData {
  audioBuffer: AudioBuffer;
  audioContext: AudioContext;
  peakDb: number;
  rmsDb: number;
  frequencyBalance: number[];
  spectrogramData: Float32Array[];
  stereoCorrelation: number[];
  duration: number;
  sampleRate: number;
  channels: number;
  fileSize: number;
}

async function decodeAndAnalyzeAudio(file: File): Promise<AudioData> {
  const arrayBuffer = await file.arrayBuffer();
  const audioContext = new AudioContext();
  const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
  
  const leftChannel = audioBuffer.getChannelData(0);
  const rightChannel = audioBuffer.numberOfChannels > 1 ? audioBuffer.getChannelData(1) : leftChannel;
  
  // Peak and RMS
  let peak = 0, rmsSum = 0;
  for (let i = 0; i < leftChannel.length; i++) {
    const abs = Math.abs(leftChannel[i]);
    if (abs > peak) peak = abs;
    rmsSum += leftChannel[i] ** 2;
  }
  const rms = Math.sqrt(rmsSum / leftChannel.length);
  const peakDb = 20 * Math.log10(Math.max(peak, 1e-10));
  const rmsDb = 20 * Math.log10(Math.max(rms, 1e-10));
  
  // Frequency balance (average spectrum)
  const frequencyBalance = computeAverageSpectrum(leftChannel, audioBuffer.sampleRate);
  
  // Spectrogram data
  const spectrogramData = computeSpectrogram(leftChannel, audioBuffer.sampleRate);
  
  // Stereo correlation over time
  const stereoCorrelation = computeStereoCorrelation(leftChannel, rightChannel);
  
  return {
    audioBuffer,
    audioContext,
    peakDb,
    rmsDb,
    frequencyBalance,
    spectrogramData,
    stereoCorrelation,
    duration: audioBuffer.duration,
    sampleRate: audioBuffer.sampleRate,
    channels: audioBuffer.numberOfChannels,
    fileSize: file.size,
  };
}

function computeAverageSpectrum(samples: Float32Array, sampleRate: number): number[] {
  const fftSize = 2048;
  const bands = 12; // Sub, Bass, Low-Mids, Mids, etc.
  const bandEnergies = new Array(bands).fill(0);
  let frameCount = 0;
  
  // Simplified FFT-based spectrum (would use proper FFT in production)
  for (let i = 0; i < samples.length - fftSize; i += fftSize * 4) {
    for (let b = 0; b < bands; b++) {
      const start = Math.floor((b / bands) * fftSize);
      const end = Math.floor(((b + 1) / bands) * fftSize);
      let sum = 0;
      for (let j = start; j < end; j++) {
        sum += Math.abs(samples[i + j]);
      }
      bandEnergies[b] += sum / (end - start);
    }
    frameCount++;
  }
  
  return bandEnergies.map(e => e / Math.max(frameCount, 1));
}

function computeSpectrogram(samples: Float32Array, sampleRate: number): Float32Array[] {
  const fftSize = 2048;
  const hopSize = 512;
  const spectrogram: Float32Array[] = [];
  
  // Simplified spectrogram computation
  // In production, would use proper FFT via OfflineAudioContext or dsp.js
  const numFrames = Math.floor((samples.length - fftSize) / hopSize);
  const binsPerFrame = 64;
  
  for (let frame = 0; frame < Math.min(numFrames, 800); frame++) {
    const start = frame * hopSize;
    const freqData = new Float32Array(binsPerFrame);
    
    // Simplified magnitude calculation per frequency band
    for (let bin = 0; bin < binsPerFrame; bin++) {
      let sum = 0;
      const binStart = Math.floor((bin / binsPerFrame) * fftSize);
      const binEnd = Math.floor(((bin + 1) / binsPerFrame) * fftSize);
      for (let i = binStart; i < binEnd && start + i < samples.length; i++) {
        sum += Math.abs(samples[start + i]);
      }
      freqData[bin] = sum / Math.max(binEnd - binStart, 1);
    }
    
    spectrogram.push(freqData);
  }
  
  return spectrogram;
}

function computeStereoCorrelation(left: Float32Array, right: Float32Array): number[] {
  const windowSize = 4096;
  const hopSize = 8192;
  const correlations: number[] = [];
  
  for (let i = 0; i < left.length - windowSize; i += hopSize) {
    let sumL = 0, sumR = 0, sumLR = 0;
    for (let j = 0; j < windowSize; j++) {
      sumL += left[i + j] ** 2;
      sumR += right[i + j] ** 2;
      sumLR += left[i + j] * right[i + j];
    }
    const corr = sumLR / Math.sqrt(Math.max(sumL * sumR, 1e-10));
    correlations.push(Math.max(-1, Math.min(1, corr)));
  }
  
  return correlations;
}

// ============================================
// VISUALIZATION A: METADATA + SPECTRUM BAR
// ============================================

function VisualizationA({ data, currentTime }: { data: AudioData; currentTime: number }) {
  const formatDuration = (s: number) => {
    const mins = Math.floor(s / 60);
    const secs = Math.floor(s % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };
  
  const formatSize = (bytes: number) => {
    if (bytes > 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / 1024).toFixed(0)} KB`;
  };
  
  const maxFreq = Math.max(...data.frequencyBalance, 0.001);
  
  return (
    <div className="bg-bg-card border border-border rounded-sm p-3">
      <div className="flex items-center gap-2 mb-3">
        <BarChart3 className="w-4 h-4 text-accent" />
        <span className="text-xs font-bold text-text-primary tracking-widest uppercase">Option A: Metadata + Spectrum</span>
      </div>
      
      {/* Metadata Grid */}
      <div className="grid grid-cols-4 gap-2 mb-3">
        <div className="bg-bg-surface p-2 rounded-sm text-center">
          <div className="text-[9px] font-mono text-text-secondary uppercase">Duration</div>
          <div className="text-sm font-bold text-text-primary">{formatDuration(data.duration)}</div>
        </div>
        <div className="bg-bg-surface p-2 rounded-sm text-center">
          <div className="text-[9px] font-mono text-text-secondary uppercase">Sample Rate</div>
          <div className="text-sm font-bold text-text-primary">{(data.sampleRate / 1000).toFixed(1)} kHz</div>
        </div>
        <div className="bg-bg-surface p-2 rounded-sm text-center">
          <div className="text-[9px] font-mono text-text-secondary uppercase">Channels</div>
          <div className="text-sm font-bold text-text-primary">{data.channels === 2 ? 'Stereo' : 'Mono'}</div>
        </div>
        <div className="bg-bg-surface p-2 rounded-sm text-center">
          <div className="text-[9px] font-mono text-text-secondary uppercase">File Size</div>
          <div className="text-sm font-bold text-text-primary">{formatSize(data.fileSize)}</div>
        </div>
        <div className="bg-bg-surface p-2 rounded-sm text-center">
          <div className="text-[9px] font-mono text-text-secondary uppercase">Peak</div>
          <div className="text-sm font-bold text-text-primary">{data.peakDb.toFixed(1)} dB</div>
        </div>
        <div className="bg-bg-surface p-2 rounded-sm text-center">
          <div className="text-[9px] font-mono text-text-secondary uppercase">RMS</div>
          <div className="text-sm font-bold text-text-primary">{data.rmsDb.toFixed(1)} dB</div>
        </div>
        <div className="bg-bg-surface p-2 rounded-sm text-center col-span-2">
          <div className="text-[9px] font-mono text-text-secondary uppercase">Bitrate (est.)</div>
          <div className="text-sm font-bold text-text-primary">{Math.round((data.fileSize * 8) / data.duration / 1000)} kbps</div>
        </div>
      </div>
      
      {/* Frequency Balance Bar */}
      <div>
        <div className="text-[9px] font-mono text-text-secondary uppercase mb-1">Frequency Balance</div>
        <div className="flex gap-1 h-8 items-end">
          {data.frequencyBalance.map((val, i) => (
            <div
              key={i}
              className="flex-1 bg-gradient-to-t from-orange-600 to-orange-400 rounded-sm"
              style={{ height: `${(val / maxFreq) * 100}%`, minHeight: 2 }}
              title={`Band ${i + 1}: ${val.toFixed(3)}`}
            />
          ))}
        </div>
        <div className="flex justify-between text-[8px] font-mono text-text-secondary/60 mt-1">
          <span>Sub</span>
          <span>Bass</span>
          <span>Mids</span>
          <span>Highs</span>
          <span>Air</span>
        </div>
      </div>
    </div>
  );
}

// ============================================
// VISUALIZATION B: SPECTROGRAM
// ============================================

function VisualizationB({ data, currentTime }: { data: AudioData; currentTime: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const progressRef = useRef<number>(0);
  
  useEffect(() => {
    if (!canvasRef.current || data.spectrogramData.length === 0) return;
    
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const width = canvas.width;
    const height = canvas.height;
    
    ctx.clearRect(0, 0, width, height);
    
    const numFrames = data.spectrogramData.length;
    const numBins = data.spectrogramData[0]?.length || 64;
    
    // Find max for normalization
    let maxVal = 0;
    data.spectrogramData.forEach(frame => {
      frame.forEach(val => { if (val > maxVal) maxVal = val; });
    });
    
    // Draw spectrogram
    const frameWidth = width / numFrames;
    const binHeight = height / numBins;
    
    data.spectrogramData.forEach((frame, x) => {
      frame.forEach((magnitude, y) => {
        const normalized = magnitude / Math.max(maxVal, 0.001);
        const hue = (1 - normalized) * 240; // Blue to red
        const lightness = normalized * 50;
        
        ctx.fillStyle = `hsl(${hue}, 80%, ${lightness}%)`;
        ctx.fillRect(
          x * frameWidth,
          height - (y + 1) * binHeight,
          Math.max(1, frameWidth),
          Math.max(1, binHeight)
        );
      });
    });
    
    // Draw frequency labels
    ctx.fillStyle = '#ff8800';
    ctx.font = '9px monospace';
    ctx.fillText('20Hz', 4, height - 4);
    ctx.fillText('1kHz', 4, height * 0.3);
    ctx.fillText('10kHz', 4, 14);
    ctx.fillText('20kHz', 4, 6);
    
  }, [data.spectrogramData]);
  
  // Draw playhead
  useEffect(() => {
    progressRef.current = currentTime / data.duration;
  }, [currentTime, data.duration]);
  
  const progressPercent = (currentTime / data.duration) * 100;
  
  return (
    <div className="bg-bg-card border border-border rounded-sm p-3">
      <div className="flex items-center gap-2 mb-3">
        <Radio className="w-4 h-4 text-accent" />
        <span className="text-xs font-bold text-text-primary tracking-widest uppercase">Option B: Spectrogram</span>
      </div>
      
      <div className="relative bg-bg-surface-darker rounded-sm overflow-hidden">
        <canvas
          ref={canvasRef}
          width={800}
          height={120}
          className="w-full h-32"
        />
        {/* Playhead */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-white pointer-events-none"
          style={{ left: `${progressPercent}%` }}
        />
      </div>
      
      {/* Time ruler */}
      <div className="flex justify-between text-[8px] font-mono text-text-secondary/60 mt-1 px-1">
        <span>0:00</span>
        <span>{Math.floor(data.duration / 4 / 60)}:{Math.floor(data.duration / 4 % 60).toString().padStart(2, '0')}</span>
        <span>{Math.floor(data.duration / 2 / 60)}:{Math.floor(data.duration / 2 % 60).toString().padStart(2, '0')}</span>
        <span>{Math.floor(data.duration * 3 / 4 / 60)}:{Math.floor(data.duration * 3 / 4 % 60).toString().padStart(2, '0')}</span>
        <span>{Math.floor(data.duration / 60)}:{Math.floor(data.duration % 60).toString().padStart(2, '0')}</span>
      </div>
    </div>
  );
}

// ============================================
// VISUALIZATION C: MULTI-LAYER DISPLAY
// ============================================

function VisualizationC({ data, currentTime }: { data: AudioData; currentTime: number }) {
  const waveformCanvasRef = useRef<HTMLCanvasElement>(null);
  const correlationCanvasRef = useRef<HTMLCanvasElement>(null);
  
  const progressPercent = (currentTime / data.duration) * 100;
  
  // Draw stereo waveform
  useEffect(() => {
    const canvas = waveformCanvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const leftChannel = data.audioBuffer.getChannelData(0);
    const rightChannel = data.audioBuffer.numberOfChannels > 1 
      ? data.audioBuffer.getChannelData(1) 
      : leftChannel;
    
    const width = canvas.width;
    const height = canvas.height;
    const halfHeight = height / 2;
    
    ctx.clearRect(0, 0, width, height);
    
    // Draw center line
    ctx.strokeStyle = '#ff880030';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, halfHeight);
    ctx.lineTo(width, halfHeight);
    ctx.stroke();
    
    // Draw left channel (top half)
    ctx.strokeStyle = '#ff8800';
    ctx.lineWidth = 1;
    ctx.beginPath();
    const samplesPerPixel = Math.floor(leftChannel.length / width);
    for (let x = 0; x < width; x++) {
      const start = x * samplesPerPixel;
      let min = 0, max = 0;
      for (let i = 0; i < samplesPerPixel && start + i < leftChannel.length; i++) {
        const val = leftChannel[start + i];
        if (val < min) min = val;
        if (val > max) max = val;
      }
      ctx.moveTo(x, halfHeight - max * halfHeight * 0.9);
      ctx.lineTo(x, halfHeight - min * halfHeight * 0.9);
    }
    ctx.stroke();
    
    // Draw right channel (bottom half)
    ctx.strokeStyle = '#00aaff';
    ctx.beginPath();
    for (let x = 0; x < width; x++) {
      const start = x * samplesPerPixel;
      let min = 0, max = 0;
      for (let i = 0; i < samplesPerPixel && start + i < rightChannel.length; i++) {
        const val = rightChannel[start + i];
        if (val < min) min = val;
        if (val > max) max = val;
      }
      ctx.moveTo(x, halfHeight + max * halfHeight * 0.9);
      ctx.lineTo(x, halfHeight + min * halfHeight * 0.9);
    }
    ctx.stroke();
    
    // Labels
    ctx.fillStyle = '#ff8800';
    ctx.font = '9px monospace';
    ctx.fillText('L', 4, 12);
    ctx.fillStyle = '#00aaff';
    ctx.fillText('R', 4, height - 4);
  }, [data.audioBuffer]);
  
  // Draw stereo correlation
  useEffect(() => {
    const canvas = correlationCanvasRef.current;
    if (!canvas || data.stereoCorrelation.length === 0) return;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const width = canvas.width;
    const height = canvas.height;
    
    ctx.clearRect(0, 0, width, height);
    
    // Draw correlation graph
    ctx.strokeStyle = '#ff8800';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    
    const correlations = data.stereoCorrelation;
    const step = width / correlations.length;
    
    correlations.forEach((corr, i) => {
      const x = i * step;
      const y = height / 2 - corr * (height / 2) * 0.9;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    
    // Draw center line (correlation = 0)
    ctx.strokeStyle = '#ffffff20';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    ctx.lineTo(width, height / 2);
    ctx.stroke();
    
    // Labels
    ctx.fillStyle = '#ff8800';
    ctx.font = '8px monospace';
    ctx.fillText('+1', 4, 10);
    ctx.fillText('0', 4, height / 2 + 4);
    ctx.fillText('-1', 4, height - 4);
  }, [data.stereoCorrelation]);
  
  const maxFreq = Math.max(...data.frequencyBalance, 0.001);
  
  return (
    <div className="bg-bg-card border border-border rounded-sm p-3">
      <div className="flex items-center gap-2 mb-3">
        <Layers className="w-4 h-4 text-accent" />
        <span className="text-xs font-bold text-text-primary tracking-widest uppercase">Option C: Multi-Layer Display</span>
      </div>
      
      {/* Stereo Waveform */}
      <div className="mb-2">
        <div className="text-[9px] font-mono text-text-secondary uppercase mb-1">Stereo Waveform</div>
        <div className="relative bg-bg-surface-darker rounded-sm overflow-hidden">
          <canvas ref={waveformCanvasRef} width={800} height={60} className="w-full h-16" />
          <div className="absolute top-0 bottom-0 w-0.5 bg-white pointer-events-none" style={{ left: `${progressPercent}%` }} />
        </div>
      </div>
      
      {/* Stereo Correlation */}
      <div className="mb-2">
        <div className="text-[9px] font-mono text-text-secondary uppercase mb-1">Stereo Correlation</div>
        <div className="relative bg-bg-surface-darker rounded-sm overflow-hidden">
          <canvas ref={correlationCanvasRef} width={800} height={40} className="w-full h-10" />
          <div className="absolute top-0 bottom-0 w-0.5 bg-white pointer-events-none" style={{ left: `${progressPercent}%` }} />
        </div>
      </div>
      
      {/* Frequency Balance */}
      <div>
        <div className="text-[9px] font-mono text-text-secondary uppercase mb-1">Frequency Balance</div>
        <div className="flex gap-1 h-6 items-end">
          {data.frequencyBalance.slice(0, 8).map((val, i) => {
            const colors = ['#ff4444', '#ff6644', '#ff8844', '#ffaa44', '#ffcc44', '#ffee44', '#ffff44', '#aaffaa'];
            return (
              <div
                key={i}
                className="flex-1 rounded-sm transition-all"
                style={{ 
                  height: `${(val / maxFreq) * 100}%`, 
                  minHeight: 2,
                  backgroundColor: colors[i],
                }}
              />
            );
          })}
        </div>
        <div className="flex justify-between text-[7px] font-mono text-text-secondary/60 mt-0.5">
          <span>Sub</span>
          <span>Bass</span>
          <span>Low</span>
          <span>Mid</span>
          <span>HiMid</span>
          <span>Pres</span>
          <span>High</span>
          <span>Air</span>
        </div>
      </div>
    </div>
  );
}

// ============================================
// MAIN COMPONENT
// ============================================

export function AudioVisualizationStack({ audioUrl, audioFile }: AudioVisualizationStackProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const wavesurferRef = useRef<WaveSurfer | null>(null);
  
  const [isPlaying, setIsPlaying] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [audioData, setAudioData] = useState<AudioData | null>(null);
  const [isDecoding, setIsDecoding] = useState(false);
  
  // Analyser for real-time visualizations
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaElementAudioSourceNode | null>(null);
  
  // Decode audio and compute all visualizations
  useEffect(() => {
    if (!audioFile) return;
    
    setIsDecoding(true);
    decodeAndAnalyzeAudio(audioFile)
      .then(data => {
        setAudioData(data);
        setIsDecoding(false);
      })
      .catch(err => {
        console.error('Failed to decode audio:', err);
        setIsDecoding(false);
      });
  }, [audioFile]);
  
  // Initialize WaveSurfer for playback
  useEffect(() => {
    if (!containerRef.current || (!audioFile && !audioUrl)) return;
    
    setIsReady(false);
    setCurrentTime(0);
    
    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: '#4a4b50',
      progressColor: '#ff8800',
      cursorColor: '#ffffff',
      barWidth: 2,
      barGap: 2,
      barRadius: 2,
      height: 60,
      normalize: true,
      cursorWidth: 2,
    });
    
    wavesurferRef.current = ws;
    
    const setupAnalyser = (mediaElement: HTMLMediaElement) => {
      try {
        if (!audioContextRef.current) {
          audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
        }
        if (!analyserRef.current) {
          analyserRef.current = audioContextRef.current.createAnalyser();
          analyserRef.current.fftSize = 256;
        }
        if (!sourceRef.current) {
          sourceRef.current = audioContextRef.current.createMediaElementSource(mediaElement);
          sourceRef.current.connect(analyserRef.current);
          analyserRef.current.connect(audioContextRef.current.destination);
        }
      } catch (e) {
        console.error('Error setting up audio analyzer:', e);
      }
    };
    
    ws.on('ready', () => {
      setIsReady(true);
      const mediaElement = ws.getMediaElement();
      if (mediaElement) {
        setupAnalyser(mediaElement);
      }
    });
    ws.on('decode', () => {
      setIsReady(true);
      const mediaElement = ws.getMediaElement();
      if (mediaElement) {
        setupAnalyser(mediaElement);
      }
    });
    ws.on('play', () => {
      setIsPlaying(true);
      if (audioContextRef.current?.state === 'suspended') {
        void audioContextRef.current.resume();
      }
    });
    ws.on('pause', () => setIsPlaying(false));
    ws.on('finish', () => setIsPlaying(false));
    
    // Track current time for sync
    ws.on('audioprocess', () => {
      setCurrentTime(ws.getCurrentTime());
    });
    ws.on('seeking', () => {
      setCurrentTime(ws.getCurrentTime());
    });
    
    if (audioFile) {
      ws.loadBlob(audioFile).catch(err => console.error('WaveSurfer load error:', err));
    } else if (audioUrl) {
      ws.load(audioUrl).catch(err => console.error('WaveSurfer load error:', err));
    }
    
    return () => {
      if (sourceRef.current) {
        try { sourceRef.current.disconnect(); } catch (e) {}
        sourceRef.current = null;
      }
      if (analyserRef.current) {
        try { analyserRef.current.disconnect(); } catch (e) {}
        analyserRef.current = null;
      }
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        try { void audioContextRef.current.close(); } catch (e) {}
        audioContextRef.current = null;
      }
      ws.destroy();
    };
  }, [audioFile, audioUrl]);
  
  // Update time during playback
  useEffect(() => {
    if (!isPlaying) return;
    
    const interval = setInterval(() => {
      if (wavesurferRef.current) {
        setCurrentTime(wavesurferRef.current.getCurrentTime());
      }
    }, 50);
    
    return () => clearInterval(interval);
  }, [isPlaying]);
  
  const togglePlay = () => {
    if (wavesurferRef.current && isReady) {
      wavesurferRef.current.playPause();
    }
  };
  
  return (
    <div className="flex flex-col space-y-4 w-full bg-bg-panel p-4 rounded-sm border border-border">
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-1 border-b border-border/30 pb-2">
        <div className="flex items-center space-x-2">
          <Activity className="w-4 h-4 text-accent" />
          <span className="text-xs font-bold text-text-primary tracking-widest uppercase">Audio Visualization Stack</span>
        </div>
        <div className="flex space-x-1">
          <div className={`w-2 h-2 rounded-full ${isReady && !isDecoding ? 'bg-success' : 'bg-warning'}`}></div>
          <span className="text-[9px] font-mono text-text-secondary uppercase">
            {isDecoding ? 'DECODING' : isReady ? 'ONLINE' : 'SYNCING'}
          </span>
        </div>
      </div>
      
      {/* Play Button + Waveform */}
      <div className="flex items-center space-x-4 px-2">
        <button
          onClick={togglePlay}
          disabled={!isReady || isDecoding}
          className={`w-12 h-12 flex items-center justify-center rounded-sm border-2 transition-all ${
            isPlaying 
              ? 'bg-accent text-bg-app border-accent' 
              : 'bg-bg-card text-accent border-border hover:border-accent hover:text-accent/80'
          } disabled:opacity-50 disabled:cursor-not-allowed disabled:border-border`}
          title={isPlaying ? "Pause" : "Play"}
        >
          {(!isReady || isDecoding) ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : isPlaying ? (
            <Pause className="w-5 h-5 fill-current" />
          ) : (
            <Play className="w-5 h-5 ml-1 fill-current" />
          )}
        </button>
        
        <div className="flex-grow bg-bg-card rounded-sm border border-border/50 p-2 relative overflow-hidden">
          <div ref={containerRef} className="w-full" />
        </div>
      </div>
      
      {/* Current Time Display */}
      {audioData && (
        <div className="text-center text-sm font-mono text-text-secondary">
          {Math.floor(currentTime / 60)}:{Math.floor(currentTime % 60).toString().padStart(2, '0')} / {Math.floor(audioData.duration / 60)}:{Math.floor(audioData.duration % 60).toString().padStart(2, '0')}
        </div>
      )}
      
      {/* Stacked Visualizations */}
      {isDecoding && (
        <div className="text-center py-8 text-text-secondary">
          <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
          <span className="text-sm">Decoding audio and computing visualizations...</span>
        </div>
      )}
      
      {audioData && !isDecoding && (
        <div className="space-y-4">
          {/* Spectral Waveform Visualizer */}
          <RetroVisualizer 
            analyser={analyserRef.current} 
            isPlaying={isPlaying} 
            audioBuffer={audioData.audioBuffer} 
          />
        </div>
      )}
    </div>
  );
}

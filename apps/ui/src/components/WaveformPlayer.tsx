import React, { useCallback, useEffect, useRef, useState } from 'react';
import WaveSurfer from 'wavesurfer.js';
import { Play, Pause, Loader2, Activity } from 'lucide-react';

import { isSpectrumActive, nextPeakValue } from './waveformPlayerUtils';

interface WaveformPlayerProps {
  audioUrl: string;
  audioFile?: File;
  onAudioElement?: (el: HTMLAudioElement) => void;
}

const BAR_COUNT = 64;
const PEAK_DROP_RATE = 2;
const SEGMENT_HEIGHT = 4;
const SEGMENT_GAP = 1;

export function WaveformPlayer({ audioUrl, audioFile, onAudioElement }: WaveformPlayerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wavesurferRef = useRef<WaveSurfer | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const [isSeekPreviewActive, setIsSeekPreviewActive] = useState(false);

  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<MediaElementAudioSourceNode | null>(null);
  const animationRef = useRef<number | null>(null);
  const frequencyDataRef = useRef<Uint8Array | null>(null);
  const peakDataRef = useRef<Uint8Array | null>(null);
  const seekingRef = useRef(false);
  const seekPreviewTimeoutRef = useRef<number | null>(null);

  const stopSpectrumLoop = useCallback(() => {
    if (animationRef.current !== null) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
  }, []);

  const clearSeekPreview = useCallback(() => {
    if (seekPreviewTimeoutRef.current !== null) {
      window.clearTimeout(seekPreviewTimeoutRef.current);
      seekPreviewTimeoutRef.current = null;
    }
    setIsSeekPreviewActive(false);
  }, []);

  const ensureSpectrumBuffers = useCallback((bufferLength: number) => {
    if (!frequencyDataRef.current || frequencyDataRef.current.length !== bufferLength) {
      frequencyDataRef.current = new Uint8Array(bufferLength);
    }

    if (!peakDataRef.current || peakDataRef.current.length !== BAR_COUNT) {
      peakDataRef.current = new Uint8Array(BAR_COUNT);
    }

    return {
      frequencyData: frequencyDataRef.current,
      peakData: peakDataRef.current,
    };
  }, []);

  const drawSpectrumFrame = useCallback(() => {
    const canvas = canvasRef.current;
    const analyser = analyserRef.current;
    if (!canvas || !analyser) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const bufferLength = analyser.frequencyBinCount;
    const { frequencyData, peakData } = ensureSpectrumBuffers(bufferLength);

    analyser.getByteFrequencyData(frequencyData);
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const barWidth = canvas.width / BAR_COUNT;
    const effectiveBarWidth = Math.max(1, barWidth - 2);
    const step = Math.max(1, Math.floor(bufferLength / BAR_COUNT / 1.5));

    for (let i = 0; i < BAR_COUNT; i++) {
      const dataIndex = Math.min(bufferLength - 1, i * step);
      const value = frequencyData[dataIndex];
      peakData[i] = nextPeakValue(peakData[i], value, PEAK_DROP_RATE);

      const height = (value / 255) * canvas.height;
      const x = i * barWidth;
      const segmentCount = Math.floor(height / (SEGMENT_HEIGHT + SEGMENT_GAP));

      for (let j = 0; j < segmentCount; j++) {
        const segmentY = canvas.height - (j * (SEGMENT_HEIGHT + SEGMENT_GAP)) - SEGMENT_HEIGHT;

        let fillStyle = '#ff8800';
        if (j > 20) fillStyle = '#ff4444';
        else if (j > 15) fillStyle = '#ffcc00';

        ctx.fillStyle = fillStyle;
        ctx.globalAlpha = 0.8;
        ctx.fillRect(x, segmentY, effectiveBarWidth, SEGMENT_HEIGHT);
      }

      const peakY = canvas.height - (peakData[i] / 255) * canvas.height;
      ctx.fillStyle = '#ffffff';
      ctx.globalAlpha = 0.5;
      ctx.fillRect(x, peakY, effectiveBarWidth, 2);
    }

    ctx.globalAlpha = 1;

    if (isSpectrumActive(wavesurferRef.current?.isPlaying() ?? false, seekingRef.current)) {
      animationRef.current = requestAnimationFrame(drawSpectrumFrame);
      return;
    }

    animationRef.current = null;
  }, [ensureSpectrumBuffers]);

  const startSpectrumLoop = useCallback(() => {
    if (animationRef.current !== null) return;
    drawSpectrumFrame();
  }, [drawSpectrumFrame]);

  const redrawSpectrum = useCallback(() => {
    stopSpectrumLoop();
    drawSpectrumFrame();
  }, [drawSpectrumFrame, stopSpectrumLoop]);

  const setupAnalyzer = useCallback((mediaElement: HTMLMediaElement) => {
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
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;

    setIsReady(false);
    setIsPlaying(false);
    clearSeekPreview();
    stopSpectrumLoop();
    seekingRef.current = false;
    frequencyDataRef.current = null;
    peakDataRef.current = null;

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: '#4a4b50', // Muted gray for unplayed
      progressColor: '#ff8800', // Accent color for played
      cursorColor: '#ffffff',
      barWidth: 2,
      barGap: 2,
      barRadius: 2,
      height: 60,
      normalize: true,
      cursorWidth: 2,
    });

    wavesurferRef.current = ws;
    const mediaElement = ws.getMediaElement();
    onAudioElement?.(mediaElement);

    const handleReady = () => {
      setIsReady(true);
      setupAnalyzer(mediaElement);
      redrawSpectrum();
    };

    ws.on('ready', handleReady);
    ws.on('decode', handleReady);

    ws.on('error', (err) => {
      console.error('WaveSurfer error:', err);
      setIsReady(true); // Fallback to allow play attempt
    });

    ws.on('play', () => {
      setIsPlaying(true);
      clearSeekPreview();
      if (audioContextRef.current?.state === 'suspended') {
        void audioContextRef.current.resume();
      }
      startSpectrumLoop();
    });

    ws.on('pause', () => {
      setIsPlaying(false);
      if (!seekingRef.current) {
        stopSpectrumLoop();
      }
    });

    ws.on('finish', () => {
      setIsPlaying(false);
      seekingRef.current = false;
      clearSeekPreview();
      stopSpectrumLoop();
    });

    const handleSeeking = () => {
      seekingRef.current = true;
      clearSeekPreview();
      setIsSeekPreviewActive(true);
      startSpectrumLoop();
    };

    const handleSeeked = () => {
      seekingRef.current = false;
      redrawSpectrum();
      clearSeekPreview();
      seekPreviewTimeoutRef.current = window.setTimeout(() => {
        setIsSeekPreviewActive(false);
        seekPreviewTimeoutRef.current = null;
      }, 180);
    };

    mediaElement.addEventListener('seeking', handleSeeking);
    mediaElement.addEventListener('seeked', handleSeeked);

    // Load the audio explicitly
    if (audioFile) {
      ws.loadBlob(audioFile).catch((err) => {
        console.error('WaveSurfer loadBlob error:', err);
      });
    } else {
      ws.load(audioUrl).catch((err) => {
        console.error('WaveSurfer load error:', err);
      });
    }

    return () => {
      mediaElement.removeEventListener('seeking', handleSeeking);
      mediaElement.removeEventListener('seeked', handleSeeked);
      clearSeekPreview();
      stopSpectrumLoop();
      if (sourceRef.current) {
        try {
          sourceRef.current.disconnect();
        } catch (e) {}
        sourceRef.current = null;
      }
      if (analyserRef.current) {
        try {
          analyserRef.current.disconnect();
        } catch (e) {}
        analyserRef.current = null;
      }
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        try {
          void audioContextRef.current.close();
        } catch (e) {}
        audioContextRef.current = null;
      }
      frequencyDataRef.current = null;
      peakDataRef.current = null;
      ws.destroy();
    };
  }, [audioFile, audioUrl, clearSeekPreview, redrawSpectrum, setupAnalyzer, startSpectrumLoop, stopSpectrumLoop]);

  const togglePlay = () => {
    if (wavesurferRef.current && isReady) {
      wavesurferRef.current.playPause();
    }
  };

  return (
    <div
      data-testid="waveform-player"
      className="flex flex-col space-y-4 w-full bg-bg-panel p-4 rounded-sm border border-border relative overflow-hidden group"
    >
      <div className="flex items-center justify-between px-4 pt-1 border-b border-border/30 pb-2">
        <div className="flex items-center space-x-2">
          <Activity className="w-4 h-4 text-accent" />
          <span className="text-xs font-bold text-text-primary tracking-widest uppercase">Signal Monitor</span>
        </div>
        <div className="flex space-x-1">
          <div className={`w-2 h-2 rounded-full ${isReady ? 'bg-success' : 'bg-error'}`}></div>
          <span className="text-[9px] font-mono text-text-secondary uppercase">{isReady ? 'ONLINE' : 'SYNCING'}</span>
        </div>
      </div>

      <div className="flex items-center space-x-4 px-2">
        <button
          onClick={togglePlay}
          disabled={!isReady}
          data-testid="waveform-play-toggle"
          className={`w-12 h-12 flex items-center justify-center rounded-sm border-2 transition-all ${
            isPlaying 
              ? 'bg-accent text-bg-app border-accent' 
              : 'bg-bg-card text-accent border-border hover:border-accent hover:text-accent/80'
          } disabled:opacity-50 disabled:cursor-not-allowed disabled:border-border`}
          title={isPlaying ? "Pause" : "Play"}
        >
          {!isReady ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : isPlaying ? (
            <Pause className="w-5 h-5 fill-current" />
          ) : (
            <Play className="w-5 h-5 ml-1 fill-current" />
          )}
        </button>
        
        <div className="flex-grow bg-bg-card rounded-sm border border-border/50 p-2 relative overflow-hidden">
          <div ref={containerRef} data-testid="waveform-track" className="w-full" />
        </div>
      </div>

      <div className="w-full h-32 bg-bg-surface-darker rounded-sm border border-border overflow-hidden relative">
        <canvas 
          ref={canvasRef} 
          width={800} 
          height={128} 
          className="w-full h-full object-fill opacity-90 relative z-10"
        />
        
        {!isPlaying && isReady && !isSeekPreviewActive && (
          <div className="absolute inset-0 flex flex-col items-center justify-center z-30">
            <p className="text-xs text-accent font-mono uppercase tracking-widest">Awaiting Signal</p>
            <p className="text-[10px] text-text-secondary font-mono mt-1">PRESS PLAY TO INITIALIZE SPECTRAL ANALYSIS</p>
          </div>
        )}
        
        {/* Technical readout overlay */}
        <div className="absolute top-2 right-2 z-30 flex flex-col items-end pointer-events-none">
          <span className="text-[8px] font-mono text-accent/50">FFT_SIZE: 256</span>
          <span className="text-[8px] font-mono text-accent/50">SR: 44.1kHz</span>
        </div>
      </div>
    </div>
  );
}

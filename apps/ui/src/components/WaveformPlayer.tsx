import React, { useCallback, useEffect, useRef, useState } from 'react';
import WaveSurfer from 'wavesurfer.js';
import { Play, Pause, Loader2, Activity } from 'lucide-react';

import { RetroVisualizer } from './RetroVisualizer';

interface WaveformPlayerProps {
  audioUrl: string;
  audioFile?: File;
  onAudioElement?: (el: HTMLAudioElement) => void;
}

const METER_SEGMENTS = 20;

function PeakMeter({ analyserL, analyserR, isPlaying }: {
  analyserL: AnalyserNode | null;
  analyserR: AnalyserNode | null;
  isPlaying: boolean;
}) {
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const animRef = useRef<number | null>(null);
  const peakLRef = useRef(0);
  const peakRRef = useRef(0);

  useEffect(() => {
    if (!isPlaying || !analyserL || !analyserR) {
      if (animRef.current !== null) {
        cancelAnimationFrame(animRef.current);
        animRef.current = null;
      }
      peakLRef.current = 0;
      peakRRef.current = 0;
      if (leftRef.current) leftRef.current.style.height = '0%';
      if (rightRef.current) rightRef.current.style.height = '0%';
      return;
    }

    const bufL = new Uint8Array(analyserL.fftSize);
    const bufR = new Uint8Array(analyserR.fftSize);

    const tick = () => {
      analyserL.getByteTimeDomainData(bufL);
      analyserR.getByteTimeDomainData(bufR);

      let maxL = 0, maxR = 0;
      for (let i = 0; i < bufL.length; i++) {
        const absL = Math.abs(bufL[i] - 128);
        const absR = Math.abs(bufR[i] - 128);
        if (absL > maxL) maxL = absL;
        if (absR > maxR) maxR = absR;
      }

      const levelL = maxL / 128;
      const levelR = maxR / 128;

      peakLRef.current = Math.max(levelL, peakLRef.current * 0.97);
      peakRRef.current = Math.max(levelR, peakRRef.current * 0.97);

      if (leftRef.current) leftRef.current.style.height = `${peakLRef.current * 100}%`;
      if (rightRef.current) rightRef.current.style.height = `${peakRRef.current * 100}%`;

      animRef.current = requestAnimationFrame(tick);
    };

    animRef.current = requestAnimationFrame(tick);
    return () => {
      if (animRef.current !== null) cancelAnimationFrame(animRef.current);
    };
  }, [analyserL, analyserR, isPlaying]);

  const segments = Array.from({ length: METER_SEGMENTS }, (_, i) => {
    const pos = i / METER_SEGMENTS;
    let color = 'bg-success/70';
    if (pos > 0.85) color = 'bg-error/80';
    else if (pos > 0.7) color = 'bg-warning/70';
    return color;
  });

  return (
    <div className="flex gap-0.5 h-12">
      {['L', 'R'].map((ch) => (
        <div key={ch} className="flex flex-col items-center gap-0.5 w-[6px]">
          <div className="relative w-full flex-1 bg-bg-surface-darker rounded-sm overflow-hidden">
            <div className="absolute bottom-0 left-0 right-0 flex flex-col-reverse gap-px">
              {segments.map((color, i) => (
                <div key={i} className={`h-[2px] w-full ${color} opacity-20`} />
              ))}
            </div>
            <div
              ref={ch === 'L' ? leftRef : rightRef}
              className="absolute bottom-0 left-0 right-0 overflow-hidden"
              style={{ height: '0%' }}
            >
              <div className="absolute bottom-0 left-0 right-0 flex flex-col-reverse gap-px">
                {segments.map((color, i) => (
                  <div key={i} className={`h-[2px] w-full ${color}`} />
                ))}
              </div>
            </div>
          </div>
          <span className="text-[6px] font-mono text-text-secondary/50">{ch}</span>
        </div>
      ))}
    </div>
  );
}

export function WaveformPlayer({ audioUrl, audioFile, onAudioElement }: WaveformPlayerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const wavesurferRef = useRef<WaveSurfer | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const [hasJustLoaded, setHasJustLoaded] = useState(false);
  const [beatPulse, setBeatPulse] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const beatTimeoutRef = useRef<number | null>(null);

  const handleBeat = useCallback(() => {
    setBeatPulse(true);
    if (beatTimeoutRef.current !== null) window.clearTimeout(beatTimeoutRef.current);
    beatTimeoutRef.current = window.setTimeout(() => setBeatPulse(false), 120);
  }, []);

  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const analyserLRef = useRef<AnalyserNode | null>(null);
  const analyserRRef = useRef<AnalyserNode | null>(null);
  const splitterRef = useRef<ChannelSplitterNode | null>(null);
  const sourceRef = useRef<MediaElementAudioSourceNode | null>(null);

  const setupAnalyzer = useCallback((mediaElement: HTMLMediaElement) => {
    try {
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
      }
      const ctx = audioContextRef.current;

      if (!analyserRef.current) {
        analyserRef.current = ctx.createAnalyser();
        analyserRef.current.fftSize = 256;
      }
      if (!analyserLRef.current) {
        analyserLRef.current = ctx.createAnalyser();
        analyserLRef.current.fftSize = 256;
      }
      if (!analyserRRef.current) {
        analyserRRef.current = ctx.createAnalyser();
        analyserRRef.current.fftSize = 256;
      }
      if (!splitterRef.current) {
        splitterRef.current = ctx.createChannelSplitter(2);
      }

      if (!sourceRef.current) {
        sourceRef.current = ctx.createMediaElementSource(mediaElement);
        sourceRef.current.connect(analyserRef.current);
        analyserRef.current.connect(ctx.destination);
        sourceRef.current.connect(splitterRef.current);
        splitterRef.current.connect(analyserLRef.current, 0);
        splitterRef.current.connect(analyserRRef.current, 1);
      }
    } catch (e) {
      console.error('Error setting up audio analyzer:', e);
    }
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;

    setIsReady(false);
    setIsPlaying(false);

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
    const mediaElement = ws.getMediaElement();
    onAudioElement?.(mediaElement);

    const handleReady = () => {
      setIsReady(true);
      setHasJustLoaded(true);
      setDuration(ws.getDuration());
      setTimeout(() => setHasJustLoaded(false), 600);
      setupAnalyzer(mediaElement);
    };

    ws.on('ready', handleReady);
    ws.on('decode', handleReady);

    ws.on('error', (err) => {
      console.error('WaveSurfer error:', err);
      setIsReady(true);
    });

    ws.on('play', () => {
      setIsPlaying(true);
      if (audioContextRef.current?.state === 'suspended') {
        void audioContextRef.current.resume();
      }
    });
    ws.on('pause', () => setIsPlaying(false));
    ws.on('finish', () => setIsPlaying(false));
    ws.on('audioprocess', () => setCurrentTime(ws.getCurrentTime()));
    ws.on('seeking', () => setCurrentTime(ws.getCurrentTime()));

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
      if (beatTimeoutRef.current !== null) window.clearTimeout(beatTimeoutRef.current);
      if (sourceRef.current) {
        try { sourceRef.current.disconnect(); } catch (e) {}
        sourceRef.current = null;
      }
      if (splitterRef.current) {
        try { splitterRef.current.disconnect(); } catch (e) {}
        splitterRef.current = null;
      }
      if (analyserRef.current) {
        try { analyserRef.current.disconnect(); } catch (e) {}
        analyserRef.current = null;
      }
      if (analyserLRef.current) {
        try { analyserLRef.current.disconnect(); } catch (e) {}
        analyserLRef.current = null;
      }
      if (analyserRRef.current) {
        try { analyserRRef.current.disconnect(); } catch (e) {}
        analyserRRef.current = null;
      }
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        try { void audioContextRef.current.close(); } catch (e) {}
        audioContextRef.current = null;
      }
      ws.destroy();
    };
  }, [audioFile, audioUrl, setupAnalyzer]);

  const togglePlay = () => {
    if (wavesurferRef.current && isReady) {
      wavesurferRef.current.playPause();
    }
  };

  return (
    <div
      data-testid="waveform-player"
      className={`flex flex-col space-y-3 w-full bg-bg-panel p-4 rounded-sm border relative overflow-hidden group transition-[border-color] duration-100 ${
        beatPulse ? 'border-accent/50' : 'border-border'
      }`}
    >
      <div className={`flex items-center justify-between px-4 pt-1 border-b border-border/30 pb-2 transition-colors duration-200 ${hasJustLoaded ? 'bg-accent/8' : ''}`}>
        <div className="flex items-center space-x-2">
          <Activity className="w-4 h-4 text-accent" />
          <span className="text-xs font-bold text-text-primary tracking-widest uppercase">Signal Monitor</span>
        </div>
        <div className="flex items-center space-x-1">
          <div className={`w-2 h-2 rounded-full transition-all duration-200 ${
            isReady
              ? hasJustLoaded ? 'bg-accent shadow-[0_0_6px_rgba(255,136,0,0.6)]' : 'bg-success'
              : 'bg-error'
          }`}></div>
          <span className="text-[9px] font-mono text-text-secondary uppercase">{isReady ? 'ONLINE' : 'SYNCING'}</span>
        </div>
      </div>

      <div className="flex items-center space-x-3 px-2">
        <div className="flex items-center gap-1.5">
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
          <PeakMeter
            analyserL={analyserLRef.current}
            analyserR={analyserRRef.current}
            isPlaying={isPlaying}
          />
        </div>
        
        <div className="flex-grow bg-bg-card rounded-sm border border-border/50 p-2 relative overflow-hidden">
          <div ref={containerRef} data-testid="waveform-track" className="w-full" />
        </div>
      </div>

      {/* (1) Beat-reactive border pulse on signal monitor panel */}
      <RetroVisualizer
        analyser={analyserRef.current}
        isPlaying={isPlaying}
        audioBuffer={null}
        onBeat={handleBeat}
        currentTime={currentTime}
        duration={duration}
      />
    </div>
  );
}

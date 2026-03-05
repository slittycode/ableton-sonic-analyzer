import React, { useEffect, useRef, useState } from 'react';
import WaveSurfer from 'wavesurfer.js';
import { Play, Pause, Loader2, Activity } from 'lucide-react';

interface WaveformPlayerProps {
  audioUrl: string;
  audioFile?: File;
}

export function WaveformPlayer({ audioUrl, audioFile }: WaveformPlayerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wavesurferRef = useRef<WaveSurfer | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isReady, setIsReady] = useState(false);
  
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<MediaElementAudioSourceNode | null>(null);
  const animationRef = useRef<number | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    
    setIsReady(false);
    setIsPlaying(false);

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: '#4a4b50', // Muted gray for unplayed
      progressColor: '#ff9500', // Accent color for played
      cursorColor: '#ffffff',
      barWidth: 2,
      barGap: 2,
      barRadius: 2,
      height: 60,
      normalize: true,
      cursorWidth: 2,
    });

    wavesurferRef.current = ws;

    const handleReady = () => {
      setIsReady(true);
      setupAnalyzer(ws.getMediaElement());
    };

    ws.on('ready', handleReady);
    ws.on('decode', handleReady);

    ws.on('error', (err) => {
      console.error('WaveSurfer error:', err);
      setIsReady(true); // Fallback to allow play attempt
    });

    ws.on('play', () => {
      setIsPlaying(true);
      if (audioContextRef.current?.state === 'suspended') {
        audioContextRef.current.resume();
      }
      drawSpectrum();
    });
    
    ws.on('pause', () => {
      setIsPlaying(false);
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    });
    
    ws.on('finish', () => {
      setIsPlaying(false);
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    });

    // Load the audio explicitly
    if (audioFile) {
      ws.loadBlob(audioFile).catch(err => {
        console.error("WaveSurfer loadBlob error:", err);
      });
    } else {
      ws.load(audioUrl).catch(err => {
        console.error("WaveSurfer load error:", err);
      });
    }

    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
      if (sourceRef.current) {
        try { sourceRef.current.disconnect(); } catch (e) {}
        sourceRef.current = null;
      }
      if (analyserRef.current) {
        try { analyserRef.current.disconnect(); } catch (e) {}
        analyserRef.current = null;
      }
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        try { audioContextRef.current.close(); } catch (e) {}
        audioContextRef.current = null;
      }
      ws.destroy();
    };
  }, [audioUrl, audioFile]);

  const setupAnalyzer = (mediaElement: HTMLMediaElement) => {
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
      console.error("Error setting up audio analyzer:", e);
    }
  };

  const drawSpectrum = () => {
    if (!canvasRef.current || !analyserRef.current) return;
    
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

      const bufferLength = analyserRef.current.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      
      // Peak hold functionality
      const peakData = new Uint8Array(bufferLength).fill(0);
      const peakDropRate = 2;

      const draw = () => {
        if (!wavesurferRef.current?.isPlaying()) {
          setIsPlaying(false);
          return;
        }
        animationRef.current = requestAnimationFrame(draw);

        analyserRef.current!.getByteFrequencyData(dataArray);

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Visualizer settings
        const barCount = 64; // Number of bars to draw
        const barWidth = canvas.width / barCount;
        const gap = 2;
        const effectiveBarWidth = barWidth - gap;
        
        // We only use the lower half of the frequency data for better visuals (most music energy is there)
        const step = Math.floor(bufferLength / barCount / 1.5); 

        for (let i = 0; i < barCount; i++) {
          const dataIndex = i * step;
          let value = dataArray[dataIndex];
          
          // Peak hold logic
          if (value > peakData[i]) {
            peakData[i] = value;
          } else {
            peakData[i] = Math.max(0, peakData[i] - peakDropRate);
          }

          const percent = value / 255;
          const height = percent * canvas.height;
          const x = i * barWidth;
          const y = canvas.height - height;

          // Draw LED bars (segmented)
          const segmentHeight = 4;
          const segmentGap = 1;
          const segmentCount = Math.floor(height / (segmentHeight + segmentGap));

          for (let j = 0; j < segmentCount; j++) {
            const segmentY = canvas.height - (j * (segmentHeight + segmentGap)) - segmentHeight;
            
            // Color gradient based on height
            let fillStyle = '#ff9500'; // Default orange
            if (j > 20) fillStyle = '#ff4444'; // Red at top
            else if (j > 15) fillStyle = '#ffcc00'; // Yellow
            
            ctx.fillStyle = fillStyle;
            ctx.globalAlpha = 0.8;
            ctx.fillRect(x, segmentY, effectiveBarWidth, segmentHeight);
          }
          
          // Draw Peak
          const peakY = canvas.height - (peakData[i] / 255) * canvas.height;
          ctx.fillStyle = '#ffffff';
          ctx.globalAlpha = 0.5;
          ctx.fillRect(x, peakY, effectiveBarWidth, 2);
          
          ctx.globalAlpha = 1.0;
        }
      };

      draw();
    };

  const togglePlay = () => {
    if (wavesurferRef.current && isReady) {
      wavesurferRef.current.playPause();
    }
  };

  return (
    <div className="flex flex-col space-y-4 w-full bg-bg-panel p-4 rounded-sm border border-border relative overflow-hidden group">
      <div className="flex items-center justify-between px-4 pt-1 border-b border-border/30 pb-2">
        <div className="flex items-center space-x-2">
          <Activity className="w-4 h-4 text-accent" />
          <span className="text-xs font-bold text-text-primary tracking-widest uppercase">Signal Monitor</span>
        </div>
        <div className="flex space-x-1">
          <div className={`w-2 h-2 rounded-full ${isReady ? 'bg-green-500' : 'bg-red-500'}`}></div>
          <span className="text-[9px] font-mono text-text-secondary uppercase">{isReady ? 'ONLINE' : 'SYNCING'}</span>
        </div>
      </div>

      <div className="flex items-center space-x-4 px-2">
        <button
          onClick={togglePlay}
          disabled={!isReady}
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
          <div ref={containerRef} className="w-full" />
        </div>
      </div>

      <div className="w-full h-32 bg-[#1a1a1a] rounded-sm border border-border overflow-hidden relative">
        <canvas 
          ref={canvasRef} 
          width={800} 
          height={128} 
          className="w-full h-full object-fill opacity-90 relative z-10"
        />
        
        {!isPlaying && isReady && (
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

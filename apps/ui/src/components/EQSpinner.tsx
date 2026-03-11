import React, { useEffect, useRef, useState } from 'react';

const ABLETON_COLORS = [
  '#FF4B4B', // Red
  '#FF8A27', // Orange
  '#E3C938', // Yellow
  '#89D966', // Green
  '#44C5D2', // Light Blue
  '#4A8CFF', // Blue
  '#B266FF', // Purple
  '#FF59A6', // Pink
];

// Pre-defined random-looking animation properties to avoid the "wave" effect
const ANIMATION_PROPS = [
  { duration: '0.4s', delay: '0.1s' },
  { duration: '0.5s', delay: '0.3s' },
  { duration: '0.35s', delay: '0.0s' },
  { duration: '0.45s', delay: '0.2s' },
  { duration: '0.55s', delay: '0.4s' },
  { duration: '0.4s', delay: '0.1s' },
  { duration: '0.6s', delay: '0.3s' },
  { duration: '0.35s', delay: '0.2s' },
];

interface EQSpinnerProps {
  audioUrl?: string | null;
}

export function EQSpinner({ audioUrl }: EQSpinnerProps) {
  const barsRef = useRef<(HTMLDivElement | null)[]>([]);
  const [isReacting, setIsReacting] = useState(false);
  const animationRef = useRef<number | null>(null);

  useEffect(() => {
    if (!audioUrl) {
      setIsReacting(false);
      return;
    }

    let audioCtx: AudioContext | null = null;
    let audio: HTMLAudioElement | null = null;

    const setupAudio = async () => {
      try {
        audio = new Audio(audioUrl);
        audio.loop = true;

        audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 128; // 64 bins

        const source = audioCtx.createMediaElementSource(audio);
        const gainNode = audioCtx.createGain();
        gainNode.gain.value = 0; // Mute output so it doesn't play out loud

        source.connect(analyser);
        analyser.connect(gainNode);
        gainNode.connect(audioCtx.destination);

        const playPromise = audio.play();
        if (playPromise !== undefined) {
          playPromise.then(() => {
            setIsReacting(true);
          }).catch(err => {
            if (err.name !== 'AbortError' && !err.message?.includes('interrupted')) {
              console.error("Failed to play audio for EQ spinner:", err);
            }
            setIsReacting(false);
          });
        } else {
          setIsReacting(true);
        }

        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const draw = () => {
          animationRef.current = requestAnimationFrame(draw);
          analyser.getByteFrequencyData(dataArray);

          // We want 8 bars. Skip the very lowest and highest bins for better visual movement
          const usableBins = Math.floor(bufferLength * 0.8);
          const step = Math.max(1, Math.floor(usableBins / 8));

          for (let i = 0; i < 8; i++) {
            let sum = 0;
            const startIndex = i * step;
            for (let j = 0; j < step; j++) {
              sum += dataArray[startIndex + j] || 0;
            }
            const average = sum / step;
            
            // Add a bit of a boost so it looks active even on quieter tracks
            const heightPercent = Math.min(100, Math.max(15, (average / 255) * 120));

            if (barsRef.current[i]) {
              barsRef.current[i]!.style.height = `${heightPercent}%`;
            }
          }
        };

        draw();
      } catch (err) {
        console.error("Failed to setup reactive EQ spinner:", err);
        setIsReacting(false);
      }
    };

    setupAudio();

    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
      if (audio) {
        audio.pause();
        audio.src = '';
      }
      if (audioCtx && audioCtx.state !== 'closed') {
        audioCtx.close().catch(() => {});
      }
    };
  }, [audioUrl]);

  return (
    <div className="flex items-end justify-center space-x-1.5 h-8 mb-4">
      {ABLETON_COLORS.map((color, i) => (
        <div
          key={i}
          ref={el => barsRef.current[i] = el}
          className="w-2 rounded-t-sm"
          style={{
            backgroundColor: color,
            height: isReacting ? '15%' : undefined,
            animation: isReacting ? 'none' : `eq-bounce ${ANIMATION_PROPS[i].duration} ease-in-out infinite alternate`,
            animationDelay: isReacting ? '0s' : ANIMATION_PROPS[i].delay,
            minHeight: '4px',
            transition: isReacting ? 'height 0.05s ease-out' : 'none',
          }}
        />
      ))}
    </div>
  );
}

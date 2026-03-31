import type { ReactNode } from 'react';
import { motion } from 'motion/react';
import {
  Activity,
  ArrowLeft,
  AudioWaveform,
  Disc3,
  Gauge,
  Layers3,
  Play,
  Sparkles,
} from 'lucide-react';

import { getAppViewHref } from '../utils/appView';

const transportMarkers = ['00:00', '00:32', '01:04', '01:36', '02:08', '02:40'];

const featureRows = [
  ['Tempo', '128.5 BPM', 'Locked'],
  ['Key', 'C Major', 'Stable'],
  ['LUFS-I', '-14.2', 'Target'],
  ['Stereo', '0.74', 'Wide'],
  ['Transients', '8.1 / 10', 'Hot'],
  ['Pitch Guide', '89%', 'Best-effort'],
];

const cueCards = [
  {
    label: 'Bus Notes',
    value: 'Kick and bass are sharing too much 90-140 Hz weight.',
  },
  {
    label: 'Arrangement',
    value: 'Drop energy rises cleanly, but the pre-chorus vocal stack is masking the snare crack.',
  },
  {
    label: 'Export',
    value: 'MIDI lane + JSON report queued for the same session snapshot.',
  },
];

const channelStrips = [
  { name: 'Input', tone: '#ff7a1a', db: '-2.1', meter: 82 },
  { name: 'Glue', tone: '#ff9f43', db: '-6.8', meter: 64 },
  { name: 'Stereo', tone: '#70d6ff', db: '-8.4', meter: 56 },
  { name: 'Limiter', tone: '#ffd166', db: '-1.2', meter: 92 },
];

const noteLanes = [
  {
    name: 'Bass stem',
    accent: '#ff7a1a',
    notes: [
      { left: '2%', width: '18%' },
      { left: '24%', width: '12%' },
      { left: '40%', width: '22%' },
      { left: '66%', width: '16%' },
    ],
  },
  {
    name: 'Other stem',
    accent: '#70d6ff',
    notes: [
      { left: '8%', width: '10%' },
      { left: '28%', width: '14%' },
      { left: '48%', width: '18%' },
      { left: '74%', width: '10%' },
    ],
  },
  {
    name: 'Confidence',
    accent: '#ffd166',
    notes: [
      { left: '4%', width: '20%' },
      { left: '34%', width: '16%' },
      { left: '58%', width: '12%' },
      { left: '76%', width: '8%' },
    ],
  },
];

function SectionFrame({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-[1.35rem] border border-white/8 bg-black/35 shadow-[0_24px_60px_rgba(0,0,0,0.42)] backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-white/8 px-5 py-3">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-[0.28em] text-[#8a8a8a]">{eyebrow}</p>
          <h2 className="mt-1 text-sm font-semibold uppercase tracking-[0.14em] text-[#f3efe8]">{title}</h2>
        </div>
        <div className="h-2.5 w-2.5 rounded-full bg-[#ff7a1a] shadow-[0_0_14px_rgba(255,122,26,0.75)]" />
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

export default function DenseDawConcept() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-[#090909] text-[#f3efe8]">
      <div
        className="absolute inset-0 opacity-80"
        style={{
          background:
            'radial-gradient(circle at top left, rgba(255,122,26,0.18), transparent 30%), radial-gradient(circle at top right, rgba(112,214,255,0.12), transparent 34%), linear-gradient(180deg, #101010 0%, #090909 100%)',
        }}
      />
      <div
        className="absolute inset-0 opacity-[0.08]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.8) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.8) 1px, transparent 1px)',
          backgroundSize: '88px 88px',
        }}
      />

      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: 'easeOut' }}
        className="relative mx-auto flex min-h-screen w-full max-w-[1600px] flex-col px-4 py-4 md:px-6 md:py-6"
      >
        <header className="rounded-[1.5rem] border border-white/10 bg-[#121212]/90 px-4 py-4 shadow-[0_30px_80px_rgba(0,0,0,0.55)] backdrop-blur-xl md:px-6">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <a
                  href={getAppViewHref('app')}
                  className="inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/5 px-3 py-1.5 text-[11px] font-mono uppercase tracking-[0.18em] text-[#d7d0c7] transition-colors hover:border-[#ff7a1a]/50 hover:text-white"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                  Current UI
                </a>
                <span className="inline-flex items-center gap-2 rounded-full border border-[#ff7a1a]/35 bg-[#ff7a1a]/10 px-3 py-1.5 text-[11px] font-mono uppercase tracking-[0.18em] text-[#ffb27d]">
                  Dense DAW concept
                </span>
              </div>

              <div className="flex items-start gap-3">
                <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
                  <AudioWaveform className="h-7 w-7 text-[#ff7a1a]" />
                </div>
                <div>
                  <p className="text-[10px] font-mono uppercase tracking-[0.32em] text-[#8a8a8a]">ASA parallel concept</p>
                  <h1 className="mt-2 max-w-3xl text-2xl font-semibold uppercase tracking-[0.14em] text-[#f8f4ec] md:text-[2rem]">
                    Obsidian Rack Workspace
                  </h1>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-[#bbb4aa]">
                    A denser producer-first shell that treats the analyzer like a serious DAW utility:
                    transport first, measurement center-stage, pitch guides visible, and AI notes parked as
                    supporting context rather than the hero.
                  </p>
                </div>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3 xl:min-w-[520px]">
              <div className="rounded-[1.1rem] border border-white/10 bg-black/30 px-4 py-3">
                <p className="text-[10px] font-mono uppercase tracking-[0.24em] text-[#8a8a8a]">Session</p>
                <p className="mt-2 text-lg font-semibold tracking-[0.12em] text-[#f8f4ec]">LATE BUS MIX</p>
                <p className="mt-1 text-xs font-mono uppercase tracking-[0.18em] text-[#ffb27d]">Run 0218 / locked analysis</p>
              </div>
              <div className="rounded-[1.1rem] border border-white/10 bg-black/30 px-4 py-3">
                <p className="text-[10px] font-mono uppercase tracking-[0.24em] text-[#8a8a8a]">Measurement</p>
                <p className="mt-2 text-lg font-semibold tracking-[0.12em] text-[#f8f4ec]">Tempo / Key / LUFS</p>
                <p className="mt-1 text-xs font-mono uppercase tracking-[0.18em] text-[#70d6ff]">Authoritative layer</p>
              </div>
              <div className="rounded-[1.1rem] border border-white/10 bg-black/30 px-4 py-3">
                <p className="text-[10px] font-mono uppercase tracking-[0.24em] text-[#8a8a8a]">Translation</p>
                <p className="mt-2 text-lg font-semibold tracking-[0.12em] text-[#f8f4ec]">Stem note lane</p>
                <p className="mt-1 text-xs font-mono uppercase tracking-[0.18em] text-[#ffd166]">Best-effort guide</p>
              </div>
            </div>
          </div>
        </header>

        <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.92fr)]">
          <div className="space-y-5">
            <SectionFrame eyebrow="Transport" title="Master Bus And Signal Flow">
              <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
                <div className="rounded-[1.1rem] border border-white/8 bg-[#101010] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <button className="inline-flex h-12 w-12 items-center justify-center rounded-full border border-[#ff7a1a]/40 bg-[#ff7a1a]/12 text-[#ff9f43]">
                        <Play className="ml-0.5 h-5 w-5 fill-current" />
                      </button>
                      <div>
                        <p className="text-[10px] font-mono uppercase tracking-[0.28em] text-[#8a8a8a]">Playback</p>
                        <p className="mt-1 text-lg font-semibold uppercase tracking-[0.16em] text-[#f5f0e8]">Reference stem monitor</p>
                      </div>
                    </div>
                    <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[11px] font-mono uppercase tracking-[0.18em] text-[#d2cbc2]">
                      <Disc3 className="h-3.5 w-3.5 text-[#70d6ff]" />
                      48 kHz / 24-bit
                    </div>
                  </div>

                  <div className="mt-5 rounded-[1rem] border border-white/8 bg-[#090909] px-4 py-4">
                    <div className="relative h-44 overflow-hidden rounded-[0.9rem] border border-white/6 bg-[#070707]">
                      <div
                        className="absolute inset-0 opacity-90"
                        style={{
                          background:
                            'linear-gradient(180deg, rgba(255,122,26,0.08), transparent 42%), linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px)',
                          backgroundSize: 'auto, 80px 100%',
                        }}
                      />
                      <div className="absolute inset-x-0 top-1/2 h-px bg-white/6" />
                      <svg viewBox="0 0 1200 220" className="absolute inset-0 h-full w-full">
                        <defs>
                          <linearGradient id="wave-fill" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" stopColor="#ff7a1a" stopOpacity="0.18" />
                            <stop offset="40%" stopColor="#ff9f43" stopOpacity="0.42" />
                            <stop offset="100%" stopColor="#70d6ff" stopOpacity="0.22" />
                          </linearGradient>
                        </defs>
                        <path
                          d="M0 111 C45 46, 82 176, 128 110 S214 52, 266 111 355 175, 404 112 480 52, 528 111 615 177, 670 108 735 38, 792 112 885 174, 944 109 1012 54, 1070 113 1146 165, 1200 109"
                          fill="none"
                          stroke="url(#wave-fill)"
                          strokeWidth="7"
                          strokeLinecap="round"
                        />
                        <path
                          d="M0 111 C45 67, 82 151, 128 110 S214 74, 266 111 355 149, 404 112 480 73, 528 111 615 151, 670 108 735 62, 792 112 885 147, 944 109 1012 74, 1070 113 1146 152, 1200 109"
                          fill="none"
                          stroke="#f6d5ba"
                          strokeOpacity="0.18"
                          strokeWidth="2"
                          strokeLinecap="round"
                        />
                      </svg>
                      <div className="absolute inset-y-0 left-[61%] w-[2px] bg-[#ff7a1a] shadow-[0_0_18px_rgba(255,122,26,0.9)]" />
                      <div className="absolute inset-x-4 bottom-3 flex items-center justify-between text-[9px] font-mono uppercase tracking-[0.24em] text-[#7f7b74]">
                        {transportMarkers.map((marker) => (
                          <span key={marker}>{marker}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="grid gap-3">
                  {channelStrips.map((strip) => (
                    <div key={strip.name} className="rounded-[1rem] border border-white/8 bg-[#101010] px-4 py-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-[10px] font-mono uppercase tracking-[0.24em] text-[#8a8a8a]">{strip.name}</p>
                          <p className="mt-1 text-sm font-semibold uppercase tracking-[0.16em] text-[#f3efe8]">{strip.db} dB</p>
                        </div>
                        <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-[#bdb6ad]">Active</span>
                      </div>
                      <div className="mt-3 flex h-14 items-end gap-1 rounded-[0.9rem] border border-white/8 bg-black/40 px-2 py-2">
                        {Array.from({ length: 18 }, (_, index) => {
                          const threshold = Math.round((index / 17) * 100);
                          const active = strip.meter >= threshold;
                          return (
                            <span
                              key={`${strip.name}-${index}`}
                              className={`w-full rounded-t-[2px] ${active ? 'animate-pulse' : ''}`}
                              style={{
                                height: `${28 + (index % 6) * 8}%`,
                                background: active ? strip.tone : 'rgba(255,255,255,0.08)',
                                boxShadow: active ? `0 0 10px ${strip.tone}55` : 'none',
                              }}
                            />
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </SectionFrame>

            <SectionFrame eyebrow="Translation" title="Pitch Guide Lanes">
              <div className="rounded-[1.1rem] border border-white/8 bg-[#0b0b0b] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-[10px] font-mono uppercase tracking-[0.28em] text-[#8a8a8a]">Stem-aligned piano roll</p>
                    <p className="mt-1 text-sm text-[#c7c0b8]">
                      Built for quick producer decisions. This remains a guide, not full polyphonic truth.
                    </p>
                  </div>
                  <div className="inline-flex items-center gap-2 rounded-full border border-[#ffd166]/25 bg-[#ffd166]/10 px-3 py-1.5 text-[11px] font-mono uppercase tracking-[0.18em] text-[#ffd166]">
                    <Layers3 className="h-3.5 w-3.5" />
                    Confidence 89%
                  </div>
                </div>

                <div className="mt-5 space-y-4">
                  {noteLanes.map((lane) => (
                    <div key={lane.name} className="grid gap-3 md:grid-cols-[140px_minmax(0,1fr)] md:items-center">
                      <div className="rounded-[0.85rem] border border-white/8 bg-[#121212] px-3 py-2">
                        <p className="text-[10px] font-mono uppercase tracking-[0.24em] text-[#8a8a8a]">{lane.name}</p>
                        <p className="mt-1 text-xs font-semibold uppercase tracking-[0.16em] text-[#efeae2]">Stem monitor</p>
                      </div>
                      <div className="relative h-16 overflow-hidden rounded-[0.95rem] border border-white/8 bg-[#080808]">
                        <div
                          className="absolute inset-0 opacity-30"
                          style={{
                            backgroundImage:
                              'linear-gradient(90deg, rgba(255,255,255,0.08) 1px, transparent 1px), linear-gradient(180deg, rgba(255,255,255,0.05) 1px, transparent 1px)',
                            backgroundSize: '10% 100%, 100% 33%',
                          }}
                        />
                        {lane.notes.map((note, index) => (
                          <span
                            key={`${lane.name}-${index}`}
                            className="absolute top-1/2 h-5 -translate-y-1/2 rounded-md"
                            style={{
                              left: note.left,
                              width: note.width,
                              background: `linear-gradient(135deg, ${lane.accent}, ${lane.accent}aa)`,
                              boxShadow: `0 0 16px ${lane.accent}40`,
                            }}
                          />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </SectionFrame>
          </div>

          <div className="space-y-5">
            <SectionFrame eyebrow="Measurement" title="Authoritative Core">
              <div className="grid gap-3 sm:grid-cols-2">
                {featureRows.map(([label, value, state], index) => (
                  <motion.div
                    key={label}
                    initial={{ opacity: 0, x: 14 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.28, delay: index * 0.04 }}
                    className="rounded-[1rem] border border-white/8 bg-[#0e0e0e] px-4 py-4"
                  >
                    <p className="text-[10px] font-mono uppercase tracking-[0.24em] text-[#8a8a8a]">{label}</p>
                    <p className="mt-3 text-xl font-semibold uppercase tracking-[0.14em] text-[#f6f1e8]">{value}</p>
                    <p className="mt-2 text-[11px] font-mono uppercase tracking-[0.2em] text-[#ffb27d]">{state}</p>
                  </motion.div>
                ))}
              </div>

              <div className="mt-4 rounded-[1rem] border border-white/8 bg-[#0d0d0d] px-4 py-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[10px] font-mono uppercase tracking-[0.24em] text-[#8a8a8a]">Spectrum pressure</p>
                    <p className="mt-1 text-sm text-[#c8c1b8]">Sub-to-low-mid buildup is the current bottleneck.</p>
                  </div>
                  <Gauge className="h-5 w-5 text-[#70d6ff]" />
                </div>
                <div className="mt-4 flex h-28 items-end gap-2 rounded-[0.9rem] border border-white/8 bg-black/45 px-3 py-3">
                  {[24, 44, 76, 92, 86, 58, 46, 54, 67, 74, 55, 28].map((height, index) => (
                    <span
                      key={`spectrum-${index}`}
                      className="w-full rounded-t-md"
                      style={{
                        height: `${height}%`,
                        background:
                          height > 80
                            ? 'linear-gradient(180deg, #ff7a1a, #7c2c00)'
                            : height > 60
                              ? 'linear-gradient(180deg, #ffd166, #7b5a13)'
                              : 'linear-gradient(180deg, #70d6ff, #154b66)',
                      }}
                    />
                  ))}
                </div>
              </div>
            </SectionFrame>

            <SectionFrame eyebrow="Interpretation" title="Producer Guidance">
              <div className="space-y-3">
                {cueCards.map((card) => (
                  <div key={card.label} className="rounded-[1rem] border border-white/8 bg-[#0f0f0f] px-4 py-4">
                    <div className="flex items-center gap-2">
                      {card.label === 'Arrangement' ? (
                        <Sparkles className="h-4 w-4 text-[#ffd166]" />
                      ) : card.label === 'Export' ? (
                        <Activity className="h-4 w-4 text-[#70d6ff]" />
                      ) : (
                        <Disc3 className="h-4 w-4 text-[#ff7a1a]" />
                      )}
                      <p className="text-[10px] font-mono uppercase tracking-[0.24em] text-[#8a8a8a]">{card.label}</p>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-[#d9d1c7]">{card.value}</p>
                  </div>
                ))}
              </div>
            </SectionFrame>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { AnalysisResults, characterToggleLabel, toggleOpenKeySet } from '../../src/components/AnalysisResults';
import { MIDI_DOWNLOAD_FILE_NAME } from '../../src/components/SessionMusicianPanel';
import { Phase1Result, Phase2Result } from '../../src/types';

const basePhase1: Phase1Result = {
  bpm: 126,
  bpmConfidence: 0.91,
  key: 'F minor',
  keyConfidence: 0.87,
  timeSignature: '4/4',
  durationSeconds: 210.6,
  lufsIntegrated: -7.9,
  truePeak: -0.2,
  stereoWidth: 0.69,
  stereoCorrelation: 0.84,
  spectralBalance: {
    subBass: -0.7,
    lowBass: 1.2,
    mids: -0.3,
    upperMids: 0.4,
    highs: 1.0,
    brilliance: 0.8,
  },
};

const basePhase2: Phase2Result = {
  trackCharacter: 'Tight modern electronic mix.',
  detectedCharacteristics: [
    { name: 'Stereo Discipline', confidence: 'HIGH', explanation: 'Controlled width and correlation.' },
  ],
  arrangementOverview: {
    summary: 'Arrangement transitions and energy shifts.',
    segments: [
      {
        index: 1,
        startTime: 0,
        endTime: 30,
        lufs: -8.4,
        description: 'Intro: sparse opening.',
        spectralNote: 'High shelf lift around 8 kHz on hats.',
      },
      {
        index: 2,
        startTime: 30,
        endTime: 75,
        lufs: -7.0,
        description: 'Drop: dense full-range impact.',
      },
    ],
    noveltyNotes: 'Novel shifts at 14.0s and 63.5s align with transitions.',
  },
  sonicElements: {
    kick: 'Punchy kick body.',
    bass: 'Focused bass lane.',
    melodicArp: 'Simple melodic motif.',
    grooveAndTiming: 'Quantized groove.',
    effectsAndTexture: 'Light atmospherics.',
  },
  mixAndMasterChain: [
    {
      order: 1,
      device: 'Drum Buss',
      parameter: 'Drive',
      value: '5 dB',
      reason: 'Adds punch to drums.',
    },
    {
      order: 2,
      device: 'EQ Eight',
      parameter: 'Low Cut',
      value: '30 Hz',
      reason: 'Removes rumble from bass bus.',
    },
  ],
  secretSauce: {
    title: 'Punch Layering',
    explanation: 'Layered transient enhancement.',
    implementationSteps: ['Step 1', 'Step 2'],
  },
  confidenceNotes: [{ field: 'Key Signature', value: 'HIGH', reason: 'Stable detection.' }],
};

describe('AnalysisResults UI wiring', () => {
  it('toggles only the targeted sonic card key', () => {
    const initial = new Set<string>(['kick']);

    const openBass = toggleOpenKeySet(initial, 'bass');
    expect(openBass.has('kick')).toBe(true);
    expect(openBass.has('bass')).toBe(true);

    const closeKick = toggleOpenKeySet(openBass, 'kick');
    expect(closeKick.has('kick')).toBe(false);
    expect(closeKick.has('bass')).toBe(true);

    // Ensure original set remains unchanged.
    expect(initial.has('kick')).toBe(true);
    expect(initial.has('bass')).toBe(false);
  });

  it('renders mix and patch cards using flex-wrap layout without grid test ids', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: basePhase1,
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('class="flex flex-wrap gap-4"');
    expect(html).not.toContain('data-testid="mix-group-grid-');
    expect(html).not.toContain('data-testid="patch-grid"');
  });

  it('renders character card with collapsed toggle by default', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: basePhase1,
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('line-clamp-2');
    expect(html).toContain('▼ MORE');
  });

  it('returns expected character toggle labels', () => {
    expect(characterToggleLabel(false)).toBe('▼ MORE');
    expect(characterToggleLabel(true)).toBe('▲ LESS');
  });

  it('uses normalized midi download filename', () => {
    expect(MIDI_DOWNLOAD_FILE_NAME).toBe('track-analysis.mid');
  });

  it('renders MIDI unavailable state when melodyDetail is missing', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: basePhase1,
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('MIDI TRANSCRIPTION UNAVAILABLE');
    expect(html).toContain('Re-run analysis with FLAC source for melody extraction, or paste DSP JSON with melodyDetail field populated');
  });

  it('renders arrangement novelty and spectral note labels', () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResults, {
        phase1: basePhase1,
        phase2: basePhase2,
        sourceFileName: 'example.wav',
      }),
    );

    expect(html).toContain('NOVELTY EVENTS');
    expect(html).toContain('SPECTRAL NOTE');
    expect(html).toContain('▲ +0.5 dB');
    expect(html).toContain('▼ -0.9 dB');
  });
});

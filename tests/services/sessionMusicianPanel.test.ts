import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { filterNotesByConfidence, formatFilteredNoteCount, SessionMusicianPanel } from '../../src/components/SessionMusicianPanel';
import { Phase1Result } from '../../src/types';

const basePhase1: Phase1Result = {
  bpm: 128,
  bpmConfidence: 0.91,
  key: 'A minor',
  keyConfidence: 0.87,
  timeSignature: '4/4',
  durationSeconds: 12,
  lufsIntegrated: -8.4,
  truePeak: -0.5,
  stereoWidth: 0.75,
  stereoCorrelation: 0.82,
  spectralBalance: {
    subBass: -1.2,
    lowBass: 0.8,
    mids: -0.4,
    upperMids: 0.2,
    highs: 1.1,
    brilliance: 0.5,
  },
};

describe('SessionMusicianPanel confidence helpers', () => {
  it('renders monophonic stats without a filtered prefix and disables the confidence slider', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: {
          ...basePhase1,
          melodyDetail: {
            noteCount: 3,
            notes: [
              { midi: 60, onset: 0.2, duration: 0.3 },
              { midi: 64, onset: 0.8, duration: 0.2 },
              { midi: 67, onset: 1.2, duration: 0.4 },
            ],
            dominantNotes: [60, 64, 67],
            pitchRange: { min: 60, max: 67 },
            pitchConfidence: 0.72,
            midiFile: null,
            sourceSeparated: false,
            vibratoPresent: false,
            vibratoExtent: 0,
            vibratoRate: 0,
            vibratoConfidence: 0.1,
          },
        },
      }),
    );

    expect(html).toContain('3 NOTES');
    expect(html).not.toContain('3 / 3 NOTES');
    expect(html).toContain('Per-note confidence not available in monophonic mode');
    expect(html).toMatch(/CONFIDENCE<\/span><input[^>]*disabled=""/);
  });

  it('filters notes at or above the confidence threshold', () => {
    const filtered = filterNotesByConfidence(
      [
        {
          midi: 48,
          name: 'C3',
          startTime: 0.1,
          duration: 0.4,
          velocity: 90,
          confidence: 0.19,
        },
        {
          midi: 55,
          name: 'G3',
          startTime: 0.6,
          duration: 0.3,
          velocity: 90,
          confidence: 0.2,
        },
        {
          midi: 60,
          name: 'C4',
          startTime: 0.9,
          duration: 0.25,
          velocity: 90,
          confidence: 0.8,
        },
      ],
      0.2,
    );

    expect(filtered).toHaveLength(2);
    expect(filtered.map((note) => note.midi)).toEqual([55, 60]);
  });

  it('formats the filtered count using the number of notes that pass the confidence filter', () => {
    const activeNotes = [
      {
        midi: 48,
        name: 'C3',
        startTime: 0.1,
        duration: 0.4,
        velocity: 90,
        confidence: 0.19,
      },
      {
        midi: 55,
        name: 'G3',
        startTime: 0.6,
        duration: 0.3,
        velocity: 90,
        confidence: 0.2,
      },
      {
        midi: 60,
        name: 'C4',
        startTime: 0.9,
        duration: 0.25,
        velocity: 90,
        confidence: 0.8,
      },
    ];
    const filteredNotes = filterNotesByConfidence(activeNotes, 0.2);

    expect(filteredNotes).toHaveLength(2);
    expect(formatFilteredNoteCount(filteredNotes.length, activeNotes.length, 0.2)).toBe('2 / 3 NOTES');
  });

  it('formats filtered note counts when the threshold is active', () => {
    expect(formatFilteredNoteCount(2, 3, 0.2)).toBe('2 / 3 NOTES');
  });

  it('formats note counts without the filtered prefix when threshold is zero', () => {
    expect(formatFilteredNoteCount(3, 3, 0)).toBe('3 NOTES');
  });
});

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, vi } from 'vitest';

import {
  deriveTranscriptionProvenance,
  filterNotesByConfidence,
  formatFilteredNoteCount,
  SessionMusicianPanel,
} from '../../src/components/SessionMusicianPanel';
import { MeasurementResult, TranscriptionDetail } from '../../src/types';

const baseMeasurement: MeasurementResult = {
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
    lowMids: 0.0,
    mids: -0.4,
    upperMids: 0.2,
    highs: 1.1,
    brilliance: 0.5,
  },
};

afterEach(() => {
  vi.doUnmock('react');
  vi.resetModules();
  vi.restoreAllMocks();
});

describe('SessionMusicianPanel confidence helpers', () => {
  it('shows the melody low-confidence warning at the inclusive 0.15 threshold', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: {
          ...baseMeasurement,
          melodyDetail: {
            noteCount: 1,
            notes: [{ midi: 60, onset: 0.2, duration: 0.3 }],
            dominantNotes: [60],
            pitchRange: { min: 60, max: 60 },
            pitchConfidence: 0.15,
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

    expect(html).toContain('SESSION MUSICIAN');
    expect(html).toContain('title="Low confidence — treat this as approximate."');
    expect(html).toContain('⚠');
  });

  it('does not show the melody low-confidence warning above the threshold', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: {
          ...baseMeasurement,
          melodyDetail: {
            noteCount: 1,
            notes: [{ midi: 60, onset: 0.2, duration: 0.3 }],
            dominantNotes: [60],
            pitchRange: { min: 60, max: 60 },
            pitchConfidence: 0.16,
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

    expect(html).not.toContain('title="Low confidence — treat this as approximate."');
  });

  it('renders melody-guide stats without a filtered prefix and disables the confidence slider', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: {
          ...baseMeasurement,
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
    expect(html).toContain('Per-note confidence not available in melody-guide mode');
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

  it('derives transcription provenance only for the active pitch-note source', () => {
    const mixedSourceTranscriptionDetail: TranscriptionDetail = {
      transcriptionMethod: 'torchcrepe-viterbi',
      noteCount: 4,
      averageConfidence: 0.83,
      stemSeparationUsed: true,
      fullMixFallback: false,
      stemsTranscribed: ['bass', 'other'],
      dominantPitches: [
        { pitchMidi: 48, pitchName: 'C3', count: 2 },
        { pitchMidi: 60, pitchName: 'C4', count: 2 },
      ],
      pitchRange: {
        minMidi: 48,
        maxMidi: 60,
        minName: 'C3',
        maxName: 'C4',
      },
      notes: [
        {
          pitchMidi: 48,
          pitchName: 'C3',
          onsetSeconds: 0,
          durationSeconds: 0.5,
          confidence: 0.92,
          stemSource: 'bass',
        },
      ],
    };

    expect(deriveTranscriptionProvenance('pitchNote', mixedSourceTranscriptionDetail)).toEqual({
      transcriptionPathLabel: 'STEM-AWARE',
      stemSourcesLabel: 'bass, other',
    });
    expect(deriveTranscriptionProvenance('melodyGuide', mixedSourceTranscriptionDetail)).toEqual({
      transcriptionPathLabel: null,
      stemSourcesLabel: null,
    });
    expect(deriveTranscriptionProvenance('none', mixedSourceTranscriptionDetail)).toEqual({
      transcriptionPathLabel: null,
      stemSourcesLabel: null,
    });
    expect(
      deriveTranscriptionProvenance('pitchNote', {
        ...mixedSourceTranscriptionDetail,
        stemSeparationUsed: false,
        stemsTranscribed: ['full_mix'],
      }),
    ).toEqual({
      transcriptionPathLabel: 'FULL MIX',
      stemSourcesLabel: null,
    });
  });

  it('shows a quality-limited badge for pitch-note full-mix fallback results', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: {
          ...baseMeasurement,
          transcriptionDetail: {
          transcriptionMethod: 'torchcrepe-viterbi',
          noteCount: 2,
          averageConfidence: 0.42,
          stemSeparationUsed: false,
          fullMixFallback: true,
          stemsTranscribed: ['full_mix'],
          dominantPitches: [{ pitchMidi: 48, pitchName: 'C3', count: 2 }],
          pitchRange: {
            minMidi: 48,
            maxMidi: 52,
            minName: 'C3',
            maxName: 'E3',
          },
          notes: [
            {
              pitchMidi: 48,
              pitchName: 'C3',
              onsetSeconds: 0.1,
              durationSeconds: 0.4,
              confidence: 0.48,
              stemSource: 'full_mix',
            },
            {
              pitchMidi: 52,
              pitchName: 'E3',
              onsetSeconds: 0.8,
              durationSeconds: 0.2,
              confidence: 0.36,
              stemSource: 'full_mix',
            },
          ],
          },
        },
      }),
    );

    expect(html).toContain('FULL MIX');
    expect(html).toContain('FULL MIX — quality limited');
  });

  it('hides pitch-note provenance badges and updates helper copy in melody-guide mixed-source mode', async () => {
    vi.resetModules();
    vi.doMock('react', async () => {
      const actual = await vi.importActual<typeof import('react')>('react');
      let useStateCallCount = 0;

      return {
        ...actual,
        default: actual,
        useState<T>(initialState: T | (() => T)) {
          useStateCallCount += 1;
          if (useStateCallCount === 3) {
            return actual.useState('melodyGuide' as T);
          }
          return actual.useState(initialState);
        },
      };
    });

    const { SessionMusicianPanel: MockedSessionMusicianPanel } = await import('../../src/components/SessionMusicianPanel');

    const html = renderToStaticMarkup(
      React.createElement(MockedSessionMusicianPanel, {
        phase1: {
          ...baseMeasurement,
          transcriptionDetail: {
            transcriptionMethod: 'torchcrepe-viterbi',
            noteCount: 4,
            averageConfidence: 0.83,
            stemSeparationUsed: true,
            fullMixFallback: false,
            stemsTranscribed: ['bass', 'other'],
            dominantPitches: [
              { pitchMidi: 48, pitchName: 'C3', count: 2 },
              { pitchMidi: 60, pitchName: 'C4', count: 2 },
            ],
            pitchRange: {
              minMidi: 48,
              maxMidi: 60,
              minName: 'C3',
              maxName: 'C4',
            },
            notes: [
              {
                pitchMidi: 48,
                pitchName: 'C3',
                onsetSeconds: 0,
                durationSeconds: 0.5,
                confidence: 0.92,
                stemSource: 'bass',
              },
            ],
          },
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

    expect(html).toContain('MELODY GUIDE: ESSENTIA');
    expect(html).not.toContain('STEM-AWARE');
    expect(html).not.toContain('STEMS: bass, other');
    expect(html).toContain('Per-note confidence not available in melody-guide mode');
    expect(html).not.toContain('Adjust confidence threshold to filter noise before export.');
    expect(html).toContain('Essentia melody guide. Adjust quantize before preview/export.');
  });
});

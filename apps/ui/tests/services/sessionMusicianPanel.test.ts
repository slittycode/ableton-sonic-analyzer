import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  deriveNoteDraftRenderState,
  deriveTranscriptionProvenance,
  filterNotesByConfidence,
  formatFilteredNoteCount,
  formatVibratoConfidence,
  isLegacyTranscriptionMethod,
  MIDI_DOWNLOAD_FILE_NAME,
  SessionMusicianPanel,
} from '../../src/components/SessionMusicianPanel';
import type { MeasurementResult, MelodyDetail, TranscriptionDetail } from '../../src/types';

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

const stemAwareTranscription = (overrides: Partial<TranscriptionDetail> = {}): TranscriptionDetail => ({
  transcriptionMethod: 'torchcrepe-viterbi',
  noteCount: 2,
  averageConfidence: 0.72,
  stemSeparationUsed: true,
  fullMixFallback: false,
  stemsTranscribed: ['bass', 'other'],
  dominantPitches: [
    { pitchMidi: 48, pitchName: 'C3', count: 2 },
    { pitchMidi: 60, pitchName: 'C4', count: 1 },
  ],
  pitchRange: { minMidi: 48, maxMidi: 60, minName: 'C3', maxName: 'C4' },
  notes: [
    {
      pitchMidi: 48,
      pitchName: 'C3',
      onsetSeconds: 0,
      durationSeconds: 0.5,
      confidence: 0.92,
      stemSource: 'bass',
    },
    {
      pitchMidi: 60,
      pitchName: 'C4',
      onsetSeconds: 0.6,
      durationSeconds: 0.4,
      confidence: 0.65,
      stemSource: 'other',
    },
  ],
  ...overrides,
});

const melodyContour = (overrides: Partial<MelodyDetail> = {}): MelodyDetail => ({
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
  vibratoConfidence: 0,
  ...overrides,
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Backwards-compat pure helpers (the ones still exported from the panel)
// ---------------------------------------------------------------------------

describe('SessionMusicianPanel backwards-compat helpers', () => {
  it('exports the legacy MIDI download filename for old tests', () => {
    expect(MIDI_DOWNLOAD_FILE_NAME).toBe('track-analysis.mid');
  });

  it('filters notes at or above the confidence threshold', () => {
    const filtered = filterNotesByConfidence(
      [
        { midi: 48, name: 'C3', startTime: 0.1, duration: 0.4, velocity: 90, confidence: 0.19 },
        { midi: 55, name: 'G3', startTime: 0.6, duration: 0.3, velocity: 90, confidence: 0.2 },
        { midi: 60, name: 'C4', startTime: 0.9, duration: 0.25, velocity: 90, confidence: 0.8 },
      ],
      0.2,
    );
    expect(filtered).toHaveLength(2);
    expect(filtered.map((note) => note.midi)).toEqual([55, 60]);
  });

  it('formats note counts without a filtered prefix when threshold is zero', () => {
    expect(formatFilteredNoteCount(3, 3, 0)).toBe('3 NOTES');
  });

  it('formats filtered note counts when the threshold is active', () => {
    expect(formatFilteredNoteCount(2, 3, 0.2)).toBe('2 / 3 NOTES');
  });

  it('formats present vibrato confidence below 1 percent as less-than-one', () => {
    expect(formatVibratoConfidence(0.004, true)).toBe('< 1');
  });

  it('formats present vibrato confidence normally when it rounds above zero', () => {
    expect(formatVibratoConfidence(0.15, true)).toBe('15');
  });

  it('formats not-detected vibrato confidence as zero without the present guard', () => {
    expect(formatVibratoConfidence(0, false)).toBe('0');
  });

  it('re-exports deriveTranscriptionProvenance for the legacy activeSource shape', () => {
    const provenance = deriveTranscriptionProvenance('pitchNote', stemAwareTranscription());
    expect(provenance).toEqual({
      transcriptionPathLabel: 'STEM-AWARE',
      stemSourcesLabel: 'bass, other',
    });
    expect(
      deriveTranscriptionProvenance('melodyGuide', stemAwareTranscription()),
    ).toEqual({ transcriptionPathLabel: null, stemSourcesLabel: null });
  });

  it('re-exports renderState helpers from the panel module path', () => {
    expect(typeof deriveNoteDraftRenderState).toBe('function');
    expect(typeof isLegacyTranscriptionMethod).toBe('function');
  });
});

// ---------------------------------------------------------------------------
// Block-A render-state matrix via the panel's static markup
// ---------------------------------------------------------------------------

describe('SessionMusicianPanel — Block A render states', () => {
  it('renders the stem-aware draft with piano roll, stem filter, slider, and Download', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: { ...baseMeasurement, transcriptionDetail: stemAwareTranscription() },
        pitchNoteMode: 'stem_notes',
      }),
    );
    expect(html).toContain('data-render-state="stem-aware"');
    expect(html).toContain('data-testid="note-draft-piano-roll"');
    expect(html).toContain('data-testid="midi-download-stems"');
    expect(html).toContain('data-testid="midi-preview-stems"');
    expect(html).toContain('Workable draft · 72%');
    // Stem filter buttons render
    expect(html).toMatch(/>bass</);
    expect(html).toMatch(/>other</);
    // Confidence slider markup
    expect(html).toMatch(/type="range"/);
    // What stays useful chips
    expect(html).toContain('Range: C3 – C4');
    expect(html).toContain('Most-played: C3, C4');
    expect(html).toContain('Avg note length');
  });

  it('renders the full-mix-fallback override, hides stem filter and slider, keeps Download', () => {
    const transcriptionDetail = stemAwareTranscription({
      stemSeparationUsed: false,
      fullMixFallback: true,
      stemsTranscribed: ['full_mix'],
      notes: stemAwareTranscription().notes.map((note) => ({ ...note, stemSource: 'full_mix' })),
    });
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: { ...baseMeasurement, transcriptionDetail },
        pitchNoteMode: 'stem_notes',
      }),
    );
    expect(html).toContain('data-render-state="full-mix-fallback"');
    expect(html).toContain('Full-mix fallback');
    expect(html).toContain('drift between instruments');
    expect(html).toContain('data-testid="note-draft-piano-roll"');
    expect(html).toContain('data-testid="midi-download-stems"');
    // No stem filter buttons (only full_mix would appear, and we hide the row)
    expect(html).not.toMatch(/Stems:/);
    // The confidence slider (label "CONFIDENCE") is hidden in fallback mode.
    // The Swing slider in QuantizeControls is still present, so checking for
    // any type="range" would be a false positive — anchor on the unique label.
    expect(html).not.toContain('>Confidence<');
  });

  it('routes basic-pitch (legacy) data to the legacy render state even when fullMixFallback is also true', () => {
    const transcriptionDetail = stemAwareTranscription({
      transcriptionMethod: 'basic-pitch',
      fullMixFallback: true,
      stemSeparationUsed: false,
    });
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: { ...baseMeasurement, transcriptionDetail },
        pitchNoteMode: 'stem_notes',
      }),
    );
    expect(html).toContain('data-render-state="legacy"');
    expect(html).toContain('Legacy run');
    expect(html).toContain('Re-analyze for current stem-aware quality');
    // Confirm precedence on the helper directly too:
    expect(deriveNoteDraftRenderState(transcriptionDetail, 'stem_notes')).toBe('legacy');
  });

  it('shows requested-but-unavailable notice when stem_notes is on but transcription is missing', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: { ...baseMeasurement },
        pitchNoteMode: 'stem_notes',
      }),
    );
    expect(html).toContain('data-render-state="requested-but-unavailable"');
    // Apostrophe is HTML-escaped to &#x27; in the rendered markup.
    expect(html).toContain('didn&#x27;t produce output');
    expect(html).not.toContain('data-testid="note-draft-piano-roll"');
    expect(html).not.toContain('data-testid="midi-download-stems"');
  });

  it('does not render Block A when pitchNoteMode is off, even with stale transcription data', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: { ...baseMeasurement, transcriptionDetail: stemAwareTranscription() },
        pitchNoteMode: 'off',
      }),
    );
    expect(html).not.toContain('data-testid="note-draft-block"');
    expect(html).not.toContain('data-testid="note-draft-piano-roll"');
    expect(html).not.toContain('data-testid="midi-download-stems"');
    // Off-state banner is the only thing rendered above where the block would be
    expect(html).toContain('data-testid="session-musician-off-banner"');
  });

  it('shows the ran-with-no-result notice when transcription arrives empty', () => {
    const transcriptionDetail = stemAwareTranscription({ notes: [], noteCount: 0 });
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: { ...baseMeasurement, transcriptionDetail },
        pitchNoteMode: 'stem_notes',
      }),
    );
    expect(html).toContain('data-render-state="ran-with-no-result"');
    expect(html).toContain('didn&#x27;t find a pitched line');
    expect(html).not.toContain('data-testid="note-draft-piano-roll"');
    expect(html).not.toContain('data-testid="midi-download-stems"');
  });

  it('renders the Unreliable band pill when stem-aware confidence is below 25%', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: {
          ...baseMeasurement,
          transcriptionDetail: stemAwareTranscription({ averageConfidence: 0.12 }),
        },
        pitchNoteMode: 'stem_notes',
      }),
    );
    expect(html).toContain('Unreliable · 12%');
    expect(html).toContain("don&#x27;t trust specific notes");
    // Piano roll + Download still render — we badge, we don't hide
    expect(html).toContain('data-testid="note-draft-piano-roll"');
    expect(html).toContain('data-testid="midi-download-stems"');
  });
});

// ---------------------------------------------------------------------------
// Block-B (melody contour) render states
// ---------------------------------------------------------------------------

describe('SessionMusicianPanel — Block B (melody contour) render states', () => {
  it('renders the melody block with its own Preview/Download and band pill', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: { ...baseMeasurement, melodyDetail: melodyContour({ pitchConfidence: 0.62 }) },
      }),
    );
    expect(html).toContain('data-testid="melody-contour-block"');
    expect(html).toContain('data-testid="melody-contour-piano-roll"');
    expect(html).toContain('data-testid="midi-download-melody"');
    expect(html).toContain('Workable draft · 62%');
    expect(html).toContain('Download melody .mid');
    // No per-note confidence slider in melody mode
    expect(html).not.toMatch(/Confidence<\/span><input/);
  });

  it('renders ran-with-no-result for empty melody notes', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: { ...baseMeasurement, melodyDetail: melodyContour({ noteCount: 0, notes: [] }) },
      }),
    );
    expect(html).toContain('data-render-state="ran-with-no-result"');
    expect(html).toContain('Melody extraction ran but');
    expect(html).not.toContain('data-testid="melody-contour-piano-roll"');
    expect(html).not.toContain('data-testid="midi-download-melody"');
  });

  it('renders Rough band copy when melody confidence is between 25 and 50 percent', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: { ...baseMeasurement, melodyDetail: melodyContour({ pitchConfidence: 0.3 }) },
      }),
    );
    expect(html).toContain('Rough sketch · 30%');
    expect(html).toContain('data-testid="midi-download-melody"');
  });
});

// ---------------------------------------------------------------------------
// Off-state banner copy and visibility
// ---------------------------------------------------------------------------

describe('SessionMusicianPanel — off-state banner', () => {
  it('renders the with-melody banner when opted out and melody is present', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: { ...baseMeasurement, melodyDetail: melodyContour() },
        pitchNoteMode: 'off',
        hasStemListeningNotes: true,
      }),
    );
    expect(html).toContain('data-testid="session-musician-off-banner"');
    expect(html).toContain("You&#x27;re seeing the measurement-layer melody contour below");
    expect(html).toContain('stem listening notes below');
    // Melody block still renders
    expect(html).toContain('data-testid="melody-contour-block"');
  });

  it('renders the no-melody-with-listening banner when opted out, no melody, listening notes present', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: { ...baseMeasurement },
        pitchNoteMode: 'off',
        hasStemListeningNotes: true,
      }),
    );
    expect(html).toContain('data-testid="session-musician-off-banner"');
    expect(html).toContain('appears when available');
    expect(html).toContain('stem listening notes below describe each stem');
    expect(html).not.toContain('data-testid="melody-contour-block"');
    expect(html).not.toContain('data-testid="note-draft-block"');
  });

  it('renders the no-melody-no-listening banner when opted out and nothing else is available', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: { ...baseMeasurement },
        pitchNoteMode: 'off',
        hasStemListeningNotes: false,
      }),
    );
    expect(html).toContain('data-testid="session-musician-off-banner"');
    expect(html).toContain('appears when available');
    // Should NOT include the cross-link sentence
    expect(html).not.toContain('stem listening notes below describe each stem');
  });

  it('does not render the off banner when pitchNoteMode is null (legacy snapshot)', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: { ...baseMeasurement, transcriptionDetail: stemAwareTranscription() },
        pitchNoteMode: null,
      }),
    );
    expect(html).not.toContain('data-testid="session-musician-off-banner"');
    // Inferred from data — stem-aware block renders
    expect(html).toContain('data-render-state="stem-aware"');
  });
});

// ---------------------------------------------------------------------------
// Simultaneous rendering of both blocks
// ---------------------------------------------------------------------------

describe('SessionMusicianPanel — simultaneous rendering', () => {
  it('renders both Block A and Block B at once when both data sources are present', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: {
          ...baseMeasurement,
          transcriptionDetail: stemAwareTranscription(),
          melodyDetail: melodyContour(),
        },
        pitchNoteMode: 'stem_notes',
      }),
    );
    expect(html).toContain('data-testid="note-draft-block"');
    expect(html).toContain('data-testid="melody-contour-block"');
    expect(html).toContain('data-testid="midi-download-stems"');
    expect(html).toContain('data-testid="midi-download-melody"');
    // No source-mode toggle remains
    expect(html).not.toContain('PITCH/NOTE</button>');
    expect(html).not.toContain('MELODY</button>');
    // Panel summary describes both
    expect(html).toContain('Two reads of the pitched material');
  });

  it('renders the no-data message when neither block has content and we are not opted out', () => {
    const html = renderToStaticMarkup(
      React.createElement(SessionMusicianPanel, {
        phase1: { ...baseMeasurement },
        pitchNoteMode: null,
      }),
    );
    expect(html).toContain('data-testid="session-musician-no-data"');
    expect(html).toContain('PITCH &amp; MELODY UNAVAILABLE');
  });
});

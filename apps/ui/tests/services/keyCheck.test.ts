import { describe, expect, it } from 'vitest';

import {
  APPROXIMATE_KEY_CONFIDENCE,
  buildKeyCheckModel,
  computerKeyLabelFor,
  computerKeyToMidi,
  droneMidis,
  isBlackKey,
  midiNoteName,
  midiToFrequency,
  parseKeyLabel,
  relativeKey,
  resolveTuning,
} from '../../src/services/keyCheck';
import type { Phase1Result } from '../../src/types';
import { phase1EnvelopeFixture } from '../fixtures/phase1FullPayload';

const fixture = phase1EnvelopeFixture as unknown as Phase1Result;

function withOverrides(overrides: Partial<Phase1Result>): Phase1Result {
  return { ...fixture, ...overrides };
}

describe('parseKeyLabel', () => {
  it('parses Essentia labels into tonic, mode and scale', () => {
    expect(parseKeyLabel('A minor')).toEqual({
      label: 'A minor',
      tonicPc: 9,
      mode: 'minor',
      scalePcs: [9, 11, 0, 2, 4, 5, 7],
      preferFlats: false,
    });
    expect(parseKeyLabel('C major')?.scalePcs).toEqual([0, 2, 4, 5, 7, 9, 11]);
  });

  it('handles accidentals and keeps their spelling', () => {
    expect(parseKeyLabel('F# minor')).toMatchObject({ label: 'F# minor', tonicPc: 6, preferFlats: false });
    expect(parseKeyLabel('Bb major')).toMatchObject({ label: 'Bb major', tonicPc: 10, preferFlats: true });
    expect(parseKeyLabel('E♭ minor')).toMatchObject({ label: 'Eb minor', tonicPc: 3 });
    expect(parseKeyLabel('Cb major')).toMatchObject({ tonicPc: 11 });
  });

  it('spells conventionally-flat natural keys with flats', () => {
    expect(parseKeyLabel('F major')?.preferFlats).toBe(true);
    expect(parseKeyLabel('D minor')?.preferFlats).toBe(true);
    expect(parseKeyLabel('G major')?.preferFlats).toBe(false);
    expect(parseKeyLabel('E minor')?.preferFlats).toBe(false);
  });

  it('accepts short forms', () => {
    expect(parseKeyLabel('Am')).toMatchObject({ tonicPc: 9, mode: 'minor' });
    expect(parseKeyLabel('ebmaj')).toMatchObject({ tonicPc: 3, mode: 'major' });
    expect(parseKeyLabel('G')).toMatchObject({ tonicPc: 7, mode: 'major' });
  });

  it('returns null for unusable labels', () => {
    expect(parseKeyLabel(null)).toBeNull();
    expect(parseKeyLabel('')).toBeNull();
    expect(parseKeyLabel('Unknown')).toBeNull();
    expect(parseKeyLabel('A dorian')).toBeNull();
    expect(parseKeyLabel('H minor')).toBeNull();
  });
});

describe('relativeKey', () => {
  it('maps minor to its relative major and back, keeping the spelling', () => {
    expect(relativeKey(parseKeyLabel('A minor')!).label).toBe('C major');
    expect(relativeKey(parseKeyLabel('F# minor')!).label).toBe('A major');
    expect(relativeKey(parseKeyLabel('Eb major')!).label).toBe('C minor');
    expect(relativeKey(parseKeyLabel('D minor')!).label).toBe('F major');
  });
});

describe('note helpers', () => {
  it('computes equal-tempered frequency against an A4 reference', () => {
    expect(midiToFrequency(69)).toBe(440);
    expect(midiToFrequency(57)).toBeCloseTo(220, 10);
    expect(midiToFrequency(60)).toBeCloseTo(261.6256, 3);
    expect(midiToFrequency(69, 442)).toBe(442);
  });

  it('names notes with MIDI 60 = C4, like the rest of ASA', () => {
    expect(midiNoteName(60, false)).toBe('C4');
    expect(midiNoteName(57, false)).toBe('A3');
    expect(midiNoteName(70, true)).toBe('Bb4');
    expect(midiNoteName(70, false)).toBe('A#4');
  });

  it('identifies black keys', () => {
    expect([60, 61, 62, 63, 64, 65, 66].map(isBlackKey)).toEqual([false, true, false, true, false, false, true]);
  });

  it('builds a mode-neutral tonic + fifth drone around C3', () => {
    expect(droneMidis(parseKeyLabel('A minor')!)).toEqual([57, 64]);
    expect(droneMidis(parseKeyLabel('C major')!)).toEqual([48, 55]);
  });
});

describe('computer keyboard mapping', () => {
  it('follows the Live computer MIDI keyboard layout', () => {
    expect(computerKeyToMidi('KeyA', 48)).toBe(48);
    expect(computerKeyToMidi('KeyW', 48)).toBe(49);
    expect(computerKeyToMidi('KeyK', 48)).toBe(60);
    expect(computerKeyToMidi('Semicolon', 48)).toBe(64);
    expect(computerKeyToMidi('KeyZ', 48)).toBeNull();
    expect(computerKeyToMidi('Space', 48)).toBeNull();
  });

  it('labels keys with their computer key', () => {
    expect(computerKeyLabelFor(48, 48)).toBe('A');
    expect(computerKeyLabelFor(64, 48)).toBe(';');
    expect(computerKeyLabelFor(65, 48)).toBeNull();
  });
});

describe('resolveTuning', () => {
  it('uses the measured reference when it is in range', () => {
    expect(resolveTuning({ tuningFrequency: 440.12, tuningCents: 0.05 })).toEqual({
      referenceHz: 440.12,
      cents: 0.05,
      source: 'measured',
    });
  });

  it('derives cents when only the frequency is reported', () => {
    const tuning = resolveTuning({ tuningFrequency: 432, tuningCents: null });
    expect(tuning.source).toBe('measured');
    expect(tuning.cents).toBeCloseTo(-31.77, 1);
  });

  it('falls back to 440 Hz when tuning was not measured (fast mode)', () => {
    expect(resolveTuning({ tuningFrequency: undefined, tuningCents: undefined })).toEqual({
      referenceHz: 440,
      cents: null,
      source: 'not_measured',
    });
  });

  it('rejects estimates more than about a semitone from 440 Hz', () => {
    expect(resolveTuning({ tuningFrequency: 400, tuningCents: -165 }).source).toBe('rejected');
    expect(resolveTuning({ tuningFrequency: 480, tuningCents: 150 }).referenceHz).toBe(440);
  });
});

describe('buildKeyCheckModel', () => {
  it('re-expresses the Phase 1 key, trust, ensemble and tuning', () => {
    const model = buildKeyCheckModel(fixture);
    expect(model.measured?.label).toBe('A minor');
    expect(model.trust).toMatchObject({ status: 'authoritative', label: 'LOCAL', tone: 'success' });
    expect(model.trust.plainEnglish).toBe('Key was measured locally.');
    expect(model.ensemble).toEqual({ agreeing: 2, total: 3 });
    expect(model.alternates.map((alt) => alt.label)).toEqual(['C major']);
    expect(model.tuning.referenceHz).toBe(440.12);
    expect(model.isApproximate).toBe(false);
  });

  it('never lists the shipped key as its own alternate and dedupes alternates', () => {
    const model = buildKeyCheckModel(
      withOverrides({
        keyEnsemble: {
          method: 'profile_vote.v1',
          agreement: 1,
          profiles: [
            { profile: 'edma', key: 'A minor', strength: 0.5 },
            { profile: 'temperley', key: 'E minor', strength: 0.6 },
            { profile: 'krumhansl', key: 'C major', strength: 0.4 },
          ],
          alternates: [
            { key: 'C major', strength: 0.4 },
            { key: 'A minor', strength: 0.5 },
            { key: 'E minor', strength: 0.6 },
            { key: 'Em', strength: 0.55 },
          ],
        },
      }),
    );
    expect(model.alternates.map((alt) => alt.label)).toEqual(['E minor', 'C major']);
  });

  it('flags low-confidence keys as approximate, at the same threshold as the results header', () => {
    expect(buildKeyCheckModel(withOverrides({ keyConfidence: APPROXIMATE_KEY_CONFIDENCE })).isApproximate).toBe(true);
    expect(buildKeyCheckModel(withOverrides({ keyConfidence: 0.61 })).isApproximate).toBe(false);
  });

  it('degrades cleanly when Phase 1 has no key, ensemble, trust or tuning', () => {
    const model = buildKeyCheckModel(
      withOverrides({
        key: null,
        keyEnsemble: null,
        fundamentalsQuality: null,
        tuningFrequency: null,
        tuningCents: null,
      }),
    );
    expect(model.measured).toBeNull();
    expect(model.rawKeyLabel).toBeNull();
    expect(model.ensemble).toBeNull();
    expect(model.alternates).toEqual([]);
    expect(model.trust.label).toBe('NOT RUN');
    expect(model.tuning.source).toBe('not_measured');
  });

  it('keeps an unparseable label for display without highlighting anything', () => {
    const model = buildKeyCheckModel(withOverrides({ key: 'A dorian' }));
    expect(model.measured).toBeNull();
    expect(model.rawKeyLabel).toBe('A dorian');
  });
});

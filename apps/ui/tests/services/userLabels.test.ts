/**
 * Locks in the single translation layer from internal Phase 1 field paths
 * (camelCase JSON keys) to producer-readable labels. The CitationBlock
 * primitive (audit Finding #2) reads through this map at every Mix Chain /
 * Patches / Sonic Element card render.
 */
import { describe, expect, it } from 'vitest';
import { FIELD_LABELS, humanizeFieldPath } from '../../src/services/userLabels';

describe('FIELD_LABELS', () => {
  // Spot-check a representative sample of the curated map. The full set
  // (~50 entries) is exercised at render time via the CitationBlock tests;
  // here we just guard against accidental removals of the load-bearing
  // entries the audit specifically called out.
  it.each<[string, string]>([
    ['bpm', 'Tempo'],
    ['bpmConfidence', 'Tempo confidence'],
    ['key', 'Key'],
    ['keyConfidence', 'Key confidence'],
    ['timeSignature', 'Meter'],
    ['lufsIntegrated', 'Integrated loudness'],
    ['truePeak', 'True peak'],
    ['crestFactor', 'Crest factor'],
    ['stereoWidth', 'Stereo width'],
    ['spectralBalance.subBass', 'Sub-bass balance'],
    ['spectralBalance.highs', 'Highs balance'],
    ['kickDetail.fundamentalHz', 'Kick fundamental frequency'],
    ['kickDetail.thd', 'Kick harmonic distortion (THD)'],
    ['sidechainDetail.pumpingStrength', 'Pumping strength'],
    ['genreDetail.genre', 'Genre'],
    ['reverbDetail.rt60', 'Reverb tail (RT60)'],
  ])('maps %s to producer label %s', (path, expected) => {
    expect(FIELD_LABELS[path]).toBe(expected);
  });
});

describe('humanizeFieldPath', () => {
  it('returns the curated label when one exists', () => {
    expect(humanizeFieldPath('bpm')).toBe('Tempo');
    expect(humanizeFieldPath('spectralBalance.highs')).toBe('Highs balance');
  });

  it('splits camelCase + dots for unknown paths', () => {
    // Defensive — these aren't curated yet but must not render as raw JSON.
    expect(humanizeFieldPath('totallyNewField')).toBe('Totally new field');
    expect(humanizeFieldPath('nested.somethingElse')).toBe('Nested · something else');
    expect(humanizeFieldPath('deeply.nested.fieldName')).toBe('Deeply · nested · field name');
  });

  it('handles ALLCAPS run as a single uppercase block', () => {
    // "URLPath" should read as "Url path" (or "URL path"); the current
    // implementation prefers the safe lowercased form. Either is acceptable
    // as long as it doesn't expose raw camelCase.
    expect(humanizeFieldPath('URLPath')).toMatch(/url path/i);
  });

  it('handles plain lowercase paths', () => {
    expect(humanizeFieldPath('bpm')).toBe('Tempo'); // mapped
    expect(humanizeFieldPath('unmappedlower')).toBe('Unmappedlower'); // unmapped
  });

  it('handles paths with digits', () => {
    expect(humanizeFieldPath('rt60')).toBe('Rt60');
    expect(humanizeFieldPath('lufs5')).toBe('Lufs5');
  });
});

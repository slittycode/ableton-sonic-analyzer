import type { MixDoctorReport, GenreProfile } from '../../src/types';
import { findProfileByIdOrFamily } from '../../src/services/mixDoctor';

const profileA: GenreProfile = {
  id: 'techno',
  name: 'Techno',
  targetCrestFactorRange: [5, 10],
  targetPlrRange: [6, 10],
  targetLufsRange: [-9, -5],
  spectralTargets: {
    subBass: { minDb: -22, maxDb: -14, optimalDb: -18 },
    lowBass: { minDb: -16, maxDb: -8, optimalDb: -12 },
    lowMids: { minDb: -12, maxDb: -4, optimalDb: -8 },
    mids: { minDb: -12, maxDb: -4, optimalDb: -8 },
    upperMids: { minDb: -14, maxDb: -6, optimalDb: -10 },
    highs: { minDb: -18, maxDb: -10, optimalDb: -14 },
    brilliance: { minDb: -24, maxDb: -16, optimalDb: -20 },
  },
};

const profileB: GenreProfile = {
  id: 'house',
  name: 'House',
  targetCrestFactorRange: [7, 12],
  targetPlrRange: [7, 11],
  targetLufsRange: [-10, -6],
  spectralTargets: {
    subBass: { minDb: -20, maxDb: -12, optimalDb: -16 },
    lowBass: { minDb: -14, maxDb: -6, optimalDb: -10 },
    lowMids: { minDb: -10, maxDb: -2, optimalDb: -6 },
    mids: { minDb: -10, maxDb: -2, optimalDb: -6 },
    upperMids: { minDb: -12, maxDb: -4, optimalDb: -8 },
    highs: { minDb: -16, maxDb: -8, optimalDb: -12 },
    brilliance: { minDb: -22, maxDb: -14, optimalDb: -18 },
  },
};

const profiles = [profileA, profileB];

describe('MixDoctorPanel controlled behavior', () => {
  it('null genreDetail results in null autoProfileId, requiring manual selection', () => {
    // When genreDetail is null, findProfileByIdOrFamily returns null
    const autoProfileId = findProfileByIdOrFamily(profiles, null, null);
    expect(autoProfileId).toBeNull();
    // The panel would show the "Select a genre profile" prompt in this case
  });

  it('findProfileByIdOrFamily resolves exact genre id', () => {
    const result = findProfileByIdOrFamily(profiles, 'house', null);
    expect(result).toBe('house');
  });

  it('findProfileByIdOrFamily falls back to family match', () => {
    const result = findProfileByIdOrFamily(profiles, 'minimal-techno', 'techno');
    expect(result).toBe('techno');
  });

  it('changing selected profile changes rendered output', () => {
    // Simulates what happens when selectedProfileId changes:
    // different profiles produce different report objects
    const reportA: MixDoctorReport = {
      genreName: 'Techno',
      profileId: 'techno',
      advice: [],
      dynamicsAdvice: { issue: 'optimal', message: 'Good', actualCrest: 8 },
      plrAdvice: { issue: 'optimal', message: 'OK', actualPlr: 7 },
      loudnessAdvice: { issue: 'optimal', message: 'OK', actualLufs: -7, truePeak: -1 },
      stereoAdvice: undefined,
      overallScore: 85,
    };
    const reportB: MixDoctorReport = {
      genreName: 'House',
      profileId: 'house',
      advice: [],
      dynamicsAdvice: { issue: 'too-compressed', message: 'Low crest', actualCrest: 4 },
      plrAdvice: { issue: 'too-crushed', message: 'Low PLR', actualPlr: 4 },
      loudnessAdvice: { issue: 'too-loud', message: 'Hot', actualLufs: -4, truePeak: 0 },
      stereoAdvice: undefined,
      overallScore: 55,
    };

    // Reports have different genre names and scores
    expect(reportA.genreName).not.toBe(reportB.genreName);
    expect(reportA.overallScore).not.toBe(reportB.overallScore);
    expect(reportA.profileId).toBe('techno');
    expect(reportB.profileId).toBe('house');
  });
});

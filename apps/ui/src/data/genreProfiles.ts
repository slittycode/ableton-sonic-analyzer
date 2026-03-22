/**
 * Static knowledge base defining standard spectral and dynamic profiles for genres.
 * Values are in dB relative to full scale (dBFS), representing the *average*
 * energy expected in that spectral band for a commercially mixed track.
 *
 * LUFS targets reflect streaming-era mastering norms:
 * - Streaming platforms normalise to -14 (Spotify/YouTube) or -16 (Apple Music)
 * - Club-oriented genres push louder (-10 to -8 LUFS pre-normalization)
 * - Acoustic / ambient sit naturally quieter (-18 to -14 LUFS)
 *
 * Spectral bands:
 * - Sub Bass (20-80 Hz)
 * - Low Bass (80-250 Hz)
 * - Low Mids (250-500 Hz)
 * - Mids (500-2000 Hz)
 * - Upper Mids (2000-5000 Hz)
 * - Highs (5000-10000 Hz)
 * - Brilliance (10000-20000 Hz)
 */

export interface SpectralTarget {
  minDb: number;
  maxDb: number;
  optimalDb: number;
}

export interface GenreProfile {
  id: string;
  name: string;
  targetCrestFactorRange: [number, number];
  targetPlrRange: [number, number];
  targetLufsRange: [number, number];
  spectralTargets: {
    'Sub Bass': SpectralTarget;
    'Low Bass': SpectralTarget;
    'Low Mids': SpectralTarget;
    Mids: SpectralTarget;
    'Upper Mids': SpectralTarget;
    Highs: SpectralTarget;
    Brilliance: SpectralTarget;
  };
}

export const GENRE_PROFILES: GenreProfile[] = [
  // ═══════════════════════════════════════════════════════════════════════════════
  // CORE GENRES (Legacy compatibility)
  // ═══════════════════════════════════════════════════════════════════════════════
  {
    id: 'edm',
    name: 'Electronic / EDM',
    targetCrestFactorRange: [5, 9], // heavily compressed
    targetPlrRange: [6, 10],
    targetLufsRange: [-16, -10],
    spectralTargets: {
      'Sub Bass': { minDb: -15, maxDb: -8, optimalDb: -11 },
      'Low Bass': { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Low Mids': { minDb: -26, maxDb: -18, optimalDb: -22 }, // often scooped for clarity
      Mids: { minDb: -22, maxDb: -14, optimalDb: -18 },
      'Upper Mids': { minDb: -24, maxDb: -16, optimalDb: -20 },
      Highs: { minDb: -28, maxDb: -18, optimalDb: -23 },
      Brilliance: { minDb: -32, maxDb: -22, optimalDb: -27 },
    },
  },
  {
    id: 'hiphop',
    name: 'Hip Hop / Trap',
    targetCrestFactorRange: [7, 11], // punchy drums, thick subs
    targetPlrRange: [7, 11],
    targetLufsRange: [-14, -8],
    spectralTargets: {
      'Sub Bass': { minDb: -16, maxDb: -6, optimalDb: -10 }, // loudest sub bass
      'Low Bass': { minDb: -20, maxDb: -10, optimalDb: -15 },
      'Low Mids': { minDb: -28, maxDb: -18, optimalDb: -23 }, // vocal space
      Mids: { minDb: -20, maxDb: -12, optimalDb: -16 }, // vocal presence
      'Upper Mids': { minDb: -24, maxDb: -15, optimalDb: -19 },
      Highs: { minDb: -26, maxDb: -18, optimalDb: -22 },
      Brilliance: { minDb: -30, maxDb: -22, optimalDb: -26 },
    },
  },
  {
    id: 'rock',
    name: 'Rock / Metal',
    targetCrestFactorRange: [9, 14], // more dynamic range, transient drums
    targetPlrRange: [9, 14],
    targetLufsRange: [-16, -10],
    spectralTargets: {
      'Sub Bass': { minDb: -25, maxDb: -15, optimalDb: -20 }, // less sub weight
      'Low Bass': { minDb: -18, maxDb: -10, optimalDb: -14 }, // bass guitar & kick
      'Low Mids': { minDb: -20, maxDb: -12, optimalDb: -16 }, // guitar body
      Mids: { minDb: -18, maxDb: -10, optimalDb: -14 }, // guitars out front
      'Upper Mids': { minDb: -20, maxDb: -12, optimalDb: -16 }, // vocal & guitar attack
      Highs: { minDb: -24, maxDb: -16, optimalDb: -20 }, // cymbals
      Brilliance: { minDb: -30, maxDb: -20, optimalDb: -25 },
    },
  },
  {
    id: 'pop',
    name: 'Modern Pop',
    targetCrestFactorRange: [6, 10], // controlled, loud, vocal upfront
    targetPlrRange: [7, 11],
    targetLufsRange: [-16, -10],
    spectralTargets: {
      'Sub Bass': { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Low Bass': { minDb: -18, maxDb: -12, optimalDb: -15 },
      'Low Mids': { minDb: -24, maxDb: -16, optimalDb: -20 },
      Mids: { minDb: -18, maxDb: -10, optimalDb: -14 }, // vocal upfront
      'Upper Mids': { minDb: -18, maxDb: -10, optimalDb: -14 }, // vocal presence/air
      Highs: { minDb: -22, maxDb: -14, optimalDb: -18 }, // bright & airy
      Brilliance: { minDb: -26, maxDb: -16, optimalDb: -20 },
    },
  },
  {
    id: 'acoustic',
    name: 'Acoustic / Indie',
    targetCrestFactorRange: [12, 18], // highly dynamic, uncompressed
    targetPlrRange: [13, 20],
    targetLufsRange: [-20, -14],
    spectralTargets: {
      'Sub Bass': { minDb: -35, maxDb: -25, optimalDb: -30 }, // negligible sub
      'Low Bass': { minDb: -24, maxDb: -14, optimalDb: -19 }, // acoustic body
      'Low Mids': { minDb: -22, maxDb: -14, optimalDb: -18 }, // warmth
      Mids: { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Upper Mids': { minDb: -22, maxDb: -14, optimalDb: -18 },
      Highs: { minDb: -26, maxDb: -16, optimalDb: -21 }, // acoustic string noise
      Brilliance: { minDb: -32, maxDb: -22, optimalDb: -27 },
    },
  },

  // ═══════════════════════════════════════════════════════════════════════════════
  // ELECTRONIC SUBGENRES (35+ profiles with enhanced classification)
  // ═══════════════════════════════════════════════════════════════════════════════

  // --- AMBIENT / DOWNTEMPO ---
  {
    id: 'ambient',
    name: 'Ambient / Downtempo',
    targetCrestFactorRange: [10, 18],
    targetPlrRange: [12, 20],
    targetLufsRange: [-24, -16],
    spectralTargets: {
      'Sub Bass': { minDb: -28, maxDb: -18, optimalDb: -23 },
      'Low Bass': { minDb: -24, maxDb: -14, optimalDb: -19 },
      'Low Mids': { minDb: -22, maxDb: -14, optimalDb: -18 },
      Mids: { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Upper Mids': { minDb: -20, maxDb: -12, optimalDb: -16 },
      Highs: { minDb: -22, maxDb: -12, optimalDb: -17 },
      Brilliance: { minDb: -24, maxDb: -14, optimalDb: -19 },
    },
  },
  {
    id: 'ambient-drone',
    name: 'Ambient / Drone',
    targetCrestFactorRange: [12, 22],
    targetPlrRange: [14, 24],
    targetLufsRange: [-26, -18],
    spectralTargets: {
      'Sub Bass': { minDb: -38, maxDb: -22, optimalDb: -30 },
      'Low Bass': { minDb: -30, maxDb: -18, optimalDb: -24 },
      'Low Mids': { minDb: -26, maxDb: -16, optimalDb: -21 },
      Mids: { minDb: -24, maxDb: -14, optimalDb: -19 },
      'Upper Mids': { minDb: -26, maxDb: -16, optimalDb: -21 },
      Highs: { minDb: -28, maxDb: -16, optimalDb: -22 },
      Brilliance: { minDb: -30, maxDb: -18, optimalDb: -24 },
    },
  },
  {
    id: 'ambient-techno',
    name: 'Ambient Techno',
    targetCrestFactorRange: [10, 18],
    targetPlrRange: [12, 20],
    targetLufsRange: [-22, -16],
    spectralTargets: {
      'Sub Bass': { minDb: -30, maxDb: -18, optimalDb: -24 },
      'Low Bass': { minDb: -26, maxDb: -16, optimalDb: -21 },
      'Low Mids': { minDb: -24, maxDb: -16, optimalDb: -20 },
      Mids: { minDb: -22, maxDb: -14, optimalDb: -18 },
      'Upper Mids': { minDb: -24, maxDb: -14, optimalDb: -19 },
      Highs: { minDb: -26, maxDb: -14, optimalDb: -20 },
      Brilliance: { minDb: -28, maxDb: -16, optimalDb: -22 },
    },
  },
  {
    id: 'dub-techno',
    name: 'Dub Techno',
    targetCrestFactorRange: [8, 15],
    targetPlrRange: [10, 17],
    targetLufsRange: [-20, -14],
    spectralTargets: {
      'Sub Bass': { minDb: -24, maxDb: -14, optimalDb: -19 },
      'Low Bass': { minDb: -22, maxDb: -12, optimalDb: -17 },
      'Low Mids': { minDb: -26, maxDb: -16, optimalDb: -21 },
      Mids: { minDb: -24, maxDb: -14, optimalDb: -19 },
      'Upper Mids': { minDb: -26, maxDb: -14, optimalDb: -20 },
      Highs: { minDb: -28, maxDb: -14, optimalDb: -21 },
      Brilliance: { minDb: -30, maxDb: -16, optimalDb: -23 },
    },
  },

  // --- DEEP / ORGANIC HOUSE ---
  {
    id: 'deep-house',
    name: 'Deep House',
    targetCrestFactorRange: [7, 12],
    targetPlrRange: [8, 13],
    targetLufsRange: [-18, -12],
    spectralTargets: {
      'Sub Bass': { minDb: -22, maxDb: -12, optimalDb: -17 },
      'Low Bass': { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Low Mids': { minDb: -24, maxDb: -16, optimalDb: -20 },
      Mids: { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Upper Mids': { minDb: -22, maxDb: -14, optimalDb: -18 },
      Highs: { minDb: -26, maxDb: -16, optimalDb: -21 },
      Brilliance: { minDb: -30, maxDb: -18, optimalDb: -24 },
    },
  },
  {
    id: 'organic-house',
    name: 'Organic House / Downtempo',
    targetCrestFactorRange: [9, 16],
    targetPlrRange: [11, 18],
    targetLufsRange: [-20, -14],
    spectralTargets: {
      'Sub Bass': { minDb: -26, maxDb: -16, optimalDb: -21 },
      'Low Bass': { minDb: -22, maxDb: -14, optimalDb: -18 },
      'Low Mids': { minDb: -24, maxDb: -14, optimalDb: -19 },
      Mids: { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Upper Mids': { minDb: -22, maxDb: -12, optimalDb: -17 },
      Highs: { minDb: -26, maxDb: -14, optimalDb: -20 },
      Brilliance: { minDb: -28, maxDb: -16, optimalDb: -22 },
    },
  },

  // --- HOUSE VARIANTS ---
  {
    id: 'house',
    name: 'House',
    targetCrestFactorRange: [5, 10],
    targetPlrRange: [6, 10],
    targetLufsRange: [-16, -10],
    spectralTargets: {
      'Sub Bass': { minDb: -16, maxDb: -8, optimalDb: -12 },
      'Low Bass': { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Low Mids': { minDb: -24, maxDb: -16, optimalDb: -20 },
      Mids: { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Upper Mids': { minDb: -22, maxDb: -14, optimalDb: -18 },
      Highs: { minDb: -26, maxDb: -16, optimalDb: -21 },
      Brilliance: { minDb: -30, maxDb: -20, optimalDb: -25 },
    },
  },
  {
    id: 'classic-house',
    name: 'Classic House',
    targetCrestFactorRange: [6, 11],
    targetPlrRange: [7, 11],
    targetLufsRange: [-18, -12],
    spectralTargets: {
      'Sub Bass': { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Low Bass': { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Low Mids': { minDb: -24, maxDb: -16, optimalDb: -20 },
      Mids: { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Upper Mids': { minDb: -22, maxDb: -14, optimalDb: -18 },
      Highs: { minDb: -26, maxDb: -16, optimalDb: -21 },
      Brilliance: { minDb: -30, maxDb: -18, optimalDb: -24 },
    },
  },
  {
    id: 'tech-house',
    name: 'Tech House',
    targetCrestFactorRange: [5, 9],
    targetPlrRange: [6, 10],
    targetLufsRange: [-16, -10],
    spectralTargets: {
      'Sub Bass': { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Low Bass': { minDb: -16, maxDb: -8, optimalDb: -12 },
      'Low Mids': { minDb: -24, maxDb: -16, optimalDb: -20 },
      Mids: { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Upper Mids': { minDb: -22, maxDb: -14, optimalDb: -18 },
      Highs: { minDb: -26, maxDb: -16, optimalDb: -21 },
      Brilliance: { minDb: -30, maxDb: -18, optimalDb: -24 },
    },
  },
  {
    id: 'progressive-house',
    name: 'Progressive House',
    targetCrestFactorRange: [6, 10],
    targetPlrRange: [7, 11],
    targetLufsRange: [-16, -10],
    spectralTargets: {
      'Sub Bass': { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Low Bass': { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Low Mids': { minDb: -24, maxDb: -16, optimalDb: -20 },
      Mids: { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Upper Mids': { minDb: -20, maxDb: -12, optimalDb: -16 },
      Highs: { minDb: -24, maxDb: -14, optimalDb: -19 },
      Brilliance: { minDb: -28, maxDb: -16, optimalDb: -22 },
    },
  },
  {
    id: 'afro-house',
    name: 'Afro House / Tribal',
    targetCrestFactorRange: [7, 13],
    targetPlrRange: [8, 13],
    targetLufsRange: [-18, -12],
    spectralTargets: {
      'Sub Bass': { minDb: -22, maxDb: -12, optimalDb: -17 },
      'Low Bass': { minDb: -20, maxDb: -10, optimalDb: -15 },
      'Low Mids': { minDb: -24, maxDb: -14, optimalDb: -19 },
      Mids: { minDb: -20, maxDb: -10, optimalDb: -15 },
      'Upper Mids': { minDb: -22, maxDb: -12, optimalDb: -17 },
      Highs: { minDb: -26, maxDb: -14, optimalDb: -20 },
      Brilliance: { minDb: -30, maxDb: -16, optimalDb: -23 },
    },
  },

  // --- TECHNO VARIANTS ---
  {
    id: 'techno',
    name: 'Techno',
    targetCrestFactorRange: [4, 8],
    targetPlrRange: [5, 9],
    targetLufsRange: [-14, -8],
    spectralTargets: {
      'Sub Bass': { minDb: -14, maxDb: -6, optimalDb: -10 },
      'Low Bass': { minDb: -16, maxDb: -8, optimalDb: -12 },
      'Low Mids': { minDb: -28, maxDb: -18, optimalDb: -23 },
      Mids: { minDb: -24, maxDb: -16, optimalDb: -20 },
      'Upper Mids': { minDb: -22, maxDb: -14, optimalDb: -18 },
      Highs: { minDb: -26, maxDb: -16, optimalDb: -21 },
      Brilliance: { minDb: -30, maxDb: -20, optimalDb: -25 },
    },
  },
  {
    id: 'minimal-techno',
    name: 'Minimal Techno',
    targetCrestFactorRange: [7, 12],
    targetPlrRange: [8, 14],
    targetLufsRange: [-18, -12],
    spectralTargets: {
      'Sub Bass': { minDb: -22, maxDb: -14, optimalDb: -18 },
      'Low Bass': { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Low Mids': { minDb: -28, maxDb: -18, optimalDb: -23 },
      Mids: { minDb: -24, maxDb: -16, optimalDb: -20 },
      'Upper Mids': { minDb: -24, maxDb: -14, optimalDb: -19 },
      Highs: { minDb: -28, maxDb: -16, optimalDb: -22 },
      Brilliance: { minDb: -32, maxDb: -18, optimalDb: -25 },
    },
  },
  {
    id: 'melodic-techno',
    name: 'Melodic Techno',
    targetCrestFactorRange: [8, 14],
    targetPlrRange: [9, 15],
    targetLufsRange: [-16, -10],
    spectralTargets: {
      'Sub Bass': { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Low Bass': { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Low Mids': { minDb: -26, maxDb: -16, optimalDb: -21 },
      Mids: { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Upper Mids': { minDb: -22, maxDb: -12, optimalDb: -17 },
      Highs: { minDb: -26, maxDb: -14, optimalDb: -20 },
      Brilliance: { minDb: -30, maxDb: -16, optimalDb: -23 },
    },
  },
  {
    id: 'driving-techno',
    name: 'Driving / Peak Time Techno',
    targetCrestFactorRange: [4, 8],
    targetPlrRange: [5, 9],
    targetLufsRange: [-14, -8],
    spectralTargets: {
      'Sub Bass': { minDb: -16, maxDb: -8, optimalDb: -12 },
      'Low Bass': { minDb: -14, maxDb: -6, optimalDb: -10 },
      'Low Mids': { minDb: -28, maxDb: -18, optimalDb: -23 },
      Mids: { minDb: -24, maxDb: -14, optimalDb: -19 },
      'Upper Mids': { minDb: -24, maxDb: -14, optimalDb: -19 },
      Highs: { minDb: -28, maxDb: -16, optimalDb: -22 },
      Brilliance: { minDb: -32, maxDb: -18, optimalDb: -25 },
    },
  },
  {
    id: 'industrial-techno',
    name: 'Industrial Techno',
    targetCrestFactorRange: [3, 7],
    targetPlrRange: [4, 8],
    targetLufsRange: [-14, -8],
    spectralTargets: {
      'Sub Bass': { minDb: -14, maxDb: -6, optimalDb: -10 },
      'Low Bass': { minDb: -12, maxDb: -4, optimalDb: -8 },
      'Low Mids': { minDb: -24, maxDb: -14, optimalDb: -19 },
      Mids: { minDb: -22, maxDb: -12, optimalDb: -17 },
      'Upper Mids': { minDb: -22, maxDb: -12, optimalDb: -17 },
      Highs: { minDb: -26, maxDb: -14, optimalDb: -20 },
      Brilliance: { minDb: -30, maxDb: -16, optimalDb: -23 },
    },
  },
  {
    id: 'hard-techno',
    name: 'Hard Techno / Schranz',
    targetCrestFactorRange: [3, 7],
    targetPlrRange: [4, 8],
    targetLufsRange: [-12, -7],
    spectralTargets: {
      'Sub Bass': { minDb: -12, maxDb: -4, optimalDb: -8 },
      'Low Bass': { minDb: -10, maxDb: -2, optimalDb: -6 },
      'Low Mids': { minDb: -22, maxDb: -12, optimalDb: -17 },
      Mids: { minDb: -20, maxDb: -10, optimalDb: -15 },
      'Upper Mids': { minDb: -20, maxDb: -10, optimalDb: -15 },
      Highs: { minDb: -26, maxDb: -14, optimalDb: -20 },
      Brilliance: { minDb: -30, maxDb: -16, optimalDb: -23 },
    },
  },
  {
    id: 'acid-techno',
    name: 'Acid Techno / 303',
    targetCrestFactorRange: [6, 11],
    targetPlrRange: [7, 12],
    targetLufsRange: [-16, -10],
    spectralTargets: {
      'Sub Bass': { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Low Bass': { minDb: -16, maxDb: -8, optimalDb: -12 },
      'Low Mids': { minDb: -26, maxDb: -16, optimalDb: -21 },
      Mids: { minDb: -22, maxDb: -12, optimalDb: -17 },
      'Upper Mids': { minDb: -24, maxDb: -14, optimalDb: -19 },
      Highs: { minDb: -28, maxDb: -16, optimalDb: -22 },
      Brilliance: { minDb: -32, maxDb: -18, optimalDb: -25 },
    },
  },
  {
    id: 'detroit-techno',
    name: 'Detroit Techno',
    targetCrestFactorRange: [7, 13],
    targetPlrRange: [8, 14],
    targetLufsRange: [-18, -12],
    spectralTargets: {
      'Sub Bass': { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Low Bass': { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Low Mids': { minDb: -24, maxDb: -14, optimalDb: -19 },
      Mids: { minDb: -20, maxDb: -10, optimalDb: -15 },
      'Upper Mids': { minDb: -22, maxDb: -12, optimalDb: -17 },
      Highs: { minDb: -26, maxDb: -14, optimalDb: -20 },
      Brilliance: { minDb: -30, maxDb: -16, optimalDb: -23 },
    },
  },

  // --- TRANCE & PROGRESSIVE ---
  {
    id: 'trance',
    name: 'Trance',
    targetCrestFactorRange: [6, 11],
    targetPlrRange: [7, 11],
    targetLufsRange: [-14, -9],
    spectralTargets: {
      'Sub Bass': { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Low Bass': { minDb: -16, maxDb: -8, optimalDb: -12 },
      'Low Mids': { minDb: -26, maxDb: -16, optimalDb: -21 },
      Mids: { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Upper Mids': { minDb: -20, maxDb: -10, optimalDb: -15 },
      Highs: { minDb: -24, maxDb: -12, optimalDb: -18 },
      Brilliance: { minDb: -26, maxDb: -14, optimalDb: -20 },
    },
  },
  {
    id: 'psytrance',
    name: 'Psytrance',
    targetCrestFactorRange: [5, 10],
    targetPlrRange: [6, 10],
    targetLufsRange: [-14, -8],
    spectralTargets: {
      'Sub Bass': { minDb: -16, maxDb: -8, optimalDb: -12 },
      'Low Bass': { minDb: -14, maxDb: -6, optimalDb: -10 },
      'Low Mids': { minDb: -26, maxDb: -14, optimalDb: -20 },
      Mids: { minDb: -20, maxDb: -10, optimalDb: -15 },
      'Upper Mids': { minDb: -22, maxDb: -10, optimalDb: -16 },
      Highs: { minDb: -24, maxDb: -12, optimalDb: -18 },
      Brilliance: { minDb: -26, maxDb: -14, optimalDb: -20 },
    },
  },

  // --- BASS MUSIC ---
  {
    id: 'dubstep',
    name: 'Dubstep',
    targetCrestFactorRange: [7, 13],
    targetPlrRange: [8, 14],
    targetLufsRange: [-14, -8],
    spectralTargets: {
      'Sub Bass': { minDb: -16, maxDb: -6, optimalDb: -11 },
      'Low Bass': { minDb: -14, maxDb: -6, optimalDb: -10 },
      'Low Mids': { minDb: -24, maxDb: -14, optimalDb: -19 },
      Mids: { minDb: -20, maxDb: -10, optimalDb: -15 },
      'Upper Mids': { minDb: -22, maxDb: -12, optimalDb: -17 },
      Highs: { minDb: -26, maxDb: -14, optimalDb: -20 },
      Brilliance: { minDb: -30, maxDb: -16, optimalDb: -23 },
    },
  },
  {
    id: 'bass-house',
    name: 'Bass House',
    targetCrestFactorRange: [5, 10],
    targetPlrRange: [6, 10],
    targetLufsRange: [-14, -9],
    spectralTargets: {
      'Sub Bass': { minDb: -16, maxDb: -8, optimalDb: -12 },
      'Low Bass': { minDb: -14, maxDb: -6, optimalDb: -10 },
      'Low Mids': { minDb: -26, maxDb: -16, optimalDb: -21 },
      Mids: { minDb: -20, maxDb: -10, optimalDb: -15 },
      'Upper Mids': { minDb: -22, maxDb: -12, optimalDb: -17 },
      Highs: { minDb: -26, maxDb: -14, optimalDb: -20 },
      Brilliance: { minDb: -30, maxDb: -16, optimalDb: -23 },
    },
  },

  // --- D&B & BREAKS ---
  {
    id: 'dnb',
    name: 'Drum & Bass / Jungle',
    targetCrestFactorRange: [6, 12],
    targetPlrRange: [7, 11],
    targetLufsRange: [-14, -8],
    spectralTargets: {
      'Sub Bass': { minDb: -14, maxDb: -6, optimalDb: -10 },
      'Low Bass': { minDb: -16, maxDb: -8, optimalDb: -12 },
      'Low Mids': { minDb: -26, maxDb: -16, optimalDb: -21 },
      Mids: { minDb: -22, maxDb: -14, optimalDb: -18 },
      'Upper Mids': { minDb: -20, maxDb: -12, optimalDb: -16 },
      Highs: { minDb: -24, maxDb: -14, optimalDb: -19 },
      Brilliance: { minDb: -28, maxDb: -18, optimalDb: -23 },
    },
  },
  {
    id: 'drum-bass',
    name: 'Drum & Bass',
    targetCrestFactorRange: [6, 12],
    targetPlrRange: [7, 12],
    targetLufsRange: [-14, -8],
    spectralTargets: {
      'Sub Bass': { minDb: -16, maxDb: -8, optimalDb: -12 },
      'Low Bass': { minDb: -14, maxDb: -6, optimalDb: -10 },
      'Low Mids': { minDb: -26, maxDb: -16, optimalDb: -21 },
      Mids: { minDb: -22, maxDb: -12, optimalDb: -17 },
      'Upper Mids': { minDb: -22, maxDb: -12, optimalDb: -17 },
      Highs: { minDb: -26, maxDb: -14, optimalDb: -20 },
      Brilliance: { minDb: -30, maxDb: -18, optimalDb: -24 },
    },
  },
  {
    id: 'neurofunk',
    name: 'Neurofunk',
    targetCrestFactorRange: [5, 10],
    targetPlrRange: [6, 10],
    targetLufsRange: [-14, -8],
    spectralTargets: {
      'Sub Bass': { minDb: -14, maxDb: -6, optimalDb: -10 },
      'Low Bass': { minDb: -12, maxDb: -4, optimalDb: -8 },
      'Low Mids': { minDb: -26, maxDb: -14, optimalDb: -20 },
      Mids: { minDb: -22, maxDb: -10, optimalDb: -16 },
      'Upper Mids': { minDb: -22, maxDb: -10, optimalDb: -16 },
      Highs: { minDb: -26, maxDb: -12, optimalDb: -19 },
      Brilliance: { minDb: -30, maxDb: -16, optimalDb: -23 },
    },
  },
  {
    id: 'breaks',
    name: 'Breaks / Breakbeat',
    targetCrestFactorRange: [7, 13],
    targetPlrRange: [8, 14],
    targetLufsRange: [-16, -10],
    spectralTargets: {
      'Sub Bass': { minDb: -20, maxDb: -12, optimalDb: -16 },
      'Low Bass': { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Low Mids': { minDb: -26, maxDb: -16, optimalDb: -21 },
      Mids: { minDb: -20, maxDb: -10, optimalDb: -15 },
      'Upper Mids': { minDb: -22, maxDb: -12, optimalDb: -17 },
      Highs: { minDb: -26, maxDb: -14, optimalDb: -20 },
      Brilliance: { minDb: -30, maxDb: -18, optimalDb: -24 },
    },
  },

  // --- UK BASS / GARAGE ---
  {
    id: 'garage',
    name: 'Garage / UK Bass',
    targetCrestFactorRange: [6, 11],
    targetPlrRange: [6, 10],
    targetLufsRange: [-16, -10],
    spectralTargets: {
      'Sub Bass': { minDb: -14, maxDb: -6, optimalDb: -10 },
      'Low Bass': { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Low Mids': { minDb: -24, maxDb: -16, optimalDb: -20 },
      Mids: { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Upper Mids': { minDb: -22, maxDb: -14, optimalDb: -18 },
      Highs: { minDb: -26, maxDb: -16, optimalDb: -21 },
      Brilliance: { minDb: -30, maxDb: -20, optimalDb: -25 },
    },
  },
  {
    id: 'uk-garage',
    name: 'UK Garage',
    targetCrestFactorRange: [6, 11],
    targetPlrRange: [7, 11],
    targetLufsRange: [-16, -10],
    spectralTargets: {
      'Sub Bass': { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Low Bass': { minDb: -16, maxDb: -8, optimalDb: -12 },
      'Low Mids': { minDb: -26, maxDb: -16, optimalDb: -21 },
      Mids: { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Upper Mids': { minDb: -22, maxDb: -12, optimalDb: -17 },
      Highs: { minDb: -26, maxDb: -14, optimalDb: -20 },
      Brilliance: { minDb: -30, maxDb: -18, optimalDb: -24 },
    },
  },
  {
    id: 'bassline',
    name: 'Bassline / Niche',
    targetCrestFactorRange: [5, 10],
    targetPlrRange: [6, 10],
    targetLufsRange: [-14, -9],
    spectralTargets: {
      'Sub Bass': { minDb: -16, maxDb: -8, optimalDb: -12 },
      'Low Bass': { minDb: -14, maxDb: -6, optimalDb: -10 },
      'Low Mids': { minDb: -26, maxDb: -16, optimalDb: -21 },
      Mids: { minDb: -18, maxDb: -10, optimalDb: -14 },
      'Upper Mids': { minDb: -22, maxDb: -12, optimalDb: -17 },
      Highs: { minDb: -26, maxDb: -14, optimalDb: -20 },
      Brilliance: { minDb: -30, maxDb: -18, optimalDb: -24 },
    },
  },
];

/**
 * Returns a default profile if none requested.
 */
export function getProfile(id: string): GenreProfile {
  const profile = GENRE_PROFILES.find((p) => p.id === id);
  return profile || GENRE_PROFILES[0]; // Default to EDM
}

/**
 * Get profile for enhanced genre (includes all 35+ profiles).
 */
export function getEnhancedProfile(id: string): GenreProfile {
  const profile = GENRE_PROFILES.find((p) => p.id === id);
  return profile || getProfile('driving-techno');
}

/**
 * Map legacy genre IDs to new enhanced subgenres.
 */
export function mapLegacyToEnhanced(legacyId: string): string[] {
  const mapping: Record<string, string[]> = {
    edm: ['progressive-house', 'classic-house'],
    techno: ['driving-techno', 'melodic-techno', 'minimal-techno'],
    house: ['classic-house', 'deep-house', 'tech-house'],
    ambient: ['ambient-drone', 'ambient-techno', 'dub-techno'],
    dnb: ['drum-bass', 'neurofunk'],
    garage: ['uk-garage', 'bassline'],
  };
  return mapping[legacyId] || [legacyId];
}

/**
 * Get all available genre IDs.
 */
export function getAllGenreIds(): string[] {
  return GENRE_PROFILES.map((p) => p.id);
}

/**
 * Get genre display name.
 */
export function getGenreName(id: string): string {
  const profile = GENRE_PROFILES.find((p) => p.id === id);
  return profile?.name || id;
}

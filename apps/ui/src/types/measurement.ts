export interface MelodyNote {
  midi: number;
  onset: number;
  duration: number;
}

export interface MelodyPitchRange {
  min: number | null;
  max: number | null;
}

export interface MelodyDetail {
  noteCount: number;
  notes: MelodyNote[];
  dominantNotes: number[];
  pitchRange: MelodyPitchRange;
  pitchConfidence: number;
  midiFile: string | null;
  sourceSeparated: boolean;
  vibratoPresent: boolean;
  vibratoExtent: number;
  vibratoRate: number;
  vibratoConfidence: number;
}

export interface TranscriptionNote {
  pitchMidi: number;
  pitchName: string;
  onsetSeconds: number;
  durationSeconds: number;
  confidence: number;
  stemSource: "bass" | "other" | "full_mix";
}

export interface TranscriptionDetail {
  transcriptionMethod: string;
  noteCount: number;
  averageConfidence: number;
  stemSeparationUsed: boolean;
  fullMixFallback: boolean;
  stemsTranscribed: string[];
  /**
   * Mean confidence per stem source, computed over the post-dedup, post-cap notes.
   * Empty `{}` when `fullMixFallback` is true; otherwise contains one entry per
   * stem with at least one surviving note (e.g. `{"bass": 0.85, "other": 0.32}`).
   * Optional because legacy snapshots and the empty-notes path may omit it.
   */
  perStemAverageConfidence?: Record<string, number>;
  dominantPitches: Array<{
    pitchMidi: number;
    pitchName: string;
    count: number;
  }>;
  pitchRange: {
    minMidi: number | null;
    maxMidi: number | null;
    minName: string | null;
    maxName: string | null;
  };
  notes: TranscriptionNote[];
}

/**
 * Optional MT3 (Magenta Multi-Task Multitrack) polyphonic-transcription
 * output. Emitted only when the backend env var `ASA_ENABLE_MT3=1` is set
 * AND the MT3 extra is installed (see apps/backend/requirements-mt3.txt and
 * the apps/backend/mt3_transcription.py module docstring).
 *
 * Purely additive to Phase 1 — does NOT override Essentia chord/key/beat/
 * melody outputs (PURPOSE.md invariant #1). Rendered by `Mt3TranscriptionPanel`
 * (mounted from `AnalysisResults`) when the MT3 stage completed with at least
 * one track; the camelCase field names mirror the backend JSON verbatim
 * (CLAUDE.md tripwire #3 — no conversion layer between camelCase JSON and TS).
 */
/**
 * One per-instrument track in the MT3 stage result.
 *
 * NOTE: this is the *stored* shape served by `GET /api/analysis-runs/{id}`,
 * not the raw subprocess emission. The MT3 subprocess emits a `midiB64`
 * (inline base64) field on each track; the staged-runtime executor in
 * `apps/backend/server.py::_execute_mt3_attempt` persists those bytes as
 * a per-stem artifact and replaces `midiB64` with `midiArtifactId`. So
 * the Python `Mt3Track` dataclass (in `apps/backend/mt3_transcription.py`)
 * has `midi_b64`; this TS interface has `midiArtifactId`. They describe
 * the same per-stem concept at different layers of the pipeline.
 */
export interface Mt3Track {
  /**
   * Stem the MIDI was extracted from (Demucs canonical names: "bass",
   * "other", "vocals", "drums") or "full_mix" when no stems were provided.
   */
  instrument: string;
  /**
   * Artifact ID for the MIDI bytes. Decoupled from the snapshot itself
   * because a multi-track MT3 result is 0.5-3MB of base64 per track and
   * inline blobs would balloon every snapshot poll. Fetch the actual MIDI
   * via `GET /api/analysis-runs/{run_id}/artifacts/{midiArtifactId}`.
   * Null if the track was emitted with no MIDI body (defensive — should
   * not happen in practice; the backend writes empty-bytes MIDI when a
   * stem produced no notes).
   */
  midiArtifactId: string | null;
  midiSizeBytes: number;
  noteCount: number;
  /** `[minMidi, maxMidi]` over all notes in this track; `[0, 0]` when empty. */
  pitchRange: [number, number];
}

export interface Mt3Transcription {
  /**
   * Pinned identifier of the MT3 module + checkpoint that produced the notes.
   * Format: `"mt3-py-<module-version>+<checkpoint-id>"` — Phase 2 reads this
   * verbatim to know what to attribute the notes to.
   */
  version: string;
  stemsUsed: string[];
  tracks: Mt3Track[];
}

/**
 * Top-level namespace for *additive* transcription backends that produce
 * full MIDI rather than the lighter per-note schema in `TranscriptionDetail`.
 * Reserved for future translation backends; today only `mt3` is wired.
 * The whole namespace is *absent* (not null) when no opt-in backend ran.
 */
export interface TranscriptionNamespace {
  mt3?: Mt3Transcription;
}

export interface DanceabilityResult {
  danceability: number;
  dfa: number;
}

export interface LufsCurvePoint {
  t: number;
  lufs: number;
}

export interface LufsCurve {
  shortTerm: LufsCurvePoint[];
  momentary: LufsCurvePoint[];
}

export interface SpectralBalanceTimeSeriesPoint {
  t: number;
  subBass: number;
  lowBass: number;
  lowMids: number;
  mids: number;
  upperMids: number;
  highs: number;
  brilliance: number;
}

/**
 * Per-Demucs-stem analytical surface from Phase 1.B's stem-first overlay.
 *
 * Populated only when stem separation was requested AND succeeded
 * (``--separate``/``run_separation`` path on the backend). When stems are
 * unavailable this is ``null`` and the top-level full-mix scalars are the
 * only source of truth. The subset of analyzers run per-stem mirrors the
 * full-mix versions — spectralBalance, spectralDetail, loudness, stereo,
 * dynamics — so Phase 2 can cite e.g. ``stemAnalysis.bass.spectralBalance.subBass``
 * for a bass-targeted EQ move instead of conflating every element under one
 * full-mix scalar. Song-level fields (BPM, key, time signature, structure
 * novelty) are intentionally absent here.
 */
export interface StemAnalysisEntry {
  spectralBalance?: {
    subBass: number;
    lowBass: number;
    lowMids: number;
    mids: number;
    upperMids: number;
    highs: number;
    brilliance: number;
  } | null;
  spectralBalanceTimeSeries?: SpectralBalanceTimeSeriesPoint[] | null;
  spectralDetail?: SpectralDetail | null;
  lufsIntegrated?: number | null;
  lufsRange?: number | null;
  lufsMomentaryMax?: number | null;
  lufsShortTermMax?: number | null;
  lufsCurve?: LufsCurve | null;
  stereoDetail?: StereoDetail | null;
  truePeak?: number | null;
  crestFactor?: number | null;
  dynamicSpread?: number | null;
  dynamicCharacter?: DynamicCharacter | null;
  /**
   * Phase 1.D #5 — per-stem reverb estimation. The analyzer runs the
   * same RT60-slope-fit pipeline on each Demucs stem; the drums stem is
   * usually the most defensible signal (real room reverb) while bass /
   * other / vocals may report long RT60s that actually reflect sustained
   * tonal decay rather than reverb. `measured: false` means the analyzer
   * didn't find enough transients to fit a slope on this stem — caller
   * should treat the result as a fallback.
   */
  reverbDetail?: ReverbDetail | null;
}

export interface StemAnalysis {
  drums?: StemAnalysisEntry;
  bass?: StemAnalysisEntry;
  other?: StemAnalysisEntry;
  vocals?: StemAnalysisEntry;
}

export interface TransientDensityBandEntry {
  onsetRatePerSecond: number;
  meanOnsetStrength: number;
  peakOnsetStrength: number;
  eventCount: number;
}

export interface TransientDensityDetail {
  subBass: TransientDensityBandEntry;
  lowBass: TransientDensityBandEntry;
  lowMids: TransientDensityBandEntry;
  mids: TransientDensityBandEntry;
  upperMids: TransientDensityBandEntry;
  highs: TransientDensityBandEntry;
  brilliance: TransientDensityBandEntry;
}

/**
 * Phase 1.C #4 — band-limited drum character (shared shape for snare and
 * hi-hat). Hit count, attack sharpness, body-vs-snap energy ratio, mean
 * spectral centroid in band, decay character. Phase 2 cites these for
 * snare- / hi-hat-bus EQ + saturation + dynamics moves.
 */
export interface BandDrumDetail {
  hitCount: number;
  hitsPerSecond: number;
  meanAttackSharpness: number;
  meanBodyEnergyRatio: number | null;
  meanSnapEnergyRatio: number | null;
  meanCentroidHz: number | null;
  meanDecayFrames: number;
  meanDecaySeconds: number;
  bandHz: [number, number];
}

/**
 * Phase 1.C #5 — saturation / clipping / over-compression telltales. Hint-
 * only; Phase 2 should hedge per the citation contract's low-confidence
 * rules until the audit bench confirms the signal.
 */
export interface SaturationDetail {
  clippedSampleCount: number;
  clippedSamplePercent: number;
  nearClippedSampleCount: number;
  nearClippedSamplePercent: number;
  peakRatio95to50: number | null;
  rmsToPeakRatioDb: number | null;
  saturationLikely: boolean;
}

export interface StereoCorrelationCurvePoint {
  t: number;
  full: number | null;
  sub: number | null;
}

/**
 * Phase 1.C #2 — per-frequency-band L/R Pearson correlation, keyed by the
 * same 7 bands as ``spectralBalance``. ``null`` per band when that band has
 * no usable energy (e.g. brilliance on a dark master). Phase 2 cites these
 * to recommend Utility-tool width per band ("the bass is mono at 0.98 but
 * the mids are wide at 0.45 — add Utility on the synth bus only").
 */
export interface StereoBandCorrelations {
  subBass: number | null;
  lowBass: number | null;
  lowMids: number | null;
  mids: number | null;
  upperMids: number | null;
  highs: number | null;
  brilliance: number | null;
}

export interface StereoDetail {
  stereoWidth: number | null;
  stereoCorrelation: number | null;
  subBassCorrelation?: number | null;
  subBassMono?: boolean | null;
  /**
   * 1-second windowed L/R correlation, full-band and sub-band side-by-side.
   * Surfaces stereo automation (utility-tool width sweeps, mono-collapsing
   * the drop) that the global scalars conflate into one number.
   */
  correlationCurve?: StereoCorrelationCurvePoint[] | null;
  bandCorrelations?: StereoBandCorrelations | null;
}

export interface SpectralDetail {
  spectralCentroidMean?: number | null;
  spectralRolloffMean?: number | null;
  spectralBandwidthMean?: number | null;
  spectralFlatnessMean?: number | null;
  mfcc?: number[] | null;
  chroma?: number[] | null;
  barkBands?: number[] | null;
  erbBands?: number[] | null;
  spectralContrast?: number[] | null;
  spectralValley?: number[] | null;
}

export interface PhraseGrid {
  phrases4Bar: number[];
  phrases8Bar: number[];
  phrases16Bar: number[];
  totalBars: number;
  totalPhrases8Bar: number;
}

export interface TempoCurvePoint {
  t: number;
  bpm: number;
}

export type DownbeatSource = 'kick_accent' | 'stride';

export interface RhythmDetail {
  onsetRate: number;
  beatGrid: number[];
  downbeats: number[];
  beatPositions: number[];
  /**
   * How the bar-1 phase was resolved: 'kick_accent' (kick-heaviest beat
   * position within the detected meter) or 'stride' (legacy 4/4 fallback when
   * per-beat low-band data is unavailable).
   */
  downbeatSource?: DownbeatSource;
  /**
   * How distinctly the chosen bar-1 position dominates the other beat positions
   * in kick energy. Collapses toward 0 for four-on-the-floor. Low values are
   * honest hedging — soften bar-aligned recommendations accordingly.
   */
  downbeatConfidence?: number | null;
  grooveAmount: number;
  tempoStability?: number | null;
  phraseGrid?: PhraseGrid | null;
  /**
   * Instantaneous-BPM curve smoothed with a 4-beat rolling median and
   * downsampled to ~200 points. Surfaces deliberate ritardando/accelerando
   * and DJ-tool transitions that the single mean BPM scalar conflates away.
   */
  tempoCurve?: TempoCurvePoint[] | null;
}

export interface GrooveDetail {
  kickSwing: number;
  hihatSwing: number;
  kickAccent: number[];
  hihatAccent: number[];
  /** Phase 1.C #3: per-drum-group swing across kick (20-200 Hz), snare (200-4000 Hz), and hi-hat (4000-20000 Hz) beat-loudness bands. Same tanh-normalized scale as kickSwing / hihatSwing. */
  perDrumSwing?: {
    kick: number;
    snare: number;
    hihat: number;
  } | null;
}

export interface SidechainDetail {
  pumpingStrength: number;
  pumpingRegularity: number;
  /** `"quarter" | "eighth" | "sixteenth" | "thirty_second" | null` — added thirty_second in Phase 1.C #6. */
  pumpingRate: string | null;
  pumpingConfidence: number;
  /** Median per-bar RMS envelope at 16th-note (16 samples) resolution. */
  envelopeShape?: number[] | null;
  /** Phase 1.C #6: Median per-bar RMS envelope at 32nd-note (32 samples) resolution. */
  envelopeShape32?: number[] | null;
}

export interface EffectsDetail {
  gatingDetected?: boolean | null;
  gatingRate?: 'quarter' | '8th' | '16th' | null;
  gatingRegularity?: number | null;
  gatingEventCount?: number | null;
}

export interface SynthesisCharacter {
  inharmonicity?: number | null;
  oddToEvenRatio?: number | null;
  analogLike?: boolean | null;
}

export interface StructureData {
  segments?: unknown[] | null;
  segmentCount?: number | null;
  sections?: number | null;
}

export interface ArrangementDetail {
  noveltyCurve?: number[] | null;
  noveltyPeaks?: number[] | null;
  noveltyMean?: number | null;
  noveltyStdDev?: number | null;
  sectionCount?: number | null;
}

export interface SegmentLoudnessEntry {
  segmentIndex?: number;
  start?: number;
  end?: number;
  lufs?: number | null;
  lra?: number | null;
  value?: number | null;
}

export interface SegmentSpectralEntry {
  segmentIndex: number;
  barkBands?: number[] | null;
  spectralCentroid?: number | null;
  spectralRolloff?: number | null;
  stereoWidth?: number | null;
  stereoCorrelation?: number | null;
}

export interface SegmentStereoEntry {
  segmentIndex: number;
  stereoWidth?: number | null;
  stereoCorrelation?: number | null;
}

export interface SegmentKeyEntry {
  segmentIndex: number;
  key: string | null;
  keyConfidence?: number | null;
}

/**
 * Phase 1.D #2 — temporal chord-progression timeline entry. Each entry
 * represents a stable chord region decoded by a 25-state (12 major + 12 minor
 * + "N" no-chord) Viterbi over librosa chroma_cqt; regions shorter than
 * ~250 ms are dropped as noise. `label` is short-form ("Cm", "Eb", "N");
 * `labelLong` is human-readable ("C minor", "Eb major", "N") and is optional
 * for back-compat with pre-migration stored payloads.
 */
export interface ChordTimelineEntry {
  startSec: number;
  endSec: number;
  label: string;
  labelLong?: string;
  confidence: number;
}

export interface ChordDetail {
  chordSequence?: string[] | null;
  chordStrength?: number | null;
  progression?: string[] | null;
  dominantChords?: string[] | null;
  /** Phase 1.D #2: chord segments with start/end times + per-segment confidence. */
  chordTimeline?: ChordTimelineEntry[] | null;
  /** Phase 1.D #2: count of unique chord-to-chord transitions in the Viterbi timeline. */
  chordChangeCount?: number | null;
  /** Phase 1.D #2: identifier of the engine that produced chordTimeline. Currently always "librosa_viterbi". */
  chordTimelineSource?: string | null;
  /** Phase 1.D #2: true when Viterbi's dominant matches Essentia's dominantChords[0] after enharmonic normalization. */
  chordTimelineAgreement?: boolean | null;
}

export interface PerceptualDetail {
  sharpness: number;
  roughness: number;
}

export interface EssentiaFeatures {
  zeroCrossingRate?: number | null;
  hfc?: number | null;
  spectralComplexity?: number | null;
  dissonance?: number | null;
}

export interface DynamicCharacter {
  dynamicComplexity: number;
  loudnessDb: number;
  loudnessVariation?: number | null;
  spectralFlatness: number;
  logAttackTime: number;
  attackTimeStdDev: number;
}

export interface TextureCharacter {
  textureScore: number;
  lowBandFlatness: number;
  midBandFlatness: number;
  highBandFlatness: number;
  inharmonicity?: number | null;
}

export interface BeatsLoudness {
  kickDominantRatio: number;
  midDominantRatio: number;
  highDominantRatio: number;
  patternBeatsPerBar: number;
  lowBandAccentPattern: number[];
  midBandAccentPattern: number[];
  highBandAccentPattern: number[];
  overallAccentPattern: number[];
  accentPattern: number[];
  meanBeatLoudness: number;
  beatLoudnessVariation: number;
  beatCount: number;
}

export interface RhythmTimelineWindow {
  bars: number;
  startBar: number;
  endBar: number;
  lowBandSteps: number[];
  midBandSteps: number[];
  highBandSteps: number[];
  overallSteps: number[];
}

export interface RhythmTimeline {
  beatsPerBar: number;
  stepsPerBeat: number;
  availableBars: number;
  selectionMethod: "representative_dsp_window";
  windows: RhythmTimelineWindow[];
}

export interface PitchStemResult {
  medianPitchHz: number | null;
  pitchRangeLowHz: number | null;
  pitchRangeHighHz: number | null;
  meanPeriodicity: number;
  voicedFramePercent: number;
  hopLength: number;
  sampleRate: number;
  model: string;
}

export interface PitchDetail {
  method: string;
  stems: Record<string, PitchStemResult>;
}

export interface AcidDetail {
  isAcid: boolean;
  confidence: number;
  resonanceLevel: number;
  centroidOscillationHz: number;
  bassRhythmDensity: number;
}

export interface ReverbDetail {
  rt60: number | null;
  isWet: boolean;
  tailEnergyRatio: number | null;
  measured: boolean;
  /**
   * Phase 1.D #5: RT60 estimated per octave band.
   * `low` ≈ 20-250 Hz, `lowMids` ≈ 250-2000 Hz,
   * `highMids` ≈ 2000-8000 Hz, `highs` ≈ 8000-16000 Hz.
   */
  perBandRt60?: {
    low?: number;
    lowMids?: number;
    highMids?: number;
    highs?: number;
  } | null;
  /** Phase 1.D #5: median pre-delay in milliseconds (time from direct peak to first envelope minimum). */
  preDelayMs?: number | null;
}

export interface VocalDetail {
  hasVocals: boolean;
  confidence: number;
  vocalEnergyRatio: number;
  formantStrength: number;
  mfccLikelihood: number;
  /**
   * Demucs-ghost-stem proxy #1: vocals-stem RMS / full-mix RMS. Null when no
   * vocals stem was used (full-mix path). Below ~0.05 indicates the vocals
   * stem is leakage from a track with no real vocal content; the analyzer
   * scales `confidence` down linearly when this is the case.
   */
  stemEnergyRatio?: number | null;
  /**
   * Demucs-ghost-stem proxy #2: Pearson correlation between the vocals stem
   * and the "other" stem at a 200 Hz envelope rate. High correlation (>0.3)
   * means Demucs is splitting one source (typically a melodic lead) into two
   * stems — the "vocals" stem is misclassified content, not a genuine voice.
   * The analyzer scales `confidence` down proportionally above 0.3.
   * Null when either stem is unavailable or too short to compute.
   */
  stemOtherCorrelation?: number | null;
}

export interface SupersawDetail {
  isSupersaw: boolean;
  confidence: number;
  voiceCount: number;
  avgDetuneCents: number;
  spectralComplexity: number;
}

export interface BassDetail {
  averageDecayMs: number;
  type: "punchy" | "medium" | "rolling" | "sustained";
  transientRatio: number;
  fundamentalHz: number | null;
  transientCount: number;
  swingPercent: number;
  grooveType: string;
}

export interface KickDetail {
  isDistorted: boolean;
  thd: number;
  harmonicRatio: number;
  fundamentalHz: number | null;
  kickCount: number;
}

export interface GenreDetail {
  genre: string;
  confidence: number;
  secondaryGenre: string | null;
  genreFamily: "house" | "techno" | "dnb" | "ambient" | "trance" | "dubstep" | "breaks" | "other";
  topScores: Array<{ genre: string; score: number }>;
}

export interface Phase1Result {
  bpm: number;
  bpmConfidence: number;
  bpmPercival?: number | null;
  bpmAgreement?: boolean | null;
  bpmDoubletime?: boolean | null;
  bpmSource?: string | null;
  bpmRawOriginal?: number | null;
  key: string | null;
  keyConfidence: number;
  keyProfile?: string | null;
  tuningFrequency?: number | null;
  tuningCents?: number | null;
  timeSignature: string;
  timeSignatureSource?: string | null;
  timeSignatureConfidence?: number | null;
  durationSeconds: number;
  sampleRate?: number | null;
  lufsIntegrated: number;
  lufsRange?: number | null;
  lufsMomentaryMax?: number | null;
  lufsShortTermMax?: number | null;
  truePeak: number;
  plr?: number | null;
  crestFactor?: number | null;
  dynamicSpread?: number | null;
  dynamicCharacter?: DynamicCharacter | null;
  textureCharacter?: TextureCharacter | null;
  /**
   * Per-frame EBU R128 momentary (400 ms window) and short-term (3 s window)
   * loudness, downsampled to ~200 points each. Phase 2 cites
   * lufsCurve.shortTerm to explain breakdown vs drop loudness contrast.
   * Null when LUFS extraction failed.
   */
  lufsCurve?: LufsCurve | null;
  stereoWidth: number;
  stereoCorrelation: number;
  stereoDetail?: StereoDetail | null;
  monoCompatible?: boolean | null;
  spectralBalance: {
    subBass: number;
    lowBass: number;
    lowMids: number;
    mids: number;
    upperMids: number;
    highs: number;
    brilliance: number;
  };
  /**
   * Sibling time-series partner for spectralBalance. Each row carries all
   * seven bands at a given timestamp. Downsampled to ~200 rows on a 2-min
   * track so Phase 2 can cite section-relative spectral motion ("the
   * high-end opens up at 1:23") instead of static averages alone.
   * Sibling rather than nested because spectralBalance's exact 7-key shape
   * is asserted by backend tests.
   */
  spectralBalanceTimeSeries?: SpectralBalanceTimeSeriesPoint[] | null;
  spectralDetail?: SpectralDetail | null;
  /**
   * Phase 1.B per-stem analytical surface (Demucs-separated). Null when
   * separation wasn't requested or failed. See {@link StemAnalysis}.
   */
  stemAnalysis?: StemAnalysis | null;
  /**
   * Phase 1.C #1 — per-frequency-band onset density across the 7
   * spectralBalance bands. Each entry carries rate (events/sec), mean
   * onset strength, peak, and event count. Phase 2 cites e.g.
   * ``transientDensityDetail.highs.onsetRatePerSecond`` for hi-hat
   * density claims or ``transientDensityDetail.lowBass`` for kick.
   */
  transientDensityDetail?: TransientDensityDetail | null;
  /**
   * Phase 1.C #5 — saturation / clipping / over-compression hints.
   */
  saturationDetail?: SaturationDetail | null;
  /**
   * Phase 1.C #4 — snare-band character (120-2000 Hz). Uses the drums stem
   * when available, otherwise full-mix audio with spectrum-bin selection.
   */
  snareDetail?: BandDrumDetail | null;
  /**
   * Phase 1.C #4 — hi-hat-band character (2000-12000 Hz). meanDecaySeconds
   * is a rough open-vs-closed proxy.
   */
  hihatDetail?: BandDrumDetail | null;
  rhythmDetail?: RhythmDetail | null;
  melodyDetail?: MelodyDetail;
  transcriptionDetail?: TranscriptionDetail | null;
  /**
   * Optional MT3 polyphonic-transcription namespace. Present only when the
   * backend env var `ASA_ENABLE_MT3=1` is set and the MT3 extra is installed.
   * The whole field is *absent* (not `null`) when the gate is off — see
   * apps/backend/mt3_transcription.py and JSON_SCHEMA.md "Optional MT3
   * Namespace" for the contract. Rendered by `Mt3TranscriptionPanel`
   * (mounted from `AnalysisResults` in the Session Musician suite) when
   * `transcription.mt3.tracks` is non-empty; the per-track MIDI is fetched
   * lazily via `services/mt3Client.ts`.
   */
  transcription?: TranscriptionNamespace;
  pitchDetail?: PitchDetail | null;
  grooveDetail?: GrooveDetail | null;
  beatsLoudness?: BeatsLoudness | null;
  rhythmTimeline?: RhythmTimeline | null;
  sidechainDetail?: SidechainDetail | null;
  effectsDetail?: EffectsDetail | null;
  synthesisCharacter?: SynthesisCharacter | null;
  danceability?: DanceabilityResult | null;
  structure?: StructureData | null;
  arrangementDetail?: ArrangementDetail | null;
  segmentLoudness?: SegmentLoudnessEntry[] | null;
  segmentSpectral?: SegmentSpectralEntry[] | null;
  segmentStereo?: SegmentStereoEntry[] | null;
  segmentKey?: SegmentKeyEntry[] | null;
  chordDetail?: ChordDetail | null;
  perceptual?: PerceptualDetail | null;
  essentiaFeatures?: EssentiaFeatures | null;
  acidDetail?: AcidDetail | null;
  reverbDetail?: ReverbDetail | null;
  vocalDetail?: VocalDetail | null;
  supersawDetail?: SupersawDetail | null;
  bassDetail?: BassDetail | null;
  kickDetail?: KickDetail | null;
  genreDetail?: GenreDetail | null;
}

export type MeasurementResult = Omit<Phase1Result, 'transcriptionDetail'>;

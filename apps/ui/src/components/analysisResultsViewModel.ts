import { AbletonRecommendation, Phase1Result, Phase2Result } from "../types";

export type ConfidenceLevel = "High" | "Moderate" | "Low";

export interface ConfidenceBadgeViewModel {
  label: string;
  level: ConfidenceLevel;
}

const SENTENCE_BREAK_REGEX = /(?<=[.!?])\s+/;

const CONFIDENCE_LABEL_MAP: Record<string, string> = {
  "key signature": "Key",
  "true peak": "Peak",
  "chord progression": "Chords",
  "melody transcription": "Melody",
  "sidechain detection": "Sidechain",
  "segment key (short segment)": "Segment Key",
};

const SEGMENT_COLOR_CLASSES = [
  "bg-[#355070]",
  "bg-[#6d597a]",
  "bg-[#b56576]",
  "bg-[#e56b6f]",
  "bg-[#eaac8b]",
  "bg-[#4f772d]",
];

const GROUP_ORDER = [
  "DRUM PROCESSING",
  "BASS PROCESSING",
  "SYNTH / MELODIC",
  "MID PROCESSING",
  "HIGH-END DETAIL",
  "MASTER BUS",
] as const;

type ProcessingGroup = (typeof GROUP_ORDER)[number];

export interface ArrangementSegmentViewModel {
  id: string;
  name: string;
  startTime: number;
  endTime: number;
  lufs: number | null;
  widthPercent: number;
  leftPercent: number;
  lufsLabel: string;
  description: string;
  spectralNote?: string;
  colorClass: string;
}

export interface NoveltyMarkerViewModel {
  time: number;
  label: string;
  leftPercent: number;
}

export interface ArrangementViewModel {
  summary: string;
  noveltyNotes: string;
  totalDuration: number;
  segments: ArrangementSegmentViewModel[];
  noveltyMarkers: NoveltyMarkerViewModel[];
}

export interface SonicMeasurementViewModel {
  icon: string;
  label: string;
  value: string;
}

export interface SonicElementCardViewModel {
  id: string;
  title: string;
  icon: string;
  summary: string;
  description: string;
  measurements: SonicMeasurementViewModel[];
  isWidthAndStereo: boolean;
  transcriptionDerived?: boolean;
  sources?: string[];
}

export interface ChainParameterViewModel {
  label: string;
  value: string;
}

export interface MixChainCardViewModel {
  id: string;
  order: number;
  device: string;
  category: string;
  role: string;
  parameters: ChainParameterViewModel[];
  proTip: string;
}

export interface MixChainGroupViewModel {
  name: string;
  cards: MixChainCardViewModel[];
  annotation?: string;
}

export interface PatchCardViewModel {
  id: string;
  device: string;
  category: string;
  patchRole: string;
  whyThisWorks: string;
  parameters: ChainParameterViewModel[];
  proTip: string;
  transcriptionDerived?: boolean;
}

export interface MelodyInsightsViewModel {
  noteCount: number;
  dominantNotes: string[];
  rangeLabel: string;
  confidence: number;
  confidenceLabel: ConfidenceLevel;
  isDraft: boolean;
}

interface SonicElementDefinition {
  title: string;
  icon: string;
}

interface HighEndInference {
  cues: string[];
  stereoAware: boolean;
}

const SONIC_ELEMENT_DEFINITIONS: Record<string, SonicElementDefinition> = {
  kick: { title: "Kick", icon: "🥁" },
  bass: { title: "Bass", icon: "🫧" },
  melodicArp: { title: "Melodic Arp", icon: "🎹" },
  grooveAndTiming: { title: "Groove & Timing", icon: "⏱" },
  effectsAndTexture: { title: "Effects & Texture", icon: "🛰" },
  widthAndStereo: { title: "Width & Stereo", icon: "↔" },
  harmonicContent: { title: "Harmonic Content", icon: "🎼" },
};

const HIGH_END_CUE_MAP: Array<{ keywords: string[]; label: string }> = [
  { keywords: ["hat", "hihat", "hi-hat", "cymbal", "shaker"], label: "Hi-hats & Cymbals" },
  { keywords: ["sweep", "riser", "uplifter", "noise sweep"], label: "Synth Sweeps" },
  {
    keywords: ["pitched percussion", "tom", "pluck", "bell", "mallet", "percussive melody"],
    label: "Pitched Percussion",
  },
  { keywords: ["vocal chop", "vocal sample", "chop", "vox"], label: "Vocal Samples" },
  { keywords: ["air", "sparkle", "brilliance", "top end", "high end"], label: "Air & Brilliance" },
];

export function truncateAtSentenceBoundary(text: string, maxChars = 600): string {
  const normalized = text.trim();
  if (!normalized) return "";
  if (normalized.length <= maxChars) return normalized;

  const clipped = normalized.slice(0, maxChars);
  const punctuationIndexes: number[] = [];

  for (let i = 0; i < clipped.length; i += 1) {
    const char = clipped[i];
    if (char === "." || char === "!" || char === "?") {
      punctuationIndexes.push(i);
    }
  }

  if (punctuationIndexes.length > 0) {
    const index = punctuationIndexes[punctuationIndexes.length - 1];
    return `${clipped.slice(0, index + 1).trim()}...`;
  }

  const lastWordBoundary = clipped.lastIndexOf(" ");
  if (lastWordBoundary > 0) {
    return `${clipped.slice(0, lastWordBoundary).trim()}...`;
  }

  return `${clipped.trim()}...`;
}

export function truncateBySentenceCount(text: string, maxSentences: number): string {
  const normalized = text.trim();
  if (!normalized) return "";
  if (maxSentences <= 0) return "";

  const sentences = normalized
    .split(SENTENCE_BREAK_REGEX)
    .map((sentence) => sentence.trim())
    .filter(Boolean);

  if (sentences.length <= maxSentences) {
    return normalized;
  }

  return `${sentences.slice(0, maxSentences).join(" ").trim()}...`;
}

function sanitizeText(text: string, maxChars = 600): string {
  return truncateAtSentenceBoundary(text, maxChars);
}

function normalizeConfidenceFieldLabel(field: string): string {
  const normalized = field.trim().toLowerCase();
  if (!normalized) return "Signal";

  if (CONFIDENCE_LABEL_MAP[normalized]) {
    return CONFIDENCE_LABEL_MAP[normalized];
  }

  const cleaned = field.split("(")[0].split(":")[0].trim();
  if (!cleaned) return "Signal";

  const compact = cleaned.split(/\s+/)[0];
  return compact.length > 14 ? `${compact.slice(0, 14)}...` : compact;
}

function parseConfidenceScalar(raw: string): number | null {
  const normalized = raw.trim().toLowerCase();
  if (!normalized) return null;

  if (normalized.includes("%")) {
    const value = Number.parseFloat(normalized.replace("%", ""));
    return Number.isFinite(value) ? value / 100 : null;
  }

  const value = Number.parseFloat(normalized);
  if (!Number.isFinite(value)) return null;
  if (value > 1) return value / 100;
  return value;
}

function normalizeConfidenceLevel(raw: string): ConfidenceLevel {
  const normalized = raw.trim().toLowerCase();

  if (normalized.includes("high")) return "High";
  if (normalized.includes("moderate") || normalized.includes("medium") || normalized === "med") {
    return "Moderate";
  }
  if (normalized.includes("low")) return "Low";

  const scalar = parseConfidenceScalar(raw);
  if (scalar === null) return "Moderate";
  if (scalar >= 0.8) return "High";
  if (scalar >= 0.5) return "Moderate";
  return "Low";
}

export function toConfidenceBadges(
  notes: Phase2Result["confidenceNotes"] | undefined | null,
): ConfidenceBadgeViewModel[] {
  if (!Array.isArray(notes)) return [];

  return notes.map((note) => ({
    label: normalizeConfidenceFieldLabel(note.field),
    level: normalizeConfidenceLevel(note.value),
  }));
}

function formatSeconds(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0s";
  const rounded = Math.round(seconds * 10) / 10;
  return `${rounded}s`;
}

function parseSegmentName(description: string, index: number): string {
  const raw = description.trim();
  const lowered = raw.toLowerCase();

  const keywordMap: Array<[RegExp, string]> = [
    [/\bintro\b/, "INTRO"],
    [/\bbuild\b/, "BUILD"],
    [/\bdrop\b/, "DROP"],
    [/\bbreak\s?down\b/, "BREAKDOWN"],
    [/\bbridge\b/, "BRIDGE"],
    [/\bchorus\b/, "CHORUS"],
    [/\bverse\b/, "VERSE"],
    [/\boutro\b/, "OUTRO"],
  ];

  for (const [pattern, label] of keywordMap) {
    if (pattern.test(lowered)) return label;
  }

  const prefixMatch = raw.match(/^([A-Za-z][A-Za-z\s/-]{2,22})\s*[:\-]/);
  if (prefixMatch?.[1]) {
    return prefixMatch[1].toUpperCase().trim();
  }

  return `SECTION ${index + 1}`;
}

function parseNoveltyTimestamps(noveltyNotes: string | undefined, totalDuration: number): number[] {
  if (!noveltyNotes) return [];

  const matches = noveltyNotes.matchAll(/(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)?/gi);
  const values = new Set<number>();

  for (const match of matches) {
    const value = Number.parseFloat(match[1]);
    if (Number.isFinite(value) && value >= 0 && value <= totalDuration) {
      values.add(Math.round(value * 10) / 10);
    }
  }

  return Array.from(values).sort((a, b) => a - b);
}

export function buildArrangementViewModel(
  phase1: Phase1Result,
  arrangementOverview: Phase2Result["arrangementOverview"] | undefined,
): ArrangementViewModel | null {
  if (!arrangementOverview || !Array.isArray(arrangementOverview.segments) || arrangementOverview.segments.length === 0) {
    return null;
  }

  const maxEndTime = Math.max(...arrangementOverview.segments.map((segment) => segment.endTime));
  const totalDuration = Math.max(phase1.durationSeconds || 0, maxEndTime || 0, 1);

  const segments = arrangementOverview.segments.map((segment, index) => {
    const startTime = Number.isFinite(segment.startTime) ? segment.startTime : 0;
    const endTime = Number.isFinite(segment.endTime) ? segment.endTime : startTime + 1;
    const lufs = Number.isFinite(segment.lufs) ? (segment.lufs as number) : null;
    const widthPercent = Math.max(((endTime - startTime) / totalDuration) * 100, 6);
    const leftPercent = Math.max((startTime / totalDuration) * 100, 0);

    return {
      id: `segment-${index + 1}`,
      name: parseSegmentName(segment.description, index),
      startTime,
      endTime,
      lufs,
      widthPercent,
      leftPercent,
      lufsLabel: lufs !== null ? `${lufs.toFixed(1)} LUFS` : "LUFS n/a",
      description: truncateAtSentenceBoundary(segment.description, 600),
      spectralNote: segment.spectralNote ? truncateAtSentenceBoundary(segment.spectralNote, 260) : undefined,
      colorClass: SEGMENT_COLOR_CLASSES[index % SEGMENT_COLOR_CLASSES.length],
    } satisfies ArrangementSegmentViewModel;
  });

  const noveltyMarkers = parseNoveltyTimestamps(arrangementOverview.noveltyNotes, totalDuration).map((time) => ({
    time,
    label: `Peak ${formatSeconds(time)}`,
    leftPercent: Math.max((time / totalDuration) * 100, 0),
  }));

  return {
    summary: arrangementOverview.summary ? truncateAtSentenceBoundary(arrangementOverview.summary, 600) : "",
    noveltyNotes: arrangementOverview.noveltyNotes ? truncateAtSentenceBoundary(arrangementOverview.noveltyNotes, 600) : "",
    totalDuration,
    segments,
    noveltyMarkers,
  };
}

function toOneLineSummary(text: string, maxLength = 80): string {
  const sanitized = sanitizeText(text, 600);
  const firstSentence = sanitized.split(SENTENCE_BREAK_REGEX)[0]?.trim() || "";
  if (firstSentence.length <= maxLength) return firstSentence;

  const clipped = firstSentence.slice(0, maxLength);
  const wordBoundary = clipped.lastIndexOf(" ");
  if (wordBoundary > 0) {
    return `${clipped.slice(0, wordBoundary).trim()}...`;
  }
  return `${clipped.trim()}...`;
}

function formatSignedDb(value: number): string {
  const fixed = value.toFixed(1);
  return `${value >= 0 ? "+" : ""}${fixed} dB`;
}

function midiToNoteName(midi: number): string {
  const noteNames = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"] as const;
  const clamped = Math.max(0, Math.min(127, Math.round(midi)));
  const octave = Math.floor(clamped / 12) - 1;
  return `${noteNames[clamped % 12]}${octave}`;
}

export function buildMelodyInsights(phase1: Phase1Result): MelodyInsightsViewModel | null {
  const transcriptionDetail =
    phase1.transcriptionDetail && phase1.transcriptionDetail.noteCount > 0 ? phase1.transcriptionDetail : null;
  if (transcriptionDetail) {
    const noteCount = Number.isFinite(transcriptionDetail.noteCount)
      ? Math.max(0, Math.round(transcriptionDetail.noteCount))
      : 0;
    const dominantNotes = Array.isArray(transcriptionDetail.dominantPitches)
      ? transcriptionDetail.dominantPitches.map((note) => note.pitchName)
      : [];
    const hasRange = transcriptionDetail.pitchRange.minName !== null && transcriptionDetail.pitchRange.maxName !== null;
    const rangeLabel = hasRange
      ? `${transcriptionDetail.pitchRange.minName as string} - ${transcriptionDetail.pitchRange.maxName as string}`
      : "n/a";
    const confidence = Math.max(0, Math.min(1, transcriptionDetail.averageConfidence ?? 0));
    const confidenceLabel: ConfidenceLevel = confidence >= 0.8 ? "High" : confidence >= 0.5 ? "Moderate" : "Low";

    return {
      noteCount,
      dominantNotes,
      rangeLabel,
      confidence,
      confidenceLabel,
      isDraft: confidence < 0.15,
    };
  }

  const detail = phase1.melodyDetail;
  if (!detail) return null;

  const noteCount = Number.isFinite(detail.noteCount) ? Math.max(0, Math.round(detail.noteCount)) : 0;
  const dominantNotes = Array.isArray(detail.dominantNotes) ? detail.dominantNotes.map((note) => midiToNoteName(note)) : [];
  const hasRange = detail.pitchRange?.min !== null && detail.pitchRange?.max !== null;
  const rangeLabel = hasRange
    ? `${midiToNoteName(detail.pitchRange.min as number)} - ${midiToNoteName(detail.pitchRange.max as number)}`
    : "n/a";
  const confidence = Math.max(0, Math.min(1, detail.pitchConfidence ?? 0));
  const confidenceLabel: ConfidenceLevel = confidence >= 0.8 ? "High" : confidence >= 0.5 ? "Moderate" : "Low";

  return {
    noteCount,
    dominantNotes,
    rangeLabel,
    confidence,
    confidenceLabel,
    isDraft: confidence < 0.15,
  };
}

function getSonicMeasurements(
  key: string,
  phase1: Phase1Result,
  melodyInsights: MelodyInsightsViewModel | null,
): SonicMeasurementViewModel[] {
  const sets: Record<string, SonicMeasurementViewModel[]> = {
    kick: [
      { icon: "🎚", label: "Low Bass", value: formatSignedDb(phase1.spectralBalance.lowBass) },
      { icon: "📏", label: "Peak", value: `${phase1.truePeak.toFixed(1)} dB` },
      { icon: "⏱", label: "Tempo", value: `${Math.round(phase1.bpm)} BPM` },
    ],
    bass: [
      { icon: "🔻", label: "Sub Bass", value: formatSignedDb(phase1.spectralBalance.subBass) },
      { icon: "🎚", label: "Low Bass", value: formatSignedDb(phase1.spectralBalance.lowBass) },
      { icon: "🔑", label: "Key", value: phase1.key ?? "Unknown" },
    ],
    melodicArp: [
      { icon: "🎼", label: "Key", value: phase1.key ?? "Unknown" },
      { icon: "⏱", label: "Tempo", value: `${Math.round(phase1.bpm)} BPM` },
      { icon: "🧭", label: "Meter", value: phase1.timeSignature },
      ...(melodyInsights
        ? [
            { icon: "🧮", label: "Transcribed Notes", value: `${melodyInsights.noteCount}` },
            { icon: "📐", label: "Note Range", value: melodyInsights.rangeLabel },
            {
              icon: "🎵",
              label: "Dominant Notes",
              value: melodyInsights.dominantNotes.slice(0, 3).join(", ") || "n/a",
            },
            {
              icon: "📝",
              label: "Transcription",
              value: `${melodyInsights.confidenceLabel} (${Math.round(melodyInsights.confidence * 100)}%)`,
            },
          ]
        : []),
    ],
    grooveAndTiming: [
      { icon: "⏱", label: "Tempo", value: `${Math.round(phase1.bpm)} BPM` },
      { icon: "🧭", label: "Meter", value: phase1.timeSignature },
      { icon: "⌛", label: "Duration", value: formatSeconds(phase1.durationSeconds) },
    ],
    effectsAndTexture: [
      { icon: "✨", label: "Brilliance", value: formatSignedDb(phase1.spectralBalance.brilliance) },
      { icon: "📡", label: "Stereo Corr", value: phase1.stereoCorrelation.toFixed(2) },
      { icon: "🎚", label: "Highs", value: formatSignedDb(phase1.spectralBalance.highs) },
    ],
    widthAndStereo: [
      { icon: "↔", label: "Width", value: phase1.stereoWidth.toFixed(2) },
      { icon: "📡", label: "Correlation", value: phase1.stereoCorrelation.toFixed(2) },
      { icon: "🧲", label: "Peak", value: `${phase1.truePeak.toFixed(1)} dB` },
    ],
    harmonicContent: [
      { icon: "🎼", label: "Key", value: phase1.key ?? "Unknown" },
      { icon: "🎚", label: "Mids", value: formatSignedDb(phase1.spectralBalance.mids) },
      { icon: "🔍", label: "Key Conf", value: `${Math.round(phase1.keyConfidence * 100)}%` },
    ],
  };

  return sets[key] ?? sets.harmonicContent;
}

export function buildSonicElementCards(
  phase1: Phase1Result,
  sonicElements: Phase2Result["sonicElements"] | undefined,
): SonicElementCardViewModel[] {
  if (!sonicElements || typeof sonicElements !== "object") return [];
  const melodyInsights = buildMelodyInsights(phase1);

  return Object.entries(sonicElements)
    .filter(([, value]) => {
      if (typeof value === "string") return value.trim().length > 0;
      if (typeof value === "object" && value !== null) {
        return typeof (value as { description?: string }).description === "string" &&
          (value as { description?: string }).description!.trim().length > 0;
      }
      return false;
    })
    .map(([key, rawValue]) => {
      const def = SONIC_ELEMENT_DEFINITIONS[key] ?? {
        title: key.replace(/([A-Z])/g, " $1").trim(),
        icon: "🎛",
      };

      const isWidthAndStereo = key === "widthAndStereo";
      const transcriptionDerived = key === "melodicArp" && !!melodyInsights;

      // Handle both string and object formats
      let descriptionText: string;
      let sources: string[] | undefined;
      if (typeof rawValue === "string") {
        descriptionText = rawValue;
      } else if (typeof rawValue === "object" && rawValue !== null) {
        descriptionText = (rawValue as { description?: string }).description || "";
        sources = (rawValue as { sources?: string[] }).sources;
      } else {
        descriptionText = String(rawValue);
      }

      const sanitized = sanitizeText(descriptionText, 600);
      const sentenceCap = isWidthAndStereo ? 6 : 4;

      return {
        id: key,
        title: def.title,
        icon: def.icon,
        summary: toOneLineSummary(sanitized, 80),
        description: truncateBySentenceCount(sanitized, sentenceCap),
        measurements: getSonicMeasurements(key, phase1, melodyInsights),
        isWidthAndStereo,
        transcriptionDerived,
        sources,
      } satisfies SonicElementCardViewModel;
    });
}

function normalizeCategory(device: string, parameter: string, reason: string): string {
  const text = `${device} ${parameter} ${reason}`.toLowerCase();

  if (/limit|master|clip/.test(text)) return "MASTERING";
  if (/eq|filter|shelf|cut/.test(text)) return "EQ";
  if (/compress|glue|transient|dynamics/.test(text)) return "DYNAMICS";
  if (/stereo|width|utility|pan|mid\/side/.test(text)) return "STEREO";
  if (/route|bus|send|return/.test(text)) return "ROUTING";
  if (/midi|arp|note|chord/.test(text)) return "MIDI";
  if (/synth|osc|wavetable|operator/.test(text)) return "SYNTHESIS";
  return "EFFECTS";
}

function scoreByKeywords(text: string, keywords: string[]): number {
  return keywords.reduce((score, keyword) => score + (text.includes(keyword) ? 1 : 0), 0);
}

function hasStereoIntent(text: string): boolean {
  return /\bstereo\b|\bwidth\b|\bimage\b|\bpan\b|\bmid\/side\b|\bside\b/.test(text);
}

function detectHighEndCues(text: string): string[] {
  if (!text.trim()) return [];

  const normalized = text.toLowerCase();
  const cues: string[] = [];

  for (const cue of HIGH_END_CUE_MAP) {
    if (cue.keywords.some((keyword) => normalized.includes(keyword))) {
      cues.push(cue.label);
    }
  }

  return Array.from(new Set(cues));
}

function inferHighEndContext(
  itemText: string,
  sonicElements: Phase2Result["sonicElements"] | undefined,
): HighEndInference {
  const contextText = [
    itemText,
    sonicElements?.effectsAndTexture ?? "",
    sonicElements?.widthAndStereo ?? "",
  ]
    .join(" ")
    .toLowerCase();

  const cues = detectHighEndCues(contextText);
  return {
    cues,
    stereoAware: hasStereoIntent(contextText),
  };
}

function summarizeHighEndFocus(cues: string[]): string {
  if (cues.length === 0) return "Hi-hats / sweeps / pitched perc / vocal samples";
  return cues.slice(0, 3).join(" + ");
}

function inferProcessingGroup(text: string, positionRatio: number): ProcessingGroup {
  const specificGroups: Array<{ group: ProcessingGroup; keywords: string[] }> = [
    { group: "DRUM PROCESSING", keywords: ["kick", "drum", "snare", "transient", "groove", "percussion"] },
    { group: "BASS PROCESSING", keywords: ["bass", "sub", "low end", "low bass", "mono below"] },
    { group: "SYNTH / MELODIC", keywords: ["synth", "arp", "melodic", "harmony", "lead", "pad"] },
    { group: "MID PROCESSING", keywords: ["mid", "presence", "body", "clarity", "mids"] },
    {
      group: "HIGH-END DETAIL",
      keywords: [
        "high-end",
        "high end",
        "top end",
        "air band",
        "brilliance",
        "sparkle",
        "brightness",
        "hat",
        "hihat",
        "hi-hat",
        "cymbal",
        "shaker",
        "sweep",
        "riser",
        "pitched percussion",
        "vocal chop",
        "vocal sample",
      ],
    },
  ];

  let best: { group: ProcessingGroup; score: number } | null = null;
  for (const candidate of specificGroups) {
    const score = scoreByKeywords(text, candidate.keywords);
    if (score > 0 && (!best || score > best.score)) {
      best = { group: candidate.group, score };
    }
  }

  if (best) return best.group;

  const masterScore = scoreByKeywords(text, ["master", "limiter", "ceiling", "final", "bus"]);
  if (masterScore > 0) return "MASTER BUS";

  // Deterministic fallback by chain position.
  if (positionRatio <= 0.18) return "DRUM PROCESSING";
  if (positionRatio <= 0.34) return "BASS PROCESSING";
  if (positionRatio <= 0.54) return "SYNTH / MELODIC";
  if (positionRatio <= 0.76) return "MID PROCESSING";
  if (positionRatio <= 0.9) return "HIGH-END DETAIL";
  return "MASTER BUS";
}

function normalizeParameterLabel(label: string): string {
  const text = label.trim();
  if (!text) return "Target";

  const map: Record<string, string> = {
    threshold: "Threshold",
    ratio: "Ratio",
    attack: "Attack",
    release: "Release",
    gain: "Output Gain",
    ceiling: "Ceiling",
    width: "Stereo Width",
    cutoff: "Cutoff",
  };

  const key = text.toLowerCase();
  if (map[key]) return map[key];
  return text;
}

function uniqueParameters(parameters: ChainParameterViewModel[], maxCount = 4): ChainParameterViewModel[] {
  const seen = new Set<string>();
  const results: ChainParameterViewModel[] = [];

  for (const parameter of parameters) {
    const key = parameter.label.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    results.push(parameter);
    if (results.length >= maxCount) break;
  }

  return results;
}

function buildDerivedChainParameters(
  group: ProcessingGroup,
  phase1: Phase1Result,
  highEnd: HighEndInference = { cues: [], stereoAware: false },
): ChainParameterViewModel[] {
  switch (group) {
    case "DRUM PROCESSING":
      return [
        { label: "Tempo Sync", value: `${Math.round(phase1.bpm)} BPM` },
        { label: "Punch Target", value: `${phase1.truePeak.toFixed(1)} dB peak` },
      ];
    case "BASS PROCESSING":
      return [
        { label: "Bass mono below", value: "100 Hz" },
        { label: "Low Bass Focus", value: formatSignedDb(phase1.spectralBalance.lowBass) },
      ];
    case "SYNTH / MELODIC":
      return [
        { label: "Key Center", value: phase1.key ?? "Unknown" },
        { label: "Grid", value: phase1.timeSignature },
      ];
    case "MID PROCESSING":
      return [
        { label: "Mid Balance", value: formatSignedDb(phase1.spectralBalance.mids) },
        { label: "Upper Mids", value: formatSignedDb(phase1.spectralBalance.upperMids) },
      ];
    case "HIGH-END DETAIL":
      return uniqueParameters(
        [
          { label: "Focus Elements", value: summarizeHighEndFocus(highEnd.cues) },
          { label: "Highs Balance", value: formatSignedDb(phase1.spectralBalance.highs) },
          { label: "Brilliance", value: formatSignedDb(phase1.spectralBalance.brilliance) },
          ...(highEnd.stereoAware
            ? [{ label: "Top-End Spread", value: `${phase1.stereoWidth.toFixed(2)} width` }]
            : []),
        ],
        4,
      );
    case "MASTER BUS":
      return [
        { label: "Ceiling", value: `${Math.min(-0.3, phase1.truePeak - 0.1).toFixed(1)} dB` },
        { label: "Integrated Loudness", value: `${phase1.lufsIntegrated.toFixed(1)} LUFS` },
      ];
    default:
      return [];
  }
}

function buildRoleSentence(reason: string, group: ProcessingGroup, highEndCues: string[] = []): string {
  const base = sanitizeText(reason, 220);
  const sentence = base.split(SENTENCE_BREAK_REGEX)[0] || base;
  const prefixMap: Record<ProcessingGroup, string> = {
    "DRUM PROCESSING": "Shapes drum impact",
    "BASS PROCESSING": "Controls bass energy",
    "SYNTH / MELODIC": "Supports melodic clarity",
    "MID PROCESSING": "Balances the center band",
    "HIGH-END DETAIL": "Refines high-end articulation",
    "MASTER BUS": "Finalizes the master bus",
  };
  const cueSuffix = group === "HIGH-END DETAIL" && highEndCues.length > 0
    ? ` for ${summarizeHighEndFocus(highEndCues)}`
    : "";
  return `${prefixMap[group]}${cueSuffix} by ${sentence.charAt(0).toLowerCase()}${sentence.slice(1)}`;
}

function buildProTip(group: ProcessingGroup): string {
  const tips: Record<ProcessingGroup, string> = {
    "DRUM PROCESSING": "A/B the chain with kick-only playback so the groove stays punchy after processing.",
    "BASS PROCESSING": "Check the bass in mono after each tweak to keep the low end centered and stable.",
    "SYNTH / MELODIC": "Automate one key parameter over 4-8 bars so melodic parts evolve without adding clutter.",
    "MID PROCESSING": "Bypass every few bars and adjust only until mids feel present but never nasal.",
    "HIGH-END DETAIL": "Solo hats/sweeps/chops and trim only until top-end detail reads clearly without hiss buildup.",
    "MASTER BUS": "Set ceiling first, then raise input slowly until loudness increases without pumping artifacts.",
  };
  return tips[group];
}

function makeLimiterFallbackCard(phase1: Phase1Result, nextOrder: number): MixChainCardViewModel {
  return {
    id: "fallback-limiter",
    order: nextOrder,
    device: "Limiter",
    category: "MASTERING",
    role: "Finalizes loudness control so peaks stay contained while preserving punch.",
    parameters: [
      { label: "Ceiling", value: `${Math.min(-0.3, phase1.truePeak - 0.1).toFixed(1)} dB` },
      { label: "Integrated Loudness", value: `${phase1.lufsIntegrated.toFixed(1)} LUFS` },
      { label: "Stereo Width", value: phase1.stereoWidth.toFixed(2) },
    ],
    proTip: buildProTip("MASTER BUS"),
  };
}

function mergeGroupAnnotations(left?: string, right?: string): string | undefined {
  const parts = [left, right].filter((value): value is string => typeof value === "string" && value.trim().length > 0);
  return parts.length > 0 ? parts.join(" • ") : undefined;
}

function mergeDisplayGroups(left: MixChainGroupViewModel, right: MixChainGroupViewModel): MixChainGroupViewModel {
  return {
    name: `${left.name} / ${right.name}`,
    cards: [...left.cards, ...right.cards],
    annotation: mergeGroupAnnotations(left.annotation, right.annotation),
  };
}

function isProtectedMixGroup(name: string): boolean {
  return (
    name.includes("DRUM")
    || name.includes("BASS")
    || name.includes("HIGH-END")
    || name.includes("MASTER BUS")
  );
}

function canMergeMixGroups(left: MixChainGroupViewModel, right: MixChainGroupViewModel | undefined): right is MixChainGroupViewModel {
  if (!right) return false;
  if (left.cards.length !== 1 || right.cards.length !== 1) return false;
  if (isProtectedMixGroup(left.name) || isProtectedMixGroup(right.name)) return false;
  return true;
}

function compactMixChainGroups(groups: MixChainGroupViewModel[]): MixChainGroupViewModel[] {
  if (groups.length <= 1) return groups;

  const compacted: MixChainGroupViewModel[] = [];
  let index = 0;

  while (index < groups.length) {
    const current = groups[index];
    if (!current) break;

    const next = groups[index + 1];

    if (!canMergeMixGroups(current, next)) {
      compacted.push({
        name: current.name,
        cards: [...current.cards],
        annotation: current.annotation,
      });
      index += 1;
      continue;
    }

    compacted.push(mergeDisplayGroups(current, next));
    index += 2;
  }

  return compacted;
}

export function buildMixChainGroups(
  phase1: Phase1Result,
  chain: Phase2Result["mixAndMasterChain"] | undefined,
  sonicElements?: Phase2Result["sonicElements"],
): MixChainGroupViewModel[] {
  if (!Array.isArray(chain) || chain.length === 0) return [];

  const total = chain.length;

  const cards = chain.map((item, index) => {
    const text = `${item.device} ${item.parameter} ${item.reason}`.toLowerCase();
    const positionRatio = total <= 1 ? 1 : index / (total - 1);
    const group = inferProcessingGroup(text, positionRatio);
    const category = normalizeCategory(item.device, item.parameter, item.reason);
    const highEnd = group === "HIGH-END DETAIL"
      ? inferHighEndContext(text, sonicElements)
      : { cues: [], stereoAware: false };

    const derivedParams = buildDerivedChainParameters(group, phase1, highEnd);
    const parameters = uniqueParameters(
      [
        { label: normalizeParameterLabel(item.parameter), value: sanitizeText(item.value, 120) },
        ...derivedParams,
      ],
      4,
    );

    // Ensure at least two parameters.
    const safeParameters = parameters.length >= 2 ? parameters : uniqueParameters([...parameters, ...derivedParams], 3);

    return {
      id: `${item.order}-${item.device}-${index}`,
      order: item.order,
      device: item.device,
      category,
      role: buildRoleSentence(item.reason, group, highEnd.cues),
      parameters: safeParameters,
      proTip: buildProTip(group),
      group,
      highEndCues: highEnd.cues,
    } satisfies MixChainCardViewModel & { group: ProcessingGroup; highEndCues: string[] };
  });

  const hasLimiter = cards.some((card) => /limit/i.test(card.device));
  if (!hasLimiter) {
    const nextOrder = Math.max(...cards.map((card) => card.order), 0) + 1;
    cards.push({ ...makeLimiterFallbackCard(phase1, nextOrder), group: "MASTER BUS", highEndCues: [] });
  }

  const grouped = new Map<ProcessingGroup, Array<MixChainCardViewModel & { highEndCues?: string[] }>>();
  for (const group of GROUP_ORDER) {
    grouped.set(group, []);
  }

  cards
    .sort((a, b) => a.order - b.order)
    .forEach((card) => {
      grouped.get(card.group)?.push(card);
    });

  const displayGroups = GROUP_ORDER.map((group) => {
    const groupCards = grouped.get(group) ?? [];
    const uniqueHighEndCues = group === "HIGH-END DETAIL"
      ? Array.from(new Set(groupCards.flatMap((card) => card.highEndCues ?? [])))
      : [];

    return {
      name: group,
      cards: groupCards.map(({ highEndCues, ...card }) => card),
      annotation: group === "HIGH-END DETAIL"
        ? `Annotated high-end focus: ${summarizeHighEndFocus(uniqueHighEndCues)}`
        : undefined,
    };
  }).filter((group) => group.cards.length > 0);

  return compactMixChainGroups(displayGroups);
}

function mapPatchRole(category: string): string {
  const key = category.toLowerCase();
  if (key.includes("synth")) return "Primary tone generator";
  if (key.includes("eq")) return "Tone shaper";
  if (key.includes("dynamic")) return "Dynamic control stage";
  if (key.includes("stereo")) return "Stereo placement stage";
  if (key.includes("midi")) return "Pattern driver";
  if (key.includes("routing")) return "Signal routing stage";
  return "Texture and movement stage";
}

function groupRecommendationsByDevice(recommendations: AbletonRecommendation[]): Array<{
  device: string;
  category: string;
  items: AbletonRecommendation[];
}> {
  const map = new Map<string, { category: string; items: AbletonRecommendation[] }>();

  recommendations.forEach((item) => {
    const key = item.device.trim();
    if (!map.has(key)) {
      map.set(key, {
        category: item.category,
        items: [],
      });
    }
    map.get(key)?.items.push(item);
  });

  return Array.from(map.entries()).map(([device, value]) => ({
    device,
    category: value.category,
    items: value.items,
  }));
}

function buildPatchFallbackParameters(phase1: Phase1Result): ChainParameterViewModel[] {
  return [
    { label: "Tempo", value: `${Math.round(phase1.bpm)} BPM` },
    { label: "Key", value: phase1.key ?? "Unknown" },
    { label: "Stereo Width", value: phase1.stereoWidth.toFixed(2) },
  ];
}

function buildMelodyPatchParameters(insights: MelodyInsightsViewModel): ChainParameterViewModel[] {
  return [
    { label: "Transcribed Notes", value: `${insights.noteCount}` },
    { label: "Note Range", value: insights.rangeLabel },
    { label: "Dominant Notes", value: insights.dominantNotes.slice(0, 3).join(", ") || "n/a" },
    { label: "Transcription Confidence", value: `${Math.round(insights.confidence * 100)}% (${insights.confidenceLabel})` },
  ];
}

function isMidiFocusedGroup(device: string, category: string): boolean {
  const text = `${device} ${category}`.toLowerCase();
  return /midi|arp|note|sequencer|clip|scale|chord/.test(text);
}

function buildStereoWidthPatchCard(
  phase1: Phase1Result,
  phase2: Phase2Result,
  order: number,
): PatchCardViewModel {
  const widthNarrative = sanitizeText(
    phase2.sonicElements?.widthAndStereo ||
      "Keep stereo image controlled: widen upper layers while the low end stays centered.",
    260,
  );

  return {
    id: `patch-${order}-stereo-width`,
    device: "Utility / Stereo Imager",
    category: "UTILITY",
    patchRole: "Stereo image management",
    whyThisWorks: truncateAtSentenceBoundary(
      `${widthNarrative} This maps directly to measured width ${phase1.stereoWidth.toFixed(2)} and correlation ${phase1.stereoCorrelation.toFixed(2)}.`,
      320,
    ),
    parameters: [
      { label: "Stereo Width", value: phase1.stereoWidth.toFixed(2) },
      { label: "Correlation Floor", value: phase1.stereoCorrelation.toFixed(2) },
      { label: "Bass mono below", value: "100 Hz" },
      { label: "Ceiling", value: `${Math.min(-0.3, phase1.truePeak - 0.1).toFixed(1)} dB` },
    ],
    proTip:
      "Make width moves in the highs first, then mono-check kick and bass before committing the setting.",
    transcriptionDerived: false,
  };
}

export function buildPatchCards(
  phase1: Phase1Result,
  phase2: Phase2Result | null,
): PatchCardViewModel[] {
  if (!phase2) {
    return [];
  }

  const melodyInsights = buildMelodyInsights(phase1);
  const recommendations = Array.isArray(phase2.abletonRecommendations) ? phase2.abletonRecommendations : [];
  const grouped = groupRecommendationsByDevice(recommendations);
  const characteristicContext = Array.isArray(phase2.detectedCharacteristics)
    ? phase2.detectedCharacteristics.slice(0, 2).map((item) => item.name).join(" + ")
    : "the detected track profile";

  const cards: PatchCardViewModel[] = grouped.map((group, index) => {
    const normalizedCategory = String(group.category || "EFFECTS").toUpperCase();
    const midiFocused = !!melodyInsights && isMidiFocusedGroup(group.device, normalizedCategory);
    const parameters = uniqueParameters(
      group.items.map((item) => ({
        label: normalizeParameterLabel(item.parameter),
        value: sanitizeText(item.value, 120),
      })),
      5,
    );

    const mergedParameters = parameters.length >= 3
      ? parameters
      : uniqueParameters([...parameters, ...buildPatchFallbackParameters(phase1)], 5);
    const enrichedParameters = midiFocused
      ? uniqueParameters([...mergedParameters, ...buildMelodyPatchParameters(melodyInsights as MelodyInsightsViewModel)], 5)
      : mergedParameters;

    const topReason = sanitizeText(group.items[0]?.reason || "Supports the current sonic direction.", 240);
    const baseWhy = truncateAtSentenceBoundary(
      `${topReason} This aligns with ${characteristicContext || "the detected sonic characteristics"}.`,
      320,
    );
    const transcriptionContext = midiFocused
      ? ` Transcription-derived: ${melodyInsights?.noteCount ?? 0} notes across ${melodyInsights?.rangeLabel ?? "n/a"}, dominant tones ${melodyInsights?.dominantNotes.slice(0, 3).join(", ") || "n/a"}.`
      : "";
    const caution = midiFocused && melodyInsights?.isDraft
      ? " Confidence is low, so use this as a draft guide and verify by ear."
      : "";
    const whyThisWorks = truncateAtSentenceBoundary(`${baseWhy}${transcriptionContext}${caution}`, 420);

    const firstTip = group.items.find((item) => item.advancedTip)?.advancedTip;

    return {
      id: `patch-${index}-${group.device}`,
      device: group.device,
      category: normalizedCategory,
      patchRole: midiFocused ? `${mapPatchRole(normalizedCategory)} • Transcription-driven` : mapPatchRole(normalizedCategory),
      whyThisWorks,
      parameters: enrichedParameters,
      proTip: sanitizeText(
        firstTip || "Automate one macro over each phrase to keep motion while maintaining the core tone.",
        240,
      ),
      transcriptionDerived: midiFocused,
    };
  });

  const hasMidiFocusedCard = cards.some((card) => card.transcriptionDerived);
  if (melodyInsights && !hasMidiFocusedCard) {
    cards.push({
      id: `patch-${cards.length}-midi-clip-guide`,
      device: "MIDI Clip Guide",
      category: "MIDI",
      patchRole: "Transcription-derived melodic scaffold",
      whyThisWorks: truncateAtSentenceBoundary(
        `Transcription-derived: ${melodyInsights.noteCount} notes covering ${melodyInsights.rangeLabel} with dominant notes ${melodyInsights.dominantNotes.slice(0, 3).join(", ") || "n/a"}. ${
          melodyInsights.isDraft
            ? "Confidence is low, so treat this as a draft pattern and confirm by ear."
            : "Confidence is stable enough to use as a first-pass melodic blueprint."
        }`,
        420,
      ),
      parameters: uniqueParameters(
        [...buildMelodyPatchParameters(melodyInsights), ...buildPatchFallbackParameters(phase1)],
        5,
      ),
      proTip: melodyInsights.isDraft
        ? "Start with this clip as rough contour, then simplify rhythm and re-voice intervals by ear."
        : "Duplicate the guide clip and vary only rhythm first, then alter note order to keep motif identity.",
      transcriptionDerived: true,
    });
  }

  const hasStereoFocusedDevice = grouped.some((group) =>
    /stereo|width|imager|utility|pan/i.test(group.device) || /stereo|utility|space/i.test(group.category),
  );

  if (!hasStereoFocusedDevice) {
    cards.push(buildStereoWidthPatchCard(phase1, phase2, cards.length));
  }

  return cards;
}

export function calculateStereoBandStyle(width: number): { left: string; width: string } {
  const clamped = Math.max(0, Math.min(width, 1));
  const bandWidth = Math.max(clamped * 100, 4);
  const left = 50 - bandWidth / 2;

  return {
    left: `${left}%`,
    width: `${bandWidth}%`,
  };
}

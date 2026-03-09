import { GoogleGenAI, Type, Type as SchemaType } from "@google/genai";
import { appConfig, isGeminiPhase2Available } from "../config";
import { DiagnosticLogEntry, Phase1Result, Phase2Result } from "../types";
import { PHASE2_LABEL } from "./phaseLabels";

const INLINE_SIZE_LIMIT = 20_971_520;

interface AnalyzePhase2Args {
  file: File;
  modelName: string;
  phase1Result: Phase1Result;
  audioMetadata: DiagnosticLogEntry["audioMetadata"];
}

interface AnalyzePhase2Result {
  result: Phase2Result;
  log: DiagnosticLogEntry;
}

async function withRetry<T>(
  operation: () => Promise<T>,
  maxRetries = 3,
  baseDelayMs = 2_000,
): Promise<T> {
  let attempt = 0;
  while (attempt < maxRetries) {
    try {
      return await operation();
    } catch (error: unknown) {
      attempt += 1;
      const errorMessage = formatError(error);
      const isRetryable =
        errorMessage.includes("503") ||
        errorMessage.includes("high demand") ||
        errorMessage.includes("429") ||
        errorMessage.includes("quota") ||
        errorMessage.includes("UNAVAILABLE");

      if (!isRetryable || attempt >= maxRetries) {
        throw error;
      }

      const delay = baseDelayMs * Math.pow(2, attempt - 1) + Math.random() * 1_000;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
  throw new Error("Max retries reached for Gemini phase-2 analysis.");
}

export function canRunGeminiPhase2(): boolean {
  return isGeminiPhase2Available();
}

export async function analyzePhase2WithGemini({
  file,
  modelName,
  phase1Result,
  audioMetadata,
}: AnalyzePhase2Args): Promise<AnalyzePhase2Result> {
  if (!canRunGeminiPhase2()) {
    throw new Error("Gemini phase-2 is disabled or missing VITE_GEMINI_API_KEY.");
  }

  const ai = new GoogleGenAI({
    apiKey: appConfig.geminiApiKey,
    httpOptions: {
      timeout: 5 * 60 * 1_000,
    },
  });
  const phase2Prompt = `You are an expert Ableton Live 12 producer and sound designer 
specialising in electronic music reconstruction. You receive:
1. A structured JSON object of deterministic DSP measurements
2. The audio file itself

ABSOLUTE RULES:
1. Every numeric value in the JSON is ground truth from a 
   deterministic DSP engine. Do not re-estimate or override 
   any numeric field using audio inference.
2. You are PROHIBITED from overriding: bpm, key, lufsIntegrated, 
   lufsRange, truePeak, stereoDetail values, durationSeconds.
3. Use the exact key string provided. Do not reinterpret as 
   relative major/minor. Do not override from audio perception.
4. If audio perception contradicts JSON, JSON is correct.
5. bpmAgreement: true = two algorithms agree. High confidence.
6. Low confidence handling:
   - pitchConfidence below 0.15 = melody is draft only
   - chordStrength below 0.70 = chords approximate
   - pumpingConfidence below 0.40 = do not assert sidechain
   - segmentKey from segments shorter than 10s = low confidence
7. When transcriptionDetail is present, use dominantPitches for note name recommendations, not melodyDetail.dominantNotes.
8. stemSeparationUsed: true means bass and melodic content have been transcribed independently - treat bass stem notes and other stem notes as separate layers.
9. You are a producer reading a spec sheet, not an audio analyser.
10. mixAndMasterChain must contain a minimum of 8 device objects. If fewer than 8 real devices can be inferred from the audio, supplement with contextually appropriate Ableton Live devices that would suit the detected characteristics. Never return fewer than 8.

FIELD GLOSSARY:
- bpm: use exactly as Ableton project tempo
- grooveAmount near 0.0 = fully quantised, straight grid
- kickSwing > hihatSwing = kick has more timing push than hats
- kickAccent[16] = kick energy per 16th position, high variance = 
  dynamic pattern, low variance = four-on-the-floor
- lufsIntegrated: club electronic target is -6 to -9 LUFS
- truePeak above 0.0 dBTP = intersample clipping present
- crestFactor: higher = more transient punch, lower = more limited
- stereoWidth near 0.0 = effectively mono
- subBassMono: true = sub below 80Hz is mono, standard club mastering
- spectralCentroid: higher = brighter tonality
- segmentSpectral centroid rising across segments = filter opening
- oddToEvenRatio above 1.0 = saw/square character
- oddToEvenRatio below 1.0 = sine/triangle character  
- inharmonicity above 0.2 = FM or noise synthesis character
- logAttackTime more negative = faster attack transients
- attackTimeStdDev low = consistent mechanical transients
- structure.segments = arrangement blocks, plus or minus 5-10s
- segmentLoudness = per-section LUFS, reveals drops and builds
- dominantNotes = MIDI numbers, convert to note names
- transcriptionDetail (when present):
  - noteCount: total polyphonic notes detected
  - averageConfidence: mean note confidence 0-1
  - dominantPitches[]: top pitches with count
  - pitchRange: min/max MIDI and note names
  - stemSeparationUsed: true if Demucs was used
  - stemsTranscribed: which stems were analysed
  - notes[].stemSource: "bass"|"other"|"full_mix"
  - When stemSeparationUsed is true, bass notes and melodic notes are separated by stemSource
  - Prefer transcriptionDetail over melodyDetail for harmonic and melodic reconstruction advice when transcriptionDetail is present
- pumpingStrength + pumpingConfidence both above 0.35 = sidechain
- arrangementDetail.noveltyPeaks = structural event timestamps
- segmentSpectral.stereoWidth changes = intentional width automation

IMPORTANT SPECTRAL NOTE:
- spectralBalance dB values describe spectral shape relative 
  to each other only, not absolute loudness or quality
- Do not use spectralBalance values to make qualitative 
  judgements about the track's perceived sound or production 
  quality
- High subBass dB does not mean "good bass" — it means 
  the spectral energy is concentrated there relative to 
  other bands
- Use spectralBalance only to inform EQ and filter 
  recommendations, not character descriptions

GENRE INFERENCE AND ADAPTATION:
- Infer the most likely genre from the combined evidence of 
  bpm, synthesisCharacter (especially inharmonicity and 
  oddToEvenRatio), crestFactor, spectral profile, grooveDetail, 
  and any available melodic or harmonic data.
- State the inferred genre explicitly at the very start of 
  trackCharacter, including a confidence indicator in plain 
  language and the specific measurements that support the inference.
- Use the inferred genre to choose device types, production 
  techniques, terminology, and secretSauce framing. Derive 
  those conventions from the inferred genre, not from a fixed 
  list of hard-coded genre assumptions.
- If the DSP signature is ambiguous across genres, say so 
  explicitly in trackCharacter and explain which measured 
  characteristics point in different directions rather than guessing.

OUTPUT REQUIREMENTS — QUANTITY AND DEPTH ARE MANDATORY:

trackCharacter:
Write 4-5 sentences. Reference at least 4 specific numeric values 
from the JSON. The opening sentence must name the inferred genre 
and confidence. The next sentence(s) must justify that inference 
with specific measurements. Describe synthesis character, dynamic 
approach, stereo philosophy, and spectral signature. Be specific 
and production-focused, not generic.

detectedCharacteristics:
Return exactly 5 items. Each must reference a specific measured 
value. Confidence must be HIGH, MED, or LOW exactly.
Cover: loudness/dynamics, stereo field, spectral character, 
synthesis approach, rhythmic/groove characteristic.

arrangementOverview:
Return a structured object with three keys:
- summary: 2-3 sentence overview of the track's structural 
  philosophy referencing durationSeconds and overall 
  loudness approach
- segments: an array with one entry per segment in 
  structure.segments. For each segment include:
    index: segment number starting at 1
    startTime: start time in seconds from structure.segments
    endTime: end time in seconds from structure.segments
    lufs: LUFS value from segmentLoudness for this segment
    description: 3-4 sentences covering what is happening 
      musically and production-wise in this section, 
      referencing the segment's measured values
    spectralNote: one sentence on spectralCentroid or 
      stereoWidth change from segmentSpectral if available
- noveltyNotes: one paragraph mapping each noveltyPeak 
  timestamp to the structural event it represents

sonicElements:
Return ALL of the following keys with substantive content.
Each must be at minimum 4 sentences with specific values referenced:
- kick: reference crestFactor, kickAccent pattern, spectralBalance 
  subBass and lowBass, logAttackTime. Name specific Ableton devices 
  with parameter values.
- bass: reference synthesisCharacter oddToEvenRatio and 
  inharmonicity, subBassMono, spectralBalance subBass/lowBass. 
  Select synth architecture from inharmonicity:
  - 0.1-0.25 = FM / Operator
  - below 0.1 = subtractive / Analog
  - above 0.25 = wavetable or noise / Wavetable plus noise oscillator
  Explain why that instrument choice fits the measured synthesis 
  character of THIS track using inharmonicity and oddToEvenRatio. 
  Suggest oscillator type, filter settings, and mono routing.
- melodicArp: convert dominantNotes MIDI to note names. Reference 
  pitchConfidence explicitly — if below 0.15 say so. Reference 
  chordDetail.dominantChords. Suggest synth approach and MIDI pattern.
- grooveAndTiming: reference grooveAmount, kickSwing, hihatSwing 
  with specific ms offset calculations at the track BPM. Suggest 
  Ableton groove pool settings.
- effectsAndTexture: reference effectsDetail, vibratoPresent, 
  arrangementDetail noveltyPeaks. Use audio perception here for 
  qualitative texture. Reference spectralContrast values.
- widthAndStereo: reference stereoWidth, stereoCorrelation, 
  subBassMono, segmentSpectral stereoWidth changes across segments. 
  Suggest Utility device settings and any width automation.
- harmonicContent: reference key, keyConfidence, segmentKey changes, 
  chordDetail.dominantChords, chordStrength. Suggest scale/mode 
  for writing new parts.

mixAndMasterChain:
Return an array of device objects in signal flow order.
Return a minimum of 8 devices covering the full signal chain from sound design through to the master bus.
Cover all three frequency ranges with at least one device per range:
- Low end: sub bass, kick, or bass processing
- Mid range: main body, saturation, compression, or harmonic shaping
- High end: air, presence, transient detail, or top-end polish
Where applicable to the track, the chain must explicitly cover:
- transient shaping or drum processing
- bass/sub management
- mid-range saturation or harmonic excitation
- stereo width control
- high-frequency air or presence
- bus compression or glue
- limiting/mastering
At least one device entry must embody a technique native to the 
inferred genre and must justify that technique using both the 
genre inference and the measured DSP values for this track.
Each object must include:
- order: position in chain starting at 1
- device: exact Ableton Live 12 device name
- parameter: specific parameter name as shown in Ableton
- value: specific numeric or descriptive target value 
  derived from JSON measurements
- reason: one sentence referencing the specific measured 
  value that justifies this device and setting
Never return fewer than 8 devices.

secretSauce:
Title: a specific named technique that is native to the inferred 
genre and the measured characteristics of this track. Generic 
production-technique titles are not acceptable.
icon: one word describing the core technique type. 
Must be exactly one of: DISTORTION, FILTER, COMPRESSION, 
MODULATION, ROUTING, SATURATION, STEREO, SYNTHESIS
Explanation: 4-5 sentences explaining what makes this technique 
specific to THIS track based on its measurements. It must also 
state why this technique is native to the inferred genre. Reference 
at least 3 specific JSON values.
implementationSteps: return exactly 6 steps. Each step must be 
a complete sentence with specific Ableton device names, parameter 
names, and numeric values. Steps must build on each other 
sequentially.

confidenceNotes:
Return at least 5 items. 
For the field name, use a human-readable label, NOT the JSON 
field name. For example:
- use "Key Signature" not "key"
- use "True Peak" not "truePeak"  
- use "Chord Progression" not "chordDetail.chordStrength"
- use "Melody Transcription" not "melodyDetail.pitchConfidence"
- use "Sidechain Detection" not "sidechainDetail.pumpingConfidence"
- use "Segment Key (short segment)" not "segmentKey[1]"
Every field that has a known accuracy limitation must appear here.

abletonRecommendations:
Return at least 10 device recommendation cards.
Cover the full signal chain: sound design devices, effects, 
group processing, and mastering.
For each card:
- device: exact Ableton Live 12 device name
- category: one of SYNTHESIS, DYNAMICS, EQ, EFFECTS, 
  STEREO, MASTERING, MIDI, ROUTING
- parameter: specific parameter name as it appears in Ableton
- value: specific numeric or descriptive target value derived 
  from JSON measurements
- reason: one sentence referencing the specific measured value 
  that justifies this recommendation
- advancedTip: one concrete advanced technique for this device 
  in this context

Do not pad with generic advice. Every recommendation must be 
justified by a specific measurement from the JSON.

Phase 1 Measurements:
${JSON.stringify(phase1Result, null, 2)}`;

  if (file.size <= INLINE_SIZE_LIMIT) {
    const base64Audio = await fileToBase64(file);
    const mimeType = file.type || (file.name.toLowerCase().endsWith('.flac') ? 'audio/flac' : file.name.toLowerCase().endsWith('.wav') ? 'audio/wav' : 'audio/mpeg');
    const phase2StartTime = Date.now();
    const phase2Response = await generatePhase2Response(ai, modelName, phase2Prompt, {
      inlineData: {
        data: base64Audio,
        mimeType,
      },
    });
    const phase2EndTime = Date.now();

    return buildPhase2Result({
      modelName,
      phase2Prompt,
      phase2Response,
      audioMetadata,
      durationMs: phase2EndTime - phase2StartTime,
      message: "Phase 2 advisory complete.",
    });
  }

  const uploadStartTime = Date.now();
  const uploadedFile = await withRetry(
    () =>
      ai.files.upload({
        file,
        config: {
          mimeType: file.type || (file.name.toLowerCase().endsWith('.flac') ? 'audio/flac' : file.name.toLowerCase().endsWith('.wav') ? 'audio/wav' : 'audio/mpeg'),
          displayName: file.name,
        },
      }),
    3,
    2_000,
  );

  let phase2Response;
  const phase2StartTime = Date.now();
  try {
    phase2Response = await generatePhase2Response(ai, modelName, phase2Prompt, {
      fileData: {
        fileUri: uploadedFile.uri,
        mimeType: uploadedFile.mimeType,
      },
    });
  } finally {
    try {
      await ai.files.delete({ name: uploadedFile.name });
    } catch {
      // Files auto-expire; cleanup failures should not fail the analysis.
    }
  }
  const phase2EndTime = Date.now();

  const uploadMs = phase2StartTime - uploadStartTime;
  const generateMs = phase2EndTime - phase2StartTime;

  return buildPhase2Result({
    modelName,
    phase2Prompt,
    phase2Response,
    audioMetadata,
    durationMs: phase2EndTime - uploadStartTime,
    message: `Phase 2 advisory complete. Upload: ${uploadMs}ms, Generate: ${generateMs}ms`,
  });
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      if (typeof reader.result !== "string") {
        reject(new Error("Failed to read file as base64."));
        return;
      }
      const base64 = reader.result.split(",")[1];
      resolve(base64);
    };
    reader.onerror = (error) => reject(error);
  });
}

function formatError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

function generatePhase2Response(
  ai: GoogleGenAI,
  modelName: string,
  phase2Prompt: string,
  mediaPart: Record<string, unknown>,
) {
  return withRetry(
    () =>
      ai.models.generateContent({
        model: modelName,
        contents: [
          {
            parts: [
              mediaPart,
              { text: phase2Prompt },
            ],
          },
        ],
        config: {
          responseMimeType: "application/json",
          responseSchema: {
            type: Type.OBJECT,
            properties: {
              trackCharacter: { type: Type.STRING },
              detectedCharacteristics: {
                type: Type.ARRAY,
                items: {
                  type: Type.OBJECT,
                  properties: {
                    name: { type: Type.STRING },
                    confidence: { type: Type.STRING },
                    explanation: { type: Type.STRING },
                  },
                  required: ["name", "confidence", "explanation"],
                },
              },
              arrangementOverview: {
                type: SchemaType.OBJECT,
                properties: {
                  summary: { type: SchemaType.STRING },
                  segments: {
                    type: SchemaType.ARRAY,
                    items: {
                      type: SchemaType.OBJECT,
                      properties: {
                        index: { type: SchemaType.NUMBER },
                        startTime: { type: SchemaType.NUMBER },
                        endTime: { type: SchemaType.NUMBER },
                        lufs: { type: SchemaType.NUMBER },
                        description: { type: SchemaType.STRING },
                        spectralNote: { type: SchemaType.STRING },
                      },
                      required: ["index", "startTime", "endTime", "description"],
                    },
                  },
                  noveltyNotes: { type: SchemaType.STRING },
                },
                required: ["summary", "segments"],
              },
              sonicElements: {
                type: Type.OBJECT,
                properties: {
                  kick: { type: Type.STRING },
                  bass: { type: Type.STRING },
                  melodicArp: { type: Type.STRING },
                  grooveAndTiming: { type: Type.STRING },
                  effectsAndTexture: { type: Type.STRING },
                  widthAndStereo: { type: SchemaType.STRING },
                  harmonicContent: { type: SchemaType.STRING },
                },
                required: ["kick", "bass", "melodicArp", "grooveAndTiming", "effectsAndTexture"],
              },
              mixAndMasterChain: {
                type: SchemaType.ARRAY,
                items: {
                  type: SchemaType.OBJECT,
                  properties: {
                    order: { type: SchemaType.NUMBER },
                    device: { type: SchemaType.STRING },
                    parameter: { type: SchemaType.STRING },
                    value: { type: SchemaType.STRING },
                    reason: { type: SchemaType.STRING },
                  },
                  required: ["order", "device", "parameter", "value", "reason"],
                },
              },
              secretSauce: {
                type: Type.OBJECT,
                properties: {
                  title: { type: Type.STRING },
                  icon: { type: SchemaType.STRING },
                  explanation: { type: Type.STRING },
                  implementationSteps: { type: Type.ARRAY, items: { type: Type.STRING } },
                },
                required: ["title", "explanation", "implementationSteps"],
              },
              confidenceNotes: {
                type: Type.ARRAY,
                items: {
                  type: Type.OBJECT,
                  properties: {
                    field: { type: Type.STRING },
                    value: { type: Type.STRING },
                    reason: { type: Type.STRING },
                  },
                  required: ["field", "value", "reason"],
                },
              },
              abletonRecommendations: {
                type: Type.ARRAY,
                items: {
                  type: Type.OBJECT,
                  properties: {
                    device: { type: Type.STRING },
                    category: { type: Type.STRING },
                    parameter: { type: Type.STRING },
                    value: { type: Type.STRING },
                    reason: { type: Type.STRING },
                    advancedTip: { type: Type.STRING },
                  },
                  required: ["device", "category", "parameter", "value", "reason"],
                },
              },
            },
            required: [
              "trackCharacter",
              "detectedCharacteristics",
              "arrangementOverview",
              "sonicElements",
              "mixAndMasterChain",
              "secretSauce",
              "confidenceNotes",
              "abletonRecommendations",
            ],
          },
        },
      }),
    3,
    2_000,
  );
}

function buildPhase2Result({
  modelName,
  phase2Prompt,
  phase2Response,
  audioMetadata,
  durationMs,
  message,
}: {
  modelName: string;
  phase2Prompt: string;
  phase2Response: { text?: string };
  audioMetadata: DiagnosticLogEntry["audioMetadata"];
  durationMs: number;
  message: string;
}): AnalyzePhase2Result {
  const result = JSON.parse(phase2Response.text || "{}") as Phase2Result;
  const log: DiagnosticLogEntry = {
    model: modelName,
    phase: PHASE2_LABEL,
    promptLength: phase2Prompt.length,
    responseLength: phase2Response.text?.length || 0,
    durationMs,
    audioMetadata,
    timestamp: new Date().toISOString(),
    source: "gemini",
    status: "success",
    message,
  };

  return {
    result,
    log,
  };
}

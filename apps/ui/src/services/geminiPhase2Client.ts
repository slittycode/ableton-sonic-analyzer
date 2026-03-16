import { GoogleGenAI, Type, Type as SchemaType } from "@google/genai";
import { appConfig, isGeminiPhase2Available } from "../config";
import { DiagnosticLogEntry, Phase1Result, Phase2Result } from "../types";
import { getAudioMimeTypeOrDefault } from "./audioFile";
import { createUserCancelledError } from "./backendPhase1Client";
import { PHASE2_LABEL, PHASE2_SKIPPED_LABEL } from "./phaseLabels";

const INLINE_SIZE_LIMIT = 20_971_520;

interface AnalyzePhase2Args {
  file: File;
  modelName: string;
  phase1Result: Phase1Result;
  audioMetadata: DiagnosticLogEntry["audioMetadata"];
  signal?: AbortSignal;
}

interface AnalyzePhase2Result {
  result: Phase2Result | null;
  log: DiagnosticLogEntry;
}

interface RetryLoggingHooks {
  onAttempt?: (attempt: number, maxRetries: number) => void;
  onRetryableFailure?: (
    attempt: number,
    maxRetries: number,
    errorMessage: string,
    delayMs: number,
  ) => void;
  onExhausted?: (maxRetries: number, errorMessage: string) => void;
}

async function withRetry<T>(
  operation: () => Promise<T>,
  maxRetries = 3,
  baseDelayMs = 2_000,
  loggingHooks?: RetryLoggingHooks,
  signal?: AbortSignal,
): Promise<T> {
  let attempt = 0;
  while (attempt < maxRetries) {
    throwIfUserCancelled(signal);
    const currentAttempt = attempt + 1;
    loggingHooks?.onAttempt?.(currentAttempt, maxRetries);
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
        if (isRetryable && attempt >= maxRetries) {
          loggingHooks?.onExhausted?.(maxRetries, errorMessage);
        }
        throw error;
      }

      const delay = baseDelayMs * Math.pow(2, attempt - 1) + Math.random() * 1_000;
      loggingHooks?.onRetryableFailure?.(attempt, maxRetries, errorMessage, Math.round(delay));
      await waitForRetryDelay(delay, signal);
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
  signal,
}: AnalyzePhase2Args): Promise<AnalyzePhase2Result> {
  if (!canRunGeminiPhase2()) {
    throw new Error("Gemini phase-2 is disabled or missing VITE_GEMINI_API_KEY.");
  }

  throwIfUserCancelled(signal);

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
4. If audio perception contradicts a measured JSON field, keep the JSON measurement and describe the contradiction rather than rewriting the number.
5. Low confidence handling:
   - pitchConfidence below 0.15 = melody is draft only
   - chordStrength below 0.70 = chords approximate
   - pumpingConfidence below 0.40 = do not assert sidechain
   - segmentKey from segments shorter than 10s = low confidence
6. When transcriptionDetail is present, use dominantPitches for note name recommendations, not melodyDetail.dominantNotes.
7. stemSeparationUsed: true means bass and melodic content have been transcribed independently - treat bass stem notes and other stem notes as separate layers.
8. For measured values, the JSON is authoritative. For genre identification only, audio perception is authoritative.
9. mixAndMasterChain must contain a minimum of 8 device objects. If fewer than 8 real devices can be inferred from the audio, supplement with contextually appropriate Ableton Live devices that would suit the detected characteristics. Never return fewer than 8.

FIELD GLOSSARY:
- bpm: use exactly as Ableton project tempo
- grooveDetail.kickSwing: timing variance in kick band — higher = more swing
- grooveDetail.hihatSwing: timing variance in high band — higher = more loose feel
- grooveDetail.kickAccent: 16-value array of kick energy per 16th note position
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
Compute kickAccentVariance as the variance of grooveDetail.kickAccent (the 16-value array) and use the DSP values below as context rather than as the genre label itself.

RHYTHM CLUSTER (from DSP measurements — use as context, not as genre):
  - kickSwing < 0.15 AND kickAccentVariance < 0.15 → tight mechanical pulse
  - kickSwing > 0.50 AND kickAccentVariance < 0.10 → loose psychedelic pulse
  - kickSwing < 0.12 AND kickAccentVariance < 0.05 → minimal/no pulse
  - kickAccentVariance > 0.28 → complex broken pattern
  - otherwise → ambiguous rhythm profile

SYNTHESIS TIER (from synthesisCharacter — use to confirm genre, not define it):
  - inharmonicity 0.10-0.25 → FM/acid character
  - inharmonicity < 0.10 → subtractive/clean character
  - inharmonicity > 0.25 → wavetable/noise/complex character
  - oddToEvenRatio > 1.5 → saw/square dominant
  - oddToEvenRatio < 0.8 → sine/triangle dominant

GENRE INFERENCE PROCESS:
  1. State the rhythm cluster and synthesis tier from the JSON above.
  2. Listen to the audio and identify the genre from audio perception.
  3. Cross-check: does the audio genre match the rhythm cluster and synthesis tier? If yes, HIGH confidence. If partially, MED confidence with explanation. If the audio clearly contradicts the DSP, state the contradiction explicitly — the DSP measurement may be capturing something the audio does not, or vice versa.
  4. Never override the measured DSP values with audio perception. Only use audio perception for the genre label itself.

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
- kick: Derive the kick recommendation directly from kickAccentVariance and kickSwing:
  - kickAccentVariance < 0.15 AND kickSwing < 0.06 → four-on-the-floor → Kick 2, short decay, 909/808
  - kickAccentVariance > 0.25 → complex pattern → Sampler, layered kicks
  - kickAccentVariance 0.15–0.25 → moderate variation → Drum Rack, mixed approach
  Also reference crestFactor, logAttackTime, and spectralBalance subBass with specific values.
- bass: reference synthesisCharacter oddToEvenRatio and 
  inharmonicity, subBassMono, spectralBalance subBass/lowBass. 
  Select synth architecture from inharmonicity:
  - 0.1-0.25 = FM / Operator
  - below 0.1 = subtractive / Analog
  - above 0.25 = wavetable or noise / Wavetable plus noise oscillator
  Apply this rule regardless of the genre label inferred in trackCharacter.
  The measured inharmonicity is ground truth.
  Explain why that instrument choice fits the measured synthesis
  character of THIS track using inharmonicity and oddToEvenRatio.
  Suggest oscillator type, filter settings, and mono routing.
- melodicArp: convert dominantNotes MIDI to note names. Reference 
  pitchConfidence explicitly — if below 0.15 say so. Reference 
  chordDetail.dominantChords. Suggest synth approach and MIDI pattern.
- grooveAndTiming: reference grooveDetail.kickSwing, grooveDetail.hihatSwing,
  and grooveDetail.kickAccent with specific ms offset calculations at the track BPM.
  Suggest Ableton groove pool settings.
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
At least one device entry must embody a technique justified by measured
synthesisCharacter, grooveDetail, or sidechainDetail values — not by genre
label alone. If genre confidence is LOW or MED, provide a measurement-based
justification regardless of genre name.
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
Title: a specific named technique derived from the dominant measured characteristic
of this track — the single most distinctive DSP feature. State which genre(s)
commonly apply this technique, but derive the technique from the measurement,
not from the genre label. Generic production-technique titles are not acceptable.
icon: one word describing the core technique type.
Must be exactly one of: DISTORTION, FILTER, COMPRESSION,
MODULATION, ROUTING, SATURATION, STEREO, SYNTHESIS
Explanation: 4-5 sentences explaining what makes this technique
specific to THIS track based on its measurements. Cite at least 3 specific JSON
values that make this technique appropriate for this track. Then name the genre(s)
where this technique is common. If genre confidence is LOW or MED, acknowledge
that the technique is measurement-driven, not genre-confirmed.
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
Always include:
- Rhythm cluster: which bucket and why
- Synthesis tier: which tier and the specific inharmonicity + oddToEvenRatio values
- Genre confidence: HIGH/MED/LOW with specific reason for any degradation

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
  const resolvedMimeType = getAudioMimeTypeOrDefault(file);

  if (file.size <= INLINE_SIZE_LIMIT) {
    const base64Audio = await fileToBase64(file);
    throwIfUserCancelled(signal);
    const phase2StartTime = Date.now();
    const phase2Response = await generatePhase2Response(ai, modelName, phase2Prompt, {
      inlineData: {
        data: base64Audio,
        mimeType: resolvedMimeType,
      },
    }, signal);
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
          mimeType: resolvedMimeType,
          displayName: file.name,
        },
      }),
    3,
    2_000,
    {
      onAttempt: (attempt, maxRetries) => {
        console.warn(`[Phase2] Upload attempt ${attempt} of ${maxRetries}...`);
      },
      onRetryableFailure: (attempt, _maxRetries, errorMessage, delayMs) => {
        console.warn(
          `[Phase2] Upload attempt ${attempt} failed (${errorMessage}), retrying in ${delayMs}ms...`,
        );
      },
      onExhausted: (maxRetries, errorMessage) => {
        console.warn(
          `[Phase2] Upload attempts exhausted after ${maxRetries} tries (${errorMessage}).`,
        );
      },
    },
    signal,
  );

  let phase2Response;
  const phase2StartTime = Date.now();
  let phase2EndTime = phase2StartTime;
  try {
    throwIfUserCancelled(signal);
    phase2Response = await generatePhase2Response(ai, modelName, phase2Prompt, {
      fileData: {
        fileUri: uploadedFile.uri,
        mimeType: uploadedFile.mimeType,
      },
    }, signal);
    phase2EndTime = Date.now();
  } finally {
    try {
      await ai.files.delete({ name: uploadedFile.name });
    } catch {
      // Files auto-expire; cleanup failures should not fail the analysis.
    }
  }

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

function throwIfUserCancelled(signal?: AbortSignal) {
  if (signal?.aborted) {
    throw createUserCancelledError();
  }
}

function waitForRetryDelay(delayMs: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(createUserCancelledError());
      return;
    }

    let settled = false;
    const timeoutId = setTimeout(() => {
      settled = true;
      if (signal && abortHandler) {
        signal.removeEventListener("abort", abortHandler);
      }
      resolve();
    }, delayMs);

    const abortHandler = () => {
      if (settled) return;
      clearTimeout(timeoutId);
      if (signal) {
        signal.removeEventListener("abort", abortHandler);
      }
      reject(createUserCancelledError());
    };

    signal?.addEventListener("abort", abortHandler, { once: true });
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
  signal?: AbortSignal,
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
    undefined,
    signal,
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
  const parsed = parsePhase2Result(phase2Response.text);

  if (parsed.skipMessage) {
    return {
      result: null,
      log: {
        model: modelName,
        phase: PHASE2_SKIPPED_LABEL,
        promptLength: phase2Prompt.length,
        responseLength: phase2Response.text?.length || 0,
        durationMs,
        audioMetadata,
        timestamp: new Date().toISOString(),
        source: "gemini",
        status: "skipped",
        message: parsed.skipMessage,
      },
    };
  }

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
    result: parsed.result,
    log,
  };
}

function parsePhase2Result(responseText: string | undefined): {
  result: Phase2Result | null;
  skipMessage?: string;
} {
  const rawText = responseText?.trim();

  if (!rawText) {
    return {
      result: null,
      skipMessage: "Phase 2 advisory skipped because Gemini returned an empty response.",
    };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(rawText);
  } catch {
    return {
      result: null,
      skipMessage: "Phase 2 advisory skipped because Gemini returned invalid JSON.",
    };
  }

  if (!isPhase2Result(parsed)) {
    return {
      result: null,
      skipMessage: "Phase 2 advisory skipped because Gemini returned an invalid response shape.",
    };
  }

  return { result: parsed };
}

function isPhase2Result(value: unknown): value is Phase2Result {
  const record = asRecord(value);
  if (!record) return false;

  return (
    isString(record.trackCharacter) &&
    isDetectedCharacteristics(record.detectedCharacteristics) &&
    isArrangementOverview(record.arrangementOverview) &&
    isSonicElements(record.sonicElements) &&
    isMixAndMasterChain(record.mixAndMasterChain) &&
    isSecretSauce(record.secretSauce) &&
    isConfidenceNotes(record.confidenceNotes) &&
    isAbletonRecommendations(record.abletonRecommendations)
  );
}

function isDetectedCharacteristics(value: unknown): boolean {
  return (
    Array.isArray(value) &&
    value.every((item) => {
      const record = asRecord(item);
      return (
        !!record &&
        isString(record.name) &&
        isString(record.explanation) &&
        (record.confidence === "HIGH" || record.confidence === "MED" || record.confidence === "LOW")
      );
    })
  );
}

function isArrangementOverview(value: unknown): boolean {
  const record = asRecord(value);
  if (!record || !isString(record.summary) || !Array.isArray(record.segments)) return false;

  const segmentsAreValid = record.segments.every((segment) => {
    const entry = asRecord(segment);
    return (
      !!entry &&
      isNumber(entry.index) &&
      isNumber(entry.startTime) &&
      isNumber(entry.endTime) &&
      isString(entry.description) &&
      isOptionalNumber(entry.lufs) &&
      isOptionalString(entry.spectralNote)
    );
  });

  return segmentsAreValid && isOptionalString(record.noveltyNotes);
}

function isSonicElements(value: unknown): boolean {
  const record = asRecord(value);
  return (
    !!record &&
    isString(record.kick) &&
    isString(record.bass) &&
    isString(record.melodicArp) &&
    isString(record.grooveAndTiming) &&
    isString(record.effectsAndTexture) &&
    isOptionalString(record.widthAndStereo) &&
    isOptionalString(record.harmonicContent)
  );
}

function isMixAndMasterChain(value: unknown): boolean {
  return (
    Array.isArray(value) &&
    value.every((item) => {
      const record = asRecord(item);
      return (
        !!record &&
        isNumber(record.order) &&
        isString(record.device) &&
        isString(record.parameter) &&
        isString(record.value) &&
        isString(record.reason)
      );
    })
  );
}

function isSecretSauce(value: unknown): boolean {
  const record = asRecord(value);
  return (
    !!record &&
    isString(record.title) &&
    isOptionalString(record.icon) &&
    isString(record.explanation) &&
    isStringArray(record.implementationSteps)
  );
}

function isConfidenceNotes(value: unknown): boolean {
  return (
    Array.isArray(value) &&
    value.every((item) => {
      const record = asRecord(item);
      return !!record && isString(record.field) && isString(record.value) && isString(record.reason);
    })
  );
}

function isAbletonRecommendations(value: unknown): boolean {
  return (
    Array.isArray(value) &&
    value.every((item) => {
      const record = asRecord(item);
      return (
        !!record &&
        isString(record.device) &&
        isString(record.category) &&
        isString(record.parameter) &&
        isString(record.value) &&
        isString(record.reason) &&
        isOptionalString(record.advancedTip)
      );
    })
  );
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isOptionalString(value: unknown): boolean {
  return value === undefined || isString(value);
}

function isOptionalNumber(value: unknown): boolean {
  return value === undefined || isNumber(value);
}

function isStringArray(value: unknown): boolean {
  return Array.isArray(value) && value.every((item) => isString(item));
}

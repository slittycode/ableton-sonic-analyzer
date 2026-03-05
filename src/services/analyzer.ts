import { GoogleGenAI, Type } from "@google/genai";
import { Phase1Result, Phase2Result, DiagnosticLogEntry } from "../types";

const ai = new GoogleGenAI({ 
  apiKey: process.env.GEMINI_API_KEY,
  httpOptions: {
    timeout: 5 * 60 * 1000, // 5 minutes timeout for large audio files
  }
});

async function withRetry<T>(
  operation: () => Promise<T>,
  maxRetries: number = 3,
  baseDelayMs: number = 2000
): Promise<T> {
  let attempt = 0;
  while (attempt < maxRetries) {
    try {
      return await operation();
    } catch (error: any) {
      attempt++;
      const errorMessage = error?.message || String(error);
      const isRetryable = 
        errorMessage.includes("503") || 
        errorMessage.includes("high demand") || 
        errorMessage.includes("429") || 
        errorMessage.includes("quota") ||
        errorMessage.includes("UNAVAILABLE");
      
      if (!isRetryable || attempt >= maxRetries) {
        throw error;
      }
      
      // Exponential backoff with jitter
      const delay = baseDelayMs * Math.pow(2, attempt - 1) + Math.random() * 1000;
      console.warn(`API high demand/rate limit (attempt ${attempt}/${maxRetries}). Retrying in ${Math.round(delay)}ms...`, errorMessage);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
  throw new Error("Max retries reached");
}

export async function analyzeAudio(
  file: File,
  modelName: string,
  dspJson: string | null,
  onPhase1Complete: (result: Phase1Result, log: DiagnosticLogEntry) => void,
  onPhase2Complete: (result: Phase2Result, log: DiagnosticLogEntry) => void,
  onError: (error: Error) => void
) {
  try {
    const base64Audio = await fileToBase64(file);
    const mimeType = file.type || "audio/mp3";
    
    const audioMetadata = {
      name: file.name,
      size: file.size,
      type: mimeType,
    };

    // Phase 1
    const phase1Prompt = `You are a sonic analysis engine for Ableton Live 12 producers. You operate in three distinct phases. Always return valid JSON only — no preamble, no markdown, no explanation outside the JSON structure.

PHASE 1 — DSP Measurement (audio required)
Listen to the audio and extract only hard, measurable data. Do not interpret, classify genre, or make aesthetic judgements. Return:
{
  "bpm": number,
  "bpmConfidence": number (0-1),
  "key": string or null,
  "keyConfidence": number (0-1),
  "timeSignature": string,
  "durationSeconds": number,
  "lufsIntegrated": number,
  "truePeak": number,
  "stereoWidth": number (0-1),
  "stereoCorrelation": number (-1 to 1),
  "spectralBalance": {
    "subBass": number (dB),
    "lowBass": number (dB),
    "mids": number (dB),
    "upperMids": number (dB),
    "highs": number (dB),
    "brilliance": number (dB)
  }
}`;

    const phase1Parts: any[] = [];
    
    if (dspJson) {
      phase1Parts.push({
        text: `Here is the DSP analysis JSON for this track:\n${dspJson}\n\nPlease analyse the uploaded audio using these measurements as ground truth.`
      });
    }

    phase1Parts.push({
      inlineData: {
        data: base64Audio,
        mimeType: mimeType,
      },
    });

    phase1Parts.push({ text: phase1Prompt });

    const phase1StartTime = Date.now();
    const phase1Response = await withRetry(() => ai.models.generateContent({
      model: modelName,
      contents: [
        {
          parts: phase1Parts,
        },
      ],
      config: {
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            bpm: { type: Type.NUMBER, description: "Estimated BPM" },
            bpmConfidence: { type: Type.NUMBER, description: "Confidence score for BPM (0-1)" },
            key: { type: Type.STRING, description: "Estimated musical key", nullable: true },
            keyConfidence: { type: Type.NUMBER, description: "Confidence score for key (0-1)" },
            timeSignature: { type: Type.STRING, description: "Estimated time signature" },
            durationSeconds: { type: Type.NUMBER, description: "Duration in seconds" },
            lufsIntegrated: { type: Type.NUMBER, description: "Integrated LUFS" },
            truePeak: { type: Type.NUMBER, description: "True Peak in dB" },
            stereoWidth: { type: Type.NUMBER, description: "Stereo width (0-1)" },
            stereoCorrelation: { type: Type.NUMBER, description: "Stereo correlation (-1 to 1)" },
            spectralBalance: {
              type: Type.OBJECT,
              properties: {
                subBass: { type: Type.NUMBER, description: "Sub bass in dB" },
                lowBass: { type: Type.NUMBER, description: "Low bass in dB" },
                mids: { type: Type.NUMBER, description: "Mids in dB" },
                upperMids: { type: Type.NUMBER, description: "Upper mids in dB" },
                highs: { type: Type.NUMBER, description: "Highs in dB" },
                brilliance: { type: Type.NUMBER, description: "Brilliance in dB" },
              },
              required: ["subBass", "lowBass", "mids", "upperMids", "highs", "brilliance"],
            }
          },
          required: ["bpm", "bpmConfidence", "key", "keyConfidence", "timeSignature", "durationSeconds", "lufsIntegrated", "truePeak", "stereoWidth", "stereoCorrelation", "spectralBalance"],
        },
      },
    }));
    const phase1EndTime = Date.now();
    
    const phase1Result: Phase1Result = JSON.parse(phase1Response.text || "{}");
    
    const phase1Log: DiagnosticLogEntry = {
      model: modelName,
      phase: "Phase 1: Foundational Metadata",
      promptLength: phase1Prompt.length,
      responseLength: phase1Response.text?.length || 0,
      durationMs: phase1EndTime - phase1StartTime,
      audioMetadata,
      timestamp: new Date().toISOString(),
    };
    
    onPhase1Complete(phase1Result, phase1Log);

    // Phase 2
    const phase2Prompt = `You are an expert Ableton Live 12 producer and sound designer specialising in electronic music reconstruction. You receive two inputs simultaneously:

1. A structured JSON object containing deterministic DSP measurements from a local Essentia analysis engine
2. The audio file itself

Your job is to combine ground truth measurements from the JSON with qualitative audio perception to produce specific, actionable Ableton Live 12 reconstruction advice.

---

ABSOLUTE RULES — THESE OVERRIDE EVERYTHING ELSE:

1. Every numeric value in the JSON is a measurement from a deterministic DSP engine. It is ground truth. Do not re-estimate or override any numeric field using audio inference.

2. You are PROHIBITED from overriding these fields with audio perception:
   - bpm (use exact value, do not detect tempo from audio)
   - key (use exact string, do not reinterpret or override)
   - lufsIntegrated, lufsRange, truePeak
   - stereoDetail values including subBassMono
   - durationSeconds, sampleRate

3. The key field is produced by Essentia's Temperley profile KeyExtractor. Display and use the exact key string as provided. Do not reinterpret it as its relative major or minor. Do not override it based on what you hear.

4. If your audio perception contradicts a JSON value, the JSON is correct. Do not mention the discrepancy. Do not hedge.

5. bpmAgreement: true means two independent algorithms agree on tempo. This is high confidence. Do not question it.

6. Fields with low confidence scores should be treated as approximate hints, not facts. Specifically:
   - melodyDetail.pitchConfidence below 0.15 = treat melody as draft only, do not over-interpret note sequence
   - chordDetail.chordStrength below 0.70 = treat chord progression as approximate, cross-reference with key and dominantNotes
   - sidechainDetail.pumpingConfidence below 0.40 = do not confidently assert sidechain compression is present
   - segmentKey entries from segments shorter than 10 seconds = treat as low confidence regardless of keyConfidence value
   - arrangementDetail noveltyPeaks = timestamps are approximate, within ±2 seconds

7. Your role is to INTERPRET measurements and generate Ableton reconstruction advice FROM them. You are a music producer reading a precision spec sheet, not an audio analyser.

---

FIELD GLOSSARY — HOW TO INTERPRET KEY VALUES:

TEMPO AND RHYTHM:
- bpm: project tempo for Ableton, use exactly
- grooveAmount near 0.0 = fully quantised, use straight grid
- kickSwing vs hihatSwing: if kickSwing > hihatSwing, kick has more timing push than hi-hats — suggest separate groove pools
- kickAccent array: 16 values showing kick energy per beat position — high variance = dynamic pattern, low variance = four-on-the-floor

LOUDNESS:
- lufsIntegrated: target for electronic club music is -6 to -9 LUFS
- truePeak above 0.0 dBTP = intersample clipping likely
- crestFactor: higher = more transient punch, lower = more limited
- lufsRange (LRA): low values (below 3 LU) = heavily compressed or automated

STEREO:
- stereoWidth near 0.0 = effectively mono full mix
- subBassMono: true = sub bass below ~80Hz is mono — standard for club music, advise keeping bass synthesis mono below 150Hz
- stereoCorrelation above 0.8 = mono-compatible mix

SPECTRAL:
- spectralBalance values are relative dB per band — compare bands against each other, not as absolute targets
- spectralCentroid: higher = brighter overall tonality
- segmentSpectral.spectralCentroid across segments reveals filter automation — rising centroid = filter opening

SYNTHESIS CHARACTER:
- oddToEvenRatio above 1.0 = saw/square wave character → suggest Operator with saw or square oscillator
- oddToEvenRatio below 1.0 = sine/triangle character → suggest Operator with sine or triangle oscillator
- inharmonicity above 0.2 = FM or noise character → suggest FM synthesis or processed oscillator

DYNAMICS:
- logAttackTime: more negative = faster attack (e.g. -4.3 ≈ 0.05ms = very fast, punchy transients)
- attackTimeStdDev low = consistent mechanical transients
- dynamicComplexity: higher = more envelope movement

STRUCTURE:
- structure.segments: treat as approximate arrangement blocks (±5-10 seconds tolerance on boundaries)
- segmentLoudness: compare LUFS across segments to identify drops, breakdowns, and energy builds
- segmentSpectral.stereoWidth changes across segments = intentional width automation

MELODY AND HARMONY:
- dominantNotes are MIDI note numbers (60=C4, 69=A4)
- If pitchConfidence is low, treat notes as approximate tonal centre hints, not transcription
- chordDetail.dominantChords are more reliable than chordSequence on full-mix masters
- vibratoPresent: false on electronic music is expected and normal

EFFECTS:
- effectsDetail.gatingDetected: treat as experimental — verify by ear
- arrangementDetail.noveltyPeaks: timestamps of structural energy changes, useful for arrangement locator placement

SIDECHAIN:
- pumpingStrength combined with pumpingConfidence — only assert sidechain presence when both are above 0.35
- pumpingRate when confident = suggested compressor trigger grid

---

OUTPUT STRUCTURE:

Respond with valid JSON only. Use the following schema. Be specific — every recommendation must name an Ableton Live 12 device with parameter values where possible.

TONE AND FORMAT:
- Write for an intermediate-to-advanced Ableton producer
- Technical but not academic — production language, not DSP terminology
- Specific over vague — "set attack to 2ms" not "fast attack"
- Where measurements are ambiguous, say so briefly and move on
- British English spelling

Phase 1 Measurements:
${JSON.stringify(phase1Result, null, 2)}`;

    const phase2StartTime = Date.now();
    const phase2Response = await withRetry(() => ai.models.generateContent({
      model: modelName,
      contents: [
        {
          parts: [
            {
              inlineData: {
                data: base64Audio,
                mimeType: mimeType,
              },
            },
            { text: phase2Prompt },
          ],
        },
      ],
      config: {
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            trackCharacter: { type: Type.STRING, description: "2-3 sentences describing the track's production character based on measurements. Reference specific values. No genre assumptions unless BPM + spectral + synthesis character make it unambiguous." },
            detectedCharacteristics: {
              type: Type.ARRAY,
              description: "List up to 5 production techniques detected from the data with confidence indicators.",
              items: {
                type: Type.OBJECT,
                properties: {
                  name: { type: Type.STRING, description: "Technique name" },
                  confidence: { type: Type.STRING, description: "HIGH, MED, or LOW" },
                  explanation: { type: Type.STRING, description: "One sentence explanation referencing the specific measurement." }
                },
                required: ["name", "confidence", "explanation"]
              }
            },
            arrangementOverview: { type: Type.STRING, description: "Based on structure.segments and segmentLoudness, describe the track layout. Include approximate timestamps. Note any key or spectral changes across segments from segmentKey and segmentSpectral." },
            sonicElements: {
              type: Type.OBJECT,
              properties: {
                kick: { type: Type.STRING, description: "Specific reconstruction advice. Reference crestFactor, grooveDetail.kickAccent pattern, spectralBalance.subBass and lowBass. Name Ableton devices and suggest parameter ranges." },
                bass: { type: Type.STRING, description: "Reference synthesisCharacter, spectralBalance.subBass/lowBass, stereoDetail.subBassMono. Suggest oscillator type, mono routing, and approximate filter cutoff." },
                melodicArp: { type: Type.STRING, description: "Reference dominantNotes (convert MIDI to note names), chordDetail.dominantChords, synthesisCharacter, pitchConfidence. If pitchConfidence is low, say so explicitly. Suggest MIDI note pattern and synth approach." },
                grooveAndTiming: { type: Type.STRING, description: "Reference grooveAmount, kickSwing, hihatSwing, beatPositions. Suggest specific Ableton groove pool settings or manual timing offsets in ms." },
                effectsAndTexture: { type: Type.STRING, description: "Reference effectsDetail, vibratoDetail, arrangementDetail. Use audio perception here for qualitative texture description." }
              },
              required: ["kick", "bass", "melodicArp", "grooveAndTiming", "effectsAndTexture"]
            },
            mixAndMasterChain: { type: Type.STRING, description: "Based on lufsIntegrated, truePeak, lufsRange, stereoDetail, spectralBalance — suggest a specific Ableton device chain in order to match the mix character. Include parameter values." },
            secretSauce: {
              type: Type.OBJECT,
              properties: {
                title: { type: Type.STRING, description: "Name of the technique" },
                explanation: { type: Type.STRING, description: "One specific production technique that defines this track's character. Use both JSON measurements and audio perception." },
                implementationSteps: { type: Type.ARRAY, items: { type: Type.STRING }, description: "Be concrete — name the technique, the Ableton implementation, and approximate settings." }
              },
              required: ["title", "explanation", "implementationSteps"]
            },
            confidenceNotes: {
              type: Type.ARRAY,
              description: "Flag any measurements that should be verified by ear before committing to.",
              items: {
                type: Type.OBJECT,
                properties: {
                  field: { type: Type.STRING, description: "Field name" },
                  value: { type: Type.STRING, description: "Value" },
                  reason: { type: Type.STRING, description: "Reason for caution" }
                },
                required: ["field", "value", "reason"]
              }
            },
            abletonRecommendations: {
              type: Type.ARRAY,
              items: {
                type: Type.OBJECT,
                properties: {
                  device: { type: Type.STRING, description: "Ableton Live 12 device name" },
                  category: { type: Type.STRING, description: "Category of the device (e.g., Dynamics, EQ, Saturation, Space, Modulation, Utility, Synth, Sampler, Other)" },
                  parameter: { type: Type.STRING, description: "Parameter name" },
                  value: { type: Type.STRING, description: "Suggested value" },
                  reason: { type: Type.STRING, description: "Reason for the recommendation" },
                  advancedTip: { type: Type.STRING, description: "Advanced tip for using this device/parameter in Live 12" },
                },
                required: ["device", "category", "parameter", "value", "reason", "advancedTip"],
              },
            },
          },
          required: ["trackCharacter", "detectedCharacteristics", "arrangementOverview", "sonicElements", "mixAndMasterChain", "secretSauce", "confidenceNotes", "abletonRecommendations"],
        },
      },
    }));
    const phase2EndTime = Date.now();

    const phase2Result: Phase2Result = JSON.parse(phase2Response.text || "{}");
    
    const phase2Log: DiagnosticLogEntry = {
      model: modelName,
      phase: "Phase 2: Reconstruction & Mix Critique",
      promptLength: phase2Prompt.length,
      responseLength: phase2Response.text?.length || 0,
      durationMs: phase2EndTime - phase2StartTime,
      audioMetadata,
      timestamp: new Date().toISOString(),
    };

    onPhase2Complete(phase2Result, phase2Log);

  } catch (error) {
    console.error("Analysis Error:", error);
    onError(error instanceof Error ? error : new Error(String(error)));
  }
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      if (typeof reader.result === "string") {
        // Remove the data URL prefix (e.g., "data:audio/mp3;base64,")
        const base64 = reader.result.split(",")[1];
        resolve(base64);
      } else {
        reject(new Error("Failed to read file as base64"));
      }
    };
    reader.onerror = (error) => reject(error);
  });
}

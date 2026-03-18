import json
import logging
import math
import mimetypes
import os
import random
import time
from typing import Any, Dict, Optional

try:
    from google import genai
    from google.genai import types
    _GENAI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]
    _GENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

# Legacy helper module retained for older experiments.
# The live Gemini integration and prompt routing now live in server.py,
# including the Layer 1/2/3 grounding split and the stem_summary profile.

# --- Constants & Configuration ---
INLINE_SIZE_LIMIT = 104_857_600  # 100 MiB — confirmed by Google on 2026-01-12
GEMINI_TIMEOUT_SECONDS = 300  # 5 minutes
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_BASE_DELAY_MS = 2_000
GEMINI_RETRYABLE_SUBSTRINGS = ["503", "high demand", "429", "quota", "unavailable"]

# --- Prompt & Schema ---
PHASE2_PROMPT_TEMPLATE = """You are an expert Ableton Live 12 producer and sound designer 
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
  - noteCount: total symbolic notes detected by the legacy comparison backend
  - averageConfidence: mean note confidence 0-1
  - dominantPitches[]: top pitches with count
  - pitchRange: min/max MIDI and note names
  - stemSeparationUsed: true if Demucs was used
  - stemsTranscribed: which stems were analysed
  - notes[].stemSource: "bass"|"other"|"full_mix"
  - When stemSeparationUsed is true, bass notes and melodic notes are separated by stemSource
  - Treat transcriptionDetail as best-effort symbolic guidance, not authoritative measurement
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

CITATION REQUIREMENT:
For every field in your output, include a "sources" array listing the specific 
Phase 1 JSON fields that justify this recommendation.

Example:
"sonicElements": {
  "kick": {
    "description": "Four-on-the-floor pattern with moderate swing...",
    "sources": ["grooveDetail.kickAccent", "grooveDetail.kickSwing", "bpm"]
  }
}

Fields that MUST have sources:
- All sonicElements (kick, bass, melodicArp, grooveAndTiming, etc.)
- Every device in mixAndMasterChain
- secretSauce.implementationSteps
- All abletonRecommendations

Fields where sources are OPTIONAL:
- trackCharacter (narrative summary)
- confidenceNotes (self-referential)

Phase 1 Measurements:
"""

PHASE2_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "trackCharacter": {"type": "STRING"},
        "detectedCharacteristics": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "confidence": {"type": "STRING"},
                    "explanation": {"type": "STRING"},
                },
                "required": ["name", "confidence", "explanation"],
            },
        },
        "arrangementOverview": {
            "type": "OBJECT",
            "properties": {
                "summary": {"type": "STRING"},
                "segments": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "index": {"type": "NUMBER"},
                            "startTime": {"type": "NUMBER"},
                            "endTime": {"type": "NUMBER"},
                            "lufs": {"type": "NUMBER"},
                            "description": {"type": "STRING"},
                            "spectralNote": {"type": "STRING"},
                        },
                        "required": ["index", "startTime", "endTime", "description"],
                    },
                },
                "noveltyNotes": {"type": "STRING"},
            },
            "required": ["summary", "segments"],
        },
        "sonicElements": {
            "type": "OBJECT",
            "properties": {
                "kick": {"type": "STRING"},
                "bass": {"type": "STRING"},
                "melodicArp": {"type": "STRING"},
                "grooveAndTiming": {"type": "STRING"},
                "effectsAndTexture": {"type": "STRING"},
                "widthAndStereo": {"type": "STRING"},
                "harmonicContent": {"type": "STRING"},
            },
            "required": ["kick", "bass", "melodicArp", "grooveAndTiming", "effectsAndTexture"],
        },
        "mixAndMasterChain": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "order": {"type": "NUMBER"},
                    "device": {"type": "STRING"},
                    "parameter": {"type": "STRING"},
                    "value": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                },
                "required": ["order", "device", "parameter", "value", "reason"],
            },
        },
        "secretSauce": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING"},
                "icon": {"type": "STRING"},
                "explanation": {"type": "STRING"},
                "implementationSteps": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
            "required": ["title", "explanation", "implementationSteps"],
        },
        "confidenceNotes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "field": {"type": "STRING"},
                    "value": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                },
                "required": ["field", "value", "reason"],
            },
        },
        "abletonRecommendations": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "device": {"type": "STRING"},
                    "category": {"type": "STRING"},
                    "parameter": {"type": "STRING"},
                    "value": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                    "advancedTip": {"type": "STRING"},
                },
                "required": ["device", "category", "parameter", "value", "reason"],
            },
        },
    },
    "required": [
        "trackCharacter",
        "detectedCharacteristics",
        "arrangementOverview",
        "sonicElements",
        "mixAndMasterChain",
        "secretSauce",
        "confidenceNotes",
        "abletonRecommendations",
    ],
}

# --- Exceptions ---
class GeminiClientError(Exception):
    """Raised when Phase 2 analysis fails."""
    def __init__(self, message: str, retryable: bool = False, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.retryable = retryable
        self.original_error = original_error

# --- Core Logic ---
def _is_retryable_error(error: Exception) -> bool:
    err_msg = str(error).lower()
    for substr in GEMINI_RETRYABLE_SUBSTRINGS:
        if substr in err_msg:
            return True
    return False

def _with_retry(operation, max_retries=GEMINI_MAX_RETRIES, base_delay_ms=GEMINI_RETRY_BASE_DELAY_MS):
    attempt = 0
    while attempt < max_retries:
        try:
            return operation()
        except Exception as e:
            attempt += 1
            is_retryable = _is_retryable_error(e)
            if not is_retryable or attempt >= max_retries:
                logger.error(f"Gemini operation failed after {attempt} attempts: {str(e)}")
                raise GeminiClientError(
                    f"Phase 2 generation failed: {str(e)}", 
                    retryable=is_retryable, 
                    original_error=e
                )
            
            # Exponential backoff with jitter
            delay = (base_delay_ms * math.pow(2, attempt - 1) + random.uniform(0, 1000)) / 1000.0
            logger.warning(f"Gemini operation failed, retrying in {delay:.2f}s: {str(e)}")
            time.sleep(delay)
    
    raise GeminiClientError("Max retries reached for Gemini analysis.", retryable=True)

def analyze_phase2(file_path: str, phase1_result: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    """
    Execute the Phase 2 LLM analysis against the audio file and DSP measurements.
    
    Args:
        file_path: Absolute path to the local audio file to analyze.
        phase1_result: The JSON dictionary produced by Phase 1 (analyze.py).
        model_name: The Gemini model name to use (e.g. 'gemini-2.5-pro').
        
    Returns:
        Dict[str, Any]: The parsed JSON response matching PHASE2_RESPONSE_SCHEMA.
        
    Raises:
        GeminiClientError: If generation fails, including network errors, auth errors, 
                           or failure to parse the LLM's JSON response.
    """
    if not _GENAI_AVAILABLE:
        raise GeminiClientError("google-genai SDK is not installed.", retryable=False)
        
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiClientError("GEMINI_API_KEY environment variable is missing.", retryable=False)
        
    # Configure the client globally. The new SDK picks up api_key from kwargs.
    client = genai.Client(api_key=api_key)
    
    prompt = f"{PHASE2_PROMPT_TEMPLATE}\n{json.dumps(phase1_result, indent=2)}"
    
    file_size = os.path.getsize(file_path)
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "audio/mpeg"
        
    def _generate(contents_payload):
        return client.models.generate_content(
            model=model_name,
            contents=contents_payload,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PHASE2_RESPONSE_SCHEMA,
            ),
        )

    # 1. Inline Data (Fast path for smaller files, <= 100 MiB)
    if file_size <= INLINE_SIZE_LIMIT:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
            
        audio_part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
        response = _with_retry(lambda: _generate([audio_part, prompt]))
        
        try:
            return json.loads(response.text)
        except json.JSONDecodeError as e:
             raise GeminiClientError("Failed to parse Phase 2 LLM JSON output.", retryable=False, original_error=e)

    # 2. Uploaded Data (For larger files)
    uploaded_file = _with_retry(
        lambda: client.files.upload(file=file_path, config={"mime_type": mime_type})
    )
    
    try:
        response = _with_retry(lambda: _generate([uploaded_file, prompt]))
        return json.loads(response.text)
    except json.JSONDecodeError as e:
         raise GeminiClientError("Failed to parse Phase 2 LLM JSON output.", retryable=False, original_error=e)
    finally:
        try:
            client.files.delete(name=uploaded_file.name)
        except Exception as e:
            # Cleanup failures shouldn't fail the primary analysis; Google auto-expires them anyway.
            logger.warning(f"Failed to delete uploaded file {uploaded_file.name}: {e}")

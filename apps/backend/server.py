import asyncio
import base64
import json
import mimetypes
import os
import random
import subprocess
import sys
import tempfile
from datetime import datetime
from math import ceil
from math import isfinite
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from google import genai as _genai
    from google.genai import types as _genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    _genai = None  # type: ignore[assignment]
    _genai_types = None  # type: ignore[assignment]
    _GENAI_AVAILABLE = False

from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from analyze import build_analysis_estimate, get_audio_duration_seconds


app = FastAPI(title="Sonic Analyzer Local API")

ANALYZE_TIMEOUT_BUFFER_SECONDS = 15
ERROR_PHASE_LOCAL_DSP = "phase1_local_dsp"
ERROR_PHASE_GEMINI = "phase2_gemini"
ENGINE_VERSION = "analyze.py"
MAX_SNIPPET_LENGTH = 2000
DEFAULT_SERVER_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 8100

INLINE_SIZE_LIMIT = 20_971_520  # 20 MiB — matches geminiPhase2Client.ts
ALLOWED_GEMINI_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3-flash-preview",
    "gemini-3-pro-preview",
    "gemini-3.1-flash-preview",
    "gemini-3.1-pro-preview",
}
GEMINI_TIMEOUT_SECONDS = 300  # 5 minutes — matches TS httpOptions.timeout
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_BASE_DELAY_MS = 2_000
GEMINI_RETRYABLE_SUBSTRINGS = ["503", "high demand", "429", "quota", "UNAVAILABLE"]

# Copied verbatim from apps/ui/src/services/geminiPhase2Client.ts lines 96-363.
# The trailing newline is deliberate: phase1 JSON is appended directly after.
PHASE2_PROMPT_TEMPLATE = """You are an expert Ableton Live 12 producer and sound designer \nspecialising in electronic music reconstruction. You receive:
1. A structured JSON object of deterministic DSP measurements
2. The audio file itself

ABSOLUTE RULES:
1. Every numeric value in the JSON is ground truth from a \n   deterministic DSP engine. Do not re-estimate or override \n   any numeric field using audio inference.
2. You are PROHIBITED from overriding: bpm, key, lufsIntegrated, \n   lufsRange, truePeak, stereoDetail values, durationSeconds.
3. Use the exact key string provided. Do not reinterpret as \n   relative major/minor. Do not override from audio perception.
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
- spectralBalance dB values describe spectral shape relative \n  to each other only, not absolute loudness or quality
- Do not use spectralBalance values to make qualitative \n  judgements about the track's perceived sound or production \n  quality
- High subBass dB does not mean "good bass" — it means \n  the spectral energy is concentrated there relative to \n  other bands
- Use spectralBalance only to inform EQ and filter \n  recommendations, not character descriptions

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
Write 4-5 sentences. Reference at least 4 specific numeric values \nfrom the JSON. The opening sentence must name the inferred genre \nand confidence. The next sentence(s) must justify that inference \nwith specific measurements. Describe synthesis character, dynamic \napproach, stereo philosophy, and spectral signature. Be specific \nand production-focused, not generic.

detectedCharacteristics:
Return exactly 5 items. Each must reference a specific measured \nvalue. Confidence must be HIGH, MED, or LOW exactly.
Cover: loudness/dynamics, stereo field, spectral character, \nsynthesis approach, rhythmic/groove characteristic.

arrangementOverview:
Return a structured object with three keys:
- summary: 2-3 sentence overview of the track's structural \n  philosophy referencing durationSeconds and overall \n  loudness approach
- segments: an array with one entry per segment in \n  structure.segments. For each segment include:
    index: segment number starting at 1
    startTime: start time in seconds from structure.segments
    endTime: end time in seconds from structure.segments
    lufs: LUFS value from segmentLoudness for this segment
    description: 3-4 sentences covering what is happening \n      musically and production-wise in this section, \n      referencing the segment's measured values
    spectralNote: one sentence on spectralCentroid or \n      stereoWidth change from segmentSpectral if available
- noveltyNotes: one paragraph mapping each noveltyPeak \n  timestamp to the structural event it represents

sonicElements:
Return ALL of the following keys with substantive content.
Each must be at minimum 4 sentences with specific values referenced:
- kick: Derive the kick recommendation directly from kickAccentVariance and kickSwing:
  - kickAccentVariance < 0.15 AND kickSwing < 0.06 → four-on-the-floor → Kick 2, short decay, 909/808
  - kickAccentVariance > 0.25 → complex pattern → Sampler, layered kicks
  - kickAccentVariance 0.15–0.25 → moderate variation → Drum Rack, mixed approach
  Also reference crestFactor, logAttackTime, and spectralBalance subBass with specific values.
- bass: reference synthesisCharacter oddToEvenRatio and \n  inharmonicity, subBassMono, spectralBalance subBass/lowBass. \n  Select synth architecture from inharmonicity:
  - 0.1-0.25 = FM / Operator
  - below 0.1 = subtractive / Analog
  - above 0.25 = wavetable or noise / Wavetable plus noise oscillator
  Apply this rule regardless of the genre label inferred in trackCharacter.
  The measured inharmonicity is ground truth.
  Explain why that instrument choice fits the measured synthesis
  character of THIS track using inharmonicity and oddToEvenRatio.
  Suggest oscillator type, filter settings, and mono routing.
- melodicArp: convert dominantNotes MIDI to note names. Reference \n  pitchConfidence explicitly — if below 0.15 say so. Reference \n  chordDetail.dominantChords. Suggest synth approach and MIDI pattern.
- grooveAndTiming: reference grooveDetail.kickSwing, grooveDetail.hihatSwing,
  and grooveDetail.kickAccent with specific ms offset calculations at the track BPM.
  Suggest Ableton groove pool settings.
- effectsAndTexture: reference effectsDetail, vibratoPresent, \n  arrangementDetail noveltyPeaks. Use audio perception here for \n  qualitative texture. Reference spectralContrast values.
- widthAndStereo: reference stereoWidth, stereoCorrelation, \n  subBassMono, segmentSpectral stereoWidth changes across segments. \n  Suggest Utility device settings and any width automation.
- harmonicContent: reference key, keyConfidence, segmentKey changes, \n  chordDetail.dominantChords, chordStrength. Suggest scale/mode \n  for writing new parts.

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
- value: specific numeric or descriptive target value \n  derived from JSON measurements
- reason: one sentence referencing the specific measured \n  value that justifies this device and setting
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
implementationSteps: return exactly 6 steps. Each step must be \na complete sentence with specific Ableton device names, parameter \nnames, and numeric values. Steps must build on each other \nsequentially.

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
Cover the full signal chain: sound design devices, effects, \ngroup processing, and mastering.
For each card:
- device: exact Ableton Live 12 device name
- category: one of SYNTHESIS, DYNAMICS, EQ, EFFECTS, \n  STEREO, MASTERING, MIDI, ROUTING
- parameter: specific parameter name as it appears in Ableton
- value: specific numeric or descriptive target value derived \n  from JSON measurements
- reason: one sentence referencing the specific measured value \n  that justifies this recommendation
- advancedTip: one concrete advanced technique for this device \n  in this context

Do not pad with generic advice. Every recommendation must be \njustified by a specific measurement from the JSON.

CITATION REQUIREMENT:
For every field in your output, include a "sources" array listing the specific \nPhase 1 JSON fields that justify this recommendation.

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
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3100",
    "http://127.0.0.1:3100",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _coerce_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        numeric = float(value)
        if isfinite(numeric):
            return numeric
    return default


def _coerce_string(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _coerce_nullable_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None


def _coerce_positive_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        numeric = int(round(float(value)))
        return numeric if numeric >= 0 else default
    return default


def _coerce_nullable_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if isfinite(numeric):
            return numeric
    return None


def _current_time() -> datetime:
    return datetime.now()


def resolve_server_port() -> int:
    raw_value = os.getenv("SONIC_ANALYZER_PORT", str(DEFAULT_SERVER_PORT)).strip()
    try:
        port = int(raw_value)
    except ValueError:
        return DEFAULT_SERVER_PORT
    if 0 < port <= 65535:
        return port
    return DEFAULT_SERVER_PORT


def _elapsed_ms(started_at: datetime | None, ended_at: datetime | None) -> float:
    if started_at is None or ended_at is None:
        return 0.0
    return max((ended_at - started_at).total_seconds() * 1000, 0.0)


def _build_phase1(payload: dict[str, Any]) -> dict[str, Any]:
    stereo_detail = payload.get("stereoDetail")
    if not isinstance(stereo_detail, dict):
        stereo_detail = {}

    spectral_balance = payload.get("spectralBalance")
    if not isinstance(spectral_balance, dict):
        spectral_balance = {}

    return {
        "bpm": _coerce_number(payload.get("bpm")),
        "bpmConfidence": _coerce_number(payload.get("bpmConfidence")),
        "key": _coerce_nullable_string(payload.get("key")),
        "keyConfidence": _coerce_number(payload.get("keyConfidence")),
        "timeSignature": _coerce_string(payload.get("timeSignature"), "4/4"),
        "durationSeconds": _coerce_number(payload.get("durationSeconds")),
        "lufsIntegrated": _coerce_number(payload.get("lufsIntegrated")),
        "lufsRange": _coerce_nullable_number(payload.get("lufsRange")),
        "truePeak": _coerce_number(payload.get("truePeak")),
        "crestFactor": _coerce_nullable_number(payload.get("crestFactor")),
        "stereoWidth": _coerce_number(stereo_detail.get("stereoWidth")),
        "stereoCorrelation": _coerce_number(stereo_detail.get("stereoCorrelation")),
        "stereoDetail": payload.get("stereoDetail"),
        "spectralBalance": {
            "subBass": _coerce_number(spectral_balance.get("subBass")),
            "lowBass": _coerce_number(spectral_balance.get("lowBass")),
            "mids": _coerce_number(spectral_balance.get("mids")),
            "upperMids": _coerce_number(spectral_balance.get("upperMids")),
            "highs": _coerce_number(spectral_balance.get("highs")),
            "brilliance": _coerce_number(spectral_balance.get("brilliance")),
        },
        "spectralDetail": payload.get("spectralDetail"),
        "rhythmDetail": payload.get("rhythmDetail"),
        "melodyDetail": payload.get("melodyDetail"),
        "transcriptionDetail": payload.get("transcriptionDetail"),
        "grooveDetail": payload.get("grooveDetail"),
        "sidechainDetail": payload.get("sidechainDetail"),
        "effectsDetail": payload.get("effectsDetail"),
        "synthesisCharacter": payload.get("synthesisCharacter"),
        "danceability": payload.get("danceability"),
        "structure": payload.get("structure"),
        "arrangementDetail": payload.get("arrangementDetail"),
        "segmentLoudness": payload.get("segmentLoudness"),
        "segmentSpectral": payload.get("segmentSpectral"),
        "segmentKey": payload.get("segmentKey"),
        "chordDetail": payload.get("chordDetail"),
        "perceptual": payload.get("perceptual"),
    }


def _persist_upload(track: UploadFile) -> tuple[str, int]:
    suffix = Path(track.filename or "upload.bin").suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = temp_file.name
        total_bytes = 0
        while True:
            chunk = track.file.read(1024 * 1024)
            if not chunk:
                break
            total_bytes += len(chunk)
            temp_file.write(chunk)
    return temp_path, total_bytes


def _cleanup_temp_path(temp_path: str | None) -> None:
    if temp_path and os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass


def _safe_snippet(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    snippet = text.strip()
    if not snippet:
        return None
    return snippet[:MAX_SNIPPET_LENGTH]


def _normalize_estimate_stage(raw_stage: dict[str, Any]) -> dict[str, Any]:
    raw_key = _coerce_string(raw_stage.get("key"), "local_dsp")
    raw_label = _coerce_string(raw_stage.get("label"), "Local DSP analysis")
    stage_key = {
        "dsp": "local_dsp",
        "separation": "demucs_separation",
    }.get(raw_key, raw_key)
    stage_label = {
        "local_dsp": "Local DSP analysis",
        "demucs_separation": "Demucs separation",
    }.get(stage_key, raw_label)
    seconds = raw_stage.get("seconds")
    if not isinstance(seconds, dict):
        seconds = {}
    low_ms = _coerce_positive_int(seconds.get("min")) * 1000
    high_ms = _coerce_positive_int(seconds.get("max")) * 1000
    if high_ms < low_ms:
        high_ms = low_ms
    return {
        "key": stage_key,
        "label": stage_label,
        "lowMs": low_ms,
        "highMs": high_ms,
    }


def _build_backend_estimate(
    audio_path: str,
    run_separation: bool,
    run_transcribe: bool,
) -> dict[str, Any]:
    try:
        duration_seconds = get_audio_duration_seconds(audio_path)
    except Exception:
        duration_seconds = None

    safe_duration = duration_seconds if duration_seconds is not None else 0.0
    raw_estimate = build_analysis_estimate(
        safe_duration, run_separation, run_transcribe
    )
    raw_stages = raw_estimate.get("stages")
    stages = (
        [
            _normalize_estimate_stage(stage)
            for stage in raw_stages
            if isinstance(stage, dict)
        ]
        if isinstance(raw_stages, list)
        else []
    )

    total_seconds = raw_estimate.get("totalSeconds")
    if isinstance(total_seconds, dict):
        total_low_ms = _coerce_positive_int(total_seconds.get("min")) * 1000
        total_high_ms = _coerce_positive_int(total_seconds.get("max")) * 1000
    else:
        total_low_ms = sum(stage["lowMs"] for stage in stages)
        total_high_ms = sum(stage["highMs"] for stage in stages)

    if total_high_ms < total_low_ms:
        total_high_ms = total_low_ms

    normalized_duration = (
        round(float(duration_seconds), 1)
        if isinstance(duration_seconds, (int, float))
        and isfinite(float(duration_seconds))
        else round(float(raw_estimate.get("durationSeconds", 0.0)), 1)
    )

    return {
        "durationSeconds": normalized_duration,
        "totalLowMs": total_low_ms,
        "totalHighMs": total_high_ms,
        "stages": stages,
    }


# ---------------------------------------------------------------------------
# Gemini Phase 2 helpers
# ---------------------------------------------------------------------------


def _get_audio_mime_type(filename: str, fallback: str = "audio/mpeg") -> str:
    mime, _ = mimetypes.guess_type(filename)
    if mime and mime.startswith("audio/"):
        return mime
    return fallback


def _is_retryable_gemini_error(error_message: str) -> bool:
    return any(sub in error_message for sub in GEMINI_RETRYABLE_SUBSTRINGS)


async def _gemini_with_retry(
    operation: Any,
    max_retries: int = GEMINI_MAX_RETRIES,
    base_delay_ms: float = GEMINI_RETRY_BASE_DELAY_MS,
) -> Any:
    """Run a synchronous callable in a thread with exponential-backoff retry.

    Retry logic mirrors withRetry() in geminiPhase2Client.ts exactly:
      delay = base * 2^(attempt-1) + random(0..1000) ms
    Retryable substrings match GEMINI_RETRYABLE_SUBSTRINGS.
    """
    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            return await asyncio.to_thread(operation)
        except Exception as exc:
            error_msg = str(exc)
            is_retryable = _is_retryable_gemini_error(error_msg)
            if not is_retryable or attempt >= max_retries:
                raise
            delay_ms = base_delay_ms * (2 ** (attempt - 1)) + random.random() * 1_000
            await asyncio.sleep(delay_ms / 1_000)
    raise RuntimeError("Max retries reached for Gemini Phase 2.")


def _build_phase2_prompt(phase1_dict: dict[str, Any]) -> str:
    return PHASE2_PROMPT_TEMPLATE + json.dumps(phase1_dict, indent=2)


def _is_str(v: Any) -> bool:
    return isinstance(v, str)


def _is_finite_num(v: Any) -> bool:
    return not isinstance(v, bool) and isinstance(v, (int, float)) and isfinite(float(v))


def _is_opt_str(v: Any) -> bool:
    """Absent (None) or string — matches TS isOptionalString(undefined | string)."""
    return v is None or _is_str(v)


def _is_opt_num(v: Any) -> bool:
    """Absent (None) or finite number — matches TS isOptionalNumber."""
    return v is None or _is_finite_num(v)


def _is_str_list(v: Any) -> bool:
    return isinstance(v, list) and all(_is_str(i) for i in v)


def _as_record(v: Any) -> dict[str, Any] | None:
    if not v or not isinstance(v, dict):
        return None
    return v


def _is_detected_characteristics(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        r = _as_record(item)
        if not r:
            return False
        if not (_is_str(r.get("name")) and _is_str(r.get("explanation"))):
            return False
        if r.get("confidence") not in ("HIGH", "MED", "LOW"):
            return False
    return True


def _is_arrangement_overview(v: Any) -> bool:
    r = _as_record(v)
    if not r or not _is_str(r.get("summary")) or not isinstance(r.get("segments"), list):
        return False
    for seg in r["segments"]:
        s = _as_record(seg)
        if not s:
            return False
        if not (_is_finite_num(s.get("index")) and _is_finite_num(s.get("startTime"))
                and _is_finite_num(s.get("endTime")) and _is_str(s.get("description"))):
            return False
        if not _is_opt_num(s.get("lufs")) or not _is_opt_str(s.get("spectralNote")):
            return False
    return _is_opt_str(r.get("noveltyNotes"))


def _is_sonic_elements(v: Any) -> bool:
    r = _as_record(v)
    if not r:
        return False
    required_keys = ("kick", "bass", "melodicArp", "grooveAndTiming", "effectsAndTexture")
    optional_keys = ("widthAndStereo", "harmonicContent")
    return (
        all(_is_str(r.get(k)) for k in required_keys)
        and all(_is_opt_str(r.get(k)) for k in optional_keys)
    )


def _is_mix_and_master_chain(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        r = _as_record(item)
        if not r:
            return False
        if not (_is_finite_num(r.get("order")) and _is_str(r.get("device"))
                and _is_str(r.get("parameter")) and _is_str(r.get("value"))
                and _is_str(r.get("reason"))):
            return False
    return True


def _is_secret_sauce(v: Any) -> bool:
    r = _as_record(v)
    if not r:
        return False
    return (
        _is_str(r.get("title"))
        and _is_opt_str(r.get("icon"))
        and _is_str(r.get("explanation"))
        and _is_str_list(r.get("implementationSteps"))
    )


def _is_confidence_notes(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        r = _as_record(item)
        if not r:
            return False
        if not (_is_str(r.get("field")) and _is_str(r.get("value")) and _is_str(r.get("reason"))):
            return False
    return True


def _is_ableton_recommendations(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        r = _as_record(item)
        if not r:
            return False
        required = ("device", "category", "parameter", "value", "reason")
        if not all(_is_str(r.get(k)) for k in required):
            return False
        if not _is_opt_str(r.get("advancedTip")):
            return False
    return True


def _is_valid_phase2_shape(data: Any) -> bool:
    """Mirrors isPhase2Result() in geminiPhase2Client.ts."""
    r = _as_record(data)
    if not r:
        return False
    return (
        _is_str(r.get("trackCharacter"))
        and _is_detected_characteristics(r.get("detectedCharacteristics"))
        and _is_arrangement_overview(r.get("arrangementOverview"))
        and _is_sonic_elements(r.get("sonicElements"))
        and _is_mix_and_master_chain(r.get("mixAndMasterChain"))
        and _is_secret_sauce(r.get("secretSauce"))
        and _is_confidence_notes(r.get("confidenceNotes"))
        and _is_ableton_recommendations(r.get("abletonRecommendations"))
    )


def _parse_phase2_result(
    response_text: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Returns (result, skip_message). Mirrors parsePhase2Result() in geminiPhase2Client.ts.

    Skip cases return 200 with phase2=null — they are NOT errors.
    """
    raw = (response_text or "").strip()
    if not raw:
        return None, "Phase 2 advisory skipped because Gemini returned an empty response."
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None, "Phase 2 advisory skipped because Gemini returned invalid JSON."
    if not _is_valid_phase2_shape(parsed):
        return None, "Phase 2 advisory skipped because Gemini returned an invalid response shape."
    return parsed, None


def _build_phase2_success_response(
    *,
    request_id: str,
    phase2_result: dict[str, Any] | None,
    message: str,
    model_name: str,
    request_started_at: datetime,
    api_started_at: datetime | None,
    api_completed_at: datetime | None,
    flags_used: list[str],
    file_size_bytes: int,
) -> JSONResponse:
    estimate: dict[str, Any] = {"totalLowMs": 0, "totalHighMs": 0}
    diagnostics = _build_diagnostics(
        request_id=request_id,
        estimate=estimate,
        timeout_seconds=GEMINI_TIMEOUT_SECONDS,
        request_started_at=request_started_at,
        analysis_started_at=api_started_at,
        analysis_completed_at=api_completed_at,
        flags_used=flags_used,
        file_size_bytes=file_size_bytes,
        file_duration_seconds=None,
        engine_version=model_name,
    )
    return JSONResponse(
        content={
            "requestId": request_id,
            "phase2": phase2_result,
            "message": message,
            "diagnostics": diagnostics,
        }
    )


def _build_phase2_error_response(
    *,
    request_id: str,
    status_code: int,
    error_code: str,
    message: str,
    retryable: bool,
    model_name: str,
    request_started_at: datetime,
    api_started_at: datetime | None,
    api_completed_at: datetime | None,
    flags_used: list[str],
    file_size_bytes: int,
    stderr: Any = None,
) -> JSONResponse:
    estimate: dict[str, Any] = {"totalLowMs": 0, "totalHighMs": 0}
    diagnostics = _build_diagnostics(
        request_id=request_id,
        estimate=estimate,
        timeout_seconds=GEMINI_TIMEOUT_SECONDS,
        request_started_at=request_started_at,
        analysis_started_at=api_started_at,
        analysis_completed_at=api_completed_at,
        flags_used=flags_used,
        file_size_bytes=file_size_bytes,
        file_duration_seconds=None,
        engine_version=model_name,
        stderr=stderr,
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "requestId": request_id,
            "error": {
                "code": error_code,
                "message": message,
                "phase": ERROR_PHASE_GEMINI,
                "retryable": retryable,
            },
            "diagnostics": diagnostics,
        },
    )


# ---------------------------------------------------------------------------
# End Gemini Phase 2 helpers
# ---------------------------------------------------------------------------


def _compute_timeout_seconds(estimate: dict[str, Any]) -> int:
    estimated_high_ms = _coerce_positive_int(estimate.get("totalHighMs"))
    estimated_high_seconds = (
        ceil(estimated_high_ms / 1000) if estimated_high_ms > 0 else 45
    )
    return estimated_high_seconds + ANALYZE_TIMEOUT_BUFFER_SECONDS


def _compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _round_timing_value(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _format_timing_summary_value(
    value: float | None, suffix: str = "", digits: int = 1
) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}{suffix}"


def _build_timings(
    *,
    request_started_at: datetime,
    analysis_started_at: datetime | None,
    analysis_completed_at: datetime | None,
    flags_used: list[str],
    file_size_bytes: int,
    file_duration_seconds: float | None,
) -> dict[str, Any]:
    response_ready_at = _current_time()
    total_ms = _elapsed_ms(request_started_at, response_ready_at)
    analysis_ms = _elapsed_ms(analysis_started_at, analysis_completed_at)
    server_overhead_ms = max(total_ms - analysis_ms, 0.0)
    normalized_duration_seconds = _coerce_nullable_number(file_duration_seconds)
    ms_per_second_of_audio = None
    if normalized_duration_seconds is not None and normalized_duration_seconds > 0:
        ms_per_second_of_audio = analysis_ms / normalized_duration_seconds

    return {
        "totalMs": _round_timing_value(total_ms),
        "analysisMs": _round_timing_value(analysis_ms),
        "serverOverheadMs": _round_timing_value(server_overhead_ms),
        "flagsUsed": list(flags_used),
        "fileSizeBytes": int(file_size_bytes),
        "fileDurationSeconds": _round_timing_value(normalized_duration_seconds),
        "msPerSecondOfAudio": _round_timing_value(ms_per_second_of_audio),
    }


def _log_timing_summary(timings: dict[str, Any]) -> None:
    flags_used = timings.get("flagsUsed")
    flags_label = (
        f"[{', '.join(flags_used)}]"
        if isinstance(flags_used, list) and flags_used
        else "[]"
    )
    file_size_bytes = _coerce_positive_int(timings.get("fileSizeBytes"))
    file_size_mb = file_size_bytes / (1024 * 1024)
    print(
        f"[TIMING] total={_format_timing_summary_value(timings.get('totalMs'), 'ms')} "
        f"analysis={_format_timing_summary_value(timings.get('analysisMs'), 'ms')} "
        f"overhead={_format_timing_summary_value(timings.get('serverOverheadMs'), 'ms')} "
        f"flags={flags_label} "
        f"fileSize={_format_timing_summary_value(file_size_mb, 'MB')} "
        f"duration={_format_timing_summary_value(timings.get('fileDurationSeconds'), 's')} "
        f"ms/s={_format_timing_summary_value(timings.get('msPerSecondOfAudio'), digits=2)}",
        file=sys.stderr,
    )


def _build_diagnostics(
    *,
    request_id: str,
    estimate: dict[str, Any],
    timeout_seconds: int,
    request_started_at: datetime,
    analysis_started_at: datetime | None,
    analysis_completed_at: datetime | None,
    flags_used: list[str],
    file_size_bytes: int,
    file_duration_seconds: float | None,
    engine_version: str | None = None,
    stdout: Any = None,
    stderr: Any = None,
) -> dict[str, Any]:
    timings = _build_timings(
        request_started_at=request_started_at,
        analysis_started_at=analysis_started_at,
        analysis_completed_at=analysis_completed_at,
        flags_used=flags_used,
        file_size_bytes=file_size_bytes,
        file_duration_seconds=file_duration_seconds,
    )
    _log_timing_summary(timings)
    return _compact_dict(
        {
            "requestId": request_id,
            "backendDurationMs": timings["analysisMs"],
            "engineVersion": engine_version,
            "estimatedLowMs": _coerce_positive_int(estimate.get("totalLowMs")),
            "estimatedHighMs": _coerce_positive_int(estimate.get("totalHighMs")),
            "timeoutSeconds": timeout_seconds,
            "timings": timings,
            "stdoutSnippet": _safe_snippet(stdout),
            "stderrSnippet": _safe_snippet(stderr),
        }
    )


def _build_error_response(
    *,
    request_id: str,
    status_code: int,
    error_code: str,
    message: str,
    retryable: bool,
    timeout_seconds: int,
    estimate: dict[str, Any],
    request_started_at: datetime,
    analysis_started_at: datetime | None,
    analysis_completed_at: datetime | None,
    flags_used: list[str],
    file_size_bytes: int,
    file_duration_seconds: float | None,
    stdout: Any = None,
    stderr: Any = None,
) -> JSONResponse:
    diagnostics = _build_diagnostics(
        request_id=request_id,
        estimate=estimate,
        timeout_seconds=timeout_seconds,
        request_started_at=request_started_at,
        analysis_started_at=analysis_started_at,
        analysis_completed_at=analysis_completed_at,
        flags_used=flags_used,
        file_size_bytes=file_size_bytes,
        file_duration_seconds=file_duration_seconds,
        stdout=stdout,
        stderr=stderr,
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "requestId": request_id,
            "error": {
                "code": error_code,
                "message": message,
                "phase": ERROR_PHASE_LOCAL_DSP,
                "retryable": retryable,
            },
            "diagnostics": diagnostics,
        },
    )


def _build_success_response(
    *,
    request_id: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    estimate: dict[str, Any],
    request_started_at: datetime,
    analysis_started_at: datetime,
    analysis_completed_at: datetime,
    flags_used: list[str],
    file_size_bytes: int,
) -> JSONResponse:
    diagnostics = _build_diagnostics(
        request_id=request_id,
        estimate=estimate,
        timeout_seconds=timeout_seconds,
        request_started_at=request_started_at,
        analysis_started_at=analysis_started_at,
        analysis_completed_at=analysis_completed_at,
        flags_used=flags_used,
        file_size_bytes=file_size_bytes,
        file_duration_seconds=payload.get("durationSeconds"),
        engine_version=ENGINE_VERSION,
    )
    return JSONResponse(
        content={
            "requestId": request_id,
            "phase1": _build_phase1(payload),
            "diagnostics": diagnostics,
        }
    )


@app.post("/api/analyze/estimate")
async def estimate_analysis(
    track: UploadFile = File(...),
    dsp_json_override: str | None = Form(None),
    transcribe: bool = Form(False),
    separate: bool = Form(False),
    separate_query: bool = Query(
        False, alias="separate", description="Pass --separate to analyze.py when true"
    ),
    separate_flag: bool = Query(
        False,
        alias="--separate",
        description="Alias for separate; accepts query key --separate",
    ),
):
    temp_path: str | None = None
    try:
        temp_path, _file_size_bytes = _persist_upload(track)
        _ = dsp_json_override
        run_separation = bool(separate or separate_query or separate_flag)
        estimate = _build_backend_estimate(temp_path, run_separation, transcribe)
        return JSONResponse(
            content={
                "requestId": str(uuid4()),
                "estimate": estimate,
            }
        )
    finally:
        await track.close()
        _cleanup_temp_path(temp_path)


@app.post("/api/analyze")
async def analyze_audio(
    track: UploadFile = File(...),
    dsp_json_override: str | None = Form(None),
    transcribe: bool = Form(False),
    separate: bool = Form(False),
    separate_query: bool = Query(
        False, alias="separate", description="Pass --separate to analyze.py when true"
    ),
    separate_flag: bool = Query(
        False,
        alias="--separate",
        description="Alias for separate; accepts query key --separate",
    ),
):
    temp_path: str | None = None
    request_id = str(uuid4())
    request_started_at = _current_time()
    analysis_started_at: datetime | None = None
    analysis_completed_at: datetime | None = None
    try:
        temp_path, file_size_bytes = _persist_upload(track)
        _ = dsp_json_override
        run_separation = bool(separate or separate_query or separate_flag)
        estimate = _build_backend_estimate(temp_path, run_separation, transcribe)

        command = ["./venv/bin/python", "analyze.py", temp_path, "--yes"]
        flags_used: list[str] = []
        if run_separation:
            command.append("--separate")
            flags_used.append("--separate")
        if transcribe:
            command.append("--transcribe")
            flags_used.append("--transcribe")

        timeout_seconds = _compute_timeout_seconds(estimate)
        analysis_started_at = _current_time()
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            analysis_completed_at = _current_time()
            return _build_error_response(
                request_id=request_id,
                status_code=504,
                error_code="ANALYZER_TIMEOUT",
                message="Local DSP analysis timed out before completion.",
                retryable=True,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                request_started_at=request_started_at,
                analysis_started_at=analysis_started_at,
                analysis_completed_at=analysis_completed_at,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
                file_duration_seconds=None,
                stdout=exc.stdout,
                stderr=exc.stderr,
            )
        except Exception as exc:
            analysis_completed_at = _current_time()
            return _build_error_response(
                request_id=request_id,
                status_code=500,
                error_code="BACKEND_INTERNAL_ERROR",
                message="Local DSP backend hit an unexpected server error.",
                retryable=False,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                request_started_at=request_started_at,
                analysis_started_at=analysis_started_at,
                analysis_completed_at=analysis_completed_at,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
                file_duration_seconds=None,
                stderr=exc,
            )
        analysis_completed_at = _current_time()

        if result.returncode != 0:
            return _build_error_response(
                request_id=request_id,
                status_code=502,
                error_code="ANALYZER_FAILED",
                message="Local DSP analysis failed before a valid result was produced.",
                retryable=True,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                request_started_at=request_started_at,
                analysis_started_at=analysis_started_at,
                analysis_completed_at=analysis_completed_at,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
                file_duration_seconds=None,
                stdout=result.stdout,
                stderr=result.stderr,
            )

        stdout = result.stdout.strip()
        if not stdout:
            return _build_error_response(
                request_id=request_id,
                status_code=502,
                error_code="ANALYZER_EMPTY_OUTPUT",
                message="Local DSP analysis completed without returning any JSON.",
                retryable=False,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                request_started_at=request_started_at,
                analysis_started_at=analysis_started_at,
                analysis_completed_at=analysis_completed_at,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
                file_duration_seconds=None,
                stderr=result.stderr,
            )

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return _build_error_response(
                request_id=request_id,
                status_code=502,
                error_code="ANALYZER_INVALID_JSON",
                message="Local DSP analysis returned malformed JSON.",
                retryable=False,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                request_started_at=request_started_at,
                analysis_started_at=analysis_started_at,
                analysis_completed_at=analysis_completed_at,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
                file_duration_seconds=None,
                stdout=stdout,
                stderr=result.stderr,
            )

        if not isinstance(payload, dict):
            return _build_error_response(
                request_id=request_id,
                status_code=502,
                error_code="ANALYZER_BAD_PAYLOAD",
                message="Local DSP analysis returned a JSON payload that did not match the expected contract.",
                retryable=False,
                timeout_seconds=timeout_seconds,
                estimate=estimate,
                request_started_at=request_started_at,
                analysis_started_at=analysis_started_at,
                analysis_completed_at=analysis_completed_at,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
                file_duration_seconds=None,
                stdout=stdout,
                stderr=result.stderr,
            )

        return _build_success_response(
            request_id=request_id,
            payload=payload,
            timeout_seconds=timeout_seconds,
            estimate=estimate,
            request_started_at=request_started_at,
            analysis_started_at=analysis_started_at,
            analysis_completed_at=analysis_completed_at,
            flags_used=flags_used,
            file_size_bytes=file_size_bytes,
        )
    finally:
        await track.close()
        _cleanup_temp_path(temp_path)


@app.post("/api/phase2")
async def analyze_phase2(
    track: UploadFile = File(...),
    phase1_json: str = Form(...),
    model_name: str = Form("gemini-2.5-flash"),
) -> JSONResponse:
    """Run Gemini Phase 2 advisory reconstruction server-side.

    Accepts the audio file + stringified Phase1Result.
    Returns { requestId, phase2: Phase2Result | null, message, diagnostics }.
    Skip cases (empty/bad JSON/bad shape from Gemini) return 200 with phase2=null.
    Infrastructure failures (timeout, auth, quota) return 4xx/5xx.
    """
    if not _GENAI_AVAILABLE:
        return JSONResponse(
            status_code=500,
            content={
                "requestId": str(uuid4()),
                "error": {
                    "code": "GEMINI_NOT_INSTALLED",
                    "message": "google-genai package is not installed on the backend.",
                    "phase": ERROR_PHASE_GEMINI,
                    "retryable": False,
                },
            },
        )

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return JSONResponse(
            status_code=500,
            content={
                "requestId": str(uuid4()),
                "error": {
                    "code": "GEMINI_NOT_CONFIGURED",
                    "message": "GEMINI_API_KEY is not set on the backend.",
                    "phase": ERROR_PHASE_GEMINI,
                    "retryable": False,
                },
            },
        )

    if model_name not in ALLOWED_GEMINI_MODELS:
        return JSONResponse(
            status_code=400,
            content={
                "requestId": str(uuid4()),
                "error": {
                    "code": "INVALID_MODEL",
                    "message": f"model_name '{model_name}' is not allowed. Must be one of: {sorted(ALLOWED_GEMINI_MODELS)}",
                    "phase": ERROR_PHASE_GEMINI,
                    "retryable": False,
                },
            },
        )

    temp_path: str | None = None
    request_id = str(uuid4())
    request_started_at = _current_time()
    api_started_at: datetime | None = None
    api_completed_at: datetime | None = None
    flags_used: list[str] = []
    file_size_bytes = 0

    try:
        # 1. Persist upload
        temp_path, file_size_bytes = _persist_upload(track)
        filename = track.filename or "upload.bin"
        mime_type = _get_audio_mime_type(filename)

        # 2. Parse phase1_json — use as-is (already normalized by frontend)
        try:
            phase1_dict = json.loads(phase1_json)
        except json.JSONDecodeError:
            return _build_phase2_error_response(
                request_id=request_id,
                status_code=400,
                error_code="PHASE2_BAD_PHASE1_JSON",
                message="phase1_json field could not be parsed as JSON.",
                retryable=False,
                model_name=model_name,
                request_started_at=request_started_at,
                api_started_at=None,
                api_completed_at=None,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
            )
        if not isinstance(phase1_dict, dict):
            return _build_phase2_error_response(
                request_id=request_id,
                status_code=400,
                error_code="PHASE2_BAD_PHASE1_JSON",
                message="phase1_json must be a JSON object.",
                retryable=False,
                model_name=model_name,
                request_started_at=request_started_at,
                api_started_at=None,
                api_completed_at=None,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
            )

        # 3. Build prompt
        prompt = _build_phase2_prompt(phase1_dict)

        # 4. Create Gemini client
        client = _genai.Client(
            api_key=api_key,
            http_options={"timeout": GEMINI_TIMEOUT_SECONDS * 1_000},
        )
        generate_config = _genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PHASE2_RESPONSE_SCHEMA,
        )

        # 5. Inline or Files API path — threshold matches INLINE_SIZE_LIMIT in TS
        api_started_at = _current_time()
        uploaded_gemini_file = None

        if file_size_bytes <= INLINE_SIZE_LIMIT:
            flags_used.append("inline")
            with open(temp_path, "rb") as f:
                audio_bytes = f.read()
            audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
            media_part = {"inline_data": {"data": audio_b64, "mime_type": mime_type}}

            def _generate_inline() -> Any:
                return client.models.generate_content(
                    model=model_name,
                    contents=[{"parts": [media_part, {"text": prompt}]}],
                    config=generate_config,
                )

            try:
                response = await _gemini_with_retry(_generate_inline)
            except Exception as exc:
                api_completed_at = _current_time()
                error_msg = str(exc)
                status_code = 429 if "429" in error_msg or "quota" in error_msg.lower() else 502
                return _build_phase2_error_response(
                    request_id=request_id,
                    status_code=status_code,
                    error_code="GEMINI_GENERATE_FAILED",
                    message=f"Gemini generation failed: {error_msg[:200]}",
                    retryable=True,
                    model_name=model_name,
                    request_started_at=request_started_at,
                    api_started_at=api_started_at,
                    api_completed_at=_current_time(),
                    flags_used=flags_used,
                    file_size_bytes=file_size_bytes,
                    stderr=error_msg,
                )

            api_completed_at = _current_time()
            message_suffix = "Phase 2 advisory complete."

        else:
            flags_used.append("files-api")

            def _upload_file() -> Any:
                return client.files.upload(
                    file=temp_path,
                    config=_genai_types.UploadFileConfig(
                        mime_type=mime_type,
                        display_name=filename,
                    ),
                )

            try:
                upload_start = _current_time()
                uploaded_gemini_file = await _gemini_with_retry(_upload_file)
                upload_end = _current_time()
            except Exception as exc:
                api_completed_at = _current_time()
                return _build_phase2_error_response(
                    request_id=request_id,
                    status_code=502,
                    error_code="GEMINI_UPLOAD_FAILED",
                    message=f"Gemini file upload failed: {str(exc)[:200]}",
                    retryable=True,
                    model_name=model_name,
                    request_started_at=request_started_at,
                    api_started_at=api_started_at,
                    api_completed_at=_current_time(),
                    flags_used=flags_used,
                    file_size_bytes=file_size_bytes,
                    stderr=str(exc),
                )

            media_part = {
                "file_data": {
                    "file_uri": uploaded_gemini_file.uri,
                    "mime_type": uploaded_gemini_file.mime_type,
                }
            }

            def _generate_files_api() -> Any:
                return client.models.generate_content(
                    model=model_name,
                    contents=[{"parts": [media_part, {"text": prompt}]}],
                    config=generate_config,
                )

            try:
                generate_start = _current_time()
                response = await _gemini_with_retry(_generate_files_api)
                generate_end = _current_time()
            except Exception as exc:
                api_completed_at = _current_time()
                error_msg = str(exc)
                status_code = 429 if "429" in error_msg or "quota" in error_msg.lower() else 502
                return _build_phase2_error_response(
                    request_id=request_id,
                    status_code=status_code,
                    error_code="GEMINI_GENERATE_FAILED",
                    message=f"Gemini generation failed: {error_msg[:200]}",
                    retryable=True,
                    model_name=model_name,
                    request_started_at=request_started_at,
                    api_started_at=api_started_at,
                    api_completed_at=_current_time(),
                    flags_used=flags_used,
                    file_size_bytes=file_size_bytes,
                    stderr=error_msg,
                )
            finally:
                # Always delete the uploaded file — mirrors try/finally in TS
                if uploaded_gemini_file:
                    try:
                        await asyncio.to_thread(
                            lambda: client.files.delete(name=uploaded_gemini_file.name)
                        )
                    except Exception:
                        pass  # files auto-expire ~24h; cleanup failures must not fail the analysis

            api_completed_at = _current_time()
            upload_ms = int(_elapsed_ms(upload_start, upload_end))
            generate_ms = int(_elapsed_ms(generate_start, generate_end))
            message_suffix = f"Phase 2 advisory complete. Upload: {upload_ms}ms, Generate: {generate_ms}ms"

        # 6. Parse and validate Gemini response
        response_text: str | None = getattr(response, "text", None)
        phase2_result, skip_message = _parse_phase2_result(response_text)

        if skip_message:
            return _build_phase2_success_response(
                request_id=request_id,
                phase2_result=None,
                message=skip_message,
                model_name=model_name,
                request_started_at=request_started_at,
                api_started_at=api_started_at,
                api_completed_at=api_completed_at,
                flags_used=flags_used,
                file_size_bytes=file_size_bytes,
            )

        return _build_phase2_success_response(
            request_id=request_id,
            phase2_result=phase2_result,
            message=message_suffix,
            model_name=model_name,
            request_started_at=request_started_at,
            api_started_at=api_started_at,
            api_completed_at=api_completed_at,
            flags_used=flags_used,
            file_size_bytes=file_size_bytes,
        )

    except Exception as exc:
        api_completed_at = api_completed_at or _current_time()
        return _build_phase2_error_response(
            request_id=request_id,
            status_code=500,
            error_code="BACKEND_INTERNAL_ERROR",
            message="Phase 2 backend hit an unexpected server error.",
            retryable=False,
            model_name=model_name,
            request_started_at=request_started_at,
            api_started_at=api_started_at,
            api_completed_at=api_completed_at,
            flags_used=flags_used,
            file_size_bytes=file_size_bytes,
            stderr=str(exc),
        )
    finally:
        await track.close()
        _cleanup_temp_path(temp_path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host=DEFAULT_SERVER_HOST, port=resolve_server_port(), reload=False)

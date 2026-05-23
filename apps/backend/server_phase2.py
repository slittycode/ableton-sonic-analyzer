"""Phase 2 (Gemini interpretation): validation, normalization, parsing, prompts."""

import json
import mimetypes
import re
from math import isfinite
from pathlib import Path
from typing import Any, Callable

from analysis_runtime import AnalysisRuntime, UnsupportedPitchNoteModeError
from server_phase1 import (
    _coerce_nullable_number,
    _coerce_nullable_string,
    _normalize_spectral_detail,
    _safe_snippet,
)


GEMINI_RETRYABLE_SUBSTRINGS = [
    "503",
    "high demand",
    "429",
    "quota",
    "UNAVAILABLE",
    "peer closed connection",
    "incomplete chunked read",
    "RemoteProtocolError",
    "ConnectionError",
    "ConnectionResetError",
]

_PROMPTS_DIR = Path(__file__).parent / "prompts"

_ALLOWED_LIVE12_DEVICE_FAMILIES = {"NATIVE", "MAX_FOR_LIVE"}
_ALLOWED_LIVE12_DEVICE_CLASSES = {
    "instrument",
    "audio_effect",
    "midi_effect",
    "utility",
    "routing",
    "mastering",
}
_ALLOWED_PHASE2_RECOMMENDATION_CATEGORIES = {
    "SYNTHESIS",
    "DYNAMICS",
    "EQ",
    "EFFECTS",
    "STEREO",
    "MASTERING",
    "MIDI",
    "ROUTING",
}
_ALLOWED_PHASE2_WORKFLOW_STAGES = {
    "PROJECT_SETUP",
    "SOUND_DESIGN",
    "ARRANGEMENT",
    "MIX",
    "MASTER",
}
_ALLOWED_PHASE2_WARP_MODES = {
    "Beats",
    "Tones",
    "Texture",
    "Re-Pitch",
    "Complex",
    "Complex Pro",
}
_DEVICE_FAMILY_COERCION: dict[str, str] = {
    "STOCK": "NATIVE",
    "BUILT_IN": "NATIVE",
    "BUILT-IN": "NATIVE",
    "BUILTIN": "NATIVE",
    "ABLETON": "NATIVE",
    "LIVE": "NATIVE",
    "THIRD_PARTY": "MAX_FOR_LIVE",
    "PLUGIN": "MAX_FOR_LIVE",
    "M4L": "MAX_FOR_LIVE",
    "MAX4LIVE": "MAX_FOR_LIVE",
}
_WORKFLOW_STAGE_COERCION: dict[str, str] = {
    "SYNTHESIS": "SOUND_DESIGN",
    "PATCHING": "SOUND_DESIGN",
    "PRODUCTION": "SOUND_DESIGN",
    "COMPOSITION": "ARRANGEMENT",
    "RECORDING": "PROJECT_SETUP",
    "MIXING": "MIX",
    "MASTERING": "MASTER",
    "MIXDOWN": "MIX",
}
_RECOMMENDATION_CATEGORY_COERCION: dict[str, str] = {
    "DRUMS": "DYNAMICS",
    "COMPRESSION": "DYNAMICS",
    "SATURATION": "DYNAMICS",
    "SPACE": "EFFECTS",
    "REVERB": "EFFECTS",
    "DELAY": "EFFECTS",
    "MODULATION": "EFFECTS",
    "DISTORTION": "EFFECTS",
    "FILTERING": "EQ",
    "PANNING": "STEREO",
    "IMAGING": "STEREO",
    "WIDTH": "STEREO",
    "LIMITING": "MASTERING",
    "LOUDNESS": "MASTERING",
    "SEQUENCING": "MIDI",
    "AUTOMATION": "ROUTING",
}

def _load_prompt_template(name: str) -> str:
    path = _PROMPTS_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuntimeError(
            f"Prompt template '{name}' not found at {path}. "
            "Re-run from the apps/backend directory."
        ) from None


def _load_live12_device_catalog(path: Path | None = None) -> dict[str, Any]:
    catalog_path = path or (_PROMPTS_DIR / "live12_device_catalog.json")
    try:
        raw = catalog_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuntimeError(
            f"Live 12 device catalog not found at {catalog_path}. "
            "Add apps/backend/prompts/live12_device_catalog.json before starting Phase A."
        ) from None

    try:
        catalog = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Live 12 device catalog at {catalog_path} contains invalid JSON: {exc}"
        ) from exc

    if not isinstance(catalog, dict):
        raise RuntimeError("Live 12 device catalog must be a JSON object with a devices array.")

    devices = catalog.get("devices")
    if not isinstance(devices, list) or not devices:
        raise RuntimeError("Live 12 device catalog must contain a non-empty devices array.")

    seen_names: set[str] = set()
    for index, device in enumerate(devices):
        if not isinstance(device, dict):
            raise RuntimeError(f"Live 12 device catalog entry {index} must be an object.")

        name = device.get("name")
        family = device.get("family")
        device_class = device.get("class")
        allowed_parameters = device.get("allowedParameters")

        if not isinstance(name, str) or not name.strip():
            raise RuntimeError(f"Live 12 device catalog entry {index} is missing a valid name.")
        if name in seen_names:
            raise RuntimeError(f"Live 12 device catalog contains a duplicate device name: {name}")
        seen_names.add(name)

        if family not in _ALLOWED_LIVE12_DEVICE_FAMILIES:
            raise RuntimeError(
                f"Live 12 device catalog entry '{name}' has invalid family '{family}'."
            )
        if device_class not in _ALLOWED_LIVE12_DEVICE_CLASSES:
            raise RuntimeError(
                f"Live 12 device catalog entry '{name}' has invalid class '{device_class}'."
            )
        if (
            not isinstance(allowed_parameters, list)
            or not allowed_parameters
            or not all(isinstance(item, str) and item.strip() for item in allowed_parameters)
        ):
            raise RuntimeError(
                f"Live 12 device catalog entry '{name}' must have a non-empty allowedParameters array."
            )

        # Optional parameterAliases: {alias_string: canonical_string} where every
        # canonical_string must already be in allowedParameters. Catches typos in
        # the alias-target at startup rather than at runtime.
        aliases = device.get("parameterAliases")
        if aliases is not None:
            if not isinstance(aliases, dict):
                raise RuntimeError(
                    f"Live 12 device catalog entry '{name}' parameterAliases must be an object."
                )
            allowed_set = set(allowed_parameters)
            for alias, canonical in aliases.items():
                if not isinstance(alias, str) or not alias.strip():
                    raise RuntimeError(
                        f"Live 12 device catalog entry '{name}' parameterAliases has a non-string key."
                    )
                if not isinstance(canonical, str) or not canonical.strip():
                    raise RuntimeError(
                        f"Live 12 device catalog entry '{name}' parameterAliases['{alias}'] must be a non-empty string."
                    )
                if canonical not in allowed_set:
                    raise RuntimeError(
                        f"Live 12 device catalog entry '{name}' parameterAliases['{alias}'] -> "
                        f"'{canonical}' is not in allowedParameters."
                    )

    return catalog



PRODUCER_SUMMARY_PROMPT_TEMPLATE = _load_prompt_template("phase2_system.txt")
STEM_SUMMARY_PROMPT_TEMPLATE = _load_prompt_template("stem_summary_system.txt")
LIVE12_DEVICE_CATALOG = _load_live12_device_catalog()
LIVE12_DEVICE_LOOKUP = {
    device["name"]: device for device in LIVE12_DEVICE_CATALOG["devices"]
}
PHASE2_PROMPT_TEMPLATE = PRODUCER_SUMMARY_PROMPT_TEMPLATE
PRODUCER_SUMMARY_PROMPT_VERSION = "producer_summary.phase_abcd2.current"
SUPPORTED_INTERPRETATION_PROFILES = {"producer_summary", "stem_summary"}

PHASE2_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "trackCharacter": {"type": "STRING"},
        "projectSetup": {
            "type": "OBJECT",
            "properties": {
                "tempoBpm": {"type": "NUMBER"},
                "timeSignature": {"type": "STRING"},
                "sampleRate": {"type": "NUMBER"},
                "bitDepth": {"type": "NUMBER"},
                "headroomTarget": {"type": "STRING"},
                "sessionGoal": {"type": "STRING"},
            },
            "required": [
                "tempoBpm",
                "timeSignature",
                "sampleRate",
                "bitDepth",
                "headroomTarget",
                "sessionGoal",
            ],
        },
        "trackLayout": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "order": {"type": "NUMBER"},
                    "name": {"type": "STRING"},
                    "type": {"type": "STRING"},
                    "purpose": {"type": "STRING"},
                    "grounding": {
                        "type": "OBJECT",
                        "properties": {
                            "phase1Fields": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"},
                            },
                            "segmentIndexes": {
                                "type": "ARRAY",
                                "items": {"type": "NUMBER"},
                            },
                        },
                        "required": ["phase1Fields"],
                    },
                },
                "required": ["order", "name", "type", "purpose", "grounding"],
            },
        },
        "routingBlueprint": {
            "type": "OBJECT",
            "properties": {
                "sidechainSource": {"type": "STRING"},
                "sidechainTargets": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "returns": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "name": {"type": "STRING"},
                            "purpose": {"type": "STRING"},
                            "sendSources": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"},
                            },
                            "deviceFocus": {"type": "STRING"},
                            "levelGuidance": {"type": "STRING"},
                        },
                        "required": [
                            "name",
                            "purpose",
                            "sendSources",
                            "deviceFocus",
                            "levelGuidance",
                        ],
                    },
                },
                "notes": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
            },
            "required": ["sidechainTargets", "returns", "notes"],
        },
        "warpGuide": {
            "type": "OBJECT",
            "properties": {
                "fullTrack": {
                    "type": "OBJECT",
                    "properties": {
                        "warpMode": {"type": "STRING"},
                        "settings": {"type": "STRING"},
                        "reason": {"type": "STRING"},
                    },
                    "required": ["warpMode", "reason"],
                },
                "drums": {
                    "type": "OBJECT",
                    "properties": {
                        "warpMode": {"type": "STRING"},
                        "settings": {"type": "STRING"},
                        "reason": {"type": "STRING"},
                    },
                    "required": ["warpMode", "reason"],
                },
                "bass": {
                    "type": "OBJECT",
                    "properties": {
                        "warpMode": {"type": "STRING"},
                        "settings": {"type": "STRING"},
                        "reason": {"type": "STRING"},
                    },
                    "required": ["warpMode", "reason"],
                },
                "melodic": {
                    "type": "OBJECT",
                    "properties": {
                        "warpMode": {"type": "STRING"},
                        "settings": {"type": "STRING"},
                        "reason": {"type": "STRING"},
                    },
                    "required": ["warpMode", "reason"],
                },
                "vocals": {
                    "type": "OBJECT",
                    "properties": {
                        "warpMode": {"type": "STRING"},
                        "settings": {"type": "STRING"},
                        "reason": {"type": "STRING"},
                    },
                    "required": ["warpMode", "reason"],
                },
                "rationale": {"type": "STRING"},
            },
            "required": ["fullTrack", "drums", "bass", "melodic", "rationale"],
        },
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
        "audioObservations": {
            "type": "OBJECT",
            "properties": {
                "soundDesignFingerprint": {"type": "STRING"},
                "elementCharacter": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "element": {"type": "STRING"},
                            "description": {"type": "STRING"},
                        },
                        "required": ["element", "description"],
                    },
                },
                "productionSignatures": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "mixContext": {"type": "STRING"},
            },
            "required": [
                "soundDesignFingerprint",
                "elementCharacter",
                "productionSignatures",
                "mixContext",
            ],
        },
        "styleProfile": {
            "type": "OBJECT",
            "properties": {
                "genre": {"type": "STRING"},
                "subGenre": {"type": "STRING"},
                "mood": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "instruments": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "productionTechniques": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "description": {"type": "STRING"},
                "generationPrompt": {"type": "STRING"},
                "authoritativeMeasurements": {
                    "type": "OBJECT",
                    "properties": {
                        "bpm": {"type": "NUMBER"},
                        "key": {"type": "STRING"},
                        "timeSignature": {"type": "STRING"},
                    },
                    "required": ["bpm", "key", "timeSignature"],
                },
            },
            "required": [
                "genre",
                "mood",
                "instruments",
                "productionTechniques",
                "description",
                "generationPrompt",
                "authoritativeMeasurements",
            ],
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
                            "sceneName": {"type": "STRING"},
                            "abletonAction": {"type": "STRING"},
                            "automationFocus": {"type": "STRING"},
                        },
                        "required": [
                            "index",
                            "startTime",
                            "endTime",
                            "description",
                            "sceneName",
                            "abletonAction",
                            "automationFocus",
                        ],
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
                    "deviceFamily": {"type": "STRING"},
                    "trackContext": {"type": "STRING"},
                    "workflowStage": {"type": "STRING"},
                    "parameter": {"type": "STRING"},
                    "value": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                    "phase1Fields": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                    },
                },
                "required": [
                    "order",
                    "device",
                    "deviceFamily",
                    "trackContext",
                    "workflowStage",
                    "parameter",
                    "value",
                    "reason",
                    "phase1Fields",
                ],
            },
        },
        "secretSauce": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING"},
                "icon": {"type": "STRING"},
                "explanation": {"type": "STRING"},
                "implementationSteps": {"type": "ARRAY", "items": {"type": "STRING"}},
                "workflowSteps": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "step": {"type": "NUMBER"},
                            "trackContext": {"type": "STRING"},
                            "device": {"type": "STRING"},
                            "parameter": {"type": "STRING"},
                            "value": {"type": "STRING"},
                            "instruction": {"type": "STRING"},
                            "measurementJustification": {"type": "STRING"},
                            "phase1Fields": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"},
                            },
                        },
                        "required": [
                            "step",
                            "trackContext",
                            "device",
                            "parameter",
                            "value",
                            "instruction",
                            "measurementJustification",
                            "phase1Fields",
                        ],
                    },
                },
            },
            "required": ["title", "explanation", "implementationSteps", "workflowSteps"],
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
                    "deviceFamily": {"type": "STRING"},
                    "trackContext": {"type": "STRING"},
                    "workflowStage": {"type": "STRING"},
                    "category": {"type": "STRING"},
                    "parameter": {"type": "STRING"},
                    "value": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                    "advancedTip": {"type": "STRING"},
                    "phase1Fields": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                    },
                },
                "required": [
                    "device",
                    "deviceFamily",
                    "trackContext",
                    "workflowStage",
                    "category",
                    "parameter",
                    "value",
                    "reason",
                    "advancedTip",
                    "phase1Fields",
                ],
            },
        },
    },
    "required": [
        "trackCharacter",
        "projectSetup",
        "trackLayout",
        "routingBlueprint",
        "warpGuide",
        "detectedCharacteristics",
        "arrangementOverview",
        "sonicElements",
        "mixAndMasterChain",
        "secretSauce",
        "confidenceNotes",
        "abletonRecommendations",
    ],
}
STEM_SUMMARY_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "bars": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "barStart": {"type": "NUMBER"},
                    "barEnd": {"type": "NUMBER"},
                    "startTime": {"type": "NUMBER"},
                    "endTime": {"type": "NUMBER"},
                    "noteHypotheses": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "scaleDegreeHypotheses": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "rhythmicPattern": {"type": "STRING"},
                    "uncertaintyLevel": {"type": "STRING"},
                    "uncertaintyReason": {"type": "STRING"},
                },
                "required": [
                    "barStart",
                    "barEnd",
                    "startTime",
                    "endTime",
                    "noteHypotheses",
                    "scaleDegreeHypotheses",
                    "rhythmicPattern",
                    "uncertaintyLevel",
                    "uncertaintyReason",
                ],
            },
        },
        "globalPatterns": {
            "type": "OBJECT",
            "properties": {
                "bassRole": {"type": "STRING"},
                "melodicRole": {"type": "STRING"},
                "pumpingOrModulation": {"type": "STRING"},
                "synthesisCharacter": {"type": "STRING"},
                "vocalPresence": {"type": "STRING"},
                "bassCharacter": {"type": "STRING"},
            },
            "required": [
                "bassRole",
                "melodicRole",
                "pumpingOrModulation",
                "synthesisCharacter",
                "vocalPresence",
                "bassCharacter",
            ],
        },
        "uncertaintyFlags": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["summary", "bars", "globalPatterns", "uncertaintyFlags"],
}

def _resolve_pitch_note_mode_for_legacy(transcribe: bool) -> str:
    return "stem_notes" if transcribe else "off"


def _resolve_estimate_flags_for_stage_request(
    requested_pitch_note_mode: str,
) -> tuple[bool, bool]:
    if requested_pitch_note_mode == "off":
        return False, False
    if requested_pitch_note_mode == "stem_notes":
        return True, True
    raise UnsupportedPitchNoteModeError(requested_pitch_note_mode)



def _resolve_analysis_mode_value(value: Any) -> str:
    if not isinstance(value, str):
        return "full"
    return AnalysisRuntime._resolve_analysis_mode(value)



def _stem_summary_label(stem_kind: str) -> str:
    if stem_kind == "bass":
        return "Bass stem"
    if stem_kind == "other":
        return "Musical stem"
    return f"{stem_kind.title()} stem"


def _build_combined_stem_summary_result(stem_results: list[dict[str, Any]]) -> dict[str, Any]:
    combined_uncertainty: list[str] = []
    combined_summary_parts: list[str] = []
    stems_payload: list[dict[str, Any]] = []

    for stem_result in stem_results:
        stem_kind = str(stem_result["stem"])
        single_result = stem_result["result"]
        stems_payload.append(
            {
                "stem": stem_kind,
                "label": _stem_summary_label(stem_kind),
                "summary": single_result["summary"],
                "bars": single_result["bars"],
                "globalPatterns": single_result["globalPatterns"],
                "uncertaintyFlags": single_result["uncertaintyFlags"],
            }
        )
        combined_summary_parts.append(f"{_stem_summary_label(stem_kind)}: {single_result['summary']}")
        for flag in single_result["uncertaintyFlags"]:
            if flag not in combined_uncertainty:
                combined_uncertainty.append(flag)

    return {
        "summary": " ".join(combined_summary_parts),
        "stems": stems_payload,
        "uncertaintyFlags": combined_uncertainty,
    }



def _get_audio_mime_type(filename: str, fallback: str = "audio/mpeg") -> str:
    mime, _ = mimetypes.guess_type(filename)
    if mime and mime.startswith("audio/"):
        return mime
    return fallback


def _is_retryable_gemini_error(error_message: str) -> bool:
    return any(sub in error_message for sub in GEMINI_RETRYABLE_SUBSTRINGS)



def _normalize_measurement_result_for_gemini(payload: dict[str, Any]) -> dict[str, Any]:
    """Rename the spectral fields Gemini sees so they match what the frontend
    parses and what the Phase 2 citation contract names.

    The analyzer emits ``spectralDetail.spectralCentroid`` (without the
    ``Mean`` suffix) but ``server_phase1._build_phase1`` renames those keys to
    ``spectralCentroidMean`` etc. when shaping the snapshot for the frontend.
    Gemini was previously seeing the raw names, then citing them under
    ``phase1Fields`` — and the validator (which checks against the
    frontend-shaped Phase 1 payload) flagged those citations as invented
    paths.

    Applying the same renames here unifies the field-name contract: the JSON
    Gemini reads, the JSON the frontend parses, and the paths the validator
    accepts all line up. The normalization is applied to both the top-level
    ``spectralDetail`` AND to every per-stem ``stemAnalysis.{stem}.spectralDetail``
    so Gemini sees one consistent name everywhere.
    """
    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    spectral_detail = normalized.get("spectralDetail")
    if isinstance(spectral_detail, dict):
        normalized["spectralDetail"] = _normalize_spectral_detail(spectral_detail)
    stem_analysis = normalized.get("stemAnalysis")
    if isinstance(stem_analysis, dict):
        normalized_stems = {}
        for stem_name, stem_entry in stem_analysis.items():
            if not isinstance(stem_entry, dict):
                normalized_stems[stem_name] = stem_entry
                continue
            stem_copy = dict(stem_entry)
            stem_spectral_detail = stem_copy.get("spectralDetail")
            if isinstance(stem_spectral_detail, dict):
                stem_copy["spectralDetail"] = _normalize_spectral_detail(stem_spectral_detail)
            normalized_stems[stem_name] = stem_copy
        normalized["stemAnalysis"] = normalized_stems
    return normalized


def _build_phase2_prompt(
    *,
    measurement_result: dict[str, Any],
    pitch_note_result: dict[str, Any] | None,
    grounding_metadata: dict[str, Any],
    descriptor_hooks: dict[str, Any] | None = None,
) -> str:
    measurement_for_gemini = _normalize_measurement_result_for_gemini(measurement_result)
    sections = [
        PRODUCER_SUMMARY_PROMPT_TEMPLATE.rstrip(),
        "\n\nAUTHORITATIVE_MEASUREMENT_RESULT_JSON:\n",
        json.dumps(measurement_for_gemini, indent=2),
        "\n\nOPTIONAL_PITCH_NOTE_TRANSLATION_RESULT_JSON:\n",
        json.dumps(pitch_note_result, indent=2),
        "\n\nLIVE_12_DEVICE_CATALOG_JSON:\n",
        json.dumps(LIVE12_DEVICE_CATALOG, indent=2),
        "\n\nGROUNDING_METADATA:\n",
        json.dumps(grounding_metadata, indent=2),
    ]
    if descriptor_hooks:
        sections.extend(
            [
                "\n\nMEASUREMENT_DERIVED_DESCRIPTOR_HOOKS:\n",
                json.dumps(descriptor_hooks, indent=2),
            ]
    )
    return "".join(sections)


def _build_stem_summary_prompt(
    *,
    measurement_result: dict[str, Any],
    pitch_note_result: dict[str, Any] | None,
    grounding_metadata: dict[str, Any],
    descriptor_hooks: dict[str, Any],
) -> str:
    sections = [
        STEM_SUMMARY_PROMPT_TEMPLATE.rstrip(),
        "\n\nAUTHORITATIVE_MEASUREMENT_RESULT_JSON:\n",
        json.dumps(measurement_result, indent=2),
        "\n\nOPTIONAL_PITCH_NOTE_TRANSLATION_RESULT_JSON:\n",
        json.dumps(pitch_note_result, indent=2),
        "\n\nMEASUREMENT_DERIVED_DESCRIPTOR_HOOKS:\n",
        json.dumps(descriptor_hooks, indent=2),
        "\n\nGROUNDING_METADATA:\n",
        json.dumps(grounding_metadata, indent=2),
    ]
    return "".join(sections)


def _build_descriptor_hooks(measurement_result: dict[str, Any]) -> dict[str, Any]:
    duration_seconds = _coerce_nullable_number(measurement_result.get("durationSeconds"))
    rhythm_detail = measurement_result.get("rhythmDetail")
    segment_loudness = measurement_result.get("segmentLoudness")
    sidechain_detail = measurement_result.get("sidechainDetail")
    melody_detail = measurement_result.get("melodyDetail")
    groove_detail = measurement_result.get("grooveDetail")

    downbeats: list[float] = []
    if isinstance(rhythm_detail, dict) and isinstance(rhythm_detail.get("downbeats"), list):
        for entry in rhythm_detail["downbeats"]:
            if _is_finite_num(entry):
                downbeats.append(round(float(entry), 4))

    bar_grid: list[dict[str, Any]] = []
    if downbeats:
        for index, start_time in enumerate(downbeats):
            end_time = (
                downbeats[index + 1]
                if index + 1 < len(downbeats)
                else duration_seconds
            )
            if end_time is None:
                continue
            bar_grid.append(
                {
                    "barStart": index + 1,
                    "barEnd": index + 1,
                    "startTime": round(float(start_time), 4),
                    "endTime": round(float(end_time), 4),
                }
            )

    energy_curve: dict[str, Any] = {
        "segmentLoudness": [],
        "kickAccent16": [],
        "hihatAccent16": [],
    }
    if isinstance(segment_loudness, list):
        for entry in segment_loudness:
            if not isinstance(entry, dict):
                continue
            energy_curve["segmentLoudness"].append(
                {
                    "segmentIndex": entry.get("segmentIndex"),
                    "start": entry.get("start"),
                    "end": entry.get("end"),
                    "lufs": entry.get("lufs"),
                    "lra": entry.get("lra"),
                }
            )
    if isinstance(groove_detail, dict):
        if isinstance(groove_detail.get("kickAccent"), list):
            energy_curve["kickAccent16"] = groove_detail.get("kickAccent")
        if isinstance(groove_detail.get("hihatAccent"), list):
            energy_curve["hihatAccent16"] = groove_detail.get("hihatAccent")

    pumping_descriptor = {
        "pumpingStrength": None,
        "pumpingRegularity": None,
        "pumpingRate": None,
        "pumpingConfidence": None,
        "vibratoPresent": None,
        "vibratoRate": None,
        "vibratoConfidence": None,
    }
    if isinstance(sidechain_detail, dict):
        pumping_descriptor["pumpingStrength"] = sidechain_detail.get("pumpingStrength")
        pumping_descriptor["pumpingRegularity"] = sidechain_detail.get("pumpingRegularity")
        pumping_descriptor["pumpingRate"] = sidechain_detail.get("pumpingRate")
        pumping_descriptor["pumpingConfidence"] = sidechain_detail.get("pumpingConfidence")
    if isinstance(melody_detail, dict):
        pumping_descriptor["vibratoPresent"] = melody_detail.get("vibratoPresent")
        pumping_descriptor["vibratoRate"] = melody_detail.get("vibratoRate")
        pumping_descriptor["vibratoConfidence"] = melody_detail.get("vibratoConfidence")

    return {
        "stableBarGrid": bar_grid,
        "beatSynchronousEnergyCurve": energy_curve,
        "pumpingOrModulationDescriptor": pumping_descriptor,
    }


def _interpretation_schema_version(profile_id: str) -> str:
    return "interpretation.v2" if profile_id == "producer_summary" else "interpretation.v1"


def _resolve_interpretation_profile_config(profile_id: str) -> dict[str, Any]:
    if profile_id == "producer_summary":
        return {
            "responseSchema": PHASE2_RESPONSE_SCHEMA,
            "buildPrompt": _build_phase2_prompt,
            "parseResult": _parse_phase2_result,
            "parseDebugResult": _parse_phase2_result_debug,
            "successMessage": "AI interpretation complete.",
            "promptVersion": PRODUCER_SUMMARY_PROMPT_VERSION,
            "schemaVersion": "interpretation.v2",
        }
    if profile_id == "stem_summary":
        return {
            "responseSchema": STEM_SUMMARY_RESPONSE_SCHEMA,
            "buildPrompt": _build_stem_summary_prompt,
            "parseResult": _parse_stem_summary_result,
            "parseDebugResult": None,
            "successMessage": "Stem summary complete.",
        }
    raise ValueError(
        f"interpretation_profile '{profile_id}' is unsupported. "
        f"Supported profiles: {sorted(SUPPORTED_INTERPRETATION_PROFILES)}"
    )


### -----------------------------------------------------------------------
### Phase 2 grammar post-process: rewrite "by <3rd-person-singular-verb>" to
### "by <gerund>". Gemini consistently emits the wrong form in role/reason
### text (e.g., "Shapes drum impact by recreates the harmonic distortion"
### instead of "...by recreating the harmonic distortion"). The audit's
### final round prescribed a server-side post-process; the prompt nudge in
### phase2_system.txt did not take.
###
### Conservative: only rewrites when the word after "by" is at least 4
### characters and lowercase a-z, and is NOT in the small denylist of common
### plural nouns that legitimately appear after "by" in technical prose.
### -----------------------------------------------------------------------

_PHASE2_BY_VERB_RE = re.compile(r"\bby ([a-z]{4,})s\b")

_PHASE2_BY_NOUN_DENYLIST = frozenset(
    {
        # Plural nouns / measure words that legitimately appear after "by" in
        # technical writing. Anything in this set is left as-is.
        "tones", "notes", "lines", "sides", "modes", "kinds", "codes",
        "cases", "rates", "types", "pairs", "rules", "bands", "parts",
        "tools", "forms", "works", "phases", "stages", "features",
        "systems", "classes", "numbers", "measures", "reasons", "sources",
        "targets", "units", "tracks", "cycles", "beats", "hits",
        "samples", "patterns", "pieces", "levels", "values", "amounts",
        "degrees", "effects", "paths", "fields", "frames", "styles",
        "genres", "others", "ranges", "drums", "stems", "voices",
        "channels", "tracks", "groups", "buses", "passes", "blocks",
        "chords", "scales", "octaves", "intervals", "harmonics",
    }
)


# Verbs requiring consonant doubling at the gerund (control → controlling,
# submit → submitting). English doubling is stress-conditional and not worth
# implementing algorithmically — this map covers the music-production verbs
# Gemini actually emits after "by".
_GERUND_IRREGULARS: dict[str, str] = {
    "controls": "controlling",
    "submits": "submitting",
    "commits": "committing",
    "transmits": "transmitting",
    "permits": "permitting",
    "omits": "omitting",
    "emits": "emitting",
    "runs": "running",
    "begins": "beginning",
    "compels": "compelling",
}


def _to_gerund(verb_3sg: str) -> str:
    """3rd-person singular → gerund (best effort, no dictionary lookup).

    "matches"   → "matching"   (strip -es, +ing)
    "shapes"    → "shaping"    (strip -s, drop terminal -e, +ing)
    "recreates" → "recreating" (same)
    "absorbs"   → "absorbing"  (strip -s, +ing)
    "controls"  → "controlling" (via _GERUND_IRREGULARS)
    """
    if verb_3sg in _GERUND_IRREGULARS:
        return _GERUND_IRREGULARS[verb_3sg]
    if verb_3sg.endswith(("ches", "shes", "sses", "tches", "xes", "zzes")):
        stem = verb_3sg[:-2]
    else:
        stem = verb_3sg[:-1]
    if stem.endswith("e") and not stem.endswith(("ee", "oe", "ye", "ie")):
        stem = stem[:-1]
    return stem + "ing"


def _fix_by_gerund_in_text(text: str) -> str:
    """Rewrite "by <bad-verb-form>" patterns inside a single string.

    Empty/non-string inputs pass through unchanged. The regex is bounded to
    lowercase a-z words 4+ chars long, and the denylist guards against
    common plural-noun false positives.
    """
    if not isinstance(text, str) or not text:
        return text

    def _repl(match: re.Match) -> str:
        word_with_s = match.group(1) + "s"
        if word_with_s in _PHASE2_BY_NOUN_DENYLIST:
            return match.group(0)
        return f"by {_to_gerund(word_with_s)}"

    return _PHASE2_BY_VERB_RE.sub(_repl, text)


def _fix_grammar_in_record(record: Any, fields: tuple[str, ...]) -> Any:
    """Apply `_fix_by_gerund_in_text` to specific string fields of a record.
    Returns the record unchanged if it isn't a dict or has none of the fields.
    """
    if not isinstance(record, dict):
        return record
    for field in fields:
        original = record.get(field)
        if isinstance(original, str):
            fixed = _fix_by_gerund_in_text(original)
            if fixed != original:
                record[field] = fixed
    return record


def _apply_phase2_grammar_fixes(normalized: dict[str, Any]) -> None:
    """Walk the relevant Phase 2 free-text fields and rewrite "by <verb>s"
    to "by <verb>ing" in-place. Targets:
      - abletonRecommendations[].{reason, advancedTip}
      - mixAndMasterChain[].reason
      - secretSauce.workflowSteps[].{measurementJustification, instruction}
    """
    recs = normalized.get("abletonRecommendations")
    if isinstance(recs, list):
        for item in recs:
            _fix_grammar_in_record(item, ("reason", "advancedTip"))

    mix_chain = normalized.get("mixAndMasterChain")
    if isinstance(mix_chain, list):
        for item in mix_chain:
            _fix_grammar_in_record(item, ("reason",))

    secret_sauce = normalized.get("secretSauce")
    if isinstance(secret_sauce, dict):
        workflow_steps = secret_sauce.get("workflowSteps")
        if isinstance(workflow_steps, list):
            for item in workflow_steps:
                _fix_grammar_in_record(item, ("measurementJustification", "instruction"))


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


def _is_num_list(v: Any) -> bool:
    return isinstance(v, list) and all(_is_finite_num(i) for i in v)


def _as_record(v: Any) -> dict[str, Any] | None:
    if not v or not isinstance(v, dict):
        return None
    return v


def _is_project_setup(v: Any) -> bool:
    record = _as_record(v)
    if not record:
        return False
    return (
        _is_finite_num(record.get("tempoBpm"))
        and _is_str(record.get("timeSignature"))
        and _is_finite_num(record.get("sampleRate"))
        and _is_finite_num(record.get("bitDepth"))
        and _is_str(record.get("headroomTarget"))
        and _is_str(record.get("sessionGoal"))
    )


def _is_track_grounding(v: Any) -> bool:
    record = _as_record(v)
    if not record or not _is_str_list(record.get("phase1Fields")):
        return False
    return record.get("segmentIndexes") is None or _is_num_list(record.get("segmentIndexes"))


def _is_track_layout(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        record = _as_record(item)
        if not record:
            return False
        if not (
            _is_finite_num(record.get("order"))
            and _is_str(record.get("name"))
            and _is_str(record.get("type"))
            and _is_str(record.get("purpose"))
            and _is_track_grounding(record.get("grounding"))
        ):
            return False
    return True


def _is_routing_returns(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        record = _as_record(item)
        if not record:
            return False
        if not (
            _is_str(record.get("name"))
            and _is_str(record.get("purpose"))
            and _is_str_list(record.get("sendSources"))
            and _is_str(record.get("deviceFocus"))
            and _is_str(record.get("levelGuidance"))
        ):
            return False
    return True


def _is_routing_blueprint(v: Any) -> bool:
    record = _as_record(v)
    if not record:
        return False
    return (
        _is_opt_str(record.get("sidechainSource"))
        and _is_str_list(record.get("sidechainTargets"))
        and _is_routing_returns(record.get("returns"))
        and _is_str_list(record.get("notes"))
    )


def _is_warp_target(v: Any) -> bool:
    record = _as_record(v)
    if not record:
        return False
    return (
        record.get("warpMode") in _ALLOWED_PHASE2_WARP_MODES
        and _is_opt_str(record.get("settings"))
        and _is_str(record.get("reason"))
    )


def _is_warp_guide(v: Any) -> bool:
    record = _as_record(v)
    if not record:
        return False
    return (
        _is_warp_target(record.get("fullTrack"))
        and _is_warp_target(record.get("drums"))
        and _is_warp_target(record.get("bass"))
        and _is_warp_target(record.get("melodic"))
        and (_is_warp_target(record.get("vocals")) if record.get("vocals") is not None else True)
        and _is_str(record.get("rationale"))
    )


def _is_device_family(v: Any) -> bool:
    return v in _ALLOWED_LIVE12_DEVICE_FAMILIES


def _is_workflow_stage(v: Any) -> bool:
    return v in _ALLOWED_PHASE2_WORKFLOW_STAGES


def _is_recommendation_category(v: Any) -> bool:
    return v in _ALLOWED_PHASE2_RECOMMENDATION_CATEGORIES


def _is_secret_sauce_workflow_steps(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        record = _as_record(item)
        if not record:
            return False
        if not (
            _is_finite_num(record.get("step"))
            and _is_str(record.get("trackContext"))
            and _is_str(record.get("device"))
            and _is_str(record.get("parameter"))
            and _is_str(record.get("value"))
            and _is_str(record.get("instruction"))
            and _is_str(record.get("measurementJustification"))
        ):
            return False
    return True


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


def _is_audio_element_character(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        record = _as_record(item)
        if not record:
            return False
        if not (_is_str(record.get("element")) and _is_str(record.get("description"))):
            return False
    return True


def _is_audio_observations(v: Any) -> bool:
    record = _as_record(v)
    if not record:
        return False
    return (
        _is_str(record.get("soundDesignFingerprint"))
        and _is_audio_element_character(record.get("elementCharacter"))
        and _is_str_list(record.get("productionSignatures"))
        and _is_str(record.get("mixContext"))
    )


def _is_style_profile_authoritative_measurements(v: Any) -> bool:
    record = _as_record(v)
    if not record:
        return False
    return (
        "bpm" in record
        and "key" in record
        and "timeSignature" in record
        and _is_opt_num(record.get("bpm"))
        and _is_opt_str(record.get("key"))
        and _is_opt_str(record.get("timeSignature"))
    )


def _is_style_profile(v: Any) -> bool:
    record = _as_record(v)
    if not record:
        return False
    return (
        _is_str(record.get("genre"))
        and _is_opt_str(record.get("subGenre"))
        and _is_str_list(record.get("mood"))
        and _is_str_list(record.get("instruments"))
        and _is_str_list(record.get("productionTechniques"))
        and _is_str(record.get("description"))
        and _is_str(record.get("generationPrompt"))
        and _is_style_profile_authoritative_measurements(
            record.get("authoritativeMeasurements")
        )
    )


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
        if not (
            _is_opt_num(s.get("lufs"))
            and _is_opt_str(s.get("spectralNote"))
            and _is_str(s.get("sceneName"))
            and _is_str(s.get("abletonAction"))
            and _is_str(s.get("automationFocus"))
        ):
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


def _is_mix_and_master_chain_item(v: Any) -> bool:
    r = _as_record(v)
    if not r:
        return False
    return (
        _is_finite_num(r.get("order"))
        and _is_str(r.get("device"))
        and _is_device_family(r.get("deviceFamily"))
        and _is_str(r.get("trackContext"))
        and _is_workflow_stage(r.get("workflowStage"))
        and _is_str(r.get("parameter"))
        and _is_str(r.get("value"))
        and _is_str(r.get("reason"))
    )


def _is_mix_and_master_chain(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        if not _is_mix_and_master_chain_item(item):
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
        and _is_secret_sauce_workflow_steps(r.get("workflowSteps"))
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


def _is_ableton_recommendation_item(v: Any) -> bool:
    r = _as_record(v)
    if not r:
        return False
    return (
        _is_str(r.get("device"))
        and _is_device_family(r.get("deviceFamily"))
        and _is_str(r.get("trackContext"))
        and _is_workflow_stage(r.get("workflowStage"))
        and _is_recommendation_category(r.get("category"))
        and _is_str(r.get("parameter"))
        and _is_str(r.get("value"))
        and _is_str(r.get("reason"))
        and _is_str(r.get("advancedTip"))
    )


def _is_ableton_recommendations(v: Any) -> bool:
    if not isinstance(v, list):
        return False
    for item in v:
        if not _is_ableton_recommendation_item(item):
            return False
    return True


def _is_valid_phase2_shape(data: Any) -> bool:
    """Mirrors isPhase2Result() in geminiPhase2Client.ts."""
    r = _as_record(data)
    if not r:
        return False
    return (
        _is_str(r.get("trackCharacter"))
        and _is_project_setup(r.get("projectSetup"))
        and _is_track_layout(r.get("trackLayout"))
        and _is_routing_blueprint(r.get("routingBlueprint"))
        and _is_warp_guide(r.get("warpGuide"))
        and _is_detected_characteristics(r.get("detectedCharacteristics"))
        and (r.get("audioObservations") is None or _is_audio_observations(r.get("audioObservations")))
        and (r.get("styleProfile") is None or _is_style_profile(r.get("styleProfile")))
        and _is_arrangement_overview(r.get("arrangementOverview"))
        and _is_sonic_elements(r.get("sonicElements"))
        and _is_mix_and_master_chain(r.get("mixAndMasterChain"))
        and _is_secret_sauce(r.get("secretSauce"))
        and _is_confidence_notes(r.get("confidenceNotes"))
        and _is_ableton_recommendations(r.get("abletonRecommendations"))
    )


def _sanitize_optional_phase2_fields(
    data: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sanitized = dict(data)
    warnings: list[dict[str, Any]] = []
    if "audioObservations" in sanitized and not _is_audio_observations(
        sanitized.get("audioObservations")
    ):
        sanitized.pop("audioObservations", None)
    if "styleProfile" in sanitized and not _is_style_profile(sanitized.get("styleProfile")):
        dropped = sanitized.pop("styleProfile", None)
        warnings.append(
            _build_phase2_validation_warning(
                code="DROPPED_INVALID_STYLE_PROFILE",
                path="styleProfile",
                message="Dropped styleProfile because the nested shape was invalid.",
                original_value=_stringify_warning_value(dropped),
                drop_reason="Invalid nested styleProfile shape.",
            )
        )
    return sanitized, warnings


_PHASE2_DEBUG_SHAPE_ISSUE_LIMIT = 16
_PHASE2_SALVAGE_WARNING_CODES = {"COERCED_ENUM_VALUE", "DROPPED_INVALID_ARRAY_ITEM", "BACKFILLED_FIELD"}
_PHASE2_SALVAGE_REQUIRED_ARRAYS = {"abletonRecommendations", "mixAndMasterChain"}


def _stringify_warning_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _collect_mix_and_master_chain_item_issues(item: Any, path: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    record = _as_record(item)
    if record is None:
        return [{"path": path, "message": f"Expected object but got {_type_label(item)}."}]
    if not _is_finite_num(record.get("order")):
        issues.append({"path": f"{path}.order", "message": "Expected finite number."})
    if not _is_str(record.get("device")):
        issues.append({"path": f"{path}.device", "message": "Expected string."})
    if not _is_device_family(record.get("deviceFamily")):
        issues.append(
            {
                "path": f"{path}.deviceFamily",
                "message": (
                    f"Value '{record.get('deviceFamily')}' is not allowed. Expected one of "
                    f"{sorted(_ALLOWED_LIVE12_DEVICE_FAMILIES)}."
                ),
            }
        )
    if not _is_str(record.get("trackContext")):
        issues.append({"path": f"{path}.trackContext", "message": "Expected string."})
    if not _is_workflow_stage(record.get("workflowStage")):
        issues.append(
            {
                "path": f"{path}.workflowStage",
                "message": (
                    f"Value '{record.get('workflowStage')}' is not allowed. Expected one of "
                    f"{sorted(_ALLOWED_PHASE2_WORKFLOW_STAGES)}."
                ),
            }
        )
    if not _is_str(record.get("parameter")):
        issues.append({"path": f"{path}.parameter", "message": "Expected string."})
    if not _is_str(record.get("value")):
        issues.append({"path": f"{path}.value", "message": "Expected string."})
    if not _is_str(record.get("reason")):
        issues.append({"path": f"{path}.reason", "message": "Expected string."})
    return issues


def _collect_ableton_recommendation_item_issues(item: Any, path: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    record = _as_record(item)
    if record is None:
        return [{"path": path, "message": f"Expected object but got {_type_label(item)}."}]
    if not _is_str(record.get("device")):
        issues.append({"path": f"{path}.device", "message": "Expected string."})
    if not _is_device_family(record.get("deviceFamily")):
        issues.append(
            {
                "path": f"{path}.deviceFamily",
                "message": (
                    f"Value '{record.get('deviceFamily')}' is not allowed. Expected one of "
                    f"{sorted(_ALLOWED_LIVE12_DEVICE_FAMILIES)}."
                ),
            }
        )
    if not _is_str(record.get("trackContext")):
        issues.append({"path": f"{path}.trackContext", "message": "Expected string."})
    if not _is_workflow_stage(record.get("workflowStage")):
        issues.append(
            {
                "path": f"{path}.workflowStage",
                "message": (
                    f"Value '{record.get('workflowStage')}' is not allowed. Expected one of "
                    f"{sorted(_ALLOWED_PHASE2_WORKFLOW_STAGES)}."
                ),
            }
        )
    if not _is_recommendation_category(record.get("category")):
        issues.append(
            {
                "path": f"{path}.category",
                "message": (
                    f"Value '{record.get('category')}' is not allowed. Expected one of "
                    f"{sorted(_ALLOWED_PHASE2_RECOMMENDATION_CATEGORIES)}."
                ),
            }
        )
    if not _is_str(record.get("parameter")):
        issues.append({"path": f"{path}.parameter", "message": "Expected string."})
    if not _is_str(record.get("value")):
        issues.append({"path": f"{path}.value", "message": "Expected string."})
    if not _is_str(record.get("reason")):
        issues.append({"path": f"{path}.reason", "message": "Expected string."})
    if not _is_str(record.get("advancedTip")):
        issues.append({"path": f"{path}.advancedTip", "message": "Expected string."})
    return issues


def _coerce_enum_fields(
    normalized: dict[str, Any],
    *,
    base_path: str,
    fields: tuple[tuple[str, frozenset[str], dict[str, str]], ...],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for field, allowed, coercion_map in fields:
        value = normalized.get(field)
        if isinstance(value, str) and value not in allowed:
            coerced = coercion_map.get(value)
            if coerced is not None:
                normalized[field] = coerced
                warnings.append(
                    _build_phase2_validation_warning(
                        code="COERCED_ENUM_VALUE",
                        path=f"{base_path}.{field}",
                        message=f"Coerced {field} '{value}' to '{coerced}' for {base_path.split('[')[0]}.",
                        original_value=value,
                        coerced_value=coerced,
                    )
                )
    return warnings


_RECOMMENDATION_ENUM_FIELDS: tuple[tuple[str, frozenset[str], dict[str, str]], ...] = (
    ("deviceFamily", frozenset(_ALLOWED_LIVE12_DEVICE_FAMILIES), _DEVICE_FAMILY_COERCION),
    ("workflowStage", frozenset(_ALLOWED_PHASE2_WORKFLOW_STAGES), _WORKFLOW_STAGE_COERCION),
    ("category", frozenset(_ALLOWED_PHASE2_RECOMMENDATION_CATEGORIES), _RECOMMENDATION_CATEGORY_COERCION),
)

_MIX_CHAIN_ENUM_FIELDS: tuple[tuple[str, frozenset[str], dict[str, str]], ...] = (
    ("deviceFamily", frozenset(_ALLOWED_LIVE12_DEVICE_FAMILIES), _DEVICE_FAMILY_COERCION),
    ("workflowStage", frozenset(_ALLOWED_PHASE2_WORKFLOW_STAGES), _WORKFLOW_STAGE_COERCION),
)


def _normalize_phase2_recommendation_item(
    item: Any,
    *,
    index: int,
) -> tuple[Any, list[dict[str, Any]]]:
    record = _as_record(item)
    if record is None:
        return item, []
    normalized = dict(record)
    warnings = _coerce_enum_fields(
        normalized,
        base_path=f"abletonRecommendations[{index}]",
        fields=_RECOMMENDATION_ENUM_FIELDS,
    )
    if not _is_str(normalized.get("advancedTip")) and _is_str(normalized.get("reason")):
        normalized["advancedTip"] = normalized["reason"]
        warnings.append(
            _build_phase2_validation_warning(
                code="BACKFILLED_FIELD",
                path=f"abletonRecommendations[{index}].advancedTip",
                message="Backfilled missing advancedTip from reason.",
                original_value=None,
                coerced_value=normalized["reason"],
            )
        )
    return normalized, warnings


def _normalize_mix_chain_item(
    item: Any,
    *,
    index: int,
) -> tuple[Any, list[dict[str, Any]]]:
    record = _as_record(item)
    if record is None:
        return item, []
    normalized = dict(record)
    warnings = _coerce_enum_fields(
        normalized,
        base_path=f"mixAndMasterChain[{index}]",
        fields=_MIX_CHAIN_ENUM_FIELDS,
    )
    return normalized, warnings


def _normalize_track_context_value(
    value: Any,
    *,
    path: str,
) -> tuple[Any, list[dict[str, Any]]]:
    if not isinstance(value, str):
        return value, []
    if not value.startswith("Return: "):
        return value, []
    normalized = f"Return:{value[len('Return: '):].strip()}"
    if normalized == value or normalized == "Return:":
        return value, []
    return normalized, [
        _build_phase2_validation_warning(
            code="COERCED_TRACK_CONTEXT",
            path=path,
            message=(
                f"Coerced trackContext '{value}' to '{normalized}' to match the "
                "required Return:<name> format."
            ),
            original_value=value,
            coerced_value=normalized,
        )
    ]


def _declared_return_names(data: dict[str, Any]) -> list[str]:
    routing_blueprint = _as_record(data.get("routingBlueprint"))
    returns = routing_blueprint.get("returns") if routing_blueprint else None
    if not isinstance(returns, list):
        return []
    names: list[str] = []
    for item in returns:
        record = _as_record(item)
        if record and _is_str(record.get("name")):
            names.append(record["name"])
    return names


def _repair_return_track_context(
    value: str,
    *,
    path: str,
    declared_returns: list[str],
) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(value, str) or not value.startswith("Return:"):
        return value, []
    suffix = value[len("Return:"):]
    if not suffix:
        return value, []
    exact_set = {f"Return:{name}" for name in declared_returns}
    if value in exact_set:
        return value, []
    # Case-insensitive exact match
    suffix_lower = suffix.lower()
    ci_matches = [name for name in declared_returns if suffix_lower == name.lower()]
    if len(ci_matches) == 1:
        repaired = f"Return:{ci_matches[0]}"
        return repaired, [
            _build_phase2_validation_warning(
                code="COERCED_TRACK_CONTEXT",
                path=path,
                message=(
                    f"Coerced trackContext '{value}' to '{repaired}' by matching "
                    "against declared routingBlueprint return names."
                ),
                original_value=value,
                coerced_value=repaired,
            )
        ]
    # Substring match (suffix is a substring of a declared return name)
    sub_matches = [
        name for name in declared_returns if suffix_lower in name.lower()
    ]
    if len(sub_matches) == 1:
        repaired = f"Return:{sub_matches[0]}"
        return repaired, [
            _build_phase2_validation_warning(
                code="COERCED_TRACK_CONTEXT",
                path=path,
                message=(
                    f"Coerced trackContext '{value}' to '{repaired}' by matching "
                    "against declared routingBlueprint return names."
                ),
                original_value=value,
                coerced_value=repaired,
            )
        ]
    return value, []


def _salvage_phase2_array_items(
    items: Any,
    *,
    array_path: str,
    item_validator: Callable[[Any], bool],
    item_issue_collector: Callable[[Any, str], list[dict[str, str]]],
) -> tuple[Any, list[dict[str, Any]], bool]:
    if not isinstance(items, list):
        return items, [], False

    salvaged = False
    warnings: list[dict[str, Any]] = []
    kept_items: list[Any] = []
    for index, item in enumerate(items):
        item_path = f"{array_path}[{index}]"
        if item_validator(item):
            kept_items.append(item)
            continue
        salvaged = True
        issues = item_issue_collector(item, item_path)
        if issues:
            issue_path = issues[0].get("path", item_path)
            issue_field = issue_path.split(".")[-1] if "." in issue_path else issue_path
            drop_reason = f"{issue_field}: {issues[0]['message']}"
        else:
            drop_reason = "Item failed strict validation."
        warnings.append(
            _build_phase2_validation_warning(
                code="DROPPED_INVALID_ARRAY_ITEM",
                path=item_path,
                message=f"Dropped invalid {array_path} item after bounded salvage.",
                original_value=_stringify_warning_value(item),
                drop_reason=drop_reason,
            )
        )
    return kept_items, warnings, salvaged


def _normalize_and_salvage_phase2_result(
    data: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    normalized = dict(data)
    warnings: list[dict[str, Any]] = []
    emptied_required_arrays: set[str] = set()
    declared_returns = _declared_return_names(data)

    recommendations = normalized.get("abletonRecommendations")
    if isinstance(recommendations, list):
        normalized_recommendations: list[Any] = []
        for index, item in enumerate(recommendations):
            normalized_item, item_warnings = _normalize_phase2_recommendation_item(
                item,
                index=index,
            )
            normalized_record = _as_record(normalized_item)
            if normalized_record is not None:
                track_context, track_context_warnings = _normalize_track_context_value(
                    normalized_record.get("trackContext"),
                    path=f"abletonRecommendations[{index}].trackContext",
                )
                track_context, repair_warnings = _repair_return_track_context(
                    track_context,
                    path=f"abletonRecommendations[{index}].trackContext",
                    declared_returns=declared_returns,
                )
                normalized_item = dict(normalized_record)
                normalized_item["trackContext"] = track_context
                warnings.extend(track_context_warnings)
                warnings.extend(repair_warnings)
            normalized_recommendations.append(normalized_item)
            warnings.extend(item_warnings)
        normalized["abletonRecommendations"] = normalized_recommendations

    mix_chain = normalized.get("mixAndMasterChain")
    if isinstance(mix_chain, list):
        normalized_mix_chain: list[Any] = []
        for index, item in enumerate(mix_chain):
            normalized_item, item_enum_warnings = _normalize_mix_chain_item(
                item, index=index,
            )
            warnings.extend(item_enum_warnings)
            record = _as_record(normalized_item)
            if record is None:
                normalized_mix_chain.append(normalized_item)
                continue
            normalized_item = dict(record)
            track_context, track_context_warnings = _normalize_track_context_value(
                normalized_item.get("trackContext"),
                path=f"mixAndMasterChain[{index}].trackContext",
            )
            track_context, repair_warnings = _repair_return_track_context(
                track_context,
                path=f"mixAndMasterChain[{index}].trackContext",
                declared_returns=declared_returns,
            )
            normalized_item["trackContext"] = track_context
            normalized_mix_chain.append(normalized_item)
            warnings.extend(track_context_warnings)
            warnings.extend(repair_warnings)
        normalized["mixAndMasterChain"] = normalized_mix_chain

    secret_sauce = _as_record(normalized.get("secretSauce"))
    workflow_steps = secret_sauce.get("workflowSteps") if secret_sauce else None
    if isinstance(workflow_steps, list):
        normalized_steps: list[Any] = []
        for index, item in enumerate(workflow_steps):
            record = _as_record(item)
            if record is None:
                normalized_steps.append(item)
                continue
            normalized_item = dict(record)
            track_context, track_context_warnings = _normalize_track_context_value(
                normalized_item.get("trackContext"),
                path=f"secretSauce.workflowSteps[{index}].trackContext",
            )
            track_context, repair_warnings = _repair_return_track_context(
                track_context,
                path=f"secretSauce.workflowSteps[{index}].trackContext",
                declared_returns=declared_returns,
            )
            normalized_item["trackContext"] = track_context
            normalized_steps.append(normalized_item)
            warnings.extend(track_context_warnings)
            warnings.extend(repair_warnings)
        normalized_secret_sauce = dict(secret_sauce)
        normalized_secret_sauce["workflowSteps"] = normalized_steps
        normalized["secretSauce"] = normalized_secret_sauce

    for array_path, item_validator, item_issue_collector in (
        (
            "abletonRecommendations",
            _is_ableton_recommendation_item,
            _collect_ableton_recommendation_item_issues,
        ),
        (
            "mixAndMasterChain",
            _is_mix_and_master_chain_item,
            _collect_mix_and_master_chain_item_issues,
        ),
    ):
        salvaged_items, item_warnings, salvaged = _salvage_phase2_array_items(
            normalized.get(array_path),
            array_path=array_path,
            item_validator=item_validator,
            item_issue_collector=item_issue_collector,
        )
        if salvaged:
            normalized[array_path] = salvaged_items
            if isinstance(salvaged_items, list) and len(salvaged_items) == 0:
                emptied_required_arrays.add(array_path)
        warnings.extend(item_warnings)

    # Audit final round: rewrite Gemini's "by recreates / by shapes / by
    # generates / ..." → "by recreating / by shaping / by generating / ...".
    # The prompt instruction added earlier didn't take; this is the salvage
    # post-process. Runs in-place on `normalized`; no validation warnings
    # emitted because grammar repair is not a contract failure.
    _apply_phase2_grammar_fixes(normalized)

    return normalized, warnings, emptied_required_arrays


def _type_label(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def _append_shape_issue(
    issues: list[dict[str, str]],
    *,
    path: str,
    message: str,
) -> None:
    if len(issues) >= _PHASE2_DEBUG_SHAPE_ISSUE_LIMIT:
        return
    issues.append({"path": path, "message": message})


def _collect_phase2_shape_issues(data: Any) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    def expect_record(value: Any, path: str) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            _append_shape_issue(
                issues,
                path=path,
                message=f"Expected object but got {_type_label(value)}.",
            )
            return None
        return value

    def expect_list(value: Any, path: str) -> list[Any] | None:
        if not isinstance(value, list):
            _append_shape_issue(
                issues,
                path=path,
                message=f"Expected array but got {_type_label(value)}.",
            )
            return None
        return value

    def expect_str(value: Any, path: str) -> None:
        if not isinstance(value, str):
            _append_shape_issue(
                issues,
                path=path,
                message=f"Expected string but got {_type_label(value)}.",
            )

    def expect_num(value: Any, path: str) -> None:
        if not _is_finite_num(value):
            _append_shape_issue(
                issues,
                path=path,
                message=f"Expected finite number but got {_type_label(value)}.",
            )

    def expect_optional_str(value: Any, path: str) -> None:
        if value is not None and not isinstance(value, str):
            _append_shape_issue(
                issues,
                path=path,
                message=f"Expected string or null but got {_type_label(value)}.",
            )

    def expect_string_list(value: Any, path: str) -> None:
        items = expect_list(value, path)
        if items is None:
            return
        for index, item in enumerate(items):
            if not isinstance(item, str):
                _append_shape_issue(
                    issues,
                    path=f"{path}[{index}]",
                    message=f"Expected string but got {_type_label(item)}.",
                )

    def expect_number_list(value: Any, path: str) -> None:
        items = expect_list(value, path)
        if items is None:
            return
        for index, item in enumerate(items):
            if not _is_finite_num(item):
                _append_shape_issue(
                    issues,
                    path=f"{path}[{index}]",
                    message=f"Expected finite number but got {_type_label(item)}.",
                )

    def expect_enum(value: Any, path: str, allowed: set[str]) -> None:
        if not isinstance(value, str):
            _append_shape_issue(
                issues,
                path=path,
                message=f"Expected one of {sorted(allowed)} but got {_type_label(value)}.",
            )
            return
        if value not in allowed:
            _append_shape_issue(
                issues,
                path=path,
                message=f"Value '{value}' is not allowed. Expected one of {sorted(allowed)}.",
            )

    def validate_track_grounding(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        expect_string_list(record.get("phase1Fields"), f"{path}.phase1Fields")
        if "segmentIndexes" in record and record.get("segmentIndexes") is not None:
            expect_number_list(record.get("segmentIndexes"), f"{path}.segmentIndexes")

    def validate_project_setup(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        expect_num(record.get("tempoBpm"), f"{path}.tempoBpm")
        expect_str(record.get("timeSignature"), f"{path}.timeSignature")
        expect_num(record.get("sampleRate"), f"{path}.sampleRate")
        expect_num(record.get("bitDepth"), f"{path}.bitDepth")
        expect_str(record.get("headroomTarget"), f"{path}.headroomTarget")
        expect_str(record.get("sessionGoal"), f"{path}.sessionGoal")

    def validate_track_layout(value: Any, path: str) -> None:
        items = expect_list(value, path)
        if items is None:
            return
        for index, item in enumerate(items):
            item_path = f"{path}[{index}]"
            record = expect_record(item, item_path)
            if record is None:
                continue
            expect_num(record.get("order"), f"{item_path}.order")
            expect_str(record.get("name"), f"{item_path}.name")
            expect_str(record.get("type"), f"{item_path}.type")
            expect_str(record.get("purpose"), f"{item_path}.purpose")
            validate_track_grounding(record.get("grounding"), f"{item_path}.grounding")

    def validate_routing_blueprint(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        expect_optional_str(record.get("sidechainSource"), f"{path}.sidechainSource")
        expect_string_list(record.get("sidechainTargets"), f"{path}.sidechainTargets")
        returns = expect_list(record.get("returns"), f"{path}.returns")
        if returns is not None:
            for index, item in enumerate(returns):
                item_path = f"{path}.returns[{index}]"
                return_record = expect_record(item, item_path)
                if return_record is None:
                    continue
                expect_str(return_record.get("name"), f"{item_path}.name")
                expect_str(return_record.get("purpose"), f"{item_path}.purpose")
                expect_string_list(return_record.get("sendSources"), f"{item_path}.sendSources")
                expect_str(return_record.get("deviceFocus"), f"{item_path}.deviceFocus")
                expect_str(return_record.get("levelGuidance"), f"{item_path}.levelGuidance")
        expect_string_list(record.get("notes"), f"{path}.notes")

    def validate_warp_target(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        expect_enum(record.get("warpMode"), f"{path}.warpMode", _ALLOWED_PHASE2_WARP_MODES)
        expect_optional_str(record.get("settings"), f"{path}.settings")
        expect_str(record.get("reason"), f"{path}.reason")

    def validate_warp_guide(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        validate_warp_target(record.get("fullTrack"), f"{path}.fullTrack")
        validate_warp_target(record.get("drums"), f"{path}.drums")
        validate_warp_target(record.get("bass"), f"{path}.bass")
        validate_warp_target(record.get("melodic"), f"{path}.melodic")
        if record.get("vocals") is not None:
            validate_warp_target(record.get("vocals"), f"{path}.vocals")
        expect_str(record.get("rationale"), f"{path}.rationale")

    def validate_detected_characteristics(value: Any, path: str) -> None:
        items = expect_list(value, path)
        if items is None:
            return
        for index, item in enumerate(items):
            item_path = f"{path}[{index}]"
            record = expect_record(item, item_path)
            if record is None:
                continue
            expect_str(record.get("name"), f"{item_path}.name")
            expect_enum(record.get("confidence"), f"{item_path}.confidence", {"HIGH", "MED", "LOW"})
            expect_str(record.get("explanation"), f"{item_path}.explanation")

    def validate_audio_observations(value: Any, path: str) -> None:
        if value is None:
            return
        record = expect_record(value, path)
        if record is None:
            return
        expect_str(record.get("soundDesignFingerprint"), f"{path}.soundDesignFingerprint")
        elements = expect_list(record.get("elementCharacter"), f"{path}.elementCharacter")
        if elements is not None:
            for index, item in enumerate(elements):
                item_path = f"{path}.elementCharacter[{index}]"
                element_record = expect_record(item, item_path)
                if element_record is None:
                    continue
                expect_str(element_record.get("element"), f"{item_path}.element")
                expect_str(element_record.get("description"), f"{item_path}.description")
        expect_string_list(record.get("productionSignatures"), f"{path}.productionSignatures")
        expect_str(record.get("mixContext"), f"{path}.mixContext")

    def validate_style_profile(value: Any, path: str) -> None:
        if value is None:
            return
        record = expect_record(value, path)
        if record is None:
            return
        expect_str(record.get("genre"), f"{path}.genre")
        expect_optional_str(record.get("subGenre"), f"{path}.subGenre")
        expect_string_list(record.get("mood"), f"{path}.mood")
        expect_string_list(record.get("instruments"), f"{path}.instruments")
        expect_string_list(record.get("productionTechniques"), f"{path}.productionTechniques")
        expect_str(record.get("description"), f"{path}.description")
        expect_str(record.get("generationPrompt"), f"{path}.generationPrompt")
        measurements = expect_record(
            record.get("authoritativeMeasurements"),
            f"{path}.authoritativeMeasurements",
        )
        if measurements is None:
            return
        if measurements.get("bpm") is not None:
            expect_num(measurements.get("bpm"), f"{path}.authoritativeMeasurements.bpm")
        expect_optional_str(measurements.get("key"), f"{path}.authoritativeMeasurements.key")
        expect_optional_str(
            measurements.get("timeSignature"),
            f"{path}.authoritativeMeasurements.timeSignature",
        )

    def validate_arrangement_overview(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        expect_str(record.get("summary"), f"{path}.summary")
        segments = expect_list(record.get("segments"), f"{path}.segments")
        if segments is not None:
            for index, item in enumerate(segments):
                item_path = f"{path}.segments[{index}]"
                segment_record = expect_record(item, item_path)
                if segment_record is None:
                    continue
                expect_num(segment_record.get("index"), f"{item_path}.index")
                expect_num(segment_record.get("startTime"), f"{item_path}.startTime")
                expect_num(segment_record.get("endTime"), f"{item_path}.endTime")
                if segment_record.get("lufs") is not None:
                    expect_num(segment_record.get("lufs"), f"{item_path}.lufs")
                expect_str(segment_record.get("description"), f"{item_path}.description")
                expect_optional_str(segment_record.get("spectralNote"), f"{item_path}.spectralNote")
                expect_str(segment_record.get("sceneName"), f"{item_path}.sceneName")
                expect_str(segment_record.get("abletonAction"), f"{item_path}.abletonAction")
                expect_str(segment_record.get("automationFocus"), f"{item_path}.automationFocus")
        expect_optional_str(record.get("noveltyNotes"), f"{path}.noveltyNotes")

    def validate_sonic_elements(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        for key in ("kick", "bass", "melodicArp", "grooveAndTiming", "effectsAndTexture"):
            expect_str(record.get(key), f"{path}.{key}")
        for key in ("widthAndStereo", "harmonicContent"):
            if key in record:
                expect_optional_str(record.get(key), f"{path}.{key}")

    def validate_mix_chain(value: Any, path: str) -> None:
        items = expect_list(value, path)
        if items is None:
            return
        for index, item in enumerate(items):
            item_path = f"{path}[{index}]"
            record = expect_record(item, item_path)
            if record is None:
                continue
            expect_num(record.get("order"), f"{item_path}.order")
            expect_str(record.get("device"), f"{item_path}.device")
            expect_enum(record.get("deviceFamily"), f"{item_path}.deviceFamily", _ALLOWED_LIVE12_DEVICE_FAMILIES)
            expect_str(record.get("trackContext"), f"{item_path}.trackContext")
            expect_enum(record.get("workflowStage"), f"{item_path}.workflowStage", _ALLOWED_PHASE2_WORKFLOW_STAGES)
            expect_str(record.get("parameter"), f"{item_path}.parameter")
            expect_str(record.get("value"), f"{item_path}.value")
            expect_str(record.get("reason"), f"{item_path}.reason")

    def validate_secret_sauce(value: Any, path: str) -> None:
        record = expect_record(value, path)
        if record is None:
            return
        expect_str(record.get("title"), f"{path}.title")
        if "icon" in record:
            expect_optional_str(record.get("icon"), f"{path}.icon")
        expect_str(record.get("explanation"), f"{path}.explanation")
        expect_string_list(record.get("implementationSteps"), f"{path}.implementationSteps")
        workflow_steps = expect_list(record.get("workflowSteps"), f"{path}.workflowSteps")
        if workflow_steps is not None:
            for index, item in enumerate(workflow_steps):
                item_path = f"{path}.workflowSteps[{index}]"
                step_record = expect_record(item, item_path)
                if step_record is None:
                    continue
                expect_num(step_record.get("step"), f"{item_path}.step")
                expect_str(step_record.get("trackContext"), f"{item_path}.trackContext")
                expect_str(step_record.get("device"), f"{item_path}.device")
                expect_str(step_record.get("parameter"), f"{item_path}.parameter")
                expect_str(step_record.get("value"), f"{item_path}.value")
                expect_str(step_record.get("instruction"), f"{item_path}.instruction")
                expect_str(
                    step_record.get("measurementJustification"),
                    f"{item_path}.measurementJustification",
                )

    def validate_confidence_notes(value: Any, path: str) -> None:
        items = expect_list(value, path)
        if items is None:
            return
        for index, item in enumerate(items):
            item_path = f"{path}[{index}]"
            record = expect_record(item, item_path)
            if record is None:
                continue
            expect_str(record.get("field"), f"{item_path}.field")
            expect_str(record.get("value"), f"{item_path}.value")
            expect_str(record.get("reason"), f"{item_path}.reason")

    def validate_ableton_recommendations(value: Any, path: str) -> None:
        items = expect_list(value, path)
        if items is None:
            return
        for index, item in enumerate(items):
            item_path = f"{path}[{index}]"
            record = expect_record(item, item_path)
            if record is None:
                continue
            expect_str(record.get("device"), f"{item_path}.device")
            expect_enum(record.get("deviceFamily"), f"{item_path}.deviceFamily", _ALLOWED_LIVE12_DEVICE_FAMILIES)
            expect_str(record.get("trackContext"), f"{item_path}.trackContext")
            expect_enum(record.get("workflowStage"), f"{item_path}.workflowStage", _ALLOWED_PHASE2_WORKFLOW_STAGES)
            expect_enum(record.get("category"), f"{item_path}.category", _ALLOWED_PHASE2_RECOMMENDATION_CATEGORIES)
            expect_str(record.get("parameter"), f"{item_path}.parameter")
            expect_str(record.get("value"), f"{item_path}.value")
            expect_str(record.get("reason"), f"{item_path}.reason")
            expect_str(record.get("advancedTip"), f"{item_path}.advancedTip")

    record = expect_record(data, "root")
    if record is None:
        return issues

    expect_str(record.get("trackCharacter"), "trackCharacter")
    validate_project_setup(record.get("projectSetup"), "projectSetup")
    validate_track_layout(record.get("trackLayout"), "trackLayout")
    validate_routing_blueprint(record.get("routingBlueprint"), "routingBlueprint")
    validate_warp_guide(record.get("warpGuide"), "warpGuide")
    validate_detected_characteristics(record.get("detectedCharacteristics"), "detectedCharacteristics")
    validate_audio_observations(record.get("audioObservations"), "audioObservations")
    validate_style_profile(record.get("styleProfile"), "styleProfile")
    validate_arrangement_overview(record.get("arrangementOverview"), "arrangementOverview")
    validate_sonic_elements(record.get("sonicElements"), "sonicElements")
    validate_mix_chain(record.get("mixAndMasterChain"), "mixAndMasterChain")
    validate_secret_sauce(record.get("secretSauce"), "secretSauce")
    validate_confidence_notes(record.get("confidenceNotes"), "confidenceNotes")
    validate_ableton_recommendations(record.get("abletonRecommendations"), "abletonRecommendations")
    return issues


def _parse_phase2_result_debug(response_text: str | None) -> dict[str, Any]:
    raw = (response_text or "").strip()
    if not raw:
        return {
            "result": None,
            "skipMessage": "Phase 2 advisory skipped because Gemini returned an empty response.",
            "skipReason": "empty_response",
            "parseOutcome": "skipped",
            "rawResponseText": raw,
            "shapeIssues": [],
            "validationWarnings": [],
        }
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            "result": None,
            "skipMessage": "Phase 2 advisory skipped because Gemini returned invalid JSON.",
            "skipReason": "invalid_json",
            "parseOutcome": "skipped",
            "rawResponseText": raw,
            "shapeIssues": [],
            "parseError": str(exc),
            "validationWarnings": [],
        }
    validation_warnings: list[dict[str, Any]] = []
    emptied_required_arrays: set[str] = set()
    record = _as_record(parsed)
    if record is not None:
        parsed, sanitize_warnings = _sanitize_optional_phase2_fields(record)
        parsed, salvage_warnings, emptied_required_arrays = _normalize_and_salvage_phase2_result(
            parsed
        )
        validation_warnings = sanitize_warnings + salvage_warnings
    shape_issues = _collect_phase2_shape_issues(parsed)
    for array_path in sorted(emptied_required_arrays):
        _append_shape_issue(
            shape_issues,
            path=array_path,
            message="Required array became empty after bounded salvage.",
        )
    if shape_issues:
        return {
            "result": None,
            "skipMessage": "Phase 2 advisory skipped because Gemini returned an invalid response shape.",
            "skipReason": "invalid_shape",
            "parseOutcome": "skipped",
            "rawResponseText": raw,
            "shapeIssues": shape_issues,
            "validationWarnings": validation_warnings,
        }
    return {
        "result": parsed,
        "skipMessage": None,
        "skipReason": None,
        "parseOutcome": "valid",
        "rawResponseText": raw,
        "shapeIssues": [],
        "validationWarnings": validation_warnings,
    }


def _parse_phase2_result(
    response_text: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Returns (result, skip_message). Mirrors parsePhase2Result() in geminiPhase2Client.ts.

    Skip cases return 200 with phase2=null — they are NOT errors.
    """
    debug = _parse_phase2_result_debug(response_text)
    return debug["result"], debug["skipMessage"]


def _build_phase2_validation_warning(
    *,
    code: str,
    path: str,
    message: str,
    original_value: str | None = None,
    coerced_value: str | None = None,
    drop_reason: str | None = None,
) -> dict[str, Any]:
    warning = {
        "code": code,
        "path": path,
        "message": message,
    }
    if original_value is not None:
        warning["originalValue"] = original_value
    if coerced_value is not None:
        warning["coercedValue"] = coerced_value
    if drop_reason is not None:
        warning["dropReason"] = drop_reason
    return warning


def _finalize_style_profile_authoritative_measurements(
    interpretation_result: dict[str, Any],
    measurement_result: dict[str, Any],
) -> list[dict[str, Any]]:
    style_profile = _as_record(interpretation_result.get("styleProfile"))
    if style_profile is None:
        return []

    authoritative = _as_record(style_profile.get("authoritativeMeasurements"))
    if authoritative is None:
        authoritative = {}
        style_profile["authoritativeMeasurements"] = authoritative

    measured_values = {
        "bpm": _coerce_nullable_number(measurement_result.get("bpm")),
        "key": _coerce_nullable_string(measurement_result.get("key")),
        "timeSignature": _coerce_nullable_string(measurement_result.get("timeSignature")),
    }

    warnings: list[dict[str, Any]] = []
    for field, measured_value in measured_values.items():
        current_value = authoritative.get(field)
        if current_value != measured_value:
            warnings.append(
                _build_phase2_validation_warning(
                    code="AUTHORITATIVE_MEASUREMENT_OVERRIDDEN",
                    path=f"styleProfile.authoritativeMeasurements.{field}",
                    message=(
                        f"Overrode styleProfile.authoritativeMeasurements.{field} with "
                        "the authoritative Phase 1 measurement."
                    ),
                    original_value=_stringify_warning_value(current_value),
                    coerced_value=_stringify_warning_value(measured_value),
                )
            )
        authoritative[field] = measured_value

    interpretation_result["styleProfile"] = style_profile
    return warnings


def _validate_phase2_catalog_entry(
    *,
    warnings: list[dict[str, Any]],
    device: str,
    device_family: str | None,
    parameter: str,
    base_path: str,
) -> None:
    catalog_entry = LIVE12_DEVICE_LOOKUP.get(device)
    if catalog_entry is None:
        warnings.append(
            _build_phase2_validation_warning(
                code="UNKNOWN_DEVICE",
                path=f"{base_path}.device",
                message=f"Device '{device}' is not in the curated Live 12 catalog.",
            )
        )
        return

    expected_family = catalog_entry["family"]
    if device_family is not None and device_family != expected_family:
        warnings.append(
            _build_phase2_validation_warning(
                code="DEVICE_FAMILY_MISMATCH",
                path=f"{base_path}.deviceFamily",
                message=(
                    f"Device '{device}' is tagged as '{device_family}', "
                    f"but the catalog says '{expected_family}'."
                ),
            )
        )

    # Resolve aliases before membership check. parameterAliases is a
    # per-device map of {wrong-but-defensible-name: canonical-name}. The
    # alias only affects validation — the recommendation's emitted
    # `parameter` value is NOT mutated by this layer. Closes the long-form
    # naming bleed (instrument-side "Filter Resonance" misapplied to the
    # Auto Filter audio effect).
    alias_map = catalog_entry.get("parameterAliases") or {}
    canonical_parameter = alias_map.get(parameter, parameter)
    allowed_parameters = set(catalog_entry.get("allowedParameters", []))
    if canonical_parameter not in allowed_parameters:
        warnings.append(
            _build_phase2_validation_warning(
                code="UNKNOWN_PARAMETER",
                path=f"{base_path}.parameter",
                message=(
                    f"Parameter '{parameter}' is not allowed for device '{device}' "
                    "in the curated Live 12 catalog."
                ),
            )
        )


def _valid_track_contexts(phase2_result: dict[str, Any]) -> set[str]:
    contexts = {"Master"}
    track_layout = phase2_result.get("trackLayout")
    if isinstance(track_layout, list):
        for item in track_layout:
            record = _as_record(item)
            if record and _is_str(record.get("name")):
                contexts.add(record["name"])

    routing_blueprint = _as_record(phase2_result.get("routingBlueprint"))
    returns = routing_blueprint.get("returns") if routing_blueprint else None
    if isinstance(returns, list):
        for item in returns:
            record = _as_record(item)
            if record and _is_str(record.get("name")):
                contexts.add(f"Return:{record['name']}")
    return contexts


def _validate_track_context(
    *,
    warnings: list[dict[str, Any]],
    track_context: str,
    base_path: str,
    valid_contexts: set[str],
) -> None:
    if track_context in valid_contexts:
        return
    warnings.append(
        _build_phase2_validation_warning(
            code="UNKNOWN_TRACK_CONTEXT",
            path=f"{base_path}.trackContext",
            message=(
                f"Track context '{track_context}' does not match trackLayout names, "
                "Master, or any Return:<name> context."
            ),
        )
    )


def _validate_phase2_semantics(phase2_result: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    valid_contexts = _valid_track_contexts(phase2_result)

    for index, item in enumerate(phase2_result.get("mixAndMasterChain") or []):
        record = _as_record(item)
        if not record:
            continue
        base_path = f"mixAndMasterChain[{index}]"
        _validate_phase2_catalog_entry(
            warnings=warnings,
            device=str(record.get("device")),
            device_family=str(record.get("deviceFamily")),
            parameter=str(record.get("parameter")),
            base_path=base_path,
        )
        _validate_track_context(
            warnings=warnings,
            track_context=str(record.get("trackContext")),
            base_path=base_path,
            valid_contexts=valid_contexts,
        )

    for index, item in enumerate(phase2_result.get("abletonRecommendations") or []):
        record = _as_record(item)
        if not record:
            continue
        base_path = f"abletonRecommendations[{index}]"
        _validate_phase2_catalog_entry(
            warnings=warnings,
            device=str(record.get("device")),
            device_family=str(record.get("deviceFamily")),
            parameter=str(record.get("parameter")),
            base_path=base_path,
        )
        _validate_track_context(
            warnings=warnings,
            track_context=str(record.get("trackContext")),
            base_path=base_path,
            valid_contexts=valid_contexts,
        )

    workflow_steps = _as_record(phase2_result.get("secretSauce"))
    steps = workflow_steps.get("workflowSteps") if workflow_steps else None
    if isinstance(steps, list):
        for index, item in enumerate(steps):
            record = _as_record(item)
            if not record:
                continue
            base_path = f"secretSauce.workflowSteps[{index}]"
            _validate_phase2_catalog_entry(
                warnings=warnings,
                device=str(record.get("device")),
                device_family=None,
                parameter=str(record.get("parameter")),
                base_path=base_path,
            )
            _validate_track_context(
                warnings=warnings,
                track_context=str(record.get("trackContext")),
                base_path=base_path,
                valid_contexts=valid_contexts,
            )

    return warnings


def _walk_measurement_paths(value: Any, prefix: str, paths: set[str]) -> None:
    """Faithful port of walkForPaths() in apps/ui/src/services/phase2Validator.ts.

    Registers the dotted path of every nested key. For arrays, registers the
    array path itself and, for arrays of objects, descends into ``prefix.key``
    so a citation against an array-item field (e.g. ``noveltyPeaks.time``)
    resolves. Keeping this byte-for-byte equivalent to the frontend is what lets
    the two citation-existence checks agree.
    """
    if value is None:
        return
    if isinstance(value, list):
        if prefix:
            paths.add(prefix)
        for item in value:
            if isinstance(item, dict):
                for key in item:
                    sub_path = f"{prefix}.{key}" if prefix else key
                    _walk_measurement_paths(item[key], sub_path, paths)
        return
    if not isinstance(value, dict):
        if prefix:
            paths.add(prefix)
        return
    if prefix:
        paths.add(prefix)
    for key in value:
        sub_path = f"{prefix}.{key}" if prefix else key
        _walk_measurement_paths(value[key], sub_path, paths)


def _collect_measurement_field_paths(measurement_result: dict[str, Any]) -> set[str]:
    """Collect every concrete dotted path present in the measurement payload.

    Mirror of collectPhase1FieldPaths() in phase2Validator.ts.
    """
    paths: set[str] = set()
    _walk_measurement_paths(measurement_result, "", paths)
    return paths


def _validate_citation_paths_for_record(
    *,
    warnings: list[dict[str, Any]],
    record: dict[str, Any],
    base_path: str,
    allowed: set[str],
) -> None:
    phase1_fields = record.get("phase1Fields")
    if not isinstance(phase1_fields, list):
        return
    for cited in phase1_fields:
        if not isinstance(cited, str):
            continue
        normalized = cited.strip()
        if not normalized or normalized in allowed:
            continue
        warnings.append(
            _build_phase2_validation_warning(
                code="UNRESOLVED_CITATION_PATH",
                path=f"{base_path}.phase1Fields",
                message=(
                    f'phase1Fields entry "{normalized}" does not resolve to any path '
                    "present in the authoritative measurement payload."
                ),
                original_value=normalized,
            )
        )


def _validate_phase2_citation_paths(
    phase2_result: dict[str, Any],
    measurement_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Backend defense-in-depth mirror of the frontend's citation-existence check.

    For every recommendation that exposes a ``phase1Fields`` array, flag each
    cited dotted path that does not resolve against the authoritative
    measurement payload. WARNING-only — never reject and never raise; Phase 1
    authority means an invented citation is flagged, not failed.

    Coarser than the frontend's ``validatePhase1FieldCitations`` (which also
    flags missing/empty ``phase1Fields`` arrays as errors); the frontend remains
    authoritative for the rich consistency checks.
    """
    allowed = _collect_measurement_field_paths(measurement_result)
    warnings: list[dict[str, Any]] = []

    for index, item in enumerate(phase2_result.get("mixAndMasterChain") or []):
        record = _as_record(item)
        if record:
            _validate_citation_paths_for_record(
                warnings=warnings,
                record=record,
                base_path=f"mixAndMasterChain[{index}]",
                allowed=allowed,
            )

    for index, item in enumerate(phase2_result.get("abletonRecommendations") or []):
        record = _as_record(item)
        if record:
            _validate_citation_paths_for_record(
                warnings=warnings,
                record=record,
                base_path=f"abletonRecommendations[{index}]",
                allowed=allowed,
            )

    secret_sauce = _as_record(phase2_result.get("secretSauce"))
    steps = secret_sauce.get("workflowSteps") if secret_sauce else None
    if isinstance(steps, list):
        for index, item in enumerate(steps):
            record = _as_record(item)
            if record:
                _validate_citation_paths_for_record(
                    warnings=warnings,
                    record=record,
                    base_path=f"secretSauce.workflowSteps[{index}]",
                    allowed=allowed,
                )

    return warnings


def _is_string_array(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_stem_summary_bars(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        record = _as_record(item)
        if not record:
            return False
        if not (
            _is_finite_num(record.get("barStart"))
            and _is_finite_num(record.get("barEnd"))
            and _is_finite_num(record.get("startTime"))
            and _is_finite_num(record.get("endTime"))
            and _is_string_array(record.get("noteHypotheses"))
            and _is_string_array(record.get("scaleDegreeHypotheses"))
            and _is_str(record.get("rhythmicPattern"))
            and record.get("uncertaintyLevel") in ("LOW", "MED", "HIGH")
            and _is_str(record.get("uncertaintyReason"))
        ):
            return False
    return True


def _is_stem_summary_global_patterns(value: Any) -> bool:
    record = _as_record(value)
    if not record:
        return False
    return (
        _is_str(record.get("bassRole"))
        and _is_str(record.get("melodicRole"))
        and _is_str(record.get("pumpingOrModulation"))
        and isinstance(record.get("synthesisCharacter"), str)
        and bool(record.get("synthesisCharacter", "").strip())
        and isinstance(record.get("vocalPresence"), str)
        and bool(record.get("vocalPresence", "").strip())
        and isinstance(record.get("bassCharacter"), str)
        and bool(record.get("bassCharacter", "").strip())
    )


def _is_valid_stem_summary_shape(value: Any) -> bool:
    record = _as_record(value)
    if not record:
        return False
    return (
        _is_str(record.get("summary"))
        and _is_stem_summary_bars(record.get("bars"))
        and _is_stem_summary_global_patterns(record.get("globalPatterns"))
        and _is_string_array(record.get("uncertaintyFlags"))
    )


def _parse_stem_summary_result(
    response_text: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    raw = (response_text or "").strip()
    if not raw:
        return None, "Stem summary skipped because Gemini returned an empty response."
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None, "Stem summary skipped because Gemini returned invalid JSON."
    if not _is_valid_stem_summary_shape(parsed):
        return None, "Stem summary skipped because Gemini returned an invalid response shape."
    return parsed, None



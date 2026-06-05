"""Deterministic mock Phase 2 interpreter for the MOSS sidecar.

Pure stdlib. Produces a **full, schema-valid ``Phase2Result``** grounded in the
provided Phase 1 measurement JSON, citing only Phase 1 field paths that actually
resolve. This exists so the provider abstraction, the FastAPI sidecar, the unit
tests, and the citation-accuracy eval can all run end-to-end **with no model and
no GPU** — and so the schema/citation contract is exercised on every commit.

IMPORTANT — what this is and is NOT:
  - It IS a contract fixture: every required ``Phase2Result`` field is populated
    with shape-valid content, and every citation resolves against the supplied
    Phase 1 payload (so its citation accuracy is ~1.0 *by construction*).
  - It is NOT a quality proxy for the real MOSS-Audio model. The mock's
    citation accuracy says nothing about whether MOSS would cite correctly; it
    only proves the pipeline + scorer work. The real model path is licence-gated
    (see ``docs/PHASE2_PROVIDER.md``) and deliberately not wired.

Determinism: no randomness, no clock. Same Phase 1 in → same result out.
"""

from __future__ import annotations

from typing import Any


# Candidate top-level Phase 1 scalars to cite, in priority order. Only those
# present in the supplied payload are emitted, so citations always resolve.
_CITATION_CANDIDATES: tuple[str, ...] = (
    "bpm",
    "lufsIntegrated",
    "key",
    "lufsRange",
    "truePeak",
    "crestFactor",
    "timeSignature",
    "durationSeconds",
    "sampleRate",
    "danceability",
)


def _present(phase1: dict[str, Any], path: str) -> bool:
    """Does a dotted path resolve in the Phase 1 payload?

    Mirrors the descent semantics of
    ``server_phase2._collect_measurement_field_paths`` closely enough that any
    path this returns True for will also be accepted by
    ``_validate_phase2_citation_paths``: descend dict keys; for a list, treat the
    first dict element as the representative (array-item fields register under
    ``prefix.key``).
    """
    parts = path.split(".")
    node: Any = phase1
    for part in parts:
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and node and isinstance(node[0], dict) and part in node[0]:
            node = node[0][part]
        else:
            return False
    return True


def _citations(phase1: dict[str, Any], limit: int) -> list[str]:
    """Up to ``limit`` resolving citation paths, grounded in this Phase 1.

    Falls back to ``["bpm"]`` only if literally nothing resolves (defensive; a
    real Phase 1 always has ``bpm``). A non-empty list keeps the recommendation
    from tripping the frontend's "missing phase1Fields" check.
    """
    found = [path for path in _CITATION_CANDIDATES if _present(phase1, path)]
    # Add a couple of nested citations when the obvious sub-objects exist, to
    # exercise dotted-path resolution (not just top-level scalars).
    for parent, child in (("spectralBalance", None), ("kickDetail", None)):
        node = phase1.get(parent)
        if isinstance(node, dict):
            for child_key, child_val in node.items():
                if isinstance(child_val, (int, float, str)):
                    found.append(f"{parent}.{child_key}")
                    break
    deduped = list(dict.fromkeys(found))
    return (deduped or ["bpm"])[:limit]


def _num(phase1: dict[str, Any], key: str, default: float) -> float:
    value = phase1.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _str(phase1: dict[str, Any], key: str, default: str) -> str:
    value = phase1.get(key)
    return value if isinstance(value, str) and value.strip() else default


def build_mock_phase2_result(
    phase1: dict[str, Any],
    *,
    prompt: str | None = None,
    model_label: str = "moss-mock",
) -> dict[str, Any]:
    """Build a full, schema-valid ``Phase2Result`` grounded in ``phase1``.

    Satisfies every predicate in ``server_phase2._is_valid_phase2_shape`` and
    emits resolving ``phase1Fields`` citations on every cited record.
    """
    bpm = _num(phase1, "bpm", 120.0)
    key = _str(phase1, "key", "C Minor")
    time_signature = _str(phase1, "timeSignature", "4/4")
    sample_rate = int(_num(phase1, "sampleRate", 48000))
    duration = _num(phase1, "durationSeconds", 16.0)
    lufs = phase1.get("lufsIntegrated")
    lufs_text = f"{lufs:.1f} LUFS" if isinstance(lufs, (int, float)) else "the measured loudness"

    cites_loudness = _citations(phase1, 2)
    cites_tempo = _citations(phase1, 1)
    cites_tonal = _citations(phase1, 2)

    return {
        "trackCharacter": (
            f"A {bpm:.0f} BPM piece in {key} ({time_signature}). This is a "
            f"deterministic mock interpretation grounded in Phase 1 ({model_label})."
        ),
        "projectSetup": {
            "tempoBpm": bpm,
            "timeSignature": time_signature,
            "sampleRate": sample_rate,
            "bitDepth": 24,
            "headroomTarget": "-6 dBFS on the master before limiting",
            "sessionGoal": f"Rebuild the track's character at {bpm:.0f} BPM in {key}.",
        },
        "trackLayout": [
            {
                "order": 1,
                "name": "Drums",
                "type": "Drum Rack",
                "purpose": "Foundational groove and transient energy.",
                "grounding": {"phase1Fields": cites_tempo},
            },
            {
                "order": 2,
                "name": "Bass",
                "type": "Instrument",
                "purpose": "Low-end anchor tuned to the detected key.",
                "grounding": {"phase1Fields": cites_tonal},
            },
        ],
        "routingBlueprint": {
            "sidechainSource": "Kick",
            "sidechainTargets": ["Bass", "Pads"],
            "returns": [
                {
                    "name": "A - Reverb",
                    "purpose": "Shared space for melodic elements.",
                    "sendSources": ["Bass", "Lead"],
                    "deviceFocus": "Reverb",
                    "levelGuidance": "Start at -18 dB return level.",
                }
            ],
            "notes": ["Mock routing blueprint grounded in Phase 1 measurements."],
        },
        "warpGuide": {
            "fullTrack": {
                "warpMode": "Complex Pro",
                "settings": "Formants 100, Envelope 128",
                "reason": "Full-mix material warps cleanest under Complex Pro.",
            },
            "drums": {
                "warpMode": "Beats",
                "settings": "Transient Loop Mode: Loop Off",
                "reason": "Percussive transients preserved with Beats mode.",
            },
            "bass": {
                "warpMode": "Complex",
                "reason": "Sustained low end stays stable under Complex.",
            },
            "melodic": {
                "warpMode": "Tones",
                "reason": "Monophonic-leaning melodic content suits Tones.",
            },
            "rationale": f"Warp choices follow the {bpm:.0f} BPM grid measured in Phase 1.",
        },
        "detectedCharacteristics": [
            {
                "name": "Tempo lock",
                "confidence": "HIGH",
                "explanation": f"Phase 1 measured {bpm:.1f} BPM.",
            },
            {
                "name": "Tonal center",
                "confidence": "MED",
                "explanation": f"Phase 1 estimated the key as {key}.",
            },
        ],
        "arrangementOverview": {
            "summary": "A single-loop mock arrangement spanning the measured duration.",
            "segments": [
                {
                    "index": 0,
                    "startTime": 0.0,
                    "endTime": round(duration, 3),
                    "description": "Full loop.",
                    "sceneName": "Loop",
                    "abletonAction": "Duplicate to a 1-bar clip and loop.",
                    "automationFocus": "Filter cutoff sweep over the loop.",
                }
            ],
        },
        "sonicElements": {
            "kick": "Punchy sine-based kick with a short decay.",
            "bass": f"Sub-forward bass tuned to {key}.",
            "melodicArp": "Plucked arpeggio supporting the lead.",
            "grooveAndTiming": f"Straight {time_signature} groove at {bpm:.0f} BPM.",
            "effectsAndTexture": "Light reverb and saturation for glue.",
        },
        "mixAndMasterChain": [
            {
                "order": 1,
                "device": "EQ Eight",
                "deviceFamily": "NATIVE",
                "trackContext": "Master",
                "workflowStage": "MASTER",
                "parameter": "Low Cut",
                "value": "30 Hz, 24 dB/oct",
                "reason": "Clear inaudible sub-rumble below the fundamental.",
                "phase1Fields": cites_tonal,
            },
            {
                "order": 2,
                "device": "Glue Compressor",
                "deviceFamily": "NATIVE",
                "trackContext": "Master",
                "workflowStage": "MASTER",
                "parameter": "Ratio",
                "value": "2:1, slow attack",
                "reason": f"Gentle bus glue toward {lufs_text}.",
                "phase1Fields": cites_loudness,
            },
        ],
        "secretSauce": {
            "title": "Measurement-grounded mock recipe",
            "explanation": "A deterministic recipe demonstrating the citation contract.",
            "implementationSteps": [
                "Set the project tempo to the measured BPM.",
                "Tune the bass to the detected key.",
            ],
            "workflowSteps": [
                {
                    "step": 1,
                    "trackContext": "Master",
                    "device": "Utility",
                    "parameter": "Gain",
                    "value": "0.0 dB",
                    "instruction": "Confirm gain staging before the limiter.",
                    "measurementJustification": f"Targeting {lufs_text} measured in Phase 1.",
                    "phase1Fields": cites_loudness,
                }
            ],
        },
        "confidenceNotes": [
            {
                "field": "key",
                "value": key,
                "reason": "Key estimate carries moderate confidence.",
            }
        ],
        "abletonRecommendations": [
            {
                "device": "Operator",
                "deviceFamily": "NATIVE",
                "trackContext": "Bass",
                "workflowStage": "SOUND_DESIGN",
                "category": "SYNTHESIS",
                "parameter": "Oscillator A Coarse",
                "value": "tuned to the detected key root",
                "reason": f"Anchor the bass to {key}.",
                "advancedTip": "Add a second detuned voice for width.",
                "phase1Fields": cites_tonal,
            },
            {
                "device": "Glue Compressor",
                "deviceFamily": "NATIVE",
                "trackContext": "Master",
                "workflowStage": "MASTER",
                "category": "DYNAMICS",
                "parameter": "Makeup",
                "value": "+2 dB",
                "reason": f"Move loudness toward {lufs_text}.",
                "advancedTip": "Engage soft-clip for extra glue.",
                "phase1Fields": cites_loudness,
            },
        ],
    }

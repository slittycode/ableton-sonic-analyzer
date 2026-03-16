#!/usr/bin/env python3
"""
genre_check.py - DSP preflight reporter.

Takes a Phase 1 JSON file and reports the deterministic DSP signals that should
anchor Gemini's genre reasoning. This script does not emit genre labels.

Usage:
    ./venv/bin/python scripts/genre_check.py <path_to_phase1_json>
"""

import json
import sys
from pathlib import Path
from typing import Any


def safe_get(data: dict, *keys: str, default: Any = None) -> Any:
    """Safely navigate nested dict keys."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is None:
            return default
    return current


def coerce_float(value: Any) -> float | None:
    """Convert numeric-like values to float, otherwise return None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_kick_accent_variance(phase1: dict) -> float | None:
    """Compute variance of grooveDetail.kickAccent (16-value array)."""
    kick_accent = safe_get(phase1, "grooveDetail", "kickAccent")
    if not kick_accent or not isinstance(kick_accent, list):
        return None
    if len(kick_accent) == 0:
        return None

    values = [coerce_float(value) for value in kick_accent if value is not None]
    values = [value for value in values if value is not None]
    if not values:
        return None

    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def classify_rhythm_cluster(
    kick_swing: float | None, kick_accent_variance: float | None
) -> str:
    """Map DSP groove measurements to the broad rhythm-feel cluster."""
    if kick_swing is None or kick_accent_variance is None:
        return "AMBIGUOUS"

    if kick_swing < 0.15 and kick_accent_variance < 0.15:
        return "TIGHT_MECHANICAL"
    if kick_swing > 0.50 and kick_accent_variance < 0.10:
        return "LOOSE_PSYCHEDELIC"
    if kick_swing < 0.12 and kick_accent_variance < 0.05:
        return "NO_PULSE"
    if kick_accent_variance > 0.28:
        return "COMPLEX_BROKEN"
    return "AMBIGUOUS"


def classify_synthesis_tier(inharmonicity: float | None) -> str:
    """Map inharmonicity to a broad synthesis-family tier."""
    if inharmonicity is None:
        return "MIXED"
    if 0.10 <= inharmonicity <= 0.25:
        return "FM_CHARACTER"
    if inharmonicity < 0.10:
        return "SUBTRACTIVE"
    if inharmonicity > 0.25:
        return "WAVETABLE_NOISE"
    return "MIXED"


def detect_sidechain(
    pumping_strength: float | None, pumping_confidence: float | None
) -> str:
    """Report deterministic sidechain detection from the DSP confidence pair."""
    if pumping_strength is None or pumping_confidence is None:
        return "NOT_DETECTED"
    if pumping_strength > 0.35 and pumping_confidence > 0.35:
        return "DETECTED"
    return "NOT_DETECTED"


def format_raw_value(value: Any) -> str:
    """Preserve raw JSON numeric formatting when possible."""
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    return "N/A"


def format_derived_value(value: float | None) -> str:
    """Format derived DSP values for consistent CLI output."""
    if value is None:
        return "N/A"
    return f"{value:.4f}"


def analyze_signals(json_path: str) -> None:
    """Load a Phase 1 payload and print the DSP preflight signals."""
    path = Path(json_path)
    if not path.exists():
        print(f"Error: File not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as error:
        print(f"Error: Invalid JSON: {error}", file=sys.stderr)
        sys.exit(1)

    phase1 = data["phase1"] if isinstance(data.get("phase1"), dict) else data

    raw_bpm = safe_get(phase1, "bpm")
    raw_kick_swing = safe_get(phase1, "grooveDetail", "kickSwing")
    raw_inharmonicity = safe_get(phase1, "synthesisCharacter", "inharmonicity")
    raw_pumping_strength = safe_get(phase1, "sidechainDetail", "pumpingStrength")
    raw_pumping_confidence = safe_get(phase1, "sidechainDetail", "pumpingConfidence")

    kick_swing = coerce_float(raw_kick_swing)
    inharmonicity = coerce_float(raw_inharmonicity)
    pumping_strength = coerce_float(raw_pumping_strength)
    pumping_confidence = coerce_float(raw_pumping_confidence)
    kick_accent_variance = compute_kick_accent_variance(phase1)

    rhythm_cluster = classify_rhythm_cluster(kick_swing, kick_accent_variance)
    synthesis_tier = classify_synthesis_tier(inharmonicity)
    sidechain_status = detect_sidechain(pumping_strength, pumping_confidence)

    print(f"Rhythm cluster: {rhythm_cluster}")
    print(f"Synthesis tier: {synthesis_tier}")
    print(f"Sidechain: {sidechain_status}")
    print(f"BPM: {format_raw_value(raw_bpm)}")
    print(f"kickSwing: {format_derived_value(kick_swing)}")
    print(f"kickAccentVariance: {format_derived_value(kick_accent_variance)}")
    print(f"inharmonicity: {format_derived_value(inharmonicity)}")


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: genre_check.py <path_to_phase1_json>", file=sys.stderr)
        sys.exit(1)

    analyze_signals(sys.argv[1])


if __name__ == "__main__":
    main()

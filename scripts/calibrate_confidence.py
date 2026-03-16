#!/usr/bin/env python3
"""
calibrate_confidence.py — Confidence threshold calibration for ableton-sonic-analyzer.

Uses ground truth dataset to find optimal confidence cutoffs for:
1. pitchConfidence threshold for "melody is draft only"
2. chordStrength threshold for "chords approximate"
3. pumpingConfidence threshold for sidechain detection

Usage:
    python scripts/calibrate_confidence.py
    python scripts/calibrate_confidence.py --ground-truth path/to/labels.json
    python scripts/calibrate_confidence.py --output path/to/results.md

Output:
    docs/confidence_calibration_results.md
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


# Configuration
DEFAULT_GROUND_TRUTH_PATH = "tests/ground_truth/labels.json"
DEFAULT_TRACKS_DIR = "tests/ground_truth/tracks"
DEFAULT_RESULTS_CACHE_DIR = "tests/ground_truth/cache"
DEFAULT_OUTPUT_PATH = "docs/confidence_calibration_results.md"
ANALYZE_SCRIPT_PATH = "apps/backend/analyze.py"

# Threshold ranges to test (as specified in OPTIMIZATION_PLAN.md)
PITCH_CONFIDENCE_THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25]
CHORD_STRENGTH_THRESHOLDS = [0.50, 0.60, 0.70, 0.80, 0.90]
PUMPING_CONFIDENCE_THRESHOLDS = [0.20, 0.30, 0.40, 0.50]

# Current thresholds (for comparison)
CURRENT_PITCH_THRESHOLD = 0.15
CURRENT_CHORD_THRESHOLD = 0.70
CURRENT_PUMPING_THRESHOLD = 0.40


def load_ground_truth(path: str) -> dict[str, Any]:
    """
    Load ground truth labels from JSON file.

    Expected format:
    {
        "track_name": {
            "genre": str,
            "bpm": int,
            "key": str,
            "has_sidechain": bool,
            "melody_accuracy": "high" | "low",
            "chord_accuracy": "high" | "low"
        }
    }

    Returns empty dict if file not found or invalid.
    """
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print(f"[warn] Ground truth file {path} does not contain a JSON object", file=sys.stderr)
            return {}
        return data
    except FileNotFoundError:
        print(f"[warn] Ground truth file not found: {path}", file=sys.stderr)
        return {}
    except json.JSONDecodeError as e:
        print(f"[warn] Invalid JSON in ground truth file: {e}", file=sys.stderr)
        return {}


def load_cached_result(path: str) -> dict[str, Any] | None:
    """Load cached analysis result from JSON file."""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def save_cached_result(path: str, result: dict[str, Any]) -> None:
    """Save analysis result to cache file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(result, f, indent=2)


def run_analysis(audio_path: str, venv_python: str | None = None) -> dict[str, Any] | None:
    """
    Run analyze.py on an audio file and return the parsed JSON result.

    Args:
        audio_path: Path to the audio file
        venv_python: Path to Python interpreter (uses system python if None)

    Returns:
        Parsed analysis result dict or None if analysis failed
    """
    python = venv_python or sys.executable

    # Find analyze.py relative to script location
    script_dir = Path(__file__).parent
    analyze_script = script_dir.parent / ANALYZE_SCRIPT_PATH

    if not analyze_script.exists():
        print(f"[warn] analyze.py not found at {analyze_script}", file=sys.stderr)
        return None

    cmd = [python, str(analyze_script), audio_path, "--yes"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            check=True
        )
        # Parse JSON from stdout (last line should be the JSON output)
        lines = result.stdout.strip().split('\n')
        for line in reversed(lines):
            line = line.strip()
            if line and line.startswith('{'):
                return json.loads(line)
        return None
    except subprocess.TimeoutExpired:
        print(f"[warn] Analysis timed out for {audio_path}", file=sys.stderr)
        return None
    except subprocess.CalledProcessError as e:
        print(f"[warn] Analysis failed for {audio_path}: {e}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"[warn] Failed to parse analysis output for {audio_path}: {e}", file=sys.stderr)
        return None


def extract_pitch_confidence(analysis: dict[str, Any]) -> float | None:
    """Extract pitch confidence from analysis result."""
    melody_detail = analysis.get("melodyDetail")
    if melody_detail is None:
        return None
    return melody_detail.get("pitchConfidence")


def extract_chord_strength(analysis: dict[str, Any]) -> float | None:
    """Extract chord strength from analysis result."""
    chord_detail = analysis.get("chordDetail")
    if chord_detail is None:
        return None
    return chord_detail.get("chordStrength")


def extract_pumping_confidence(analysis: dict[str, Any]) -> float | None:
    """Extract pumping confidence from analysis result."""
    sidechain_detail = analysis.get("sidechainDetail")
    if sidechain_detail is None:
        return None
    return sidechain_detail.get("pumpingConfidence")


def calculate_metrics(y_true: list[bool], y_pred: list[bool]) -> dict[str, float]:
    """
    Calculate precision, recall, and F1 score.

    For all metrics:
    - True Positive: Flagged as low quality AND actually low quality
    - False Positive: Flagged as low quality BUT actually high quality
    - False Negative: NOT flagged as low quality BUT actually low quality

    Args:
        y_true: True labels (True = actually low quality/should flag)
        y_pred: Predicted labels (True = flagged as low quality)

    Returns:
        Dict with precision, recall, and f1 scores
    """
    if not y_true or not y_pred or len(y_true) != len(y_pred):
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    tp = sum(1 for t, p in zip(y_true, y_pred) if t and p)
    fp = sum(1 for t, p in zip(y_true, y_pred) if not t and p)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t and not p)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
    }


def evaluate_pitch_threshold(
    tracks: list[tuple[str, float | None, str]],
    threshold: float
) -> dict[str, Any]:
    """
    Evaluate pitch confidence threshold on labeled tracks.

    Args:
        tracks: List of (track_name, pitch_confidence, melody_accuracy) tuples
                melody_accuracy is "high" or "low"
        threshold: Confidence threshold (flag if below threshold)

    Returns:
        Evaluation metrics dict
    """
    y_true = []
    y_pred = []

    for track_name, pitch_conf, accuracy in tracks:
        if pitch_conf is None:
            continue

        # True label: "low" accuracy should be flagged (True)
        should_flag = accuracy == "low"
        # Prediction: flag if confidence is below threshold
        flagged = pitch_conf < threshold

        y_true.append(should_flag)
        y_pred.append(flagged)

    metrics = calculate_metrics(y_true, y_pred)
    metrics["threshold"] = threshold
    metrics["track_count"] = len(y_true)
    return metrics


def evaluate_chord_threshold(
    tracks: list[tuple[str, float | None, str]],
    threshold: float
) -> dict[str, Any]:
    """
    Evaluate chord strength threshold on labeled tracks.

    Args:
        tracks: List of (track_name, chord_strength, chord_accuracy) tuples
                chord_accuracy is "high" or "low"
        threshold: Strength threshold (flag if below threshold)

    Returns:
        Evaluation metrics dict
    """
    y_true = []
    y_pred = []

    for track_name, chord_strength, accuracy in tracks:
        if chord_strength is None:
            continue

        should_flag = accuracy == "low"
        flagged = chord_strength < threshold

        y_true.append(should_flag)
        y_pred.append(flagged)

    metrics = calculate_metrics(y_true, y_pred)
    metrics["threshold"] = threshold
    metrics["track_count"] = len(y_true)
    return metrics


def evaluate_sidechain_threshold(
    tracks: list[tuple[str, float | None, bool]],
    threshold: float
) -> dict[str, Any]:
    """
    Evaluate pumping confidence threshold on labeled tracks.

    Args:
        tracks: List of (track_name, pumping_confidence, has_sidechain) tuples
        threshold: Confidence threshold (detect if above threshold)

    Returns:
        Evaluation metrics dict
    """
    y_true = []
    y_pred = []

    for track_name, pumping_conf, has_sidechain in tracks:
        if pumping_conf is None:
            continue

        # True label: has_sidechain should be detected (True)
        should_detect = has_sidechain
        # Prediction: detect if confidence is above threshold
        detected = pumping_conf >= threshold

        y_true.append(should_detect)
        y_pred.append(detected)

    metrics = calculate_metrics(y_true, y_pred)
    metrics["threshold"] = threshold
    metrics["track_count"] = len(y_true)
    return metrics


def find_optimal_threshold(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Find threshold with highest F1 score.

    Args:
        results: List of metric dicts from evaluate_*_threshold functions

    Returns:
        Best result dict or None if results is empty
    """
    if not results:
        return None

    # Sort by F1 descending
    best = max(results, key=lambda x: x.get("f1", 0))
    return best


def generate_markdown_report(
    calibration_results: dict[str, Any],
    track_count: int
) -> str:
    """
    Generate markdown report from calibration results.

    Args:
        calibration_results: Dict with calibration results for each metric
        track_count: Number of tracks analyzed

    Returns:
        Markdown-formatted report string
    """
    lines = [
        "# Confidence Calibration Results",
        "",
        "Generated by `scripts/calibrate_confidence.py`",
        "",
        f"Tracks analyzed: {track_count}",
        "",
        "---",
        "",
    ]

    # Pitch Confidence Section
    pitch_results = calibration_results.get("pitch_confidence", {})
    lines.extend([
        "## Pitch Confidence (Melody)",
        "",
        "**Purpose:** Threshold for flagging melody as \"draft only\"",
        "",
        f"**Current threshold:** {CURRENT_PITCH_THRESHOLD}",
        "",
        "### Tested Thresholds",
        "",
        "| Threshold | Precision | Recall | F1 Score | Tracks |",
        "|-----------|-----------|--------|----------|--------|",
    ])

    for result in pitch_results.get("tested_thresholds", []):
        lines.append(
            f"| {result['threshold']:.2f} | {result['precision']:.4f} | "
            f"{result['recall']:.4f} | {result['f1']:.4f} | {result['track_count']} |"
        )

    optimal = pitch_results.get("optimal")
    if optimal:
        lines.extend([
            "",
            f"**Recommended threshold: {optimal['threshold']:.2f}**",
            f"- F1 Score: {optimal['f1']:.4f}",
            f"- Precision: {optimal['precision']:.4f}",
            f"- Recall: {optimal['recall']:.4f}",
        ])
        if optimal["threshold"] != CURRENT_PITCH_THRESHOLD:
            lines.append(
                f"- Change from current: {optimal['threshold'] - CURRENT_PITCH_THRESHOLD:+.2f}"
            )

    # Chord Strength Section
    chord_results = calibration_results.get("chord_strength", {})
    lines.extend([
        "",
        "---",
        "",
        "## Chord Strength",
        "",
        "**Purpose:** Threshold for flagging chords as \"approximate\"",
        "",
        f"**Current threshold:** {CURRENT_CHORD_THRESHOLD}",
        "",
        "### Tested Thresholds",
        "",
        "| Threshold | Precision | Recall | F1 Score | Tracks |",
        "|-----------|-----------|--------|----------|--------|",
    ])

    for result in chord_results.get("tested_thresholds", []):
        lines.append(
            f"| {result['threshold']:.2f} | {result['precision']:.4f} | "
            f"{result['recall']:.4f} | {result['f1']:.4f} | {result['track_count']} |"
        )

    optimal = chord_results.get("optimal")
    if optimal:
        lines.extend([
            "",
            f"**Recommended threshold: {optimal['threshold']:.2f}**",
            f"- F1 Score: {optimal['f1']:.4f}",
            f"- Precision: {optimal['precision']:.4f}",
            f"- Recall: {optimal['recall']:.4f}",
        ])
        if optimal["threshold"] != CURRENT_CHORD_THRESHOLD:
            lines.append(
                f"- Change from current: {optimal['threshold'] - CURRENT_CHORD_THRESHOLD:+.2f}"
            )

    # Pumping Confidence Section
    pumping_results = calibration_results.get("pumping_confidence", {})
    lines.extend([
        "",
        "---",
        "",
        "## Pumping Confidence (Sidechain)",
        "",
        "**Purpose:** Threshold for sidechain detection confidence",
        "",
        f"**Current threshold:** {CURRENT_PUMPING_THRESHOLD}",
        "",
        "### Tested Thresholds",
        "",
        "| Threshold | Precision | Recall | F1 Score | Tracks |",
        "|-----------|-----------|--------|----------|--------|",
    ])

    for result in pumping_results.get("tested_thresholds", []):
        lines.append(
            f"| {result['threshold']:.2f} | {result['precision']:.4f} | "
            f"{result['recall']:.4f} | {result['f1']:.4f} | {result['track_count']} |"
        )

    optimal = pumping_results.get("optimal")
    if optimal:
        lines.extend([
            "",
            f"**Recommended threshold: {optimal['threshold']:.2f}**",
            f"- F1 Score: {optimal['f1']:.4f}",
            f"- Precision: {optimal['precision']:.4f}",
            f"- Recall: {optimal['recall']:.4f}",
        ])
        if optimal["threshold"] != CURRENT_PUMPING_THRESHOLD:
            lines.append(
                f"- Change from current: {optimal['threshold'] - CURRENT_PUMPING_THRESHOLD:+.2f}"
            )

    # Summary Section
    lines.extend([
        "",
        "---",
        "",
        "## Summary of Recommendations",
        "",
        "| Metric | Current | Recommended | Change | Justification |",
        "|--------|---------|-------------|--------|---------------|",
    ])

    pitch_opt = calibration_results.get("pitch_confidence", {}).get("optimal", {})
    chord_opt = calibration_results.get("chord_strength", {}).get("optimal", {})
    pumping_opt = calibration_results.get("pumping_confidence", {}).get("optimal", {})

    pitch_rec = pitch_opt.get("threshold", CURRENT_PITCH_THRESHOLD)
    chord_rec = chord_opt.get("threshold", CURRENT_CHORD_THRESHOLD)
    pumping_rec = pumping_opt.get("threshold", CURRENT_PUMPING_THRESHOLD)

    lines.append(
        f"| Pitch Confidence | {CURRENT_PITCH_THRESHOLD:.2f} | {pitch_rec:.2f} | "
        f"{pitch_rec - CURRENT_PITCH_THRESHOLD:+.2f} | F1={pitch_opt.get('f1', 0):.4f} |"
    )
    lines.append(
        f"| Chord Strength | {CURRENT_CHORD_THRESHOLD:.2f} | {chord_rec:.2f} | "
        f"{chord_rec - CURRENT_CHORD_THRESHOLD:+.2f} | F1={chord_opt.get('f1', 0):.4f} |"
    )
    lines.append(
        f"| Pumping Confidence | {CURRENT_PUMPING_THRESHOLD:.2f} | {pumping_rec:.2f} | "
        f"{pumping_rec - CURRENT_PUMPING_THRESHOLD:+.2f} | F1={pumping_opt.get('f1', 0):.4f} |"
    )

    lines.extend([
        "",
        "## Justification",
        "",
        "Thresholds are selected to maximize F1 score, which balances:",
        "- **Precision:** Of tracks flagged as low confidence, how many were actually wrong?",
        "- **Recall:** Of tracks that were actually wrong, how many were flagged?",
        "",
        "Higher precision means fewer false alarms (flagging good tracks as bad).",
        "Higher recall means fewer missed issues (bad tracks flagged as good).",
        "F1 balances these concerns equally.",
        "",
        "## Implementation Notes",
        "",
        "To apply these thresholds:",
        "",
        "1. Update the prompt in `apps/ui/src/services/geminiPhase2Client.ts`:",
        "   - `pitchConfidence < X = melody is draft only`",
        "   - `chordStrength < X = chords approximate`",
        "   - `pumpingConfidence < X = do not assert sidechain`",
        "",
        "2. Update UI components that use these thresholds",
        "",
        "3. Document any genre-specific exceptions in genre_corpus.md",
        "",
    ])

    return "\n".join(lines)


def run_calibration(
    ground_truth_path: str,
    tracks_dir: str,
    cache_dir: str | None = None,
    venv_python: str | None = None
) -> dict[str, Any]:
    """
    Run full calibration process.

    Args:
        ground_truth_path: Path to ground truth labels JSON
        tracks_dir: Directory containing audio tracks
        cache_dir: Directory for caching analysis results (optional)
        venv_python: Path to Python interpreter for analysis

    Returns:
        Calibration results dict
    """
    # Load ground truth
    ground_truth = load_ground_truth(ground_truth_path)
    if not ground_truth:
        print("[error] No ground truth data available", file=sys.stderr)
        return {}

    print(f"Loaded ground truth for {len(ground_truth)} tracks")

    # Prepare track data
    pitch_tracks = []
    chord_tracks = []
    sidechain_tracks = []

    for track_name, labels in ground_truth.items():
        # Check if track has audio file
        audio_path = os.path.join(tracks_dir, f"{track_name}.mp3")
        if not os.path.exists(audio_path):
            # Try other extensions
            for ext in [".wav", ".flac", ".aif", ".aiff"]:
                alt_path = os.path.join(tracks_dir, f"{track_name}{ext}")
                if os.path.exists(alt_path):
                    audio_path = alt_path
                    break

        # Load or run analysis
        analysis = None
        if cache_dir:
            cache_path = os.path.join(cache_dir, f"{track_name}.json")
            analysis = load_cached_result(cache_path)

        if analysis is None and os.path.exists(audio_path):
            print(f"Analyzing {track_name}...", file=sys.stderr)
            analysis = run_analysis(audio_path, venv_python)
            if analysis and cache_dir:
                cache_path = os.path.join(cache_dir, f"{track_name}.json")
                save_cached_result(cache_path, analysis)

        if analysis is None:
            print(f"[warn] No analysis available for {track_name}", file=sys.stderr)
            continue

        # Extract values for each metric
        pitch_conf = extract_pitch_confidence(analysis)
        melody_accuracy = labels.get("melody_accuracy")
        if pitch_conf is not None and melody_accuracy in ("high", "low"):
            pitch_tracks.append((track_name, pitch_conf, melody_accuracy))

        chord_strength = extract_chord_strength(analysis)
        chord_accuracy = labels.get("chord_accuracy")
        if chord_strength is not None and chord_accuracy in ("high", "low"):
            chord_tracks.append((track_name, chord_strength, chord_accuracy))

        pumping_conf = extract_pumping_confidence(analysis)
        has_sidechain = labels.get("has_sidechain")
        if pumping_conf is not None and isinstance(has_sidechain, bool):
            sidechain_tracks.append((track_name, pumping_conf, has_sidechain))

    print(f"Tracks with pitch data: {len(pitch_tracks)}")
    print(f"Tracks with chord data: {len(chord_tracks)}")
    print(f"Tracks with sidechain data: {len(sidechain_tracks)}")

    # Evaluate all thresholds
    results = {
        "pitch_confidence": {
            "current_threshold": CURRENT_PITCH_THRESHOLD,
            "tested_thresholds": [],
            "optimal": None,
        },
        "chord_strength": {
            "current_threshold": CURRENT_CHORD_THRESHOLD,
            "tested_thresholds": [],
            "optimal": None,
        },
        "pumping_confidence": {
            "current_threshold": CURRENT_PUMPING_THRESHOLD,
            "tested_thresholds": [],
            "optimal": None,
        },
    }

    # Pitch confidence thresholds
    if pitch_tracks:
        for threshold in PITCH_CONFIDENCE_THRESHOLDS:
            metrics = evaluate_pitch_threshold(pitch_tracks, threshold)
            results["pitch_confidence"]["tested_thresholds"].append(metrics)

        results["pitch_confidence"]["optimal"] = find_optimal_threshold(
            results["pitch_confidence"]["tested_thresholds"]
        )

    # Chord strength thresholds
    if chord_tracks:
        for threshold in CHORD_STRENGTH_THRESHOLDS:
            metrics = evaluate_chord_threshold(chord_tracks, threshold)
            results["chord_strength"]["tested_thresholds"].append(metrics)

        results["chord_strength"]["optimal"] = find_optimal_threshold(
            results["chord_strength"]["tested_thresholds"]
        )

    # Pumping confidence thresholds
    if sidechain_tracks:
        for threshold in PUMPING_CONFIDENCE_THRESHOLDS:
            metrics = evaluate_sidechain_threshold(sidechain_tracks, threshold)
            results["pumping_confidence"]["tested_thresholds"].append(metrics)

        results["pumping_confidence"]["optimal"] = find_optimal_threshold(
            results["pumping_confidence"]["tested_thresholds"]
        )

    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Calibrate confidence thresholds for ableton-sonic-analyzer"
    )
    parser.add_argument(
        "--ground-truth",
        default=DEFAULT_GROUND_TRUTH_PATH,
        help=f"Path to ground truth labels JSON (default: {DEFAULT_GROUND_TRUTH_PATH})"
    )
    parser.add_argument(
        "--tracks-dir",
        default=DEFAULT_TRACKS_DIR,
        help=f"Directory containing audio tracks (default: {DEFAULT_TRACKS_DIR})"
    )
    parser.add_argument(
        "--cache-dir",
        default=DEFAULT_RESULTS_CACHE_DIR,
        help=f"Directory for caching analysis results (default: {DEFAULT_RESULTS_CACHE_DIR})"
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output markdown file path (default: {DEFAULT_OUTPUT_PATH})"
    )
    parser.add_argument(
        "--venv-python",
        help="Path to Python interpreter with analyze.py dependencies"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable result caching"
    )

    args = parser.parse_args()

    cache_dir = None if args.no_cache else args.cache_dir

    # Run calibration
    results = run_calibration(
        args.ground_truth,
        args.tracks_dir,
        cache_dir,
        args.venv_python
    )

    if not results:
        print("[error] Calibration failed - no results generated", file=sys.stderr)
        sys.exit(1)

    # Count tracks analyzed
    track_count = max(
        results.get("pitch_confidence", {}).get("tested_thresholds", [{}])[0].get("track_count", 0),
        results.get("chord_strength", {}).get("tested_thresholds", [{}])[0].get("track_count", 0),
        results.get("pumping_confidence", {}).get("tested_thresholds", [{}])[0].get("track_count", 0),
    )

    # Generate report
    report = generate_markdown_report(results, track_count)

    # Write output
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w') as f:
        f.write(report)

    print(f"\nCalibration complete. Report written to: {args.output}")

    # Print summary
    print("\n=== SUMMARY ===")
    pitch_opt = results.get("pitch_confidence", {}).get("optimal", {})
    chord_opt = results.get("chord_strength", {}).get("optimal", {})
    pumping_opt = results.get("pumping_confidence", {}).get("optimal", {})

    if pitch_opt:
        print(f"Pitch Confidence:   {CURRENT_PITCH_THRESHOLD:.2f} -> {pitch_opt['threshold']:.2f} "
              f"(F1={pitch_opt['f1']:.4f})")
    if chord_opt:
        print(f"Chord Strength:     {CURRENT_CHORD_THRESHOLD:.2f} -> {chord_opt['threshold']:.2f} "
              f"(F1={chord_opt['f1']:.4f})")
    if pumping_opt:
        print(f"Pumping Confidence: {CURRENT_PUMPING_THRESHOLD:.2f} -> {pumping_opt['threshold']:.2f} "
              f"(F1={pumping_opt['f1']:.4f})")


if __name__ == "__main__":
    main()

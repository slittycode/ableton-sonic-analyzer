#!/usr/bin/env python3
"""Offline SBic structure sweep for parameter selection diagnostics."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import analyze  # noqa: E402

CPW_VALUES = [0.5, 0.7, 0.9, 1.1, 1.3, 1.5]
WINDOW_BUNDLES = [
    {
        "bundleId": "w1_fast_local",
        "size1": 220,
        "size2": 120,
        "inc1": 36,
        "inc2": 12,
        "minLength": 16,
    },
    {
        "bundleId": "w2_balanced",
        "size1": 260,
        "size2": 140,
        "inc1": 44,
        "inc2": 14,
        "minLength": 20,
    },
    {
        "bundleId": "w3_default_windows",
        "size1": 300,
        "size2": 200,
        "inc1": 60,
        "inc2": 20,
        "minLength": 24,
    },
]
FEATURE_PRESETS = ["mfcc_z", "mfcc_delta_z"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate structure segmentation tuning combinations and produce "
            "ranked diagnostics."
        )
    )
    parser.add_argument(
        "--audio",
        nargs="+",
        required=True,
        help="Audio file paths to score (e.g. Vtss + short + long sanity clips).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_DIR / ".runtime" / "reports",
        help="Directory for structure_sweep_results.json and structure_sweep_summary.md",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of top-ranked configurations to include in summary (default: 5).",
    )
    return parser.parse_args()


def _safe_float(value: float | int | None) -> float | None:
    if value is None:
        return None
    val = float(value)
    if not np.isfinite(val):
        return None
    return val


def _snap_boundaries(
    boundaries_seconds: np.ndarray,
    downbeats: np.ndarray,
    median_beat_interval: float | None,
) -> np.ndarray:
    if boundaries_seconds.size == 0 or downbeats.size == 0 or median_beat_interval is None:
        return boundaries_seconds

    snap_threshold = min(analyze.STRUCTURE_SNAP_THRESHOLD_SECONDS, 0.5 * median_beat_interval)
    snapped = [float(boundaries_seconds[0])]
    for boundary in boundaries_seconds[1:-1]:
        nearest_downbeat = float(downbeats[np.argmin(np.abs(downbeats - boundary))])
        if abs(nearest_downbeat - float(boundary)) <= snap_threshold:
            snapped.append(nearest_downbeat)
        else:
            snapped.append(float(boundary))
    snapped.append(float(boundaries_seconds[-1]))
    return np.unique(np.asarray(snapped, dtype=np.float64))


def _downbeat_alignment_rate(
    boundaries_seconds: np.ndarray,
    downbeats: np.ndarray,
    median_beat_interval: float | None,
) -> float | None:
    if boundaries_seconds.size <= 2 or downbeats.size == 0 or median_beat_interval is None:
        return None

    snap_threshold = min(analyze.STRUCTURE_SNAP_THRESHOLD_SECONDS, 0.5 * median_beat_interval)
    interior = boundaries_seconds[1:-1]
    if interior.size == 0:
        return None

    aligned = 0
    for boundary in interior:
        nearest = float(downbeats[np.argmin(np.abs(downbeats - boundary))])
        if abs(nearest - float(boundary)) <= snap_threshold:
            aligned += 1
    return round(float(aligned) / float(interior.size), 4)


def _segment_lengths(segments: list[dict[str, float | int]]) -> np.ndarray:
    if not segments:
        return np.asarray([], dtype=np.float64)
    values = []
    for segment in segments:
        start = _safe_float(segment.get("start"))
        end = _safe_float(segment.get("end"))
        if start is None or end is None:
            continue
        if end > start:
            values.append(end - start)
    return np.asarray(values, dtype=np.float64)


def _score_segments(duration: float, segment_lengths: np.ndarray) -> tuple[float, float, float]:
    segment_count = int(segment_lengths.size)
    coarse_penalty = max(0.0, float(analyze.STRUCTURE_COARSE_MIN_SEGMENT_COUNT - segment_count))
    micro_segment_penalty = float(np.sum(segment_lengths < 5.0)) if segment_count > 0 else 1.0

    if segment_count == 0:
        return 0.0, coarse_penalty, micro_segment_penalty

    if segment_count < 4:
        count_penalty = float(4 - segment_count)
    elif segment_count > 8:
        count_penalty = float(segment_count - 8)
    else:
        count_penalty = 0.0

    target_median = duration / 6.0 if duration > 0 else 0.0
    median_duration = float(np.median(segment_lengths))
    median_penalty = abs(median_duration - target_median) / max(target_median, 1.0)

    raw_score = 100.0
    raw_score -= 14.0 * count_penalty
    raw_score -= 10.0 * coarse_penalty
    raw_score -= 8.0 * micro_segment_penalty
    raw_score -= 12.0 * median_penalty

    score = max(0.0, round(raw_score, 4))
    return score, round(coarse_penalty, 4), round(micro_segment_penalty, 4)


def _evaluate_config_for_track(
    mono: np.ndarray,
    sample_rate: int,
    rhythm_data: dict | None,
    duration: float,
    feature_preset: str,
    sbic_params: dict,
) -> dict:
    feature_payload = analyze._extract_structure_feature_matrix(
        mono,
        sample_rate,
        feature_preset=feature_preset,
        frame_size=analyze.STRUCTURE_FRAME_SIZE,
        hop_size=analyze.STRUCTURE_HOP_SIZE,
    )
    if feature_payload is None:
        return {
            "segmentCountPreMerge": 0,
            "segmentCountPostMerge": 0,
            "minSegmentSec": None,
            "medianSegmentSec": None,
            "maxSegmentSec": None,
            "downbeatAlignmentRate": None,
            "coarsePenalty": 4.0,
            "microSegmentPenalty": 1.0,
            "score": 0.0,
            "mergePolicies": {},
        }

    feature_matrix, hop_size = feature_payload
    boundaries_seconds = analyze._run_structure_sbic_boundaries(
        feature_matrix,
        sample_rate=sample_rate,
        hop_size=hop_size,
        sbic_params=sbic_params,
    )
    boundaries_seconds = analyze._normalize_structure_boundaries(boundaries_seconds, duration)

    downbeats, median_beat_interval = analyze._resolve_downbeats_and_interval(rhythm_data)
    boundaries_seconds = _snap_boundaries(boundaries_seconds, downbeats, median_beat_interval)
    boundaries_seconds = analyze._normalize_structure_boundaries(boundaries_seconds, duration)

    segment_count_pre = int(max(boundaries_seconds.size - 1, 0))
    downbeat_rate = _downbeat_alignment_rate(boundaries_seconds, downbeats, median_beat_interval)

    merge_policy_details = {}
    selected_policy_segments: list[dict[str, float | int]] = []
    for policy_name in ("baseline", "adaptive_clamped"):
        floor = analyze._compute_structure_merge_floor(
            duration,
            median_beat_interval=median_beat_interval,
            policy=policy_name,
        )
        merged = analyze._merge_short_structure_segments(
            analyze._boundaries_to_structure_segments(boundaries_seconds),
            minimum_duration_seconds=floor,
        )
        merged = merged[: analyze.STRUCTURE_MAX_SEGMENTS]
        lengths = _segment_lengths(merged)
        merge_policy_details[policy_name] = {
            "mergeFloorSeconds": round(float(floor), 4),
            "segmentCount": int(len(merged)),
            "minSegmentSec": round(float(np.min(lengths)), 4) if lengths.size else None,
            "medianSegmentSec": round(float(np.median(lengths)), 4) if lengths.size else None,
            "maxSegmentSec": round(float(np.max(lengths)), 4) if lengths.size else None,
        }
        if policy_name == analyze.STRUCTURE_MERGE_POLICY:
            selected_policy_segments = merged

    if not selected_policy_segments:
        selected_policy_segments = analyze._merge_short_structure_segments(
            analyze._boundaries_to_structure_segments(boundaries_seconds),
            minimum_duration_seconds=analyze._compute_structure_merge_floor(
                duration,
                median_beat_interval=median_beat_interval,
            ),
        )

    selected_lengths = _segment_lengths(selected_policy_segments)
    score, coarse_penalty, micro_penalty = _score_segments(duration, selected_lengths)

    return {
        "segmentCountPreMerge": segment_count_pre,
        "segmentCountPostMerge": int(len(selected_policy_segments)),
        "minSegmentSec": round(float(np.min(selected_lengths)), 4) if selected_lengths.size else None,
        "medianSegmentSec": round(float(np.median(selected_lengths)), 4) if selected_lengths.size else None,
        "maxSegmentSec": round(float(np.max(selected_lengths)), 4) if selected_lengths.size else None,
        "downbeatAlignmentRate": downbeat_rate,
        "coarsePenalty": coarse_penalty,
        "microSegmentPenalty": micro_penalty,
        "score": score,
        "mergePolicies": merge_policy_details,
    }


def _aggregate_metrics(metrics_by_track: list[dict]) -> dict:
    def _mean(key: str) -> float | None:
        values = [float(item[key]) for item in metrics_by_track if item.get(key) is not None]
        if not values:
            return None
        return round(float(statistics.mean(values)), 4)

    return {
        "segmentCountPreMerge": _mean("segmentCountPreMerge"),
        "segmentCountPostMerge": _mean("segmentCountPostMerge"),
        "minSegmentSec": _mean("minSegmentSec"),
        "medianSegmentSec": _mean("medianSegmentSec"),
        "maxSegmentSec": _mean("maxSegmentSec"),
        "downbeatAlignmentRate": _mean("downbeatAlignmentRate"),
        "coarsePenalty": _mean("coarsePenalty"),
        "microSegmentPenalty": _mean("microSegmentPenalty"),
        "score": _mean("score") or 0.0,
    }


def _build_config_records(audio_tracks: list[dict]) -> list[dict]:
    records = []
    for feature_preset in FEATURE_PRESETS:
        for bundle in WINDOW_BUNDLES:
            for cpw in CPW_VALUES:
                sbic_params = {
                    "cpw": cpw,
                    "size1": bundle["size1"],
                    "size2": bundle["size2"],
                    "inc1": bundle["inc1"],
                    "inc2": bundle["inc2"],
                    "minLength": bundle["minLength"],
                }
                config_id = (
                    f"{feature_preset}-cpw{cpw:.1f}-{bundle['bundleId']}"
                )
                metrics_by_track = []
                for track in audio_tracks:
                    metrics = _evaluate_config_for_track(
                        mono=track["mono"],
                        sample_rate=track["sample_rate"],
                        rhythm_data=track["rhythm_data"],
                        duration=track["duration"],
                        feature_preset=feature_preset,
                        sbic_params=sbic_params,
                    )
                    metrics_by_track.append(
                        {
                            "trackPath": track["path"],
                            **metrics,
                        }
                    )

                aggregate = _aggregate_metrics(metrics_by_track)
                records.append(
                    {
                        "configId": config_id,
                        "featurePreset": feature_preset,
                        "cpw": cpw,
                        **bundle,
                        "metricsByTrack": metrics_by_track,
                        "aggregate": aggregate,
                    }
                )
    return records


def _write_summary(
    output_path: Path,
    winner: dict,
    ranked: list[dict],
    top_k: int,
) -> None:
    top_rows = ranked[: max(top_k, 1)]
    near_misses = ranked[1:4]

    lines = []
    lines.append("# Structure Sweep Summary")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append("## Selected Winner")
    lines.append("")
    lines.append(f"- configId: `{winner['configId']}`")
    lines.append(f"- featurePreset: `{winner['featurePreset']}`")
    lines.append(f"- cpw: `{winner['cpw']}`")
    lines.append(
        "- SBic window bundle: "
        f"size1={winner['size1']} size2={winner['size2']} "
        f"inc1={winner['inc1']} inc2={winner['inc2']} minLength={winner['minLength']}"
    )
    lines.append(f"- aggregate score: `{winner['aggregate']['score']}`")
    lines.append(
        "- rationale: best combined score with acceptable post-merge segment density "
        "and low micro/coarse penalties across provided tracks."
    )
    lines.append("")
    lines.append("## Top Ranked Configurations")
    lines.append("")
    lines.append("| Rank | configId | score | postMergeCount | medianSegSec | coarsePenalty | microPenalty |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for idx, row in enumerate(top_rows, start=1):
        agg = row["aggregate"]
        lines.append(
            "| "
            f"{idx} | `{row['configId']}` | {agg['score']} | {agg['segmentCountPostMerge']} "
            f"| {agg['medianSegmentSec']} | {agg['coarsePenalty']} | {agg['microSegmentPenalty']} |"
        )

    if near_misses:
        lines.append("")
        lines.append("## Rejected Near-Misses")
        lines.append("")
        for row in near_misses:
            agg = row["aggregate"]
            reasons = []
            if (agg.get("coarsePenalty") or 0) > (winner["aggregate"].get("coarsePenalty") or 0):
                reasons.append("higher coarse penalty")
            if (agg.get("microSegmentPenalty") or 0) > (winner["aggregate"].get("microSegmentPenalty") or 0):
                reasons.append("more micro-segments")
            if (agg.get("segmentCountPostMerge") or 0) < 4:
                reasons.append("post-merge segments below target")
            if not reasons:
                reasons.append("lower overall score")
            lines.append(f"- `{row['configId']}`: {', '.join(reasons)}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    audio_tracks = []
    for raw_path in args.audio:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Audio path not found: {path}")

        mono = analyze.load_mono(str(path), sample_rate=44_100)
        rhythm_data = analyze.extract_rhythm(mono)
        duration = float(len(mono) / 44_100) if mono.size > 0 else 0.0
        audio_tracks.append(
            {
                "path": str(path),
                "mono": mono,
                "sample_rate": 44_100,
                "rhythm_data": rhythm_data,
                "duration": duration,
            }
        )

    configs = _build_config_records(audio_tracks)
    ranked = sorted(configs, key=lambda row: float(row["aggregate"]["score"]), reverse=True)
    winner = ranked[0] if ranked else None

    results_payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "targetDurationRangeSeconds": [
            analyze.STRUCTURE_TARGET_DURATION_MIN_SECONDS,
            analyze.STRUCTURE_TARGET_DURATION_MAX_SECONDS,
        ],
        "mergePolicyUnderTest": analyze.STRUCTURE_MERGE_POLICY,
        "audioFiles": [
            {
                "path": item["path"],
                "durationSeconds": round(float(item["duration"]), 4),
                "bpm": (
                    round(float(item["rhythm_data"].get("bpm", 0.0)), 3)
                    if isinstance(item["rhythm_data"], dict)
                    else None
                ),
            }
            for item in audio_tracks
        ],
        "cpwValues": CPW_VALUES,
        "windowBundles": WINDOW_BUNDLES,
        "featurePresets": FEATURE_PRESETS,
        "configs": configs,
        "rankedConfigIds": [row["configId"] for row in ranked],
        "winnerConfigId": winner["configId"] if winner else None,
    }

    results_path = output_dir / "structure_sweep_results.json"
    summary_path = output_dir / "structure_sweep_summary.md"

    results_path.write_text(json.dumps(results_payload, indent=2), encoding="utf-8")
    if winner is not None:
        _write_summary(summary_path, winner=winner, ranked=ranked, top_k=args.top_k)

    print(json.dumps({
        "resultsPath": str(results_path),
        "summaryPath": str(summary_path),
        "winnerConfigId": results_payload["winnerConfigId"],
    }, indent=2))


if __name__ == "__main__":
    main()

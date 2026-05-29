"""Analysis estimation and CLI confirmation utilities."""

import os
import sys

import numpy as np

try:
    import essentia.standard as es
except ImportError:
    es = None


def _format_duration_label(seconds: float) -> str:
    total_seconds = max(0, int(round(float(seconds))))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


def _estimate_stage_seconds(
    duration_seconds: float,
    min_ratio: float,
    max_ratio: float,
    min_overhead: float,
    max_overhead: float,
) -> dict:
    safe_duration = max(0.0, float(duration_seconds))
    stage_min = max(min_overhead, safe_duration * min_ratio)
    stage_max = max(max_overhead, safe_duration * max_ratio)
    if stage_max < stage_min:
        stage_max = stage_min
    return {
        "min": int(round(stage_min)),
        "max": int(round(stage_max)),
    }


def get_audio_duration_seconds(audio_path: str) -> float | None:
    try:
        reader = es.MetadataReader(filename=audio_path)
        metadata = dict(zip(reader.outputNames(), reader()))
        duration_seconds = metadata.get("duration")
        if duration_seconds is None:
            return None
        duration_value = float(duration_seconds)
        return (
            duration_value
            if np.isfinite(duration_value) and duration_value > 0
            else None
        )
    except Exception:
        return None


def build_analysis_estimate(
    duration_seconds: float,
    run_separation: bool,
    run_transcribe: bool,
    run_fast: bool = False,
    run_standard: bool = False,
    run_mt3: bool = False,
) -> dict:
    stages = []

    if run_fast:
        dsp_seconds = _estimate_stage_seconds(
            duration_seconds, 0.01, 0.03, 3.0, 10.0
        )
    elif run_standard:
        dsp_seconds = _estimate_stage_seconds(
            duration_seconds, 0.03, 0.08, 10.0, 25.0
        )
    else:
        dsp_seconds = _estimate_stage_seconds(
            duration_seconds, 0.06, 0.14, 20.0, 45.0
        )
    stages.append(
        {
            "key": "dsp",
            "label": "DSP analysis",
            "seconds": dsp_seconds,
        }
    )

    if run_separation:
        separation_seconds = _estimate_stage_seconds(
            duration_seconds, 0.16, 0.32, 45.0, 90.0
        )
        stages.append(
            {
                "key": "separation",
                "label": "Demucs separation",
                "seconds": separation_seconds,
            }
        )

    if run_transcribe:
        transcription_key = (
            "transcription_stems" if run_separation else "transcription_full_mix"
        )
        transcription_label = (
            "Torchcrepe on bass + other stems"
            if run_separation
            else "Torchcrepe on full mix"
        )
        transcription_seconds = (
            _estimate_stage_seconds(duration_seconds, 0.22, 0.42, 60.0, 150.0)
            if run_separation
            else _estimate_stage_seconds(duration_seconds, 0.10, 0.22, 25.0, 75.0)
        )
        stages.append(
            {
                "key": transcription_key,
                "label": transcription_label,
                "seconds": transcription_seconds,
            }
        )

    if run_mt3:
        # MT3 cost model: high fixed overhead from JAX/t5x model load
        # (~30-60s on first call, multi-GB weights), then per-second
        # inference ranging ~0.2-0.8x duration on CPU. On a 4-min track
        # this lands around 60s-200s; on a 10s clip it's overhead-bound
        # at ~60-180s. Numbers tuned to be conservative — operator-facing
        # UIs should err high so users aren't surprised mid-run.
        mt3_seconds = _estimate_stage_seconds(
            duration_seconds, 0.20, 0.80, 60.0, 180.0
        )
        stages.append(
            {
                "key": "mt3_transcription",
                "label": "MT3 polyphonic transcription",
                "seconds": mt3_seconds,
            }
        )

    total_min = sum(stage["seconds"]["min"] for stage in stages)
    total_max = sum(stage["seconds"]["max"] for stage in stages)

    return {
        "durationSeconds": round(float(duration_seconds), 1),
        "stages": stages,
        "totalSeconds": {
            "min": total_min,
            "max": total_max,
        },
    }


def print_analysis_estimate(audio_path: str, estimate: dict) -> None:
    print(
        f"Estimated analysis time for {os.path.basename(audio_path)}: "
        f"{_format_duration_label(estimate['totalSeconds']['min'])}-"
        f"{_format_duration_label(estimate['totalSeconds']['max'])}",
        file=sys.stderr,
    )
    for stage in estimate.get("stages", []):
        seconds = stage.get("seconds", {})
        print(
            f"- {stage.get('label')}: "
            f"{_format_duration_label(seconds.get('min', 0))}-"
            f"{_format_duration_label(seconds.get('max', 0))}",
            file=sys.stderr,
        )


def should_prompt_for_confirmation(is_tty: bool, auto_yes: bool) -> bool:
    return bool(is_tty) and not auto_yes


def prompt_to_continue() -> bool:
    try:
        response = input("Continue? [y/N]: ").strip().lower()
    except EOFError:
        return False
    return response in {"y", "yes"}
